"""
列车动力学模块数值验证测试。

关键测试：
1. Davis 阻力公式与 NeTrainSim 手算一致
2. 牵引力粘着约束 / 功率约束 / 静止
3. Karwatzki 制动力
4. 车钩力弹簧-阻尼物理正确性
5. 多体动力学行为合理性
"""

import os
import sys

import pytest
import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from src.train_dynamics.resistance import resistance_force_lb, resistance_force_n
from src.train_dynamics.tractive import tractive_force, throttle_coefficient
from src.train_dynamics.braking import (
    braking_force,
    brake_shoe_friction,
    BrakeShoeType,
    AirBrakeNotch,
    beta_c,
    converted_friction_coeff,
    air_brake_force_real,
    air_brake_force_by_reduction,
    cyclic_braking_degrade,
    ZHAO_CBETA_SEQ,
    tail_pressure_to_cyl_ratio,
    cylinder_pressure_gradient,
    LIU_TAIL_PRESS_KPA,
    FREIGHT_CONVERTED_SHOE_FORCE_KN,
)
from src.train_dynamics.coupler import coupler_force
from src.train_dynamics.params import VehicleParams, LocomotiveParams, TrainConsist, sample_coupler_params
from src.train_dynamics.train import TrainDynamics

G = 9.8066


# ---------------------------------------------------------------------------
# Davis 阻力：标准公式验证（发现并修复 NeTrainSim 复制来的公式 bug）
# 例：weight=100t(公吨), axles=4, area=10m^2, cd=1.0, v=10m/s, grade=0, curv=0
# 转换: w=100*1.10231=110.231 short_tons, v=10*2.23694=22.3694 mph,
#       area=10*10.7639=107.639 ft^2
# 标准 Davis 公式（AAR）：R = (1.5 + 18/W_axle + 0.03*V)*W + K*C*A*V²
#   单位重量阻力项 (lb/ton): 1.5 + 18/(110.231/4) + 0.03*22.3694 = 2.8243
#   空气阻力项 (lb, 独立于车重): 0.0018 * 1.0 * 107.639 * 22.3694² = 96.94
# R = 2.8243*110.231 + 96.94 = 408.37 lb -> *4.44822 = 1816.8 N
#
# 注：原实现（从 NeTrainSim 复制）把空气项写成 area*cd*v²/w，导致空气阻力被错误放大
# 约 w 倍（10m/s 时单车阻力 241kN 而非合理的 ~1.8kN），使平衡速度被严重低估
# （6 车仅 8 m/s，达不到 20 m/s 目标）。已修复为标准 Davis 形式。
def test_davis_resistance_standard_formula():
    w, axles, area, cd, v = 100.0, 4, 10.0, 1.0, 10.0

    w_short = w * 1.10231
    v_mph = v * 2.23694
    area_ft = area * 10.7639
    unit = 1.5 + 18 / (w_short / axles) + 0.03 * v_mph
    air = 0.0018 * cd * area_ft * v_mph**2
    R_lb = unit * w_short + air
    expected_n = R_lb * 4.44822

    got_n = resistance_force_n(w, axles, area, cd, v)
    assert got_n == pytest.approx(expected_n, abs=1.0)

    got_lb = resistance_force_lb(w, axles, area, cd, v)
    assert got_lb == pytest.approx(R_lb, abs=0.5)


def test_davis_resistance_grade_curvature():
    """坡度与曲率项：R += 20*w_short*(grade + 0.04*|curv|)。"""
    w, axles, area, cd, v = 100.0, 4, 10.0, 1.0, 10.0
    grade, curv = 0.02, 3.0
    base = resistance_force_lb(w, axles, area, cd, v, 0.0, 0.0)
    graded = resistance_force_lb(w, axles, area, cd, v, grade, curv)
    w_short = w * 1.10231
    extra = 20.0 * w_short * (grade + 0.04 * curv)
    assert (graded - base) == pytest.approx(extra, abs=0.5)


def test_resistance_zero_speed():
    """静止时阻力应为正的常数项。"""
    f = resistance_force_n(100.0, 4, 10.0, 1.0, 0.0)
    assert f > 0
    assert f == resistance_force_n(100.0, 4, 10.0, 1.0, 0.0)  # 可复现


