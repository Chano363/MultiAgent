"""Score two archived fleet branches over exactly their shared time samples."""
import argparse
import hashlib
import json
from pathlib import Path

import numpy as np


def read_segments(directories):
    arrays = []
    provenance = {}
    native = None
    for directory in directories:
        directory = Path(directory)
        metadata = json.loads((directory/'metadata.json').read_text(encoding='utf-8'))
        hashes = metadata['initial_fleet_manifest']['native_source_sha256']
        if native is not None and hashes != native:
            raise ValueError('Physical/controller source hashes differ between segments')
        native = hashes
        with np.load(directory/'trajectory.npz') as a, np.load(directory/'telemetry.npz') as b:
            means = a['vehicle_speeds_mps'].mean(axis=2)*3.6
            gaps = b['last_vehicle_centers'][:, :-1]-b['heads'][:, 1:]
            rows = a['rows']
            arrays.append(np.column_stack((rows[:, 0], rows[:, 5]/1000,
                rows[:, 3]*3.6, rows[:, 2]*3.6, b['safety_events_delta'], means, gaps)))
        for name in ('trajectory.npz', 'telemetry.npz', 'metadata.json'):
            path = directory/name
            provenance[str(path)] = hashlib.sha256(path.read_bytes()).hexdigest()
    data = np.concatenate(arrays)
    data = data[np.argsort(data[:, 0])]
    keys = np.rint(data[:, 0]*10).astype(np.int64)
    if len(np.unique(keys)) != len(keys) or np.max(abs(keys/10-data[:, 0])) > 1e-5:
        raise ValueError('Requires unique samples on this experiment 0.1s grid')
    return data, keys, native, provenance


def score(data, reference_gap):
    means, gaps = data[:, 5:8], data[:, 8:10]
    if data.shape[1] != 10 or not np.isfinite(data).all():
        raise ValueError('Requires finite three-train archives')
    return dict(internal_peak_kn=float(data[:, 1].max()),
        min_vehicle_kmh=float(data[:, 2].min()), max_vehicle_kmh=float(data[:, 3].max()),
        safety_event_count=int(data[:, 4].sum()),
        mean_speed_spread_kmh=float(np.mean(np.ptp(means, axis=1))),
        max_speed_spread_kmh=float(np.max(np.ptp(means, axis=1))),
        mean_absolute_gap_error_m=float(np.mean(abs(gaps-reference_gap))),
        max_absolute_gap_error_m=float(np.max(abs(gaps-reference_gap))),
        min_gap_m=float(gaps.min()), max_gap_m=float(gaps.max()),
        end_mean_kmh=means[-1].tolist(), end_gaps_m=gaps[-1].tolist())


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--baseline', type=Path, nargs='+', required=True)
    parser.add_argument('--candidate', type=Path, nargs='+', required=True)
    parser.add_argument('--reference-gap-m', type=float, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    if not np.isfinite(args.reference_gap_m) or args.reference_gap_m <= 0:
        parser.error('Positive finite reference required')
    a, ak, ah, ap = read_segments(args.baseline)
    b, bk, bh, bp = read_segments(args.candidate)
    if ah != bh:
        raise ValueError('Branches use different native sources')
    shared, ai, bi = np.intersect1d(ak, bk, return_indices=True)
    if not len(shared) or np.any(np.diff(shared) != 1):
        raise ValueError('A contiguous common time window is required')
    result = dict(scope='Common-window diagnostic comparison, not full-route acceptance',
        window_s=[float(shared[0]/10), float(shared[-1]/10)], samples=len(shared),
        reference_gap_m=args.reference_gap_m,
        baseline=score(a[ai], args.reference_gap_m),
        candidate=score(b[bi], args.reference_gap_m),
        source_sha256={**ap, **bp}, entry_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest())
    with args.output.open('x', encoding='utf-8') as stream:
        json.dump(result, stream, indent=2)
    print(json.dumps({k: v for k, v in result.items() if not k.endswith('sha256')}, indent=2))


if __name__ == '__main__':
    main()
