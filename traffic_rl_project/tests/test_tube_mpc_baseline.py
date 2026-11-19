# -*- coding: utf-8 -*-
"""Tube MPC 移植单测：忠实性 sanity（求解器数学，不碰主仓 env）。

对照：`zba` 复现 `tube_mpc.py`（146 行逐行保真移植，参数换主仓口径）。
"""
from types import SimpleNamespace

import numpy as np
import pytest

from src.evaluation.evaluate_mpc_tube import (cycle_brake, make_train,
                                              solve_tube_command, speed_guard)
from src.mpc_baseline.params import (D_DES, ED_MAX, M_LOCO, M_WAGON_GROUP,
                                     U_MIN, U_MAX, W_LIM_KN, KAPPA,
                                     SE_COUPLE_LIM, V_MIN_RELEASE)
from src.mpc_baseline.tube_mpc import TubeMPC, pair_A
from src.train_dynamics.braking import AirBrakeNotch
from src.train_dynamics.grade_profile import PROFILES


@pytest.fixture
def mpc():
    return TubeMPC(idx=0)


def test_pair_a_damping_sign(mpc=None):
    """ξ 必须为负（阻力是耗散项）：A=[[0,1],[0,ξ]]，ξ=-(C1+2C2·v0)/m。"""
    A, xi = pair_A(M_LOCO)
    assert xi < 0.0
    A2, xi2 = pair_A(M_WAGON_GROUP)
    assert xi2 < 0.0
    # 质量越大 |ξ| 越小（阻力加速度越小）
    assert abs(xi2) < abs(xi)


def test_zero_error_state_returns_near_zero_input(mpc):
    """名义平衡：x0=0、a_ref=0、d2=0 ⇒ 无需控制，û*≈0。"""
    x0 = np.zeros(4)
    u = mpc.solve(x0, v_ref0=60.0 / 3.6, a_ref=0.0, d2=0.0)
    assert abs(u) < 1e-3


def test_speed_below_reference_commands_acceleration(mpc):
    """低于参考速度 2 m/s ⇒ û > 0。符号约定（zba）：x0[1]=v_ref−v_actual，
    正 = 实际速度低于参考 ⇒ 正 û（缓解/牵引）向参考收敛。"""
    x0 = np.array([0.0, 2.0, 0.0, 0.0])
    u = mpc.solve(x0, v_ref0=60.0 / 3.6, a_ref=0.0, d2=0.0)
    assert u > 0.0


def test_speed_above_reference_commands_braking(mpc):
    """高于参考速度 2 m/s ⇒ û < 0（x0[1]=v_ref−v 为负 = 实际高于参考）。"""
    x0 = np.array([0.0, -2.0, 0.0, 0.0])
    u = mpc.solve(x0, v_ref0=60.0 / 3.6, a_ref=0.0, d2=0.0)
    assert u < 0.0


def test_input_respects_tightened_bounds(mpc):
    """输入收紧（式 56）：bounds = [U_MIN+κe, U_MAX−κe]/m，解不得越界。"""
    x0 = np.array([0.0, -8.0, 0.0, 0.0])   # 大偏差，逼出边界
    u = mpc.solve(x0, v_ref0=60.0 / 3.6, a_ref=0.0, d2=0.0)
    assert u >= mpc.u_min_n + mpc.du_tight - 1e-6
    assert u <= mpc.u_max_n - mpc.du_tight + 1e-6


def test_tube_wideness_positive_and_finite(mpc):
    """tube 收紧量（式 54-56）必须为正有限：ε_v=η/(κ−ξ), ε_s=ηHδ/(κ−ξ)。"""
    assert 0.0 < mpc.eps_v < np.inf
    assert 0.0 < mpc.eps_s < np.inf
    assert mpc.kappa > mpc.xi      # κ > ξ 是 tube 反馈稳定的前提（式 55）


def test_main_gauge_parameters(mpc):
    """主仓口径参数抽查（ADR-068 / consist_10kt_1plus0）：防 zba 值残留。"""
    assert mpc.m_loco == M_LOCO == 188.0
    assert M_WAGON_GROUP == 5400.0
    assert D_DES == 1424.7       # 车长 1296 + 75 口径 d_eff 128.7
    assert mpc.se_lim == SE_COUPLE_LIM
    # 扰动界与收紧自洽：du_tight = κ·ε_v = κ·η/(κ−ξ)（式 56，η=W/m_loco）
    _, xi = pair_A(M_LOCO)
    expect = KAPPA * (W_LIM_KN / M_LOCO) / (KAPPA - xi)
    assert mpc.du_tight == pytest.approx(expect)


def test_solver_reports_status_after_solve():
    """每次求解必须暴露 success/attempts，禁止失败后静默当成功。"""
    m = TubeMPC(0)
    m.solve(np.array([0.0, -1.95, 0.0, -1.546]), 16.0, 0.0, 0.0)
    assert m.last_solve_attempts >= 1
    assert isinstance(m.last_solve_success, bool)
    assert m.last_solve_status


def test_tube_feedback_resets_nominal_state(mpc):
    """zba 每步令 xbar=x0，z=0；不得把完整 x0 再叠加到 û* 上。"""
    x0 = np.array([0.0, -8.0, 0.0, 0.0])
    u = solve_tube_command(mpc, x0, 60.0 / 3.6, 0.0, 0.0)
    np.testing.assert_array_equal(mpc.xbar, x0)
    assert u >= mpc.u_min_n + mpc.du_tight - 1e-6
    assert u <= mpc.u_max_n - mpc.du_tight + 1e-6


def test_cycle_brake_uses_release_time_and_45s_recharge():
    """45 s 是缓解后的最短充风时间，不是单次施加的最大时长。"""
    dyn = SimpleNamespace(vel=np.array([17.0]))
    assert cycle_brake(dyn, 16.0, 0.0)
    assert cycle_brake(dyn, 16.0, 100.0)  # 高速时持续施加，不在 45 s 强制缓解

    dyn.vel[0] = 15.0
    assert not cycle_brake(dyn, 16.0, 101.0)
    dyn.vel[0] = 17.0
    assert not cycle_brake(dyn, 16.0, 102.0)  # 充风未满，禁止立即重施
    assert cycle_brake(dyn, 16.0, 146.0)

    dyn.vel[0] = V_MIN_RELEASE - 0.1
    assert not cycle_brake(dyn, 16.0, 147.0)  # 低速强制缓解并记录缓解时刻
    assert dyn._mpc_cycle_state["t_rel"] == 147.0


def test_speed_guard_overrides_mpc_traction_when_overspeed():
    """超参考 0.5 m/s 时必须零牵引、满电制动；未超速时不改 MPC 指令。"""
    dyn = SimpleNamespace(vel=np.array([17.0]))
    assert speed_guard(dyn, 16.0, 0.4, 0.1) == (0.0, ED_MAX)
    dyn.vel[0] = 16.2
    assert speed_guard(dyn, 16.0, 0.4, 0.1) == (0.4, 0.1)


def test_zero_coupler_has_zero_interface_force_after_step():
    """主对比关车钩时，断面力必须在实际积分后仍严格为零。"""
    profile = PROFILES["shuozhou_ningwuxi_beidaniu_49km"]()
    dyn = make_train("zero", 4300.0, profile)
    dyn.step_vehicles_ed_ab(np.zeros(dyn.num_vehicles),
                            np.zeros(dyn.num_vehicles), AirBrakeNotch.RELEASE)
    np.testing.assert_array_equal(dyn.coupler_interface_forces(),
                                  np.zeros(dyn.num_vehicles - 1))
