"""Agent Lightning integration for the drone formation RL project.

This adapter keeps the existing PPO/DQN control logic intact while routing
episode execution through Agent Lightning's `Trainer.fit` + `LitAgent` flow.
It avoids any extra LLM dependencies by using a local LiteLLM compatibility
shim in the project workspace.
"""

from __future__ import annotations

import logging
import multiprocessing as mp
from pathlib import Path
from typing import Any, Dict, List, Optional
import time

import numpy as np
import torch
import yaml

from agentlightning.algorithm.fast import Baseline
from agentlightning.emitter.reward import emit_reward
from agentlightning.execution.shared_memory import SharedMemoryExecutionStrategy
from agentlightning.litagent import LitAgent
from agentlightning.types.resources import LLM, PromptTemplate
from agentlightning.trainer import Trainer
from agentlightning.tracer.otel import OtelTracer

from src.algorithms.optimized_dqn import OptimizedDQNAgent
from src.algorithms.optimized_ppo import OptimizedPPOAgent
from src.algorithms.sac_agent import SACAgent
from src.environments import make_formation_control_env
from src.utils import plot_training_curve, save_results

# 获取 logger（不重复配置）
logger = logging.getLogger('DroneRL')


def load_config(config_path: str) -> Dict[str, Any]:
    """Load a YAML config file."""
    with open(config_path, "r", encoding="utf-8") as handle:
        return yaml.safe_load(handle)


def set_seed(seed: int) -> None:
    """Set deterministic seeds for the training run."""
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
):
    """Create the project-specific RL agent."""
    algo_params = config.get("training", {}).get("hyperparameters", {})

    if algorithm.upper() == "DQN":
        params = algo_params.get("dqn", {})
        return OptimizedDQNAgent(
            state_dim=state_dim,
            action_dim=action_dim,
            learning_rate=params.get("learning_rate", 2.5e-4),
            gamma=params.get("gamma", 0.99),
            epsilon_start=params.get("epsilon_start", 1.0),
            epsilon_decay=params.get("epsilon_decay", 0.995),
            epsilon_min=params.get("epsilon_min", 0.01),
            buffer_size=params.get("buffer_size", 10000),
            batch_size=params.get("batch_size", 128),
            target_update_freq=params.get("target_update_freq", 100),
            device=device,
            hidden_sizes=params.get("network_architecture", [256, 256, 128]),
            use_layer_norm=params.get("use_layer_norm", True),
            use_prioritized_replay=params.get("use_prioritized_replay", True),
            double_dqn=params.get("double_dqn", True),
        )

    if algorithm.upper() == "PPO":
        params = algo_params.get("ppo", {})
        return OptimizedPPOAgent(
            state_dim=state_dim,
            action_dim=action_dim,
            learning_rate=params.get("learning_rate", 2.5e-4),
            gamma=params.get("gamma", 0.99),
            gae_lambda=params.get("gae_lambda", 0.95),
            clip_epsilon=params.get("clip_epsilon", 0.15),
            entropy_coef=params.get("entropy_coef", 0.005),
            value_coef=params.get("value_coef", 0.5),
            epochs=params.get("epochs", 10),
            batch_size=params.get("batch_size", 128),
            n_steps=params.get("n_steps", 100),
            max_grad_norm=params.get("max_grad_norm", 0.5),
            device=device,
            use_gae=params.get("use_gae", True),
            use_clipped_value_loss=params.get("use_clipped_value_loss", True),
            use_entropy_decay=params.get("use_entropy_decay", True),
        )

    if algorithm.upper() == "SAC":
        params = algo_params.get("sac", {})
        return SACAgent(
            state_dim=state_dim,
            action_dim=action_dim,
            learning_rate=params.get("learning_rate", 3e-4),
            gamma=params.get("gamma", 0.99),
            tau=params.get("tau", 0.005),
            alpha=params.get("alpha", 0.2),
            automatic_entropy_tuning=params.get("automatic_entropy_tuning", True),
            buffer_capacity=params.get("buffer_capacity", 1000000),
            batch_size=params.get("batch_size", 256),
            device=device,
        )

    raise ValueError(f"不支持的算法: {algorithm}")


def _check_convergence(rewards: List[float], window: int, threshold: float) -> bool:
    if len(rewards) < window:
        return False

    recent_rewards = rewards[-window:]
    mean_reward = np.mean(recent_rewards)
    std_reward = np.std(recent_rewards)
    return std_reward < threshold * abs(mean_reward)


