"""Preserve native clocks and smooth handback before the air-source edge."""
from types import SimpleNamespace

import numpy as np
import pytest

from src.evaluation import held_air_speed_balance as balance
from src.evaluation.held_air_smooth_handoff import smooth_handoff
from src.evaluation.pre_release_chase_exit import candidate


def case():
    ctrl = SimpleNamespace(_pre_release_chase_exit_enabled=True,
        _pre_release_chase_exit_done=False, _ab_on=[True], _ab_step=120,
        _ab_last_release_step=[10], ab_min_refill_s=222., dt=.1,
        cyclic_brake_trigger_kmh=65., _held_air_balance_enabled=True,
        _held_air_balance_active=True, _held_air_smooth_handoff_enabled=True,
        _held_air_gap_reference_m=183.33, num_locomotives=1, AB_SUPPRESS_MARGIN_MPS=.5)
    train = SimpleNamespace(dynamics=SimpleNamespace(vel=np.array([60./3.6]), pos=np.array([100.])),
        etcs_targets=[SimpleNamespace(position_m=1000., kind='gap')])
    return ctrl, train


def test_exit_arms_existing_smooth_handoff_without_resetting_source_clocks(monkeypatch):
    ctrl, train = case()
    monkeypatch.setattr(balance, 'balanced_request', lambda c, t, r, f, cap: np.asarray(f).copy())
    final = np.array([[1., -.05]])
    with candidate():
        raw = balance.balanced_request(ctrl, train, np.zeros((1, 2)), final, 80./3.6)
    assert not ctrl._held_air_balance_active
    assert ctrl._held_air_balance_enabled
    smoothed = smooth_handoff(ctrl, train, np.zeros((1, 2)), raw, .3, True, 80./3.6)
    assert smoothed[0, 0] == pytest.approx(.305)
    assert smoothed[0, 1] == -.05
    assert ctrl._ab_on == [True] and ctrl._ab_step == 120
    assert ctrl._ab_last_release_step == [10] and ctrl.ab_min_refill_s == 222.


def test_disable_flag_is_restored_even_when_nested_controller_raises(monkeypatch):
    ctrl, train = case()
    def fail(*args):
        raise RuntimeError('injected')
    monkeypatch.setattr(balance, 'balanced_request', fail)
    with pytest.raises(RuntimeError), candidate():
        balance.balanced_request(ctrl, train, np.zeros((1, 2)), [[1., -.05]], 80./3.6)
    assert ctrl._held_air_balance_enabled
    assert balance.balanced_request is fail


def test_one_cycle_gate_does_not_suppress_later_cycles(monkeypatch):
    ctrl, train = case()
    observed = []
    def original(c, *args):
        observed.append(c._held_air_balance_enabled)
        return np.array([[1., 0.]])
    monkeypatch.setattr(balance, 'balanced_request', original)
    with candidate():
        ctrl._ab_on = [False]
        balance.balanced_request(ctrl, train, np.zeros((1, 2)), [[1., 0.]], 80./3.6)
        ctrl._ab_on = [True]
        balance.balanced_request(ctrl, train, np.zeros((1, 2)), [[1., -.05]], 80./3.6)
    assert ctrl._pre_release_chase_exit_done and observed == [True, True]