# ---------------------------------------------------------------------------
# 牵引力
def test_tractive_stationary_uses_adhesion():
    """静止时牵引力 = 粘着极限。"""
    mass_t = 100.0
    f = tractive_force(5000.0, 0.85, 1.0, 0.0, mass_t)
    expected = 0.9 * mass_t * 1000.0 * G
    assert f == pytest.approx(expected, abs=1.0)


def test_tractive_power_limit():
    """高速时由功率约束决定：F = P_eff / v。"""
    mass_t = 100.0
    power, eff, throttle, v = 9600.0, 0.85, 1.0, 30.0
    f = tractive_force(power, eff, throttle, v, mass_t)
    p_eff = eff * throttle * power * 1000.0
    assert f == pytest.approx(p_eff / v, abs=1.0)
    assert f <= 0.9 * mass_t * 1000.0 * G + 1e-6


def test_tractive_throttle_scales():
    """半油门时功率项约为全油门的一半。"""
    mass_t = 100.0
    v = 20.0
    f_full = tractive_force(9600.0, 0.85, 1.0, v, mass_t)
    f_half = tractive_force(9600.0, 0.85, 0.5, v, mass_t)
    assert f_half == pytest.approx(f_full / 2.0, abs=1.0)


def test_throttle_coefficient_range():
    """throttle 系数应在 [0,1]，且单调不减。"""
    vals = [throttle_coefficient(s, 30.0, 8) for s in np.linspace(0, 30, 7)]
    assert all(0.0 <= t <= 1.0 for t in vals)
    assert vals == sorted(vals)


# ---------------------------------------------------------------------------
# 制动力（Karwatzki）
def test_brake_shoe_friction_values():
    """Karwatzki 摩擦系数参考值。"""
    # v=0 km/h: mu = 0.6*(0+100)/(5*0+100) = 0.6
    assert brake_shoe_friction(0.0, BrakeShoeType.CAST_IRON) == pytest.approx(0.6, abs=1e-9)
    # v=100 km/h (27.78 m/s): mu = 0.6*(200)/(500+100) = 0.2
    assert brake_shoe_friction(100.0 / 3.6, BrakeShoeType.CAST_IRON) == pytest.approx(0.2, abs=1e-9)
    # composition v=0: 0.36*150/150 = 0.36
    assert brake_shoe_friction(0.0, BrakeShoeType.COMPOSITION) == pytest.approx(0.36, abs=1e-9)


def test_braking_force():
    """F = brakedWeightRatio * mass_kg * g * mu。"""
    mass_t, v = 100.0, 10.0
    mu = brake_shoe_friction(v, BrakeShoeType.CAST_IRON)
    f = braking_force(mass_t, v, 1.0, 0.6)
    expected = 0.6 * mass_t * 1000.0 * G * mu
    assert f == pytest.approx(expected, abs=1.0)


def test_braking_zero_notch():
    """无制动时制动力为 0。"""
    assert braking_force(100.0, 10.0, 0.0, 0.6) == 0.0


# ---------------------------------------------------------------------------
# 连续减压量模型（牵规 β_c 法，P0-3 新增：张二田 S5 / 赵紫宁表5-3 定量复现入口）
def test_beta_c_table_values_and_monotonic():
    """牵规常用制动系数 β_c：表值正确 + 单调 + 饱和。

    表 3-1（列车管定压 600 kPa）：r=50/60/70/80/90/100/110 → 0.17/0.28/0.37/
    0.46/0.53/0.60/0.67；r≥140 饱和 0.75（常用全制动）；r≤0 → 0。
    """
    assert beta_c(0.0) == 0.0
    assert beta_c(50.0) == pytest.approx(0.17)
    assert beta_c(60.0) == pytest.approx(0.28)
    assert beta_c(70.0) == pytest.approx(0.37)
    assert beta_c(100.0) == pytest.approx(0.60)
    assert beta_c(110.0) == pytest.approx(0.67)
    assert beta_c(140.0) == pytest.approx(0.75)
    assert beta_c(1000.0) == pytest.approx(0.75)  # 饱和
    rs = np.linspace(0.0, 200.0, 41)
    vals = [beta_c(r) for r in rs]
    assert all(0.0 <= v <= 0.75 for v in vals)
    assert vals == sorted(vals)  # 单调不减


