"""One-cycle forecast trial: prepare an ED force before release, then hold it."""
from contextlib import contextmanager

import numpy as np


def request(controller, train, rl, final):
    result = np.asarray(final, dtype=float).copy()
    if (not getattr(controller, '_pre_release_fixed_ed_enabled', False)
            or getattr(controller, '_pre_release_fixed_ed_done', False)
            or controller.num_locomotives != 1 or np.any(np.asarray(rl) != 0)
            or result[0, 0] < 0):
        return result
    dyn = train.dynamics
    curve, targets = getattr(train, 'etcs_curve', None), getattr(train, 'etcs_targets', ())
    ceiling = float(controller._operating_ceiling(train, 80./3.6, 0.))
    # The leader normally has no predecessor target. This is a valid native
    # operating-ceiling case, not missing safety authority.
    if curve is not None and targets:
        _, sbi = train.safety._etcs_check(float(dyn.pos[0]), float(dyn.vel[0]), curve, targets)
        if sbi is not None and np.isfinite(sbi):
            ceiling = min(ceiling, float(sbi))
    ceiling -= controller.AB_SUPPRESS_MARGIN_MPS
    if np.max(dyn.vel) >= ceiling:
        return result  # Native safety command retains authority.
    held = controller._ed_hold_steps > 0
    prepared = getattr(controller, '_pre_release_fixed_ed_armed', False)
    in_brake = (controller._cyclic_braking and all(controller._ab_on)
        and float(dyn.vel.mean()) <= 60./3.6
        and float(np.min(dyn._brake_pressure)) >= .99
        and float(np.min(dyn._air_brake_release_frac)) >= .99)
    if in_brake:
        prepared = controller._pre_release_fixed_ed_armed = True
    if prepared and held:
        controller._pre_release_fixed_ed_seen_hold = True
    if (prepared and not held
            and getattr(controller, '_pre_release_fixed_ed_seen_hold', False)):
        controller._pre_release_fixed_ed_done = True
        return result
    if not prepared or not (in_brake or held):
        return result
    target = float(controller._ed_frac_for_total_kn(train, 350.))
    previous = getattr(controller, '_pre_release_fixed_ed_previous', float(result[0, 0]))
    # Preparatory transitions are gradual. The plateau requests a fixed force,
    # so throttle changes with speed through the native inverse actuator map.
    if not held:
        target = max(target, previous-.05*controller.dt)
    result[0, 0] = min(result[0, 0], max(0., target))
    controller._pre_release_fixed_ed_previous = float(result[0, 0])
    controller._previous_ed = result[:, 0].copy()
    return result


@contextmanager
def candidate():
    from src.evaluation import release_budget_guard
    original = release_budget_guard.limit_release_request

    def fixed(controller, train, rl, final, floor):
        return request(controller, train, rl,
                       original(controller, train, rl, final, floor))

    release_budget_guard.limit_release_request = fixed
    try:
        yield
    finally:
        release_budget_guard.limit_release_request = original
