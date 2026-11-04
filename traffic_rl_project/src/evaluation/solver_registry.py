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
EXPERIMENTAL_SOLVERS = ('newton_analytic', 'newton_analytic_time_error', 'balanced')
SOLVERS = (PRODUCTION_SOLVER,) + EXPERIMENTAL_SOLVERS

# Captured at import time, before any diagnostic wrapper can patch the class.
PRODUCTION_STEP_NEWMARK = TrainDynamics._step_newmark

_ACTIVE_LABEL = None


def solver_is_production() -> bool:
    """True when no diagnostic wrapper replaced the production integrator."""
    return TrainDynamics._step_newmark is PRODUCTION_STEP_NEWMARK


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
                      newmark_tol=getattr(dyn, 'newmark_tol', None))
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
    if solver == 'newton_analytic_time_error':
        from src.evaluation.error_controlled_mechanics import candidate
        with labelled(solver), candidate(samples if samples is not None else [],
                                         **settings):
            yield
        return
    raise ValueError(f'Unknown solver {solver!r}; expected one of {SOLVERS}')
