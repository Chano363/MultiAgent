# -*- coding: utf-8 -*-
"""刚性（聚合质点）列车模型 —— 仿真器交叉验证专用（VALIDATION_BASELINE 第二锚）。

用途
----
与 ``TrainDynamics`` 多体纵向动力学积分器做**同工况交叉对照**（对应赵紫宁 2022 论文
"刚性多质点模型 vs 纵向动力学模型" 的双模型交叉验证思路）。

独立性边界（刻意设计）
----------------------
1. **不 import** ``train.py``（多体积分器）与 ``coupler.py``（钩缓模型）；
2. 受力公式只复用规范层 ``resistance.py`` / ``braking.py``（源头 NeTrainSim / TB1407，
   属于已验证的规范公式层，见 docs/VALIDATION_BASELINE.md V2）；
3. 积分采用最简单的**半隐式 Euler**，便于人工逐步复核。

模型假设
--------
全列聚合为单一质点。在恒定坡度 + 同型车辆 + 稳态空气制动（传播已完成）条件下，
聚合质点与多质点无钩模型的动力学严格等价；与多体带钩模型在**宏观量**
（速度曲线、稳态速度、制动距离）上应一致，瞬时车钩内力则不出现在本模型中。

能抓的 bug 类型：多体积分器符号错、质量组装错、钩力项系统性误差、
坡度力方向错、子步进/积分格式引入的漂移。
"""

from __future__ import annotations

from src.train_dynamics.braking import AirBrakeNotch, air_brake_force_real, electric_brake_force_n

G = 9.8066  # m/s²，与 resistance.py 保持同一重力常数


