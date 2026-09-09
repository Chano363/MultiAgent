"""
【legacy 2026-09-06】已被 run_training.py 统一框架替代（对应 configs/experiments/platoon_mappo.yaml
 或 decompose_loco_ed_ab.yaml），保留为 append-only 供复现/评估兼容。
重载列车群组（多列编队）MAPPO 训练入口。

【架构澄清（2026-08-14）】
- 多智能体 = 多列万吨列车（每列 = 1 智能体，列间编队协同）
- 列内 = 单列控制（1 机车 + 100 拖挂，车钩力作为该列状态/奖励约束）

本脚本实现层级一（列间 MARL）：
- 智能体 = 每列万吨列车
- 每列 obs = 速度误差/列间间距/前方坡度/车钩力统计（均值/峰值/超限）
- 每列 action = throttle ∈ [-1,1]（正=机车牵引，负=全列空气制动）
- 列内推进用 TrainFormationEnv.step（单列控制）

复用 MAPPOAgent（共享策略 + 集中式 Critic + GAE + KL 早停 + ValueNorm）。
"""

import sys
import os
import json
from pathlib import Path
import time
import argparse
import logging
from typing import Dict

sys.path.append(str(Path(__file__).parent.parent.parent))

import numpy as np
import torch

logging.basicConfig(level=logging.INFO, format='%(message)s')
logger = logging.getLogger('TrainFleet')

from src.environments.train_fleet_env import TrainFleetEnv
from src.algorithms.mappo_agent import MAPPOAgent
from src.physics_config import PhysicsConfig
from src.physics_governance import SimCase, official_world_config, assert_case_allows
from src.metadata import save_metadata, assert_training_metadata
from .artifacts import save_training_artifacts  # 【2026-09-06 统一框架】迁移至 artifacts.py，此处 re-export 保兼容





def set_seed(seed: int):
    np.random.seed(seed)
    torch.manual_seed(seed)
    if torch.cuda.is_available():
        torch.cuda.manual_seed(seed)


def make_env(config: Dict) -> TrainFleetEnv:
    return TrainFleetEnv(config)


