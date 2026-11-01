"""Diagnostic slew cap at the formation traction injection point."""
from contextlib import contextmanager
import numpy as np


def limited_coordination(ctrl, result):
    if not (getattr(ctrl, '_formation_traction_slew_enabled', False)
            and getattr(ctrl, '_formation_traction_slew_zero_rl', False)):
        ctrl._formation_traction_slew_last = 0.
        return result
    upper, lower, requested = result
    previous_ed = np.asarray(getattr(ctrl, '_previous_ed', [1.]), dtype=float)
    clear = (np.isfinite(previous_ed).all() and np.all(previous_ed <= 1e-9)
             and not ctrl._cyclic_braking and not any(ctrl._ab_on))
    previous = float(getattr(ctrl, '_formation_traction_slew_last', 0.))
    allowed = min(max(0., requested), previous+.05*ctrl.dt) if clear else 0.
    ctrl._formation_traction_slew_last = allowed
    return upper, lower, allowed


@contextmanager
def candidate():
    from src.controllers.multi_loco_controller import MultiLocoController
    from src.environments.train_fleet_env import TrainFleetEnv
    coordination = MultiLocoController.coordination_adj
    step = TrainFleetEnv._step_decomposed_fleet

    def guarded_coordination(self, *args, **kwargs):
        return limited_coordination(self, coordination(self, *args, **kwargs))

    def guarded_step(self, actions):
        actions = np.asarray(actions)
        offset = 0
        for train, ctrl in zip(self.trains, self.multi_loco_controllers):
            count = len(train.loco_indices)
            ctrl._formation_traction_slew_zero_rl = bool(np.all(actions[offset:offset+count] == 0))
            offset += count
        return step(self, actions)

    MultiLocoController.coordination_adj = guarded_coordination
    TrainFleetEnv._step_decomposed_fleet = guarded_step
    try:
        yield
    finally:
        MultiLocoController.coordination_adj = coordination
        TrainFleetEnv._step_decomposed_fleet = step
