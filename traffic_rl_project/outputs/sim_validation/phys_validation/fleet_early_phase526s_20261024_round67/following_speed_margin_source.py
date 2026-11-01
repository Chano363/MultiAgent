"""Experimental restrictive rule ceiling; leaves ATP thresholds untouched."""
from contextlib import contextmanager
import numpy as np


def restrictive_ceiling(ceiling, margin, targets, enabled):
    if not np.isfinite(margin) or margin < 0:
        raise ValueError('Finite nonnegative rule margin required')
    if enabled and any(getattr(t, 'kind', None) == 'gap' for t in targets):
        return max(0., ceiling-margin)
    return ceiling


@contextmanager
def candidate():
    from src.controllers.multi_loco_controller import MultiLocoController
    original = MultiLocoController._operating_ceiling
    def earlier(self, train, v_max, v_max_adj):
        ceiling = original(self, train, v_max, v_max_adj)
        return restrictive_ceiling(ceiling, getattr(self, '_following_rule_margin_mps', 0.),
                                   getattr(train, 'etcs_targets', ()), self.anticipate_etcs)
    MultiLocoController._operating_ceiling = earlier
    try:
        yield
    finally:
        MultiLocoController._operating_ceiling = original