def train(
    episodes: int = 200,
    num_trains: int = 3,
    consist_preset: str = '10kt_1plus0',
    grade_profile: str = 'shuozhou_23800',
    target_speed: float = None,
    target_gap: float = 100.0,
    max_steps: int = 300,
    v_max: float = PhysicsConfig.v_max_mps,      # 参数中心化：统一取 physics_config
    v_min: float = PhysicsConfig.v_min_mps,
    lr: float = 5e-5,
    entropy: float = 0.005,
    batch_size: int = 64,
    epochs: int = 4,
    device: str = None,
    seed: int = 42,
    case: str = 'official',          # 【治理】SimCase.official/debug；调试物理进正式训练会被拒
    max_accel: float = PhysicsConfig.max_accel,
    enable_disturbance: bool = False,
    disturbance_step: int = 150,
    disturbance_duration: int = 300,
    disturbance_target_accel: float = -0.8,
    use_coupler_constraint: bool = True,
    hierarchical: bool = False,
    layer1_checkpoint: str = 'outputs/checkpoints/cyclic_mappo_best_seed0_v40-80_init80.pt',
    adj_coef: float = 0.3,
    action_dim: int = 1,               # 【方向A】协同动作维度：1=coor_adj 整带平移；2=v_max/v_min 独立偏移
    group_obs: bool = False,           # 【方向B】全局一致性观测（obs_dim 11→13），修根因3
    decompose: str = None,             # 【ADR-009.1 2026-09-05 换架构】'loco_ed_ab'=逐机车 RL
                                       # 智能体（每机车独立 ED/AB 分配调制），None=旧列级模式
    decision_interval: int = 1,        # 【2026-09-05 RL 层救回①】decompose 模式 RL 决策间隔
                                       # （动作保持 N 步，semi-MDP）：砍短超长时域信用链
                                       # （15000 步→1500 决策），rule 基线仍逐步执行
    mask_lever: str = 'none',          # 【2026-09-05 杠杆隔离消融】'none'/'ed'/'ab'：
                                       # 禁用 ed_mod（仅 AB 杠杆）或 ab_mod（仅 ED 杠杆）
    hetero: bool = False,              # 【E4-H 车钩异构】训练在逐车钩独立参数分布上（分布内）
    hetero_seed: int = 0,              # 车钩异构抽样 seed（训练固定；评估 held-out 用另一组）
    enable_etcs: bool = False,       # 【2026-09-03】训练时启用 ETCS（与评估 --etcs 对齐，
                                     # 消除"训练无 ETCS / 评估有 ETCS"的分布不一致）
    random_init_speed: bool = False,
    init_speed_min: float = 55.0 / 3.6,
    init_speed_max: float = 75.0 / 3.6,
    init_speed_kmh: float = 65.0,   # 固定初始速度（km/h），循环制动场景用 80
    checkpoint_dir: str = 'outputs/checkpoints',
    results_dir: str = 'outputs/results',
    curriculum: str = None,          # 可选：'300-1000-3000'（相对）或 '1000:66,3000:132'（绝对全局ep边界）
    resume: str = None,              # 可选：续训检查点路径（加载策略继续训练，前台分块训练用）
    start_ep: int = -1,              # 可选：起始全局回合号（-1=从 resume 历史推断；从头训练分块续训用）
):
    if device is None:
        device = 'cuda' if torch.cuda.is_available() else 'cpu'

    set_seed(seed)

    env_cfg = {
        'num_trains': num_trains,
        'consist_preset': consist_preset,
        'grade_profile': grade_profile,
        'v_max': v_max,
        'v_min': v_min,
        'target_gap': target_gap,
        'max_steps': max_steps,
        'max_accel': max_accel,
        'enable_disturbance': enable_disturbance,
        'disturbance_step': disturbance_step,
        'disturbance_duration': disturbance_duration,
        'disturbance_target_accel': disturbance_target_accel,
        'use_coupler_constraint': use_coupler_constraint,
        'hierarchical': hierarchical,
        'layer1_checkpoint': layer1_checkpoint,
        'adj_coef': adj_coef,
        'action_dim': action_dim,   # 【方向A】1=整带平移；2=v_max/v_min 独立偏移
        'group_obs': group_obs,     # 【方向B】全局一致性观测（修根因3）
        'decompose': decompose,     # 【ADR-009.1】逐机车电空分工模式（None=向后兼容）
        'mask_lever': mask_lever,   # 【杠杆隔离消融】'none'/'ed'/'ab'
        'hetero': hetero,           # 【E4-H 车钩异构】True=逐车钩独立参数
        'hetero_seed': hetero_seed,
        'enable_etcs': enable_etcs,   # 【2026-09-03】训练/评估 ETCS 对齐
    }
    if target_speed is not None:
        env_cfg['target_speed'] = target_speed
    env = make_env(env_cfg)

    # 【治理】工况断言 + 元数据落盘：调试物理(衰减/列尾压/减压覆盖)进入正式训练即抛异常
    _case = SimCase(case)
    assert_case_allows(_case, official_world_config(PhysicsConfig()), __file__)
    extra_hp = {
        "algorithm": "mappo",
        "episodes": episodes, "num_trains": num_trains,
        "consist_preset": consist_preset, "grade_profile": grade_profile,
        "target_speed": target_speed, "target_gap": target_gap, "max_steps": max_steps,
        "lr": lr, "entropy": entropy, "batch_size": batch_size, "epochs": epochs,
        "decision_interval": decision_interval, "mask_lever": mask_lever,
        "decompose": decompose, "action_dim": action_dim, "group_obs": group_obs,
        "hetero": hetero, "hetero_seed": hetero_seed,
        "hierarchical": hierarchical, "adj_coef": adj_coef,
        "use_coupler_constraint": use_coupler_constraint, "enable_etcs": enable_etcs,
        "curriculum": curriculum, "resume": resume, "start_ep": start_ep,
        "init_speed_kmh": init_speed_kmh, "random_init_speed": random_init_speed,
        "init_speed_min": init_speed_min, "init_speed_max": init_speed_max,
        "disturbance": {
            "enabled": enable_disturbance, "step": disturbance_step,
            "duration": disturbance_duration, "target_accel": disturbance_target_accel,
        },
    }
    save_metadata(results_dir, project_root=str(Path(__file__).parent.parent.parent),
                  case=_case.value, world_cfg=official_world_config(PhysicsConfig()), seed=seed,
                  entry=__file__, extra={"hyperparameters": extra_hp})

    obs_dim = env.obs_dim       # 每智能体观测维度
    act_dim = env.act_dim       # 每智能体动作维度（decompose=2 [ed_mod,ab_mod]；否则=action_dim）
    num_agents = env.num_agents  # 智能体数（decompose=Σ每列机车数；否则=列数）
    if decompose and decision_interval > 1:
        logger.info(f"RL 决策间隔: {decision_interval} 步/决策（动作保持，rule 基线逐步执行）")

    logger.info("=" * 70)
    logger.info("重载列车群组（多列编队）MAPPO 训练")
    logger.info("=" * 70)
    logger.info(f"编队列数: {num_trains} 列")
    logger.info(f"单列编组: {consist_preset}")
    logger.info(f"坡度剖面: {grade_profile}")
    logger.info(f"限速区间: [{v_min*3.6:.0f}, {v_max*3.6:.0f}] km/h (循环制动)")
    logger.info(f"巡航参考速度: {(env.target_speed):.1f} m/s | 列间目标间距: {target_gap} m")
    logger.info(f"每列 obs={obs_dim}维, act={act_dim}维")
    logger.info(f"设备: {device}")

    agent = MAPPOAgent(
        num_drones=num_agents,   # 智能体 = 每机车（decompose）或每列（旧模式）
        obs_per_drone=obs_dim,
        act_per_drone=act_dim,
        learning_rate=lr,
        gamma=0.99,
        gae_lambda=0.95,
        clip_epsilon=0.2,
        entropy_coef=entropy,
        value_coef=0.5,
        epochs=epochs,
        batch_size=batch_size,
        device=device,
    )

    Path(checkpoint_dir).mkdir(parents=True, exist_ok=True)
    Path(results_dir).mkdir(parents=True, exist_ok=True)

    # 【2026-08-30】断点续训：加载已有策略继续训练（前台分块训练用，
    # 优化器状态随 checkpoint 一并保存/恢复，热启动续训不打断学习进程）
    cp_tag = f"{'dec_' if decompose else ''}ad{act_dim}{'g' if group_obs else ''}_{'m'+mask_lever if mask_lever and mask_lever != 'none' else ''}_{'cp' if use_coupler_constraint else 'nocp'}"
    if resume and Path(resume).exists():
        agent.load(resume)
        logger.info(f"已加载续训检查点: {resume}")
    elif resume:
        logger.warning(f"[警告] 续训检查点不存在，从头训练: {resume}")

    episode_rewards = []
    episode_peak_coupler = []
    episode_violations = []
    best_reward = float('-inf')
    # 【2026-08-30 无缝续训】加载历史与 best（跨块不丢数据、best 全局跟踪）：
    # 分块训练每块重开 best=-inf 会让 best checkpoint 被后块劣质模型覆盖
    # （实测导致评估非单调恶化）。续训时从已存 history 恢复累计列表与 best。
    if resume and Path(resume).exists():
        hist_path = Path(results_dir) / f"train_history_{cp_tag}_seed{seed}.json"
        if hist_path.exists():
            h = json.loads(hist_path.read_text(encoding='utf-8'))
            episode_rewards = list(h.get('rewards', []))
            episode_peak_coupler = list(h.get('peak_coupler_kN', []))
            episode_violations = list(h.get('violations', []))
            best_reward = float(h.get('meta', {}).get('best_reward', float('-inf')))
            if start_ep < 0:
                start_ep = len(episode_rewards)
            logger.info(f"已恢复历史: {len(episode_rewards)} ep, best={best_reward:.1f}, "
                        f"从全局 ep{start_ep} 继续")
    if start_ep < 0:
        start_ep = 0

    # curriculum 解析（支持两种格式，均以【全局回合号】判定阶段）：
    #   1) 相对格式 '300-1000-3000'：按本块 episodes 均分（兼容旧用法）
    #   2) 绝对格式 '1000:66,3000:132'：ep66 起 horizon=1000，ep132 起=3000
    #      （分块续训用绝对格式，各块传相同字符串，阶段边界全局一致）
    cur_plan = []  # [(global_ep_boundary, max_steps), ...] 升序
    if curriculum:
        if ':' in curriculum:
            for part in curriculum.split(','):
                h_str, e_str = part.strip().split(':')
                cur_plan.append((int(e_str), int(h_str)))
            cur_plan.sort()
            logger.info(f"curriculum 绝对边界: {cur_plan}")
        else:
            stages = [int(x) for x in curriculum.split('-')]
            per_stage = max(1, episodes // len(stages))
            cur_plan = [(i * per_stage, h) for i, h in enumerate(stages)]
            logger.info(f"curriculum 分段: {stages}（每段约 {per_stage} ep）")

    def _resolve_horizon(gep: int) -> int:
        """按全局回合号返回该回合的 max_steps（curriculum 生效）。"""
        h = max_steps
        for e_bound, h_stage in cur_plan:
            if gep >= e_bound:
                h = h_stage
        return h

    logger.info("=" * 70)
    logger.info("开始训练")
    logger.info("=" * 70)
    start_time = time.time()

    for ep in range(episodes):
        gep = start_ep + ep          # 全局回合号（跨块连续）
        env.max_steps = _resolve_horizon(gep)
        if 'cur_horizon' not in locals() or locals()['cur_horizon'] != env.max_steps:
            cur_horizon = env.max_steps
            logger.info(f"curriculum: 全局 ep{gep+1} → horizon {cur_horizon} 步")
        # 初始速度：默认对齐 Zhang2024 长大下坡循环制动 65 km/h（18.06 m/s）；
        # 若 random_init_speed=True 则随机采样 [init_speed_min, init_speed_max]，
        # 增强策略对多初始条件的鲁棒性（E9 泛化：初始55/75表现差）。
        if random_init_speed:
            init_speed = float(np.random.uniform(init_speed_min, init_speed_max))
        else:
            init_speed = init_speed_kmh / 3.6  # 固定初始速度（默认65，循环制动用80）
        obs, _ = env.reset(options={'speed': init_speed})
        done = False
        ep_reward = 0.0
        ep_peak = 0.0
        ep_viol = 0
        step = 0

        # 【bug修复 2026-08-30】原用基础 max_steps 截断，而 curriculum 改的是
        # env.max_steps → curriculum 静默失效（所有阶段实际都跑 max_steps 步，
        # 与不开 curriculum 结果完全一致）。改为按 env.max_steps 截断。
        while not done and step < env.max_steps:
            flat_obs = obs.flatten()
            actions, log_prob = agent.select_actions(flat_obs)
            action_for_env = actions.reshape(num_agents, act_dim)

            value = agent.get_value(flat_obs)
            if decision_interval > 1:
                # semi-MDP 动作保持：RL 每 N 步决策一次，窗口内奖励求和存一条转移
                # （信用链 15000 步→max_steps/N 条决策；rule 基线不受影响逐步执行）
                next_obs, reward, terminated, truncated = obs, 0.0, False, False
                for _ in range(decision_interval):
                    next_obs, r_step, terminated, truncated, info = env.step(action_for_env)
                    reward += r_step
                    step += 1
                    if terminated or truncated or step >= env.max_steps:
                        break
            else:
                next_obs, reward, terminated, truncated, info = env.step(action_for_env)
                step += 1

            # 【V5.1 修正的适用范围澄清（2026-08-20 审计）】
            # V5.1 教训（安全层修正后需用实际执行动作重算 log_prob）仅适用于
            # "RL 直接输出 throttle 且在同一动作空间被 SafetyLayer 修正"的场景
            # （如 train_cyclic_braking 单列控速）。
            # 本 fleet 环境为分层/映射模式：RL 输出列级动作（δ 协同调整 / 目标
            # 加速度），经底层控制器确定性映射为 throttle 后才执行。策略分布定义
            # 在"RL 输出动作"空间，log_prob 必须基于原始 RL 动作 actions 计算，
            # 用执行 throttle 重算反而是错误（量纲/语义不同，会污染重要性采样）。
            # 因此这里不再用 executed_actions 重算 log_prob，直接存原始 actions。
            # 注：旧的 _executed_actions 恒0 + _actions_modified 恒True 导致每步
            # 用全0动作重算 log_prob（PPO 重要性采样完全失效，E19-E24 训练可信度
            # 受质疑），已由 env 修复（executed 正确记录 + actions_modified=False）。
            done = terminated or truncated or step >= env.max_steps
            agent.store_transition(flat_obs, actions, reward, log_prob, done, value)

            ep_reward += reward
            ep_peak = max(ep_peak, info.get('coupler_force_peak', 0))
            ep_viol = info.get('coupler_limit_violations', 0)
            obs = next_obs

        metrics = agent.update()

        episode_rewards.append(ep_reward)
        episode_peak_coupler.append(ep_peak / 1e3)  # kN
        episode_violations.append(ep_viol)
        if ep_reward > best_reward:
            best_reward = ep_reward
            # 保存 best 模型（策略最优时的 checkpoint）——论文评估应报告 best 而非末 ep
            # （V5.14 教训：策略可能后期退化，末 ep 模型性能可能差于早期）
            # 文件名含 coupler 标识（消融实验：有车钩力 _cp / 无车钩力 _nocp）
            cp_tag = f"{'dec_' if decompose else ''}ad{act_dim}{'g' if group_obs else ''}_{'m'+mask_lever if mask_lever and mask_lever != 'none' else ''}_{'cp' if use_coupler_constraint else 'nocp'}"
            agent.save(str(Path(checkpoint_dir) / f"mappo_fleet_best_{cp_tag}_seed{seed}.pt"))

        if (gep + 1) % 10 == 0 or ep == episodes - 1:
            recent = np.mean(episode_rewards[-10:]) if len(episode_rewards) >= 10 else np.mean(episode_rewards)
            recent_peak = np.mean(episode_peak_coupler[-10:])
            recent_viol = np.mean(episode_violations[-10:])
            logger.info(
                f"Ep {gep+1}(块{ep+1}/{episodes}) | Reward {ep_reward:+.1f} (avg {recent:+.1f}) | "
                f"best {best_reward:+.1f} | peakCoupler {recent_peak:.0f}kN | "
                f"viol {recent_viol:.1f} | loss {metrics.get('total_loss',0):.3f}"
            )
            sys.stdout.flush()
            # checkpoint 带 seed + coupler 标识 + 【全局回合号】ep{gep+1}
            cp_tag = f"{'dec_' if decompose else ''}ad{act_dim}{'g' if group_obs else ''}_{'m'+mask_lever if mask_lever and mask_lever != 'none' else ''}_{'cp' if use_coupler_constraint else 'nocp'}"
            agent.save(str(Path(checkpoint_dir) / f"mappo_fleet_ep{gep+1}_{cp_tag}_seed{seed}.pt"))

        # 【2026-08-30】训练历史落盘 + 学习曲线图（论文/PPT 用，前台中断也不丢数据）
        if (gep + 1) % 10 == 0 or ep == episodes - 1:
            cp_tag = f"{'dec_' if decompose else ''}ad{act_dim}{'g' if group_obs else ''}_{'m'+mask_lever if mask_lever and mask_lever != 'none' else ''}_{'cp' if use_coupler_constraint else 'nocp'}"
            save_training_artifacts(
                episode_rewards, episode_peak_coupler, episode_violations,
                meta={
                    'seed': seed, 'episodes': len(episode_rewards),
                    'num_trains': num_trains,
                    'grade_profile': grade_profile, 'max_steps': max_steps,
                    'curriculum': curriculum, 'start_ep': start_ep,
                    'hierarchical': hierarchical, 'adj_coef': adj_coef,
                    'action_dim': action_dim,   # 【方向A】1=整带平移；2=v_max/v_min 独立偏移
                    'group_obs': group_obs,     # 【方向B】全局一致性观测
                    'decompose': decompose,     # 【ADR-009.1】逐机车电空分工模式
                    'coupler_constraint': use_coupler_constraint,
                    'best_reward': float(best_reward),
                    'physics': 'R0(2026-09-06)+MT2统一(2026-09-07): 全列MT-2 Stribeck 750/500 + 卸载刚度 + 牵规β_c + 并行波速 + 段间衰减D + 两段式缓解τ=6s + Newmark-β',
                },
                results_dir=results_dir,
                figures_dir='outputs/figures',
                tag=f"{cp_tag}_seed{seed}",
            )

    total_time = time.time() - start_time
    logger.info("=" * 70)
    logger.info(f"训练完成！总耗时 {total_time:.1f}s ({total_time/60:.1f}min)")
    logger.info(f"最佳奖励: {best_reward:.2f}")
    logger.info(f"最终平均奖励: {np.mean(episode_rewards[-10:]):.2f}")
    logger.info(f"平均车钩力峰值: {np.mean(episode_peak_coupler[-10:]):.1f} kN")
    logger.info(f"平均超限次数: {np.mean(episode_violations[-10:]):.1f}")
    logger.info(f"模型已保存: {checkpoint_dir}")
    # 【防漏】训练结束强制校验权威 metadata.json 已生成（入口 save_metadata 已写）
    assert_training_metadata(results_dir)
    logger.info("=" * 70)

    return {
        'rewards': episode_rewards,
        'peak_coupler_kN': episode_peak_coupler,
        'violations': episode_violations,
        'best_reward': best_reward,
        'num_trains': num_trains,
        'grade_profile': grade_profile,
    }


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='重载列车群组（多列编队）MAPPO 训练')
    parser.add_argument('--episodes', type=int, default=200)
    parser.add_argument('--num_trains', type=int, default=3)
    parser.add_argument('--preset', type=str, default='10kt_1plus0')
    parser.add_argument('--grade', type=str, default='shuozhou_real_53km',
                        help='坡度剖面（默认朔黄完整真实纵断面 53.2km，循环制动）')
    parser.add_argument('--target_speed', type=float, default=None,
                        help='巡航参考速度（默认取限速区间中值）')
    parser.add_argument('--target_gap', type=float, default=100.0)
    parser.add_argument('--max_steps', type=int, default=300)
    parser.add_argument('--v_max', type=float, default=80.0 / 3.6,
                        help='限速上限 m/s（默认 80 km/h，朔黄线线路限速，Zhang2024）')
    parser.add_argument('--v_min', type=float, default=40.0 / 3.6,
                        help='限速下限 m/s（默认 40 km/h，重载最小缓解速度，Zhang2024）')
    parser.add_argument('--lr', type=float, default=5e-5)
    parser.add_argument('--entropy', type=float, default=0.005)
    parser.add_argument('--batch_size', type=int, default=64)
    parser.add_argument('--epochs', type=int, default=4)
    parser.add_argument('--device', type=str, default=None)
    parser.add_argument('--seed', type=int, default=42)
    parser.add_argument('--simcase', type=str, default='official', choices=['official', 'debug'],
                        help='【治理】official=正式(调试物理禁入训练)；debug=调试/探针(不落正式结论)')
    parser.add_argument('--max_accel', type=float, default=1.0)
    parser.add_argument('--enable_disturbance', action='store_true',
                        help='开启领航车突发减速扰动（协同制动场景）')
    parser.add_argument('--disturbance_step', type=int, default=150)
    parser.add_argument('--disturbance_duration', type=int, default=300,
                        help='扰动持续步数（短暂窗口模拟临时限速，训练加扰动鲁棒性）')
    parser.add_argument('--disturbance_target_accel', type=float, default=-0.8)
    parser.add_argument('--no_coupler_constraint', action='store_true',
                        help='关闭车钩力约束（消融实验：模拟忽略车钩力）')
    parser.add_argument('--hierarchical', action='store_true',
                        help='分层模式：第1层策略控速，RL 只学协同调整（E4）')
    parser.add_argument('--random_init_speed', action='store_true',
                        help='训练时随机化初始速度 [55,75]km/h，增强多初始条件鲁棒性（E9泛化）')
    parser.add_argument('--init_speed_min', type=float, default=55.0 / 3.6)
    parser.add_argument('--init_speed_max', type=float, default=75.0 / 3.6)
    parser.add_argument('--init_speed_kmh', type=float, default=65.0,
                        help='固定初始速度 km/h（默认65，循环制动场景用80）')
    parser.add_argument('--layer1_checkpoint', type=str,
                        default='outputs/checkpoints/cyclic_mappo_best_seed0_v40-80_init80.pt',
                        help='第1层单列控速策略 checkpoint（[40,80]限速）')
    parser.add_argument('--adj_coef', type=float, default=0.3,
                        help='协同调整量缩放系数（分层模式）')
    parser.add_argument('--action_dim', type=int, default=1,
                        help='【方向A】协同动作维度：1=coor_adj 整带平移（兼容旧）；2=v_max/v_min 独立偏移(压缩带宽)')
    parser.add_argument('--group_obs', action='store_true',
                        help='【方向B】启用全局一致性观测（obs_dim 11→13，修根因3）')
    parser.add_argument('--decompose', type=str, default=None, choices=['loco_ed_ab'],
                        help='【ADR-009.1 换架构】loco_ed_ab=逐机车 RL 智能体（每机车独立 ED/AB 分配'
                             '调制，需配 10kt_1plus1 等多机车编组）；默认 None=旧列级模式')
    parser.add_argument('--decision_interval', type=int, default=1,
                        help='【RL 层救回①】decompose 模式 RL 决策间隔 N（动作保持 N 步，'
                             'semi-MDP 砍短信用链；rule 基线仍逐步执行），建议 10')
    parser.add_argument('--mask_lever', type=str, default='none', choices=['none', 'ed', 'ab'],
                        help='【杠杆隔离消融】none=双杠杆；ed=禁用 ed_mod(仅 AB 杠杆)；'
                             'ab=禁用 ab_mod(仅 ED 杠杆)。训练与评估须一致。')
    parser.add_argument('--hetero', action='store_true',
                        help='【E4-H 车钩异构】训练在逐车钩独立参数分布上（分布内）；评估 held-out 用另一组 hetero_seed')
    parser.add_argument('--hetero_seed', type=int, default=0,
                        help='车钩异构抽样 seed（训练固定；评估 held-out 用另一组）')
    parser.add_argument('--enable_etcs', action='store_true',
                        help='训练时启用 ETCS 真 ATP（与评估 --etcs 对齐，消除分布不一致）')
    parser.add_argument('--checkpoint_dir', type=str, default='outputs/checkpoints',
                        help='checkpoint 输出目录（多 run 并行不互相覆盖）')
    parser.add_argument('--results_dir', type=str, default='outputs/results',
                        help='结果输出目录')
    parser.add_argument('--curriculum', type=str, default=None,
                        help='curriculum 递增 horizon：如 "300-1000-3000"，分段增强长程泛化（缓解短训过拟合）')
    parser.add_argument('--resume', type=str, default=None,
                        help='续训检查点路径（加载策略+优化器继续训练，前台分块训练用）')
    parser.add_argument('--start_ep', type=int, default=-1,
                        help='起始全局回合号（-1=从 resume 历史推断；分块续训时传入已完成回合数）')

    args = parser.parse_args()
    train(
        episodes=args.episodes,
        num_trains=args.num_trains,
        consist_preset=args.preset,
        grade_profile=args.grade,
        target_speed=args.target_speed,
        target_gap=args.target_gap,
        max_steps=args.max_steps,
        v_max=args.v_max,
        v_min=args.v_min,
        lr=args.lr,
        entropy=args.entropy,
        batch_size=args.batch_size,
        epochs=args.epochs,
        device=args.device,
        seed=args.seed,
        case=args.simcase,
        max_accel=args.max_accel,
        enable_disturbance=args.enable_disturbance,
        disturbance_step=args.disturbance_step,
        disturbance_duration=args.disturbance_duration,
        disturbance_target_accel=args.disturbance_target_accel,
        use_coupler_constraint=not args.no_coupler_constraint,
        hierarchical=args.hierarchical,
        layer1_checkpoint=args.layer1_checkpoint,
        adj_coef=args.adj_coef,
        action_dim=args.action_dim,
        group_obs=args.group_obs,
        decompose=args.decompose,
        decision_interval=args.decision_interval,
        mask_lever=args.mask_lever,
        hetero=args.hetero,
        hetero_seed=args.hetero_seed,
        enable_etcs=args.enable_etcs,
        random_init_speed=args.random_init_speed,
        init_speed_min=args.init_speed_min,
        init_speed_max=args.init_speed_max,
        init_speed_kmh=args.init_speed_kmh,
        curriculum=args.curriculum,
        checkpoint_dir=args.checkpoint_dir,
        results_dir=args.results_dir,
        resume=args.resume,
        start_ep=args.start_ep,
    )
