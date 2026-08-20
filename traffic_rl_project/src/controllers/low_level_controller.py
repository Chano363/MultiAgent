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
        enforce_coupler: bool = True,
        coupler_override: str = 'release',
    ):
        self.num_vehicles = num_vehicles
        self.dt = dt
        self.max_accel = max_accel  # throttle=±1 对应的满牵引/满制动加速度
        self.coupler_force_limit_n = coupler_force_limit_n
        # 是否执行车钩力约束（消融实验：enforce_coupler=False 模拟"忽略车钩力"控制）
        self.enforce_coupler = enforce_coupler
        self._safety = SafetyLayer(
            num_vehicles=num_vehicles,
            coupler_force_limit_n=coupler_force_limit_n,
            coupler_override=coupler_override,
        )

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

        # 【E3 修复：限制制动深度，禁止探索期打满 EMERGENCY 制动】
        # 根因2：RL 探索期随机输出 throttle<-0.8 → EMERGENCY 满制动 + 空气制动波速传播延迟
        # → 列内前后制动力不同步 → 车钩力轻易爆表（v3 峰值1439kN）。第1层固定 -0.75(SERVICE)
        # 温和制动所以成功。这里把制动幅度压缩到 [-MIN_BRAKE, 0]，牵引保留 [-1,1]。
        # MIN_BRAKE=-0.75 = SERVICE 档（0.75倍制动力），对齐第1层成功配置。
        if throttle < 0.0:
            throttle = max(throttle, -0.75)  # 制动最深到 SERVICE 档，不打满 EMERGENCY

        # 车钩力约束（可开关，消融实验用）
        if self.enforce_coupler:
            # 车钩力接近上限时按比例缓和 throttle（"接近上限预缓和"）：
            # 车钩力越高，允许的牵引/制动幅度越小，避免动作冲过上限导致车钩力爆表。
            snapshot = self._state_snapshot(train_env)
            coupler_peak = float(np.max(np.abs(snapshot['coupler_forces']))) if self.num_vehicles else 0.0
            if coupler_peak > 0:
                ratio = coupler_peak / max(self.coupler_force_limit_n, 1e-6)
                if ratio > 0.8:
                    scale = max(1.0 - (ratio - 0.8) / 0.2, 0.0)  # 0.8→1.0 时 scale 1→0
                    throttle *= scale
        else:
            snapshot = self._state_snapshot(train_env)

        # 列级动作（所有车厢统一 throttle）
        actions = np.full(self.num_vehicles, throttle)

        # 安全层：车钩力超限时钳制该车动作（对称拦牵引/制动）
        if self.enforce_coupler:
            actions = self._safety.protect(actions, snapshot)
        return actions

    def get_action_cyclic_braking(self, train_env, v_max: float, v_min: float,
                                  brake_notch: float = -0.75,
                                  release_throttle: float = 0.0,
                                  v_max_adj: float = 0.0,
                                  v_min_adj: float = 0.0) -> np.ndarray:
        """【混合方案·列内】规则循环制动：按当前速度在限速区间内做制动-缓解循环。

        对齐 Zhang2024（Algorithms 2024,17,190）的循环制动策略：
        - 速度 > v_max（上限，如 80 km/h）→ 制动（brake_notch，负 throttle）
        - 速度 < v_min（下限，如 40 km/h）→ 缓解（release_throttle，0 或小牵引）
        - 中间区间 → 维持上次动作（制动/缓解交替，模拟循环制动，减少频繁切换）

        循环制动 → 速度在 [v_min, v_max] 间波动 → 每次制动是列内纵向冲动源，
        车钩力在此压力下凸显（这是第2层"车钩力是群组协同瓶颈"的列内基础）。

        输出仍走车钩力安全层钳制（保证车钩力 ≤1000kN）。

        Args:
            train_env: TrainFormationEnv（该列），读当前速度/车钩力状态
            v_max: 限速上限（m/s），高于此速度触发制动
            v_min: 限速下限（m/s），低于此速度缓解
            brake_notch: 制动档位（负 throttle ∈ [-1,0)，默认 -0.75）
            release_throttle: 缓解动作（默认 0，即惰行）

        Returns:
            actions: 该列所有车厢统一的 throttle ∈ [-1,1]（列级动作）
        """
        # 维持上次制动状态（循环制动的"保持"逻辑，避免频繁切换）
        if not hasattr(self, '_cyclic_braking'):
            self._cyclic_braking = False

        # E17 协同参数调整：第2层 RL 输出 v_max_adj/v_min_adj 调整该列制动/缓解
        # 触发阈值（不直接动 throttle，不破坏规则循环制动逻辑）。
        # v_max_adj>0 → 提前制动（更高速度触发制动，防超速）；<0 → 延后制动。
        # v_min_adj>0 → 提前缓解（更高速度恢复牵引）；<0 → 延后缓解（更低速度缓解）。
        eff_v_max = v_max + v_max_adj
        eff_v_min = v_min + v_min_adj

        vel = float(train_env.dynamics.vel[0])  # 机车速度（列首）
        if vel >= eff_v_max:
            self._cyclic_braking = True          # 超速 → 制动
        elif vel <= eff_v_min:
            self._cyclic_braking = False         # 低速 → 缓解
        # 中间区间维持 self._cyclic_braking（制动/缓解交替）

        throttle = float(brake_notch if self._cyclic_braking else release_throttle)

        # 车钩力约束（可开关，消融实验用）
        snapshot = self._state_snapshot(train_env)
        if self.enforce_coupler:
            coupler_peak = float(np.max(np.abs(snapshot['coupler_forces']))) if self.num_vehicles else 0.0
            if coupler_peak > 0:
                ratio = coupler_peak / max(self.coupler_force_limit_n, 1e-6)
                if ratio > 0.8:
                    # 车钩力接近上限时按比例缓和 throttle（"接近上限预缓和"）
                    scale = max(1.0 - (ratio - 0.8) / 0.2, 0.0)  # 0.8→1.0 时 scale 1→0
                    throttle *= scale

        # 列级动作（所有车厢统一 throttle）
        actions = np.full(self.num_vehicles, throttle)

        # 安全层：车钩力超限时钳制该车动作（对称拦牵引/制动）
        if self.enforce_coupler:
            actions = self._safety.protect(actions, snapshot)
        return actions

    def reset(self):
        # 重置循环制动状态（跨回合，避免上一个回合的制动状态泄漏到本回合）
        if hasattr(self, '_cyclic_braking'):
            self._cyclic_braking = False

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
