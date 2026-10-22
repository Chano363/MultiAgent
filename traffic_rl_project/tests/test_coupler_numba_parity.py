"""车钩力 numba 内核 vs numpy 实现的数值对照（性能改造守门测试）。

背景：`_coupler_interface_forces_vec` 占 env.step 约 27%（cProfile，tottime 第一），
2026-10-21 增加 numba 快速路径。物理公式必须与 numpy 分支**逐项等价**，
否则训练/评估的物理口径会发生漂移（本项目「两侧物理同源」铁律）。

失败处理：若本测试不过，设 TRAIN_RL_NO_NUMBA=1 即可整体回退到 numpy 分支。
"""
import numpy as np
import pytest

from src.train_dynamics.coupler import RONG2025_FL_N, RONG2025_FU_N, RONG2025_X_M
from src.train_dynamics.params import CouplerParams
from src.train_dynamics.train import (
    STIFFNESS_BASE_N_PER_M, _HAS_NUMBA, _coupler_force_kernel,
)

pytestmark = pytest.mark.skipif(not _HAS_NUMBA, reason='numba 不可用，已自动回退 numpy 分支')


def _numpy_impl(e, dv, gap, v_eps, rigid_k, stroke, gain, max_impulse,
                xs, fl_tab, fu_tab):
    """与 train.py 中 numpy 分支逐行对应的参考实现。"""
    s_e = np.tanh(e / gap)
    d = np.abs(e) - gap
    contact = 0.5 * (1.0 + np.tanh(d / 0.004))
    x_el = np.maximum(d, 0.0)
    rigid = rigid_k * np.maximum(x_el - stroke, 0.0)
    dir_sm = np.tanh(s_e * dv / v_eps)
    fl_x = np.interp(x_el, xs, fl_tab)
    fu_x = np.interp(x_el, xs, fu_tab)
    f0 = 0.5 * (fl_x + fu_x) * gain
    half = 0.5 * (fl_x - fu_x) * gain
    f_imp = np.clip(contact * (f0 - dir_sm * half), 0.0, max_impulse)
    return s_e * (f_imp + rigid)


def _param_arrays(m: int) -> dict:
    p = CouplerParams()
    return dict(
        gap=np.full(m, max(p.coupler_gap_m, 1e-9)),
        v_eps=np.full(m, p.friction_v_eps),
        rigid_k=np.full(m, p.rigid_stiffness_nm),
        stroke=np.full(m, p.stroke_m),
        gain=np.full(m, p.stiffness / STIFFNESS_BASE_N_PER_M),
        max_impulse=np.full(m, p.max_impulse_n),
    )


@pytest.mark.parametrize('m', [1, 217])
def test_kernel_matches_numpy_on_random_states(m):
    """随机状态（含游隙内、接触、行程限位三区）下两实现一致。"""
    rng = np.random.default_rng(20261021)
    pr = _param_arrays(m)
    for _ in range(20):
        e = rng.uniform(-0.15, 0.15, m)     # 覆盖 −150~150 mm 行程
        dv = rng.uniform(-0.6, 0.6, m)
        got = _coupler_force_kernel(
            e, dv, pr['gap'], pr['v_eps'], pr['rigid_k'], pr['stroke'],
            pr['gain'], pr['max_impulse'], RONG2025_X_M, RONG2025_FL_N, RONG2025_FU_N)
        want = _numpy_impl(e, dv, **pr, xs=RONG2025_X_M,
                           fl_tab=RONG2025_FL_N, fu_tab=RONG2025_FU_N)
        np.testing.assert_allclose(got, want, rtol=1e-12, atol=1e-9)


def test_kernel_handles_zero_gap_and_quiescent_state():
    """零相对速度 + 零伸长量（全列静止）时两实现同为 0。"""
    m = 8
    pr = _param_arrays(m)
    e = np.zeros(m)
    dv = np.zeros(m)
    got = _coupler_force_kernel(
        e, dv, pr['gap'], pr['v_eps'], pr['rigid_k'], pr['stroke'],
        pr['gain'], pr['max_impulse'], RONG2025_X_M, RONG2025_FL_N, RONG2025_FU_N)
    want = _numpy_impl(e, dv, **pr, xs=RONG2025_X_M,
                       fl_tab=RONG2025_FL_N, fu_tab=RONG2025_FU_N)
    np.testing.assert_allclose(got, want, rtol=0.0, atol=1e-12)


def test_kernel_saturates_and_rigid_limit_stacks():
    """饱和封顶（max_impulse）与刚性限位力独立叠加的行为一致。"""
    m = 4
    pr = _param_arrays(m)
    e = np.full(m, 0.5)          # 远超行程 → 刚性限位生效
    dv = np.full(m, 5.0)
    got = _coupler_force_kernel(
        e, dv, pr['gap'], pr['v_eps'], pr['rigid_k'], pr['stroke'],
        pr['gain'], pr['max_impulse'], RONG2025_X_M, RONG2025_FL_N, RONG2025_FU_N)
    want = _numpy_impl(e, dv, **pr, xs=RONG2025_X_M,
                       fl_tab=RONG2025_FL_N, fu_tab=RONG2025_FU_N)
    np.testing.assert_allclose(got, want, rtol=1e-12, atol=1e-9)
    assert np.all(got > pr['max_impulse']), '刚性限位力应在饱和封顶之外独立叠加'
