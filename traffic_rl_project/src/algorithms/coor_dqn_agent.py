"""
协同阈值 DQN 智能体（公平 baseline：M-DQN-fair）。

【定位】与 M1（MAPPO 协同阈值）完全同架构，只把第2层 RL 算法从 MAPPO 换成 DQN：
- 第1层：规则循环制动 + 车钩力安全层（与 M1/M3/M4 相同，HierarchicalController）
- 第2层：DQN 每列输出离散 coor_adj ∈ [-1,1]（映射为 v_max_adj/v_min_adj 阈值偏移），
  喂给与 M1 完全相同的 HierarchicalController.get_action(train_env, coor_adj)。

与朴素 M-DQN（Zhang2024 式，学单列循环制动、无安全层、无协同）不同，本 agent
是有"规则循环制动 + 车钩力安全层 + DQN 协同"的公平 baseline，可回答审稿人
"DQN 输是因为没协同/没安全层，还是因为 DQN 本身不如 MAPPO"的质疑。

离散动作空间 = 协同阈值偏移档位。obs 与 M1 相同（11 维，train_fleet_env._get_obs）。

【2026-09-10 基类重构】网络/回放/更新/存档协议上移至 base_agent.BaseDQNAgent，
本文件只保留协同档位映射。
"""
import numpy as np

from .base_agent import BaseDQNAgent, QNetworkMLP


class CoorDQN(QNetworkMLP):
    """Q 网络：obs -> Q(s, a)（保留原名，向后兼容既有导入）。"""


class CoorDQNAgent(BaseDQNAgent):
    """DQN 协同阈值智能体（每列独立 DQN 输出 coor_adj）。"""

    # 离散动作 → 协同阈值偏移 coor_adj ∈ [-1,1]（均匀档位，负=延后制动/提前缓解，
    # 正=提前制动/延后缓解，0=无偏移）。经 HierarchicalController 映射为
    # v_max_adj/v_min_adj（限制 ±COOP_LIMIT=±5km/h）。
    # 用奇数量档位保证 0 是中间档（无协同偏移），与 M3（δ=0）可比。
    NUM_ACTIONS = 5
    COOR_GRID = np.linspace(-1.0, 1.0, NUM_ACTIONS, dtype=np.float32)  # [-1,-0.5,0,0.5,1]

    def __init__(
        self,
        obs_dim: int,
        num_actions: int = None,
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
            obs_dim, num_actions or self.NUM_ACTIONS, lr=lr, gamma=gamma, tau=tau,
            buffer_size=buffer_size, batch_size=batch_size,
            eps_start=eps_start, eps_end=eps_end, eps_decay=eps_decay,
            device=device)

    def action_to_coor(self, action_idx: int) -> float:
        """离散动作索引 → coor_adj ∈ [-1,1]。"""
        return float(self.COOR_GRID[action_idx])
