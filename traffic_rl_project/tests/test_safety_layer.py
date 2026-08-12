"""
规则式 ATP 安全层（SafetyLayer）验证测试。
"""

import os
import sys

import pytest
import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from src.safety_layer import SafetyLayer, DEFAULT_COUPLER_FORCE_LIMIT_N
from src.train_dynamics.braking import (
    AirBrakeNotch, air_brake_force_n, electric_brake_force_n,
    notch_from_throttle, AIR_BRAKE_RATIO,
)
from src.train_dynamics.params import VehicleParams, LocomotiveParams, TrainConsist
from src.train_dynamics.train import TrainDynamics
from src.environments.train_env import TrainFormationEnv

G = 9.8066


# ---------------------------------------------------------------------------
# 安全层：限速防护
def test_safety_overspeed_forbids_traction():
    """已达限速时，牵引动作应被钳制为制动。"""
    sl = SafetyLayer(num_vehicles=2, max_speed_mps=30.0)
    actions = np.array([1.0, 1.0])
    obs_state = {
        'vel': np.array([30.0, 30.0]),
        'coupler_forces': np.zeros(2),
        'gaps': np.array([0.0, 1.0]),
    }
    corrected = sl.protect(actions, obs_state)
    assert corrected[0] <= 0.0
    assert any(e['rule'] == 'overspeed' for e in sl.last_events)


def test_safety_overspeed_allows_normal():
    """低于限速时，牵引动作不被修正。"""
    sl = SafetyLayer(num_vehicles=2, max_speed_mps=30.0)
    actions = np.array([0.5, 0.5])
    obs_state = {
        'vel': np.array([20.0, 20.0]),
        'coupler_forces': np.zeros(2),
        'gaps': np.array([0.0, 1.0]),
    }
    corrected = sl.protect(actions, obs_state)
    assert corrected[0] == pytest.approx(0.5)
    assert corrected[1] == pytest.approx(0.5)


# ---------------------------------------------------------------------------
# 安全层：车钩力上限防护
def test_safety_coupler_force_limit_blocks_traction():
    """车钩力达上限（1000 kN）时，牵引动作应被抑制。"""
    sl = SafetyLayer(num_vehicles=2, coupler_force_limit_n=DEFAULT_COUPLER_FORCE_LIMIT_N)
    actions = np.array([1.0, 0.5])
    obs_state = {
        'vel': np.array([20.0, 20.0]),
        'coupler_forces': np.array([1.0e6, 1.0e6]),
        'gaps': np.array([0.0, 1.0]),
    }
    corrected = sl.protect(actions, obs_state)
    assert corrected[0] == 0.0  # 牵引被钳制
    assert any(e['rule'] == 'coupler_force_limit' for e in sl.last_events)


def test_safety_coupler_force_below_limit_unchanged():
    """车钩力低于上限时，牵引不被修正。"""
    sl = SafetyLayer(num_vehicles=2, coupler_force_limit_n=DEFAULT_COUPLER_FORCE_LIMIT_N)
    actions = np.array([0.8, 0.3])
    obs_state = {
        'vel': np.array([20.0, 20.0]),
        'coupler_forces': np.array([5.0e5, 5.0e5]),
        'gaps': np.array([0.0, 1.0]),
    }
    corrected = sl.protect(actions, obs_state)
    assert corrected[0] == pytest.approx(0.8)


# ---------------------------------------------------------------------------
# 安全层：间距防护
def test_safety_min_gap_blocks_acceleration():
    """间距过小时，后车继续加速应被抑制。"""
    sl = SafetyLayer(num_vehicles=2, min_gap_m=0.5)
    actions = np.array([0.0, 1.0])  # 后车（idx 1）加速
    obs_state = {
        'vel': np.array([20.0, 20.0]),
        'coupler_forces': np.zeros(2),
        'gaps': np.array([0.0, 0.3]),  # 间距小于 0.5
    }
    corrected = sl.protect(actions, obs_state)
    assert corrected[1] == 0.0
    assert any(e['rule'] == 'min_gap' for e in sl.last_events)


# ---------------------------------------------------------------------------
# 离散空气制动
def test_air_brake_discrete_levels():
    """空气制动力对应离散档位（RELEASE/MIN/SERVICE/EMERGENCY）。"""
    mass_t, v = 100.0, 10.0
    f_release = air_brake_force_n(mass_t, v, AirBrakeNotch.RELEASE, 0.6)
    f_min = air_brake_force_n(mass_t, v, AirBrakeNotch.MIN, 0.6)
    f_service = air_brake_force_n(mass_t, v, AirBrakeNotch.SERVICE, 0.6)
    f_emergency = air_brake_force_n(mass_t, v, AirBrakeNotch.EMERGENCY, 0.6)
    assert f_release == 0.0
    assert f_min < f_service < f_emergency
    # 紧急制动 = 最大制动力
    mu = 0.6 * (v * 3.6 + 100.0) / (5.0 * v * 3.6 + 100.0)
    expected_max = 0.6 * mass_t * 1000.0 * G * mu
    assert f_emergency == pytest.approx(expected_max, abs=1.0)


