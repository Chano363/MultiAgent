"""Isolated zero-RL release candidate; no physical parameter changes."""
import numpy as np


def release_ed_cap(dyn, floor_mps, recovery_s=60.0):
    """Total ED force budget to avoid spending the remaining speed margin fast.

    This is a local engineering controller horizon, not a calibrated pneumatic
    parameter or a guarantee that a train can maintain speed without traction.
    """
    margin = max(0., float(dyn.vel.mean()) - floor_mps)
    budget = (float(dyn._grade_forces().sum())
              - float(dyn._resistance_forces().sum())
              + float(dyn._air_braking_forces().sum())
              + float(dyn.masses_kg.sum()) * margin / recovery_s)
    return max(0., budget) / 1000.


def low_speed_release_source(source):
    if '_low_speed_release_action' in source:
        raise ValueError('Candidate already installed')
    return source + '''

from src.evaluation.release_low_speed_controller import release_ed_cap
_low_speed_release_base = MultiLocoController.get_action_decomposed

def _low_speed_release_action(self, train_env, rl_actions, *args, **kwargs):
    previous = None if self._previous_ed is None else self._previous_ed.copy()
    final, baseline = _low_speed_release_base(self, train_env, rl_actions, *args, **kwargs)
    controls = dict(zip(('v_max', 'v_min', 'ed_mod_coef', 'v_max_adj', 'v_min_adj'), args))
    controls.update(kwargs)
    floor = float(controls.get('v_min', 40.0/3.6))
    dyn = train_env.dynamics
    if (self.num_locomotives == 1 and np.all(np.asarray(rl_actions) == 0.)
            and not self._cyclic_braking and not any(self._ab_on)
            and final[0, 1] == 0. and float(dyn.vel.mean()) < 55.0/3.6):
        target = self._ed_frac_for_total_kn(train_env, release_ed_cap(dyn, floor))
        # Reduce gradually from the last executed value. Never raise base ED.
        if previous is not None:
            target = np.maximum(target, np.asarray(previous) - 0.05*self.dt)
        final[:, 0] = np.minimum(final[:, 0], target)
    return final, baseline

MultiLocoController.get_action_decomposed = _low_speed_release_action
'''
