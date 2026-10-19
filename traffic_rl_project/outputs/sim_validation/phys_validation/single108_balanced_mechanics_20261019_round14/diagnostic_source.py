"""Additional fixed-input mechanical refinements from our trusted capture."""
import argparse
import copy
import hashlib
import json
import logging
import pickle
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from src.evaluation.diagnose_actuator_sensitivity import native_source_hashes
from src.evaluation.newmark_observer import replay_fixed_mechanics
from src.evaluation.adaptive_newmark_candidate import advance_mechanics


def main():
    logging.basicConfig(level=logging.INFO)
    parser = argparse.ArgumentParser()
    parser.add_argument('--capture-dir', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--subdivisions', type=int, nargs='+', default=[8, 16])
    parser.add_argument('--tolerance', type=float)
    parser.add_argument('--max-iter', type=int)
    parser.add_argument('--adaptive', action='store_true')
    parser.add_argument('--solver', choices=['native', 'balanced'], default='native')
    parser.add_argument('--max-step', type=float, default=0.00125)
    parser.add_argument('--force-tolerance-n', type=float, default=100.0)
    args = parser.parse_args()
    if not args.subdivisions or min(args.subdivisions) < 1 or len(set(args.subdivisions)) != len(args.subdivisions):
        parser.error('Unique positive subdivisions required')
    if args.tolerance is not None and (not np.isfinite(args.tolerance) or args.tolerance <= 0):
        parser.error('Tolerance must be positive and finite')
    if args.max_iter is not None and args.max_iter < 1:
        parser.error('Iteration limit must be positive')
    directory = args.capture_dir.resolve()
    if not directory.is_relative_to((Path.cwd() / 'outputs/sim_validation/phys_validation').resolve()):
        parser.error('Only trusted local mechanical captures may be loaded')
    origin = json.loads((directory / 'result.json').read_text(encoding='utf-8'))
    payload = (directory / 'trusted_mechanics_initial.pkl').read_bytes()
    if (hashlib.sha256(payload).hexdigest() != origin['summary']['mechanics_initial_sha256']
            or not origin['summary']['observer_trajectory_exact']
            or not origin['summary']['mechanics_refinement'][0]['native_replay_exact']
            or native_source_hashes() != origin['metadata']['native_state_manifest']['native_source_sha256']):
        raise ValueError('Original replay or state provenance differs; do not deserialize')
    # This is our own numerical capture, never an external pickle.
    capture = {'initial_dynamics': pickle.loads(payload)}
    with np.load(directory / 'mechanics_inputs.npz', allow_pickle=False) as saved:
        capture.update({key: saved[key].copy() for key in saved.files})
    args.output.mkdir(parents=True, exist_ok=False)
    for path, name in ((Path(__file__), 'diagnostic_source.py'),
                       (Path('src/evaluation/newmark_observer.py'), 'observer_source.py'),
                       (Path('src/evaluation/adaptive_newmark_candidate.py'), 'candidate_source.py')):
        (args.output / name).write_bytes(path.read_bytes())
    result = {'metadata': {
        'origin_result_sha256': hashlib.sha256((directory / 'result.json').read_bytes()).hexdigest(),
        'input_force_grade_sha256': hashlib.sha256((directory / 'mechanics_inputs.npz').read_bytes()).hexdigest(),
        'initial_mechanics_sha256': hashlib.sha256(payload).hexdigest(),
        'native_source_sha256': native_source_hashes(),
        'numpy_version': np.__version__,
        'scope': 'fixed identical force/grade schedule; mechanics only, not coupled pneumatic or controller acceptance'},
        'cases': []}
    if args.adaptive:
        dyn = copy.deepcopy(capture['initial_dynamics'])
        totals = dict(attempts=0, rejected=0, accepted=0)
        peaks, forces, positions, velocities, records = [], [], [], [], []
        for force, grade, dt in zip(capture['control_forces'], capture['grade'], capture['dt']):
            dyn.grade = grade.copy()
            stat = advance_mechanics(dyn, force, float(dt), max_step=args.max_step,
                                     tol=args.tolerance or 1e-9,
                                     max_iter=args.max_iter or 100,
                                     force_tol_n=args.force_tolerance_n, solver=args.solver)
            for key in totals:
                totals[key] += stat[key]
            records.append([stat['min_accepted_step_s'], stat['max_force_residual_n']])
            peaks.append(stat['peak_interface_n'])
            forces.append(dyn.coupler_interface_forces().copy())
            positions.append(dyn.pos.copy())
            velocities.append(dyn.vel.copy())
        np.savez_compressed(args.output / 'adaptive_mechanics.npz',
                            forces_n=forces, positions=positions, velocities=velocities,
                            interval_peak_n=peaks, step_stats=records)
        result['cases'].append({**totals, 'peak_kn': float(np.max(peaks) / 1000),
                                'solver': args.solver,
                                'max_step_s': args.max_step,
                                'min_accepted_step_s': float(np.min(np.asarray(records)[:, 0])),
                                'max_force_residual_n': float(np.max(np.asarray(records)[:, 1])),
                                'tolerance_m': args.tolerance or 1e-9,
                                'max_iter': args.max_iter or 100,
                                'force_tolerance_n': args.force_tolerance_n})
        (args.output / 'result.json').write_text(json.dumps(result, indent=2), encoding='utf-8')
        print(json.dumps(result['cases'][0]), flush=True)
        return
    for case in replay_fixed_mechanics(capture, tuple(args.subdivisions),
                                       tol=args.tolerance, max_iter=args.max_iter):
        arrays = {key: case.pop(key) for key in
                  ('positions', 'velocities', 'aligned_peak_n', 'iterations')}
        np.savez_compressed(args.output / f'mechanics_split{case["subdivision"]}.npz', **arrays)
        result['cases'].append(case)
        (args.output / 'result.json').write_text(json.dumps(result, indent=2), encoding='utf-8')
        print(json.dumps(case), flush=True)


if __name__ == '__main__':
    main()
