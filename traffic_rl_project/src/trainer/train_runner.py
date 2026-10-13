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

        # 【路线覆盖修复 2026-10-06】起点随机化 seed 继承本次运行 seed：
        # 使 5 个 seed 各自独立随机化（而非共用同一固定序列），且单 seed 内可复现。
        # 仅在配置显式开启且未显式指定 seed 时注入。
        _sr = cfg.env_cfg.get('start_randomization')
        if isinstance(_sr, dict) and _sr.get('enabled', False) and _sr.get('seed', None) is None:
            _sr['seed'] = int(cfg.seed)

        # cyclic 限速按配置显式设置（cyclic_obs/cyclic_reward 用）
        if cfg.obs == 'cyclic' or cfg.reward == 'cyclic':
            set_cyclic_limits(
                v_max_mps=cfg.env_cfg.get('v_max', 80.0 / 3.6),
                v_min_mps=cfg.env_cfg.get('v_min', 40.0 / 3.6))

        # 【续训】先解析 --resume（路径不存在直接报错，禁止静默从头重训）
        resume_plan = None
        if str(getattr(cfg, 'resume', '') or '').strip():
            from src.trainer.resume import resolve_checkpoint, read_progress
            cfg.resume = resolve_checkpoint(cfg)
            resume_plan = read_progress(cfg, cfg.resume)
            logger.info(
                f"[resume] 源权重 {resume_plan.source_pt} | 已训 {resume_plan.done_ep} ep "
                f"| best {resume_plan.best_reward:+.1f} | weights_only={resume_plan.weights_only}")

        env, agents, inter = Registry.build(cfg, device)
        if isinstance(agents, list):
            num_agents = len(agents)
        else:
            num_agents = int(getattr(env, 'num_agents', 0)) or int(getattr(env, 'num_trains', 1))
        act_dim = int(getattr(env, 'act_dim', 1)) or int(cfg.env_cfg.get('action_dim', 1))
        namer = make_namer(cfg, act_dim=act_dim, num_trains=num_agents)

        # 运行派生（2026-09-30）：consist 等由本次实验 env_cfg 决定，随 metadata 固化，
        # 避免 physics 块固报 PhysicsConfig 默认编组（1+0）而运行实为 1+1。
        world_cfg = official_world_config(PhysicsConfig(), env_cfg=cfg.env_cfg)
        # 自包含 checkpoint：权威 metadata 嵌入每个 .pt（对标 YOLO best.pt，
        # 2026-09-10），与 metadata.json 双轨——权重单文件即可溯源复现。
        # 【续训】base metadata 为静态部分；训练进度（done_ep/best_reward/long_eval_best）
        # 由 _ckpt_meta_now() 在每次落盘时动态追加。
        meta_extra = {"hyperparameters": cfg_to_dict(cfg)}
        self._resume_info = None
        if resume_plan is not None:
            self._resume_info = {'source': resume_plan.source_pt,
                                 'done_ep': resume_plan.done_ep,
                                 'weights_only': resume_plan.weights_only}
            meta_extra["resume"] = dict(self._resume_info)
        self._base_ckpt_meta = build_metadata(
            project_root=str(Path(__file__).parent.parent.parent),
            case=cfg.simcase, world_cfg=world_cfg, seed=cfg.seed,
            entry="run_training.py",
            extra=meta_extra)
        self._best_eval_ref = None
        with training_metadata_guard(cfg.results_dir, world_cfg=world_cfg,
                                     seed=cfg.seed, simcase=cfg.simcase,
                                     entry="run_training.py",
                                     extra=meta_extra):
            case = SimCase(cfg.simcase)
            assert_case_allows(case, world_cfg, __file__)

            # 【续训】加载训练状态（完整 or 纯权重）。必须在 warm start 之前，
            # 否则 BC 白跑一遍又立刻被 resume 权重覆盖。
            if resume_plan is not None:
                if isinstance(agents, list):
                    raise ValueError(
                        "[resume] list-agent（coor_dqn）产线已下线，不支持续训；"
                        "请改用单 agent 产线，或逐 train 手动加载权重。")
                agents.load(resume_plan.source_pt, weights_only=resume_plan.weights_only)
                cfg.warm_start = False
                logger.info(f"[resume] 已加载 {resume_plan.source_pt}"
                            f"（weights_only={resume_plan.weights_only}）")

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

            # 【续训】--episodes = 总目标集数 → 实跑 = 总目标 - 已训。
            # 非续训路径保持 --episodes = 实跑集数（行为不变）。
            cur_plan = self._parse_curriculum()
            total_episodes = int(cfg.episodes)
            if resume_plan is not None:
                from src.trainer.resume import plan_run_episodes
                done_ep = int(resume_plan.done_ep)
                run_episodes = plan_run_episodes(cfg, done_ep)
                logger.info(f"[resume] 已训 {done_ep} ep，目标总 {total_episodes} ep，"
                            f"本轮跑 {run_episodes} ep")
            else:
                done_ep = 0
                run_episodes = total_episodes

            # 历史曲线拼接：续训时以源 history 为初值，本轮只 append → 曲线连续
            episode_rewards = list(resume_plan.prior_rewards) if resume_plan else []
            peak_coupler = list(resume_plan.prior_peak) if resume_plan else []
            violations = list(resume_plan.prior_viol) if resume_plan else []
            best_reward = (resume_plan.best_reward if resume_plan is not None
                           else self._restore_best(namer))
            # 【2026-09-22 长程评估选优】long_eval_interval>0 时 best 文件改由完整剖面
            # 确定性评估驱动（诊断-2026-09-22：训练窗口 reward 最优≠长程评估最优）
            long_eval = int(getattr(cfg, 'long_eval_interval', 0) or 0)
            if long_eval > 0:
                best_eval = (dict(resume_plan.long_eval_best) if resume_plan is not None
                             else self._restore_long_eval_best(cfg))
                self._best_eval_ref = best_eval
            else:
                best_eval = None
            # global_ep 为"已完成集数"计数；首次自增后 = done_ep（集编号 done_ep+1）
            global_ep = done_ep - 1

            # 【YOLO 式日志】TensorBoard + tqdm 实时表 + 每集 CSV + last.pt 快照
            if getattr(cfg, 'yolo_logging', True):
                from src.trainer.logger import TrainingLogger
                self._tlog = TrainingLogger(
                    log_dir=cfg.results_dir,
                    figures_dir=cfg.figures_dir,
                    checkpoint_dir=cfg.checkpoint_dir,
                    tag=namer.history_tag(cfg.seed),
                    seed=cfg.seed,
                    total_episodes=total_episodes,
                    ckpt_meta=lambda: self._ckpt_meta_now(global_ep + 1, best_reward),
                    save_fn=agents.save if not isinstance(agents, list) else None,
                    tb=getattr(cfg, 'yolo_tb', True),
                    initial=done_ep,
                    resume=resume_plan is not None,
                )
            else:
                self._tlog = None

            # 【并行多环境】同一 env 每个 ep 跑 n_env 条独立轨迹（不同初始速度提供
            # 样本多样性，策略/共享 value），全部进 agent 共享 buffer、统一一次 update。
            # GAE 靠 dones 正确处理多轨迹边界；多轨迹平均 advantage≥ 信噪比×n_env。
            n_env = max(1, int(cfg.n_env))

            # 【2026-10-07 进程级并行】n_env 条轨迹原本串行（单核），开此开关改走进程池：
            # 每条轨迹一个 worker 进程并行跑，用满多核（见 src/trainer/parallel_rollout.py）。
            parallel = None
            if (bool(getattr(cfg, 'n_env_parallel', False)) and n_env > 1
                    and cfg.interaction == 'mappo_fleet' and cfg.obs == 'env'
                    and cfg.reward != 'cyclic' and not isinstance(agents, list)
                    and not cfg.env_cfg.get('hetero', False)):
                from src.trainer.parallel_rollout import ParallelRollout
                parallel = ParallelRollout(cfg, n_env)
                logger.info(f"[并行 rollout] 进程级并行已启用：n_env={n_env} 个 worker 进程")

            start = time.time()
            for ep in range(run_episodes):
                global_ep += 1
                horizon = self._resolve_horizon(global_ep, cur_plan)
                parallel_len = int(cfg.parallel_traj_len) or horizon
                env.max_steps = parallel_len
                self._traj_reward, self._traj_peak, self._traj_viol = [], [], []
                # 列间间距监控（2026-09-23 新增）：每轨迹聚合间距误差均值 / 最小间距
                self._traj_gap_err, self._traj_gap_min = [], []

                # 并行 n_env 条独立轨迹（初速均匀铺开 [min,max]，随机化时叠加抖动）：
                # 全部进共享 buffer，统一 end_episode 一次
                for ei in range(n_env):
                    if parallel is not None:
                        break   # 并行路径：串行循环空转一次即退出，改由下方 parallel 分支跑
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
                    # 列间间距监控（2026-09-23 新增）：本轨迹间距误差累计 / 最小间距
                    ep_gap_err_sum, ep_gap_min, gap_steps = 0.0, float('inf'), 0
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
                        # 列间间距监控（2026-09-23 新增）
                        if info is not None:
                            _ge = info.get('gap_err_mean', 0.0)
                            _gm = info.get('gap_min_m', float('inf'))
                            ep_gap_err_sum += float(_ge)
                            ep_gap_min = min(ep_gap_min, float(_gm))
                            gap_steps += 1
                        obs = next_obs

                    self._traj_reward.append(ep_reward)
                    self._traj_peak.append(ep_peak)
                    self._traj_viol.append(ep_viol)
                    # 列间间距监控：轨迹级 = 间距误差均值 / 最小间距（无步则留空）
                    if gap_steps > 0:
                        self._traj_gap_err.append(ep_gap_err_sum / gap_steps)
                        self._traj_gap_min.append(ep_gap_min)
                    else:
                        self._traj_gap_err.append(0.0)
                        self._traj_gap_min.append(0.0)

                # 【2026-10-07 进程级并行】n_env 条轨迹分发到进程池并行跑；初速仍由父进程
                # 按同一顺序抽取（保持 RNG 流与串行版一致），随后按序重放 transitions。
                if parallel is not None:
                    inits = []
                    for ei in range(n_env):
                        if cfg.random_init_speed:
                            lo, hi = cfg.init_speed_min, cfg.init_speed_max
                            init = lo + (hi - lo) * (ei + 0.5 + np.random.uniform(-0.3, 0.3)) / max(n_env, 1)
                            init = float(np.clip(init, lo, hi)) / 3.6
                        else:
                            init = cfg.init_speed_kmh / 3.6
                        inits.append(init)
                    results = parallel.run_episode(agents, parallel_len, global_ep, inits)
                    for res in results:
                        for flat, actions, reward, log_prob, done, value in res['transitions']:
                            agents.store_transition(flat, actions, reward, log_prob, done, value)
                        self._traj_reward.append(res['reward'])
                        self._traj_peak.append(res['peak'])
                        self._traj_viol.append(res['viol'])
                        self._traj_gap_err.append(res['gap_err'])
                        self._traj_gap_min.append(res['gap_min'])

                # 并行 n_env 条轨迹跑完后统一 update，聚合指标取平均
                metrics = inter.end_episode() or {}
                ep_reward = float(np.mean(self._traj_reward))
                ep_peak = float(np.max(self._traj_peak))
                ep_viol = int(np.sum(self._traj_viol))
                # 列间间距监控（2026-09-23 新增）：全轨迹间距误差均值 / 最危险的最小间距
                ep_gap_err = float(np.mean(self._traj_gap_err))
                ep_gap_min = float(np.min(self._traj_gap_min))
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
                        gap_err_mean=ep_gap_err,
                        gap_min_m=ep_gap_min,
                        # 【X2 2026-09-30】优化器诊断量落盘（value 发散可证伪）
                        value_loss=float(metrics.get('value_loss', 0.0)),
                        policy_loss=float(metrics.get('policy_loss', 0.0)),
                        entropy=float(metrics.get('entropy', 0.0)),
                        approx_kl=float(metrics.get('approx_kl', 0.0)),
                        grad_norm=float(metrics.get('grad_norm', 0.0)),
                        value_norm_mean=float(metrics.get('value_norm_mean', 0.0)),
                        value_norm_std=float(metrics.get('value_norm_std', 0.0)),
                    )

                # 【2026-09-22】long_eval 启用时 best 由完整剖面评估驱动，训练窗口
                # reward 不再直接写 best（否则选出短视激进的长程崩权重）
                if long_eval <= 0:
                    self._maybe_save_best(inter, agents, namer, ep_reward, best_reward,
                                          seed=cfg.seed, done_ep=global_ep + 1)
                best_reward = max(best_reward, ep_reward)

                # 周期性完整剖面评估选优（viol==0 且 车钩力≤限 且 末速在带内 才可当选）
                if long_eval > 0 and (ep + 1) % long_eval == 0:
                    self._long_eval(agents, cfg, namer, global_ep + 1, best_eval)

                if (ep + 1) % cfg.log_interval == 0 or ep == run_episodes - 1:
                    recent = np.mean(episode_rewards[-cfg.log_interval:]) if len(episode_rewards) >= cfg.log_interval else np.mean(episode_rewards)
                    logger.info(
                        f"Ep {global_ep + 1}/{total_episodes} (本轮 {ep + 1}/{run_episodes}) | "
                        f"Reward {ep_reward:+.1f} "
                        f"(avg {recent:+.1f}) | best {best_reward:+.1f} | "
                        f"peakCoupler {np.mean(peak_coupler[-cfg.log_interval:]):.0f}kN | "
                        f"viol {np.mean(violations[-cfg.log_interval:]):.1f} | "
                        f"loss {metrics.get('total_loss', 0):.3f}")
                    if self._tlog is not None:
                        # last.pt 中间权重快照（YOLO weights/last 语义，周期粒度）
                        self._tlog.save_last(global_ep + 1, namer.best_path(cfg.seed))
                    self._periodic(inter, agents, namer, episode_rewards, peak_coupler, violations,
                                   global_ep, best_reward)

            # 收尾：关闭并行进程池 / tqdm / TensorBoard writer
            if parallel is not None:
                parallel.close()
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

    def _ckpt_meta_now(self, done_ep: int, best_reward: float) -> dict:
        """当前时刻的权威 metadata（base + 训练进度），供所有 checkpoint 落盘使用。

        进度写进 .pt 内嵌 metadata，使权重单文件即可续训（读 done_ep/best_reward/
        long_eval_best），不再依赖外置 train_history JSON。
        """
        meta = dict(getattr(self, '_base_ckpt_meta', {}) or {})
        meta['done_ep'] = int(done_ep)
        meta['best_reward'] = float(best_reward)
        if getattr(self, '_resume_info', None):
            meta['resume_from'] = self._resume_info.get('source')
            meta['resume_done_ep'] = self._resume_info.get('done_ep')
        if getattr(self, '_best_eval_ref', None):
            meta['long_eval_best'] = dict(self._best_eval_ref)
        return meta

    def _maybe_save_best(self, inter, agents, namer, ep_reward, best_reward, seed, done_ep):
        if ep_reward <= best_reward:
            return
        meta = self._ckpt_meta_now(done_ep, max(best_reward, ep_reward))
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
        grade = getattr(cfg, 'long_eval_grade', '') or cfg.env_cfg.get('grade_profile', 'shuozhou_ningwuxi_beidaniu_49km')
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
            prev_viol = 0.0   # env 的 viol 计数器为 episode 级单调累计，须取每步增量
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
                # env 的 coupler/safety 计数器是 episode 级单调累计（reset 清零、step 间不清零），
                # 此处必须取其每步增量累加；否则 O(n²) 叠加会把 viol 放大到 1e6~1e8，
                # 日志读出天文数字、评估判据看似失效（与 `evaluate_decompose.py` 2026-09-25
                # 的同一处修复对齐；本处当时漏改）。
                cur_viol = float(info.get('coupler_limit_violations', 0))
                viol += cur_viol - prev_viol
                prev_viol = cur_viol
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
            # 【2026-10-07 治本】每次长程评估都留痕（含未达标）。
            self._append_long_eval_history(cfg, {
                'ep': int(global_ep), 'reward': float(ep_r), 'peak_kN': float(peak_kN),
                'viol': int(viol), 'band': float(band / max(n, 1)),
                'final_kmh': float(final_kmh), 'grade': grade, 'ok': bool(ok),
            })
            if ok and ep_r > best_eval.get('reward', float('-inf')):
                best_eval.update({'reward': ep_r, 'ep': global_ep,
                                  'peak_kN': peak_kN, 'viol': int(viol),
                                  'final_kmh': final_kmh, 'grade': grade})
                agents.save(str(Path(cfg.checkpoint_dir) / namer.best_path(cfg.seed)),
                            metadata=self._ckpt_meta_now(global_ep, best_eval.get('reward', float('-inf'))))
                self._save_long_eval_best(cfg, best_eval)
                logger.info(f"[long_eval] 新 best（长程评估达标）已保存: "
                            f"{namer.best_path(cfg.seed)} @ ep{global_ep} (reward {ep_r:+.0f})")
        except Exception as e:
            # 长程评估为附加选优机制：失败不中断训练（本次不选优，下周期再试）
            logger.warning(f"[long_eval] ep{global_ep}: 长程评估失败 "
                           f"({type(e).__name__}: {e})，跳过本次选优")
            self._append_long_eval_history(cfg, {
                'ep': int(global_ep), 'error': f"{type(e).__name__}: {e}", 'ok': False,
            })
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

    def _append_long_eval_history(self, cfg, rec):
        """**每次长程评估都留痕**（含未达标/异常），追加写 JSONL，永不覆盖。

        【2026-10-07 治本｜证据不再丢】旧行为只在**达标**时写 `long_eval_best.json`；
        未达标仅打一条 `logger.info`。一旦 stdout 没有落盘（例如用 `| tail -N` 截断，
        LRN-20261007-002），"未达标"这件事就只剩"文件不存在"这一个间接线索 —— 既不知道
        卡在哪条判据（peak / viol / 末速），也不知道随训练如何演化，被迫重跑 53 km
        确定性评估（每次 ~30 min）来补证据。此处 append-only 落地，作为长程评估的权威流水。
        """
        p = Path(cfg.results_dir) / 'long_eval_history.jsonl'
        rec = dict(rec)
        rec['time'] = time.strftime('%Y-%m-%d %H:%M:%S')
        try:
            with open(p, 'a', encoding='utf-8') as f:
                f.write(json.dumps(rec, ensure_ascii=False) + '\n')
        except Exception as e:
            logger.warning(f"[long_eval] 历史流水写入失败（{type(e).__name__}: {e}）")

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
            results_dir=self.cfg.results_dir, figures_dir=self.cfg.figures_dir, tag=tag,
            write_csv=False)   # CSV 归 ExperimentLogger（8 列含 gap_min_m），勿用 4 列覆写
        # periodic checkpoint（fleet 保留 ep{gep+1} 存档协议）
        p = namer.periodic_path(global_ep, self.cfg.seed)
        if p and (global_ep + 1) % self.cfg.log_interval == 0 and not isinstance(agents, list):
            agents.save(str(Path(self.cfg.checkpoint_dir) / p),
                        metadata=self._ckpt_meta_now(global_ep + 1, best_reward))