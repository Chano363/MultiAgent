"""Fixed-force trial preserves native clocks and yields to RL/safety."""
from types import SimpleNamespace

import numpy as np
import pytest

from src.evaluation.pre_release_fixed_ed import request


def make_case():
    dyn = SimpleNamespace(pos=np.array([1000.]), vel=np.array([58./3.6]),
        _brake_pressure=np.ones(1), _air_brake_release_frac=np.ones(1))
    train = SimpleNamespace(dynamics=dyn, etcs_curve=object(), etcs_targets=[object()],
        safety=SimpleNamespace(_etcs_check=lambda *args: (False, 80./3.6)))
    ctrl = SimpleNamespace(_pre_release_fixed_ed_enabled=True, num_locomotives=1,
        _ed_hold_steps=0, _cyclic_braking=True, _ab_on=[True], dt=.1,
        AB_SUPPRESS_MARGIN_MPS=.5,
        _operating_ceiling=lambda *args: 80./3.6,
        _ed_frac_for_total_kn=lambda train, force: force/600.)
    return ctrl, train


def test_prepare_gradually_and_preserve_air_and_clock():
    ctrl, train = make_case()
    final = np.array([[1., -.05]])
    first = request(ctrl, train, np.zeros((1, 2)), final)
    second = request(ctrl, train, np.zeros((1, 2)), final)
    assert first[0, 0] == pytest.approx(.995)
    assert second[0, 0] == pytest.approx(.990)
    assert np.array_equal(final, [[1., -.05]])
    assert second[0, 1] == -.05 and ctrl._ab_on == [True]
    assert ctrl._ed_hold_steps == 0


def test_plateau_uses_force_mapping_without_resetting_hold_then_exits():
    ctrl, train = make_case()
    ctrl._pre_release_fixed_ed_armed = True
    ctrl._ed_hold_steps, ctrl._cyclic_braking, ctrl._ab_on = 499, False, [False]
    actual = request(ctrl, train, np.zeros((1, 2)), [[1., 0.]])
    assert actual[0, 0] == pytest.approx(350./600)
    assert ctrl._ed_hold_steps == 499 and ctrl._ab_on == [False]
    ctrl._ed_hold_steps = 0
    assert np.array_equal(request(ctrl, train, np.zeros((1, 2)), [[1., 0.]]), [[1., 0.]])
    assert ctrl._pre_release_fixed_ed_done


def test_leader_without_predecessor_targets_uses_native_operating_ceiling():
    ctrl, train = make_case()
    train.etcs_targets = []
    assert request(ctrl, train, np.zeros((1, 2)), [[1., -.05]])[0, 0] == pytest.approx(.995)


@pytest.mark.parametrize('case', ['rl', 'safety', 'unestablished', 'disabled'])
def test_outside_trial_authority_preserves_native_request(case):
    ctrl, train = make_case()
    rl = np.zeros((1, 2))
    if case == 'rl':
        rl[0, 0] = .1
    elif case == 'safety':
        train.safety._etcs_check = lambda *args: (True, 58./3.6)
    elif case == 'unestablished':
        train.dynamics._brake_pressure[:] = .5
    else:
        ctrl._pre_release_fixed_ed_enabled = False
    assert np.array_equal(request(ctrl, train, rl, [[1., -.05]]), [[1., -.05]])
