"""
无人机编队控制强化学习系统
主入口文件 - 基于 gym-pybullet-drones 专业物理仿真器
"""

import os
import sys
import argparse
from pathlib import Path

sys.path.append(str(Path(__file__).parent.parent))

from src.environments.formation_control_env import FormationControlEnv
from src.algorithms import PPOAgent, DQNAgent
from src.utils import MetricsTracker, plot_training_curve, save_results
import numpy as np


def parse_args():
    """解析命令行参数"""
    parser = argparse.ArgumentParser(
        description='Drone Formation Control RL - Main Entry'
    )

    parser.add_argument(
        '--mode',
        type=str,
        default='train',
        choices=['train', 'test', 'demo'],
        help='运行模式: train (训练), test (测试), demo (演示)'
    )

    parser.add_argument(
        '--algorithm',
        type=str,
        default='PPO',
        choices=['DQN', 'PPO'],
        help='强化学习算法'
    )

    parser.add_argument(
        '--episodes',
        type=int,
        default=50,
        help='训练回合数'
    )

    parser.add_argument(
        '--max_steps',
        type=int,
        default=1000,
        help='每个回合最大步数'
    )

    parser.add_argument(
        '--num_drones',
        type=int,
        default=3,
        help='无人机数量'
    )

    parser.add_argument(
        '--device',
        type=str,
        default='cuda' if os.environ.get('CUDA_VISIBLE_DEVICES') else 'cpu',
        help='计算设备'
    )

    parser.add_argument(
        '--checkpoint',
        type=str,
        default=None,
        help='模型检查点路径'
    )

    parser.add_argument(
        '--render',
        action='store_true',
        default=False,
        help='是否启用可视化渲染'
    )

    return parser.parse_args()


def train(args):
    """训练函数"""
    print("=" * 60)
    print("Drone Formation Control RL - Training Mode")
    print("=" * 60)
    print(f"Algorithm: {args.algorithm}")
    print(f"Episodes: {args.episodes}")
    print(f"Max Steps per Episode: {args.max_steps}")
    print(f"Number of Drones: {args.num_drones}")
    print(f"Render: {args.render}")
    print("=" * 60)

    try:
        env = FormationControlEnv(
            num_drones=args.num_drones,
            render_mode='human' if args.render else None
        )
    except Exception as e:
        print(f"\n✗ Failed to create environment: {e}")
        print("\n⚠ Note: gym-pybullet-drones must be installed properly.")
        return

    print(f"\n✓ Environment created successfully")
    print(f"  - Observation space: {env.observation_space}")
    print(f"  - Action space: {env.action_space}")

    state_dim = env.observation_space.shape[0]
    action_dim = env.action_space.shape[0]

    if args.algorithm == 'DQN':
        agent = DQNAgent(
            state_dim=state_dim,
            action_dim=action_dim,
            learning_rate=1e-3,
            gamma=0.99,
            device=args.device
        )
    else:
        agent = PPOAgent(
            state_dim=state_dim,
            action_dim=action_dim,
            device=args.device
        )

    if args.checkpoint:
        agent.load(args.checkpoint)
        print(f"\n✓ Loaded checkpoint from: {args.checkpoint}")

    tracker = MetricsTracker()

    print("\n开始训练...")
    print("-" * 60)

    for episode in range(args.episodes):
        obs, info = env.reset()
        episode_reward = 0
        episode_loss = 0
        update_count = 0

        for step in range(args.max_steps):
            state = obs

            if args.algorithm == 'DQN':
                action = agent.select_action(state, training=True)
            else:
                action, log_prob = agent.select_action(state)

            next_obs, reward, terminated, truncated, info = env.step(action)

            done = terminated or truncated

            if args.algorithm == 'DQN':
                agent.store_transition(state, action, reward, next_obs, done)
                loss = agent.update()
                if loss > 0:
                    episode_loss += loss
                    update_count += 1
            else:
                agent.store_transition(state, action, reward, log_prob, done)
                if step % 100 == 0:
                    values = [0] * 100
                    metrics = agent.update(values)
                    episode_loss += abs(metrics.get('policy_loss', 0))

            episode_reward += reward
            obs = next_obs

            if done:
                break

        if args.algorithm == 'DQN' and episode % 10 == 0:
            agent.update_target_network()

        tracker.add_reward(episode_reward)
        tracker.add_loss(episode_loss / max(update_count, 1))

        if (episode + 1) % 10 == 0:
            recent_rewards = tracker.metrics['rewards'][-10:]
            avg_reward = np.mean(recent_rewards)
            print(f"Episode {episode + 1}/{args.episodes} | "
                  f"Reward: {episode_reward:.2f} | "
                  f"Avg(10): {avg_reward:.2f}" +
                  (f" | Epsilon: {agent.epsilon:.4f}" if args.algorithm == 'DQN' else ""))

    env.close()

    print("-" * 60)
    print("训练完成!")

    save_dir = Path("outputs")
    save_dir.mkdir(parents=True, exist_ok=True)

    tracker.save(str(save_dir / "training_metrics"))
    plot_training_curve(tracker, str(save_dir / "training_curve.png"))
    print(f"\n训练指标已保存到: {save_dir / 'training_metrics'}")


