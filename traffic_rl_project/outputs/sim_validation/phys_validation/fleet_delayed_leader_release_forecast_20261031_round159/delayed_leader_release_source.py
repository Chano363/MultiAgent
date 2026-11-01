"""Wait for current follower releases, subject to the original speed floor."""
from contextlib import contextmanager
import copy
import hashlib
from pathlib import Path

import numpy as np

from src.evaluation.ready_cycle_pacing import arm_current_cycle


def arm(env, manifest):
    env, result = arm_current_cycle(env, manifest, release_kmh=49.)
    leader = env.multi_loco_controllers[0]
    leader._delayed_release_followers = env.multi_loco_controllers[1:]
    leader._delayed_release_floor_kmh = env.v_min*3.6
    leader._delayed_release_consumed = False
    result = copy.deepcopy(result)
    result['delayed_leader_release_trial'] = dict(
        scope='One established-air cycle; wait for observed follower source-off, never reset clocks',
        floor_kmh=env.v_min*3.6, follower_thresholds_unchanged=True)
    for name in ('ready_cycle_pacing', 'delayed_leader_release', 'forecast_terminal_evidence'):
        result['numerical']['source_sha256'][name] = hashlib.sha256(
            Path('src/evaluation', name+'.py').read_bytes()).hexdigest()
    return env, result


@contextmanager
def candidate():
    from src.controllers.multi_loco_controller import MultiLocoController
    original = MultiLocoController.get_action_cyclic_braking

    def action(self, train, *args, **kwargs):
        followers = getattr(self, '_delayed_release_followers', None)
        if followers and not self._delayed_release_consumed:
            if not any(self._ab_on):
                self._delayed_release_consumed = True
            elif any(any(ctrl._ab_on) for ctrl in followers):
                self.cyclic_release_kmh = self._delayed_release_floor_kmh
            else:
                velocity = float(train.dynamics.vel[0])*3.6
                # Native min-speed/release-ceiling/source admission still apply.
                if np.isfinite(velocity):
                    self.cyclic_release_kmh = max(self._delayed_release_floor_kmh, velocity+1.e-7)
        return original(self, train, *args, **kwargs)

    MultiLocoController.get_action_cyclic_braking = action
    try:
        yield
    finally:
        MultiLocoController.get_action_cyclic_braking = original
