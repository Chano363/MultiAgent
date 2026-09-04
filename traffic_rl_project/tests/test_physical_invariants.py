# -*- coding: utf-8 -*-
"""第一锚：物理硬约束测试（不依赖任何外部数据，抓公式/单位/积分器错）。

对应 docs/VALIDATION_BASELINE.md「三层锚验证体系」第一层：
  - 静止不动 / 下坡加速（坡度符号护栏）
  - 平坡惰行能量守恒（阻力做功 ↔ 动能减少，独立计算对照）
  - 恒坡 + 恒电制动稳态速度闭式解（二分法独立求解对照）
  - 阻力线性缩放护栏（防"阻力被总重放大"的历史 bug 复发）
  - 单车退化（n=1 无钩力）
"""

import os
import sys

import numpy as np
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from src.train_dynamics.braking import AirBrakeNotch, electric_brake_force_n
from src.train_dynamics.grade_profile import GradeProfile, GradeSegment
from src.train_dynamics.params import (
    CouplerParams,
    LocomotiveParams,
    TrainConsist,
    VehicleParams,
)
from src.train_dynamics.resistance import resistance_force_n
from src.train_dynamics.rigid_multi_particle import RigidTrain
from src.train_dynamics.train import TrainDynamics

G = 9.8066


def _make_train(n_freight: int = 5, mass_t: float = 100.0):
    consist = TrainConsist(
        [LocomotiveParams()] + [VehicleParams(mass_t=mass_t) for _ in range(n_freight)]
    )
    td = TrainDynamics(consist, coupler=CouplerParams(), dt=0.1)
    return consist, td


# ---------------------------------------------------------------- 1. 静止/加速


def test_rest_stays_still_on_flat():
    """平坡、无牵引、无制动、初速 0、零预载车钩 → 列车必须严格静止。

    护栏：重力/坡度符号错、主动力泄漏、积分器漂移。
    注：默认车钩含 preload_n=2e5 N 预载（MT-2 迟滞特性），静止时会产生有限蠕动，
    该行为由 test_rest_drift_with_default_preload 单独约束；本测试用零预载隔离验证
    "无外力 → 无运动"这一力学恒等式。
    """
    consist = TrainConsist(
        [LocomotiveParams()] + [VehicleParams() for _ in range(5)]
    )
    td = TrainDynamics(
        consist, coupler=CouplerParams(preload_n=0.0, friction_n=0.0), dt=0.1
    )
    n = td.num_vehicles
    pos0 = td.pos.copy()
    for _ in range(1000):  # 100 s
        td.step_vehicles_ed_ab(
            throttle=np.zeros(n), ed_throttle=np.zeros(n), ab_command=None
        )
    assert np.all(td.vel == 0.0), f"平坡静止列车发生移动: vel={td.vel}"
    assert np.allclose(td.pos, pos0), (
        f"平坡静止列车位置漂移: Δpos={td.pos - pos0}"
    )


def test_rest_drift_with_default_preload():
    """默认车钩（含 200 kN 预载）静止蠕动行为记录：100 s 内漂移速度 < 0.1 m/s。

    这是 MT-2 预载模型的可接受特性（预载被钩缓摩擦逐步平衡），
    但必须是有界蠕动而非持续加速。
    """
    _, td = _make_train()
    n = td.num_vehicles
    for _ in range(1000):
        td.step_vehicles_ed_ab(
            throttle=np.zeros(n), ed_throttle=np.zeros(n), ab_command=None
        )
    assert float(np.max(td.vel)) < 0.1, (
        f"默认预载下静止列车蠕动加速: vel_max={np.max(td.vel):.4f} m/s"
    )


def test_downhill_accelerates_from_rest():
    """−10.2‰ 陡坡从静止下滑（无制动）→ 速度单调上升。

    护栏：坡度力方向（负坡度必须产生前进方向助力）。
    注意：这是纯下滑试验，列车放在坡段起点，避免缓坡助力 < 阻力的假阴性。
    """
    _, td = _make_train()
    td.set_grade_profile(GradeProfile(segments=[GradeSegment(0.0, -10.2)]))
    n = td.num_vehicles
    prev_min = 0.0
    for i in range(2000):  # 200 s
        td.step_vehicles_ed_ab(
            throttle=np.zeros(n), ed_throttle=np.zeros(n), ab_command=None
        )
        cur_min = float(np.min(td.vel))
        if i > 100:  # 跳过起步瞬间（阻力建立）
            assert cur_min >= prev_min - 1e-9, (
                f"下坡列车减速了（坡度方向错?）: step={i}, vel_min={cur_min:.3f}"
            )
        prev_min = max(prev_min, cur_min)
    assert float(np.min(td.vel)) > 1.0, "下坡 200s 后仍几乎未加速"


