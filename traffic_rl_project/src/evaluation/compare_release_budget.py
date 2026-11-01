"""Compare archived same-condition zero-RL release experiments without rerunning."""
import argparse
import hashlib
import json
from pathlib import Path

import numpy as np


def summarize(directory):
    result = json.loads((directory/'run/result.json').read_text(encoding='utf-8'))
    numerical = json.loads((directory/'numerical_summary.json').read_text(encoding='utf-8'))
    if numerical['status'] != 'completed':
        raise ValueError('Incomplete numerical trial cannot be compared as a completed run')
    with np.load(directory/'run/trajectory.npz') as data:
        time = data['rows'][:, 0]
        means = data['vehicle_speeds_mps'].mean(axis=2)*3.6
        per_train = []
        for j in range(means.shape[1]):
            low = np.flatnonzero(means[:, j] < 40.)
            air = np.max(np.abs(data['vehicle_air_force_n'][:, j]), axis=1) > 1.
            onset = np.flatnonzero(air & ~np.r_[False, air[:-1]])
            offset = np.flatnonzero(~air & np.r_[False, air[:-1]])
            ed = data['physical_loco_ed'][:, j, 0]
            per_train.append(dict(train_one_based=j+1,
                min_mean_kmh=float(means[:, j].min()),
                min_vehicle_kmh=float(data['vehicle_speeds_mps'][:, j].min()*3.6),
                first_mean_below40_s=float(time[low[0]]) if len(low) else None,
                below40_train_samples=int(len(low)),
                largest_ed_decrease_per_control=float(max(0., -np.diff(ed).min())),
                physical_air_onset_s=time[onset].tolist(),
                physical_air_offset_s=time[offset].tolist()))
        initial = dict(first_heads=data['heads'][0].tolist(),
                       first_speeds=data['vehicle_speeds_mps'][0].tolist())
        command_hash = hashlib.sha256(data['commands'].tobytes()).hexdigest()
    return dict(summary=result['summary'], numerical=numerical,
                metadata=result['metadata'], per_train=per_train,
                initial=initial, command_sha256=command_hash)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--baseline', type=Path, required=True)
    parser.add_argument('--candidate', type=Path, required=True)
    args = parser.parse_args()
    baseline, candidate = summarize(args.baseline), summarize(args.candidate)
    for key in ('env_cfg', 'train_dynamics_sha256', 'train_env_sha256', 'fleet_env_sha256'):
        if key not in baseline['metadata'] or key not in candidate['metadata']:
            raise ValueError(f'Missing required provenance: {key}')
        if baseline['metadata'][key] != candidate['metadata'][key]:
            raise ValueError(f'Comparison differs in {key}')
    if (baseline['initial'] != candidate['initial'] or
            baseline['numerical']['settings'] != candidate['numerical']['settings']):
        raise ValueError('Initial states or numerical settings differ')
    output = dict(scope='Same-condition controller comparison; not full-route acceptance',
        baseline=str(args.baseline), candidate=str(args.candidate),
        common_initial_and_numerical_settings=True)
    for label, record in (('baseline', baseline), ('candidate', candidate)):
        output[label+'_results'] = dict(summary=record['summary'], per_train=record['per_train'],
            internal_peak_kn=record['numerical']['internal_peak_kn'],
            command_sha256=record['command_sha256'])
    target = args.candidate/'controller_comparison.json'
    if target.exists():
        raise FileExistsError('Comparison already exists')
    target.write_text(json.dumps(output, indent=2), encoding='utf-8')
    print(json.dumps(output, indent=2))


if __name__ == '__main__':
    main()
