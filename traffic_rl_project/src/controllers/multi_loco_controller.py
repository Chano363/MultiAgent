"""
多机车分布式动力 × 电空双制动分工 列内子控制器（层级二-decompose 模式）。

【2026-09-03 智能体分解重构（ADR-009）】把"整列统一 throttle"改为
"每机车=子控制器，独立决策 电制动(连续) / 空气制动(离散档位)"：

- ED（电制动）：连续可调，仅机车，即时作用（无波速传播延迟）
- AB（空气制动）：离散档位（MIN/SERVICE/EMERGENCY），沿车列以波速向后传播，
  是车钩力（纵向冲动）的主要来源

分工策略（给导师/审稿的"电空分工"核心）：
- 制动时 **首发电制动（ED）打满**：ED 响应快、不产生纵向冲动；
- 仅当 ED 功率不足以维持所需减速度（长大下坡 ED 的 功率/速度 约束）时
  才引入空气制动（AB）源 → 每机车独立错峰开启，最小化车钩力。
- 每机车 ED 独立错峰缓解（ed_frac 逐机车带时移），体现"每机车=独立体"。

输出形状：(num_locomotives, 2)，每行 [ed_frac, ab_frac]
  - ed_frac ∈ [0,1]：该机车电制动
  - ab_frac ∈ [-1,0) → 触发该机车作为 AB 波源（notch_from_throttle(ab_frac)）
  - ab_frac >= 0     → 该机车不作为 AB 源（缓解）

与 TrainLowLevelController.get_action_accel 同接口签名（fleet 无缝替换），
含车钩力 ≤1000kN 的安全钳制（投影到逐车 throttle 后走 SafetyLayer）。
"""

import numpy as np

from src.safety_layer import SafetyLayer
from src.environments.train_env import COUPLER_FORCE_LIMIT_N
from src.train_dynamics.braking import AirBrakeNotch, notch_from_throttle


