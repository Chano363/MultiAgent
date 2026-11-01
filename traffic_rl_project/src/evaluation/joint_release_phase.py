"""One-cycle phase trial; native source/refill clocks are never reset."""
import copy
import hashlib
from pathlib import Path

import numpy as np

from src.evaluation.ready_cycle_pacing import arm_current_cycle


def arm(env, manifest, follower_kmh=53.):
    if not np.isfinite(follower_kmh) or not env.v_min*3.6 <= follower_kmh < env.v_max*3.6:
        raise ValueError('Follower release must be finite and inside the operating band')
    # Validate every train's established air/refill state before modifying it.
    for train, ctrl in zip(env.trains[1:], env.multi_loco_controllers[1:]):
        ceiling = ctrl._operating_ceiling(train, env.v_max, 0.)*3.6
        if (ctrl.cyclic_release_kmh is None or ctrl.cyclic_brake_trigger_kmh is None
                or follower_kmh >= min(ceiling, ctrl.cyclic_brake_trigger_kmh)):
            raise ValueError('Release must precede native braking and safety ceilings')
    env, result = arm_current_cycle(env, manifest, release_kmh=49.)
    result = copy.deepcopy(result)
    trials = []
    for ctrl in env.multi_loco_controllers[1:]:
        old = ctrl.cyclic_release_kmh
        ctrl._ready_cycle_restore_kmh = old
        ctrl._ready_cycle_override_active = True
        ctrl.cyclic_release_kmh = float(follower_kmh)
        trials.append(dict(previous_kmh=old, current_cycle_kmh=follower_kmh))
    result['joint_release_phase_trial'] = dict(leader_kmh=49., followers=trials,
        scope='One established-air cycle, restore each threshold after its source closes; not calibrated',
        refill_clock_reset=False, native_atp_unchanged=True)
    for name in ('ready_cycle_pacing', 'joint_release_phase'):
        result['numerical']['source_sha256'][name] = hashlib.sha256(
            Path('src/evaluation', name+'.py').read_bytes()).hexdigest()
    return env, result
