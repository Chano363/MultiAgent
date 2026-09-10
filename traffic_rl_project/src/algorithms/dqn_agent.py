"""
DQN 智能体（对标 Zhang2024：用 DQN 学单列循环制动）。

Zhang2024（Algorithms 2024,17,190）在朔黄线用 DQN 学单列循环制动，动作=离散制动设置。
本实现：
- Q-network：MLP，输入 obs，输出每个离散动作的 Q 值
- 离散动作空间：参考 Zhang2024 的制动档位（电制动 + 空气制动），映射为 throttle
  （负=制动，正=牵引，0=缓解/惰行）
- 训练：经验回放 + target network + ε-greedy 探索

用作论文 baseline（M-DQN）：单列 DQN 学循环制动，多列场景中每列独立 DQN（无协同），
对比 M1（MAPPO 协同）。

【2026-09-10 基类重构】网络/回放/更新/存档协议上移至 base_agent.BaseDQNAgent，
本文件只保留 Zhang2024 式动作映射。
"""
import numpy as np

from .base_agent import BaseDQNAgent, QNetworkMLP


class DQN(QNetworkMLP):
    """Q 网络：obs -> Q(s, a)（保留原名，向后兼容既有导入）。"""


class DQNAgent(BaseDQNAgent):
    """DQN 智能体（离散动作，学循环制动）。"""

    # 离散动作 → throttle 映射（对齐循环制动：制动/缓解/牵引）
    # 0: 缓解/惰行(0), 1: SERVICE制动(-0.75), 2: 牵引(+0.5), 3: 弱制动(-0.4)
    ACTION_THROTTLE = np.array([0.0, -0.75, 0.5, -0.4], dtype=np.float32)

    def __init__(
        self,
        obs_dim: int,
        num_actions: int = 4,
        lr: float = 1e-4,
        gamma: float = 0.99,
        tau: float = 0.005,
        buffer_size: int = 100000,
        batch_size: int = 128,
        eps_start: float = 1.0,
        eps_end: float = 0.05,
        eps_decay: float = 0.995,
        device: str = 'cuda',
    ):
        super().__init__(
            obs_dim, num_actions, lr=lr, gamma=gamma, tau=tau,
            buffer_size=buffer_size, batch_size=batch_size,
            eps_start=eps_start, eps_end=eps_end, eps_decay=eps_decay,
            device=device)

    def action_to_throttle(self, action_idx: int) -> float:
        """离散动作 → throttle。"""
        return float(self.ACTION_THROTTLE[action_idx])