class RigidTrain:
    """聚合质点列车模型（无车钩力）。"""

    def __init__(self, consist, dt: float = 0.1):
        self.vehicles = list(consist.vehicles)
        self.dt = float(dt)
        self.mass_kg = sum(v.mass_t for v in self.vehicles) * 1000.0
        self.loco_indices = [i for i, v in enumerate(self.vehicles)
                             if getattr(v, "is_locomotive", False)]
        self.grade = 0.0  # 无量纲，正=上坡（与 TrainDynamics 同约定）
        self.vel = 0.0    # m/s
        self.pos = 0.0    # m
        self.time = 0.0   # s
        # 【2026-09-02 P0-2】连续减压量覆盖（None=按 notch 档位默认，见 braking.py）
        self.reduction_kpa = None
        # 【2026-09-02 性能】预计算与速度无关的静态聚合系数（物理等价于逐车求和的
        # Davis 阻力，避免每步对数百辆车重复单位换算）。
        #   R_N = (C0 + C1·mph + C2·mph²) · 4.44822，其中
        #   C0 = Σ (1.5 + 18/axle_w)·w，C1 = 0.03·Σw，C2 = 0.0018·Σ(area_ft·cd)
        c0 = c1 = c2 = 0.0
        self._n_loco = 0
        for v in self.vehicles:
            w = v.mass_t * 1.10231          # 公吨 → 短吨
            c0 += (1.5 + 18.0 / (w / v.no_of_axles)) * w
            c1 += 0.03 * w
            c2 += 0.0018 * (v.frontal_area_m2 * 10.7639) * v.drag_coef
            if getattr(v, "is_locomotive", False):
                self._n_loco += 1
        self._res_c0 = c0
        self._res_c1 = c1
        self._res_c2 = c2
        self._n_freight = len(self.vehicles) - self._n_loco

    # ------------------------------------------------------------------ state
    def reset(self, speed_mps: float = 0.0, position_m: float = 0.0,
              grade: float = 0.0) -> None:
        self.vel = float(speed_mps)
        self.pos = float(position_m)
        self.grade = float(grade)
        self.time = 0.0

    def set_grade(self, grade_dimensionless: float) -> None:
        self.grade = float(grade_dimensionless)

    # ------------------------------------------------------------------ forces
    def _resistance_n(self, speed_mps: float) -> float:
        """全列基本运行阻力（Davis，聚合系数预计算，逐车求和物理等价）。

        逐车公式 R_N = (1.5 + 18/axle_w + 0.03·mph)·w + 0.0018·area_ft·cd·mph²
        对速度无关项求和即 R_N = (C0 + C1·mph + C2·mph²)·4.44822（见 __init__）。
        """
        mph = speed_mps * 2.23694
        return (self._res_c0 + self._res_c1 * mph + self._res_c2 * mph * mph) * 4.44822

    def _electric_brake_n(self, speed_mps: float, ed_throttle: float) -> float:
        """机车电制动力（N，减速方向为正）。仅机车有电制动。"""
        if not self.loco_indices or ed_throttle <= 0.0:
            return 0.0
        loco = self.vehicles[self.loco_indices[0]]
        f = electric_brake_force_n(
            mass_t=loco.mass_t,
            speed_mps=speed_mps,
            throttle_ed=ed_throttle,
            max_power_kw=getattr(loco, "max_power_kw", 9600),
        )
        return float(f)

    def _air_brake_n(self, speed_mps: float, notch: AirBrakeNotch | None) -> float:
        """全列空气制动力（N，减速方向为正）。稳态当量，无传播延迟。

        牵规 β_c 法单节制动力只由减速量/速度/闸瓦类型决定（与车重无关），
        机车与货车当前 K_h 相同 → 全列制动力 = 车数 × 单节制动力（机车单独计，
        便于未来 K_h 差异化）。
        """
        if notch is None or notch == AirBrakeNotch.RELEASE:
            return 0.0
        total = 0.0
        if self._n_loco:
            total += self._n_loco * air_brake_force_real(
                speed_mps=speed_mps, notch=notch, is_locomotive=True,
                reduction_kpa=self.reduction_kpa)
        if self._n_freight:
            total += self._n_freight * air_brake_force_real(
                speed_mps=speed_mps, notch=notch, is_locomotive=False,
                reduction_kpa=self.reduction_kpa)
        return total

    # ------------------------------------------------------------------- step
    def _accel(self, v: float, ed_throttle: float, ab_notch) -> float:
        """给定速度下的加速度（前进方向为正）。

            a = (F_grade − F_ed − F_ab − F_res) / M
        下坡 grade<0 时 F_grade = M·g·(−grade) > 0 为助力。
        """
        f_grade = self.mass_kg * G * (-self.grade)
        f_ed = self._electric_brake_n(v, ed_throttle)
        f_ab = self._air_brake_n(v, ab_notch)
        f_res = self._resistance_n(v)
        return (f_grade - f_ed - f_ab - f_res) / self.mass_kg

    def step(self, ed_throttle: float = 0.0,
             ab_notch: AirBrakeNotch | None = None) -> float:
        """前进一步（RK4 积分），返回本步加速度（m/s²）。

        积分器说明：RK4 四阶精度，dt=0.1 s 下数百秒长时程累积漂移 <0.01%，
        可作多体 Newmark-β 积分器的独立参照。（半隐式 Euler 为一阶方法，
        长时程惰行会系统性高估减速 ~9%，不能做交叉基准——实测教训。）

        静止条件：v=0 且坡度助力 ≤ 基本阻力时保持静止。
        """
        h = self.dt
        v0 = self.vel

        if v0 <= 1e-9:
            f_drive = self.mass_kg * G * (-self.grade)
            f_res0 = self._resistance_n(0.0)
            if f_drive <= f_res0:
                self.time += h
                return 0.0

        k1 = self._accel(v0, ed_throttle, ab_notch)
        k2 = self._accel(max(0.0, v0 + 0.5 * h * k1), ed_throttle, ab_notch)
        k3 = self._accel(max(0.0, v0 + 0.5 * h * k2), ed_throttle, ab_notch)
        v4 = max(0.0, v0 + h * k3)
        k4 = self._accel(v4, ed_throttle, ab_notch) if v4 > 0 else 0.0

        dv = h / 6.0 * (k1 + 2 * k2 + 2 * k3 + k4)
        v_new = max(0.0, v0 + dv)
        x_new = self.pos + h * (v0 + 2 * max(0.0, v0 + 0.5 * h * k1)
                                + 2 * max(0.0, v0 + 0.5 * h * k2) + v_new) / 6.0

        self.vel = v_new
        self.pos = x_new
        self.time += h
        return k1
