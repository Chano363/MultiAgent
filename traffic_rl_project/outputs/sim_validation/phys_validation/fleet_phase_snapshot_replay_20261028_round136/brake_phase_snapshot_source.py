"""Immutable observations for a candidate controller, with no action authority.

Relief, residual mechanical braking and refill waiting are independent axes.
This diagnostic interface does not infer auxiliary-reservoir pressure, reset
clocks, authorize ordinary AB, or override the native ATP.
"""
from dataclasses import dataclass

import numpy as np


@dataclass(frozen=True)
class BrakePhaseSnapshot:
    controller_step: int
    source_on: tuple
    native_elapsed_since_release_counter_s: tuple
    refill_remaining_s: tuple
    ordinary_refill_gate_ready: tuple
    max_abs_mechanical_air_n: float
    effective_coefficient_min: float
    effective_coefficient_max: float
    source_off_with_residual_air: bool
    source_off_with_refill_wait: bool
    negligible_air_threshold_n: float
    coefficient_semantics: str = 'Normalized effective coefficient; not kPa or reservoir charge'


def snapshot(controller, dynamics, *, mechanical_air_force_n, negligible_air_n=1.):
    """Read existing fields and supplied forces without calling a mutating actuator.

    The elapsed counter may include a native initialization sentinel; it is not
    a claim that a physical release was observed. Remaining time uses exactly
    the native ordinary-refill arithmetic, independently for each locomotive.
    """
    step = controller._ab_step
    last = np.asarray(controller._ab_last_release_step, dtype=float)
    sources = tuple(bool(x) for x in controller._ab_on)
    dt, minimum = float(controller.dt), float(controller.ab_min_refill_s)
    air = np.asarray(mechanical_air_force_n, dtype=float)
    effective = (np.asarray(dynamics._brake_pressure, dtype=float)
                 * np.asarray(dynamics._air_brake_release_frac, dtype=float)
                 * np.asarray(dynamics._air_brake_active, dtype=bool))
    if (isinstance(step, bool) or int(step) != step or step < 0
            or last.ndim != 1 or len(last) != len(sources) or not sources
            or not np.isfinite(last).all() or np.any(last != np.floor(last))
            or np.any(last > step) or not np.isfinite([dt, minimum, negligible_air_n]).all()
            or dt <= 0 or minimum < 0 or negligible_air_n < 0
            or air.ndim != 1 or air.size == 0 or effective.shape != air.shape
            or not np.isfinite(air).all() or not np.isfinite(effective).all()):
        raise ValueError('Invalid native clock, source/vehicle dimensions or observation values')
    elapsed = (step-last)*dt
    remaining = np.maximum(0., minimum-elapsed)
    maximum_air = float(np.max(abs(air)))
    return BrakePhaseSnapshot(
        controller_step=int(step), source_on=sources,
        native_elapsed_since_release_counter_s=tuple(float(x) for x in elapsed),
        refill_remaining_s=tuple(float(x) for x in remaining),
        ordinary_refill_gate_ready=tuple(bool(x == 0.) for x in remaining),
        max_abs_mechanical_air_n=maximum_air,
        effective_coefficient_min=float(effective.min()),
        effective_coefficient_max=float(effective.max()),
        source_off_with_residual_air=not any(sources) and maximum_air > negligible_air_n,
        source_off_with_refill_wait=not any(sources) and bool(np.any(remaining > 0.)),
        negligible_air_threshold_n=float(negligible_air_n))