# ---------------------------------------------------------------- 2. 能量守恒


def test_energy_balance_coast_on_flat():
    """平坡惰行：动能减少量 == 阻力做功（阻力用 resistance.py 独立重算）。

    护栏：阻力公式实现、能量记账、积分器耗散。容差 2%。
    """
    consist, td = _make_train(n_freight=5)
    td.set_grade(0.0)
    td.set_initial_speed(20.0)  # m/s
    n = td.num_vehicles

    ke0 = float(np.sum(0.5 * td.masses_kg * td.vel**2))
    work_res = 0.0
    steps = 1500  # 150 s
    for _ in range(steps):
        # 独立计算本步阻力功率（用步初速度，近似半隐式 Euler 的做功口径）
        v_mean = float(np.mean(td.vel))
        f_res = sum(
            resistance_force_n(
                weight_t=v.mass_t,
                no_of_axles=v.no_of_axles,
                frontal_area_m2=v.frontal_area_m2,
                drag_coef=v.drag_coef,
                speed_mps=v_i,
            )
            for v, v_i in zip(consist.vehicles, td.vel)
        )
        work_res += f_res * v_mean * td.dt
        td.step_vehicles_ed_ab(
            throttle=np.zeros(n), ed_throttle=np.zeros(n), ab_command=None
        )

    ke1 = float(np.sum(0.5 * td.masses_kg * td.vel**2))
    delta_ke = ke0 - ke1
    assert delta_ke > 0, "平坡惰行动能应减少"
    rel_err = abs(delta_ke - work_res) / delta_ke
    assert rel_err < 0.02, f"能量守恒破坏: ΔKE={delta_ke/1e3:.1f} kJ, W_res={work_res/1e3:.1f} kJ, 相对误差 {rel_err:.2%}"


# ---------------------------------------------------------------- 3. 稳态闭式解


def _solve_cruise_equilibrium(consist, throttle: float,
                              lo: float = 0.5, hi: float = 40.0) -> float:
    """二分法独立求解平坡稳态巡航速度：F_trac(v) = ΣF_res(v)。

    F_trac(v) = min(η·θ·P/v, 粘着极限)（与 tractive.py 同公式，独立重写）；
    F_res 用 resistance.py。平衡点稳定（v↑ → 牵引↓ 阻力↑）。
    """
    loco = consist.vehicles[0]
    p_eff = getattr(loco, "transmission_efficiency", 0.85) * throttle \
        * getattr(loco, "max_power_kw", 9600) * 1000.0  # W
    f1 = 0.9 * loco.mass_t * 1000.0 * 9.8066  # 粘着极限（tractive.py 默认 μ=0.9）

    def residual(v: float) -> float:
        f_trac = min(p_eff / v, f1)
        f_res = sum(
            resistance_force_n(
                weight_t=veh.mass_t,
                no_of_axles=veh.no_of_axles,
                frontal_area_m2=veh.frontal_area_m2,
                drag_coef=veh.drag_coef,
                speed_mps=v,
            )
            for veh in consist.vehicles
        )
        return f_trac - f_res

    f_lo, f_hi = residual(lo), residual(hi)
    assert f_lo > 0 > f_hi, "residual 在 [lo,hi] 未变号，平衡速度不在区间内"
    for _ in range(80):
        mid = 0.5 * (lo + hi)
        if residual(mid) > 0:
            lo = mid
        else:
            hi = mid
    return 0.5 * (lo + hi)


def test_steady_state_speed_matches_closed_form():
    """平坡 + 恒定牵引手柄 → 稳态巡航速度 ≈ 二分法闭式解（容差 1%）。

    物理说明：功率型牵引 F=P_eff/v 在平坡上的平衡点**稳定**
    （v↑ → 牵引↓ + 阻力↑ → 回缩），因此存在稳态巡航速度；
    而恒坡 + 功率型电制动的平衡点不稳定（v↓ → F=P/v↑ → 刹停），
    不适合做稳态测试。

    护栏：牵引 / 阻力受力的组装与量纲（闭式解由 resistance.py 独立二分求解）。
    """
    consist, td = _make_train(n_freight=5)
    throttle = 0.03
    td.set_grade(0.0)
    td.set_initial_speed(10.0)
    n = td.num_vehicles

    v_prev = float(np.mean(td.vel))
    for _ in range(20000):  # 2000 s，充分收敛
        td.step_vehicles_ed_ab(
            throttle=np.full(n, throttle), ed_throttle=np.zeros(n), ab_command=None
        )
        if int(td.time * 10) % 200 == 0:  # 每 20 s 检查一次时间方向收敛
            v_now = float(np.mean(td.vel))
            if abs(v_now - v_prev) < 1e-4:
                break
            v_prev = v_now

    v_sim = float(np.mean(td.vel))
    v_ref = _solve_cruise_equilibrium(consist, throttle)
    rel = abs(v_sim - v_ref) / v_ref
    assert rel < 0.01, (
        f"稳态巡航速度偏离闭式解: sim={v_sim:.3f} m/s, ref={v_ref:.3f} m/s, rel={rel:.2%}"
    )


