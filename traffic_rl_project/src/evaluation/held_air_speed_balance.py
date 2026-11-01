"""Opt-in zero-RL ED allocation during established air braking; no air bypass."""
from contextlib import contextmanager

import numpy as np

from src.train_dynamics.resistance import G


def balanced_request(controller, train, rl, final, ceiling):
    if not getattr(controller, '_held_air_balance_enabled', False):
        return final
    result = np.asarray(final, dtype=float).copy()
    dyn = train.dynamics
    targets = [t for t in getattr(train, 'etcs_targets', ()) if t.kind == 'gap']
    previous = getattr(controller, '_held_air_balance_previous_ed', None)
    active = getattr(controller, '_held_air_balance_active', False)
    eligible = (controller.num_locomotives == 1 and np.all(np.asarray(rl) == 0)
                and any(controller._ab_on) and result[0, 1] < 0 and result[0, 0] >= 0
                and bool(targets))
    if eligible:
        target = min(targets, key=lambda t: t.position_m)
        gap = float(target.position_m-dyn.pos[0])
        speed_target = min(float(target.speed_mps), float(ceiling))
        speed = float(dyn.vel.mean())
        margin = controller.AB_SUPPRESS_MARGIN_MPS
        eligible = (np.isfinite([gap, speed_target, speed]).all()
                    and gap > controller._held_air_gap_reference_m
                    and speed < speed_target + (margin if active else -margin)
                    and float(np.min(dyn.vel)) > 40./3.6
                    and np.max(np.abs(dyn._air_braking_forces())) > 1.)
    if eligible:
        # Engineering trial: 60s speed-error horizon, +/-0.02m/s² demand,
        # and 0.05/s ED reduction. These are not literature air parameters.
        acceleration = float(np.clip((speed_target-speed)/60., -.02, .02))
        profile = getattr(dyn, '_grade_profile', None)
        gravity = (float(np.sum(-dyn.masses_kg*G*profile.grades_for_positions(dyn.pos)))
                   if profile is not None else float(dyn._grade_forces().sum()))
        without_ed = (gravity-float(dyn._resistance_forces().sum())
                      +float(dyn._air_braking_forces().sum()))
        demand_kn = max(0., without_ed-float(dyn.masses_kg.sum())*acceleration)/1000.
        target_ed = float(controller._ed_frac_for_total_kn(train, demand_kn))
        anchor = float(result[0, 0] if previous is None else previous)
        target_ed = max(target_ed, anchor-.05*controller.dt)
        result[0, 0] = min(result[0, 0], max(0., target_ed))
        controller._previous_ed = result[:, 0].copy()
    # Loss of eligibility restores the native command immediately. ATP and
    # native source admission run downstream and retain full authority.
    controller._held_air_balance_active = bool(eligible)
    controller._held_air_balance_previous_ed = float(result[0, 0])
    return result


@contextmanager
def candidate():
    from src.controllers.multi_loco_controller import MultiLocoController
    original = MultiLocoController.get_action_decomposed

    def balanced(self, train, rl, *args, **kwargs):
        final, baseline = original(self, train, rl, *args, **kwargs)
        values = dict(zip(('v_max', 'v_min', 'ed_mod_coef', 'v_max_adj', 'v_min_adj'), args))
        values.update(kwargs)
        ceiling = self._operating_ceiling(train, values.get('v_max', 80./3.6),
                                          values.get('v_max_adj', 0.))
        return balanced_request(self, train, rl, final, ceiling), baseline

    MultiLocoController.get_action_decomposed = balanced
    try:
        yield
    finally:
        MultiLocoController.get_action_decomposed = original