class DroneFormationLitAgent(LitAgent[Dict[str, Any]]):
    """Rollout wrapper that executes one environment episode per task."""

    def __init__(
        self,
        env,
        agent,
        algorithm: str,
        device: str,
        checkpoint_dir: str,
        save_every: int = 10,
        convergence_window: int = 50,
        convergence_threshold: float = 0.1,
        max_convergence_checks: int = 5,
        total_episodes: int = 0,
    ):
        super().__init__()
        self.env = env
        self.agent = agent
        self.algorithm = algorithm.upper()
        self.device = device
        self.checkpoint_dir = Path(checkpoint_dir)
        self.save_every = save_every
        self.convergence_window = convergence_window
        self.convergence_threshold = convergence_threshold
        self.max_convergence_checks = max_convergence_checks
        self.total_episodes = total_episodes

        self.episode_rewards: List[float] = []
        self.episode_losses: List[float] = []
        self.episode_mean_velocities: List[float] = []
        self.episode_formation_errors: List[float] = []
        self.episode_height_errors: List[float] = []
        self.best_reward = float("-inf")
        self.convergence_count = 0

    def _save_checkpoint(self, episode_id: int) -> None:
        self.checkpoint_dir.mkdir(parents=True, exist_ok=True)
        checkpoint_path = self.checkpoint_dir / f"{self.algorithm.lower()}_formation_ep{episode_id}.pt"
        self.agent.save(str(checkpoint_path))
        file_size_mb = checkpoint_path.stat().st_size / (1024 * 1024)
        logger.info(f"检查点已保存: {checkpoint_path.name} ({file_size_mb:.2f} MB)")

    def rollout(self, task: Dict[str, Any], resources, rollout):  # noqa: D401
        episode_id = int(task.get("episode_id", len(self.episode_rewards)))
        episode_reward = 0.0
        episode_loss = 0.0
        episode_velocities = []
        episode_formation_errors = []
        episode_height_errors = []

        with self.tracer.operation_context(
            name="drone_episode",
            attributes={"episode_id": episode_id, "algorithm": self.algorithm},
        ):
            state, _ = self.env.reset()
            done = False
            episode_steps = 0
            termination_reason = "timeout"

            while not done:
                if self.algorithm == "DQN":
                    action = self.agent.select_action(state, training=True)
                    if len(self.env.action_space.shape) == 2:
                        action = action.reshape(self.env.num_drones, self.env.action_space.shape[1])
                    next_state, reward, terminated, truncated, info = self.env.step(action)
                    done = terminated or truncated

                    self.agent.store_transition(state, action, reward, next_state, done)
                    loss = self.agent.update()
                    if loss > 0:
                        episode_loss += loss

                    # 记录速度
                    episode_velocities.append(np.mean(np.linalg.norm(state[:, 6:9], axis=1)))
                    episode_formation_errors.append(info.get('formation_error', 0))
                    episode_height_errors.append(info.get('height_error', 0))
                    state = next_state
                elif self.algorithm == "PPO":
                    flattened_state = state.flatten()
                    action, log_prob = self.agent.select_action(flattened_state)
                    
                    original_action = action.copy()
                    
                    if len(self.env.action_space.shape) == 2:
                        action = action.reshape(self.env.num_drones, self.env.action_space.shape[1])
                    else:
                        action = action.reshape(self.env.num_drones, 4)

                    next_state, reward, terminated, truncated, info = self.env.step(action)
                    
                    if terminated:
                        termination_reason = "terminated"
                    elif truncated:
                        termination_reason = "truncated"
                    
                    done = terminated or truncated

                    with torch.no_grad():
                        state_tensor = torch.FloatTensor(flattened_state).unsqueeze(0).to(self.device)
                        value = self.agent.value(state_tensor).item()

                    self.agent.store_transition(flattened_state, original_action, reward, log_prob, done, value)
                    # 记录速度
                    episode_velocities.append(np.mean(np.linalg.norm(state[:, 6:9], axis=1)))
                    episode_formation_errors.append(info.get('formation_error', 0))
                    episode_height_errors.append(info.get('height_error', 0))
                    state = next_state
                elif self.algorithm == "SAC":
                    flattened_state = state.flatten()
                    action = self.agent.select_action(flattened_state)

                    if len(self.env.action_space.shape) == 2:
                        action_for_env = action.reshape(self.env.num_drones, self.env.action_space.shape[1])
                    else:
                        action_for_env = action.reshape(self.env.num_drones, 4)

                    next_state, reward, terminated, truncated, info = self.env.step(action_for_env)

                    if terminated:
                        termination_reason = "terminated"
                    elif truncated:
                        termination_reason = "truncated"

                    done = terminated or truncated

                    self.agent.store_transition(flattened_state, action, reward, next_state.flatten(), done)

                    metrics = self.agent.update()
                    episode_loss += metrics.get("total_loss", 0.0)

                    # 记录速度
                    episode_velocities.append(np.mean(np.linalg.norm(state[:, 6:9], axis=1)))
                    episode_formation_errors.append(info.get('formation_error', 0))
                    episode_height_errors.append(info.get('height_error', 0))
                    state = next_state

                episode_steps += 1
                episode_reward += reward

            if self.algorithm == "PPO":
                buffer_size = len(self.agent.buffer_states) if self.agent.buffer_states else 0
                metrics = self.agent.update()
                episode_loss = metrics.get("total_loss", 0.0)
                
                if episode_loss == 0.0 and buffer_size > 0:
                    logger.warning(
                        f"Ep {episode_id}: Loss=0, Buffer={buffer_size}, "
                        f"Steps={episode_steps}, Term={termination_reason}, "
                        f"BatchSize={self.agent.batch_size}"
                    )
            elif self.algorithm == "SAC":
                if episode_steps > 0:
                    episode_loss = episode_loss / episode_steps

            mean_velocity = np.mean(episode_velocities) if episode_velocities else 0.0
            mean_formation_error = np.mean(episode_formation_errors) if episode_formation_errors else 0.0
            mean_height_error = np.mean(episode_height_errors) if episode_height_errors else 0.0

        self.episode_rewards.append(float(episode_reward))
        self.episode_losses.append(float(episode_loss))
        self.episode_mean_velocities.append(float(mean_velocity))
        self.episode_formation_errors.append(float(mean_formation_error))
        self.episode_height_errors.append(float(mean_height_error))

        if episode_reward > self.best_reward:
            self.best_reward = float(episode_reward)

        # 每10个episode输出一次进度
        if (episode_id + 1) % 10 == 0 or (episode_id + 1) == self.total_episodes:
            recent_mean = np.mean(self.episode_rewards[-10:]) if len(self.episode_rewards) >= 10 else np.mean(self.episode_rewards)
            recent_std = np.std(self.episode_rewards[-10:]) if len(self.episode_rewards) >= 10 else 0
            recent_formation = np.mean(self.episode_formation_errors[-10:]) if len(self.episode_formation_errors) >= 10 else mean_formation_error
            recent_height = np.mean(self.episode_height_errors[-10:]) if len(self.episode_height_errors) >= 10 else mean_height_error
            logger.info(f"Episode {episode_id + 1:4d}/{self.total_episodes} | "
                       f"Reward: {episode_reward:+7.2f} | "
                       f"Avg10: {recent_mean:7.2f}±{recent_std:5.2f} | "
                       f"Best: {self.best_reward:7.2f} | "
                       f"Loss: {episode_loss:8.4f} | "
                       f"Speed: {mean_velocity:5.2f} m/s | "
                       f"FormationErr: {recent_formation:.3f} m | HeightErr: {recent_height:.3f} m")

        try:
            emit_reward(
                float(episode_reward),
                attributes={
                    "episode": episode_id,
                    "algorithm": self.algorithm,
                    "mean_velocity": float(mean_velocity),
                },
            )
        except Exception:
            pass

        if episode_id > 0 and episode_id % self.save_every == 0:
            self._save_checkpoint(episode_id)

        # 收敛检测
        if _check_convergence(self.episode_rewards, self.convergence_window, self.convergence_threshold):
            self.convergence_count += 1
            if self.convergence_count % 5 == 0:
                logger.info(f"收敛检测: {self.convergence_count}/{self.max_convergence_checks}")
        else:
            self.convergence_count = 0

        return float(episode_reward)

    def results(self) -> Dict[str, Any]:
        total_episodes = len(self.episode_rewards)
        return {
            "algorithm": self.algorithm,
            "total_episodes": total_episodes,
            "final_reward": float(np.mean(self.episode_rewards[-10:])) if total_episodes else 0.0,
            "best_reward": float(self.best_reward),
            "mean_reward": float(np.mean(self.episode_rewards)) if total_episodes else 0.0,
            "mean_velocity": float(np.mean(self.episode_mean_velocities)) if self.episode_mean_velocities else 0.0,
            "mean_formation_error": float(np.mean(self.episode_formation_errors)) if self.episode_formation_errors else 0.0,
            "mean_height_error": float(np.mean(self.episode_height_errors)) if self.episode_height_errors else 0.0,
            "rewards": self.episode_rewards,
            "losses": self.episode_losses,
            "mean_velocities": self.episode_mean_velocities,
            "formation_errors": self.episode_formation_errors,
            "height_errors": self.episode_height_errors,
            "converged": self.convergence_count >= self.max_convergence_checks,
            "num_drones": self.env.num_drones,
            "target_distance": self.env.target_distance,
            "max_speed": self.env.max_speed,
        }