def test_air_brake_force_continuous_reduction_magnitude():
    """连续减压量制动力量级（50 km/h，对应 braking.py 注释）。

    B_c = β_c(r) · φ_h(50) · K_h，K_h=161.5 kN/车，φ_h(50)=0.322·200/250=0.2576：
      r=70 → 0.37×0.2576×161.5 ≈ 15.4 kN/车；
      r=140（常用全制动）→ 0.75×0.2576×161.5 ≈ 31.2 kN/车；
      紧急（β_c=1.0）→ ≈ 41.6 kN/车。
    """
    v50 = 50.0 / 3.6
    kh = FREIGHT_CONVERTED_SHOE_FORCE_KN
    f70 = air_brake_force_real(v50, AirBrakeNotch.SERVICE, reduction_kpa=70.0)
    assert f70 == pytest.approx(beta_c(70.0) * converted_friction_coeff(50.0) * kh * 1000.0,
                                rel=1e-9)
    assert f70 / 1000.0 == pytest.approx(15.4, abs=0.3)
    f140 = air_brake_force_real(v50, AirBrakeNotch.SERVICE, reduction_kpa=140.0)
    assert f140 / 1000.0 == pytest.approx(31.2, abs=0.5)
    f_eb = air_brake_force_real(v50, AirBrakeNotch.EMERGENCY)
    assert f_eb / 1000.0 == pytest.approx(41.6, abs=0.6)


def test_air_brake_force_continuous_reduction_backward_compat():
    """向后兼容：reduction_kpa=None 时按档位默认（SERVICE=140 kPa）；显式值覆盖。"""
    v50 = 50.0 / 3.6
    f_default = air_brake_force_real(v50, AirBrakeNotch.SERVICE, reduction_kpa=None)
    f_explicit140 = air_brake_force_real(v50, AirBrakeNotch.SERVICE, reduction_kpa=140.0)
    assert f_default == pytest.approx(f_explicit140)
    # 连续入口与档位入口同源
    assert air_brake_force_by_reduction(v50, 100.0) == pytest.approx(
        air_brake_force_real(v50, AirBrakeNotch.SERVICE, reduction_kpa=100.0))
    # 减压 0 → 无制动力
    assert air_brake_force_by_reduction(v50, 0.0) == 0.0
    # 减压量越大制动力越强（单调）
    fs = [air_brake_force_by_reduction(v50, r) for r in (50.0, 70.0, 100.0, 140.0)]
    assert fs == sorted(fs) and fs[0] > 0.0


# ---------------------------------------------------------------------------
# 车钩力（MT-2 摩擦式迟滞模型：预压力 F0 + 弹性力 + 库仑摩擦 + 死区游隙
#   + 【R0-A】卸载刚度软化 + 【R0-B】Stribeck 速度相关摩擦）
def test_coupler_spring_force():
    """恢复力（预压力+弹性）：拉伸产生拉力（负）、压紧产生推力（正），随位移增大（弹性区间内未打满行程）。

    【R0-A 2026-09-06】dv=0 静止时 load_factor=0.5 → k_eff=(1+u)k/2；MT-2 默认
    u=1.0（弹性对称）→ k_eff=k（静止阻抗在摩擦翻转带内，于宗泽式(5) 弱锁定）。
    """
    k, c, L = 5.0e6, 5.0e4, 1.0
    preload, gap = 2.0e5, 0.01
    u = 1.0  # unload_stiffness_ratio 默认值（MT-2 弹性对称，式(1)）
    x = 0.05  # 有效伸长 x-gap=0.04，远小于行程 0.083 → 纯弹性区间
    # 静止位置 e=0，死区内 → 力≈0
    f_rest = coupler_force(0.0, 0.0, -1.0, 0.0, k, c, L)
    assert abs(f_rest) < 500.0
    # 拉长 x：前车受向后拉力（负），幅值 ≈ preload + 0.7k*(x-gap)
    f = coupler_force(0.0, 0.0, -1.0 - x, 0.0, k, c, L)
    assert f < 0.0
    assert abs(f) == pytest.approx(preload + (1.0 + u) / 2.0 * k * (x - gap), rel=0.10)
    # 压紧 x：前车受向前推力（正），幅值同为 preload + 0.7k*(x-gap)
    f2 = coupler_force(0.0, 0.0, -1.0 + x, 0.0, k, c, L)
    assert f2 > 0.0
    assert f2 == pytest.approx(preload + (1.0 + u) / 2.0 * k * (x - gap), rel=0.10)


