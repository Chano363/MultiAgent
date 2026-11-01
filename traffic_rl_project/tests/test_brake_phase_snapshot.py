from dataclasses import FrozenInstanceError
from types import SimpleNamespace as S
import copy

import numpy as np
import pytest

from src.evaluation.brake_phase_snapshot import snapshot
from src.evaluation.phase_release_screen import release_horizon_s


def state():
    return (S(_ab_step=100, _ab_last_release_step=[32], _ab_on=[False],
              dt=.1, ab_min_refill_s=222.),
            S(_brake_pressure=np.ones(2), _air_brake_release_frac=np.array([.6, .8]),
              _air_brake_active=np.array([True, True])))


def test_relief_and_refill_overlap_without_mutating_clock_or_pressure():
    c, d = state()
    before = copy.deepcopy((vars(c), vars(d)))
    phase = snapshot(c, d, mechanical_air_force_n=np.array([-2000., -4000.]))
    assert phase.source_off_with_residual_air and phase.source_off_with_refill_wait
    assert phase.refill_remaining_s == pytest.approx((215.2,))
    assert not phase.ordinary_refill_gate_ready[0]
    assert vars(c) == before[0]
    for key in before[1]:
        np.testing.assert_array_equal(vars(d)[key], before[1][key])
    with pytest.raises(FrozenInstanceError):
        phase.controller_step = 0


def test_no_air_is_not_refill_completion():
    c, d = state()
    phase = snapshot(c, d, mechanical_air_force_n=np.zeros(2))
    assert not phase.source_off_with_residual_air
    assert phase.source_off_with_refill_wait


def test_gate_becomes_ready_at_native_boundary_without_reset():
    c, d = state()
    c._ab_step = 2252
    phase = snapshot(c, d, mechanical_air_force_n=np.zeros(2))
    assert phase.ordinary_refill_gate_ready == (True,)
    assert phase.refill_remaining_s == (0.,)
    assert c._ab_last_release_step == [32]


def test_source_on_during_wait_is_reported_not_blocked():
    c, d = state()
    c._ab_on = [True]  # Observation layer must not veto a safety-owned action.
    phase = snapshot(c, d, mechanical_air_force_n=np.array([-2000., -4000.]))
    assert phase.source_on == (True,)
    assert phase.refill_remaining_s[0] > 0
    assert c._ab_on == [True]


def test_prediction_horizon_keeps_elapsed_wait_and_distinguishes_new_release():
    c, d = state()
    phase = snapshot(c, d, mechanical_air_force_n=np.zeros(2))
    assert release_horizon_s(phase, 222., 20.) == pytest.approx(235.2)
    c._ab_on = [True]
    new_release = snapshot(c, d, mechanical_air_force_n=np.zeros(2))
    assert release_horizon_s(new_release, 222., 20.) == 242.
    assert c._ab_last_release_step == [32]


@pytest.mark.parametrize('invalid', ['future_release', 'nan_force', 'dimension'])
def test_rejects_invalid_observations(invalid):
    c, d = state()
    force = np.zeros(2)
    if invalid == 'future_release':
        c._ab_last_release_step = [101]
    elif invalid == 'nan_force':
        force[0] = np.nan
    else:
        force = np.zeros(3)
    with pytest.raises(ValueError):
        snapshot(c, d, mechanical_air_force_n=force)
