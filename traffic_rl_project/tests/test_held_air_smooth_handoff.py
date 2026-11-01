from types import SimpleNamespace

import numpy as np
import pytest

from src.evaluation.held_air_smooth_handoff import smooth_handoff


def state():
    ctrl = SimpleNamespace(_held_air_smooth_handoff_enabled=True,
        _held_air_balance_active=False, num_locomotives=1, _ab_on=[True],
        _held_air_gap_reference_m=183.33, AB_SUPPRESS_MARGIN_MPS=.5, dt=.1)
    train = SimpleNamespace(dynamics=SimpleNamespace(pos=np.array([0.]), vel=np.array([18.])),
        etcs_targets=[SimpleNamespace(kind='gap', position_m=400.)])
    return ctrl, train


def test_gradual_normal_handback_preserves_air():
    ctrl, train = state()
    final = np.array([[1., -.05]])
    previous, was_active = .74, True
    for _ in range(60):
        result = smooth_handoff(ctrl, train, np.zeros((1, 2)), final, previous, was_active, 22.)
        assert 0 <= result[0, 0]-previous <= .005+1e-12
        assert result[0, 1] == -.05
        previous, was_active = result[0, 0], False
    assert previous == pytest.approx(1.)
    assert not ctrl._held_air_handoff_pending
    assert np.array_equal(final, [[1., -.05]])


@pytest.mark.parametrize('condition', ['near_sbi', 'unknown_sbi', 'short_gap', 'rl', 'no_air_source'])
def test_urgent_or_unqualified_handback_is_not_delayed(condition):
    ctrl, train = state()
    ceiling, rl = 22., np.zeros((1, 2))
    if condition == 'near_sbi':
        ceiling = 18.2
    elif condition == 'unknown_sbi':
        ceiling = float('-inf')
    elif condition == 'short_gap':
        train.etcs_targets[0].position_m = 100.
    elif condition == 'rl':
        rl[0, 0] = .1
    else:
        ctrl._ab_on = [False]
    final = np.array([[1., -.05]])
    assert np.array_equal(smooth_handoff(ctrl, train, rl, final, .74, True, ceiling), final)


def test_native_ed_reduction_has_immediate_priority():
    ctrl, train = state()
    ctrl._held_air_handoff_pending = True
    final = np.array([[.2, -.05]])
    assert np.array_equal(smooth_handoff(ctrl, train, np.zeros((1, 2)), final, .74, False, 22.), final)
