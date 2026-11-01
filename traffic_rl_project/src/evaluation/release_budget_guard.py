"""Zero-RL experimental low-speed ED budget; no actuator or physics changes."""
from contextlib import contextmanager
import numpy as np

from src.evaluation.release_low_speed_controller import release_ed_cap


def limit_release_request(controller, train, rl, final, floor_mps):
    """Keep separate request history so gradual reductions accumulate.

    60 s budget horizon and .05/s reduction are engineering trial settings,
    not literature-calibrated air timing or a speed guarantee.
    """
    result = np.asarray(final, dtype=float).copy()
    previous = getattr(controller, '_release_budget_previous_request', None)
    dyn = train.dynamics
    eligible = (controller.num_locomotives == 1 and np.all(np.asarray(rl) == 0)
                and not controller._cyclic_braking and not any(controller._ab_on)
                and result[0, 1] == 0
                and np.max(np.abs(dyn._air_braking_forces())) <= 1.
                and float(dyn.vel.mean()) < 55./3.6)
    if eligible:
        budget = release_ed_cap(dyn, floor_mps, recovery_s=60.)
        target = float(controller._ed_frac_for_total_kn(train, budget))
        if previous is not None:
            target = max(target, float(previous[0]) - .05*controller.dt)
        result[:, 0] = np.minimum(result[:, 0], target)
        controller._previous_ed = result[:, 0].copy()
    controller._release_budget_previous_request = result[:, 0].copy()
    return result


@contextmanager
def candidate():
    from src.controllers.multi_loco_controller import MultiLocoController
    original = MultiLocoController.get_action_decomposed

    def guarded(self, train_env, rl_actions, *args, **kwargs):
        final, baseline = original(self, train_env, rl_actions, *args, **kwargs)
        controls = dict(zip(('v_max', 'v_min', 'ed_mod_coef', 'v_max_adj', 'v_min_adj'), args))
        controls.update(kwargs)
        return limit_release_request(self, train_env, rl_actions, final,
                                     float(controls.get('v_min', 40./3.6))), baseline
    MultiLocoController.get_action_decomposed = guarded
    try:
        yield
    finally:
        MultiLocoController.get_action_decomposed = original
