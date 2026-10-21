"""Compare completed cold-start diagnostics without conflating route coverage."""
import argparse
import hashlib
import json
from pathlib import Path

import numpy as np


def load(root):
    record = json.loads((root/'run/result.json').read_text(encoding='utf-8'))
    solver = json.loads((root/'solver_result.json').read_text(encoding='utf-8'))
    with np.load(root/'run/trajectory.npz', allow_pickle=False) as data:
        arrays = {name: data[name].copy() for name in (
            'rows', 'commands', 'heads', 'tails', 'vehicle_speeds_mps',
            'air_brake_segment', 'initial_heads', 'initial_head_speeds',
            'predecision_refill_elapsed_s', 'safety_rule_counts')}
    return record, solver, arrays


def compare(baseline, candidate):
    records = [load(p) for p in (baseline, candidate)]
    a, b = records
    for key in ('consist_preset', 'grade_profile', 'coupler_force_limit_n'):
        if a[0]['metadata']['env_cfg'][key] != b[0]['metadata']['env_cfg'][key]:
            raise ValueError(f'Mismatched physical scenario: {key}')
    for key in ('train_dynamics_sha256', 'train_env_sha256', 'etcs_braking_sha256'):
        if not a[0]['metadata'].get(key) or a[0]['metadata'][key] != b[0]['metadata'].get(key):
            raise ValueError(f'Mismatched physical source: {key}')
    if a[1]['settings'] != b[1]['settings']:
        raise ValueError('Mismatched numerical settings')
    for key in ('initial_heads', 'initial_head_speeds'):
        np.testing.assert_array_equal(a[2][key], b[2][key])
    common_head = min(float(item[2]['heads'][-1, 0]) for item in records)
    report = {'scope': 'Completed cold prefixes; compare equal time and common head coverage separately',
              'common_head_end_m': common_head, 'runs': {}}
    for name, root, (record, solver, data) in zip(
            ('baseline', 'candidate'), (baseline, candidate), records):
        t = data['rows'][:, 0]
        request = data['commands'][:, 0, 1]
        deep_start = (request == -.75) & ~np.r_[False, request[:-1] == -.75]
        segment = data['air_brake_segment'][:, 0]
        starts = np.flatnonzero(segment > np.r_[0, segment[:-1]])
        common = data['heads'][:, 0] <= common_head + 1e-9
        report['runs'][name] = {
            'duration_s': float(t[-1]), 'head_end_m': float(data['heads'][-1, 0]),
            'tail_end_m': float(data['tails'][-1, 0]),
            'mean_speed_range_kmh': [float(data['rows'][:, 1].min()*3.6),
                                      float(data['rows'][:, 1].max()*3.6)],
            'max_vehicle_speed_kmh': float(data['vehicle_speeds_mps'].max()*3.6),
            'internal_microstep_peak_kn': solver['numerical']['live']['internal_peak_kn'],
            'brake_segments': int(segment.max()),
            '140kpa_onsets_s': t[deep_start].tolist(),
            '140kpa_onsets_within_common_head_coverage_s': t[deep_start & common].tolist(),
            'refill_elapsed_at_segment_starts_s': [float(np.asarray(
                data['predecision_refill_elapsed_s'][i]).flat[0]) for i in starts],
            'safety_events_by_column': data['safety_rule_counts'].sum(axis=(0, 1)).tolist(),
            'full_route_completed': record['summary']['full_route_completed'],
            'stop_reason': record['summary'].get('diagnostic_stop_reason'),
            'source_sha256': {n: hashlib.sha256((root/n).read_bytes()).hexdigest()
                              for n in ('run/result.json', 'run/trajectory.npz', 'solver_result.json')}}
    report['note'] = ('Less route covered can reduce event counts. Common-coverage counts do not '
                      'establish full-route performance or physical parameter calibration.')
    return report


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--baseline', type=Path, required=True)
    parser.add_argument('--candidate', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    report = compare(args.baseline, args.candidate)
    with args.output.open('x', encoding='utf-8') as stream:
        json.dump(report, stream, indent=2)
    print(json.dumps(report, indent=2))
