"""Observe accepted step-doubling endpoints without changing integration."""
from contextlib import contextmanager
import json
from pathlib import Path

import numpy as np


@contextmanager
def observe(output, live_ids):
    from src.evaluation import error_controlled_mechanics as mechanics
    original_advance = mechanics.advance
    ledger = []

    def traced_advance(dyn, force, dt, **settings):
        if id(dyn) not in live_ids:
            return original_advance(dyn, force, dt, **settings)
        original_trial = mechanics.newton_trial
        group, accepted = [], []
        start = float(dyn.time)

        def trial(*args, **kwargs):
            answer = original_trial(*args, **kwargs)
            ok = bool(answer[0])
            snapshot = None
            if ok:
                cf = dyn.coupler_interface_forces().copy()
                index = int(np.argmax(np.abs(cf)))
                snapshot = dict(pos=dyn.pos.copy(), vel=dyn.vel.copy(), force=cf,
                    detail=dict(time_s=float(dyn.time), train_one_based=live_ids[id(dyn)],
                        coupler_one_based=index+1, vehicle_pair_one_based=[index+1, index+2],
                        signed_native_force_n=float(cf[index]), peak_kn=float(abs(cf[index])/1000),
                        adjacent_speeds_kmh=(dyn.vel[index:index+2]*3.6).tolist(),
                        adjacent_positions_m=dyn.pos[index:index+2].tolist(),
                        relative_velocity_mps=float(dyn.vel[index]-dyn.vel[index+1])))
            group.append(snapshot)
            if len(group) == 2 and not ok:
                group.clear()  # Original advance skips second half if first half failed.
            elif len(group) == 3:
                coarse, first, second = group
                if all(x is not None for x in group):
                    ratio = max(float(np.max(abs(second['pos']-coarse['pos'])))/settings['position_atol'],
                        float(np.max(abs(second['vel']-coarse['vel'])))/settings['velocity_atol'],
                        float(np.max(abs(second['force']-coarse['force'])))/settings['force_atol_n'])
                    if np.isfinite(ratio) and ratio <= 1:
                        accepted.extend((first['detail'], second['detail']))
                group.clear()
            return answer

        mechanics.newton_trial = trial
        try:
            stats = original_advance(dyn, force, dt, **settings)
        finally:
            mechanics.newton_trial = original_trial
        if len(accepted) != stats['accepted']:
            raise RuntimeError('Observer accepted-step count differs from integrator')
        peak = max(accepted, key=lambda x: x['peak_kn'])
        if abs(peak['peak_kn']*1000-stats['peak_interface_n']) > 1e-6:
            raise RuntimeError('Observer peak differs from accepted-step integrator peak')
        if peak['peak_kn'] >= 800:
            record = dict(interval_start_s=start, interval_end_s=float(dyn.time), **peak)
            ledger.append(record)
        return stats

    mechanics.advance = traced_advance
    try:
        yield
    finally:
        mechanics.advance = original_advance
        output = Path(output)
        output.mkdir(parents=True, exist_ok=True)
        (output/'accepted_micropeaks.json').write_text(json.dumps(dict(
            scope='Only endpoints accepted by original step-doubling criteria; '
                  'native signed force convention, not relabelled tension/compression',
            interval_peak_filter_kn=800, records=ledger), indent=2), encoding='utf-8')
