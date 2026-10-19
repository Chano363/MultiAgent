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
