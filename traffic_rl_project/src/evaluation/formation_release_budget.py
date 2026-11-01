"""Preserve speed during fully released, refilled follower ED holding."""
from contextlib import contextmanager
import numpy as np


def coordinated_floor(ctrl, train, rl, floor):
    if not (getattr(ctrl, '_formation_release_budget_enabled', False)
            and np.all(np.asarray(rl) == 0) and not any(ctrl._ab_on)):
        return floor
    elapsed = [(ctrl._ab_step-int(last))*ctrl.dt for last in ctrl._ab_last_release_step]
    if any(t < ctrl.ab_min_refill_s for t in elapsed):
        return floor
    targets = [t for t in getattr(train, 'etcs_targets', ()) if t.kind == 'gap']
    if not targets or getattr(train, 'etcs_curve', None) is None:
        return floor
    dyn = train.dynamics
    target = min(targets, key=lambda x: x.position_m)
    speed = float(dyn.vel.mean())
    if (not np.isfinite([speed, target.speed_mps, target.position_m]).all()
            or target.position_m-dyn.pos[0] <= ctrl._held_air_gap_reference_m
            or speed >= target.speed_mps-ctrl.AB_SUPPRESS_MARGIN_MPS
            or np.max(abs(dyn._air_braking_forces())) > 1.):
        return floor
    _, sbi = train.safety._etcs_check(float(dyn.pos[0]), float(dyn.vel[0]),
                                     train.etcs_curve, train.etcs_targets)
    if sbi is None or not np.isfinite(sbi):
        return floor
    speed_cap = getattr(ctrl, '_formation_release_speed_ceiling_mps', None)
    if speed_cap is None or not np.isfinite(speed_cap):
        return floor
    ceiling = min(float(sbi), float(ctrl._operating_ceiling(train, speed_cap, 0.)))
    if dyn.vel.max() >= ceiling-ctrl.AB_SUPPRESS_MARGIN_MPS:
        return floor
    return max(float(floor), speed)


@contextmanager
def candidate():
    from src.evaluation import release_budget_guard as guard
    original = guard.limit_release_request

    def coordinated(ctrl, train, rl, final, floor):
        return original(ctrl, train, rl, final, coordinated_floor(ctrl, train, rl, floor))

    guard.limit_release_request = coordinated
    try:
        yield
    finally:
        guard.limit_release_request = original
