"""
Agent Lightning 强化学习模型训练脚本
使用优化的DQN和PPO算法训练多智能体无人机编队控制模型
基于 gym-pybullet-drones 专业物理仿真器
"""

import sys
import os
from pathlib import Path

sys.path.append(str(Path(__file__).parent.parent.parent))

import torch
import numpy as np
import yaml
import json
from typing import Dict, Any
from tqdm import tqdm
import logging

from src.algorithms.optimized_dqn import OptimizedDQNAgent
from src.algorithms.optimized_ppo import OptimizedPPOAgent
from src.agent_lightning_integration import AgentLightningWrapper, RewardOptimizer
from src.utils import MetricsTracker, plot_training_curve, save_results
from src.environments import FormationControlEnv, make_formation_control_env

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def load_config(config_path: str) -> Dict[str, Any]:
    """加载配置文件"""
    with open(config_path, 'r', encoding='utf-8') as f:
        return yaml.safe_load(f)


def set_seed(seed: int):
    """设置随机种子"""
    np.random.seed(seed)
    torch.manual_seed(seed)
    if torch.cuda.is_available():
        torch.cuda.manual_seed(seed)


def create_agent(
    algorithm: str,
    state_dim: int,
    action_dim: int,
    config: Dict[str, Any],
    device: str
):
    """创建优化后的智能体"""
    logger.info(f"创建 {algorithm} 智能体...")

    algo_params = config.get('training', {}).get('hyperparameters', {})

    if algorithm.upper() == 'DQN':
        params = algo_params.get('dqn', {})
        agent = OptimizedDQNAgent(
            state_dim=state_dim,
            action_dim=action_dim,
            learning_rate=params.get('learning_rate', 2.5e-4),
            gamma=params.get('gamma', 0.99),
            epsilon_start=params.get('epsilon_start', 1.0),
            epsilon_decay=params.get('epsilon_decay', 0.995),
            epsilon_min=params.get('epsilon_min', 0.01),
            buffer_size=params.get('buffer_size', 10000),
            batch_size=params.get('batch_size', 128),
            target_update_freq=params.get('target_update_freq', 100),
            device=device,
            hidden_sizes=params.get('network_architecture', [256, 256, 128]),
            use_layer_norm=params.get('use_layer_norm', True),
            use_prioritized_replay=params.get('use_prioritized_replay', True),
            double_dqn=params.get('double_dqn', True)
        )

    elif algorithm.upper() == 'PPO':
        params = algo_params.get('ppo', {})
        agent = OptimizedPPOAgent(
            state_dim=state_dim,
            action_dim=action_dim,
            learning_rate=params.get('learning_rate', 2.5e-4),
            gamma=params.get('gamma', 0.99),
            gae_lambda=params.get('gae_lambda', 0.95),
            clip_epsilon=params.get('clip_epsilon', 0.15),
            entropy_coef=params.get('entropy_coef', 0.005),
            value_coef=params.get('value_coef', 0.5),
            epochs=params.get('epochs', 10),
            batch_size=params.get('batch_size', 128),
            n_steps=params.get('n_steps', 100),
            max_grad_norm=params.get('max_grad_norm', 0.5),
            device=device,
            use_gae=params.get('use_gae', True),
            use_clipped_value_loss=params.get('use_clipped_value_loss', True),
            use_entropy_decay=params.get('use_entropy_decay', True)
        )

    else:
        raise ValueError(f"不支持的算法: {algorithm}")

    return agent


def check_convergence(rewards: list, window: int = 20, threshold: float = 0.05) -> bool:
    """检查是否收敛"""
    if len(rewards) < window:
        return False

    recent_rewards = rewards[-window:]
    mean_reward = np.mean(recent_rewards)
    std_reward = np.std(recent_rewards)

    if std_reward < threshold * abs(mean_reward):
        return True

    return False


