"""
Agent Lightning 强化学习模型训练循环
基于 gym-pybullet-drones 专业物理仿真器
"""

import sys
import os
from pathlib import Path
import time

sys.path.append(str(Path(__file__).parent.parent.parent))

import torch
import torch.nn as nn
import numpy as np
import yaml
import json
from typing import Dict, List, Any, Optional
from tqdm import tqdm
import logging

logging.basicConfig(
    level=logging.INFO,
    format='%(message)s',
    handlers=[
        logging.StreamHandler(sys.stderr)
    ]
)

logging.getLogger('agentlightning').setLevel(logging.WARNING)
logging.getLogger('agentlightning.runner').setLevel(logging.ERROR)
logging.getLogger('agentlightning.trainer').setLevel(logging.ERROR)
logging.getLogger('agentlightning.execution').setLevel(logging.ERROR)
logging.getLogger('urllib3').setLevel(logging.WARNING)
logging.getLogger('opentelemetry').setLevel(logging.WARNING)

sys.stderr = os.fdopen(sys.stderr.fileno(), 'w', buffering=1)

from src.algorithms.optimized_dqn import OptimizedDQNAgent
from src.algorithms.optimized_ppo import OptimizedPPOAgent
from src.algorithms.mappo_agent import MAPPOAgent
from src.algorithms.sac_agent import SACAgent
from src.utils import MetricsTracker, plot_training_curve, save_results
from src.environments import FormationControlEnv, make_formation_control_env

logger = logging.getLogger('DroneRL')


try:
    import agentlightning as agl
    AGENT_LIGHTNING_AVAILABLE = True
except ImportError:
    AGENT_LIGHTNING_AVAILABLE = False
    agl = None