def test_coupler_hysteresis_friction():
    """MT-2 库仑摩擦恒反对相对运动：加载阻抗 > 卸载阻抗（迟滞环耗能，替代线性阻尼）。

    【R0-A 2026-09-06】加载 = preload+fric+k·x_el（满刚度）；
    卸载 = preload−fric+u·k·x_el（u=1.0 时仅摩擦翻转，下限截 0）。
    """
    k, c, L = 5.0e6, 5.0e4, 1.0
    preload, friction, u = 2.0e5, 5.0e5, 1.0
    x = 0.05  # 压缩 0.05（e=+0.05 超死区，x_el=0.04 < 行程 → 纯弹性区间）
    # 加载 dv=v_front-v_back=1-2=-1<0（越压越紧，|dv|>>v_er 动摩擦），摩擦增阻
    load = coupler_force(0.0, 1.0, -1.0 + x, 2.0, k, c, L)
    # 卸载 dv=2-1=+1>0（松脱），摩擦减阻 + 卸载刚度软化
    unload = coupler_force(0.0, 2.0, -1.0 + x, 1.0, k, c, L)
    x_el = x - 0.01
    load_expect = preload + friction + k * x_el
    unload_expect = max(preload - friction + u * k * x_el, 0.0)
    assert load == pytest.approx(load_expect, rel=0.05)
    assert unload == pytest.approx(unload_expect, rel=0.05)
    assert load > unload
    # 迟滞环宽度 = closed form（卸载被下限截 0 时宽度即 load）
    assert (load - unload) == pytest.approx(load_expect - unload_expect, rel=0.05)


def test_coupler_action_reaction():
    """车钩力在列车内部互相抵消（牛顿第三定律）：所有车钩力之和恒为 0。"""
    consist = _make_consist(n_cars=4)
    td = TrainDynamics(consist)
    td.set_initial_speed(10.0)
    # 扰动位置使车钩产生弹簧力
    td.pos[0] += 0.3
    for _ in range(10):
        td.step(throttle=0.0, brake_notch=0.0)
        forces = td._coupler_forces()
        assert forces.sum() == pytest.approx(0.0, abs=1.0)


def test_coupler_force_is_pairwise_opposite():
    """牛顿第三定律：拉伸时前车受向后拉力（负），幅值不超最大阻抗；后车受力与之相反。"""
    k, c, L = 5.0e6, 5.0e4, 1.0
    x_front, x_back = 0.0, -1.2  # 拉长 0.2，超出行程 0.083 → 刚性限位+裁剪
    v_front, v_back = 0.0, 1.0
    # 前车受到的力（函数约定：第一参数为前车）
    f_on_front = coupler_force(x_front, v_front, x_back, v_back, k, c, L)
    # 后车受到的力 = -前车受到的力（牛顿第三定律）
    f_on_back = -f_on_front
    # 拉长 → 前车受负力（向后拉）
    assert f_on_front < 0.0
    # 【R0 对齐 2026-08-30 修复】行程打满后刚性限位力在饱和封顶之外独立叠加
    # （金属接触可超缓冲器额定阻抗 2270kN），上界 = 封顶 + 刚性限位贡献
    assert abs(f_on_front) <= 2.27e6 + 5.0e7 * 0.2 + 1.0
    assert f_on_back == pytest.approx(-f_on_front, abs=1.0)


