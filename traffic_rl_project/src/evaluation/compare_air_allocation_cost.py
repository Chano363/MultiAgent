"""Mechanical air-work comparison; deliberately no thermal safety inference."""
import argparse
import hashlib
import json
from pathlib import Path

import numpy as np


def load(directory):
    with np.load(directory/'trajectory.npz') as a, np.load(directory/'telemetry.npz') as b:
        return {**{k: a[k] for k in a.files}, **{k: b[k] for k in b.files}}


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--baseline', type=Path, required=True)
    p.add_argument('--candidate', type=Path, required=True)
    p.add_argument('--output', type=Path, required=True)
    args = p.parse_args()
    a, b = load(args.baseline), load(args.candidate)
    keys = [np.rint(x['rows'][:, 0]*10).astype(np.int64) for x in (a, b)]
    for key in keys:
        if len(np.unique(key)) != len(key):
            raise ValueError('Duplicate time samples')
    shared, ai, bi = np.intersect1d(*keys, return_indices=True)
    if len(shared) < 2 or np.any(np.diff(shared) != 1):
        raise ValueError('Requires contiguous 0.1s common samples')
    metadata = [json.loads((d/'metadata.json').read_text(encoding='utf-8'))
                for d in (args.baseline, args.candidate)]
    if metadata[0]['initial_fleet_manifest']['native_source_sha256'] != metadata[1]['initial_fleet_manifest']['native_source_sha256']:
        raise ValueError('Native model differs')
    result = {'scope': 'Shared-window mechanical cost, not wheel heat or route acceptance',
              'window_s': [float(shared[0]/10), float(shared[-1]/10)],
              'sample_count': len(shared), 'integrated_duration_s': len(shared)*.1}
    for label, x, indices in (('baseline', a, ai), ('candidate', b, bi)):
        power = np.maximum(0., -x['vehicle_air_force_n'][indices]*x['vehicle_speeds_mps'][indices])
        gaps = x['last_vehicle_centers'][indices, :-1]-x['heads'][indices, 1:]
        result[label] = {
            'air_mechanical_work_mj_by_train': (power.sum(axis=(0, 2))*.1/1e6).tolist(),
            'air_source_on_s_by_train': (x['ab_source_on'][indices].reshape(len(indices), 3, -1).any(axis=2).sum(axis=0)*.1).tolist(),
            'start_gaps_m': gaps[0].tolist(), 'end_gaps_m': gaps[-1].tolist(),
            'gap_change_m': (gaps[-1]-gaps[0]).tolist(),
            'max_vehicle_power_kw_by_train': (power.max(axis=(0, 2))/1000).tolist()}
    result['source_sha256'] = {str(d/n): hashlib.sha256((d/n).read_bytes()).hexdigest()
        for d in (args.baseline, args.candidate) for n in ('metadata.json', 'trajectory.npz', 'telemetry.npz')}
    with args.output.open('x', encoding='utf-8') as f:
        json.dump(result, f, indent=2)
    print(json.dumps({k: v for k, v in result.items() if k != 'source_sha256'}, indent=2))


if __name__ == '__main__':
    main()
