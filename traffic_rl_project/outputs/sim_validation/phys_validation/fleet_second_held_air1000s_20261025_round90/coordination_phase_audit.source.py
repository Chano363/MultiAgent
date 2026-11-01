"""Read-only phase ledger for contiguous three-train diagnostic archives."""
import argparse
import hashlib
import json
from pathlib import Path

import numpy as np


def audit(directories):
    blocks, hashes, native = [], {}, None
    for directory in directories:
        metadata = json.loads((directory/'metadata.json').read_text(encoding='utf-8'))
        current = metadata['initial_fleet_manifest']['native_source_sha256']
        if native is not None and native != current:
            raise ValueError('Native sources differ')
        native = current
        with np.load(directory/'trajectory.npz') as a, np.load(directory/'telemetry.npz') as b:
            t = a['rows'][:, 0]
            means = a['vehicle_speeds_mps'].mean(axis=2)*3.6
            if means.shape != (len(t), 3):
                raise ValueError('Three-train diagnostic required')
            gaps = b['last_vehicle_centers'][:, :-1]-b['heads'][:, 1:]
            ed = b['physical_loco_ed'].reshape(len(t), 3, -1)
            air = b['ab_source_on'].reshape(len(t), 3, -1).any(axis=2)
            if ed.shape[2] != 1:
                raise ValueError('One locomotive per train required')
            blocks.append(np.column_stack((t, means, gaps, ed[:, :, 0], air,
                                           b['ab_refill_remaining_s'].reshape(len(t), 3, -1).max(axis=2))))
        for name in ('trajectory.npz', 'telemetry.npz', 'metadata.json'):
            hashes[str(directory/name)] = hashlib.sha256((directory/name).read_bytes()).hexdigest()
    data = np.concatenate(blocks)
    data = data[np.argsort(data[:, 0])]
    if len(data) < 2 or not np.isfinite(data).all():
        raise ValueError('Requires finite samples')
    times = np.rint(data[:, 0]*10).astype(np.int64)
    if np.any(np.diff(times) != 1) or np.max(abs(times/10-data[:, 0])) > 1e-5:
        raise ValueError('Unique contiguous 0.1s samples required')
    events = []
    for ti in range(3):
        ed, air = data[:, 6+ti], data[:, 9+ti]
        for i in np.flatnonzero(np.diff(air) != 0)+1:
            events.append(dict(time_s=float(times[i]/10), train_one_based=ti+1,
                               kind='air_source_on' if air[i] else 'air_source_off'))
        reduced = ed < .99
        for i in np.flatnonzero(np.diff(reduced.astype(int)) != 0)+1:
            events.append(dict(time_s=float(times[i]/10), train_one_based=ti+1,
                kind='ED_below_0.99' if reduced[i] else 'ED_at_least_0.99',
                physical_ed=float(ed[i]), mean_kmh=float(data[i, 1+ti])))
    snapshots = []
    selected = sorted(set([0, len(data)-1, *np.flatnonzero(times % 100 == 0).tolist()]))
    for i in selected:
        snapshots.append(dict(time_s=float(times[i]/10), mean_kmh=data[i, 1:4].tolist(),
            gaps_m=data[i, 4:6].tolist(), physical_ed=data[i, 6:9].tolist(),
            air_source_on=data[i, 9:12].astype(bool).tolist(),
            refill_remaining_s=data[i, 12:15].tolist()))
    return dict(scope='Measured coordination phase ledger; ED crossings are observations, '
                'not internal eligibility events or a thermal safety verdict',
                window_s=[float(times[0]/10), float(times[-1]/10)], samples=len(data),
                gap_change_m=(data[-1, 4:6]-data[0, 4:6]).tolist(),
                snapshots=snapshots, events=sorted(events, key=lambda x: x['time_s']),
                source_sha256=hashes)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--segments', type=Path, nargs='+', required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    result = audit(args.segments)
    with args.output.open('x', encoding='utf-8') as stream:
        json.dump(result, stream, indent=2)
    args.output.with_suffix('.source.py').write_bytes(Path(__file__).read_bytes())
    print(json.dumps({k: v for k, v in result.items() if k != 'source_sha256'}, indent=2))


if __name__ == '__main__':
    main()
