"""
线路坡度剖面建模验证测试（P1.5 第12条，长大下坡场景）。

验证目标：
- GradeProfile 按位置查询坡度正确
- 3 种预置剖面（樊运新：长大下坡/缓坡变陡坡/V型坡）合理
- 列车在变坡剖面上运行时，每节车坡度随位置实时更新
- 长大下坡场景下环境能跑通（循环制动场景前置）
"""

import os
import sys

import pytest
import numpy as np


from src.train_dynamics.grade_profile import (
    GradeProfile, GradeSegment,
    profile_long_downhill, profile_gradual_to_steep, profile_v_shape, PROFILES,
)
from src.train_dynamics.params import VehicleParams, LocomotiveParams, TrainConsist
from src.train_dynamics.train import TrainDynamics


# ---------------------------------------------------------------------------
# 1. 坡度剖面查询
def test_grade_at_segment_boundaries():
    """坡度查询在段边界处正确切换。"""
    profile = GradeProfile(segments=[
        GradeSegment(0.0, -2.0),
        GradeSegment(500.0, -10.2),
        GradeSegment(3000.0, -2.0),
    ])
    assert profile.grade_at(0.0) == pytest.approx(-2.0 / 1000.0)
    assert profile.grade_at(499.0) == pytest.approx(-2.0 / 1000.0)
    assert profile.grade_at(500.0) == pytest.approx(-10.2 / 1000.0)
    assert profile.grade_at(2999.0) == pytest.approx(-10.2 / 1000.0)
    assert profile.grade_at(3000.0) == pytest.approx(-2.0 / 1000.0)
    assert profile.grade_at(5000.0) == pytest.approx(-2.0 / 1000.0)


def test_grade_for_positions_batch():
    """批量查询多节车坡度。"""
    profile = GradeProfile(segments=[
        GradeSegment(0.0, -2.0),
        GradeSegment(500.0, -10.2),
    ])
    pos = np.array([0.0, 300.0, 600.0, 1000.0])
    grades = profile.grades_for_positions(pos)
    assert grades[0] == pytest.approx(-2.0 / 1000.0)
    assert grades[1] == pytest.approx(-2.0 / 1000.0)
    assert grades[2] == pytest.approx(-10.2 / 1000.0)
    assert grades[3] == pytest.approx(-10.2 / 1000.0)


def test_empty_profile_zero_grade():
    """空剖面返回 0 坡度。"""
    profile = GradeProfile()
    assert profile.grade_at(100.0) == 0.0


# ---------------------------------------------------------------------------
# 2. 3 种预置剖面（樊运新）
def test_three_preset_profiles_exist():
    """3 种预置剖面存在且含长大下坡段。"""
    p_a = profile_long_downhill()
    p_b = profile_gradual_to_steep()
    p_c = profile_v_shape()
    assert len(p_a.segments) >= 2
    assert len(p_b.segments) >= 2
    assert len(p_c.segments) >= 2
    # 长大下坡段坡度应 <= -5‰（陡下坡）
    has_steep = any(s.grade_permille <= -5.0 for s in p_a.segments)
    assert has_steep, "长大下坡剖面应含陡下坡段(<=-5‰)"


def test_v_shape_has_large_grade_difference():
    """V 型坡坡度差应较大（~10.5‰）。"""
    p_c = profile_v_shape()
    grades = [s.grade_permille for s in p_c.segments]
    grade_diff = max(grades) - min(grades)
    assert grade_diff >= 10.0, f"V型坡坡度差应>=10‰，实际{grade_diff}"


