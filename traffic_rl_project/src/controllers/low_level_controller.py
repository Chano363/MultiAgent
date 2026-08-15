"""
列内底层控制器（层级二）：执行加速度指令 + 车钩力约束。

【架构（2026-08-15 方案 B）】
- 层级一（列间 MARL）：智能体 = 每列，输出该列目标加速度（宏观决策）
  （对齐 Zhang2021 每列控加速度，动作直接影响物理 → 有真实学习区分度，
   解决"目标速度被物理极限锁死"导致的"学无可学"）
- 层级二（本文件，列内底层控制器）：把目标加速度转换为该列 throttle（牵引/制动），
  并用安全层对超车钩力动作做钳制。

第一版：目标加速度 → throttle 线性映射 + 车钩力安全钳制。
"""

import numpy as np

from src.safety_layer import SafetyLayer
from src.environments.train_env import COUPLER_FORCE_LIMIT_N


class TrainLowLevelController:
    """单列底层控制器：加速度指令 → throttle + 车钩力约束。

    对一列万吨列车（1 机车 + 100 拖挂），输出单一列级 throttle（正=牵引，负=制动），
    由 TrainFormationEnv.step 执行列内动力学。

    Args:
        num_vehicles: 该列车辆数
        dt: 控制步长
        max_accel: 最大加速度（m/s²），throttle=1 对应的满牵引加速度
        coupler_force_limit_n: 车钩力上限
    """

    def __init__(
        self,
        num_vehicles: int,
        dt: float = 0.1,
        max_accel: float = 1.0,
        coupler_force_limit_n: float = COUPLER_FORCE_LIMIT_N,
    ):
        self.num_vehicles = num_vehicles
        self.dt = dt
        self.max_accel = max_accel  # throttle=±1 对应的满牵引/满制动加速度
        self.coupler_force_limit_n = coupler_force_limit_n
        self._safety = SafetyLayer(
            num_vehicles=num_vehicles,
            coupler_force_limit_n=coupler_force_limit_n,
        )

    def reset(self):
        pass

    def get_action_accel(self, train_env, target_accel: float) -> np.ndarray:
        """根据目标加速度，输出该列 throttle 动作（列级，所有车厢统一）。

        Args:
            train_env: TrainFormationEnv（该列），读当前车钩力状态
            target_accel: 层级一给定的目标加速度（m/s²，正=加速牵引，负=减速制动）

        Returns:
            actions: 该列所有车厢统一的 throttle ∈ [-1,1]（列级动作）
        """
        # 目标加速度 → throttle（线性映射：max_accel 对应 ±1）
        throttle = float(np.clip(target_accel / max(self.max_accel, 1e-6), -1.0, 1.0))

        # 车钩力接近上限时按比例缓和 throttle（"接近上限预缓和"）：
        # 车钩力越高，允许的牵引/制动幅度越小，避免动作冲过上限导致车钩力爆表。
        # 这是对"加速度动作更激进"副作用的平衡（V5.10：peakCoupler 偶尔超 1000kN）。
        snapshot = self._state_snapshot(train_env)
        coupler_peak = float(np.max(np.abs(snapshot['coupler_forces']))) if self.num_vehicles else 0.0
        if coupler_peak > 0:
            # 车钩力占比上限：>0.8 上限时开始线性缓和，到上限时 throttle 减到 0
            ratio = coupler_peak / max(self.coupler_force_limit_n, 1e-6)
            if ratio > 0.8:
                scale = max(1.0 - (ratio - 0.8) / 0.2, 0.0)  # 0.8→1.0 时 scale 1→0
                throttle *= scale

        # 列级动作（所有车厢统一 throttle）
        actions = np.full(self.num_vehicles, throttle)

        # 安全层：车钩力超限时钳制该车动作（对称拦牵引/制动）
        actions = self._safety.protect(actions, snapshot)
        return actions

    @staticmethod
    def _state_snapshot(train_env) -> dict:
        """构造安全层需要的状态快照。"""
        dyn = train_env.dynamics
        return {
            'vel': np.array(dyn.vel, dtype=float),
            'coupler_forces': np.array(np.abs(dyn._coupler_forces()), dtype=float),
            'gaps': np.zeros(train_env.num_vehicles),
            'emergency': False,
        }