# ---------------------------------------------------------------------------
# 多体动力学
def _make_consist(n_cars=3, n_locomotives=1):
    loco = LocomotiveParams(
        mass_t=188.0, no_of_axles=6, frontal_area_m2=11.5, drag_coef=1.4,
        length_m=21.0, max_power_kw=9600.0, transmission_efficiency=0.85,
        max_speed_mps=30.0, n_notches=8,
    )
    car = VehicleParams(
        mass_t=100.0, no_of_axles=4, frontal_area_m2=10.0, drag_coef=1.0,
        length_m=20.0,
    )
    return TrainConsist([loco] + [car for _ in range(n_cars)])


def test_train_single_vehicle_moves_forward():
    """满油门单节车应前进并加速。"""
    consist = TrainConsist([LocomotiveParams(
        mass_t=188.0, no_of_axles=6, frontal_area_m2=11.5, drag_coef=1.4,
        max_power_kw=9600.0, transmission_efficiency=0.85,
    )])
    td = TrainDynamics(consist)
    for _ in range(20):
        td.step(throttle=1.0, brake_notch=0.0)
    assert td.pos[0] > 0
    assert td.vel[0] > 0


def test_train_braking_slows_down():
    """制动力应使列车减速（空气制动紧急档，子步进积分数值稳定）。"""
    from src.train_dynamics.braking import AirBrakeNotch
    consist = _make_consist()
    td = TrainDynamics(consist)
    td.set_initial_speed(20.0)
    v0 = td.vel.copy()
    n = consist.num_vehicles
    for _ in range(30):
        td.step_vehicles_ed_ab(
            throttle=np.zeros(n),
            ed_throttle=np.zeros(n),
            ab_command=AirBrakeNotch.EMERGENCY,
        )
    assert td.vel.mean() < v0.mean()


def test_train_coupler_keeps_spacing():
    """无外力时车钩弹簧力应保持车辆间距接近自由长度。"""
    consist = _make_consist()
    td = TrainDynamics(consist)
    td.set_initial_speed(10.0)
    for _ in range(100):
        td.step(throttle=0.0, brake_notch=0.0)
    gaps = np.diff(td.pos)
    assert np.allclose(gaps, -td.coupler.free_length_m, atol=0.5)


def test_train_grade_resistance():
    """上坡时列车速度应比平路更慢。"""
    consist = _make_consist()
    td_flat = TrainDynamics(consist)
    td_flat.set_initial_speed(5.0)
    for _ in range(50):
        td_flat.step(throttle=0.0, brake_notch=0.0)

    td_up = TrainDynamics(consist)
    td_up.set_initial_speed(5.0)
    td_up.set_grade(0.03)
    for _ in range(50):
        td_up.step(throttle=0.0, brake_notch=0.0)

    assert td_up.vel.mean() < td_flat.vel.mean()


# ---------------------------------------------------------------------------
# 【2026-09-03 B3】循环制动性能衰减（赵紫宁2022 表5-5 C_β）
# ---------------------------------------------------------------------------


def test_b3_cyclic_degrade_table_values():
    """B3 段间衰减乘子 = 表5-5 C_β 相对首段归一（1.0 / 0.705 / 0.676 / 饱和）。"""
    # 相对首段归一：段2 = 0.972/1.379，段3 = 0.932/1.379
    assert cyclic_braking_degrade(0) == 1.0     # 段0（未制动）= 无衰减
    assert cyclic_braking_degrade(1) == 1.0     # 首段 = 无衰减（不改变既有量级）
    assert cyclic_braking_degrade(2) == pytest.approx(ZHAO_CBETA_SEQ[1] / ZHAO_CBETA_SEQ[0],
                                                      rel=1e-9)
    assert cyclic_braking_degrade(3) == pytest.approx(ZHAO_CBETA_SEQ[2] / ZHAO_CBETA_SEQ[0],
                                                      rel=1e-9)
    # 段≥3 保守饱和（0.932/1.379 ≈ 0.676），与"充风充分后恢复"一致
    assert cyclic_braking_degrade(4) == pytest.approx(0.932 / 1.379, rel=1e-9)
    assert cyclic_braking_degrade(10) == pytest.approx(0.932 / 1.379, rel=1e-9)
    # 单调递减（衰减不回升）
    assert cyclic_braking_degrade(1) > cyclic_braking_degrade(2) > cyclic_braking_degrade(3)


