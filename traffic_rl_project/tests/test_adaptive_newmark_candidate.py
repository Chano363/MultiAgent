"""Transactional rejection and independent force-residual acceptance."""
from contextlib import contextmanager

import numpy as np
import pytest

from src.evaluation import adaptive_newmark_candidate as candidate


class ToyDynamics:
    def __init__(self, fail_second=False):
        self.pos = np.array([0.0])
        self.vel = np.array([1.0])
        self._acc0 = np.array([0.0])
        self.masses_kg = np.array([1000.0])
        self.time = 0.0
        self.fail_second = fail_second
        self.pressure = np.array([123.0])

    def _step_newmark(self, force, dt, **kwargs):
        if self.fail_second and self.time >= 0.005:
            raise RuntimeError('second half failed')
        self.pos += dt
        self.time += dt
        self._acc0[:] = 1.0 if dt > 0.005 else 0.0

    def _state_forces(self, pos, vel):
        return np.zeros(1)

    def coupler_interface_forces(self):
        return np.array([2.0])


@contextmanager
def satisfied_displacement(samples):
    # Displacement alone passes even when the force equation fails.
    samples.append([0, 0, 1, 0, 1e-9, 1])
    yield


def test_force_failure_rejects_and_retries_from_original_state(monkeypatch):
    monkeypatch.setattr(candidate, 'observe_newmark', satisfied_displacement)
    dyn = ToyDynamics()
    stats = candidate.advance_mechanics(dyn, np.zeros(1), 0.01,
                                       max_step=0.01, min_step=0.005)
    assert stats['rejected'] == 1 and stats['accepted'] == 2
    assert dyn.time == pytest.approx(0.01)
    assert dyn.pos[0] == pytest.approx(0.01)
    assert dyn.pressure[0] == 123.0


def test_exception_rolls_back_already_accepted_first_half(monkeypatch):
    monkeypatch.setattr(candidate, 'observe_newmark', satisfied_displacement)
    dyn = ToyDynamics(fail_second=True)
    with pytest.raises(RuntimeError, match='second half failed'):
        candidate.advance_mechanics(dyn, np.zeros(1), 0.01,
                                    max_step=0.01, min_step=0.005)
    assert dyn.time == 0
    assert dyn.pos[0] == 0 and dyn.vel[0] == 1 and dyn._acc0[0] == 0


def test_minimum_step_failure_restores_interval(monkeypatch):
    monkeypatch.setattr(candidate, 'observe_newmark', satisfied_displacement)
    dyn = ToyDynamics()
    with pytest.raises(candidate.MechanicalConvergenceError):
        candidate.advance_mechanics(dyn, np.zeros(1), 0.01,
                                    max_step=0.01, min_step=0.01)
    assert dyn.time == 0 and dyn.pos[0] == 0


@pytest.mark.parametrize('solver', ['balanced', 'newton'])
def test_balanced_solver_matches_analytic_linear_newmark_step(solver):
    dyn = ToyDynamics()
    dyn.pos[:] = 1.0
    dyn.vel[:] = 2.0
    dyn._acc0[:] = -4.0
    dyn.masses_kg[:] = 2.0
    dyn._state_forces = lambda x, v: -8.0 * x
    h = 0.1
    expected_a = -4 * (1 + h * 2 + 0.25 * h * h * (-4)) / (1 + h * h)
    expected_x = 1 + h * 2 + 0.25 * h * h * (-4 + expected_a)
    expected_v = 2 + 0.5 * h * (-4 + expected_a)
    stat = candidate.advance_mechanics(dyn, np.zeros(1), h, max_step=h,
                                      solver=solver, tol=1e-12, force_tol_n=1e-11)
    assert stat['rejected'] == 0
    assert dyn.pos[0] == pytest.approx(expected_x, abs=1e-11)
    assert dyn.vel[0] == pytest.approx(expected_v, abs=1e-11)
    assert dyn._acc0[0] == pytest.approx(expected_a, abs=1e-9)


def test_balanced_solver_does_not_accept_small_displacement_with_large_force_error():
    dyn = ToyDynamics()
    stat = candidate.advance_mechanics(dyn, np.array([200.0]), 1e-4,
                                      max_step=1e-4, solver='balanced', tol=1e-9,
                                      force_tol_n=0.001)
    assert stat['max_force_residual_n'] <= 0.001
    assert dyn._acc0[0] == pytest.approx(0.2, abs=1e-6)


def test_frozen_forecast_relocation_changes_only_its_output_line():
    from pathlib import Path
    from src.evaluation.diagnose_balanced_cold import relocate_forecast_archive
    original = "before\n            directory = _PredictionPath('old/release_predictions')\nafter\n"
    expected = "before\n            directory = _PredictionPath('fresh/run/release_predictions')\nafter\n"
    assert relocate_forecast_archive(original, Path('fresh/run')) == expected
    with pytest.raises(ValueError):
        relocate_forecast_archive('unexpected source', Path('fresh'))


def test_banded_newton_matches_independent_three_mass_matrix_solution():
    dyn = ToyDynamics()
    mass = np.array([2., 3., 4.])
    stiffness = np.array([[4., -1., 0.], [-1., 5., -2.], [0., -2., 6.]])
    damping = np.diag([0.1, 0.2, 0.3])
    x, v = np.array([1., 1.1, 1.2]), np.full(3, 2.)
    a0 = (-stiffness @ x - damping @ v) / mass
    dyn.pos, dyn.vel, dyn._acc0, dyn.masses_kg = x.copy(), v.copy(), a0.copy(), mass
    dyn._state_forces = lambda x, v: -stiffness @ x - damping @ v
    h = 0.1
    rhs = -stiffness @ (x + h*v + 0.25*h*h*a0) - damping @ (v + 0.5*h*a0)
    expected = np.linalg.solve(np.diag(mass) + 0.25*h*h*stiffness + 0.5*h*damping, rhs)
    stat = candidate.advance_mechanics(dyn, np.zeros(3), h, max_step=h,
        solver='newton', tol=1e-12, force_tol_n=1e-9)
    np.testing.assert_allclose(dyn._acc0, expected, atol=1e-9, rtol=0)
    assert stat['rejected'] == 0
