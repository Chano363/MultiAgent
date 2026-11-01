"""Restrict the ordinary AB-upgrade threshold by the native dynamic ceiling."""
from contextlib import contextmanager

import numpy as np


def upgrade_threshold(original_kmh, operating_ceiling_mps, has_gap_target, enabled):
    if not enabled or not has_gap_target or original_kmh is None:
        return original_kmh
    if not np.isfinite(operating_ceiling_mps) or operating_ceiling_mps <= 0:
        return original_kmh
    return min(float(original_kmh), float(operating_ceiling_mps)*3.6)


@contextmanager
def candidate():
    from src.controllers.multi_loco_controller import MultiLocoController
    original = MultiLocoController.get_action_cyclic_braking

    def action(self, train, *args, **kwargs):
        previous = self.cyclic_ab_upgrade_kmh
        vmax = float(kwargs.get('v_max', args[0] if args else 80./3.6))
        adjustment = float(kwargs.get('v_max_adj', 0.))
        ceiling = self._operating_ceiling(train, vmax, adjustment)
        self.cyclic_ab_upgrade_kmh = upgrade_threshold(previous, ceiling,
            any(t.kind == 'gap' for t in getattr(train, 'etcs_targets', ())),
            getattr(self, '_dynamic_sbi_upgrade_enabled', False))
        try:
            # Reuse all native gates: full-ED static check, notch choice,
            # source admission, upgrade wave and the existing ED ramp.
            return original(self, train, *args, **kwargs)
        finally:
            self.cyclic_ab_upgrade_kmh = previous

    MultiLocoController.get_action_cyclic_braking = action
    try:
        yield
    finally:
        MultiLocoController.get_action_cyclic_braking = original