# ---------------------------------------------------------------------------
# 3. 列车在变坡剖面上运行时坡度实时更新
def test_grade_updates_with_position():
    """列车运行时，每节车坡度随位置实时更新。"""
    consist = TrainConsist([LocomotiveParams()] + [VehicleParams() for _ in range(3)])
    td = TrainDynamics(consist, dt=0.1)
    td.set_initial_speed(20.0)
    td.set_grade_profile(profile_long_downhill())
    # 初始位置在 -2‰ 段
    g0 = td.grade.copy()
    assert all(abs(g - (-2.0 / 1000.0)) < 1e-6 for g in g0)
    # 跑一段时间让列车进入 -10.2‰ 段（500m 后）
    for _ in range(500):  # 50s @ 20m/s = 1000m
        td.step_vehicles(np.zeros(4), np.zeros(4))
    g1 = td.grade.copy()
    # 至少部分车应进入 -10.2‰ 段
    assert any(abs(g - (-10.2 / 1000.0)) < 1e-6 for g in g1), \
        f"列车进入长大下坡段后坡度应更新，实际{g1}"


def test_downhill_accelerates_train():
    """长大下坡（-10.2‰段）应使列车加速（重力分量助力大于阻力）。"""
    consist = TrainConsist([LocomotiveParams()] + [VehicleParams() for _ in range(3)])
    td = TrainDynamics(consist, dt=0.1)
    td.set_initial_speed(15.0)
    td.set_grade_profile(profile_long_downhill())
    # 把列车放到 -10.2‰ 陡坡段（起点位置 500m 之后）
    td.pos = td.pos + 600.0
    td._update_grade_from_profile()
    # 确认当前在陡坡段
    assert all(abs(g - (-10.2 / 1000.0)) < 1e-6 for g in td.grade)
    v0 = td.vel.mean()
    # 在长大下坡段滑行（无牵引无制动）
    for _ in range(200):  # 20s
        td.step_vehicles(np.zeros(4), np.zeros(4))
    v1 = td.vel.mean()
    assert v1 > v0, f"长大下坡(-10.2‰)应使列车加速: v0={v0}, v1={v1}"


# ---------------------------------------------------------------------------
# 4. 环境集成：长大下坡场景能跑通
def test_env_with_grade_profile_runs():
    """环境配置长大下坡剖面能跑通（循环制动场景前置）。"""
    from src.environments.train_env import TrainFormationEnv
    env = TrainFormationEnv({
        'num_vehicles': 4,
        'grade_profile': 'long_downhill',
        'max_steps': 100,
    })
    obs, _ = env.reset()
    for _ in range(100):
        obs, r, t, tr, info = env.step(np.zeros(4))
        if t or tr:
            break
    assert info.get('speed') is not None


def test_env_invalid_profile_raises():
    """未知坡度剖面名应报错。"""
    from src.environments.train_env import TrainFormationEnv
    with pytest.raises(ValueError, match="未知坡度剖面"):
        TrainFormationEnv({'grade_profile': 'nonexistent'})


# ---------------------------------------------------------------------------
# 5. 万吨级 1+0 编组（P1.5 第13条，论文研究对象）
def test_10kt_consist_preset():
    """万吨级 1+0 编组预设：1 机 + 100 货，总重约 10188 t。"""
    from src.environments.train_env import TrainFormationEnv
    env = TrainFormationEnv({'consist_preset': '10kt_1plus0', 'max_steps': 10})
    assert env.num_vehicles == 101  # 1 机 + 100 货
    total_mass = sum(v.mass_t for v in env.dynamics.consist.vehicles)
    assert 9500 <= total_mass <= 11000, f"万吨级总重应≈10000t，实际{total_mass}t"


def test_10kt_runs_with_downhill():
    """万吨级编组在长大下坡剖面下能跑通（论文场景）。"""
    from src.environments.train_env import TrainFormationEnv
    env = TrainFormationEnv({
        'consist_preset': '10kt_1plus0',
        'grade_profile': 'long_downhill',
        'max_steps': 50,
    })
    env.reset(options={'speed': 20.0})
    for _ in range(50):
        obs, r, t, tr, info = env.step(np.full(101, -0.3))
        if t or tr:
            break
    assert info['speed'] > 0
    # 万吨级在制动下车钩力应合理（不一定超限）
    assert info['coupler_force_peak'] >= 0
