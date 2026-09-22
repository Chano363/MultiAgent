"""统一训练框架：TrainRunner —— 单一路径外层骨架 + 内建基建。

统一承载：seed/device/OMP、SimCase 门禁、training_metadata_guard（自动落 metadata +
结束强制校验）、curriculum（全局回合号地平线）、init_speed、内层逐步循环
（decision_interval 半MDP / reward 覆盖 / 车钩力指标）、best/periodic checkpoint、周期日志、
artifacts 落盘、resume 历史恢复。

【后续新增实验线】= 新写 configs/experiments/*.yaml + 注册一项（如新算法），不改本文件。
"""
import json
import logging
import os
import time
from pathlib import Path

import numpy as np
import torch
from src.utils.seed import set_seed

from src.metadata import training_metadata_guard, build_metadata
from src.physics_config import PhysicsConfig
from src.physics_governance import SimCase, official_world_config, assert_case_allows
from src.trainer.config_schema import cfg_to_dict

from src.trainer.registry import Registry
from src.trainer.ckpt_policy import make_namer
from src.trainer.artifacts import save_training_artifacts
from src.trainer.specs.cyclic_spec import cyclic_obs, cyclic_reward, quantize_to_notch, set_cyclic_limits
from src.environments.train_fleet_env import TrainFleetEnv

logger = logging.getLogger('TrainRunner')




