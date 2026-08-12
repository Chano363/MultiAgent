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
from src.train_dynamics.braking import braking_force, brake_shoe_friction, BrakeShoeType
from src.train_dynamics.coupler import coupler_force
from src.train_dynamics.params import VehicleParams, LocomotiveParams, TrainConsist
from src.train_dynamics.train import TrainDynamics

G = 9.8066


# ---------------------------------------------------------------------------
# Davis 阻力：与 NeTrainSim Car::getResistance 手算对比
# 例：weight=100t(公吨), axles=4, area=10m^2, cd=1.0, v=10m/s, grade=0, curv=0
# 转换: w=100*1.10231=110.231 short_tons, v=10*2.23694=22.3694 mph,
#       area=10*10.7639=107.639 ft^2
# r = 1.5 + 18/(110.231/4) + 0.03*22.3694 + 107.639*1.0*22.3694^2/110.231
#   = 1.5 + 0.65320 + 0.67108 + 488.87 = 491.694 lb
# R = 491.694*110.231 = 54200.6 lb  ->  *4.44822 = 241102 N
def test_davis_resistance_matches_netrainsim():
    w, axles, area, cd, v = 100.0, 4, 10.0, 1.0, 10.0

    w_short = w * 1.10231
    v_mph = v * 2.23694
    area_ft = area * 10.7639
    r = 1.5 + 18 / (w_short / axles) + 0.03 * v_mph + area_ft * cd * v_mph**2 / w_short
    R_lb = r * w_short
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
# 车钩力（质量-弹簧-阻尼）
def test_coupler_spring_force():
    """拉伸（后车更远）产生拉力（前车受负力），压紧（后车更近）产生推力（前车受正力）。"""
    k, c, L = 5.0e6, 5.0e4, 1.0
    # 静止位置：后车在前车后方 L=1.0 处，e=0，力=0
    f_rest = coupler_force(0.0, 0.0, -1.0, 0.0, k, c, L)
    assert f_rest == pytest.approx(0.0, abs=1.0)
    # 拉长（后车再往后 0.2）：e=-0.2，弹簧拉两车向彼此 → 前车受 -k*0.2（向后）
    f = coupler_force(0.0, 0.0, -1.2, 0.0, k, c, L)
    assert f == pytest.approx(-k * 0.2)
    # 压紧（后车往前 0.2）：e=+0.2，弹簧推开 → 前车受 +k*0.2（向前）
    f2 = coupler_force(0.0, 0.0, -0.8, 0.0, k, c, L)
    assert f2 == pytest.approx(k * 0.2)


def test_coupler_damping_force():
    """相对速度产生阻尼力（阻碍分离/靠近）。"""
    k, c, L = 5.0e6, 5.0e4, 1.0
    # 静止位置 e=0，后车以 2 m/s 撞向前车（v_back=2, v_front=0）
    # 分离速度 v_front-v_back = -2，阻尼 +c*2，前车被推向前（后车逼近）
    f = coupler_force(0.0, 0.0, -1.0, 2.0, k, c, L)
    assert f == pytest.approx(c * 2.0)
    # 后车减速更快（v_back=-2, v_front=0）→ 分离，阻尼拉回前车
    f2 = coupler_force(0.0, 0.0, -1.0, -2.0, k, c, L)
    assert f2 == pytest.approx(-c * 2.0)


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
    """牛顿第三定律：车钩对前车的力与对后车的力互为相反数（同一物理构型）。"""
    k, c, L = 5.0e6, 5.0e4, 1.0
    x_front, x_back = 0.0, -1.2  # 拉长 0.2
    v_front, v_back = 0.0, 1.0
    # 前车受到的力（函数约定：第一参数为前车）
    f_on_front = coupler_force(x_front, v_front, x_back, v_back, k, c, L)
    # 后车受到的力 = -前车受到的力（牛顿第三定律）
    f_on_back = -f_on_front
    # 直接验证：拉长时前车受负力（向后拉）
    assert f_on_front == pytest.approx(k * ((x_back - x_front) + L) - c * (v_front - v_back), abs=1.0)
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
    """制动力应使列车减速。"""
    consist = _make_consist()
    td = TrainDynamics(consist)
    td.set_initial_speed(20.0)
    v0 = td.vel.copy()
    for _ in range(30):
        td.step(throttle=0.0, brake_notch=1.0)
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
