"""Validate local action-response interpolation against frozen native branches.

All predictions are conditional on one archived initial state and fixed air
request. This is not a transferable dynamics model or a safety certificate.
"""
import argparse
import hashlib
import itertools
import json
from pathlib import Path
import sys

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from src.metadata import build_metadata
from src.physics_governance import official_entry_guard, official_world_config


def interpolate_corners(corners, point):
    """Multilinear interpolation using only the extreme-action branches."""
    point = np.asarray(point, dtype=float)
    if point.ndim != 1 or not np.all(np.isfinite(point)) or np.any((point < 0) | (point > 1)):
        raise ValueError('Finite action coordinates in [0, 1] required')
    expected = set(itertools.product((0, 1), repeat=len(point)))
    if set(corners) != expected:
        raise ValueError('Exactly all extreme corners required')
    prediction = np.zeros_like(next(iter(corners.values())), dtype=float)
    for coordinate, trajectory in corners.items():
        weight = float(np.prod([x if bit else 1 - x for bit, x in zip(coordinate, point)]))
        prediction += weight * trajectory
    return prediction


def summarize_prediction(actual, predicted):
    actual, predicted = np.asarray(actual), np.asarray(predicted)
    error = predicted - actual
    result = {'validation_points': len(actual), 'peak_mae_kn': float(np.mean(np.abs(error))),
              'peak_abs_error_p95_kn': float(np.quantile(np.abs(error), 0.95)),
              'maximum_underprediction_kn': float(np.maximum(-error, 0).max()),
              'maximum_overprediction_kn': float(np.maximum(error, 0).max()),
              'limits': {}}
    for limit in (1350, 1500):
        safe = predicted <= limit
        unsafe = actual > limit
        result['limits'][str(limit)] = {
            'predicted_safe': int(safe.sum()),
            'actual_unsafe': int(unsafe.sum()),
            'false_safe': int((safe & unsafe).sum()),
            'false_rejection': int((~safe & ~unsafe).sum()),
        }
    return result


def audit_archive(root):
    root = Path(root)
    record = json.loads((root / 'result.json').read_text(encoding='utf-8'))
    cases = []
    for checkpoint in record['checkpoints']:
        dt = float(record['metadata']['env_cfg'].get('dt', 0.1))
        step = int(round(checkpoint['time_s'] / dt))
        branches, fingerprints = {}, {}
        for name, item in checkpoint['variants'].items():
            coordinate = tuple(np.asarray(item['ED_depths']).ravel())
            if len(coordinate) != 4:
                raise ValueError('Two-stage, two-locomotive sequence archive required')
            file = root / f'step{step}_{name}.npz'
            with np.load(file) as data:
                branches[coordinate] = data['rows'][:, 1].copy() / 1000.0
            fingerprints[file.name] = hashlib.sha256(file.read_bytes()).hexdigest()
        grid = set(itertools.product((0.0, 0.5, 1.0), repeat=4))
        partial = record['metadata'].get('protocol', {}).get('sequence_grid_mode') == 'corner_probes'
        if partial:
            probes = set(itertools.product((0.0, 1.0), repeat=4))
            probes.update([(0.5, 0.5, 0.5, 0.5), (0.0, 1.0, 0.5, 0.5),
                           (1.0, 0.0, 0.5, 0.0)])
            if set(branches) != probes:
                raise ValueError('All 19 preregistered probes must finish before analysis')
        if set(branches) != grid and not partial:
            raise ValueError('A complete 81-point frozen grid is required')
        corners = {c: branches[c] for c in itertools.product((0, 1), repeat=4)}
        predictions = {'sequence_multilinear': [], 'second_stage_bilinear': [],
                       'second_stage_corner_envelope': []}
        for point, actual_trace in sorted(branches.items()):
            full = interpolate_corners(corners, point)
            values = [('sequence_multilinear', full, any(x == 0.5 for x in point))]
            second_coordinates = list(itertools.product((0, 1), repeat=2))
            if all(point[:2] + c in branches for c in second_coordinates):
                second_corners = {c: branches[point[:2] + c] for c in second_coordinates}
                conditional = interpolate_corners(second_corners, point[2:])
                envelope = np.max(np.stack(list(second_corners.values())), axis=0)
                values.extend([
                ('second_stage_bilinear', conditional, any(x == 0.5 for x in point[2:])),
                ('second_stage_corner_envelope', envelope, any(x == 0.5 for x in point[2:])),
                ])
            for model, trace, validation in values:
                predictions[model].append({'actions': point, 'validation': validation,
                    'actual_peak_kn': max(checkpoint['initial_peak_kn'], float(actual_trace.max())),
                    'predicted_peak_kn': max(checkpoint['initial_peak_kn'], float(trace.max())),
                    'maximum_trace_abs_error_kn': float(np.max(np.abs(trace - actual_trace)))})
        models = {}
        for name, values in predictions.items():
            test = [x for x in values if x['validation']]
            if not test:
                continue
            selected = min(values, key=lambda x: x['predicted_peak_kn'])
            best_actual = min(x['actual_peak_kn'] for x in values)
            models[name] = {'summary': summarize_prediction(
                [x['actual_peak_kn'] for x in test], [x['predicted_peak_kn'] for x in test]),
                'predicted_best': selected, 'actual_best_peak_kn': best_actual,
                'selection_regret_kn': selected['actual_peak_kn'] - best_actual,
                'selection_scope': 'observed probe set only' if partial else 'complete 81-point grid',
                'points': values}
        cases.append({'checkpoint_s': checkpoint['time_s'], 'source_metadata': record['metadata'],
                      'branch_sha256': fingerprints, 'models': models})
    return {'archive': str(root.resolve()), 'checkpoints': cases}


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
        extra={'scope': 'local action interpolation audit; not a control evaluation',
               'source_sha256': hashlib.sha256(source).hexdigest(),
               'validation_scope': 'held-out action amplitudes, not unseen initial states'}),
        'archives': [audit_archive(p) for p in args.archives]}
    (args.output / 'result.json').write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
    for archive in result['archives']:
        for checkpoint in archive['checkpoints']:
            for name, model in checkpoint['models'].items():
                print(Path(archive['archive']).name, name, json.dumps(model['summary']), flush=True)


if __name__ == '__main__':
    main()