class TrainRunner:
    def __init__(self, cfg):
        self.cfg = cfg

    # ------------------------------------------------------------------
    def run(self) -> dict:
        cfg = self.cfg
        os.makedirs(cfg.results_dir, exist_ok=True)
        os.makedirs(cfg.checkpoint_dir, exist_ok=True)

        device = cfg.device or ('cuda' if torch.cuda.is_available() else 'cpu')
        if cfg.omp_num_threads:
            torch.set_num_threads(max(1, int(cfg.omp_num_threads)))
            os.environ.setdefault('OMP_NUM_THREADS', str(cfg.omp_num_threads))
            os.environ.setdefault('MKL_NUM_THREADS', str(cfg.omp_num_threads))
        set_seed(cfg.seed)

        # cyclic 限速按配置显式设置（cyclic_obs/cyclic_reward 用）
        if cfg.obs == 'cyclic' or cfg.reward == 'cyclic':
            set_cyclic_limits(
                v_max_mps=cfg.env_cfg.get('v_max', 80.0 / 3.6),
                v_min_mps=cfg.env_cfg.get('v_min', 40.0 / 3.6))

        env, agents, inter = Registry.build(cfg, device)
        if isinstance(agents, list):
            num_agents = len(agents)
        else:
            num_agents = int(getattr(env, 'num_agents', 0)) or int(getattr(env, 'num_trains', 1))
        act_dim = int(getattr(env, 'act_dim', 1)) or int(cfg.env_cfg.get('action_dim', 1))
        namer = make_namer(cfg, act_dim=act_dim, num_trains=num_agents)

        world_cfg = official_world_config(PhysicsConfig())
        # 自包含 checkpoint：权威 metadata 嵌入每个 .pt（对标 YOLO best.pt，
        # 2026-09-10），与 metadata.json 双轨——权重单文件即可溯源复现。
        self._ckpt_meta = build_metadata(
            project_root=str(Path(__file__).parent.parent.parent),
            case=cfg.simcase, world_cfg=world_cfg, seed=cfg.seed,
            entry="run_training.py",
            extra={"hyperparameters": cfg_to_dict(cfg)})
        with training_metadata_guard(cfg.results_dir, world_cfg=world_cfg,
                                     seed=cfg.seed, simcase=cfg.simcase,
                                     entry="run_training.py",
                                     extra={"hyperparameters": cfg_to_dict(cfg)}):
            case = SimCase(cfg.simcase)
            assert_case_allows(case, world_cfg, __file__)

            # warm start（L1 BC 预训练 / fleet decompose BC）
            if cfg.warm_start and cfg.obs == 'cyclic':
                from src.trainer.specs.cyclic_spec import warm_start_bc
                warm_start_bc(inter.agent, env, env.num_vehicles, cyclic_obs,
                              v_max=cfg.env_cfg.get('v_max', 80.0 / 3.6),
                              v_min=cfg.env_cfg.get('v_min', 40.0 / 3.6),
                              episodes=cfg.bc_episodes, bc_epochs=cfg.bc_epochs,
                              brake_notch=cfg.brake_notch)
            elif cfg.warm_start and getattr(env, 'decompose', None):
                # 【2026-09-10】decompose 6 机车编队：BC 自确定性规则基线（[0,0] 即复现
                # 规则循环制动），治诊断-2026-09-10 长时程随机探索踩暴力 AB 吸态。
                from src.trainer.specs.fleet_spec import warm_start_decompose_bc
                warm_start_decompose_bc(
                    inter.agent, env,
                    episodes=cfg.bc_episodes, bc_epochs=cfg.bc_epochs,
                    init_speed=cfg.env_cfg.get('init_speed_kmh', 80.0) / 3.6,
                )

            # 【2026-09-16】resume 续训：若指定 --resume <已有 .pt>，则加载其权重并跳过
            # 从头 BC。同时把 start_ep 垫到已训进度，使 curriculum 走对应档、best 门槛继承。
            resume_pt = getattr(cfg, 'resume', None)
            if resume_pt and Path(resume_pt).exists():
                agents_to_load = agents if isinstance(agents, list) else [agents]
                for ag in agents_to_load:
                    ag.load(resume_pt)
                # 从 checkpoint 逼近已训 ep：优先用 checkpoint_dir 里已有的 history JSON
                # 的下一段，否则靠 --override start_ep。
                resume_start = int(getattr(cfg, 'start_ep', 0) or 0)
                if resume_start <= 0:
                    resume_start = self._resume_ep_from_history()
                cfg.start_ep = resume_start
                logger.info(
                    f"[resume] 已从 {resume_pt} 加载权重，续训自 ep {resume_start}"
                    f"（curriculum 将按 global_ep≥{resume_start} 解析）"
                )
                # 跳过从头 BC：续训时不需再 warm_start（权重已含安全行为）
                cfg.warm_start = False

            cur_plan = self._parse_curriculum()
            episode_rewards, peak_coupler, violations = [], [], []
            best_reward = self._restore_best(namer)
            # 【2026-09-22 长程评估选优】long_eval_interval>0 时 best 文件改由完整剖面
            # 确定性评估驱动（诊断-2026-09-22：训练窗口 reward 最优≠长程评估最优）
            long_eval = int(getattr(cfg, 'long_eval_interval', 0) or 0)
            best_eval = self._restore_long_eval_best(cfg) if long_eval > 0 else None
            global_ep = max(cfg.start_ep, -1)

            # 【YOLO 式日志】TensorBoard + tqdm 实时表 + 每集 CSV + last.pt 快照
            if getattr(cfg, 'yolo_logging', True):
                from src.trainer.logger import TrainingLogger
                self._tlog = TrainingLogger(
                    log_dir=cfg.results_dir,
                    figures_dir=cfg.figures_dir,
                    checkpoint_dir=cfg.checkpoint_dir,
                    tag=namer.history_tag(cfg.seed),
                    seed=cfg.seed,
                    total_episodes=int(cfg.episodes),
                    ckpt_meta=getattr(self, '_ckpt_meta', None),
                    save_fn=agents.save if not isinstance(agents, list) else None,
                    tb=getattr(cfg, 'yolo_tb', True),
                )
            else:
                self._tlog = None

            # 【并行多环境】同一 env 每个 ep 跑 n_env 条独立轨迹（不同初始速度提供
            # 样本多样性，策略/共享 value），全部进 agent 共享 buffer、统一一次 update。
            # GAE 靠 dones 正确处理多轨迹边界；多轨迹平均 advantage≥ 信噪比×n_env。
            n_env = max(1, int(cfg.n_env))

            start = time.time()
            for ep in range(cfg.episodes):
                global_ep += 1
                horizon = self._resolve_horizon(global_ep, cur_plan)
                parallel_len = int(cfg.parallel_traj_len) or horizon
                env.max_steps = parallel_len
                self._traj_reward, self._traj_peak, self._traj_viol = [], [], []

                # 并行 n_env 条独立轨迹（初速均匀铺开 [min,max]，随机化时叠加抖动）：
                # 全部进共享 buffer，统一 end_episode 一次
                for ei in range(n_env):
                    if n_env > 1 and cfg.random_init_speed:
                        lo, hi = cfg.init_speed_min, cfg.init_speed_max
                        init = lo + (hi - lo) * (ei + 0.5 + np.random.uniform(-0.3, 0.3)) / max(n_env, 1)
                        init = float(np.clip(init, lo, hi)) / 3.6
                    elif n_env > 1 and not cfg.random_init_speed:
                        init = cfg.init_speed_kmh / 3.6
                    else:
                        init = (float(np.random.uniform(cfg.init_speed_min, cfg.init_speed_max))
                                if cfg.random_init_speed else cfg.init_speed_kmh) / 3.6
                    obs = env.reset(options={'speed': init})
                    if isinstance(obs, tuple):
                        obs = obs[0]
                    obs = cyclic_obs(env) if cfg.obs == 'cyclic' else obs

                    ep_reward, ep_peak, ep_viol, step, done = 0.0, 0.0, 0, 0, False
                    while not done and step < parallel_len:
                        if cfg.decision_interval > 1:
                            env_act, value, aux = inter.act(obs)
                            nxt, acc, term, trunc, info = obs, 0.0, False, False, None
                            for _ in range(cfg.decision_interval):
                                nxt, r_step, term, trunc, info = env.step(env_act)
                                acc += r_step
                                step += 1
                                if term or trunc or step >= parallel_len:
                                    break
                            reward = acc
                            done = term or trunc or step >= parallel_len
                            inter.observe(obs, env_act, value, nxt, reward, done, info, aux)
                            next_obs = self._next_obs(env, nxt)
                        else:
                            env_act, value, aux = inter.act(obs)
                            next_obs, r_step, term, trunc, info = env.step(env_act)
                            step += 1
                            done = term or trunc or step >= parallel_len
                            reward = self._reward_override(env, inter, r_step)
                            inter.observe(obs, env_act, value, next_obs, reward, done, info, aux)
                            next_obs = self._next_obs(env, next_obs)

                        ep_reward += reward
                        ep_peak = max(ep_peak, info.get('coupler_force_peak', 0))
                        ep_viol = info.get('coupler_limit_violations', 0)
                        obs = next_obs

                    self._traj_reward.append(ep_reward)
                    self._traj_peak.append(ep_peak)
                    self._traj_viol.append(ep_viol)

                # 并行 n_env 条轨迹跑完后统一 update，聚合指标取平均
                metrics = inter.end_episode() or {}
                ep_reward = float(np.mean(self._traj_reward))
                ep_peak = float(np.max(self._traj_peak))
                ep_viol = int(np.sum(self._traj_viol))
                episode_rewards.append(ep_reward)
                peak_coupler.append(ep_peak / 1e3)
                violations.append(ep_viol)

                # 【YOLO 式日志】逐集驱动（CSV/TB/终端），不依赖 log_interval
                if self._tlog is not None:
                    self._tlog.log_episode(
                        ep=global_ep + 1,
                        reward=ep_reward,
                        peak_coupler_kN=ep_peak / 1e3,
                        violations=ep_viol,
                        total_loss=float(metrics.get('total_loss', 0.0)),
                    )

                # 【2026-09-22】long_eval 启用时 best 由完整剖面评估驱动，训练窗口
                # reward 不再直接写 best（否则选出短视激进的长程崩权重）
                if long_eval <= 0:
                    self._maybe_save_best(inter, agents, namer, ep_reward, best_reward, seed=cfg.seed)
                best_reward = max(best_reward, ep_reward)

                # 周期性完整剖面评估选优（viol==0 且 车钩力≤限 且 末速在带内 才可当选）
                if long_eval > 0 and (ep + 1) % long_eval == 0:
                    self._long_eval(agents, cfg, namer, global_ep + 1, best_eval)

                if (ep + 1) % cfg.log_interval == 0 or ep == cfg.episodes - 1:
                    recent = np.mean(episode_rewards[-cfg.log_interval:]) if len(episode_rewards) >= cfg.log_interval else np.mean(episode_rewards)
                    logger.info(
                        f"Ep {ep + 1}/{cfg.episodes} (全局{global_ep + 1}) | Reward {ep_reward:+.1f} "
                        f"(avg {recent:+.1f}) | best {best_reward:+.1f} | "
                        f"peakCoupler {np.mean(peak_coupler[-cfg.log_interval:]):.0f}kN | "
                        f"viol {np.mean(violations[-cfg.log_interval:]):.1f} | "
                        f"loss {metrics.get('total_loss', 0):.3f}")
                    if self._tlog is not None:
                        # last.pt 中间权重快照（YOLO weights/last 语义，周期粒度）
                        self._tlog.save_last(global_ep + 1, namer.best_path(cfg.seed))
                    self._periodic(inter, agents, namer, episode_rewards, peak_coupler, violations,
                                   global_ep, best_reward)

            # 收尾：关闭 tqdm / TensorBoard writer
            if self._tlog is not None:
                self._tlog.close()

            total_time = time.time() - start
            logger.info("=" * 60)
            logger.info(f"训练完成！耗时 {total_time:.1f}s ({total_time / 60:.1f}min)")
            logger.info(f"最佳奖励: {best_reward:.2f} | 末段平均车钩力峰值: "
                        f"{np.mean(peak_coupler[-cfg.log_interval:]):.1f} kN")
            logger.info(f"模型: {cfg.checkpoint_dir}/{Path(namer.best_path(cfg.seed)).name}")
            logger.info("=" * 60)

        return {'best_reward': best_reward, 'rewards': episode_rewards,
                'peak_coupler_kN': peak_coupler, 'violations': violations}

    # ------------------------------------------------------------------
    def _next_obs(self, env, next_obs):
        return cyclic_obs(env) if self.cfg.obs == 'cyclic' else next_obs

    def _reward_override(self, env, inter, step_reward):
        if self.cfg.reward == 'cyclic':
            th = getattr(inter, 'last_throttle', 0.0) or 0.0
            return cyclic_reward(env, 0.0, 0.0, th < -0.1, th)
        return step_reward

    def _parse_curriculum(self):
        curriculum = self.cfg.curriculum
        plan = []
        if not curriculum:
            return plan
        if ':' in curriculum:
            for part in curriculum.split(','):
                h_str, e_str = part.strip().split(':')
                plan.append((int(e_str), int(h_str)))
            plan.sort()
        else:
            stages = [int(x) for x in curriculum.split('-')]
            per = max(1, self.cfg.episodes // len(stages))
            plan = [(i * per, h) for i, h in enumerate(stages)]
        logger.info(f"curriculum 边界: {plan}")
        return plan

    def _resolve_horizon(self, gep, plan):
        h = int(self.cfg.env_cfg.get('max_steps', 300))
        for e_bound, h_stage in plan:
            if gep >= e_bound:
                h = h_stage
        return h

    def _restore_best(self, namer):
        try:
            p = Path(self.cfg.results_dir) / f"train_history_{namer.history_tag(self.cfg.seed)}.json"
            if p.exists():
                with open(p, encoding='utf-8') as f:
                    return float(json.load(f)['meta'].get('best_reward', float('-inf')))
        except Exception:
            pass
        return float('-inf')

    def _resume_ep_from_history(self) -> int:
        """从 resume 权重所在目录已存的 ep{N} checkpoint 推断已训进度（续训起始 ep）。

        兼容命名 mappo_fleet_ep{N}/*.pt-*（如 _ep120_、last_ep120）。
        找不到则返回 0（从头）。优先看 --resume 权重自身所属目录，而非新 checkpoint_dir。
        """
        import re as _re
        best = 0
        resume_pt = getattr(self.cfg, 'resume', None)
        # resume 权重自身文件名就是最佳线索：mappo_fleet_ep120_...  → 120
        if resume_pt:
            m = _re.search(r"_ep(\d+)[._]", str(resume_pt))
            if m:
                best = max(best, int(m.group(1)))
        # 兜底：扫描旧目录（resume 权重同目录）里的其他 ep{N} checkpoint
        if best <= 0 and resume_pt:
            d = Path(resume_pt).parent
            if d.exists():
                for f in d.glob("*.pt"):
                    m = _re.search(r"_ep(\d+)[._]", f.name)
                    if m:
                        best = max(best, int(m.group(1)))
        return best

    def _maybe_save_best(self, inter, agents, namer, ep_reward, best_reward, seed):
        if ep_reward <= best_reward:
            return
        meta = getattr(self, '_ckpt_meta', None)
        if self.cfg.ckpt_policy == 'coor_dqn':
            for i, ag in enumerate(agents):
                ag.save(str(Path(self.cfg.checkpoint_dir) /
                            f"coor_dqn_best_seed{seed}_train{i}.pt"), metadata=meta)
        else:
            agents.save(str(Path(self.cfg.checkpoint_dir) / namer.best_path(seed)),
                        metadata=meta)

    # ------------------------------------------------------------------
    # 【2026-09-22 长程评估选优】best 由完整剖面确定性评估驱动（诊断-2026-09-22：
    # 训练窗口 1200 步≈2.4km 的 reward 最优 ≠ 完整剖面评估最优；短视激进权重长程崩）。
    # 达标判据：viol==0 且 峰值车钩力≤限 且 末速在 [v_min,v_max] 带内；达标且评估
    # reward 创新高才覆盖 best 文件。评估 env 与训练同源（cfg.env_cfg，仅改 max_steps/
    # eval_mode/grade），杜绝训练-评估物理不一致。
    def _long_eval(self, agents, cfg, namer, global_ep, best_eval):
        if isinstance(agents, list):
            logger.warning(f"[long_eval] ep{global_ep}: 多智能体 list 暂不支持长程评估选优，跳过")
            return
        long_steps = int(getattr(cfg, 'long_eval_steps', 36000) or 36000)
        grade = getattr(cfg, 'long_eval_grade', '') or cfg.env_cfg.get('grade_profile', 'shuozhou_real_53km')
        init_kmh = float(getattr(cfg, 'long_eval_init_speed_kmh', 80.0) or 80.0)
        eval_cfg = dict(cfg.env_cfg)
        eval_cfg['max_steps'] = long_steps
        eval_cfg['eval_mode'] = True
        eval_cfg['grade_profile'] = grade
        act_interval = max(1, int(cfg.decision_interval or 1))
        env = None
        try:
            env = TrainFleetEnv(eval_cfg)
            obs, _ = env.reset(options={'speed': init_kmh / 3.6})
            ep_r = peak = viol = band = 0.0
            n = 0
            a = None
            for i in range(long_steps):
                if a is None or i % act_interval == 0:
                    flat = np.asarray(self._eval_obs(cfg, env)).flatten()
                    a, _ = agents.select_actions(flat, deterministic=True)
                    a = np.asarray(a, dtype=np.float32).reshape(env.num_agents, env.act_dim)
                obs, r, term, trunc, info = env.step(a)
                ep_r += float(r)
                peak = max(peak, float(info.get('coupler_force_peak', 0)))
                viol += int(info.get('coupler_limit_violations', 0))
                vel = float(env.trains[0].dynamics.vel[0])
                band += int(env.v_min <= vel <= env.v_max)
                n += 1
                if term or trunc:
                    break
            final_kmh = float(env.trains[0].dynamics.vel[0]) * 3.6
            lim_kN = env.coupler_force_limit_n / 1e3
            peak_kN = peak / 1e3
            ok = (int(viol) == 0 and peak_kN <= lim_kN
                  and env.v_min * 3.6 <= final_kmh <= env.v_max * 3.6)
            logger.info(f"[long_eval] ep{global_ep}: reward {ep_r:+.0f} | peak {peak_kN:.0f}kN | "
                        f"viol {int(viol)} | band {band / max(n, 1):.1%} | 末速 {final_kmh:.1f}km/h "
                        f"| 达标={ok}")
            if ok and ep_r > best_eval.get('reward', float('-inf')):
                best_eval.update({'reward': ep_r, 'ep': global_ep,
                                  'peak_kN': peak_kN, 'viol': int(viol),
                                  'final_kmh': final_kmh, 'grade': grade})
                agents.save(str(Path(cfg.checkpoint_dir) / namer.best_path(cfg.seed)),
                            metadata=getattr(self, '_ckpt_meta', None))
                self._save_long_eval_best(cfg, best_eval)
                logger.info(f"[long_eval] 新 best（长程评估达标）已保存: "
                            f"{namer.best_path(cfg.seed)} @ ep{global_ep} (reward {ep_r:+.0f})")
        except Exception as e:
            # 长程评估为附加选优机制：失败不中断训练（本次不选优，下周期再试）
            logger.warning(f"[long_eval] ep{global_ep}: 长程评估失败 "
                           f"({type(e).__name__}: {e})，跳过本次选优")
            return
        finally:
            if env is not None:
                env.close()

    def _eval_obs(self, cfg, env):
        """评估观测：cyclic 走 cyclic_obs，decompose/常规走 env 自带 obs。"""
        if cfg.obs == 'cyclic':
            return cyclic_obs(env)
        if hasattr(env, '_get_obs_decomposed'):
            return env._get_obs_decomposed()
        return env._get_obs()

    def _restore_long_eval_best(self, cfg):
        p = Path(cfg.results_dir) / 'long_eval_best.json'
        if p.exists():
            try:
                return json.loads(p.read_text(encoding='utf-8'))
            except Exception:
                pass
        return {'reward': float('-inf'), 'ep': 0}

    def _save_long_eval_best(self, cfg, best_eval):
        p = Path(cfg.results_dir) / 'long_eval_best.json'
        p.write_text(json.dumps(best_eval, ensure_ascii=False, indent=2), encoding='utf-8')

    def _periodic(self, inter, agents, namer, rewards, peaks, viols, global_ep, best_reward):
        tag = namer.history_tag(self.cfg.seed)
        save_training_artifacts(
            rewards, peaks, viols,
            meta={'seed': self.cfg.seed, 'episodes': len(rewards),
                  'grade_profile': self.cfg.env_cfg.get('grade_profile'),
                  'curriculum': self.cfg.curriculum,
                  'best_reward': float(best_reward),
                  'name': self.cfg.name,
                  'physics': 'R0(2026-09-06)+MT2统一(2026-09-07): 全列MT-2 Stribeck 750/500 + 卸载刚度 + 牵规β_c + 并行波速 + 段间衰减D + 两段式缓解τ=6s + Newmark-β'},
            results_dir=self.cfg.results_dir, figures_dir=self.cfg.figures_dir, tag=tag)
        # periodic checkpoint（fleet 保留 ep{gep+1} 存档协议）
        p = namer.periodic_path(global_ep, self.cfg.seed)
        if p and (global_ep + 1) % self.cfg.log_interval == 0 and not isinstance(agents, list):
            agents.save(str(Path(self.cfg.checkpoint_dir) / p),
                        metadata=getattr(self, '_ckpt_meta', None))