class AgentLightningWrapper:
    """Agent Lightning 集成包装器"""

    def __init__(
        self,
        agent,
        agent_type: str = "dqn",
        device: str = "cuda" if torch.cuda.is_available() else "cpu",
        enable_tracing: bool = True
    ):
        self.agent = agent
        self.agent_type = agent_type
        self.device = device
        self.enable_tracing = enable_tracing and AGENT_LIGHTNING_AVAILABLE
        self.agent_lightning = agl if self.enable_tracing else None

        if self.enable_tracing:
            self._setup_agent_lightning()
        elif enable_tracing and not AGENT_LIGHTNING_AVAILABLE:
            logger.info("Agent Lightning 未安装，跳过可选 tracing")

        self.episode_count = 0
        self.metrics_history = []

    def _setup_agent_lightning(self):
        """初始化 Agent Lightning"""
        logger.info("初始化 Agent Lightning 集成")

    def before_episode(self, episode_id: int):
        """episode开始前的回调"""
        if self.enable_tracing:
            self.episode_count = episode_id
            return {"episode_id": episode_id, "agent_type": self.agent_type}

    def after_episode(
        self,
        episode_id: int,
        episode_reward: float,
        episode_loss: float,
        metrics: Optional[Dict[str, float]] = None
    ):
        """episode结束后的回调"""
        episode_metrics = {
            "episode": episode_id,
            "reward": episode_reward,
            "loss": episode_loss,
            "agent_type": self.agent_type
        }

        if metrics:
            episode_metrics.update(metrics)

        self.metrics_history.append(episode_metrics)

        if self.enable_tracing and AGENT_LIGHTNING_AVAILABLE:
            try:
                if hasattr(self.agent_lightning, "log"):
                    self.agent_lightning.log("episode_reward", episode_reward)
                    self.agent_lightning.log("episode_loss", episode_loss)
            except:
                pass

            if metrics:
                for key, value in metrics.items():
                    try:
                        if hasattr(self.agent_lightning, "log"):
                            self.agent_lightning.log(key, value)
                    except:
                        pass

    def on_step(
        self,
        step: int,
        state: np.ndarray,
        action: int,
        reward: float,
        next_state: np.ndarray,
        done: bool
    ):
        """每个训练步骤的回调"""
        if self.enable_tracing and hasattr(self.agent, 'epsilon'):
            epsilon = getattr(self.agent, 'epsilon', 1.0)
            try:
                if hasattr(self.agent_lightning, "log"):
                    self.agent_lightning.log("exploration_rate", epsilon)
            except:
                pass

    def get_best_metrics(self) -> Dict[str, float]:
        """获取最佳指标"""
        if not self.metrics_history:
            return {}

        best_reward = max(m["reward"] for m in self.metrics_history)
        avg_reward = np.mean([m["reward"] for m in self.metrics_history[-10:]])

        return {
            "best_reward": best_reward,
            "avg_reward_10": avg_reward,
            "total_episodes": len(self.metrics_history)
        }

    def save_checkpoint(self, path: str):
        """保存检查点"""
        checkpoint = {
            "agent_state": self.agent.state_dict() if hasattr(self.agent, 'state_dict') else None,
            "agent_type": self.agent_type,
            "metrics_history": self.metrics_history,
            "episode_count": self.episode_count
        }
        torch.save(checkpoint, path)

    def load_checkpoint(self, path: str):
        """加载检查点"""
        checkpoint = torch.load(path)
        if hasattr(self.agent, 'load_state_dict') and checkpoint["agent_state"]:
            self.agent.load_state_dict(checkpoint["agent_state"])
        self.metrics_history = checkpoint.get("metrics_history", [])
        self.episode_count = checkpoint.get("episode_count", 0)


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
    device: str,
    num_drones: int = None,
    obs_per_drone: int = None,
    act_per_drone: int = None
):
    """创建智能体"""
    logger.info(f"创建 {algorithm} 智能体...")

    algo_params = config.get('training', {}).get('hyperparameters', {})
    if not isinstance(algo_params, dict):
        algo_params = {}

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

    elif algorithm.upper() == 'SAC':
        params = algo_params.get('sac', {})
        agent = SACAgent(
            state_dim=state_dim,
            action_dim=action_dim,
            learning_rate=params.get('learning_rate', 3e-4),
            gamma=params.get('gamma', 0.99),
            tau=params.get('tau', 0.005),
            alpha=params.get('alpha', 0.2),
            automatic_entropy_tuning=params.get('automatic_entropy_tuning', True),
            buffer_capacity=params.get('buffer_capacity', 1000000),
            batch_size=params.get('batch_size', 256),
            device=device
        )

    elif algorithm.upper() == 'MAPPO':
        params = algo_params.get('mappo', {})
        agent = MAPPOAgent(
            num_drones=num_drones or 3,
            obs_per_drone=obs_per_drone or 72,
            act_per_drone=act_per_drone or 4,
            learning_rate=params.get('learning_rate', 5e-5),
            gamma=params.get('gamma', 0.99),
            gae_lambda=params.get('gae_lambda', 0.95),
            clip_epsilon=params.get('clip_epsilon', 0.2),
            entropy_coef=params.get('entropy_coef', 0.005),
            value_coef=params.get('value_coef', 0.5),
            epochs=params.get('epochs', 4),
            batch_size=params.get('batch_size', 64),
            max_grad_norm=params.get('max_grad_norm', 0.5),
            device=device,
            use_gae=params.get('use_gae', True),
            use_clipped_value_loss=params.get('use_clipped_value_loss', True),
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
    """训练多智能体无人机编队控制模型"""
    
    start_time = time.time()

    logger.info(f"\n{'='*60}")
    logger.info(f"无人机编队控制训练 | {algorithm.upper()} | {device.upper()}")
    logger.info(f"{'='*60}\n")

    set_seed(42)

    if AGENT_LIGHTNING_AVAILABLE:
        from src.agent_lightning_integration import train_with_agent_lightning
        return train_with_agent_lightning(
            algorithm=algorithm,
            config_path=config_path,
            env_config_path=env_config_path,
            episodes=episodes,
            device=device,
            checkpoint_path=checkpoint_path,
            convergence_window=convergence_window,
            convergence_threshold=convergence_threshold,
        )
    else:
        logger.info("Agent Lightning 未安装，使用传统训练模式")

    logger.info("\n正在初始化仿真环境...")
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
    
    logger.info("\n环境配置:")
    logger.info(f"   - 无人机数量: {env.num_drones}")
    logger.info(f"   - 状态维度: {state_dim}")
    logger.info(f"   - 动作维度: {action_dim}")
    logger.info(f"   - 目标距离: {env.target_distance} m")
    logger.info(f"   - 最大速度: {env.max_speed} m/s")
    logger.info(f"   - 最大步数: {env.max_steps}")
    
    try:
        config = load_config(config_path)
        logger.info(f"已加载配置文件: {config_path}")
    except Exception as e:
        logger.warning(f"无法加载配置文件: {e}，使用默认配置")
        config = {'training': {'hyperparameters': {}}}

    obs_per_drone = env.observation_space.shape[1] if len(env.observation_space.shape) == 2 else env.observation_space.shape[0]
    act_per_drone = env.action_space.shape[1] if len(env.action_space.shape) == 2 else 4

    agent = create_agent(
        algorithm, state_dim, action_dim, config, device,
        num_drones=env.num_drones,
        obs_per_drone=obs_per_drone,
        act_per_drone=act_per_drone
    )
    logger.info(f"{algorithm.upper()} 智能体创建成功")

    start_episode = 0
    if checkpoint_path:
        import os
        if os.path.exists(checkpoint_path):
            logger.info(f"\n从检查点加载模型: {checkpoint_path}")
            agent.load(checkpoint_path)
            filename = os.path.basename(checkpoint_path)
            try:
                start_episode = int(filename.split('ep')[1].split('.')[0])
                logger.info(f"从第 {start_episode} 回合继续训练")
            except:
                logger.warning("无法解析检查点回合数，从 0 开始")
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
    episode_formation_errors = []
    episode_height_errors = []
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
                    logger.info(f"历史最佳奖励: {best_reward:.2f}")
            except Exception as e:
                logger.warning(f"加载历史数据失败: {e}")

    logger.info("\n" + "=" * 80)
    logger.info("开始训练")
    logger.info("=" * 80)
    
    episode_start_time = time.time()
    training_aborted = False
    abort_reason = ""

    try:
        for episode in tqdm(range(start_episode, episodes), desc=f"{algorithm.upper()} Training", ncols=100):
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

                    if len(env.action_space.shape) == 2:
                        action = action.reshape(env.num_drones, env.action_space.shape[1])

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
                    step += 1

                elif algorithm.upper() == 'PPO':
                    flattened_state = state.flatten()
                    action, log_prob = agent.select_action(flattened_state)

                    original_action = action.copy()

                    if len(env.action_space.shape) == 2:
                        action = action.reshape(env.num_drones, env.action_space.shape[1])
                    else:
                        action = action.reshape(env.num_drones, 4)

                    next_state, reward, terminated, truncated, info = env.step(action)

                    done = terminated or truncated

                    with torch.no_grad():
                        state_tensor = torch.FloatTensor(flattened_state).unsqueeze(0).to(device)
                        value = agent.value(state_tensor).item()

                    agent.store_transition(flattened_state, original_action, reward, log_prob, done, value)

                    episode_reward += reward
                    episode_info.append(info)
                    state = next_state
                    step += 1

                elif algorithm.upper() == 'MAPPO':
                    flattened_state = state.flatten()
                    actions, total_log_prob = agent.select_actions(flattened_state)

                    if len(env.action_space.shape) == 2:
                        action_for_env = actions.reshape(env.num_drones, env.action_space.shape[1])
                    else:
                        action_for_env = actions.reshape(env.num_drones, 4)

                    next_state, reward, terminated, truncated, info = env.step(action_for_env)

                    done = terminated or truncated

                    value = agent.get_value(flattened_state)

                    agent.store_transition(flattened_state, actions, reward, total_log_prob, done, value)

                    episode_reward += reward
                    episode_info.append(info)
                    state = next_state
                    step += 1

                elif algorithm.upper() == 'SAC':
                    flattened_state = state.flatten()
                    action = agent.select_action(flattened_state)

                    if len(env.action_space.shape) == 2:
                        action_for_env = action.reshape(env.num_drones, env.action_space.shape[1])
                    else:
                        action_for_env = action.reshape(env.num_drones, 4)

                    next_state, reward, terminated, truncated, info = env.step(action_for_env)

                    done = terminated or truncated

                    agent.store_transition(flattened_state, action, reward, next_state.flatten(), done)

                    metrics = agent.update()
                    episode_loss += metrics.get('total_loss', 0)
                    update_count += 1

                    episode_reward += reward
                    episode_info.append(info)
                    state = next_state
                    step += 1

            if algorithm.upper() == 'PPO':
                metrics = agent.update()
                episode_loss = metrics.get('total_loss', 0)

            elif algorithm.upper() == 'MAPPO':
                metrics = agent.update()
                episode_loss = metrics.get('total_loss', 0)

            elif algorithm.upper() == 'SAC':
                if update_count > 0:
                    episode_loss = episode_loss / update_count

            episode_rewards.append(episode_reward)
            episode_losses.append(episode_loss if episode_loss > 0 else 0)

            mean_vel = np.mean(np.linalg.norm(state[:, 6:9], axis=1)) if state.ndim > 1 else 0
            episode_mean_velocities.append(mean_vel)

            if episode_info:
                formation_errors = [info.get('formation_error', 0) for info in episode_info if info]
                height_errors = [info.get('height_error', 0) for info in episode_info if info]
                mean_formation_error = np.mean(formation_errors) if formation_errors else 0
                mean_height_error = np.mean(height_errors) if height_errors else 0
            else:
                mean_formation_error = 0
                mean_height_error = 0
            episode_formation_errors.append(mean_formation_error)
            episode_height_errors.append(mean_height_error)

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

            if episode % 10 == 0 or episode == episodes - 1:
                elapsed_time = time.time() - episode_start_time
                episodes_completed = episode - start_episode + 1
                avg_time_per_episode = elapsed_time / episodes_completed if episodes_completed > 0 else 0
                remaining_episodes = episodes - episode - 1
                estimated_remaining_time = avg_time_per_episode * remaining_episodes
                
                recent_mean = np.mean(episode_rewards[-10:]) if len(episode_rewards) >= 10 else np.mean(episode_rewards)
                recent_std = np.std(episode_rewards[-10:]) if len(episode_rewards) >= 10 else 0
                mean_vel_recent = np.mean(episode_mean_velocities[-10:]) if len(episode_mean_velocities) >= 10 else mean_vel
                mean_formation_recent = np.mean(episode_formation_errors[-10:]) if len(episode_formation_errors) >= 10 else mean_formation_error
                mean_height_recent = np.mean(episode_height_errors[-10:]) if len(episode_height_errors) >= 10 else mean_height_error

                logger.info(f"\n{'─' * 80}")
                logger.info(f"Episode {episode}/{episodes} | 用时: {elapsed_time:.1f}s | 预计剩余: {estimated_remaining_time:.0f}s")
                logger.info(f"   - 当前奖励: {episode_reward:+.2f}")
                logger.info(f"   - 近10回合平均: {recent_mean:.2f} ± {recent_std:.2f}")
                logger.info(f"   - 历史最佳: {best_reward:.2f}")
                logger.info(f"   - 损失值: {episode_loss:.4f}")
                logger.info(f"   - 平均速度: {mean_vel_recent:.2f} m/s | 编队误差: {mean_formation_recent:.3f} m | 高度误差: {mean_height_recent:.3f} m")
                
                if convergence_check and episode >= convergence_window:
                    if check_convergence(episode_rewards, window=convergence_window, threshold=convergence_threshold):
                        logger.info(f"   - 收敛检测: 是 ({convergence_count + 1}/{max_convergence_checks})")
                    else:
                        logger.info(f"   - 收敛检测: 否")
                
                logger.info(f"{'─' * 80}\n")

            if convergence_check and episode >= convergence_window:
                if check_convergence(episode_rewards, window=convergence_window, threshold=convergence_threshold):
                    convergence_count += 1
                    logger.info(f"检测到收敛迹象 ({convergence_count}/{max_convergence_checks})")

                    if convergence_count >= max_convergence_checks:
                        total_time = time.time() - start_time
                        logger.info("\n" + "=" * 80)
                        logger.info("模型已收敛！停止训练")
                        logger.info(f"总训练时间: {total_time:.1f}s ({total_time/60:.1f} min)")
                        logger.info("=" * 80)
                        break
                else:
                    convergence_count = 0

            if episode % 10 == 0 and episode > 0:
                checkpoint_dir = Path("outputs/checkpoints")
                checkpoint_dir.mkdir(parents=True, exist_ok=True)
                checkpoint_file = checkpoint_dir / f"{algorithm.lower()}_formation_ep{episode}.pt"
                agent.save(str(checkpoint_file))

    except ValueError as e:
        training_aborted = True
        abort_reason = str(e)
        logger.error("\n" + "=" * 80)
        logger.error(f"训练因严重错误中止: {abort_reason}")
        logger.error("=" * 80)
        raise
    except Exception as e:
        training_aborted = True
        abort_reason = str(e)
        logger.error("\n" + "=" * 80)
        logger.error(f"训练因未预期错误中止: {type(e).__name__}: {abort_reason}")
        logger.error("=" * 80)
        raise
    finally:
        env.close()

    total_time = time.time() - start_time
    
    logger.info("\n" + "=" * 80)
    if training_aborted:
        logger.info("训练已中止!")
        logger.info(f"中止原因: {abort_reason}")
    else:
        logger.info("训练完成!")
    logger.info("=" * 80)
    logger.info(f"总训练时间: {total_time:.1f}s ({total_time/60:.1f} min)")
    logger.info(f"总回合数: {len(episode_rewards)}")
    logger.info(f"是否收敛: {'是' if convergence_count >= max_convergence_checks else '否'}")
    logger.info(f"是否中止: {'是' if training_aborted else '否'}")
    logger.info("=" * 80)

    results_dir = Path("outputs/results")
    results_dir.mkdir(parents=True, exist_ok=True)

    plot_path = results_dir / f"{algorithm.lower()}_formation_training_results.png"
    logger.info(f"\n生成可视化图表: {plot_path}")
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
        'max_speed': env.max_speed,
        'training_time_seconds': total_time
    }

    save_results(results, str(results_dir / f"{algorithm.lower()}_formation_results"))

    logger.info("\n" + "=" * 80)
    logger.info("最终训练结果汇总")
    logger.info("=" * 80)
    logger.info(f"   - 算法: {algorithm.upper()}")
    logger.info(f"   - 无人机数量: {results['num_drones']}")
    logger.info(f"   - 目标距离: {results['target_distance']} m")
    logger.info(f"   - 最大速度: {results['max_speed']} m/s")
    logger.info(f"   - 训练回合: {results['total_episodes']}")
    logger.info(f"   - 最佳奖励: {results['best_reward']:.2f}")
    logger.info(f"   - 平均奖励: {results['mean_reward']:.2f}")
    logger.info(f"   - 最终奖励: {results['final_reward']:.2f}")
    logger.info(f"   - 平均速度: {results['mean_velocity']:.2f} m/s")
    logger.info(f"   - 已收敛: {'是' if results['converged'] else '否'}")
    logger.info("=" * 80)
    logger.info(f"\n结果已保存到: {results_dir.absolute()}")
    logger.info(f"JSON: {results_dir / f'{algorithm.lower()}_formation_results.json'}")
    logger.info(f"YAML: {results_dir / f'{algorithm.lower()}_formation_results.yaml'}")
    logger.info(f"图表: {plot_path}")
    logger.info("=" * 80 + "\n")

    return results


def main():
    """主函数"""
    import argparse

    parser = argparse.ArgumentParser(description='Agent Lightning 多智能体无人机编队控制训练')
    parser.add_argument('--algorithm', type=str, default='PPO',
                        choices=['DQN', 'PPO', 'SAC', 'MAPPO'], help='训练算法')
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