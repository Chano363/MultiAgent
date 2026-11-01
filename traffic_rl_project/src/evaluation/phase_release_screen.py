"""Phase-aware advisory horizon, deliberately without actuator authority.

The centroid predictor omits residual/new pneumatic braking and coupler motion.
A passing result is unverified; a warning after release cannot undo that release
or block native emergency/ATP actions.
"""
import numpy as np

from src.evaluation.screen_fleet_release import project_full_ed


def release_horizon_s(phase, refill_s, build_reserve_s):
    if (not np.isfinite([refill_s, build_reserve_s]).all()
            or refill_s < 0 or build_reserve_s < 0):
        raise ValueError('Finite nonnegative assumptions required')
    # Only a hypothetical NEW release starts a fresh refill wait. Existing
    # off-source clocks keep their recorded remaining time, never another 222s.
    waiting = max(refill_s if on else remaining for on, remaining in
                  zip(phase.source_on, phase.refill_remaining_s))
    return float(waiting+build_reserve_s)


def screen_release(dynamics, phase, *, refill_s, build_reserve_s,
                   speed_floor_mps, speed_ceiling_mps, dt=.2):
    if (not np.isfinite([speed_floor_mps, speed_ceiling_mps]).all()
            or not 0 <= speed_floor_mps < speed_ceiling_mps):
        raise ValueError('Finite ordered speed limits required')
    duration = release_horizon_s(phase, refill_s, build_reserve_s)
    trace = project_full_ed(dynamics, duration, dt)
    upper = bool(np.any(trace[:, 2] >= speed_ceiling_mps))
    lower = bool(np.any(trace[:, 2] < speed_floor_mps))
    return dict(scope='Phase-aware centroid advisory; no hard safety or recharge certificate',
        horizon_s=duration, build_reserve_s=float(build_reserve_s),
        hypothetical_new_release=bool(any(phase.source_on)),
        native_refill_remaining_s=list(phase.refill_remaining_s),
        current_residual_air_present=phase.source_off_with_residual_air,
        speed_ceiling_warning=upper, speed_floor_warning=lower,
        result='warning_requires_native_validation' if upper or lower else 'unverified_pass',
        min_predicted_kmh=float(trace[:, 2].min()*3.6),
        max_predicted_kmh=float(trace[:, 2].max()*3.6),
        assumptions=['Instant full native ED; translating fixed relative vehicle positions',
            'Residual air and future pneumatic buildup omitted; may cause false warnings',
            'No future recorded trajectory used; actual ATP retains priority'])
