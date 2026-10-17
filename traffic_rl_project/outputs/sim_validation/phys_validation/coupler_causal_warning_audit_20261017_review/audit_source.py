"""Causal force/relative-speed warnings on recorded native trajectories.

This audit measures warnings on the realised policy trajectory. It neither
predicts alternative control responses nor certifies a safety envelope.
"""
import argparse
import hashlib
import json
from pathlib import Path
import sys

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from src.metadata import build_metadata
from src.physics_governance import official_entry_guard, official_world_config


def warning_audit(force, velocity, dt, horizon_s, limit_n, lag_s=0.5):
    """Exclude right-censored futures; forecast uses only current/past samples."""
    force = np.asarray(force, dtype=float)
    velocity = np.asarray(velocity, dtype=float)
    if force.ndim != 2 or velocity.shape != (len(force), force.shape[1] + 1):
        raise ValueError('Require time-by-interface forces and adjacent vehicle velocities')
    if not np.all(np.isfinite(force)) or not np.all(np.isfinite(velocity)):
        raise ValueError('Finite trajectories required')
    if min(dt, horizon_s, limit_n, lag_s) <= 0:
        raise ValueError('Positive time and force parameters required')
    lag = max(1, int(round(lag_s / dt)))
    horizon = max(1, int(round(horizon_s / dt)))
    indices = np.arange(lag, len(force) - horizon)
    if not len(indices):
        raise ValueError('Insufficient complete past/future windows')
    peak = np.abs(force).max(axis=1)
    current = force[indices]
    rate = (current - force[indices - lag]) / (lag * dt)
    outward = np.maximum(np.sign(current) * rate, 0.0)
    relative_speed = velocity[indices, :-1] - velocity[indices, 1:]
    loading = np.sign(current) * relative_speed < 0.0
    forecasts = {
        'current_force': np.abs(current).max(axis=1),
        'force_rate': (np.abs(current) + horizon * dt * outward).max(axis=1),
        'force_rate_relative_speed': (
            np.abs(current) + horizon * dt * outward * loading).max(axis=1),
    }
    future = np.lib.stride_tricks.sliding_window_view(peak[1:], horizon).max(axis=1)[indices]
    # Already-over-limit samples are detection, not prospective warnings.
    eligible = peak[indices] <= limit_n
    positive = future > limit_n
    crossing = np.flatnonzero(peak > limit_n)
    first_crossing = int(crossing[0]) if len(crossing) else None
    result = {'samples': int(eligible.sum()), 'positive_samples': int((positive & eligible).sum()),
              'horizon_s': horizon * dt, 'lag_s': lag * dt,
              'observed_first_crossing_s': (first_crossing + 1) * dt if first_crossing is not None else None,
              'methods': {}}
    for name, prediction in forecasts.items():
        alarm = prediction > limit_n
        tp = int((alarm & positive & eligible).sum())
        fp = int((alarm & ~positive & eligible).sum())
        fn = int((~alarm & positive & eligible).sum())
        alarms = alarm & eligible
        onset = alarms & ~np.r_[False, alarms[:-1]]
        valid_warning = np.flatnonzero(alarms & positive & (indices < first_crossing)) if first_crossing is not None else []
        lead = (first_crossing - indices[valid_warning[0]]) * dt if len(valid_warning) else None
        result['methods'][name] = {
            'true_positive': tp, 'false_positive': fp, 'false_negative': fn,
            'recall': tp / (tp + fn) if tp + fn else None,
            'precision': tp / (tp + fp) if tp + fp else None,
            'false_warning_seconds': fp * dt, 'warning_episodes': int(onset.sum()),
            'first_observed_crossing_warning_lead_s': lead,
        }
    return result


def main():
    official_entry_guard(__file__)
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--archives', type=Path, nargs='+', required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=False)
    source = Path(__file__).read_bytes()
    (args.output / 'audit_source.py').write_bytes(source)
    first = json.loads((args.archives[0] / 'result.json').read_text(encoding='utf-8'))
    result = {'metadata': build_metadata(str(Path.cwd()), 'official',
                  official_world_config(env_cfg=first['metadata']['env_cfg']), 0, __file__,
                  extra={'scope': 'archived-warning audit; not a control or safety guarantee',
                         'audit_source_sha256': hashlib.sha256(source).hexdigest(),
                         'world_config_scope': 'reference archive only; each case retains its original metadata'}), 'cases': []}
    for root in args.archives:
        parent = json.loads((root / 'result.json').read_text(encoding='utf-8'))
        with np.load(root / 'trajectory.npz') as data:
            rows = data['rows']
            dt = float(np.median(np.diff(rows[:, 0])))
            # Deliberately audit each train independently, never merge force arrays.
            for train in range(data['coupler_interface_force_n'].shape[1]):
                item = {'archive': str(root.resolve()), 'train': train,
                        'trajectory_sha256': hashlib.sha256((root / 'trajectory.npz').read_bytes()).hexdigest(),
                        'source_metadata': parent['metadata'], 'audits': []}
                for limit_kn in (1350, 1500):
                    for horizon in (1.0, 2.0, 3.0):
                        audit = warning_audit(data['coupler_interface_force_n'][:, train],
                                              data['vehicle_speeds_mps'][:, train],
                                              dt, horizon, limit_kn * 1000)
                        item['audits'].append({'limit_kn': limit_kn, **audit})
                result['cases'].append(item)
    (args.output / 'result.json').write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
    for case in result['cases']:
        print(Path(case['archive']).name, json.dumps(case['audits'][4]), flush=True)


if __name__ == '__main__':
    main()
