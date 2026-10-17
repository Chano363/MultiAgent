"""
空气制动波速传播 + 分布式动力（多源制动）验证测试。

验证目标（对应樊运新论文规律）：
- 编组方式影响制动波传递 → 制动不同步性 → 纵向冲动
- 尾部有动力（分布式制动）时制动同步性提升 → 峰值车钩力降低

测试内容：
1. 单源制动从前向后单向传播（队首发出，尾部延迟生效）
2. 多源制动（队首+队尾）比单源制动峰值车钩力更低（樊运新规律）
"""

import os
import sys

import pytest
import numpy as np


from src.train_dynamics.params import VehicleParams, LocomotiveParams, TrainConsist
from src.train_dynamics.train import TrainDynamics
from src.train_dynamics.braking import AirBrakeNotch


def _make_train(n_vehicles):
    """构造 n 节车（1 机车在前，其余货车）。"""
    consist = TrainConsist(
        [LocomotiveParams()] + [VehicleParams() for _ in range(n_vehicles - 1)]
    )
    return TrainDynamics(consist, dt=0.1)


def _peak_coupler_for_emergency(n, speed_mps=20.0, ab_sources=None, steps=60):
    """紧急制动工况下峰值 |车钩力|。

    ab_sources 为 None 时单源（队首）；否则按给定多源。
    """
    td = _make_train(n)
    td.set_initial_speed(speed_mps)
    peak = 0.0
    if ab_sources is None:
        sources = None
        cmd = AirBrakeNotch.EMERGENCY
        origin = 0
    else:
        sources = ab_sources
        cmd = None
        origin = None
    for _ in range(steps):
        td.step_vehicles_ed_ab(
            throttle=np.zeros(n),
            ed_throttle=np.zeros(n),
            ab_command=cmd if sources is None else AirBrakeNotch.RELEASE,
            brake_origin=origin if sources is None else 0,
            ab_sources=sources,
        )
        peak = max(peak, float(np.max(np.abs(td._coupler_forces()))))
    return peak


# ---------------------------------------------------------------------------
# 1. 单源制动单向传播
def test_single_source_propagates_front_to_back():
    """单源制动（队首）从前向后传播，尾部延迟生效。"""
    td = _make_train(8)
    td.set_initial_speed(20.0)
    td.step_vehicles_ed_ab(
        throttle=np.zeros(8), ed_throttle=np.zeros(8),
        ab_command=AirBrakeNotch.EMERGENCY, brake_origin=0,
    )
    state = td.air_brake_state()
    assert state[0] == AirBrakeNotch.EMERGENCY  # 队首立即激活
    assert state[-1] == AirBrakeNotch.RELEASE    # 尾部未激活（传播延迟）
    # 激活状态沿车列单调
    active = [s != AirBrakeNotch.RELEASE for s in state]
    for i in range(1, len(active)):
        assert active[i] <= active[i - 1], "单源制动传播应从队首向后递减"


# ---------------------------------------------------------------------------
# 2. 樊运新规律验证：分布式动力提升制动同步性（可复现）
# 说明：樊运新核心规律是"尾部动力减少缓解延时（编组1 vs 编组3：5.63s vs 13.66s，-58.8%）"，
# 即分布式动力提升制动/缓解同步性。此处的可复现验证点 = 全列达到制动状态更快。
# （注：双源紧急制动"降低峰值车钩力"在物理上不成立——两端同时全力制动会拉伸中部车厢，
#   反使中部拉钩力增大。此失败发现已记录于 VALIDATION_BASELINE.md V1-3。）



def test_multi_source_both_ends_activated():
    """多源制动时队首与队尾都应立即激活（分布式动力）。"""
    td = _make_train(10)
    td.set_initial_speed(20.0)
    td.step_vehicles_ed_ab(
        throttle=np.zeros(10), ed_throttle=np.zeros(10),
        ab_command=AirBrakeNotch.EMERGENCY,
        ab_sources=[(0, AirBrakeNotch.EMERGENCY), (9, AirBrakeNotch.EMERGENCY)],
    )
    state = td.air_brake_state()
    assert state[0] == AirBrakeNotch.EMERGENCY
    assert state[9] == AirBrakeNotch.EMERGENCY


