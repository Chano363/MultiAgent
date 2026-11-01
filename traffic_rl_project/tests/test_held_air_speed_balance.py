from types import SimpleNamespace

import numpy as np
import pytest

from src.evaluation.held_air_speed_balance import balanced_request, candidate


def state():
    ctrl = SimpleNamespace(_held_air_balance_enabled=True, num_locomotives=1,
        _ab_on=[True], _held_air_gap_reference_m=183.33, AB_SUPPRESS_MARGIN_MPS=.5,
        dt=.1, _ed_frac_for_total_kn=lambda tr, kn: min(1., kn/500.))
    dyn = SimpleNamespace(pos=np.array([0., -10.]), vel=np.array([14., 14.]),
        masses_kg=np.array([1.e6, 9.e6]), _grade_profile=None,
        _grade_forces=lambda: np.array([700000.]),
        _resistance_forces=lambda: np.array([100000.]),
        _air_braking_forces=lambda: np.array([-400000.]))
    target = SimpleNamespace(kind='gap', position_m=500., speed_mps=16.)
    train = SimpleNamespace(dynamics=dyn, etcs_targets=[target])
    return ctrl, train


def test_cumulative_slew_preserves_air_and_original_input():
    ctrl, train = state()
    original = np.array([[1., -.05]])
    previous = 1.
    for _ in range(210):
        result = balanced_request(ctrl, train, np.zeros((1, 2)), original, 20.)
        assert result[0, 1] == -.05
        assert 0 <= result[0, 0] <= 1
        assert previous-result[0, 0] <= .005+1e-12
        previous = result[0, 0]
    assert previous == pytest.approx(0.)
    assert np.array_equal(original, [[1., -.05]])


def test_equilibrium_budget_includes_actual_air_force():
    ctrl, train = state()
    ctrl._held_air_balance_active = True
    ctrl._held_air_balance_previous_ed = .3
    train.etcs_targets[0].speed_mps = 14.
    result = balanced_request(ctrl, train, np.zeros((1, 2)), np.array([[1., -.05]]), 20.)
    assert result[0, 0] == pytest.approx(.4)  # (700-100-400)/500


def test_does_not_raise_a_native_reduced_ed_command():
    ctrl, train = state()
    ctrl._held_air_balance_previous_ed = 1.
    result = balanced_request(ctrl, train, np.zeros((1, 2)), np.array([[.2, -.05]]), 20.)
    assert result[0, 0] == .2


def test_temporary_context_restores_controller_even_on_error():
    from src.controllers.multi_loco_controller import MultiLocoController
    original = MultiLocoController.get_action_decomposed
    with pytest.raises(RuntimeError):
        with candidate():
            assert MultiLocoController.get_action_decomposed is not original
            raise RuntimeError('Test scope exit')
    assert MultiLocoController.get_action_decomposed is original


@pytest.mark.parametrize('condition', ['near', 'faster', 'no_air', 'no_source', 'rl', 'traction', 'disabled'])
def test_ineligible_cases_keep_native_authority(condition):
    ctrl, train = state()
    ctrl._held_air_balance_previous_ed = .2
    ctrl._held_air_balance_active = True
    rl, final = np.zeros((1, 2)), np.array([[1., -.05]])
    if condition == 'near':
        train.etcs_targets[0].position_m = 100.
    elif condition == 'faster':
        train.etcs_targets[0].speed_mps = 10.
    elif condition == 'no_air':
        train.dynamics._air_braking_forces = lambda: np.array([0.])
    elif condition == 'no_source':
        ctrl._ab_on = [False]
    elif condition == 'rl':
        rl[0, 0] = .1
    elif condition == 'traction':
        final[0, 0] = -.1
    else:
        ctrl._held_air_balance_enabled = False
    assert np.array_equal(balanced_request(ctrl, train, rl, final, 20.), final)
