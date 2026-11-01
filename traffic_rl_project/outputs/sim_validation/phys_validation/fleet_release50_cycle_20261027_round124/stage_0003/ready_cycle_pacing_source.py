"""One-cycle leader release sensitivity, armed only with established fleet AB."""
import copy
from contextlib import contextmanager
import numpy as np


def arm_current_cycle(env, manifest, release_kmh=53.):
    leader = env.multi_loco_controllers[0]
    previous = leader.cyclic_release_kmh
    if env.num_trains != 3 or previous is None or not env.v_min*3.6 <= release_kmh < previous:
        raise ValueError('Requires a restrictive within-band three-train release trial')
    for train, ctrl in zip(env.trains, env.multi_loco_controllers):
        dyn = train.dynamics
        if (not all(ctrl._ab_on) or np.min(dyn._brake_pressure) < .99
                or np.min(dyn._air_brake_release_frac) < .99
                or np.max(abs(dyn._air_braking_forces())) <= 1.):
            raise ValueError('Every train must have established air braking, not just a request')
        if any((ctrl._ab_step-last)*ctrl.dt < ctrl.ab_min_refill_s for last in ctrl._ab_last_release_step):
            raise ValueError('No follower may still be waiting for refill')
    leader._ready_cycle_restore_kmh = previous
    leader._ready_cycle_override_active = True
    leader.cyclic_release_kmh = float(release_kmh)
    result = copy.deepcopy(manifest)
    result['ready_cycle_pacing_trial'] = dict(previous_kmh=previous, current_cycle_kmh=release_kmh,
        restore_after_release=True, scope='Established-AB phase diagnostic; not a safety certificate')
    return env, result


@contextmanager
def candidate():
    from src.controllers.multi_loco_controller import MultiLocoController
    original = MultiLocoController.get_action_decomposed

    def action(self, *args, **kwargs):
        result = original(self, *args, **kwargs)
        if getattr(self, '_ready_cycle_override_active', False) and not any(self._ab_on):
            self.cyclic_release_kmh = self._ready_cycle_restore_kmh
            self._ready_cycle_override_active = False
        return result

    MultiLocoController.get_action_decomposed = action
    try:
        yield
    finally:
        MultiLocoController.get_action_decomposed = original
