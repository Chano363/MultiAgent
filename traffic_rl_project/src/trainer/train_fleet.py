"""
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


def save_training_artifacts(
    rewards, peak_coupler, violations, meta, results_dir, figures_dir, tag
):
    """保存训练历史（JSON/CSV）并绘制学习曲线 PNG（论文/PPT 用）。

    每次调用都全量覆写，保证训练中断（前台超时）后已有数据不丢失。
    """
    import json
    import csv

    Path(results_dir).mkdir(parents=True, exist_ok=True)
    Path(figures_dir).mkdir(parents=True, exist_ok=True)
    hist = {
        'rewards': [float(r) for r in rewards],
        'peak_coupler_kN': [float(c) for c in peak_coupler],
        'violations': [float(v) for v in violations],
        'meta': meta,
    }
    with open(Path(results_dir) / f"train_history_{tag}.json", 'w',
              encoding='utf-8') as f:
        json.dump(hist, f, ensure_ascii=False, indent=2)
    with open(Path(results_dir) / f"train_history_{tag}.csv", 'w',
              newline='', encoding='utf-8') as f:
        w = csv.writer(f)
        w.writerow(['episode', 'reward', 'peak_coupler_kN', 'violations'])
        for i, (r, c, v) in enumerate(zip(rewards, peak_coupler, violations)):
            w.writerow([i + 1, f"{r:.2f}", f"{c:.1f}", f"{v:.1f}"])

    # 学习曲线图（三子图：reward 原始+10ep滑动平均 / 车钩力峰值 / 超限次数）
    try:
        import matplotlib
        matplotlib.use('Agg')
        import matplotlib.pyplot as plt
        from src.utils.plot_style import setup_cjk_font
        setup_cjk_font()

        eps = np.arange(1, len(rewards) + 1)
        fig, axes = plt.subplots(3, 1, figsize=(8, 9), sharex=True)
        axes[0].plot(eps, rewards, alpha=0.35, color='tab:blue', label='每回合')
        if len(rewards) >= 10:
            ma = np.convolve(rewards, np.ones(10) / 10, mode='valid')
            axes[0].plot(eps[9:], ma, color='tab:blue', lw=2,
                         label='10 回合滑动平均')
        axes[0].axhline(0, color='gray', lw=0.6, ls='--')
        axes[0].set_ylabel('回合奖励')
        axes[0].legend(loc='lower right', fontsize=8)
        axes[0].set_title(f'MAPPO 群组协同训练曲线（{tag}）', fontsize=11)

        axes[1].plot(eps, peak_coupler, alpha=0.35, color='tab:orange')
        if len(peak_coupler) >= 10:
            ma_c = np.convolve(peak_coupler, np.ones(10) / 10, mode='valid')
            axes[1].plot(eps[9:], ma_c, color='tab:orange', lw=2)
        axes[1].axhline(1000, color='red', lw=1.0, ls='--', label='1000 kN 安全限值')
        axes[1].set_ylabel('车钩力峰值 (kN)')
        axes[1].legend(loc='upper right', fontsize=8)

        axes[2].plot(eps, violations, alpha=0.35, color='tab:green')
        if len(violations) >= 10:
            ma_v = np.convolve(violations, np.ones(10) / 10, mode='valid')
            axes[2].plot(eps[9:], ma_v, color='tab:green', lw=2)
        axes[2].set_ylabel('车钩力超限次数')
        axes[2].set_xlabel('训练回合')
        for ax in axes:
            ax.grid(alpha=0.3)
        fig.tight_layout()
        fig.savefig(Path(figures_dir) / f"fig_learning_curve_{tag}.png", dpi=150)
        plt.close(fig)
    except Exception as e:  # 绘图失败不应中断训练
        logger.warning(f"[警告] 学习曲线绘制失败（训练继续）: {e}")


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
    v_max: float = 80.0 / 3.6,
    v_min: float = 40.0 / 3.6,
    lr: float = 5e-5,
    entropy: float = 0.005,
    batch_size: int = 64,
    epochs: int = 4,
    device: str = None,
    seed: int = 42,
    max_accel: float = 1.0,
    enable_disturbance: bool = False,
    disturbance_step: int = 150,
    disturbance_duration: int = 300,
    disturbance_target_accel: float = -0.8,
    use_coupler_constraint: bool = True,
    hierarchical: bool = False,
    layer1_checkpoint: str = 'outputs/checkpoints/cyclic_mappo_best_seed0_v40-80_init80.pt',
    adj_coef: float = 0.3,
    random_init_speed: bool = False,
    init_speed_min: float = 55.0 / 3.6,
    init_speed_max: float = 75.0 / 3.6,
    init_speed_kmh: float = 65.0,   # 固定初始速度（km/h），循环制动场景用 80
    checkpoint_dir: str = 'outputs/checkpoints',
    results_dir: str = 'outputs/results',
    curriculum: str = None,          # 可选：'300-1000-3000' 形式，递增 horizon 分段训练（增强长程泛化）
    resume: str = None,              # 可选：续训检查点路径（加载策略继续训练，前台分块训练用）
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
    }
    if target_speed is not None:
        env_cfg['target_speed'] = target_speed
    env = make_env(env_cfg)

    obs_dim = env.obs_dim       # 每列观测维度（6）
    act_dim = 1                 # 每列动作维度（1）

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
        num_drones=num_trains,   # 智能体 = 列数
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
    if resume and Path(resume).exists():
        agent.load(resume)
        logger.info(f"已加载续训检查点: {resume}")
    elif resume:
        logger.warning(f"[警告] 续训检查点不存在，从头训练: {resume}")

    episode_rewards = []
    episode_peak_coupler = []
    episode_violations = []
    best_reward = float('-inf')

    # curriculum 解析：'300-1000-3000' → 分段递增 horizon，每段平均分配 episodes。
    # 通过动态调整 env.max_steps 实现（env 的 truncated 判断用 self.max_steps）。
    cur_stages = []
    if curriculum:
        cur_stages = [int(x) for x in curriculum.split('-')]
        per_stage = max(1, episodes // len(cur_stages))
        logger.info(f"curriculum 分段: {cur_stages}（每段约 {per_stage} ep）")

    logger.info("=" * 70)
    logger.info("开始训练")
    logger.info("=" * 70)
    start_time = time.time()

    for ep in range(episodes):
        # curriculum：按当前 episode 所在阶段设置 env.max_steps（递增 horizon）
        if cur_stages:
            stage_idx = min(ep // per_stage, len(cur_stages) - 1)
            env.max_steps = cur_stages[stage_idx]
            if 'cur_stage' not in locals() or locals()['cur_stage'] != stage_idx:
                cur_stage = stage_idx
                logger.info(f"curriculum 阶段切换: ep{ep+1} → horizon {env.max_steps} 步")
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
            action_for_env = actions.reshape(num_trains, 1)

            value = agent.get_value(flat_obs)
            next_obs, reward, terminated, truncated, info = env.step(action_for_env)

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
            done = terminated or truncated
            agent.store_transition(flat_obs, actions, reward, log_prob, done, value)

            ep_reward += reward
            ep_peak = max(ep_peak, info.get('coupler_force_peak', 0))
            ep_viol = info.get('coupler_limit_violations', 0)
            obs = next_obs
            step += 1

        metrics = agent.update()

        episode_rewards.append(ep_reward)
        episode_peak_coupler.append(ep_peak / 1e3)  # kN
        episode_violations.append(ep_viol)
        if ep_reward > best_reward:
            best_reward = ep_reward
            # 保存 best 模型（策略最优时的 checkpoint）——论文评估应报告 best 而非末 ep
            # （V5.14 教训：策略可能后期退化，末 ep 模型性能可能差于早期）
            # 文件名含 coupler 标识（消融实验：有车钩力 _cp / 无车钩力 _nocp）
            cp_tag = 'cp' if use_coupler_constraint else 'nocp'
            agent.save(str(Path(checkpoint_dir) / f"mappo_fleet_best_{cp_tag}_seed{seed}.pt"))

        if (ep + 1) % 10 == 0 or ep == episodes - 1:
            recent = np.mean(episode_rewards[-10:]) if len(episode_rewards) >= 10 else np.mean(episode_rewards)
            recent_peak = np.mean(episode_peak_coupler[-10:])
            recent_viol = np.mean(episode_violations[-10:])
            logger.info(
                f"Ep {ep+1}/{episodes} | Reward {ep_reward:+.1f} (avg {recent:+.1f}) | "
                f"best {best_reward:+.1f} | peakCoupler {recent_peak:.0f}kN | "
                f"viol {recent_viol:.1f} | loss {metrics.get('total_loss',0):.3f}"
            )
            sys.stdout.flush()
            # checkpoint 带 seed + coupler 标识（多种子/消融训练不互相覆盖）
            cp_tag = 'cp' if use_coupler_constraint else 'nocp'
            agent.save(str(Path(checkpoint_dir) / f"mappo_fleet_ep{ep+1}_{cp_tag}_seed{seed}.pt"))

        # 【2026-08-30】训练历史落盘 + 学习曲线图（论文/PPT 用，前台中断也不丢数据）
        if (ep + 1) % 10 == 0 or ep == episodes - 1:
            cp_tag = 'cp' if use_coupler_constraint else 'nocp'
            save_training_artifacts(
                episode_rewards, episode_peak_coupler, episode_violations,
                meta={
                    'seed': seed, 'episodes': episodes, 'num_trains': num_trains,
                    'grade_profile': grade_profile, 'max_steps': max_steps,
                    'hierarchical': hierarchical, 'adj_coef': adj_coef,
                    'coupler_constraint': use_coupler_constraint,
                    'best_reward': float(best_reward),
                    'physics': 'MT2-hysteresis+real-brake+parallel-wave (2026-08-30 基线对齐)',
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
    parser.add_argument('--grade', type=str, default='shuozhou_23800',
                        help='坡度剖面（默认朔黄线真实剖面，循环制动）')
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
    parser.add_argument('--checkpoint_dir', type=str, default='outputs/checkpoints',
                        help='checkpoint 输出目录（多 run 并行不互相覆盖）')
    parser.add_argument('--results_dir', type=str, default='outputs/results',
                        help='结果输出目录')
    parser.add_argument('--curriculum', type=str, default=None,
                        help='curriculum 递增 horizon：如 "300-1000-3000"，分段增强长程泛化（缓解短训过拟合）')
    parser.add_argument('--resume', type=str, default=None,
                        help='续训检查点路径（加载策略+优化器继续训练，前台分块训练用）')

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
        max_accel=args.max_accel,
        enable_disturbance=args.enable_disturbance,
        disturbance_step=args.disturbance_step,
        disturbance_duration=args.disturbance_duration,
        disturbance_target_accel=args.disturbance_target_accel,
        use_coupler_constraint=not args.no_coupler_constraint,
        hierarchical=args.hierarchical,
        layer1_checkpoint=args.layer1_checkpoint,
        adj_coef=args.adj_coef,
        random_init_speed=args.random_init_speed,
        init_speed_min=args.init_speed_min,
        init_speed_max=args.init_speed_max,
        init_speed_kmh=args.init_speed_kmh,
        curriculum=args.curriculum,
        checkpoint_dir=args.checkpoint_dir,
        results_dir=args.results_dir,
        resume=args.resume,
    )
