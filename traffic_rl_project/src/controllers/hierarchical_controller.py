"""
分层控制器（层级二）：规则循环制动控速（不用 RL）+ 层级一阈值协同。

【最终分层框架（2026-08-22 战略重构）】
- 层级一（第2层）：多列 MARL 智能体 = 每列，输出"协同阈值偏移" δ ∈ [-1,1]
- 层级二（本文件）：规则循环制动 get_action_cyclic_braking（领域最优，已验证
  缓解波下车钩力 523kN 稳定）负责单列控速，不用 RL。

战略依据：
- RL 学单列循环制动结构性失败（缓解波长时延 6s → PPO 信用分配失效 + 车钩力
  多体强耦合 → 探索即爆炸；连续/离散/warm start/循环引导均失败，MEMORY L72）
- 领域标准（Zhang2024/Tang2020）：重载列车 RL 用离散档位 + 规则循环制动；
  Zhang2024 用 DQN 学循环制动但忽略车钩力（单质点）——我们建模车钩力，不能照搬
- 正确分层：第1层规则循环制动（微观控速）+ 第2层 RL 宏观协同（调阈值不直接动 throttle）

协同方式：coor_adj ∈ [-1,1] 映射为 v_max_adj/v_min_adj（阈值偏移，限制 ±COOP_LIMIT），
不直接叠加 throttle（避免 E16/E18 的 δ 破坏规则循环制动）。
"""

import numpy as np
from pathlib import Path
import sys

sys.path.append(str(Path(__file__).parent.parent.parent))

from src.controllers.low_level_controller import TrainLowLevelController


class HierarchicalController:
    """每列的分层控制器：规则循环制动控速 + 协同阈值偏移 + 车钩力安全钳制。

    【重构 2026-08-22】不再用 RL 第1层策略（RL 学单列循环制动结构性失败），
    改用领域最优的规则循环制动（get_action_cyclic_braking，含车钩力安全层）。
    第2层 RL 输出 v_max_adj/v_min_adj 阈值偏移（宏观协同），不直接动 throttle。
    """

    # 协同阈值偏移上限（m/s）：coor_adj=±1 对应 ±COOP_LIMIT 的速度阈值偏移
    # 限制在 ±5km/h，避免 E17 探索到极端阈值破坏规则循环制动。
    COOP_LIMIT = 5.0 / 3.6  # 5 km/h

    def __init__(
        self,
        num_vehicles: int,
        coupler_force_limit_n: float,
        target_speed: float,
        v_max: float = 80.0 / 3.6,
        v_min: float = 40.0 / 3.6,
        adj_coef: float = 0.3,
        line_speed_limit_mps: float = 30.0,
    ):
        self.num_vehicles = num_vehicles
        self.coupler_force_limit_n = coupler_force_limit_n
        self.target_speed = target_speed
        self.v_max = v_max  # 规则循环制动限速上限
        self.v_min = v_min  # 规则循环制动限速下限
        self.adj_coef = adj_coef
        # 规则循环制动控制器（含车钩力安全层，领域最优）
        self._low_level = TrainLowLevelController(
            num_vehicles=num_vehicles,
            dt=0.1,
            coupler_force_limit_n=coupler_force_limit_n,
            enforce_coupler=True,
            coupler_override='min_brake',
        )

    def get_action(self, train_env, coor_adj: float) -> np.ndarray:
        """最终列级动作：规则循环制动 + 协同阈值偏移 v_max_adj/v_min_adj。

        Args:
            train_env: TrainFormationEnv（该列）
            coor_adj: 层级一 RL 协同调整量 ∈ [-1,1]（宏观，限制在 ±COOP_LIMIT）

        Returns:
            actions: 该列所有车厢统一的 throttle ∈ [-1,1]（列级动作）
        """
        # 协同调整 → 规则循环制动阈值偏移（不直接动 throttle，不破坏循环制动）
        # coor_adj>0 → 提前制动/延后缓解（配合前列，防追尾）；<0 → 延后制动/提前缓解
        adj = float(np.clip(coor_adj, -1.0, 1.0)) * self.adj_coef * self.COOP_LIMIT
        v_max_adj = adj   # 制动触发阈值偏移
        v_min_adj = adj   # 缓解触发阈值偏移
        return self._low_level.get_action_cyclic_braking(
            train_env,
            v_max=self.v_max,
            v_min=self.v_min,
            brake_notch=-0.75,
            release_throttle=0.0,
            v_max_adj=v_max_adj,
            v_min_adj=v_min_adj,
        )

    def reset(self):
        """重置循环制动状态（跨回合）。"""
        self._low_level.reset()
