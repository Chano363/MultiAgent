"""Observe native iteration convergence on a trusted failed control forecast."""
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
from src.environments.train_fleet_env import TrainFleetEnv
from src.evaluation.diagnose_actuator_sensitivity import native_source_hashes
from src.evaluation.newmark_observer import observe_newmark, replay_fixed_mechanics
from src.evaluation.release_feasibility import evaluate_native_release
from src.metadata import build_metadata
from src.physics_governance import official_entry_guard, official_world_config


def main():
    logging.basicConfig(level=logging.INFO)
    official_entry_guard(__file__)
    parser = argparse.ArgumentParser()
    parser.add_argument('--state-dir', type=Path, required=True)
    parser.add_argument('--controller-source', type=Path, required=True)
    parser.add_argument('--reference-npz', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--observe-after-s', type=float, default=985.0)
    parser.add_argument('--horizon-s', type=float, default=248.5)
    parser.add_argument('--mechanics-refinement', action='store_true',
                        help='Fixed force/grade-input mechanical shadow replay at1/2/4 subdivision')
    args = parser.parse_args()
    if not np.all(np.isfinite([args.observe_after_s, args.horizon_s])) or args.horizon_s <= 0:
        parser.error('Finite observation time and positive horizon required')
    directory = args.state_dir.resolve()
    if not directory.is_relative_to((Path.cwd() / 'outputs/sim_validation/phys_validation').resolve()):
        parser.error('Only trusted local native validation states may be loaded')
    manifest = json.loads((directory / 'native_release_state.json').read_text(encoding='utf-8'))
    payload = (directory / 'native_release_state.pkl').read_bytes()
    parent = (directory / 'controller_source.py').read_text(encoding='utf-8')
    if (manifest.get('format') != 'trusted-local-native-release-state-v1'
            or hashlib.sha256(payload).hexdigest() != manifest['sha256']
            or hashlib.sha256(parent.encode()).hexdigest() != manifest['controller_sha256']
            or native_source_hashes() != manifest['native_source_sha256']
            or manifest['numpy_version'] != np.__version__
            or manifest['python_version'] != list(sys.version_info[:2])):
        raise ValueError('Checkpoint provenance differs; do not deserialize')
    # Never load external pickle: this is our own recorded native state.
    saved = pickle.loads(payload)
    source = args.controller_source.read_text(encoding='utf-8')
    namespace = {'__name__': 'convergence_frozen_controller'}
    exec(compile(source, '<convergence_controller>', 'exec'), namespace)
    cls = namespace['MultiLocoController']
    controller = cls.__new__(cls)
    controller.__dict__.update(copy.deepcopy(saved['controller_state']))
    controller.ed_release_hold_s = 50.0
    controller._release_match_factor = 1.0
    args.output.mkdir(parents=True, exist_ok=False)
    for path, name in ((Path(__file__), 'diagnostic_source.py'),
                       (Path('src/evaluation/newmark_observer.py'), 'observer_source.py'),
                       (args.controller_source, 'controller_source.py')):
        (args.output / name).write_bytes(path.read_bytes())
    samples, capture = [], {}
    try:
        with observe_newmark(samples, args.observe_after_s,
                             capture=capture if args.mechanics_refinement else None):
            forecast = evaluate_native_release(saved['train_env'], controller, saved['controls'],
                args.horizon_s, singleton_leader_offset_mps=TrainFleetEnv.LEAD_TAIL_OFFSET_MPS)
        rows = forecast.pop('trajectory')
        reference = np.load(args.reference_npz, allow_pickle=False)['rows']
        exact = bool(np.array_equal(rows, reference))
        stats = np.asarray(samples)
        np.savez_compressed(args.output / 'trajectory.npz', rows=rows, iterations=stats)
        summary = {'forecast': forecast, 'observer_trajectory_exact': exact,
            'observed_substeps': len(stats),
            'unconverged_substeps': int(np.sum(stats[:, 5] == 0)) if len(stats) else 0,
            'max_displacement_residual_m': float(stats[:, 3].max()) if len(stats) else None,
            'max_iterations': int(stats[:, 2].max()) if len(stats) else None,
            'scope': 'native displacement stopping criterion only; no step-size convergence claim'}
        if args.mechanics_refinement and exact:
            np.savez_compressed(args.output / 'mechanics_inputs.npz',
                **{key: np.asarray(value) for key, value in capture.items() if key != 'initial_dynamics'})
            initial = pickle.dumps(capture['initial_dynamics'], protocol=pickle.HIGHEST_PROTOCOL)
            (args.output / 'trusted_mechanics_initial.pkl').write_bytes(initial)
            summary['mechanics_initial_sha256'] = hashlib.sha256(initial).hexdigest()
            summary['mechanics_refinement'] = []
            for case in replay_fixed_mechanics(capture):
                arrays = {key: case.pop(key) for key in
                          ('positions', 'velocities', 'aligned_peak_n', 'iterations')}
                np.savez_compressed(args.output / f'mechanics_split{case["subdivision"]}.npz', **arrays)
                summary['mechanics_refinement'].append(case)
            if not summary['mechanics_refinement'][0]['native_replay_exact']:
                raise RuntimeError('Fixed-input native replay mismatch; discard refinement interpretation')
            summary['refinement_scope'] = ('Fixed original control-force and grade samples; mechanical '
                'integration only. Not coupled pneumatic refinement or controller acceptance.')
        meta = build_metadata(str(Path.cwd()), 'official',
            official_world_config(env_cfg=manifest['env_cfg']), 0, __file__, extra={
                'native_state_manifest': manifest,
                'controller_sha256': hashlib.sha256(source.encode()).hexdigest(),
                'reference_sha256': hashlib.sha256(args.reference_npz.read_bytes()).hexdigest(),
                'observe_after_s': args.observe_after_s,
                'observer_sha256': hashlib.sha256(Path('src/evaluation/newmark_observer.py').read_bytes()).hexdigest(),
                'iteration_columns': ['time_s', 'internal_dt_s', 'iterations', 'residual_m',
                                      'tolerance_m', 'converged'],
                'physics_changed': False})
        (args.output / 'result.json').write_text(json.dumps(
            {'summary': summary, 'metadata': meta}, indent=2), encoding='utf-8')
        print(json.dumps(summary), flush=True)
        if not exact:
            raise RuntimeError('Observer changed the reference trajectory; discard convergence interpretation')
    finally:
        saved['train_env'].close()


if __name__ == '__main__':
    main()