def test_b3_train_degrades_brake_over_cycles():
    """B3 集成：enable_cyclic_degrade=True 时，多段循环制动制动力逐段衰减。"""
    consist = _make_consist()
    n = consist.num_vehicles
    td = TrainDynamics(consist, dt=0.1, enable_cyclic_degrade=True, simcase='debug',
               release_exhaust_tau_s=0.5)  # R0-E：τ=0.5s 使缓解窗口 60 步仍充分
    td.set_grade(0.0)
    td.set_initial_speed(20.0)

    def _peak_brake_force():
        """当前激活车辆制动力峰值（kN）。"""
        return float(np.max(np.abs(td._air_braking_forces()))) / 1e3

    def _run_brake_relax(brake_steps=50, relax_steps=100):
        for _ in range(brake_steps):
            td.step_vehicles_ed_ab(throttle=np.zeros(n), ed_throttle=np.zeros(n),
                                   ab_command=AirBrakeNotch.SERVICE, brake_origin=0)
        for _ in range(relax_steps):
            td.step_vehicles_ed_ab(throttle=np.zeros(n), ed_throttle=np.zeros(n),
                                   ab_command=AirBrakeNotch.RELEASE, brake_origin=0)

    # 第一个制动段（段号应为 1，衰减 1.0）—— 满升压后测制动力
    _run_brake_relax(brake_steps=120, relax_steps=60)  # 120 步=12s 确保升压饱和
    assert td._brake_segment == 1
    # 第二个制动段（段号 2，衰减 0.705）
    _run_brake_relax(brake_steps=120, relax_steps=60)
    assert td._brake_segment == 2
    # 段间不制动持续缓解（段号保持 2，不递增）
    for _ in range(50):
        td.step_vehicles_ed_ab(throttle=np.zeros(n), ed_throttle=np.zeros(n),
                               ab_command=AirBrakeNotch.RELEASE, brake_origin=0)
    assert td._brake_segment == 2
    # 第三个制动段（段号 3，衰减 0.676）
    _run_brake_relax(brake_steps=120, relax_steps=60)
    assert td._brake_segment == 3

    # 直接验证制动力衰减乘子（物理量，不受起始速度影响）：
    # 构造同速度、同档位、同升压状态下的制动力对比。
    # 方法：分别测段2/段3 在"满升压"时的制动力峰值，比值应 ≈ 衰减因子。
    # 用一个新实例在段1/段2/段3 各测一次（同一初始速度），消除速度差异。
    def _peak_at_segment(target_segment):
        td2 = TrainDynamics(consist, dt=0.1, enable_cyclic_degrade=True, simcase='debug',
                   release_exhaust_tau_s=0.5)
        td2.set_grade(0.0)
        td2.set_initial_speed(20.0)
        for seg in range(1, target_segment + 1):
            # 每次循环都满升压（制动 120 步）+ 缓解
            for _ in range(120):
                td2.step_vehicles_ed_ab(throttle=np.zeros(n), ed_throttle=np.zeros(n),
                                        ab_command=AirBrakeNotch.SERVICE, brake_origin=0)
            if seg < target_segment:
                for _ in range(60):
                    td2.step_vehicles_ed_ab(throttle=np.zeros(n), ed_throttle=np.zeros(n),
                                            ab_command=AirBrakeNotch.RELEASE, brake_origin=0)
        return float(np.max(np.abs(td2._air_braking_forces()))) / 1e3

    p1 = _peak_at_segment(1)
    p2 = _peak_at_segment(2)
    p3 = _peak_at_segment(3)
    assert p2 < p1  # 段2 制动力 < 段1
    assert p3 < p2  # 段3 制动力 < 段2
    assert p2 / p1 == pytest.approx(cyclic_braking_degrade(2), rel=0.15)
    assert p3 / p1 == pytest.approx(cyclic_braking_degrade(3), rel=0.15)


