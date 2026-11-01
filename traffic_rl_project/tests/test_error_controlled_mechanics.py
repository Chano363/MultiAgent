"""Independent analytic reference and failed-interval rollback checks."""
import numpy as np
import pytest

from src.evaluation import error_controlled_mechanics as ec
from src.evaluation.adaptive_newmark_candidate import MechanicalConvergenceError


class DampedVehicle:
    def __init__(self):
        self.pos = np.array([0.])
        self.vel = np.array([1.])
        self.masses_kg = np.array([1.])
        self._acc0 = np.array([-10.])
        self.time = 0.
        self.pressure = np.array([123.])

    def _state_forces(self, x, v):
        return -10*v

    def coupler_interface_forces(self):
        return -10*self.vel


@pytest.fixture(autouse=True)
def analytic_toy_jacobian(monkeypatch):
    from src.evaluation import native_force_tangent
    def tangent(dyn, position, velocity, h):
        return np.array([[0.], [1 + 5*h], [0.]])
    monkeypatch.setattr(native_force_tangent, 'acceleration_jacobian', tangent)


def test_adaptive_solution_matches_exponential_and_tightening_improves():
    errors, calls = [], []
    for atol in (1e-3, 1e-5):
        d = DampedVehicle()
        stats = ec.advance(d, np.zeros(1), .2, max_step=.1,
                           velocity_atol=atol, position_atol=atol,
                           force_atol_n=10*atol, force_tol_n=1e-10)
        errors.append(abs(d.vel[0]-np.exp(-2)))
        calls.append(stats['newton_calls'])
        assert d.time == pytest.approx(.2)
        assert d.pos[0] == pytest.approx((1-d.vel[0])/10, abs=1e-12)
        assert d.pressure[0] == 123
        assert stats['max_accepted_error_ratio'] <= 1
    assert errors[1] < errors[0]/5
    assert errors[1] < 1e-4
    assert calls[1] > calls[0]


def test_error_rejection_restores_entire_interval():
    d = DampedVehicle()
    with pytest.raises(MechanicalConvergenceError):
        ec.advance(d, np.zeros(1), .2, max_step=.1, min_step=.05,
                   velocity_atol=1e-15, force_atol_n=1e-15)
    np.testing.assert_array_equal(d.pos, [0.])
    np.testing.assert_array_equal(d.vel, [1.])
    np.testing.assert_array_equal(d._acc0, [-10.])
    assert d.time == 0 and d.pressure[0] == 123


def test_context_restores_mechanical_and_pneumatic_hooks_after_failure():
    native = ec.native
    cls = native.TrainDynamics
    original = (native.advance_mechanics, cls._step_newmark,
                cls._advance_control_once, cls._advance_air_brake_propagation)
    with pytest.raises(RuntimeError):
        with ec.candidate([]):
            raise RuntimeError('deliberate')
    assert original == (native.advance_mechanics, cls._step_newmark,
                        cls._advance_control_once, cls._advance_air_brake_propagation)


def test_failed_mechanics_rolls_back_pneumatic_pressure_and_control_clock(monkeypatch):
    cls = ec.native.TrainDynamics
    d = cls.__new__(cls)
    toy = DampedVehicle()
    d.__dict__.update(toy.__dict__)
    d.control_clock = 9
    d.coupler_interface_forces = lambda: np.zeros(1)
    def pneumatic_then_mechanical(self):
        self.pressure[:] += 12
        self.control_clock += 1
        self._step_newmark(np.zeros(1), .01)
    monkeypatch.setattr(cls, '_advance_control_once', pneumatic_then_mechanical)
    monkeypatch.setattr(ec, 'newton_trial', lambda *a, **kw: (False, 999., 1))
    samples = []
    with ec.candidate(samples, max_step=.01, min_step=.01):
        with pytest.raises(MechanicalConvergenceError):
            d._advance_control_once()
    assert d.pressure[0] == 123 and d.control_clock == 9
    assert d.time == 0 and d.vel[0] == 1
    assert samples == []


def test_resume_selects_recorded_error_solver_and_rejects_unknown():
    from src.evaluation.continue_fleet_numerics import recorded_context
    original = ec.native.advance_mechanics
    with recorded_context([], dict(solver='newton_analytic_time_error', settings={})):
        assert ec.native.advance_mechanics is ec.advance
    assert ec.native.advance_mechanics is original
    with pytest.raises(ValueError, match='Unsupported'):
        recorded_context([], dict(solver='unknown', settings={}))