# ---------------------------------------------------------------- 4. 阻力护栏


def test_resistance_scales_linearly_with_consist_size():
    """同型车辆线性缩放：n 节编组总阻力 == n × 单节阻力（<1e-6 相对差）。

    护栏：防止"Davis 阻力被总重放大 w 倍"的历史 bug（V 系列已修复）复发。
    轴重/迎风面积同倍放大时，单位阻力必须不变。
    """
    w, axles, area, cd, v = 100.0, 4, 10.0, 1.0, 20.0
    single = resistance_force_n(w, axles, area, cd, v)
    for n in (2, 5, 10):
        bulk = resistance_force_n(w * n, axles * n, area * n, cd, v)
        assert bulk == pytest.approx(n * single, rel=1e-9), (
            f"n={n}: 阻力未线性缩放 bulk={bulk:.1f} N vs {n}*single={n*single:.1f} N"
        )


# ---------------------------------------------------------------- 5. 退化极限


def test_single_vehicle_degenerates_no_coupler():
    """n=1 退化：无车钩断面；且行为与刚性单质点模型一致（平坡惰行 <0.5%）。"""
    consist = TrainConsist([LocomotiveParams()])
    td = TrainDynamics(consist, coupler=CouplerParams(), dt=0.1)
    assert len(td.coupler_interface_forces()) == 0

    rigid = RigidTrain(consist, dt=0.1)
    td.set_initial_speed(20.0)
    rigid.reset(speed_mps=20.0)
    n = td.num_vehicles
    for _ in range(2000):  # 200 s 惰行
        td.step_vehicles_ed_ab(
            throttle=np.zeros(n), ed_throttle=np.zeros(n), ab_command=None
        )
        rigid.step()
    assert td.vel[0] == pytest.approx(rigid.vel, rel=5e-3), (
        f"单车多体 vs 刚性模型速度不一致: {td.vel[0]:.4f} vs {rigid.vel:.4f} m/s"
    )


# ---------------------------------------------------------------- 6. 与刚性模型交叉（第二锚，平坡惰行）


def test_multibody_matches_rigid_model_coast_flat():
    """多体 vs 刚性聚合模型，平坡惰行 200 s：末速相对差 < 0.5%。

    抓：钩力项系统性误差、积分格式漂移、质量组装错。
    """
    consist, td = _make_train(n_freight=5)
    rigid = RigidTrain(consist, dt=0.1)
    td.set_grade(0.0)
    td.set_initial_speed(20.0)
    rigid.reset(speed_mps=20.0)
    n = td.num_vehicles
    for _ in range(2000):
        td.step_vehicles_ed_ab(
            throttle=np.zeros(n), ed_throttle=np.zeros(n), ab_command=None
        )
        rigid.step()
    rel = abs(float(np.mean(td.vel)) - rigid.vel) / rigid.vel
    assert rel < 0.005, f"多体 vs 刚性（平坡惰行）末速差 {rel:.3%}"


def test_multibody_matches_rigid_model_downhill_coast():
    """多体 vs 刚性聚合模型，−10.2‰ 恒坡惰行 200 s：末速相对差 < 0.5%。

    抓：坡度力组装、多体钩力传递的宏观一致性。
    （注：不使用恒电制动——功率型制动在恒坡上的平衡点不稳定，见
    test_steady_state_speed_matches_closed_form 的物理说明。）
    """
    consist, td = _make_train(n_freight=5)
    rigid = RigidTrain(consist, dt=0.1)
    td.set_grade_profile(GradeProfile(segments=[GradeSegment(0.0, -10.2)]))
    td.set_initial_speed(15.0)
    rigid.reset(speed_mps=15.0, grade=-10.2 / 1000.0)
    n = td.num_vehicles
    for _ in range(2000):  # 200 s 下坡加速
        td.step_vehicles_ed_ab(
            throttle=np.zeros(n), ed_throttle=np.zeros(n), ab_command=None
        )
        rigid.step()
    v_sim = float(np.mean(td.vel))
    rel = abs(v_sim - rigid.vel) / rigid.vel
    assert rel < 0.005, f"多体 vs 刚性（恒坡惰行）末速差 {rel:.3%}"
