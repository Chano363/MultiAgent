"""Keep formation chase from prematurely releasing an established AB source."""
from contextlib import contextmanager
import numpy as np


def release_adjustment(controller, train, rl, adjustment):
    if (getattr(controller, '_phase_release_floor_enabled', False)
            and any(controller._ab_on) and np.all(np.asarray(rl) == 0)
            and any(getattr(t, 'kind', None) == 'gap'
                    for t in getattr(train, 'etcs_targets', ()))):
        return min(0., adjustment)
    return adjustment


@contextmanager
def candidate():
    from src.controllers.multi_loco_controller import MultiLocoController
    original = MultiLocoController.get_action_decomposed
    def phase_action(self, train, rl, *args, **kwargs):
        values = list(args)
        adjustment = values[4] if len(values) > 4 else kwargs.get('v_min_adj', 0.)
        adjusted = release_adjustment(self, train, rl, adjustment)
        if len(values) > 4:
            values[4] = adjusted
        elif 'v_min_adj' in kwargs or adjusted != adjustment:
            kwargs['v_min_adj'] = adjusted
        return original(self, train, rl, *values, **kwargs)
    MultiLocoController.get_action_decomposed = phase_action
    try:
        yield
    finally:
        MultiLocoController.get_action_decomposed = original