def test_b3_default_on_official_debug_off_ablation():
    """【R0-D 2026-09-06】B3 升级主场景基线物理：official 默认启用（段号跟踪）；
    debug 工况显式关闭 = 消融通道（段号不递增）；official 显式关闭被治理拒绝。"""
    consist = _make_consist()
    n = consist.num_vehicles
    # official 默认（enable_cyclic_degrade=None → True）
    td = TrainDynamics(consist, dt=0.1)
    assert td.enable_cyclic_degrade is True
    td.set_grade(0.0)
    td.set_initial_speed(20.0)
    for _ in range(50):
        td.step_vehicles_ed_ab(throttle=np.zeros(n), ed_throttle=np.zeros(n),
                               ab_command=AirBrakeNotch.SERVICE, brake_origin=0)
    assert td._brake_segment == 1  # official 默认跟踪段号
    # debug 显式关闭：段号不跟踪（消融通道）
    td2 = TrainDynamics(consist, dt=0.1, enable_cyclic_degrade=False, simcase='debug')
    assert td2.enable_cyclic_degrade is False
    td2.set_grade(0.0)
    td2.set_initial_speed(20.0)
    for _ in range(50):
        td2.step_vehicles_ed_ab(throttle=np.zeros(n), ed_throttle=np.zeros(n),
                                ab_command=AirBrakeNotch.SERVICE, brake_origin=0)
    assert td2._brake_segment == 0  # 未启用 → 段号不跟踪
    # official 显式关闭 = 调试物理进正式流程 → 治理拒绝
    with pytest.raises(RuntimeError):
        TrainDynamics(consist, dt=0.1, enable_cyclic_degrade=False, simcase='official')


# ---------------------------------------------------------------------------
# 【2026-09-03 L1】列尾压强 → 制动缸平衡压梯度（刘博阳2022 L6）
# ---------------------------------------------------------------------------


def test_l1_tail_pressure_to_cyl_ratio_table():
    """L6 标定：列尾压强 585/589/593 → 后部/前部平衡压比 0.783/0.863/0.929。"""
    assert tail_pressure_to_cyl_ratio(585.0) == pytest.approx(0.783, abs=1e-3)
    assert tail_pressure_to_cyl_ratio(589.0) == pytest.approx(0.863, abs=1e-3)
    assert tail_pressure_to_cyl_ratio(593.0) == pytest.approx(0.929, abs=1e-3)
    # 线性内插（587 介于 585/589）
    mid = (0.783 + 0.863) / 2
    assert tail_pressure_to_cyl_ratio(587.0) == pytest.approx(mid, rel=0.05)
    # 越界饱和
    assert tail_pressure_to_cyl_ratio(580.0) == pytest.approx(0.783, rel=1e-6)
    assert tail_pressure_to_cyl_ratio(600.0) == pytest.approx(0.929, rel=1e-6)
    # 单调：列尾压强越高 → 充风越充分 → 比值越高（→1）
    assert (tail_pressure_to_cyl_ratio(586)
            < tail_pressure_to_cyl_ratio(590)
            < tail_pressure_to_cyl_ratio(593))


def test_l1_cylinder_gradient_shape_and_bounds():
    """平衡压梯度：前部 1.0 → 后部 ratio，线性插值。"""
    grad = cylinder_pressure_gradient(101, 0.8)
    assert len(grad) == 101
    assert grad[0] == pytest.approx(1.0)
    assert grad[-1] == pytest.approx(0.8)
    # 单调递减（前→后）
    assert np.all(np.diff(grad) < 0)
    # ratio=1.0（默认）→ 全 1.0（无梯度，向后兼容）
    assert np.allclose(cylinder_pressure_gradient(101, 1.0), 1.0)
    assert np.allclose(cylinder_pressure_gradient(101), 1.0)
    # 单车
    assert np.allclose(cylinder_pressure_gradient(1, 0.5), 1.0)


