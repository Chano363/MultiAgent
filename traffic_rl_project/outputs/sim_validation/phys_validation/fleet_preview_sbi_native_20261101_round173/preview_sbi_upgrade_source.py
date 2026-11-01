"""Trend-based restrictive ordinary upgrade using native response times."""
from contextlib import contextmanager

import numpy as np

from src.train_dynamics.braking import AirBrakeNotch
from src.train_dynamics.train import AIR_BRAKE_PROPAGATION_SPEED_SERVICE


def predicted_ceiling(ceiling, speed, now, previous, horizon):
    if previous is None or now <= previous[0]:
        return ceiling
    elapsed = now-previous[0]
    closing_rate = max(0., (speed-previous[2]-(ceiling-previous[1]))/elapsed)
    return max(0., ceiling-closing_rate*horizon)


@contextmanager
def candidate():
    from src.controllers.multi_loco_controller import MultiLocoController
    original = MultiLocoController.get_action_cyclic_braking

    def action(self, train, *args, **kwargs):
        if not getattr(self, '_preview_sbi_upgrade_enabled', False):
            return original(self, train, *args, **kwargs)
        vmax = float(kwargs.get('v_max', args[0] if args else 80./3.6))
        ceiling = float(self._operating_ceiling(train, vmax, float(kwargs.get('v_max_adj', 0.))))
        dyn = train.dynamics
        now, speed = float(dyn.time), float(dyn.vel[0])
        previous = getattr(self, '_preview_sbi_previous', None)
        self._preview_sbi_previous = (now, ceiling, speed)
        old = self.cyclic_ab_upgrade_kmh
        targets = getattr(train, 'etcs_targets', ())
        if (old is None or not any(t.kind == 'gap' for t in targets)
                or not any(self._ab_on) or not np.isfinite([now, speed, ceiling]).all()):
            return original(self, train, *args, **kwargs)
        lengths = dyn._vehicle_cum_lengths()
        # Conservative head-to-tail service-wave time; EOT relief assistance
        # is not incorrectly treated as a second service application source.
        wave_s = float(lengths[-1]-lengths[0])/AIR_BRAKE_PROPAGATION_SPEED_SERVICE
        rise_s = float(dyn.brake_rise_time_by_notch[AirBrakeNotch.SERVICE])
        unfilled = max(0., 1.-float(np.min(dyn._brake_pressure)))
        horizon = max(wave_s+unfilled*rise_s, float(self.ed_upgrade_ramp_s))
        projected = predicted_ceiling(ceiling, speed, now, previous, horizon)
        self._preview_sbi_last_horizon_s = horizon
        self.cyclic_ab_upgrade_kmh = min(old, projected*3.6)
        try:
            return original(self, train, *args, **kwargs)
        finally:
            self.cyclic_ab_upgrade_kmh = old

    MultiLocoController.get_action_cyclic_braking = action
    try:
        yield
    finally:
        MultiLocoController.get_action_cyclic_braking = original
