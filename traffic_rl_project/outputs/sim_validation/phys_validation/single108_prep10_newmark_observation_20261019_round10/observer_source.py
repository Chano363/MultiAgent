"""Read-only observation of the native Newmark stopping criterion."""
from contextlib import contextmanager

import numpy as np

from src.train_dynamics.train import TrainDynamics


@contextmanager
def observe_newmark(samples, after_s=0.0):
    """Recompute the last iteration residual without changing any native result.

    Class methods are restored even on failure. Diagnostic fields live on each
    dynamics instance, so copied native forecasts do not step the live train.
    """
    original_step = TrainDynamics._step_newmark
    original_force = TrainDynamics._state_forces

    def observed_force(self, positions, velocities):
        if getattr(self, '_newmark_observer_active', False):
            self._newmark_observer_x = positions.copy()
            self._newmark_observer_count += 1
        return original_force(self, positions, velocities)

    def observed_step(self, control_forces, dt, max_iter=None, tol=None):
        if self.time < after_s:
            return original_step(self, control_forces, dt, max_iter=max_iter, tol=tol)
        x_n, v_n, a_n = self.pos.copy(), self.vel.copy(), self._acc0.copy()
        self._newmark_observer_active = True
        self._newmark_observer_count = 0
        start = float(self.time)
        try:
            original_step(self, control_forces, dt, max_iter=max_iter, tol=tol)
        finally:
            self._newmark_observer_active = False
        # Native a_p is stored in _acc0 on both convergence and fallback paths.
        x_p = self._newmark_observer_x
        x_cand = x_n + dt * v_n + dt * dt * ((0.5 - 0.25) * a_n + 0.25 * self._acc0)
        x_new = x_p + 0.5 * (x_cand - x_p)
        residual = float(np.max(np.abs(x_new - x_p)))
        tolerance = self.newmark_tol if tol is None else tol
        samples.append([start, dt, self._newmark_observer_count, residual,
                        tolerance, float(residual < tolerance)])

    TrainDynamics._step_newmark = observed_step
    TrainDynamics._state_forces = observed_force
    try:
        yield
    finally:
        TrainDynamics._step_newmark = original_step
        TrainDynamics._state_forces = original_force
