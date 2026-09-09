"""
分层控制器（层级二）：规则循环制动控速（不用 RL）+ 层级一目标速度协同。

【最终分层框架（2026-08-22 战略重构）】
- 层级一（第2层）：多列 MARL 智能体 = 每列，输出"协同目标速度偏移" v_coop ∈ [-1,1]
- 层级二（本文件）：规则循环制动 get_action_cyclic_braking（领域最优，已验证
  缓解波下车钩力 523kN 稳定）负责单列控速，不用 RL。

【B 机制（2026-09-04）】协同信号从"对称阈值偏移"改为"目标巡航速度"：
- 定位（reward 分解）：原 coor_adj 对称偏移致列车制动频繁（brake 成本 −8760/8k 步）、
  循环制动 29 次（vs MPC 11）、效率低 → reward 低于 M3/MPC。
- 新机制：RL 选每列目标巡航速度（target_speed ±10km/h），规则循环制动围绕该目标
  循环（半带宽 ±10km/h）——协同直接控"高效速度水平"，减少无效制动。

战略依据：
- RL 学单列循环制动结构性失败（缓解波长时延 6s → PPO 信用分配失效 + 车钩力
  多体强耦合 → 探索即爆炸；连续/离散/warm start/循环引导均失败，MEMORY L72）
- 领域标准（Zhang2024/Tang2020）：重载列车 RL 用离散档位 + 规则循环制动；
  Zhang2024 用 DQN 学循环制动但忽略车钩力（单质点）——我们建模车钩力，不能照搬
- 正确分层：第1层规则循环制动（微观控速）+ 第2层 RL 宏观协同（选目标速度，不直接动 throttle）
"""

import numpy as np
from pathlib import Path
import sys

sys.path.append(str(Path(__file__).parent.parent.parent))

from src.controllers.low_level_controller import TrainLowLevelController


class HierarchicalController:
    """每列的分层控制器：规则循环制动控速 + 目标速度协同 + 车钩力安全钳制。

    【重构 2026-08-22】不再用 RL 第1层策略（RL 学单列循环制动结构性失败），
    改用领域最优的规则循环制动（get_action_cyclic_braking，含车钩力安全层）。
    第2层 RL 输出目标巡航速度偏移（宏观协同），不直接动 throttle。
    """

    # 目标速度协同参数（B 机制，2026-09-04）：
    # - COOP_RANGE：v_coop=±1 对应的目标巡航速度偏移（±10 km/h）
    # - CYCLIC_HALF_BAND：规则循环制动围绕目标速度的半带宽（±10 km/h）
    COOP_RANGE = 10.0 / 3.6        # 目标速度偏移范围（±10 km/h，m/s）
    CYCLIC_HALF_BAND = 10.0 / 3.6  # 循环制动带半宽（±10 km/h，m/s）

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
        self.adj_coef = adj_coef  # 兼容旧调用（B 机制下不用，保留参数）
        # 规则循环制动控制器（含车钩力安全层，领域最优）
        self._low_level = TrainLowLevelController(
            num_vehicles=num_vehicles,
            dt=0.1,
            coupler_force_limit_n=coupler_force_limit_n,
            enforce_coupler=True,
            coupler_override='min_brake',
        )

    def get_action(self, train_env, v_coop: float) -> np.ndarray:
        """目标速度协同：v_coop ∈ [-1,1] → 目标巡航速度，规则循环制动围绕目标循环。

        【B 机制（2026-09-04）】替换原"coor_adj 对称阈值偏移"：RL 直接选目标巡航
        速度（高效速度水平），循环制动在该目标附近控速（半带宽 ±10km/h）——
        减少无效制动、提升效率（定位：原机制制动频繁致 reward 低）。

        Args:
            train_env: TrainFormationEnv（该列）
            v_coop: 层级一 RL 协同目标速度偏移 ∈ [-1,1]（宏观）

        Returns:
            actions: 该列所有车厢统一的 throttle ∈ [-1,1]（列级动作）
        """
        # 目标巡航速度 = target_speed + v_coop × COOP_RANGE（±10km/h），
        # 限制在安全循环带内（保证 eff_v_max ≤ v_max, eff_v_min ≥ v_min）
        v_target = self.target_speed + float(np.clip(v_coop, -1.0, 1.0)) * self.COOP_RANGE
        v_target = float(np.clip(v_target,
                                 self.v_min + self.CYCLIC_HALF_BAND,
                                 self.v_max - self.CYCLIC_HALF_BAND))
        # 循环制动带 = 目标 ± 半带宽 → 转成相对固定 v_max/v_min 的阈值偏移
        eff_v_max = v_target + self.CYCLIC_HALF_BAND
        eff_v_min = v_target - self.CYCLIC_HALF_BAND
        v_max_adj = eff_v_max - self.v_max
        v_min_adj = eff_v_min - self.v_min
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
