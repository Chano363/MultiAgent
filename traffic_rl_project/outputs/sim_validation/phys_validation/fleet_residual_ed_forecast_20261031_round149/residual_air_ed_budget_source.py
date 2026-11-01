"""Opt-in low-speed ED budget while native air relief still carries force."""
from contextlib import contextmanager

import numpy as np

from src.evaluation.release_low_speed_controller import release_ed_cap


def limit_residual(controller, train, rl, final, floor_mps):
    result = np.asarray(final, dtype=float).copy()
    previous = getattr(controller, '_residual_air_previous_ed', None)
    dyn = train.dynamics
    eligible = (getattr(controller, '_residual_air_budget_enabled', False)
                and controller.num_locomotives == 1 and np.all(np.asarray(rl) == 0)
                and not controller._cyclic_braking and not any(controller._ab_on)
                and result[0, 1] == 0 and result[0, 0] >= 0
                and np.max(np.abs(dyn._air_braking_forces())) > 1.
                and float(dyn.vel.mean()) < 55./3.6)
    if eligible:
        # Reuse the existing 40km/h margin / 60s engineering budget, including
        # actual residual air force. No valve, wave or recharge timing changes.
        demand_kn = release_ed_cap(dyn, floor_mps, recovery_s=60.)
        target = float(controller._ed_frac_for_total_kn(train, demand_kn))
        anchor = float(result[0, 0] if previous is None else previous)
        target = max(target, anchor-.05*controller.dt)
        result[0, 0] = min(result[0, 0], max(0., target))
        controller._previous_ed = result[:, 0].copy()
    controller._residual_air_previous_ed = float(result[0, 0])
    controller._residual_air_budget_active = bool(eligible)
    return result


@contextmanager
def candidate():
    from src.evaluation import release_budget_guard
    original = release_budget_guard.limit_release_request

    def request(controller, train, rl, final, floor_mps):
        result = original(controller, train, rl, final, floor_mps)
        return limit_residual(controller, train, rl, result, floor_mps)

    release_budget_guard.limit_release_request = request
    try:
        yield
    finally:
        release_budget_guard.limit_release_request = original