def test_notch_from_throttle_mapping():
    """连续负动作到离散档位的映射。"""
    assert notch_from_throttle(0.0) == AirBrakeNotch.RELEASE
    assert notch_from_throttle(-0.1) == AirBrakeNotch.MIN
    assert notch_from_throttle(-0.5) == AirBrakeNotch.SERVICE
    assert notch_from_throttle(-0.9) == AirBrakeNotch.EMERGENCY


# ---------------------------------------------------------------------------
# 电制动（连续）
def test_electric_brake_continuous_scaling():
    """电制动力随指令连续缩放，且仅机车具备。"""
    mass_t, v = 188.0, 20.0
    f_ed_half = electric_brake_force_n(mass_t, v, 0.5)
    f_ed_full = electric_brake_force_n(mass_t, v, 1.0)
    assert f_ed_half < f_ed_full
    assert f_ed_full > 0
    # 静止时按粘着极限 * 比例
    f_ed_stationary = electric_brake_force_n(mass_t, 0.0, 1.0)
    assert f_ed_stationary == pytest.approx(0.9 * 188.0 * 1000.0 * G * 0.85, abs=1.0)


def test_electric_brake_zero():
    """无电制动指令时制动力为 0。"""
    assert electric_brake_force_n(188.0, 20.0, 0.0) == 0.0


# ---------------------------------------------------------------------------
# 空气制动波速传播（动力学集成）
def test_air_brake_propagation_delay():
    """空气制动应沿车列向后延迟传播（基于车辆累计长度）。"""
    consist = TrainConsist([
        LocomotiveParams(), VehicleParams(), VehicleParams(), VehicleParams(),
    ])
    td = TrainDynamics(consist, dt=0.1)
    td.set_initial_speed(20.0)
    # 4 辆车，每辆长 21/20m，累计约 60m，波速 250m/s → 队尾延迟约 0.24s
    for _ in range(5):  # 0.5s > 0.24s，所有车应已激活
        td.step_vehicles_ed_ab(
            throttle=np.zeros(4),
            ed_throttle=np.zeros(4),
            ab_command=AirBrakeNotch.EMERGENCY,
        )
    state = td.air_brake_state()
    assert all(state[i] == AirBrakeNotch.EMERGENCY for i in range(4))


def test_air_brake_propagation_not_instant():
    """极短时间（一个 dt）内后部车辆不应立即达到紧急制动。"""
    consist = TrainConsist([
        LocomotiveParams(), VehicleParams(), VehicleParams(), VehicleParams(),
    ])
    td = TrainDynamics(consist, dt=1e-4)  # 极短步长
    td.set_initial_speed(20.0)
    td.step_vehicles_ed_ab(
        throttle=np.zeros(4), ed_throttle=np.zeros(4),
        ab_command=AirBrakeNotch.EMERGENCY,
    )
    state = td.air_brake_state()
    # 队首立即激活，但后部车辆因传播延迟（约 0.24s）未激活
    assert state[0] == AirBrakeNotch.EMERGENCY
    assert state[-1] == AirBrakeNotch.RELEASE


def test_air_brake_propagation_slows_train():
    """施加紧急制动后列车应减速。"""
    consist = TrainConsist([
        LocomotiveParams(), VehicleParams(), VehicleParams(), VehicleParams(),
    ])
    td = TrainDynamics(consist, dt=0.1)
    td.set_initial_speed(20.0)
    v0 = td.vel.copy()
    for _ in range(60):
        td.step_vehicles_ed_ab(
            throttle=np.zeros(4), ed_throttle=np.zeros(4),
            ab_command=AirBrakeNotch.EMERGENCY,
        )
    assert td.vel.mean() < v0.mean()


# ---------------------------------------------------------------------------
# 环境：安全层集成与最终指标
def test_env_safety_layer_prevents_overspeed():
    """满油门长期运行不应超过限速（安全层兜底）。"""
    env = TrainFormationEnv({'num_vehicles': 4, 'max_steps': 500})
    env.reset()
    max_speed = env.dynamics.consist.vehicles[0].max_speed_mps
    peak = 0.0
    for _ in range(300):
        obs, reward, terminated, truncated, info = env.step(np.full(4, 1.0))
        peak = max(peak, info['speed'])
        if terminated or truncated:
            break
    assert peak <= max_speed + 1.0


def test_env_coupler_force_limit_metric_present():
    """info 应包含车钩力峰值/上限/超限计数。"""
    env = TrainFormationEnv({'num_vehicles': 4})
    env.reset()
    obs, reward, terminated, truncated, info = env.step(np.zeros(4))
    assert 'coupler_force_peak' in info
    assert 'coupler_force_limit' in info
    assert 'coupler_limit_violations' in info
    assert info['coupler_force_limit'] == pytest.approx(1.0e6)