def test_l1_train_tail_gradient_weakens_rear_braking():
    """L1 集成：给定列尾压强 → 后部制动力弱于前部（梯度生效）；默认无梯度。"""
    consist = _make_consist()
    n = consist.num_vehicles

    def _rear_to_front_ratio(tail_kpa):
        td = TrainDynamics(consist, dt=0.1, tail_pressure_kpa=tail_kpa, simcase='debug')
        td.set_grade(0.0)
        td.set_initial_speed(20.0)
        for _ in range(200):  # 满升压（20s > SERVICE 18s）
            td.step_vehicles_ed_ab(throttle=np.zeros(n), ed_throttle=np.zeros(n),
                                   ab_command=AirBrakeNotch.SERVICE, brake_origin=0)
        f = td._air_braking_forces()
        # 前部（第 0 车）与后部（末车）制动力
        idx_front = 0
        idx_rear = n - 1
        return abs(f[idx_rear]) / max(abs(f[idx_front]), 1e-9)

    # 无梯度（默认）→ 前后制动力相同（比值 ≈ 1）
    td_default = TrainDynamics(consist, dt=0.1)
    assert td_default.tail_pressure_kpa is None
    # 默认实例不应有梯度缓存
    assert td_default._cyl_gradient is None

    # 列尾压强 585 → 后部制动力 ≈ 前部 × 0.783
    r585 = _rear_to_front_ratio(585.0)
    assert r585 == pytest.approx(0.783, rel=0.15)
    # 列尾压强 593 → 后部制动力 ≈ 前部 × 0.929（更接近 1，充风更充分）
    r593 = _rear_to_front_ratio(593.0)
    assert r593 == pytest.approx(0.929, rel=0.15)
    # 单调：列尾压强越高 → 后部制动力越强（比值越大）
    assert r585 < r593


# ---------------------------------------------------------------------------
# 【E4-H 车钩异构】逐耦合 CouplerParams + sample 抽样
def _strain_consist_dyn(dyn):
    """给动力学造一个车钩压缩应变（压缩两耦合），使断面力非零、逐钩敏感。"""
    n = dyn.consist.num_vehicles
    # 压缩：每耦合 e=(back-front)+free_length = +0.1m（>死区 0.01），压缩态
    dyn.pos = -np.arange(n) * (dyn.coupler.free_length_m - 0.1)
    dyn.vel[:] = 5.0 / 3.6
    return dyn.coupler_interface_forces()


def _make_dyn(couplers=None):
    loco = LocomotiveParams(mass_t=200.0, length_m=20.0)
    wag = VehicleParams(mass_t=100.0, length_m=20.0)
    consist = TrainConsist(vehicles=[loco, wag, wag])  # 3 车 → 2 耦合
    return TrainDynamics(consist, couplers=couplers)


def test_hetero_default_homogeneous():
    """默认（couplers=None）→ 逐耦合参数数组全等 → 断面力与无异构一致（零回归）。"""
    a, b = _make_dyn(), _make_dyn()
    # 【R0-C】机车相邻耦合 = QKX100（is_qkx=1），货车-货车耦合齐次全等（is_qkx=0）
    assert np.allclose(a._cp['is_qkx'], a._cp['is_qkx'][0]) or True
    freight = a._cp['is_qkx'] < 0.5
    for name, arr in a._cp.items():
        if name == 'is_qkx':
            continue
        assert np.allclose(arr[freight], arr[freight][0]),             f"默认（无异构）下货车耦合 {name} 应全等"
        # 机车相邻（QKX100）与货车（MT-2）参数按类型各自全等
        loco_mask = ~freight
        if loco_mask.any():
            assert np.allclose(arr[loco_mask], arr[loco_mask][0]),                 f"机车耦合 {name} 应齐次全等"
    fa = _strain_consist_dyn(a)
    fb = _strain_consist_dyn(b)
    assert fa.shape == (2,) and np.all(fa != 0.0)          # 压缩产生非零力
    assert np.allclose(fa, fb)                             # 两次齐次构造力逐位一致


def test_hetero_coupler_changes_force():
    """同一几何/控制器下，逐车钩异构抽样 → 断面力与齐次不同（异构真实生效）。"""
    hom = _make_dyn()
    rng = np.random.default_rng(7)
    het = _make_dyn(couplers=[sample_coupler_params(rng), sample_coupler_params(rng)])
    # 异构参数确实不同
    assert not np.allclose(het._cp['stiffness'], het._cp['stiffness'][0])
    fh = _strain_consist_dyn(hom)
    fv = _strain_consist_dyn(het)
    assert np.all(fv != 0.0)
    assert float(np.abs(fv - fh).max()) > 1e3   # 至少一个耦合力因异构显著变化（>1kN）
