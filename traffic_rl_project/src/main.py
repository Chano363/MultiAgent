"""
无人机编队控制强化学习系统
主入口文件 - 默认使用 Agent Lightning 优化训练框架
基于 gym-pybullet-drones 专业物理仿真器
"""

import os
import sys
import argparse
from pathlib import Path
import logging
import time

sys.path.append(str(Path(__file__).parent.parent))
from src.utils.quiet_print import suppress_prints

# 在导入训练模块之前静默非错误打印，避免大量噪声输出
suppress_prints()

from src.scripts.agent_lightning_train import train_agent


# 配置日志（唯一配置点）
logger = logging.getLogger('DroneRL')
if not logger.handlers:  # 避免重复添加 handler
    logger.setLevel(logging.INFO)
    console_handler = logging.StreamHandler()
    console_handler.setFormatter(logging.Formatter('[%(levelname)s] %(message)s'))
    logger.addHandler(console_handler)
    logger.propagate = False  # 防止传播到根 logger


def parse_args():
    """解析命令行参数"""
    parser = argparse.ArgumentParser(
        description='Drone Formation Control RL - Agent Lightning Training'
    )

    parser.add_argument(
        '--mode',
        type=str,
        default='train',
        choices=['train', 'test', 'continue'],
        help='运行模式: train (新建训练), continue (断点续训), test (测试)'
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
        default=500,
        help='训练回合数（或直到收敛）'
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
        default='cuda' if torch.cuda.is_available() else 'cpu',
        help='计算设备'
    )

    parser.add_argument(
        '--checkpoint',
        type=str,
        default=None,
        help='检查点路径（用于断点续训或测试）'
    )

    parser.add_argument(
        '--config',
        type=str,
        default='configs/train_config.yaml',
        help='训练配置文件路径'
    )

    parser.add_argument(
        '--env_config',
        type=str,
        default='configs/env_config.yaml',
        help='环境配置文件路径'
    )

    parser.add_argument(
        '--no_convergence',
        action='store_true',
        default=False,
        help='禁用自动收敛检测，训练固定回合数'
    )

    parser.add_argument(
        '--render',
        action='store_true',
        default=False,
        help='启用可视化渲染（训练时建议关闭以提高性能）'
    )

    return parser.parse_args()


def main():
    """主函数 - 默认使用 Agent Lightning 训练"""
    args = parse_args()
    
    # 配置日志级别
    level_name = os.getenv('TRAFFIC_RL_LOG_LEVEL', 'INFO').upper()
    level = getattr(logging, level_name, logging.INFO)
    logger.setLevel(level)
    for handler in logger.handlers:
        handler.setLevel(level)

    # 降低常见噪声库的输出
    noisy_libs = ('matplotlib', 'urllib3', 'pybullet', 'gym', 'gym_pybullet_drones', 'torch', 'asyncio')
    for lib in noisy_libs:
        logging.getLogger(lib).setLevel(logging.WARNING)

    logger.info("=" * 80)
    logger.info("无人机编队控制强化学习系统")
    logger.info("=" * 80)
    logger.info(f"启动时间: {time.strftime('%Y-%m-%d %H:%M:%S')}")
    logger.info(f"运行模式: {args.mode}")
    logger.info(f"算法: {args.algorithm}")
    logger.info(f"回合数: {args.episodes}")
    logger.info(f"无人机数量: {args.num_drones}")
    logger.info(f"设备: {args.device}")
    logger.info(f"收敛检测: {'禁用' if args.no_convergence else '启用'}")
    logger.info(f"可视化: {'启用' if args.render else '禁用'}")
    logger.info("=" * 80)

    if args.mode == 'train':
        logger.info("\n开始新训练")
        results = train_agent(
            algorithm=args.algorithm,
            config_path=args.config,
            env_config_path=args.env_config,
            episodes=args.episodes,
            device=args.device,
            convergence_check=not args.no_convergence,
            checkpoint_path=None
        )

    elif args.mode == 'continue':
        if not args.checkpoint:
            logger.error("断点续训需要指定 --checkpoint 参数")
            logger.info("示例: python src/main.py --mode continue --checkpoint outputs/checkpoints/ppo_formation_ep100.pt")
            return
        logger.info(f"\n从检查点继续训练: {args.checkpoint}")
        results = train_agent(
            algorithm=args.algorithm,
            config_path=args.config,
            env_config_path=args.env_config,
            episodes=args.episodes,
            device=args.device,
            convergence_check=not args.no_convergence,
            checkpoint_path=args.checkpoint
        )

    elif args.mode == 'test':
        if not args.checkpoint:
            logger.error("测试模式需要指定 --checkpoint 参数")
            logger.info("示例: python src/main.py --mode test --checkpoint outputs/checkpoints/ppo_formation_best.pt")
            return

        logger.info(f"\n测试模型: {args.checkpoint}")
        test_model(args)

    else:
        logger.error(f"不支持的模式: {args.mode}")


def test_model(args):
    """测试训练好的模型"""
    from src.environments import FormationControlEnv
    from src.algorithms import PPOAgent, DQNAgent

    try:
        env = FormationControlEnv(
            num_drones=args.num_drones,
            render_mode='human' if args.render else None
        )
    except Exception as e:
        logger.error(f"创建环境失败: {e}")
        return

    state_dim = env.observation_space.shape[0] * env.num_drones
    action_dim = env.action_space.shape[0] * env.num_drones

    if args.algorithm == 'DQN':
        agent = DQNAgent(state_dim=state_dim, action_dim=action_dim, device=args.device)
    else:
        agent = PPOAgent(state_dim=state_dim, action_dim=action_dim, device=args.device)

    agent.load(args.checkpoint)
    logger.info(f"加载检查点成功: {args.checkpoint}")

    test_episodes = 10
    test_rewards = []
    episode_distances = []

    logger.info(f"\n运行 {test_episodes} 个测试回合...")
    logger.info("=" * 80)

    for episode in range(test_episodes):
        obs, info = env.reset()
        episode_reward = 0
        done = False
        step = 0

        while not done:
            if args.algorithm == 'DQN':
                action = agent.select_action(obs.flatten(), training=False)
            else:
                action, _ = agent.select_action(obs.flatten())

            action = action.reshape(args.num_drones, 4)
            next_obs, reward, terminated, truncated, info = env.step(action)

            episode_reward += reward
            obs = next_obs
            done = terminated or truncated
            step += 1

        test_rewards.append(episode_reward)
        logger.info(f"   Episode {episode + 1}/{test_episodes}: Reward = {episode_reward:+.2f}")

    env.close()

    avg_reward = np.mean(test_rewards)
    std_reward = np.std(test_rewards)
    max_reward = max(test_rewards)
    min_reward = min(test_rewards)
    
    logger.info("=" * 80)
    logger.info("测试结果汇总")
    logger.info("=" * 80)
    logger.info(f"   - 平均奖励: {avg_reward:.2f} ± {std_reward:.2f}")
    logger.info(f"   - 最高奖励: {max_reward:.2f}")
    logger.info(f"   - 最低奖励: {min_reward:.2f}")
    logger.info("=" * 80)


if __name__ == "__main__":
    import torch
    import numpy as np
    main()