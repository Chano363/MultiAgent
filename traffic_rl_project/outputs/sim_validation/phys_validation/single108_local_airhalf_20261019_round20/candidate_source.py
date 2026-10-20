"""Experimental mechanical step rejection; never installed as a production default.

Only pos/vel/acc/time are advanced by native _step_newmark. Pneumatic state
must be advanced outside this routine exactly once per original input interval.
"""
import numpy as np
import copy
from contextlib import contextmanager

from src.evaluation.newmark_observer import observe_newmark
from src.train_dynamics.train import TrainDynamics


class MechanicalConvergenceError(RuntimeError):
    """A rejected mechanical interval could not be resolved within the limit."""


def balanced_trial(dyn, force, h, tol, max_iter, force_tol_n):
    """Iterate acceleration; do not stop on displacement alone at tiny h.

    Kinematics are formed from local increments, avoiding subtraction of two
    large absolute track positions when measuring iteration convergence.
    No force law, damping, mass, or Newmark beta/gamma is changed.
    """
    x, v, a0 = dyn.pos.copy(), dyn.vel.copy(), dyn._acc0.copy()
    a = a0.copy()
    for iteration in range(1, max_iter + 1):
        position = x + h * v + h * h * (0.25 * a0 + 0.25 * a)
        velocity = v + 0.5 * h * (a0 + a)
        rhs = (force + dyn._state_forces(position, velocity)) / dyn.masses_kg
        delta = rhs - a
        residual = float(np.max(np.abs(dyn.masses_kg * delta)))
        displacement_residual = float(np.max(np.abs(0.25 * h * h * delta)))
        if (np.all(np.isfinite(rhs)) and residual <= force_tol_n
                and displacement_residual <= tol and np.all(velocity >= 0)):
            dyn.pos, dyn.vel, dyn._acc0 = position, velocity, a.copy()
            dyn.time += h
            return True, residual, iteration
        a += 0.5 * delta
    return False, residual, max_iter


def advance_mechanics(dyn, force, dt, *, max_step=0.00125, min_step=0.00001,
                      tol=1e-9, max_iter=100, force_tol_n=100.0, on_accept=None,
                      solver='native'):
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
    if solver not in ('native', 'balanced', 'newton', 'newton_analytic'):
        raise ValueError('Unknown diagnostic solver')
    stats = {'attempts': 0, 'rejected': 0, 'accepted': 0,
             'min_accepted_step_s': float('inf'), 'max_force_residual_n': 0.0,
             'peak_interface_n': 0.0}

    def state():
        return dyn.pos.copy(), dyn.vel.copy(), dyn._acc0.copy(), float(dyn.time)

    def restore(saved):
        dyn.pos, dyn.vel, dyn._acc0, dyn.time = saved

    def step(h):
        saved = state()
        if solver in ('newton', 'newton_analytic'):
            from src.evaluation.newton_mechanics_candidate import newton_trial
            converged, imbalance, _ = newton_trial(dyn, force, h, tol, max_iter, force_tol_n,
                jacobian='analytic' if solver == 'newton_analytic' else 'finite_difference')
        elif solver == 'balanced':
            converged, imbalance, _ = balanced_trial(dyn, force, h, tol, max_iter, force_tol_n)
        else:
            samples = []
            with observe_newmark(samples):
                dyn._step_newmark(force, h, tol=tol, max_iter=max_iter)
            imbalance = float(np.max(np.abs(dyn.masses_kg * dyn._acc0
                                            - force - dyn._state_forces(dyn.pos, dyn.vel))))
            converged = bool(samples[-1][5]) and imbalance <= force_tol_n
        stats['attempts'] += 1
        finite = all(np.all(np.isfinite(a)) for a in (dyn.pos, dyn.vel, dyn._acc0))
        converged = converged and finite
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


@contextmanager
def coupled_candidate(samples, live_dynamics=None, numerical_solver='balanced', **settings):
    """Diagnostic hook: retain native pneumatic interval and transactional retry.

    The whole original pneumatic/mechanical substep is rolled back on failure;
    rejected mechanical trials never advance pressure or command timers twice.
    Native control interval remains unchanged. This is not a production option.
    """
    original_step = TrainDynamics._step_newmark
    original_advance = TrainDynamics._advance_control_once

    def mechanical(self, force, dt, max_iter=None, tol=None):
        result = advance_mechanics(self, force, dt, solver=numerical_solver, **settings)
        if live_dynamics is not None:
            result['live'] = self in live_dynamics
        samples.append(result)

    def transaction(self, *args, **kwargs):
        snapshot = copy.deepcopy(self.__dict__)
        sample_count = len(samples)
        try:
            return original_advance(self, *args, **kwargs)
        except BaseException:
            self.__dict__.clear()
            self.__dict__.update(snapshot)
            del samples[sample_count:]
            raise

    TrainDynamics._step_newmark = mechanical
    TrainDynamics._advance_control_once = transaction
    try:
        yield
    finally:
        TrainDynamics._step_newmark = original_step
        TrainDynamics._advance_control_once = original_advance
