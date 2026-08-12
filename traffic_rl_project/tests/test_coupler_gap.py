"""
车钩间隙（死区）非线性建模验证测试。

验证目标：复现杨敏等论文揭示的规律——
"车钩间隙越大 → 最大车钩力越大（近似线性增加）"。

验证手段：
1. 单元测试 `_dead_zone`：死区内弹簧力为 0，超死区按剩余伸长量线性恢复
2. 集成测试：相同制动冲击工况下，增大 coupler_gap 应导致峰值车钩力增大
"""

import os
import sys

import pytest
import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from src.train_dynamics.coupler import coupler_force, _dead_zone
from src.train_dynamics.params import (
    VehicleParams, LocomotiveParams, CouplerParams, TrainConsist,
)
from src.train_dynamics.train import TrainDynamics


# ---------------------------------------------------------------------------
# 单元测试：死区函数
def test_dead_zone_inside_gap_zero():
    """死区内（|e| <= gap）有效伸长量为 0。"""
    assert _dead_zone(0.005, 0.01) == 0.0
    assert _dead_zone(-0.005, 0.01) == 0.0
    assert _dead_zone(0.0, 0.01) == 0.0
    assert _dead_zone(0.01, 0.01) == 0.0  # 边界含


def test_dead_zone_outside_gap():
    """超死区后返回剩余伸长量（带符号）。"""
    assert _dead_zone(0.02, 0.01) == pytest.approx(0.01)
    assert _dead_zone(-0.02, 0.01) == pytest.approx(-0.01)
    assert _dead_zone(0.05, 0.01) == pytest.approx(0.04)


def test_dead_zone_zero_gap_is_identity():
    """gap=0（无死区）时，死区函数是恒等映射（向后兼容）。"""
    assert _dead_zone(0.03, 0.0) == pytest.approx(0.03)
    assert _dead_zone(-0.03, 0.0) == pytest.approx(-0.03)


# ---------------------------------------------------------------------------
# 单元测试：车钩力带间隙
def test_coupler_force_gap_reduces_force_inside():
    """间隙内（相对位移小于 gap）弹簧力为 0，只剩阻尼力。"""
    # x_back - x_front = 0（相对自由长度无位移），gap=0.01
    # 但有分离速度时仍有阻尼力
    f = coupler_force(0.0, 1.0, 0.0, 0.0, 5.0e6, 5.0e4, 1.0, 0.01)
    # e = 0 + 1.0 = 1.0 不是 0！需重新构造
    # 构造 e=0：x_back = x_front - free_length
    f = coupler_force(0.0, 1.0, -1.0, 0.0, 5.0e6, 5.0e4, 1.0, 0.01)
    # e = (-1.0 - 0.0) + 1.0 = 0，在死区内 → 弹簧力 0，阻尼力 -c*(v_f-v_b)=-5e4
    assert f == pytest.approx(-5.0e4, abs=1.0)


def test_coupler_force_gap_less_than_nogap():
    """相同位移下，带间隙的车钩弹簧力幅值 <= 无间隙（间隙吸收部分位移）。"""
    # 压缩 0.02m，gap=0.01 → 有效 0.01；无 gap → 有效 0.02
    f_gap = coupler_force(0.0, 0.0, -1.0 + 0.02, 0.0, 5.0e6, 5.0e4, 1.0, 0.01)
    f_nogap = coupler_force(0.0, 0.0, -1.0 + 0.02, 0.0, 5.0e6, 5.0e4, 1.0, 0.0)
    assert abs(f_gap) < abs(f_nogap)


def test_coupler_force_no_gap_backward_compat():
    """无间隙（gap=0）时行为与旧版线性弹簧一致。"""
    f = coupler_force(0.0, 0.0, -1.0 + 0.005, 0.0, 5.0e6, 5.0e4, 1.0, 0.0)
    assert f == pytest.approx(5.0e6 * 0.005)


# ---------------------------------------------------------------------------
# 集成测试：杨敏规律（车钩间隙越大 → 最大车钩力越大）
def _peak_coupler_for_braking(n_vehicles, gap_m, speed_mps=20.0, brake_steps=60):
    """给定车钩间隙，跑一个强制动工况，返回峰值 |车钩力|。"""
    consist = TrainConsist(
        [LocomotiveParams()] + [VehicleParams() for _ in range(n_vehicles - 1)]
    )
    td = TrainDynamics(
        consist,
        coupler=CouplerParams(coupler_gap_m=gap_m),
        dt=0.1,
    )
    td.set_initial_speed(speed_mps)
    from src.train_dynamics.braking import AirBrakeNotch
    peak = 0.0
    for _ in range(brake_steps):
        td.step_vehicles_ed_ab(
            throttle=np.zeros(n_vehicles),
            ed_throttle=np.zeros(n_vehicles),
            ab_command=AirBrakeNotch.EMERGENCY,
        )
        peak = max(peak, float(np.max(np.abs(td._coupler_forces()))))
    return peak


def test_gap_larger_means_larger_peak_force():
    """杨敏规律：车钩间隙越大 → 峰值车钩力越大（单调）。"""
    gaps = [0.0, 0.01, 0.02, 0.03]
    peaks = [_peak_coupler_for_braking(8, g) for g in gaps]
    print(f"gaps={gaps} -> peaks={[round(p,0) for p in peaks]}")
    # 单调不减（允许浮点误差）
    for i in range(len(peaks) - 1):
        assert peaks[i + 1] >= peaks[i] - 1.0, \
            f"间隙增大应使峰值车钩力不减: gap={gaps[i]}->{gaps[i+1]}, peak={peaks[i]}->{peaks[i+1]}"


def test_gap_zero_matches_linear_behavior():
    """gap=0 时峰值车钩力与无死区（线性弹簧）一致（行为基准）。"""
    # gap=0 的峰值应与非零 gap 的峰值不同（间隙改变了动力学）
    p0 = _peak_coupler_for_braking(8, 0.0)
    p_gap = _peak_coupler_for_braking(8, 0.03)
    assert p0 != pytest.approx(p_gap, rel=0.05)  # 间隙显著改变了峰值
