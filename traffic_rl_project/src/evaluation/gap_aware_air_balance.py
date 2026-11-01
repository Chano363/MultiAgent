"""Diagnostic gap-error speed target; safety targets remain untouched."""
import copy
from contextlib import contextmanager

import numpy as np


def adjusted_train(controller, train, rl, ceiling):
    if (not getattr(controller, '_gap_aware_air_enabled', False)
            or not np.all(np.asarray(rl) == 0)):
        return train, ceiling
    targets = [t for t in getattr(train, 'etcs_targets', ()) if t.kind == 'gap']
    curve = getattr(train, 'etcs_curve', None)
    if not targets or curve is None:
        return train, ceiling
    _, sbi = train.safety._etcs_check(float(train.dynamics.pos[0]),
        float(train.dynamics.vel[0]), curve, train.etcs_targets)
    if sbi is None or not np.isfinite(sbi):
        return train, ceiling
    ceiling = min(float(ceiling), float(sbi)-controller.AB_SUPPRESS_MARGIN_MPS)
    if np.max(train.dynamics.vel) >= ceiling:
        return train, float('-inf')
    target = min(targets, key=lambda t: t.position_m)
    gap_error = float(target.position_m-train.dynamics.pos[0]
                      -controller._held_air_gap_reference_m)
    # Engineering trial parameters, not pressure/thermal calibration.
    bonus = float(np.clip(gap_error/60., 0., .5))
    proxy = copy.copy(train)
    proxy.etcs_targets = copy.deepcopy(train.etcs_targets)
    for old, new in zip(train.etcs_targets, proxy.etcs_targets):
        if old is target:
            object.__setattr__(new, 'speed_mps', min(float(old.speed_mps)+bonus, ceiling))
    return proxy, ceiling


@contextmanager
def candidate():
    from src.evaluation import held_air_speed_balance as balance
    original = balance.balanced_request

    def adjusted(controller, train, rl, final, ceiling):
        proxy, cap = adjusted_train(controller, train, rl, ceiling)
        return original(controller, proxy, rl, final, cap)

    balance.balanced_request = adjusted
    try:
        yield
    finally:
        balance.balanced_request = original
