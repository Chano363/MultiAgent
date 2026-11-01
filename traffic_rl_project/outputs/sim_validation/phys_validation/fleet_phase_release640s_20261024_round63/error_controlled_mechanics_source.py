"""Experimental step doubling; never enabled by the production environment.

Raw full-step/two-half-step differences are conservative indicators, not proven
global error bounds. Accepted states are the two-half-step solution; no force
smoothing, Richardson extrapolation, pressure interpolation or law change.
"""
from contextlib import contextmanager

import numpy as np

from src.evaluation import adaptive_newmark_candidate as native
from src.evaluation.newton_mechanics_candidate import newton_trial


def advance(dyn, force, dt, *, max_step=.0025, min_step=.00001,
            force_atol_n=1000., velocity_atol=1e-5, position_atol=1e-6,
            tol=1e-9, max_iter=100, force_tol_n=.01,
            solver='newton_analytic', **extra):
    """Advance one held-input mechanical interval, with whole-interval rollback.

    min_step bounds the coarse trial; its half steps may be half this value.
    All tolerances are diagnostic engineering settings awaiting validation.
    """
    if extra or solver != 'newton_analytic':
        raise ValueError('Only analytic Newton with held native force is supported')
    values = (dt, max_step, min_step, force_atol_n, velocity_atol,
              position_atol, tol, force_tol_n)
    if any(not np.isfinite(v) or v <= 0 for v in values) or min_step > max_step:
        raise ValueError('Positive finite tolerances and ordered steps required')
    if not isinstance(max_iter, int) or max_iter < 1:
        raise ValueError('Positive integer iteration limit required')

    def snapshot():
        return dyn.pos.copy(), dyn.vel.copy(), dyn._acc0.copy(), float(dyn.time)

    def restore(state):
        dyn.pos, dyn.vel, dyn._acc0, dyn.time = (
            state[0].copy(), state[1].copy(), state[2].copy(), state[3])

    stats = dict(attempts=0, accepted=0, rejected=0, newton_calls=0,
                 min_accepted_step_s=float('inf'), max_force_residual_n=0.,
                 peak_interface_n=0., max_accepted_error_ratio=0.)

    def trial(h):
        stats['newton_calls'] += 1
        return newton_trial(dyn, force, h, tol, max_iter, force_tol_n,
                            jacobian='analytic')

    initial = snapshot()
    elapsed, h = 0., min(max_step, dt)
    try:
        while dt - elapsed > max(1e-14, dt * 1e-12):
            h = min(h, dt - elapsed)
            before = snapshot()
            stats['attempts'] += 1
            if stats['attempts'] > 100000:
                raise native.MechanicalConvergenceError('Adaptive attempt budget exceeded')
            ok, _, _ = trial(h)
            coarse = snapshot() if ok else None
            coarse_force = dyn.coupler_interface_forces().copy() if ok else None
            restore(before)
            first_ok, r1, _ = trial(h / 2)
            middle_peak = float(np.max(np.abs(dyn.coupler_interface_forces()))) if first_ok else 0.
            second_ok, r2 = False, float('inf')
            if first_ok:
                second_ok, r2, _ = trial(h / 2)
            ratio = float('inf')
            if coarse is not None and first_ok and second_ok:
                fine_force = dyn.coupler_interface_forces()
                ratio = max(float(np.max(np.abs(dyn.pos-coarse[0]))) / position_atol,
                            float(np.max(np.abs(dyn.vel-coarse[1]))) / velocity_atol,
                            float(np.max(np.abs(fine_force-coarse_force))) / force_atol_n)
            if np.isfinite(ratio) and ratio <= 1:
                stats['accepted'] += 2
                stats['min_accepted_step_s'] = min(stats['min_accepted_step_s'], h/2)
                stats['max_force_residual_n'] = max(stats['max_force_residual_n'], r1, r2)
                stats['max_accepted_error_ratio'] = max(stats['max_accepted_error_ratio'], ratio)
                stats['peak_interface_n'] = max(stats['peak_interface_n'], middle_peak,
                                               float(np.max(np.abs(fine_force))))
                elapsed += h
                if ratio < .125:
                    h = min(2*h, max_step)
            else:
                restore(before)
                stats['rejected'] += 1
                if h/2 < min_step:
                    raise native.MechanicalConvergenceError(
                        f'Time-error tolerance unresolved at t={dyn.time}, h={h}, ratio={ratio}')
                h /= 2
    except BaseException:
        restore(initial)
        raise
    return stats


@contextmanager
def candidate(samples, **settings):
    """Reuse native pneumatic/control transaction boundaries, restore all hooks."""
    original = native.advance_mechanics
    native.advance_mechanics = advance
    try:
        with native.coupled_candidate(samples, numerical_solver='newton_analytic', **settings):
            yield
    finally:
        native.advance_mechanics = original