def train_with_agent_lightning(
    algorithm: str,
    config_path: str,
    env_config_path: str,
    episodes: int,
    device: str,
    checkpoint_path: Optional[str] = None,
    convergence_window: int = 50,
    convergence_threshold: float = 0.1,
    save_every: int = 10,
) -> Dict[str, Any]:
    """Train the existing RL agent through Agent Lightning orchestration."""
    
    start_time = time.time()
    
    mp.set_start_method("spawn", force=True)
    set_seed(42)

    # 环境初始化
    env = make_formation_control_env(env_config_path)
    config = load_config(config_path)

    # 计算状态和动作维度
    if len(env.observation_space.shape) == 2:
        state_dim = env.observation_space.shape[0] * env.observation_space.shape[1]
    else:
        state_dim = env.observation_space.shape[0] * env.num_drones

    if len(env.action_space.shape) == 2:
        action_dim = env.action_space.shape[0] * env.action_space.shape[1]
    else:
        action_dim = env.action_space.shape[0] * env.num_drones
    
    logger.info(f"环境: {env.num_drones}架无人机 | 状态{state_dim}维 | 动作{action_dim}维")

    # 创建智能体
    agent = create_agent(algorithm, state_dim, action_dim, config, device)

    # 加载检查点
    if checkpoint_path and Path(checkpoint_path).exists():
        agent.load(checkpoint_path)
        logger.info(f"已加载检查点: {checkpoint_path}")
    elif checkpoint_path:
        logger.warning(f"检查点不存在: {checkpoint_path}")

    # 创建 Agent Lightning 智能体
    lightning_agent = DroneFormationLitAgent(
        env=env,
        agent=agent,
        algorithm=algorithm,
        device=device,
        checkpoint_dir="outputs/checkpoints",
        save_every=save_every,
        convergence_window=convergence_window,
        convergence_threshold=convergence_threshold,
        total_episodes=episodes,
    )

    # 配置 Trainer
    trainer = Trainer(
        algorithm=Baseline(n_epochs=1, train_split=0.8, polling_interval=0.1, max_queue_length=4),
        tracer=OtelTracer(),
        strategy=SharedMemoryExecutionStrategy(n_runners=1, main_thread="algorithm"),
        initial_resources={
            "main_llm": LLM(endpoint="http://127.0.0.1:0", model="drone-formation"),
            "system_prompt": PromptTemplate(
                template="You are optimizing a drone formation controller.",
                engine="f-string",
            ),
        },
    )

    # 开始训练
    train_dataset = [{"episode_id": episode} for episode in range(episodes)]
    trainer.fit(lightning_agent, train_dataset=train_dataset)
    
    logger.debug(f"[时间跟踪] trainer.fit() 完成")

    env.close()
    
    logger.debug(f"[时间跟踪] env.close() 完成")
    
    total_time = time.time() - start_time

    # 保存结果
    results_dir = Path("outputs/results")
    results_dir.mkdir(parents=True, exist_ok=True)
    results = lightning_agent.results()

    logger.debug(f"[时间跟踪] lightning_agent.results() 完成")

    plot_path = results_dir / f"{algorithm.lower()}_formation_training_results.png"
    plot_training_curve(
        results["rewards"],
        results["losses"],
        velocities=results.get("mean_velocities"),
        formation_errors=results.get("formation_errors"),
        height_errors=results.get("height_errors"),
        save_path=str(plot_path)
    )
    
    logger.debug(f"[时间跟踪] plot_training_curve() 完成")
    
    save_results(results, str(results_dir / f"{algorithm.lower()}_formation_results"))
    
    logger.debug(f"[时间跟踪] save_results() 完成")

    # 最终结果汇总
    logger.info(f"\n{'='*60}")
    logger.info(f"训练完成 | 用时: {total_time:.1f}s ({total_time/60:.1f}min)")
    logger.info(f"{'='*60}")
    logger.info(f"回合: {results['total_episodes']} | 最佳: {results['best_reward']:.2f} | "
               f"平均: {results['mean_reward']:.2f} | 最终: {results['final_reward']:.2f}")
    logger.info(f"速度: {results['mean_velocity']:.2f} m/s | 收敛: {'是' if results['converged'] else '否'}")
    logger.info(f"结果已保存: {results_dir.absolute()}")
    logger.info(f"{'='*60}\n")

    return results
