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
from src.evaluation.adaptive_newmark_candidate import coupled_candidate
from src.evaluation.release_feasibility import evaluate_native_release
from src.metadata import build_metadata
from src.physics_governance import official_entry_guard, official_world_config


def main():
    logging.basicConfig(level=logging.INFO)
    official_entry_guard(__file__)
    parser = argparse.ArgumentParser()
    parser.add_argument('--state-dir', type=Path, required=True)
    parser.add_argument('--controller-source', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--horizon-s', type=float, default=20.0)
    args = parser.parse_args()
    if not np.isfinite(args.horizon_s) or args.horizon_s <= 0:
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
                       (Path('src/evaluation/adaptive_newmark_candidate.py'), 'candidate_source.py'),
                       (args.controller_source, 'controller_source.py')):
        (args.output / name).write_bytes(path.read_bytes())
    samples = []
    outcomes = {}
    try:
        for label in ('native', 'balanced'):
            if label == 'native':
                forecast = evaluate_native_release(saved['train_env'], controller, saved['controls'],
                    args.horizon_s, singleton_leader_offset_mps=TrainFleetEnv.LEAD_TAIL_OFFSET_MPS)
            else:
                with coupled_candidate(samples, max_step=0.000625, force_tol_n=10):
                    forecast = evaluate_native_release(saved['train_env'], controller, saved['controls'],
                        args.horizon_s, singleton_leader_offset_mps=TrainFleetEnv.LEAD_TAIL_OFFSET_MPS)
            np.savez_compressed(args.output / (label + '.npz'), rows=forecast.pop('trajectory'))
            outcomes[label] = forecast
            print(label, json.dumps(forecast), flush=True)
        outcomes['solver'] = {
            'mechanical_intervals': len(samples),
            'accepted_microsteps': sum(s['accepted'] for s in samples),
            'rejected_trials': sum(s['rejected'] for s in samples),
            'max_accepted_force_residual_n': max(s['max_force_residual_n'] for s in samples),
            'internal_peak_kn': max(s['peak_interface_n'] for s in samples) / 1000,
            'max_step_s': 0.000625, 'force_tolerance_n': 10, 'displacement_tolerance_m': 1e-9}
        result = {'outcomes': outcomes, 'metadata': {
            'native_state_manifest': manifest,
            'controller_sha256': hashlib.sha256(source.encode()).hexdigest(),
            'candidate_sha256': hashlib.sha256(Path('src/evaluation/adaptive_newmark_candidate.py').read_bytes()).hexdigest(),
            'scope': 'same native state; zero-RL copied release forecast with live pneumatic/control feedback; not full-route acceptance',
            'production_changed': False, 'experimental_numerical_solver': True}}
        (args.output / 'result.json').write_text(json.dumps(result, indent=2), encoding='utf-8')
    finally:
        saved['train_env'].close()


if __name__ == '__main__':
    main()
