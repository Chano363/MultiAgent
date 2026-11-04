"""Single source of truth for which mechanical solver actually ran.

Production numerics are the unmodified ``TrainDynamics._step_newmark``
Newmark-beta Picard integrator (``newmark_max_iter=30``, ``newmark_tol=1e-5``).
Experimental solvers stay available for numerical studies, but they are
opt-in and must be labelled here so archived metadata cannot silently claim
production numerics while running a replacement.

Nothing in this module changes physics; it only observes and labels it.
"""
from contextlib import contextmanager, nullcontext

from src.train_dynamics.train import TrainDynamics

PRODUCTION_SOLVER = 'production_newmark'
EXPERIMENTAL_SOLVERS = ('newton_analytic', 'newton_analytic_time_error', 'balanced',
                        'native_newmark_fine', 'newmark_picard_force',
                        'newmark_newton_displacement')
SOLVERS = (PRODUCTION_SOLVER,) + EXPERIMENTAL_SOLVERS

# Captured at import time, before any diagnostic wrapper can patch the class.
PRODUCTION_STEP_NEWMARK = TrainDynamics._step_newmark

# Read-only observers wrap the production step to recompute its residual but
# always delegate to it unchanged. They are not replacements and must not
# relabel production numerics as an experimental solver.
PURE_OBSERVERS = set()

_ACTIVE_LABEL = None


def solver_is_production() -> bool:
    """True when the production integrator, or a pure observer of it, is active."""
    step = TrainDynamics._step_newmark
    return step is PRODUCTION_STEP_NEWMARK or step in PURE_OBSERVERS


def active_solver_label() -> str:
    """Label the implementation that is installed right now.

    An unregistered replacement is reported explicitly rather than being
    allowed to pass as production.
    """
    if solver_is_production():
        if _ACTIVE_LABEL is not None:
            raise RuntimeError(
                f'Solver label {_ACTIVE_LABEL!r} declared while production '
                'Newmark is active')
        return PRODUCTION_SOLVER
    return _ACTIVE_LABEL or 'unregistered_replacement'


def runtime_solver_record(dyn=None) -> dict:
    """Metadata fragment describing the integrator that actually ran."""
    record = {'solver': active_solver_label()}
    if dyn is not None:
        record.update(newmark_max_iter=getattr(dyn, 'newmark_max_iter', None),
                      newmark_tol=getattr(dyn, 'newmark_tol', None),
                      newmark_mechanical_max_step=getattr(
                          dyn, 'mechanical_max_step', None))
    return record


def assert_active_solver(expected: str) -> None:
    """Refuse to archive a run whose label does not match the implementation."""
    if expected not in SOLVERS:
        raise ValueError(f'Unknown solver {expected!r}; expected one of {SOLVERS}')
    actual = active_solver_label()
    if actual != expected:
        raise RuntimeError(
            f'Requested solver {expected!r} but the active implementation is '
            f'{actual!r}; refusing to mislabel archived metadata')


@contextmanager
def labelled(label: str):
    """Declare the experimental solver installed by a diagnostic wrapper."""
    global _ACTIVE_LABEL
    if label not in EXPERIMENTAL_SOLVERS:
        raise ValueError(f'Experimental label required; got {label!r}')
    previous = _ACTIVE_LABEL
    _ACTIVE_LABEL = label
    try:
        yield
    finally:
        _ACTIVE_LABEL = previous


@contextmanager
def fine_substep_context(max_step: float):
    """Run the production integrator with a smaller internal substep.

    The force is held constant over the control interval, exactly as
    production does; only the mechanical substep is refined.
    """
    import numpy as np

    original = TrainDynamics._step_newmark

    def refined(self, force, dt, max_iter=None, tol=None):
        count = max(1, int(np.ceil(dt / max_step)))
        for _ in range(count):
            original(self, force, dt / count,
                     max_iter=30 if max_iter is None else max_iter,
                     tol=1e-5 if tol is None else tol)

    TrainDynamics._step_newmark = refined
    try:
        yield
    finally:
        TrainDynamics._step_newmark = original


@contextmanager
def fine_substep_observed_context(samples, max_step=0.0025, tol=1e-5, max_iter=30):
    """Refine the production substep and record its native convergence test."""
    import numpy as np
    from src.evaluation.newmark_observer import observe_newmark

    with observe_newmark(samples):
        observed = TrainDynamics._step_newmark

        def refined(self, force, dt, max_iter_=None, tol_=None):
            count = max(1, int(np.ceil(dt / max_step)))
            for _ in range(count):
                observed(self, force, dt / count,
                         max_iter=max_iter if max_iter_ is None else max_iter_,
                         tol=tol if tol_ is None else tol_)

        TrainDynamics._step_newmark = refined
        try:
            yield
        finally:
            TrainDynamics._step_newmark = observed


