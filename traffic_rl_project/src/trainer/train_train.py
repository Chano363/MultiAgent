"""
重载列车群组 MARL 训练入口（P1 第15条：MAPPO 迁移到列车）。

复用阶段一验证过的 MAPPOAgent（共享策略 + 集中式 Critic + GAE + KL 早停），
迁移到列车环境 TrainFormationEnv（长大下坡 + 万吨级 1+0 编组）。

对齐论文题目：面向长大下坡场景基于多智能体强化学习的重载列车群组自动控制方法。
目标：长大下坡循环制动自动控制（智能体输出牵引/制动动作 = 自动控制）。

不依赖 Agent Lightning，保持简洁可复现。不动阶段一无人机代码。
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
logger = logging.getLogger('TrainRL')

from src.environments.train_env import TrainFormationEnv
from src.algorithms.mappo_agent import MAPPOAgent


def set_seed(seed: int):
    np.random.seed(seed)
    torch.manual_seed(seed)
    if torch.cuda.is_available():
        torch.cuda.manual_seed(seed)


def make_env(config: Dict) -> TrainFormationEnv:
    """构造列车环境（支持万吨级 1+0 + 长大下坡）。"""
    return TrainFormationEnv(config)


def train(
    episodes: int = 100,
    num_vehicles: int = None,
    consist_preset: str = '10kt_1plus0',
    grade_profile: str = 'long_downhill',
    target_speed: float = 20.0,
    max_steps: int = 300,
    learning_rate: float = 5e-5,
    entropy_coef: float = 0.005,
    epochs: int = 4,
    batch_size: int = 64,
    device: str = None,
    seed: int = 42,
    checkpoint_dir: str = 'outputs/checkpoints',
    results_dir: str = 'outputs/results',
):
    """训练 MAPPO 控制列车在长大下坡场景自动控制。"""
    device = device or ('cuda' if torch.cuda.is_available() else 'cpu')
    set_seed(seed)

    env_cfg = {
        'num_vehicles': num_vehicles or 101,  # 万吨级 1+0
        'consist_preset': consist_preset,
        'grade_profile': grade_profile,
        'target_speed': target_speed,
        'max_steps': max_steps,
        'enable_safety': True,
    }
    env = make_env(env_cfg)

    num_vehicles = env.num_vehicles
    obs_dim = env.obs_dim           # 每节车观测维度 = 4
    act_dim = 1                     # 每节车动作维度 = 1
    total_obs = num_vehicles * obs_dim

    logger.info("=" * 70)
    logger.info("重载列车群组 MARL 训练（MAPPO）")
    logger.info("=" * 70)
    logger.info(f"编组: {consist_preset} ({num_vehicles}节, {sum(v.mass_t for v in env.dynamics.consist.vehicles):.0f}t)")
    logger.info(f"坡度剖面: {grade_profile}")
    logger.info(f"目标速度: {target_speed} m/s")
    logger.info(f"每节车 obs={obs_dim}维, act={act_dim}维")
    logger.info(f"设备: {device}")

    agent = MAPPOAgent(
        num_drones=num_vehicles,        # 复用参数名，实为车辆数
        obs_per_drone=obs_dim,
        act_per_drone=act_dim,
        learning_rate=learning_rate,
        gamma=0.99,
        gae_lambda=0.95,
        clip_epsilon=0.2,
        entropy_coef=entropy_coef,
        value_coef=0.5,
        epochs=epochs,
        batch_size=batch_size,
        max_grad_norm=0.5,
        device=device,
        use_gae=True,
        use_clipped_value_loss=True,
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
            # MAPPO 动作 ∈ [-1,1]，直接作为 throttle（正=牵引，负=制动）
            action_for_env = actions.reshape(num_vehicles, 1)

            value = agent.get_value(flat_obs)
            next_obs, reward, terminated, truncated, info = env.step(action_for_env)

            done = terminated or truncated
            agent.store_transition(flat_obs, actions, reward, log_prob, done, value)

            ep_reward += reward
            ep_peak = max(ep_peak, info.get('coupler_force_peak', 0))
            ep_viol += info.get('coupler_limit_violations', 0)
            obs = next_obs
            step += 1

        metrics = agent.update()

        episode_rewards.append(ep_reward)
        episode_peak_coupler.append(ep_peak / 1e3)  # kN
        episode_violations.append(ep_viol)
        if ep_reward > best_reward:
            best_reward = ep_reward

        if (ep + 1) % 10 == 0 or ep == episodes - 1:
            recent = np.mean(episode_rewards[-10:]) if len(episode_rewards) >= 10 else np.mean(episode_rewards)
            recent_peak = np.mean(episode_peak_coupler[-10:])
            recent_viol = np.mean(episode_violations[-10:])
            logger.info(
                f"Ep {ep+1}/{episodes} | Reward {ep_reward:+.1f} (avg {recent:+.1f}) | "
                f"best {best_reward:+.1f} | peakCoupler {recent_peak:.0f}kN | "
                f"viol {recent_viol:.1f} | loss {metrics.get('total_loss',0):.3f}"
            )
            sys.stdout.flush()  # 强制刷出进度日志（双保险）
            agent.save(str(Path(checkpoint_dir) / f"mappo_train_ep{ep+1}.pt"))

    total_time = time.time() - start_time
    logger.info("=" * 70)
    logger.info(f"训练完成！总耗时 {total_time:.1f}s ({total_time/60:.1f}min)")
    logger.info(f"最佳奖励: {best_reward:.2f}")
    logger.info(f"最终平均奖励: {np.mean(episode_rewards[-10:]):.2f}")
    logger.info(f"平均车钩力峰值: {np.mean(episode_peak_coupler):.1f} kN")
    logger.info(f"平均超限次数: {np.mean(episode_violations):.1f}")
    logger.info(f"模型已保存: {checkpoint_dir}")
    logger.info("=" * 70)

    return {
        'rewards': episode_rewards,
        'peak_coupler_kN': episode_peak_coupler,
        'violations': episode_violations,
        'best_reward': best_reward,
        'num_vehicles': num_vehicles,
        'grade_profile': grade_profile,
    }


def main():
    parser = argparse.ArgumentParser(description='重载列车群组 MAPPO 训练')
    parser.add_argument('--episodes', type=int, default=100)
    parser.add_argument('--preset', type=str, default='10kt_1plus0')
    parser.add_argument('--grade', type=str, default='long_downhill')
    parser.add_argument('--target_speed', type=float, default=20.0)
    parser.add_argument('--max_steps', type=int, default=300)
    parser.add_argument('--lr', type=float, default=5e-5)
    parser.add_argument('--entropy', type=float, default=0.005)
    parser.add_argument('--device', type=str, default=None)
    args = parser.parse_args()

    train(
        episodes=args.episodes,
        consist_preset=args.preset,
        grade_profile=args.grade,
        target_speed=args.target_speed,
        max_steps=args.max_steps,
        learning_rate=args.lr,
        entropy_coef=args.entropy,
        device=args.device,
    )


if __name__ == "__main__":
    main()
