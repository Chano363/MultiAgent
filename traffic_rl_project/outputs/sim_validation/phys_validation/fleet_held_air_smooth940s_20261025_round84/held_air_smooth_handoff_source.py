"""Rate-limited ordinary ED handback, with immediate safety-margin bypass."""
from contextlib import contextmanager

import numpy as np


def smooth_handoff(controller, train, rl, final, previous, was_active, safety_ceiling):
    if not getattr(controller, '_held_air_smooth_handoff_enabled', False):
        return final
    result = np.asarray(final, dtype=float).copy()
    active = getattr(controller, '_held_air_balance_active', False)
    pending = getattr(controller, '_held_air_handoff_pending', False)
    if was_active and not active and previous is not None and result[0, 0] > previous:
        pending = True
    targets = [t for t in getattr(train, 'etcs_targets', ()) if t.kind == 'gap']
    gap = min((t.position_m-train.dynamics.pos[0] for t in targets), default=-1.)
    clear = (controller.num_locomotives == 1 and np.all(np.asarray(rl) == 0)
             and any(controller._ab_on) and result[0, 1] < 0 and result[0, 0] >= 0
             and np.isfinite(safety_ceiling) and gap > controller._held_air_gap_reference_m
             and np.max(train.dynamics.vel) < safety_ceiling-controller.AB_SUPPRESS_MARGIN_MPS)
    if pending and not active and clear and previous is not None:
        result[0, 0] = min(result[0, 0], previous+.05*controller.dt)
        pending = result[0, 0] < float(final[0, 0])-1e-12
        controller._previous_ed = result[:, 0].copy()
        controller._held_air_balance_previous_ed = float(result[0, 0])
    else:
        pending = False
    controller._held_air_handoff_pending = pending
    controller._held_air_handoff_previous_ed = float(result[0, 0])
    return result


@contextmanager
def candidate():
    from src.controllers.multi_loco_controller import MultiLocoController
    original = MultiLocoController.get_action_decomposed

    def guarded(self, train, rl, *args, **kwargs):
        previous = getattr(self, '_held_air_handoff_previous_ed',
                           getattr(self, '_held_air_balance_previous_ed', None))
        was_active = getattr(self, '_held_air_balance_active', False)
        final, baseline = original(self, train, rl, *args, **kwargs)
        ceiling = float(args[0] if args else kwargs.get('v_max', 80./3.6))
        curve = getattr(train, 'etcs_curve', None)
        targets = getattr(train, 'etcs_targets', ())
        if curve is None or not targets:
            ceiling = float('-inf')
        else:
            _, sbi = train.safety._etcs_check(float(train.dynamics.pos[0]),
                float(train.dynamics.vel[0]), curve, targets)
            ceiling = float('-inf') if sbi is None else min(ceiling, sbi)
        return smooth_handoff(self, train, rl, final, previous, was_active, ceiling), baseline

    MultiLocoController.get_action_decomposed = guarded
    try:
        yield
    finally:
        MultiLocoController.get_action_decomposed = original