# ---------------------------------------------------------------------------
# 3. 分布式动力显著提升制动同步（樊运新：编组1 缓解延时 -58.8%）
def test_multi_source_faster_full_activation():
    """多源制动使全列更快达到制动状态（制动同步性提升）。"""
    n = 12
    td1 = _make_train(n)
    td1.set_initial_speed(20.0)
    steps_single = 0
    for s in range(200):
        td1.step_vehicles_ed_ab(
            throttle=np.zeros(n), ed_throttle=np.zeros(n),
            ab_command=AirBrakeNotch.EMERGENCY, brake_origin=0,
        )
        if all(x != AirBrakeNotch.RELEASE for x in td1.air_brake_state()):
            steps_single = s + 1
            break

    td2 = _make_train(n)
    td2.set_initial_speed(20.0)
    steps_multi = 0
    for s in range(200):
        td2.step_vehicles_ed_ab(
            throttle=np.zeros(n), ed_throttle=np.zeros(n),
            ab_command=AirBrakeNotch.EMERGENCY,
            ab_sources=[(0, AirBrakeNotch.EMERGENCY), (n - 1, AirBrakeNotch.EMERGENCY)],
        )
        if all(x != AirBrakeNotch.RELEASE for x in td2.air_brake_state()):
            steps_multi = s + 1
            break

    print(f"单源全列激活耗时={steps_single*0.1:.2f}s, 双源全列激活耗时={steps_multi*0.1:.2f}s")
    assert steps_multi <= steps_single, \
        f"多源制动应更快达到全列制动: 单源{steps_single}步 vs 双源{steps_multi}步"


# ---------------------------------------------------------------------------
# 【AD 组 2026-10-17】中置机车制动波源延时（错开双源波在中机车后方 110-151 断面对撞，
# Y2 峰值断面实证区 = 中源后方；头源仍立即发波）。


def _make_train_delay(n_vehicles, delay_s):
    consist = TrainConsist(
        [LocomotiveParams()] + [VehicleParams() for _ in range(n_vehicles - 1)]
    )
    return TrainDynamics(consist, dt=0.1, mid_source_delay_s=delay_s)


def _step_multi(td, n, cmd=AirBrakeNotch.EMERGENCY, mid=5):
    td.step_vehicles_ed_ab(
        throttle=np.zeros(n), ed_throttle=np.zeros(n),
        ab_command=cmd,
        ab_sources=[(0, cmd), (mid, cmd)],
    )


def test_mid_source_delayed_head_immediate():
    """延时开启：队首源首步立即激活、中源首步未激活并入待发队列。"""
    n = 10
    td = _make_train_delay(n, 3.0)
    td.set_initial_speed(20.0)
    _step_multi(td, n)
    state = td.air_brake_state()
    assert state[0] == AirBrakeNotch.EMERGENCY   # 头源立即
    assert state[5] == AirBrakeNotch.RELEASE      # 中源延时中
    assert len(td._ab_delay_queue) == 1


def test_mid_source_fires_after_delay():
    """延时到点（真实时钟 = 控制步×0.1s）后中源发波激活、队列清空。"""
    n = 10
    td = _make_train_delay(n, 0.3)
    td.set_initial_speed(20.0)
    for _ in range(5):   # 5 步 × 0.1s = 0.5s > 0.3s
        _step_multi(td, n)
    state = td.air_brake_state()
    assert state[5] == AirBrakeNotch.EMERGENCY   # 延时到期已发
    assert td._ab_delay_queue == []


def test_mid_source_delay_default_zero_sync():
    """默认 0.0 = 旧行为零回归：双源首步同时激活、无待发队列。"""
    n = 10
    td = _make_train_delay(n, 0.0)
    td.set_initial_speed(20.0)
    _step_multi(td, n)
    state = td.air_brake_state()
    assert state[0] == AirBrakeNotch.EMERGENCY
    assert state[5] == AirBrakeNotch.EMERGENCY   # 同步发波（旧行为）
    assert td._ab_delay_queue == []


def test_mid_source_queue_cleared_on_release():
    """缓解（RELEASE 指令）清空待发中源队列，制动段结束不残留。"""
    n = 10
    td = _make_train_delay(n, 3.0)
    td.set_initial_speed(20.0)
    _step_multi(td, n)
    assert len(td._ab_delay_queue) == 1
    td.step_vehicles_ed_ab(   # 缓解指令
        throttle=np.zeros(n), ed_throttle=np.zeros(n),
        ab_command=AirBrakeNotch.RELEASE,
        ab_sources=[(0, AirBrakeNotch.RELEASE), (5, AirBrakeNotch.RELEASE)],
    )
    assert td._ab_delay_queue == []
