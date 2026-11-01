"""Read-only audit: mechanical relief and refill waiting can overlap.

The archive has no auxiliary-reservoir pressure. Never interpret the native
222-second gate or normalized brake coefficients as a measured recharge state.
"""
import argparse
import hashlib
import json
from pathlib import Path

import numpy as np


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--segments', type=Path, nargs='+', required=True)
    p.add_argument('--output', type=Path, required=True)
    args = p.parse_args()
    blocks, hashes, previous, native = [], {}, None, None
    for directory in args.segments:
        m = json.loads((directory/'metadata.json').read_text(encoding='utf-8'))['initial_fleet_manifest']
        if native is not None and native != m['native_source_sha256']:
            raise ValueError('Different native sources')
        if previous is not None and previous['sha256'] != m['sha256']:
            raise ValueError('Unlinked checkpoint chain')
        native = m['native_source_sha256']
        with np.load(directory/'trajectory.npz') as a, np.load(directory/'telemetry.npz') as b:
            count = len(a['rows'])
            blocks.append(dict(time=a['rows'][:, 0],
                source=b['ab_source_on'].reshape(count, 3, -1).any(axis=2),
                air=np.max(abs(b['vehicle_air_force_n']), axis=2),
                refill=b['ab_refill_remaining_s'].reshape(count, 3, -1).max(axis=2)))
        previous = json.loads((directory/'fleet_state.json').read_text(encoding='utf-8'))
        for name in ('metadata.json', 'fleet_state.json', 'trajectory.npz', 'telemetry.npz'):
            hashes[str(directory/name)] = hashlib.sha256((directory/name).read_bytes()).hexdigest()
    data = {k: np.concatenate([b[k] for b in blocks]) for k in blocks[0]}
    t = data['time']
    if len(t) < 2 or np.any(abs(np.diff(t)-.1) > 1e-6):
        raise ValueError('Requires a contiguous 0.1-second archive')
    result = dict(scope='Observed source/air-force/refill-clock overlap, not a full valve-state reconstruction',
        negligible_air_force_threshold_n=1.,
        threshold_scope='Existing diagnostic convention, not pneumatic calibration',
        window_s=[float(t[0]), float(t[-1])], trains=[], source_sha256=hashes,
        entry_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest())
    for j in range(3):
        source, present, waiting = data['source'][:, j], data['air'][:, j] > 1., data['refill'][:, j] > 1e-7
        releases = []
        for i in np.flatnonzero(source[:-1] & ~source[1:])+1:
            on_later = np.flatnonzero(source[i:])
            end = i+int(on_later[0]) if len(on_later) else len(t)
            negligible = np.flatnonzero(~present[i:end])
            ready = np.flatnonzero(~waiting[i:end])
            releases.append(dict(source_off_s=float(t[i]),
                refill_remaining_at_source_off_s=float(data['refill'][i, j]),
                first_negligible_mechanical_air_s=(float(t[i+negligible[0]]) if len(negligible) else None),
                first_refill_gate_ready_s=(float(t[i+ready[0]]) if len(ready) else None),
                next_source_on_s=(float(t[end]) if end < len(t) else None)))
        result['trains'].append(dict(train_one_based=j+1,
            source_off_air_present_and_refill_wait_s=float(np.sum(~source & present & waiting)*.1),
            source_off_air_negligible_and_refill_wait_s=float(np.sum(~source & ~present & waiting)*.1),
            source_on_with_refill_wait_s=float(np.sum(source & waiting)*.1), releases=releases))
    result['warning'] = ('Relief and refill waiting are independent observed dimensions. '
        'Pacing must not reset the native release clock; native ATP priority is unchanged.')
    args.output.mkdir(parents=True, exist_ok=False)
    (args.output/'result.json').write_text(json.dumps(result, indent=2), encoding='utf-8')
    (args.output/'entry_source.py').write_bytes(Path(__file__).read_bytes())
    print(json.dumps({k:v for k,v in result.items() if k != 'source_sha256'}, indent=2))


if __name__ == '__main__':
    main()
