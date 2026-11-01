"""One-cycle early exit from chasing ED unloading before ordinary release."""
from contextlib import contextmanager

import numpy as np


@contextmanager
def candidate():
    from src.evaluation import held_air_speed_balance as balance
    original = balance.balanced_request

    def request(ctrl, train, rl, final, ceiling):
        enabled = getattr(ctrl, '_pre_release_chase_exit_enabled', False)
        done = getattr(ctrl, '_pre_release_chase_exit_done', False)
        if enabled and not done and not any(ctrl._ab_on):
            ctrl._pre_release_chase_exit_done = True
            done = True
        threshold = ctrl.cyclic_brake_trigger_kmh
        early_exit = (enabled and not done and threshold is not None
            and any(ctrl._ab_on) and np.all(np.asarray(rl) == 0)
            and float(train.dynamics.vel.mean())*3.6 <= threshold)
        if not early_exit:
            return original(ctrl, train, rl, final, ceiling)
        was_enabled = ctrl._held_air_balance_enabled
        ctrl._held_air_balance_enabled = False
        ctrl._held_air_balance_active = False
        try:
            # Existing smooth_handoff sees loss of activity and applies its
            # unchanged 0.05/s ramp while source air is still established.
            return original(ctrl, train, rl, final, ceiling)
        finally:
            ctrl._held_air_balance_enabled = was_enabled

    balance.balanced_request = request
    try:
        yield
    finally:
        balance.balanced_request = original
