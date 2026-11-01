"""One observed leader-release event; all ordinary source gates stay native."""
from contextlib import contextmanager
import copy
import hashlib
from pathlib import Path

import numpy as np

from src.evaluation.ready_cycle_pacing import arm_current_cycle


def arm(env, manifest):
    env, result = arm_current_cycle(env, manifest, release_kmh=49.)
    for ctrl in env.multi_loco_controllers[1:]:
        ctrl._phase_sync_leader = env.multi_loco_controllers[0]
        ctrl._phase_sync_original_release = ctrl.cyclic_release_kmh
        ctrl._phase_sync_consumed = False
    result = copy.deepcopy(result)
    result['release_event_sync_trial'] = dict(
        scope='One observed source-off event; no future trace, refill reset or forced source bypass',
        leader_release_kmh=49., followers='Request native cyclic release after leader actually switches off')
    for name in ('ready_cycle_pacing', 'release_event_sync'):
        result['numerical']['source_sha256'][name] = hashlib.sha256(
            Path('src/evaluation', name+'.py').read_bytes()).hexdigest()
    return env, result


@contextmanager
def candidate():
    from src.controllers.multi_loco_controller import MultiLocoController
    original = MultiLocoController.get_action_cyclic_braking

    def action(self, train, *args, **kwargs):
        leader = getattr(self, '_phase_sync_leader', None)
        if leader is not None and not self._phase_sync_consumed:
            if not any(self._ab_on):
                self._phase_sync_consumed = True
            elif not any(leader._ab_on):
                vmax = float(kwargs.get('v_max', args[0] if args else 80./3.6))
                adjustment = float(kwargs.get('v_max_adj', 0.))
                ceiling = self._operating_ceiling(train, vmax, adjustment)
                velocity = float(train.dynamics.vel[0])
                trigger = self.cyclic_brake_trigger_kmh/3.6
                # Only a legal release request, never force air source or ATP.
                if (np.isfinite([velocity, ceiling]).all()
                        and np.max(train.dynamics.vel) < min(ceiling, trigger)
                        and velocity*3.6 >= self._phase_sync_original_release):
                    self._ready_cycle_restore_kmh = self._phase_sync_original_release
                    self._ready_cycle_override_active = True
                    self.cyclic_release_kmh = min(velocity*3.6+1.e-7,
                                                  min(ceiling, trigger)*3.6-1.e-7)
        return original(self, train, *args, **kwargs)

    MultiLocoController.get_action_cyclic_braking = action
    try:
        yield
    finally:
        MultiLocoController.get_action_cyclic_braking = original