def test(args):
    """测试函数"""
    print("=" * 60)
    print("Drone Formation Control RL - Testing Mode")
    print("=" * 60)

    if not args.checkpoint:
        print("✗ Error: --checkpoint is required for testing mode")
        return

    try:
        env = FormationControlEnv(
            num_drones=args.num_drones,
            render_mode='human' if args.render else None
        )
    except Exception as e:
        print(f"\n✗ Failed to create environment: {e}")
        return

    state_dim = env.observation_space.shape[0]
    action_dim = env.action_space.shape[0]

    if args.algorithm == 'DQN':
        agent = DQNAgent(
            state_dim=state_dim,
            action_dim=action_dim,
            device=args.device
        )
    else:
        agent = PPOAgent(
            state_dim=state_dim,
            action_dim=action_dim,
            device=args.device
        )

    agent.load(args.checkpoint)
    print(f"✓ Loaded checkpoint from: {args.checkpoint}")

    test_episodes = 10
    test_rewards = []

    print(f"\n运行 {test_episodes} 个测试回合...")

    for episode in range(test_episodes):
        obs, info = env.reset()
        episode_reward = 0

        for step in range(args.max_steps):
            state = obs

            if args.algorithm == 'DQN':
                action = agent.select_action(state, training=False)
            else:
                action, _ = agent.select_action(state)

            next_obs, reward, terminated, truncated, info = env.step(action)

            episode_reward += reward
            obs = next_obs

            if terminated or truncated:
                break

        test_rewards.append(episode_reward)
        print(f"Episode {episode + 1}: Reward = {episode_reward:.2f}")

    env.close()

    print("\n" + "=" * 60)
    print("测试结果")
    print("=" * 60)
    print(f"平均奖励: {np.mean(test_rewards):.2f} ± {np.std(test_rewards):.2f}")
    print(f"最高奖励: {max(test_rewards):.2f}")
    print(f"最低奖励: {min(test_rewards):.2f}")


def demo(args):
    """演示函数"""
    print("=" * 60)
    print("Drone Formation Control RL - Demo Mode")
    print("=" * 60)
    print("此模式需要一个训练好的模型检查点")
    print("使用 --checkpoint 参数指定模型路径")
    print("使用 --render 参数启用可视化")
    print("=" * 60)


def main():
    """主函数"""
    args = parse_args()

    if args.mode == 'train':
        train(args)
    elif args.mode == 'test':
        test(args)
    elif args.mode == 'demo':
        demo(args)


if __name__ == "__main__":
    main()