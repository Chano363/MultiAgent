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
        # 【2026-10-11 分级制动】循环制动只在**深超速**时才用调用方给的深档，
        # 刚过上限一律用浅档（= 深档幅值 × shallow_ratio，-0.8 → -0.2 = MIN 档，
        # 对齐文献「最小常用制动」口径）。依据：开环/闭环档位扫描实测
        # （DIAGNOSTICS_2026-10.md「开环对照-2026-10-11」）——
        #   纯 EMERGENCY(-0.8)：压钩 990 kN 贴限、掉速至 31.2 km/h、进出带 18 次、反转 2.85 次/min
        #   纯 MIN(-0.2)     ：压钩 512 kN、掉速 39.6、进出带 11 次、反转 0.75 次/min
        self.shallow_ratio = 0.25
        self.deep_notch_margin_kmh = 5.0
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

        if not self._cyclic_braking:
            throttle = float(release_throttle)
        else:
            # 分级制动：刚过上限用浅档（最小常用制动），深超速才用调用方给的深档。
            # 恒定深档是速度大摆与车钩力震荡的主放大器——一次深制动直接把速度
            # 打穿下限（实测 80→31 km/h），再反复"深制动↔缓解"循环（见 __init__ 注释）。
            overshoot_kmh = (vel - eff_v_max) * 3.6
            if overshoot_kmh >= self.deep_notch_margin_kmh:
                throttle = float(brake_notch)    # 深超速兜底，保留调用方档位意图
            else:
                throttle = float(np.sign(brake_notch) * abs(brake_notch) * self.shallow_ratio)

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
        """构造安全层需要的状态快照。

        【bug修复 2026-08-20】原实现 gaps 全 0，导致 SafetyLayer 规则3
        （间距下限防护）对每节车恒触发，列内正牵引被错误钳制为 0。
        现与 train_env._state_snapshot() 一致，正确计算 gaps[i]=pos[i-1]-pos[i]。
        """
        dyn = train_env.dynamics
        n = train_env.num_vehicles
        pos = dyn.pos
        gaps = np.full(n, 0.1)  # min_gap_m 兜底（与 SafetyLayer 默认一致）
        for i in range(1, n):
            gaps[i] = pos[i - 1] - pos[i]
        return {
            'vel': np.array(dyn.vel, dtype=float),
            # 【2026-09-30 口径统一】改用**断面力**每车视图（原每车净力会漏报/误报）
            'coupler_forces': np.array(
                dyn.coupler_interface_forces_per_vehicle(), dtype=float),
            # 【U 组 2026-10-16】带符号断面力（正=拉钩，负=压钩）→ 安全层方向感知分流
            'coupler_forces_signed': np.array(
                dyn.coupler_interface_forces_per_vehicle_signed(), dtype=float),
            'gaps': gaps,
            'emergency': False,
            'dt': float(train_env.dt),
        }
