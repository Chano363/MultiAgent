"""Withdraw formation traction before the existing ordinary brake threshold."""
from contextlib import contextmanager
import numpy as np


def preview_limit(ctrl, result):
    if not (getattr(ctrl, '_traction_brake_preview_enabled', False)
            and getattr(ctrl, '_formation_traction_slew_zero_rl', False)):
        return result
    speed = getattr(ctrl, '_traction_preview_speed_mps', None)
    ceiling = getattr(ctrl, '_traction_preview_ceiling_mps', None)
    maximum = getattr(ctrl, '_traction_preview_maximum', None)
    margin = ctrl.AB_SUPPRESS_MARGIN_MPS
    if (any(x is None for x in (speed, ceiling, maximum))
            or not np.isfinite([speed, ceiling, maximum, margin]).all() or margin <= 0):
        return result
    taper = float(np.clip((ceiling-speed)/margin, 0., 1.))
    limited = min(result[2], max(0., maximum)*taper)
    ctrl._formation_traction_slew_last = max(0., limited)
    return result[0], result[1], limited


@contextmanager
def candidate():
    from src.evaluation import formation_traction_slew as slew
    from src.environments.train_fleet_env import TrainFleetEnv
    original_limit = slew.limited_coordination
    original_step = TrainFleetEnv._step_decomposed_fleet

    def limited(ctrl, result):
        return preview_limit(ctrl, original_limit(ctrl, result))

    def step(self, actions):
        for train, ctrl in zip(self.trains, self.multi_loco_controllers):
            if not getattr(ctrl, '_traction_brake_preview_enabled', False):
                continue
            cap = float(ctrl._operating_ceiling(train, self.v_max, 0.))
            if ctrl.cyclic_brake_trigger_kmh is not None:
                cap = min(cap, ctrl.cyclic_brake_trigger_kmh/3.6)
            ctrl._traction_preview_speed_mps = float(np.max(train.dynamics.vel))
            ctrl._traction_preview_ceiling_mps = cap
            ctrl._traction_preview_maximum = self.LEAN_MAX_TRACTION
        return original_step(self, actions)

    slew.limited_coordination = limited
    TrainFleetEnv._step_decomposed_fleet = step
    try:
        yield
    finally:
        slew.limited_coordination = original_limit
        TrainFleetEnv._step_decomposed_fleet = original_step
