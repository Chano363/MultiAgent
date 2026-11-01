"""Offline causal same-position reference audit; never an online controller.

Match each follower head to its predecessor's earlier recorded passage at that
head position. Preserve the existing distance metrics; do not replay brake
commands or reset pneumatic state. Reject unlinked or non-monotone archives.
"""
import argparse
import hashlib
import json
from pathlib import Path

import numpy as np


def match_past_passage(times, leader_positions, follower_positions):
    if (not np.isfinite(times).all() or not np.isfinite(leader_positions).all()
            or not np.isfinite(follower_positions).all()
            or np.any(np.diff(times) <= 0) or np.any(np.diff(leader_positions) <= 0)):
        raise ValueError('Finite strictly increasing time and predecessor motion required')
    right = np.searchsorted(leader_positions, follower_positions, side='left')
    bounded = (right > 0) & (right < len(times))
    indices = np.flatnonzero(bounded)
    lo, hi = right[indices]-1, right[indices]
    fraction = ((follower_positions[indices]-leader_positions[lo])
                / (leader_positions[hi]-leader_positions[lo]))
    passage = times[lo]+fraction*(times[hi]-times[lo])
    # Both interpolation samples must already exist at follower evaluation time.
    causal = (times[hi] <= times[indices]+1e-7) & (passage < times[indices]-1e-7)
    return indices[causal], lo[causal], hi[causal], fraction[causal], passage[causal]


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--segments', type=Path, nargs='+', required=True)
    p.add_argument('--output', type=Path, required=True)
    args = p.parse_args()
    blocks, provenance, previous_manifest, native, settings = [], {}, None, None, None
    for directory in args.segments:
        metadata = json.loads((directory/'metadata.json').read_text(encoding='utf-8'))
        initial = metadata['initial_fleet_manifest']
        if native is not None and initial['native_source_sha256'] != native:
            raise ValueError('Native model differs')
        if settings is not None and initial['numerical']['settings'] != settings:
            raise ValueError('Mechanical integration settings differ')
        if previous_manifest is not None and initial['sha256'] != previous_manifest['sha256']:
            raise ValueError('Segments are not linked by the exact checkpoint SHA')
        native, settings = initial['native_source_sha256'], initial['numerical']['settings']
        with np.load(directory/'trajectory.npz') as a, np.load(directory/'telemetry.npz') as b:
            blocks.append(dict(time=a['rows'][:, 0], head=b['heads'],
                head_speed=a['vehicle_speeds_mps'][:, :, 0]*3.6,
                mean_speed=a['vehicle_speeds_mps'].mean(axis=2)*3.6,
                source=b['ab_source_on'].reshape(len(a['rows']), 3, -1).any(axis=2),
                refill=b['ab_refill_remaining_s'].reshape(len(a['rows']), 3, -1).max(axis=2)))
        previous_manifest = json.loads((directory/'fleet_state.json').read_text(encoding='utf-8'))
        for name in ('metadata.json', 'fleet_state.json', 'trajectory.npz', 'telemetry.npz'):
            provenance[str(directory/name)] = hashlib.sha256((directory/name).read_bytes()).hexdigest()
    data = {k: np.concatenate([b[k] for b in blocks]) for k in blocks[0]}
    times = data['time']
    if np.any(abs(np.diff(times)-.1) > 1e-6):
        raise ValueError('Unique contiguous 0.1-second samples required')
    result = dict(scope='Offline causal reference comparison, not a controller or acceptance',
        assumptions=['Head-position passage matching uses predecessor history only',
            'No extrapolation beyond archived predecessor positions',
            'Continuous speed is interpolated; binary source uses previous sample',
            'Same-position matching does not copy pressure, prove recharge or predict future safety',
            'Same-time and same-position tracking errors are different quantities; neither replaces gap/ATP metrics'],
        window_s=[float(times[0]), float(times[-1])], pairs=[], source_sha256=provenance,
        entry_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest())
    records = {}
    for j in (1, 2):
        indices, lo, hi, fraction, passage = match_past_passage(
            times, data['head'][:, j-1], data['head'][:, j])
        if not len(indices):
            raise ValueError('No causally covered predecessor passage')
        reference = (data['head_speed'][lo, j-1]*(1-fraction)
                     + data['head_speed'][hi, j-1]*fraction)
        measured = data['head_speed'][indices, j]
        same_time = data['head_speed'][indices, j-1]
        delay = times[indices]-passage
        pair = dict(follower_one_based=j+1, covered_samples=len(indices),
            coverage_fraction=len(indices)/len(times),
            covered_window_s=[float(times[indices[0]]), float(times[indices[-1]])],
            same_time_speed_mae_kmh=float(abs(measured-same_time).mean()),
            same_position_speed_mae_kmh=float(abs(measured-reference).mean()),
            delay_s_min_median_max=[float(np.min(delay)), float(np.median(delay)), float(np.max(delay))],
            source_mode_disagreement_fraction=float(np.mean(
                data['source'][indices, j] != data['source'][lo, j-1])))
        result['pairs'].append(pair)
        records[f'pair_{j}_{j+1}'] = np.column_stack((times[indices], passage,
            data['head'][indices, j], measured, same_time, reference, delay,
            data['source'][indices, j], data['source'][lo, j-1], data['refill'][indices, j]))
    args.output.mkdir(parents=True, exist_ok=False)
    result['columns'] = ['time_s', 'predecessor_passage_s', 'head_m', 'actual_head_kmh',
        'same_time_reference_kmh', 'same_position_reference_kmh', 'delay_s',
        'actual_ab_source_on', 'historical_ab_source_on', 'actual_refill_remaining_s']
    np.savez_compressed(args.output/'reference.npz', **records)
    (args.output/'result.json').write_text(json.dumps(result, indent=2), encoding='utf-8')
    (args.output/'entry_source.py').write_bytes(Path(__file__).read_bytes())
    print(json.dumps({k:v for k,v in result.items() if k != 'source_sha256'}, indent=2))


if __name__ == '__main__':
    main()
