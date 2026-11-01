"""Read-only source-cycle ledger; mechanical work is not a temperature model."""
import argparse
import hashlib
import json
from pathlib import Path

import numpy as np


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--segments', nargs='+', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    blocks, hashes, native = [], {}, None
    for directory in args.segments:
        metadata = json.loads((directory/'metadata.json').read_text(encoding='utf-8'))
        current = metadata['initial_fleet_manifest']['native_source_sha256']
        if native is not None and current != native:
            raise ValueError('Native source hashes differ')
        native = current
        with np.load(directory/'trajectory.npz') as a, np.load(directory/'telemetry.npz') as b:
            times = a['rows'][:, 0]
            velocities = a['vehicle_speeds_mps']
            air = b['vehicle_air_force_n']
            source = b['ab_source_on'].reshape(len(times), 3).astype(bool)
            power = np.maximum(0., -air*velocities).sum(axis=2)
            blocks.append((times, b['heads'], source, power, np.max(abs(air), axis=2)))
        for name in ('metadata.json', 'trajectory.npz', 'telemetry.npz'):
            path = directory/name
            hashes[str(path)] = hashlib.sha256(path.read_bytes()).hexdigest()
    times, heads, source, power, air_peak = [np.concatenate([b[i] for b in blocks]) for i in range(5)]
    keys = np.rint(times*10).astype(np.int64)
    if (not np.isfinite(times).all() or np.max(abs(keys/10-times)) > 1e-5
            or np.any(np.diff(keys) != 1)):
        raise ValueError('Segments must form a unique continuous 0.1s branch in supplied order')
    cycles = []
    for train in range(3):
        on = source[:, train]
        starts = np.flatnonzero(on & ~np.r_[False, on[:-1]])
        ends = np.flatnonzero(~on & np.r_[False, on[:-1]])
        for number, start in enumerate(starts):
            later = ends[ends > start]
            end = int(later[0]) if len(later) else len(times)
            next_start = int(starts[number+1]) if number+1 < len(starts) else len(times)
            end_position = min(end, len(times)-1)
            def first_clear(threshold):
                valid = np.flatnonzero(air_peak[end:next_start, train] <= threshold)
                return float(times[end+valid[0]]) if len(valid) else None
            cycles.append(dict(train_one_based=train+1, cycle_in_window=number+1,
                left_censored=bool(start == 0), right_censored=bool(end == len(times)),
                source_apply_s=float(times[start]),
                source_release_s=float(times[end]) if end < len(times) else None,
                observed_source_duration_s=float(times[end_position]-times[start]),
                observed_head_distance_m=float(heads[end_position, train]-heads[start, train]),
                source_on_mechanical_work_mj=float(power[start:end, train].sum()*.1/1e6),
                mechanical_work_until_next_source_or_end_mj=float(power[start:next_start, train].sum()*.1/1e6),
                next_source_apply_s=float(times[next_start]) if next_start < len(times) else None,
                source_off_to_next_apply_s=float(times[next_start]-times[end])
                    if end < len(times) and next_start < len(times) else None,
                all_vehicle_air_at_most_1n_s=first_clear(1.) if end < len(times) else None,
                all_vehicle_air_exact_zero_s=first_clear(0.) if end < len(times) else None))
    result = dict(window_s=[float(times[0]), float(times[-1])], dt_s=.1,
        semantics=['Controller source flags, not direct cylinder-pressure measurements',
                   'Intervals already on at first sample or on at end are censored',
                   'Distance uses post-step heads at sampled flag transitions',
                   'Mechanical work proxy sums max(0,-F_air*v)*dt per vehicle',
                   'Source-off interval and first-zero-air-force time are separate; neither is a temperature threshold'],
        total_air_mechanical_work_mj_per_train=(power.sum(axis=0)*.1/1e6).tolist(),
        cycles=cycles, source_sha256=hashes,
        entry_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest())
    with args.output.open('x', encoding='utf-8') as stream:
        json.dump(result, stream, indent=2)
    args.output.with_suffix('.source.py').write_bytes(Path(__file__).read_bytes())
    print(json.dumps(dict(window_s=result['window_s'], cycles=cycles), indent=2), flush=True)


if __name__ == '__main__':
    main()
