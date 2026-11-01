"""Zero-RL experiment: suspend positive formation chase while AB recharges."""
from contextlib import contextmanager
import numpy as np


def waiting_for_refill(controller):
    if not getattr(controller, '_refill_chase_pause_enabled', False) or any(controller._ab_on):
        return False
    elapsed = [(controller._ab_step-int(last))*controller.dt
               for last in controller._ab_last_release_step]
    return any(t < controller.ab_min_refill_s for t in elapsed)


@contextmanager
def candidate():
    from src.controllers.multi_loco_controller import MultiLocoController
    coordination = MultiLocoController.coordination_adj
    action = MultiLocoController.get_action_decomposed
    def conservative_coordination(self, *args, **kwargs):
        result = coordination(self, *args, **kwargs)
        return tuple(min(0., x) for x in result) if waiting_for_refill(self) else result
    def conservative_action(self, train, rl, *args, **kwargs):
        values = list(args)
        if (waiting_for_refill(self) and np.all(np.asarray(rl) == 0)
                and any(getattr(t, 'kind', None) == 'gap'
                        for t in getattr(train, 'etcs_targets', ()))):
            if len(values) > 4:
                values[4] = min(0., values[4])
            elif 'v_min_adj' in kwargs:
                kwargs['v_min_adj'] = min(0., kwargs['v_min_adj'])
        return action(self, train, rl, *values, **kwargs)
    MultiLocoController.coordination_adj = conservative_coordination
    MultiLocoController.get_action_decomposed = conservative_action
    try:
        yield
    finally:
        MultiLocoController.coordination_adj = coordination
        MultiLocoController.get_action_decomposed = action