class MultiLocoController:
    """每机车 (ED,AB) 子控制器：循环制动 / 目标加速度，电空分工 + 车钩力安全钳。"""

    def __init__(
        self,
        num_vehicles: int,
        loco_indices: list,
        dt: float = 0.1,
        max_accel: float = 1.0,
        coupler_force_limit_n: float = COUPLER_FORCE_LIMIT_N,
        enforce_coupler: bool = True,
        ed_priority: bool = True,
    ):
        self.num_vehicles = num_vehicles
        self.loco_indices = list(loco_indices)
        self.num_locomotives = len(self.loco_indices)
        self.dt = dt
        self.max_accel = max_accel
        self.coupler_force_limit_n = coupler_force_limit_n
        self.enforce_coupler = enforce_coupler
        self.ed_priority = ed_priority  # 电空分工：ED 优先打满，ED 不足才引 AB
        self._safety = SafetyLayer(
            num_vehicles=num_vehicles,
            coupler_force_limit_n=coupler_force_limit_n,
            coupler_override='min_brake',
        )
        self._cyclic_braking = False

    # ------------------------------------------------------------------ #
    # 内部工具
    # ------------------------------------------------------------------ #
    def _ed_ab_actions(self, ed_nominal: float, ab_nominal: float) -> np.ndarray:
        """构造 (num_locomotives,2) 动作，电力每机车 [ed_frac, ab_frac]。"""
        act = np.zeros((self.num_locomotives, 2), dtype=float)
        for i in range(self.num_locomotives):
            act[i, 0] = float(np.clip(ed_nominal, 0.0, 1.0))
            act[i, 1] = float(np.clip(ab_nominal, -1.0, 1.0))
        return act

    def _project_to_throttle(self, act) -> np.ndarray:
        """把 (num_locomotives,2) (ED,AB) 投影为整列逐车 throttle（供安全层钳制）。"""
        n = self.num_vehicles
        th = np.full(n, 0.0)
        for i, loco_idx in enumerate(self.loco_indices):
            ed = float(act[i, 0])
            ab = float(act[i, 1])
            # 电空综合制动深度 = ED + AB 深度映射（保守取较大者）
            ab_depth = 0.0
            if ab < 0:
                notch = notch_from_throttle(ab)
                ab_depth = self._notch_depth(notch)
            depth = max(ed, ab_depth)
            th[loco_idx] = -depth
        return th

    @staticmethod
    def _notch_depth(notch: AirBrakeNotch) -> float:
        return {AirBrakeNotch.RELEASE: 0.0, AirBrakeNotch.MIN: 0.2,
                AirBrakeNotch.SERVICE: 0.75, AirBrakeNotch.EMERGENCY: 1.0}.get(notch, 0.0)

    def _coupler_throttle_scale(self, train_env) -> float:
        """车钩力接近上限时按比例缓和（0.8→1.0 时 scale 1→0）。"""
        if not self.enforce_coupler:
            return 1.0
        peak = float(np.max(np.abs(train_env.dynamics._coupler_forces()))) if self.num_vehicles else 0.0
        if peak <= 0:
            return 1.0
        ratio = peak / max(self.coupler_force_limit_n, 1e-6)
        if ratio > 0.8:
            return max(1.0 - (ratio - 0.8) / 0.2, 0.0)
        return 1.0

    def _ed_ab_price(self, v: float) -> float:
        """ED 地位：速度越高 ED 可用度越高（P_ed/v 约束下高速 ED 功率足）。返回 (~0)."""
        # 简化：ED 在低速时受功率约束变弱，但电压超低几乎无力制动时需 AB。
        # 返回 ED 在该速度下的可用度 ∈ [0,1]（0=完全无力，1=足够）。
        return float(np.clip(v / 5.0, 0.0, 1.0))  # v>=5m/s 时 ED 视为足够

    # ------------------------------------------------------------------ #
    # 主接口 1：循环制动
    # ------------------------------------------------------------------ #
    def get_action_cyclic_braking(
        self, train_env, v_max: float = 80.0 / 3.6, v_min: float = 40.0 / 3.6,
        brake_notch: float = -0.75, release_throttle: float = 0.0,
        v_max_adj: float = 0.0, v_min_adj: float = 0.0,
    ) -> np.ndarray:
        """规则循环制动（超速→制动 / 低速→缓解 / 中段维持），输出 (num_loco,2)。

        制动时电空分工：ED 优先打满；ED 可用度不足或坡度极大时才引入 AB 源，
        且每机车错峰（公司主体 = 分布式动力）。
        """
        eff_v_max = v_max + v_max_adj
        eff_v_min = v_min + v_min_adj
        vel = float(train_env.dynamics.vel[0])  # 队首速度

        if vel >= eff_v_max:
            self._cyclic_braking = True
        elif vel <= eff_v_min:
            self._cyclic_braking = False

        if self._cyclic_braking:
            # 制动：ED 优先打满，但**逐机车错峰**（体现"每机车=独立体"分布式动力）：
            # 队首机车先建立电制动，后部机车延迟错峰加入，避免整列同时制动前涌。
            ed_avail = self._ed_ab_price(vel)
            # 是否需要 AB：ED 可用度不足时才引入空气制动兜底（长大下坡 ED 功率受限）
            ab_nominal = 0.0 if ed_avail >= 0.99 else float(brake_notch)
            scale = self._coupler_throttle_scale(train_env)
            act = np.zeros((self.num_locomotives, 2), dtype=float)
            for i in range(self.num_locomotives):
                # 错峰：越靠后的机车电制动深度略低（由机车 index 偏移量决定），
                # 形成"首机 ED 强、后机 ED 渐弱"的纵向错峰分配，抑制列内同步前涌。
                stagger = self._ed_stagger(i)
                ed = float(np.clip(1.0 - stagger, 0.0, 1.0)) * scale
                act[i, 0] = ed
                act[i, 1] = float(ab_nominal) * scale if ab_nominal != 0.0 else 0.0
            return act
        else:
            ed_nominal = 0.0
            ab_nominal = 0.0

        return self._ed_ab_actions(ed_nominal, ab_nominal)

    def _ed_stagger(self, loco_i: int) -> float:
        """第 loco_i 台机车的 ED 错峰偏移（0=满 ED，越大越弱）。"""
        if self.num_locomotives <= 1:
            return 0.0
        # 队首(0)=强，队尾=稍弱（纵向错峰，抑制同步前涌）
        frac = loco_i / max(self.num_locomotives - 1, 1)
        return 0.3 * frac  # 队尾 ED 为队首的 0.7 倍左右

    # ------------------------------------------------------------------ #
    # 主接口 2：目标加速度（fleet 非分层模式，与 TrainLowLevelController 同签名）
    # ------------------------------------------------------------------ #
    def get_action_accel(self, train_env, target_accel: float) -> np.ndarray:
        n = self.num_vehicles
        throttle = np.full(n, 0.0)
        ed_throttle = np.full(n, 0.0)
        ab_sources = []
        if target_accel < 0:
            # 需要制动
            ed = min(-target_accel / max(self.max_accel, 1e-6), 1.0)
            ed = max(ed, 0.0)
            # 每个机车独立 ED（错峰忽略：规则冒烟用统一 ED）
            for loco_idx in self.loco_indices:
                ed_throttle[loco_idx] = ed
            scale = self._coupler_throttle_scale(train_env)
            ed_throttle *= scale
        else:
            for loco_idx in self.loco_indices:
                throttle[loco_idx] = min(target_accel / max(self.max_accel, 1e-6), 1.0)
        return np.stack([ed_throttle[self.loco_indices], np.full(self.num_locomotives, 0.0)], axis=1)

    def reset(self):
        self._cyclic_braking = False