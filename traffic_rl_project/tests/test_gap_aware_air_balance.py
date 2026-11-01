from types import SimpleNamespace

import numpy as np
import pytest

from src.evaluation.gap_aware_air_balance import adjusted_train, candidate
from src.evaluation import held_air_speed_balance


def state(sbi=20.):
    ctrl = SimpleNamespace(_gap_aware_air_enabled=True,
        _held_air_gap_reference_m=183.33, AB_SUPPRESS_MARGIN_MPS=.5)
    target = SimpleNamespace(kind='gap', position_m=500., speed_mps=16.)
    train = SimpleNamespace(dynamics=SimpleNamespace(pos=np.array([0.]), vel=np.array([15.])),
        etcs_targets=[target], etcs_curve=object(),
        safety=SimpleNamespace(_etcs_check=lambda *args: (None, sbi)))
    return ctrl, train


def test_gap_target_does_not_mutate_live_safety_target():
    ctrl, train = state()
    proxy, cap = adjusted_train(ctrl, train, np.zeros((1, 2)), 22.)
    assert proxy.etcs_targets[0].speed_mps == 16.5
    assert train.etcs_targets[0].speed_mps == 16.
    assert proxy.dynamics is train.dynamics
    assert cap == 19.5


def test_operating_and_sbi_limits_bound_target():
    ctrl, train = state(16.3)
    proxy, cap = adjusted_train(ctrl, train, np.zeros((1, 2)), 16.1)
    assert cap == 15.8
    assert proxy.etcs_targets[0].speed_mps == 15.8


def test_near_sbi_refuses_ed_relief():
    ctrl, train = state(15.4)
    proxy, cap = adjusted_train(ctrl, train, np.zeros((1, 2)), 22.)
    assert proxy is train
    assert cap == float('-inf')


@pytest.mark.parametrize('case', ['rl', 'disabled', 'unknown_sbi', 'no_curve'])
def test_native_fallback(case):
    ctrl, train = state(None if case == 'unknown_sbi' else 20.)
    rl = np.zeros((1, 2))
    if case == 'rl':
        rl[0, 0] = .1
    if case == 'disabled':
        ctrl._gap_aware_air_enabled = False
    if case == 'no_curve':
        train.etcs_curve = None
    proxy, cap = adjusted_train(ctrl, train, rl, 22.)
    assert proxy is train and cap == 22.


def test_context_restores_on_error():
    original = held_air_speed_balance.balanced_request
    with pytest.raises(RuntimeError):
        with candidate():
            assert held_air_speed_balance.balanced_request is not original
            raise RuntimeError('scope')
    assert held_air_speed_balance.balanced_request is original
