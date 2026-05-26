"""
Agent Lightning 集成模块
用于无人机编队控制的强化学习模型优化
"""

import torch
import torch.nn as nn
import numpy as np
from typing import Dict, List, Any, Optional
import logging

try:
    import agentlightning as agl
    AGENT_LIGHTNING_AVAILABLE = True
except ImportError:
    AGENT_LIGHTNING_AVAILABLE = False
    logging.warning("Agent Lightning 未安装，将使用基础训练模式")


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

        if self.enable_tracing:
            self._setup_agent_lightning()

        self.episode_count = 0
        self.metrics_history = []

    def _setup_agent_lightning(self):
        """初始化 Agent Lightning"""
        logging.info("初始化 Agent Lightning 集成")

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
                import agentops
                agentops.log("episode_reward", episode_reward)
                agentops.log("episode_loss", episode_loss)
            except:
                pass

            if metrics:
                for key, value in metrics.items():
                    try:
                        agentops.log(key, value)
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
                import agentops
                agentops.log("exploration_rate", epsilon)
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


class RewardOptimizer:
    """奖励函数优化器"""

    def __init__(self):
        self.reward_components = {
            "queue_penalty": -0.1,
            "waiting_penalty": -0.05,
            "throughput_bonus": 0.2,
            "safety_bonus": 0.1
        }

    def compute_reward(self, info: Dict[str, Any]) -> float:
        """
        计算优化后的奖励

        Args:
            info: 环境信息，包含：
                - total_queue: 总排队车辆数
                - total_waiting_time: 总等待时间
                - vehicles_passed: 通过车辆数
                - stopped_vehicles: 停止的车辆数

        Returns:
            float: 奖励值
        """
        reward = 0.0

        if "total_queue" in info:
            reward += self.reward_components["queue_penalty"] * info["total_queue"]

        if "total_waiting_time" in info:
            reward += self.reward_components["waiting_penalty"] * info["total_waiting_time"]

        if "vehicles_passed" in info:
            reward += self.reward_components["throughput_bonus"] * info["vehicles_passed"]

        if "stopped_vehicles" in info:
            stopped_ratio = info.get("stopped_vehicles", 0) / max(info.get("total_vehicles", 1), 1)
            if stopped_ratio < 0.3:
                reward += self.reward_components["safety_bonus"]

        return reward

    def set_components(self, components: Dict[str, float]):
        """设置奖励组件权重"""
        self.reward_components.update(components)


def create_optimized_agent(
    agent_type: str,
    state_dim: int,
    action_dim: int,
    config: Optional[Dict[str, Any]] = None
):
    """
    创建优化后的智能体

    Args:
        agent_type: 智能体类型 ('dqn' 或 'ppo')
        state_dim: 状态空间维度
        action_dim: 动作空间维度
        config: 优化配置

    Returns:
        优化后的智能体
    """
    if config is None:
        config = {}

    if agent_type.lower() == "dqn":
        from src.algorithms import DQNAgent

        optimized_config = {
            "learning_rate": config.get("learning_rate", 2.5e-4),
            "gamma": config.get("gamma", 0.99),
            "epsilon": config.get("epsilon_start", 1.0),
            "epsilon_decay": config.get("epsilon_decay", 0.995),
            "epsilon_min": config.get("epsilon_min", 0.01),
            "buffer_size": config.get("buffer_size", 10000),
            "batch_size": config.get("batch_size", 128),
        }

        return DQNAgent(
            state_dim=state_dim,
            action_dim=action_dim,
            **optimized_config
        )

    elif agent_type.lower() == "ppo":
        from src.algorithms import PPOAgent

        optimized_config = {
            "learning_rate": config.get("learning_rate", 2.5e-4),
            "gamma": config.get("gamma", 0.99),
            "gae_lambda": config.get("gae_lambda", 0.95),
            "clip_epsilon": config.get("clip_epsilon", 0.15),
            "entropy_coef": config.get("entropy_coef", 0.005),
            "value_coef": config.get("value_coef", 0.5),
            "epochs": config.get("epochs", 10),
            "batch_size": config.get("batch_size", 128),
        }

        return PPOAgent(
            state_dim=state_dim,
            action_dim=action_dim,
            **optimized_config
        )

    else:
        raise ValueError(f"不支持的智能体类型: {agent_type}")


def get_default_optimization_config(agent_type: str) -> Dict[str, Any]:
    """
    获取默认优化配置

    Args:
        agent_type: 智能体类型

    Returns:
        优化配置字典
    """
    base_config = {
        "learning_rate": 2.5e-4,
        "gamma": 0.99,
        "batch_size": 128,
    }

    if agent_type.lower() == "dqn":
        return {
            **base_config,
            "epsilon_start": 1.0,
            "epsilon_decay": 0.995,
            "epsilon_min": 0.01,
            "buffer_size": 10000,
            "target_update_freq": 100,
        }

    elif agent_type.lower() == "ppo":
        return {
            **base_config,
            "gae_lambda": 0.95,
            "clip_epsilon": 0.15,
            "entropy_coef": 0.005,
            "value_coef": 0.5,
            "epochs": 10,
            "n_steps": 100,
        }

    else:
        raise ValueError(f"不支持的智能体类型: {agent_type}")
