"""Experimental mechanical step rejection; never installed as a production default.

Only pos/vel/acc/time are advanced by native _step_newmark. Pneumatic state
must be advanced outside this routine exactly once per original input interval.
"""
import numpy as np

from src.evaluation.newmark_observer import observe_newmark


class MechanicalConvergenceError(RuntimeError):
    """A rejected mechanical interval could not be resolved within the limit."""


def advance_mechanics(dyn, force, dt, *, max_step=0.00125, min_step=0.00001,
                      tol=1e-9, max_iter=100, force_tol_n=100.0, on_accept=None):
    """Reject unconverged trials and recursively bisect with transactional rollback.

    Numerical tolerances are engineering diagnostics, not vehicle parameters.
    The end-state force-equilibrium residual adds a separate force-unit check
    to the native displacement stopping test. Passing both is not an error bound.
    """
    values = (dt, max_step, min_step, tol, force_tol_n)
    if any(not np.isfinite(x) or x <= 0 for x in values) or min_step > max_step:
        raise ValueError('Positive finite step sizes and tolerances required')
    if not isinstance(max_iter, int) or max_iter < 1:
        raise ValueError('Positive integer iteration limit required')
    stats = {'attempts': 0, 'rejected': 0, 'accepted': 0,
             'min_accepted_step_s': float('inf'), 'max_force_residual_n': 0.0,
             'peak_interface_n': 0.0}

    def state():
        return dyn.pos.copy(), dyn.vel.copy(), dyn._acc0.copy(), float(dyn.time)

    def restore(saved):
        dyn.pos, dyn.vel, dyn._acc0, dyn.time = saved

    def step(h):
        saved = state()
        samples = []
        with observe_newmark(samples):
            dyn._step_newmark(force, h, tol=tol, max_iter=max_iter)
        stats['attempts'] += 1
        imbalance = float(np.max(np.abs(dyn.masses_kg * dyn._acc0
                                        - force - dyn._state_forces(dyn.pos, dyn.vel))))
        finite = all(np.all(np.isfinite(a)) for a in (dyn.pos, dyn.vel, dyn._acc0))
        converged = bool(samples[-1][5]) and finite and imbalance <= force_tol_n
        if converged:
            stats['accepted'] += 1
            stats['min_accepted_step_s'] = min(stats['min_accepted_step_s'], h)
            stats['max_force_residual_n'] = max(stats['max_force_residual_n'], imbalance)
            stats['peak_interface_n'] = max(stats['peak_interface_n'], float(
                np.max(np.abs(dyn.coupler_interface_forces()))))
            if on_accept is not None:
                on_accept(dyn, h, imbalance)
            return
        restore(saved)
        stats['rejected'] += 1
        if h / 2 < min_step:
            raise MechanicalConvergenceError(
                f'No converged step at t={dyn.time}, h={h}, force residual={imbalance}')
        step(h / 2)
        step(h / 2)

    initial = state()
    try:
        count = max(1, int(np.ceil(dt / max_step)))
        for _ in range(count):
            step(dt / count)
    except BaseException:
        # Roll back the entire requested interval, including accepted first halves.
        restore(initial)
        raise
    return stats