@contextmanager
def picard_force_context(samples, force_tol_n=0.01, max_iter=100):
    """Production Newmark formula and Picard under-relaxation, force criterion.

    Only the stopping test changes: the relaxed displacement increment of
    production is replaced by the end-of-iteration interface force residual.
    The non-converged fallback keeps production's relaxed state.
    """
    import numpy as np

    original = TrainDynamics._step_newmark

    def stepped(self, force, dt, max_iter_=None, tol=None):
        iterations = max_iter if max_iter_ is None else max_iter_
        a = self.masses_kg
        beta, gamma = 0.25, 0.5
        x_n, v_n, a_n = self.pos.copy(), self.vel.copy(), self._acc0.copy()
        x_p = x_n + dt * v_n + dt * dt * (0.5 - beta) * a_n
        v_p = v_n + dt * (1.0 - gamma) * a_n
        alpha = 0.5
        x_final = v_final = None
        converged = False
        residual = float('inf')
        iteration = 0
        for iteration in range(1, iterations + 1):
            a_p = (force + self._state_forces(x_p, v_p)) / a
            v_cand = v_n + dt * ((1.0 - gamma) * a_n + gamma * a_p)
            x_cand = x_n + dt * v_n + dt * dt * ((0.5 - beta) * a_n + beta * a_p)
            residual = float(np.max(np.abs(
                a * a_p - force - self._state_forces(x_cand, v_cand))))
            if residual <= force_tol_n:
                x_final, v_final, converged = x_cand, v_cand, True
                break
            v_new = v_p + alpha * (v_cand - v_p)
            x_new = x_p + alpha * (x_cand - x_p)
            x_p, v_p = x_new, v_new
        if not converged:
            x_final, v_final = x_new, v_new
        v_final = np.maximum(v_final, 0.0)
        self.pos, self.vel, self._acc0 = x_final, v_final, a_p
        self.time += dt
        samples.append(dict(substeps=1, converged=converged, iterations=iteration,
                            force_residual_n=residual, applied='picard_relaxed'))

    TrainDynamics._step_newmark = stepped
    try:
        yield
    finally:
        TrainDynamics._step_newmark = original


@contextmanager
def newton_displacement_context(samples, tol=1e-5, max_iter=30):
    """Analytic Newton iteration with production's displacement-only criterion.

    Step size, tolerance and the non-converged fallback are unchanged; only
    Picard is replaced. Failed Newton tries fall back to the production step
    so the comparison does not silently add step bisection.
    """
    original = TrainDynamics._step_newmark

    def stepped(self, force, dt, max_iter_=None, tol_=None):
        iterations = max_iter if max_iter_ is None else max_iter_
        criterion = tol if tol_ is None else tol_
        from src.evaluation.newton_mechanics_candidate import newton_trial
        converged, imbalance, iteration = newton_trial(
            self, force, dt, criterion, iterations, 1e12, jacobian='analytic')
        if not converged:
            original(self, force, dt, max_iter=iterations, tol=criterion)
        samples.append(dict(substeps=1, converged=converged, iterations=iteration,
                            force_residual_n=imbalance, applied='production_fallback'
                            if not converged else 'newton'))

    TrainDynamics._step_newmark = stepped
    try:
        yield
    finally:
        TrainDynamics._step_newmark = original


@contextmanager
def solver_context(solver: str, samples=None, **settings):
    """Install the requested solver; production is the default and a no-op."""
    if solver == PRODUCTION_SOLVER:
        with nullcontext():
            yield
        return
    if solver == 'newton_analytic' or solver == 'balanced':
        from src.evaluation.adaptive_newmark_candidate import coupled_candidate
        with labelled(solver), coupled_candidate(
                samples if samples is not None else [],
                numerical_solver=solver, **settings):
            yield
        return
    if solver == 'native_newmark_fine':
        # Same production Picard-Newmark integrator, only a smaller internal
        # substep; used to separate temporal resolution from iteration count.
        if samples is None:
            with labelled(solver), fine_substep_context(settings.get('max_step', 0.0025)):
                yield
        else:
            with labelled(solver), fine_substep_observed_context(
                    samples, max_step=settings.get('max_step', 0.0025),
                    tol=settings.get('tol', 1e-5),
                    max_iter=settings.get('max_iter', 30)):
                yield
        return
    if solver == 'newmark_picard_force':
        with labelled(solver), picard_force_context(
                samples if samples is not None else [], **settings):
            yield
        return
    if solver == 'newmark_newton_displacement':
        with labelled(solver), newton_displacement_context(
                samples if samples is not None else [], **settings):
            yield
        return
    if solver == 'newton_analytic_time_error':
        from src.evaluation.error_controlled_mechanics import candidate
        with labelled(solver), candidate(samples if samples is not None else [],
                                         **settings):
            yield
        return
    raise ValueError(f'Unknown solver {solver!r}; expected one of {SOLVERS}')
