"""Closed-form tests for partial-interval fill, release and upgrade timing."""
import copy
from types import SimpleNamespace

import numpy as np
import pytest

from src.evaluation.fractional_air_timing import (
    advance_fractional_air, fractional_air_timing, fractional_advance_source,
)
from src.train_dynamics.braking import AirBrakeNotch as Notch
from src.train_dynamics.train import TrainDynamics


def state():
    return SimpleNamespace(num_vehicles=1, release_exhaust_tau_s=2.,
        brake_rise_time_s=20., brake_rise_time_by_notch={Notch.CYCLIC:20.,Notch.SERVICE:10.},
        _air_brake_active=np.array([False]), _air_brake_releasing=np.array([False]),
        _brake_pressure=np.array([0.]), _air_brake_release_frac=np.array([1.]),
        _air_brake_exhaust_t=np.array([0.]), _air_brake_delay_remaining=np.array([.003]),
        _air_brake_pending=np.array([Notch.CYCLIC],dtype=object),
        _air_brake_notch=np.array([Notch.RELEASE],dtype=object),
        _air_brake_upgrade_pending=np.array([None],dtype=object),
        _air_brake_upgrade_delay=np.array([0.]), _air_notch_rank=TrainDynamics._air_notch_rank)


def test_arrival_at_three_ms_only_charges_for_seven_ms():
    dyn=state()
    advance_fractional_air(dyn,.01)
    assert dyn._brake_pressure[0] == pytest.approx(.007/20,abs=1e-15)
    native=state()
    TrainDynamics._advance_air_brake_propagation(native,.01)
    # The native caller subsequently charges for the entire .01 s.
    assert native._air_brake_active[0]
    assert .01/20 > dyn._brake_pressure[0]


def test_release_at_four_ms_only_exhausts_for_six_ms():
    dyn=state();dyn._air_brake_pending[:]=None
    dyn._air_brake_active[:]=True;dyn._air_brake_releasing[:]=True
    dyn._brake_pressure[:]=.6;dyn._air_brake_notch[:]=Notch.CYCLIC
    dyn._air_brake_delay_remaining[:]=.004
    advance_fractional_air(dyn,.01)
    assert dyn._air_brake_exhaust_t[0] == pytest.approx(.006,abs=1e-15)
    assert dyn._air_brake_release_frac[0] == pytest.approx(np.exp(-.006/2),abs=1e-15)
    assert dyn._brake_pressure[0] == .6


@pytest.mark.parametrize('releasing',[False,True])
def test_upgrade_splits_old_and_new_pressure_history(releasing):
    dyn=state();dyn._air_brake_pending[:]=None
    dyn._air_brake_active[:]=True;dyn._air_brake_releasing[:]=releasing
    dyn._brake_pressure[:]=.6;dyn._air_brake_notch[:]=Notch.CYCLIC
    dyn._air_brake_delay_remaining[:]=.002
    dyn._air_brake_upgrade_pending[:]=Notch.SERVICE;dyn._air_brake_upgrade_delay[:]=.004
    advance_fractional_air(dyn,.01)
    expected=(.6*np.exp(-.002/2) if releasing else .6+.004/20)+.006/10
    assert dyn._brake_pressure[0] == pytest.approx(expected,abs=1e-14)
    assert not dyn._air_brake_releasing[0]
    assert dyn._air_brake_release_frac[0] == 1


def test_exhaust_completion_then_later_reapplication():
    dyn=state();dyn._air_brake_pending[:]=None
    dyn._air_brake_active[:]=True;dyn._air_brake_releasing[:]=True
    dyn._brake_pressure[:]=.8;dyn._air_brake_notch[:]=Notch.CYCLIC
    dyn._air_brake_delay_remaining[:]=0
    dyn._air_brake_exhaust_t[:]=2*np.log(50)-.003
    dyn._air_brake_release_frac[:]=np.exp(-dyn._air_brake_exhaust_t/2)
    dyn._air_brake_upgrade_pending[:]=Notch.SERVICE;dyn._air_brake_upgrade_delay[:]=.006
    advance_fractional_air(dyn,.01)
    assert dyn._brake_pressure[0] == pytest.approx(.004/10,abs=1e-14)


def test_pressure_solution_is_invariant_to_interval_partition():
    a=state();a._air_brake_upgrade_pending[:]=Notch.SERVICE
    a._air_brake_upgrade_delay[:]=.0073
    b=copy.deepcopy(a)
    advance_fractional_air(a,.01)
    for _ in range(10):advance_fractional_air(b,.001)
    for key in ('_brake_pressure','_air_brake_release_frac','_air_brake_exhaust_t'):
        np.testing.assert_allclose(getattr(a,key),getattr(b,key),rtol=0,atol=1e-14)
    for key in ('_air_brake_active','_air_brake_pending','_air_brake_upgrade_pending','_air_brake_notch'):
        np.testing.assert_array_equal(getattr(a,key),getattr(b,key))


def test_generated_native_caller_removes_double_charging_and_context_restores():
    source=fractional_advance_source()
    assert 'self._brake_pressure + h / rise_times' not in source
    assert 'self._apply_air_brake_command' in source
    methods=TrainDynamics._advance_control_once,TrainDynamics._advance_air_brake_propagation
    with pytest.raises(RuntimeError):
        with fractional_air_timing(True):raise RuntimeError('abort')
    assert methods==(TrainDynamics._advance_control_once,TrainDynamics._advance_air_brake_propagation)


def caller_state():
    from types import MethodType
    dyn=state()
    dyn._ab_delay_queue=[];dyn.mid_source_delay_s=0
    dyn._advance_air_brake_propagation=MethodType(advance_fractional_air,dyn)
    dyn._tractive_forces_per_vehicle=lambda t:np.zeros(1)
    dyn._electric_braking_forces=lambda e:np.zeros(1)
    dyn._air_braking_forces=lambda:np.zeros(1)
    dyn._step_newmark=lambda f,h:None
    dyn._update_grade_from_profile=lambda:None
    return dyn


def test_generated_native_caller_does_not_charge_twice():
    dyn=caller_state()
    with fractional_air_timing(True):
        TrainDynamics._advance_control_once(dyn,None,None,None,0,None,False,.01,False)
    assert dyn._brake_pressure[0] == pytest.approx(.007/20,abs=1e-15)


def test_mechanical_failure_rolls_back_fractional_pressure_and_wave():
    from src.evaluation.adaptive_newmark_candidate import coupled_candidate
    dyn=caller_state()
    def fail(f,h):raise RuntimeError('mechanics failed')
    dyn._step_newmark=fail
    with fractional_air_timing(True),coupled_candidate([]):
        with pytest.raises(RuntimeError,match='mechanics failed'):
            TrainDynamics._advance_control_once(dyn,None,None,None,0,None,False,.01,False)
    assert dyn._brake_pressure[0] == 0
    assert not dyn._air_brake_active[0]
    assert dyn._air_brake_pending[0] is Notch.CYCLIC
    assert dyn._air_brake_delay_remaining[0] == .003


@pytest.mark.parametrize('dt',[-1,float('nan')])
def test_invalid_time_rejected(dt):
    with pytest.raises(ValueError):advance_fractional_air(state(),dt)
