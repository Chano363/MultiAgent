"""Retrospective scoring of approximate forecasts against native archives."""
import argparse
import hashlib
import json
from pathlib import Path

import numpy as np


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--forecast', type=Path, required=True)
    p.add_argument('--baseline', type=Path, nargs='+', required=True)
    p.add_argument('--output', type=Path, required=True)
    args = p.parse_args()
    prediction = json.loads((args.forecast/'result.json').read_text(encoding='utf-8'))
    f = np.load(args.forecast/'forecast.npz')
    blocks, previous, sources = [], None, {}
    for i, directory in enumerate(args.baseline):
        metadata = json.loads((directory/'metadata.json').read_text(encoding='utf-8'))
        initial = metadata['initial_fleet_manifest']
        if initial['native_source_sha256'] != prediction['source_manifest']['native_source_sha256']:
            raise ValueError('Native air/control sources differ')
        if i == 0:
            if initial['sha256'] != prediction['source_manifest']['sha256']:
                raise ValueError('Forecast and actual origin differ')
            if initial.get('ready_cycle_pacing_trial') != prediction['source_manifest'].get('ready_cycle_pacing_trial'):
                raise ValueError('Recorded release intervention differs')
        elif initial['sha256'] != previous['sha256']:
            raise ValueError('Actual trajectory segments are not linked')
        with np.load(directory/'trajectory.npz') as a, np.load(directory/'telemetry.npz') as b:
            blocks.append(dict(time=a['rows'][:, 0],
                mean_mps=a['vehicle_speeds_mps'].mean(axis=2),
                maximum_mps=a['vehicle_speeds_mps'].max(axis=2),
                ab_source_on=b['ab_source_on'], refill_remaining_s=b['ab_refill_remaining_s'],
                coefficient=np.stack((a['effective_pressure_coefficient'].min(axis=2),
                                      a['effective_pressure_coefficient'].max(axis=2)), axis=2)))
        previous = json.loads((directory/'fleet_state.json').read_text(encoding='utf-8'))
        for name in ('metadata.json', 'fleet_state.json', 'trajectory.npz', 'telemetry.npz'):
            sources[str(directory/name)] = hashlib.sha256((directory/name).read_bytes()).hexdigest()
    actual = {k: np.concatenate([b[k] for b in blocks]) for k in blocks[0]}
    keys = [np.rint(x*10).astype(np.int64) for x in (f['time'], actual['time'])]
    if any(np.any(np.diff(k) != 1) for k in keys):
        raise ValueError('Contiguous 0.1-second samples required')
    shared, fi, ai = np.intersect1d(*keys, return_indices=True)
    if len(shared) < 2 or shared[0] != keys[0][0] or shared[0] != keys[1][0]:
        raise ValueError('Common origin and overlapping finite trajectory required')
    difference = (f['mean_mps'][fi]-actual['mean_mps'][ai])*3.6
    same_source_mode = f['ab_source_on'][fi] == actual['ab_source_on'][ai]
    refill_error = abs(f['refill_remaining_s'][fi]-actual['refill_remaining_s'][ai])
    actual_summary = json.loads((args.baseline[-1]/'result.json').read_text(encoding='utf-8'))['summary']
    result = dict(scope='Retrospective forecast validation; not unseen generalization, real-time control or safety acceptance',
        window_s=[float(shared[0]/10), float(shared[-1]/10)], shared_samples=len(shared),
        predicted_stop_reason=prediction['summary']['stop_reason'],
        actual_stop_reason=actual_summary['stop_reason'],
        predicted_end_s=float(f['time'][-1]), actual_end_s=float(actual['time'][-1]),
        speed_mae_kmh_by_train=abs(difference).mean(axis=0).tolist(),
        max_abs_speed_error_kmh_by_train=abs(difference).max(axis=0).tolist(),
        predicted_max_mean_kmh_by_train=(f['mean_mps'][fi].max(axis=0)*3.6).tolist(),
        actual_max_mean_kmh_by_train=(actual['mean_mps'][ai].max(axis=0)*3.6).tolist(),
        actual_max_vehicle_kmh_by_train=(actual['maximum_mps'][ai].max(axis=0)*3.6).tolist(),
        source_disagreement_fraction_by_train=(f['ab_source_on'][fi] != actual['ab_source_on'][ai]).mean(axis=(0, 2)).tolist(),
        max_refill_error_s=float(refill_error.max()),
        max_refill_error_s_when_source_mode_matches=(float(refill_error[same_source_mode].max())
                                                     if same_source_mode.any() else None),
        timing_note='A one-sample source-off shift can compare fresh 222s against pre-release 0s; raw error is retained',
        max_effective_coefficient_error_by_train=abs(f['effective_coefficient_min_max'][fi]-actual['coefficient'][ai]).max(axis=(0, 2)).tolist(),
        source_edges={}, actual_source_sha256=sources,
        entry_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest())
    for label, times, on in [('prediction', f['time'], f['ab_source_on']),
                              ('actual', actual['time'], actual['ab_source_on'])]:
        result['source_edges'][label] = [[dict(time_s=float(times[i]), on=bool(on[i, j, 0]))
            for i in np.flatnonzero(on[1:, j, 0] != on[:-1, j, 0])+1] for j in range(3)]
    with args.output.open('x', encoding='utf-8') as stream:
        json.dump(result, stream, indent=2)
    print(json.dumps({k:v for k,v in result.items() if not k.endswith('sha256')}, indent=2))


if __name__ == '__main__':
    main()
