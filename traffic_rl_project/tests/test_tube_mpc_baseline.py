# -*- coding: utf-8 -*-
"""Tube MPC 移植单测：忠实性 sanity（求解器数学，不碰主仓 env）。

对照：`zba` 复现 `tube_mpc.py`（146 行逐行保真移植，参数换主仓口径）。
"""
import numpy as np
import pytest

from src.mpc_baseline.params import (M_LOCO, M_WAGON_GROUP, U_MIN, U_MAX,
                                     W_LIM_KN, KAPPA, SE_COUPLE_LIM)
from src.mpc_baseline.tube_mpc import TubeMPC, pair_A


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
    assert mpc.se_lim == SE_COUPLE_LIM
    # 扰动界与收紧自洽：du_tight = κ·ε_v = κ·η/(κ−ξ)（式 56，η=W/m_loco）
    _, xi = pair_A(M_LOCO)
    expect = KAPPA * (W_LIM_KN / M_LOCO) / (KAPPA - xi)
    assert mpc.du_tight == pytest.approx(expect)
