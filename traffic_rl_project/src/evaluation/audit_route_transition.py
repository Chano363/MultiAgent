"""Read-only transition audit; never reconstruct a restart from trajectories."""
import argparse
import hashlib
import json
from pathlib import Path

import numpy as np


def audit(root):
    result = json.loads((root / 'result.json').read_text(encoding='utf-8'))
    with np.load(root / 'trajectory.npz', allow_pickle=False) as data:
        time = data['rows'][:, 0]
        speed = data['vehicle_speeds_mps'] * 3.6
        request = data['commands'][:, 0, 1]
        starts = np.flatnonzero((request < -.1) & np.r_[True, request[1:] != request[:-1]])
        events = []
        for index in starts:
            events.append(dict(time_s=float(time[index]),
                head_m=float(data['vehicle_positions_m'][index, 0]),
                request=float(request[index]), max_vehicle_kmh=float(speed[index].max()),
                mean_kmh=float(speed[index].mean()),
                pressure_head_tail=data['effective_pressure_coefficient'][index, [0, -1]].tolist()))
        windows = {}
        for label, lower, upper in [('upgrade', 2400, 2550), ('terminal', 2900, 3100)]:
            mask = (time >= lower) & (time <= upper)
            if not mask.any():
                continue
            indices = np.flatnonzero(mask)
            accel = np.diff(speed[mask].mean(axis=1) / 3.6) / np.diff(time[mask])
            windows[label] = dict(start_s=float(time[indices[0]]), end_s=float(time[indices[-1]]),
                min_vehicle_kmh=float(speed[mask].min()), max_vehicle_kmh=float(speed[mask].max()),
                min_mean_kmh=float(speed[mask].mean(axis=1).min()),
                min_sampled_mean_acceleration_mps2=float(accel.min()),
                sampled_peak_kn=float(np.abs(data['coupler_interface_force_n'][mask]).max()/1000))
    files = ['result.json', 'trajectory.npz', 'controller_source.py',
             'native_release_state.json', 'native_release_state.pkl']
    return dict(scope='Archived continuation only; sampled windows exclude unsampled mechanical peaks',
        summary=result['summary'], deep_request_onsets=events, windows=windows,
        sha256={name: hashlib.sha256((root/name).read_bytes()).hexdigest() for name in files})


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--archive', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=False)
    (args.output/'audit.json').write_text(json.dumps(audit(args.archive), indent=2), encoding='utf-8')
    (args.output/'audit_source.py').write_bytes(Path(__file__).read_bytes())
