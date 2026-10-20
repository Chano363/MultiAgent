"""Experimental event-resolved timing of the existing linear-fill/exponential-release law.

No pressure curve, wave speed, valve parameter or command admission is changed.
The native advance method is copied at runtime with its pressure increment block
removed: this propagation routine accounts for charging over actual active time.
Production source remains untouched. Delayed mid-train sources are unsupported.
"""
import inspect
import textwrap
from contextlib import contextmanager

import numpy as np

from src.train_dynamics.braking import AirBrakeNotch
from src.train_dynamics.train import TrainDynamics

_NATIVE_ADVANCE = TrainDynamics._advance_control_once
EVENT_EPS_S = 1e-12


def advance_fractional_air(dyn, dt):
    """Resolve application/upgrade/release arrival and exhaust-end events within dt."""
    if not np.isfinite(dt) or dt < 0:
        raise ValueError('Finite nonnegative pneumatic duration required')
    tau = max(dyn.release_exhaust_tau_s, 1e-6)
    cutoff_time = tau*np.log(50.0)

    def masks():
        return (np.asarray([n is not None for n in dyn._air_brake_pending]),
                np.asarray([n is not None for n in dyn._air_brake_upgrade_pending]))

    def events():
        pending, upgrade = masks()
        for i in np.flatnonzero(pending & (dyn._air_brake_delay_remaining <= EVENT_EPS_S)):
            dyn._air_brake_active[i] = True
            if dyn._air_notch_rank(dyn._air_brake_pending[i]) > dyn._air_notch_rank(dyn._air_brake_notch[i]):
                dyn._air_brake_notch[i] = dyn._air_brake_pending[i]
            dyn._air_brake_pending[i] = None
            dyn._air_brake_delay_remaining[i] = 0.0
        for i in np.flatnonzero(upgrade & (dyn._air_brake_upgrade_delay <= EVENT_EPS_S)):
            notch = dyn._air_brake_upgrade_pending[i]
            if (dyn._air_brake_releasing[i] or not dyn._air_brake_active[i]
                    or dyn._air_notch_rank(notch) > dyn._air_notch_rank(dyn._air_brake_notch[i])):
                if dyn._air_brake_releasing[i]:
                    dyn._brake_pressure[i] *= dyn._air_brake_release_frac[i]
                dyn._air_brake_notch[i] = notch
                dyn._air_brake_active[i] = True
                dyn._air_brake_releasing[i] = False
                dyn._air_brake_exhaust_t[i] = 0.0
                dyn._air_brake_release_frac[i] = 1.0
            dyn._air_brake_upgrade_pending[i] = None
            dyn._air_brake_upgrade_delay[i] = 0.0
        # An upgrade arriving exactly at exhaust completion retains effective
        # pressure first, matching native application-before-release priority.
        done = (dyn._air_brake_releasing & dyn._air_brake_active
                & (dyn._air_brake_exhaust_t >= cutoff_time-EVENT_EPS_S))
        dyn._air_brake_active[done] = False
        dyn._air_brake_notch[done] = AirBrakeNotch.RELEASE
        dyn._air_brake_release_frac[done] = 0.0
        dyn._air_brake_exhaust_t[done] = 0.0
        dyn._brake_pressure[~dyn._air_brake_active] = 0.0

    events()
    remaining = float(dt)
    while remaining > 0:
        pending, upgrade = masks()
        releasing = dyn._air_brake_releasing & dyn._air_brake_active
        delayed = pending | (releasing & (dyn._air_brake_delay_remaining > EVENT_EPS_S))
        exhausting = releasing & (dyn._air_brake_delay_remaining <= EVENT_EPS_S)
        times = [remaining]
        times.extend(dyn._air_brake_delay_remaining[delayed].tolist())
        times.extend(dyn._air_brake_upgrade_delay[upgrade].tolist())
        times.extend((cutoff_time-dyn._air_brake_exhaust_t[exhausting]).tolist())
        h = min(t for t in times if t > 0)
        rising = dyn._air_brake_active & ~dyn._air_brake_releasing
        rise = np.asarray([dyn.brake_rise_time_by_notch.get(n, dyn.brake_rise_time_s)
                           for n in dyn._air_brake_notch])
        dyn._brake_pressure[rising] = np.minimum(1.0, dyn._brake_pressure[rising]+h/rise[rising])
        dyn._air_brake_delay_remaining[delayed] -= h
        dyn._air_brake_upgrade_delay[upgrade] -= h
        dyn._air_brake_exhaust_t[exhausting] += h
        dyn._air_brake_release_frac[exhausting] = np.exp(-dyn._air_brake_exhaust_t[exhausting]/tau)
        remaining = max(0.0, remaining-h)
        events()


def fractional_advance_source():
    """Fail closed if the native pressure block is no longer recognizable."""
    source = textwrap.dedent(inspect.getsource(_NATIVE_ADVANCE))
    start = '    rising = self._air_brake_active & (~self._air_brake_releasing)'
    end = '    # 【2026-08-30 标准 LTD 重构】'
    if source.count(start) != 1 or source.count(end) != 1:
        raise ValueError('Native pressure block changed; candidate requires review')
    lo, hi = source.index(start), source.index(end)
    block = source[lo:hi]
    if 'self._brake_pressure + h / rise_times' not in block:
        raise ValueError('Native fill law changed; candidate requires review')
    return source[:lo] + '    # Pressure integrated by advance_fractional_air.\n' + source[hi:]


@contextmanager
def fractional_air_timing(enabled=False):
    if not enabled:
        yield
        return
    source = fractional_advance_source()
    namespace = dict(_NATIVE_ADVANCE.__globals__)
    exec(compile(source, '<fractional_air_advance>', 'exec'), namespace)
    generated = namespace['_advance_control_once']
    original_advance = TrainDynamics._advance_control_once
    original_propagation = TrainDynamics._advance_air_brake_propagation

    def advance(self, throttle, ed_throttle, ab_command, brake_origin,
                ab_sources, eot, h, apply_command, reduction_kpa=None):
        if self._ab_delay_queue or (self.mid_source_delay_s > 0 and ab_sources
                                   and any(i != 0 for i, _ in ab_sources)):
            raise ValueError('Delayed middle sources need separate event treatment')
        return generated(self, throttle, ed_throttle, ab_command, brake_origin,
                         ab_sources, eot, h, apply_command, reduction_kpa=reduction_kpa)

    TrainDynamics._advance_control_once = advance
    TrainDynamics._advance_air_brake_propagation = advance_fractional_air
    try:
        yield
    finally:
        TrainDynamics._advance_control_once = original_advance
        TrainDynamics._advance_air_brake_propagation = original_propagation
