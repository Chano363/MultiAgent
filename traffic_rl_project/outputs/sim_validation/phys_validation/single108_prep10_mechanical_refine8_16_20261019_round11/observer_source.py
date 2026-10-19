"""Read-only observation of the native Newmark stopping criterion."""
from contextlib import contextmanager
import copy

import numpy as np

from src.train_dynamics.train import TrainDynamics


@contextmanager
def observe_newmark(samples, after_s=0.0, capture=None):
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
        if capture is not None:
            if 'initial_dynamics' not in capture:
                capture['initial_dynamics'] = copy.deepcopy(self)
                for key in ('control_forces', 'grade', 'dt', 'positions', 'velocities', 'peak_n'):
                    capture[key] = []
            capture['control_forces'].append(control_forces.copy())
            capture['grade'].append(self.grade.copy())
            capture['dt'].append(float(dt))
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
        if capture is not None:
            capture['positions'].append(self.pos.copy())
            capture['velocities'].append(self.vel.copy())
            capture['peak_n'].append(float(np.abs(self.coupler_interface_forces()).max()))

    TrainDynamics._step_newmark = observed_step
    TrainDynamics._state_forces = observed_force
    try:
        yield
    finally:
        TrainDynamics._step_newmark = original_step
        TrainDynamics._state_forces = original_force


def replay_fixed_mechanics(capture, subdivisions=(1, 2, 4)):
    """Refine mechanics with identical recorded force/grade inputs.

    Pneumatics and controller feedback are not rerun. This is a numerical
    shadow comparison, never a controller performance or safety acceptance.
    """
    results = []
    for factor in subdivisions:
        if not isinstance(factor, int) or factor < 1:
            raise ValueError('Positive integer subdivision required')
        dyn = copy.deepcopy(capture['initial_dynamics'])
        samples, positions, velocities, peaks, aligned_peaks = [], [], [], [], []
        with observe_newmark(samples):
            for force, grade, dt in zip(capture['control_forces'], capture['grade'], capture['dt']):
                dyn.grade = grade.copy()
                for _ in range(factor):
                    dyn._step_newmark(force, dt / factor)
                    peaks.append(float(np.abs(dyn.coupler_interface_forces()).max()))
                positions.append(dyn.pos.copy())
                velocities.append(dyn.vel.copy())
                aligned_peaks.append(peaks[-1])
        stats = np.asarray(samples)
        positions, velocities = np.asarray(positions), np.asarray(velocities)
        exact = (np.array_equal(positions, np.asarray(capture['positions']))
                 and np.array_equal(velocities, np.asarray(capture['velocities']))
                 and np.array_equal(aligned_peaks, capture['peak_n']))
        results.append({'subdivision': factor, 'native_replay_exact': bool(exact),
            'substeps': len(stats), 'unconverged_substeps': int(np.sum(stats[:, 5] == 0)),
            'max_residual_m': float(stats[:, 3].max()), 'peak_kn': float(np.max(peaks)/1000),
            'aligned_force_max_difference_kn': float(np.max(np.abs(
                np.asarray(aligned_peaks)-capture['peak_n']))/1000),
            'positions': positions, 'velocities': velocities,
            'aligned_peak_n': np.asarray(aligned_peaks), 'iterations': stats})
    return results
