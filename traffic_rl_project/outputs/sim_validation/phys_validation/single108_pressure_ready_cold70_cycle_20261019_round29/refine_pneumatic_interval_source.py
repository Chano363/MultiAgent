"""Diagnostic refinement of native pneumatic/control-force subintervals.

External control period and command admission are unchanged. Each command is
applied only once; native wave/pressure/timer equations advance with smaller h.
Install outside coupled_candidate so its transaction covers the whole interval.
"""
from contextlib import contextmanager

import numpy as np

from src.train_dynamics.train import TrainDynamics


@contextmanager
def refined_pneumatic_interval(max_step_s=None, hold_coarse_grade=False):
    if max_step_s is None:
        yield
        return
    if not np.isfinite(max_step_s) or not 0 < max_step_s <= .01:
        raise ValueError('Diagnostic pneumatic interval must be in (0, .01]')
    original = TrainDynamics._advance_control_once

    def refined(self, throttle, ed_throttle, ab_command, brake_origin,
                ab_sources, eot, h, apply_command, reduction_kpa=None):
        count = max(1, int(np.ceil(h/max_step_s)))
        coarse_grade = self.grade.copy() if hold_coarse_grade else None
        for i in range(count):
            if hold_coarse_grade:
                self.grade = coarse_grade.copy()
            original(self, throttle, ed_throttle, ab_command, brake_origin,
                     ab_sources, eot, h/count, apply_command and i == 0,
                     reduction_kpa=reduction_kpa)

    TrainDynamics._advance_control_once = refined
    try:
        yield
    finally:
        TrainDynamics._advance_control_once = original