def train_agent(
    algorithm: str,
    config_path: str = "configs/train_config.yaml",
    env_config_path: str = "configs/env_config.yaml",
    episodes: int = 500,
    device: str = 'cuda',
    convergence_check: bool = True,
    convergence_window: int = 50,
    convergence_threshold: float = 0.1,
    checkpoint_path: str = None
):
    """训练多智能体无人机编队控制模型直到收敛"""

    logger.info("=" * 70)
    logger.info(f"开始训练 - 算法: {algorithm}")
    logger.info("=" * 70)

    set_seed(42)

    env = make_formation_control_env(env_config_path)
    logger.info("使用 gym-pybullet-drones 专业物理仿真器")
    
    if len(env.observation_space.shape) == 2:
        state_dim = env.observation_space.shape[0] * env.observation_space.shape[1]
    else:
        state_dim = env.observation_space.shape[0] * env.num_drones
    
    if len(env.action_space.shape) == 2:
        action_dim = env.action_space.shape[0] * env.action_space.shape[1]
    else:
        action_dim = env.action_space.shape[0] * env.num_drones
    
    logger.info(f"环境初始化完成")
    logger.info(f"无人机数量: {env.num_drones}")
    logger.info(f"状态维度: {state_dim}")
    logger.info(f"动作维度: {action_dim}")
    logger.info(f"目标距离: {env.target_distance}米")
    logger.info(f"最大速度: {env.max_speed} m/s")

    try:
        config = load_config(config_path)
        logger.info(f"已加载配置: {config_path}")
    except Exception as e:
        logger.warning(f"无法加载配置文件: {e}，使用默认配置")
        config = {'training': {'hyperparameters': {}}}

    agent = create_agent(algorithm, state_dim, action_dim, config, device)

    start_episode = 0
    if checkpoint_path:
        import os
        if os.path.exists(checkpoint_path):
            logger.info(f"从检查点加载模型: {checkpoint_path}")
            agent.load(checkpoint_path)
            filename = os.path.basename(checkpoint_path)
            try:
                start_episode = int(filename.split('ep')[1].split('.')[0])
                logger.info(f"从第 {start_episode} 回合继续训练")
            except:
                logger.warning("无法解析检查点回合数，从0开始")
        else:
            logger.warning(f"检查点文件不存在: {checkpoint_path}")

    wrapper = AgentLightningWrapper(
        agent,
        agent_type=algorithm.lower(),
        device=device,
        enable_tracing=True
    )

    tracker = MetricsTracker()
    episode_rewards = []
    episode_losses = []
    episode_mean_velocities = []
    episode_distances = []
    best_reward = float('-inf')
    convergence_count = 0
    max_convergence_checks = 5

    if checkpoint_path:
        results_dir = Path("outputs/results") / f"{algorithm.lower()}_results"
        if results_dir.exists() and (results_dir / "results.json").exists():
            try:
                with open(results_dir / "results.json", 'r') as f:
                    existing_results = json.load(f)
                if 'rewards' in existing_results and isinstance(existing_results['rewards'], list):
                    episode_rewards = existing_results['rewards']
                    logger.info(f"已加载历史奖励数据: {len(episode_rewards)} 条")
                if 'best_reward' in existing_results:
                    best_reward = existing_results['best_reward']
                    logger.info(f"已加载历史最佳奖励: {best_reward:.2f}")
            except Exception as e:
                logger.warning(f"加载历史数据失败: {e}")

    logger.info(f"开始训练 {episodes} 回合 (或直到收敛)...")

    for episode in tqdm(range(start_episode, episodes), desc=f"{algorithm} Training"):
        episode_reward = 0
        episode_loss = 0
        update_count = 0

        wrapper.before_episode(episode)

        state, _ = env.reset()

        done = False
        step = 0
        episode_info = []
        while not done:
            if algorithm.upper() == 'DQN':
                action = agent.select_action(state, training=True)

                next_state, reward, terminated, truncated, info = env.step(action)

                done = terminated or truncated

                agent.store_transition(state, action, reward, next_state, done)
                loss = agent.update()

                episode_reward += reward
                if loss > 0:
                    episode_loss += loss
                    update_count += 1

                wrapper.on_step(step, state, action, reward, next_state, done)

                state = next_state

            elif algorithm.upper() == 'PPO':
                flattened_state = state.flatten()
                action, log_prob = agent.select_action(flattened_state)

                action = action.reshape(env.num_drones, 4)
                next_state, reward, terminated, truncated, info = env.step(action)

                done = terminated or truncated

                with torch.no_grad():
                    state_tensor = torch.FloatTensor(flattened_state).unsqueeze(0).to(device)
                    value = agent.value(state_tensor).item()

                agent.store_transition(flattened_state, action, reward, log_prob, done, value)

                episode_reward += reward
                episode_info.append(info)
                state = next_state

            step += 1

        if algorithm.upper() == 'PPO':
            metrics = agent.update()
            episode_loss = metrics.get('total_loss', 0)

        episode_rewards.append(episode_reward)
        episode_losses.append(episode_loss if episode_loss > 0 else 0)
        
        if episode_info:
            episode_mean_velocities.append(np.mean([info.get('mean_velocity', 0) for info in episode_info]))

        if episode_reward > best_reward:
            best_reward = episode_reward

        wrapper.after_episode(
            episode,
            episode_reward,
            episode_loss,
            {
                'best_reward': best_reward,
                'convergence_check': convergence_count
            }
        )

        if episode % 10 == 0:
            recent_mean = np.mean(episode_rewards[-10:])
            mean_vel = np.mean(episode_mean_velocities[-10:]) if episode_mean_velocities else 0
            logger.info(
                f"Episode {episode}/{episodes} | "
                f"Reward: {episode_reward:.2f} | "
                f"Avg Reward: {recent_mean:.2f} | "
                f"Best: {best_reward:.2f} | "
                f"Mean Velocity: {mean_vel:.2f} m/s"
            )

        if convergence_check and episode >= convergence_window:
            if check_convergence(episode_rewards, window=convergence_window, threshold=convergence_threshold):
                convergence_count += 1
                logger.info(f"检测到收敛迹象 ({convergence_count}/{max_convergence_checks})")

                if convergence_count >= max_convergence_checks:
                    logger.info("模型已收敛！停止训练。")
                    break
            else:
                convergence_count = 0

        if episode % 50 == 0 and episode > 0:
            checkpoint_path = Path("outputs/checkpoints")
            checkpoint_path.mkdir(parents=True, exist_ok=True)
            agent.save(str(checkpoint_path / f"{algorithm.lower()}_formation_ep{episode}.pt"))
            logger.info(f"检查点已保存")

    env.close()

    logger.info("\n" + "=" * 70)
    logger.info("训练完成!")
    logger.info("=" * 70)

    results_dir = Path("outputs/results")
    results_dir.mkdir(parents=True, exist_ok=True)

    plot_path = results_dir / f"{algorithm.lower()}_formation_training_results.png"
    plot_training_curve(episode_rewards, episode_losses, save_path=str(plot_path))

    results = {
        'algorithm': algorithm,
        'total_episodes': len(episode_rewards),
        'final_reward': float(np.mean(episode_rewards[-10:])),
        'best_reward': float(best_reward),
        'mean_reward': float(np.mean(episode_rewards)),
        'mean_velocity': float(np.mean(episode_mean_velocities)) if episode_mean_velocities else 0,
        'rewards': episode_rewards,
        'losses': episode_losses,
        'mean_velocities': episode_mean_velocities,
        'converged': convergence_count >= max_convergence_checks,
        'num_drones': env.num_drones,
        'target_distance': env.target_distance,
        'max_speed': env.max_speed
    }

    save_results(results, str(results_dir / f"{algorithm.lower()}_formation_results"))

    logger.info(f"\n最终结果:")
    logger.info(f"  - 训练回合: {len(episode_rewards)}")
    logger.info(f"  - 最佳奖励: {results['best_reward']:.2f}")
    logger.info(f"  - 平均奖励: {results['mean_reward']:.2f}")
    logger.info(f"  - 最终奖励: {results['final_reward']:.2f}")
    logger.info(f"  - 平均速度: {results['mean_velocity']:.2f} m/s")
    logger.info(f"  - 已收敛: {results['converged']}")
    logger.info(f"\n结果已保存到: {results_dir}")

    return results


def main():
    """主函数"""
    import argparse

    parser = argparse.ArgumentParser(description='Agent Lightning 多智能体无人机编队控制训练')
    parser.add_argument('--algorithm', type=str, default='PPO',
                        choices=['DQN', 'PPO'], help='训练算法')
    parser.add_argument('--config', type=str,
                        default='configs/train_config.yaml',
                        help='训练配置文件路径')
    parser.add_argument('--env_config', type=str,
                        default='configs/env_config.yaml',
                        help='环境配置文件路径')
    parser.add_argument('--episodes', type=int, default=500,
                        help='最大训练回合数')
    parser.add_argument('--device', type=str, default='cuda',
                        help='训练设备')
    parser.add_argument('--no_convergence_check', action='store_true',
                        help='禁用收敛检查')
    parser.add_argument('--checkpoint', type=str, default=None,
                        help='从检查点继续训练')

    args = parser.parse_args()

    results = train_agent(
        algorithm=args.algorithm,
        config_path=args.config,
        env_config_path=args.env_config,
        episodes=args.episodes,
        device=args.device,
        convergence_check=not args.no_convergence_check,
        checkpoint_path=args.checkpoint
    )

    return results


if __name__ == "__main__":
    main()