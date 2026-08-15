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
    grade_profile: str = 'long_downhill',
    target_speed: float = 20.0,
    target_gap: float = 100.0,
    max_steps: int = 300,
    lr: float = 5e-5,
    entropy: float = 0.005,
    batch_size: int = 64,
    epochs: int = 4,
    device: str = None,
    seed: int = 42,
    max_accel: float = 1.0,
    enable_disturbance: bool = False,
    disturbance_step: int = 150,
    disturbance_target_accel: float = -0.8,
    checkpoint_dir: str = 'outputs/checkpoints',
    results_dir: str = 'outputs/results',
):
    if device is None:
        device = 'cuda' if torch.cuda.is_available() else 'cpu'

    set_seed(seed)

    env_cfg = {
        'num_trains': num_trains,
        'consist_preset': consist_preset,
        'grade_profile': grade_profile,
        'target_speed': target_speed,
        'target_gap': target_gap,
        'max_steps': max_steps,
        'max_accel': max_accel,
        'enable_disturbance': enable_disturbance,
        'disturbance_step': disturbance_step,
        'disturbance_target_accel': disturbance_target_accel,
    }
    env = make_env(env_cfg)

    obs_dim = env.obs_dim       # 每列观测维度（6）
    act_dim = 1                 # 每列动作维度（1）

    logger.info("=" * 70)
    logger.info("重载列车群组（多列编队）MAPPO 训练")
    logger.info("=" * 70)
    logger.info(f"编队列数: {num_trains} 列")
    logger.info(f"单列编组: {consist_preset}")
    logger.info(f"坡度剖面: {grade_profile}")
    logger.info(f"目标速度: {target_speed} m/s | 列间目标间距: {target_gap} m")
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

    episode_rewards = []
    episode_peak_coupler = []
    episode_violations = []
    best_reward = float('-inf')

    logger.info("=" * 70)
    logger.info("开始训练")
    logger.info("=" * 70)
    start_time = time.time()

    for ep in range(episodes):
        obs, _ = env.reset(options={'speed': target_speed * 0.8})
        done = False
        ep_reward = 0.0
        ep_peak = 0.0
        ep_viol = 0
        step = 0

        while not done and step < max_steps:
            flat_obs = obs.flatten()
            actions, log_prob = agent.select_actions(flat_obs)
            action_for_env = actions.reshape(num_trains, 1)

            value = agent.get_value(flat_obs)
            next_obs, reward, terminated, truncated, info = env.step(action_for_env)

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
            agent.save(str(Path(checkpoint_dir) / f"mappo_fleet_best_seed{seed}.pt"))

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
            # checkpoint 带 seed 后缀（多种子训练不互相覆盖）
            agent.save(str(Path(checkpoint_dir) / f"mappo_fleet_ep{ep+1}_seed{seed}.pt"))

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
    parser.add_argument('--grade', type=str, default='long_downhill')
    parser.add_argument('--target_speed', type=float, default=20.0)
    parser.add_argument('--target_gap', type=float, default=100.0)
    parser.add_argument('--max_steps', type=int, default=300)
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
    parser.add_argument('--disturbance_target_accel', type=float, default=-0.8)

    args = parser.parse_args()
    train(
        episodes=args.episodes,
        num_trains=args.num_trains,
        consist_preset=args.preset,
        grade_profile=args.grade,
        target_speed=args.target_speed,
        target_gap=args.target_gap,
        max_steps=args.max_steps,
        lr=args.lr,
        entropy=args.entropy,
        batch_size=args.batch_size,
        epochs=args.epochs,
        device=args.device,
        seed=args.seed,
        max_accel=args.max_accel,
        enable_disturbance=args.enable_disturbance,
        disturbance_step=args.disturbance_step,
        disturbance_target_accel=args.disturbance_target_accel,
    )
