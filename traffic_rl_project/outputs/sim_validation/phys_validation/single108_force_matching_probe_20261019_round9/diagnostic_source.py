"""Paired closed-loop release forecasts from our trusted native state export."""
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
from src.evaluation.release_feasibility import evaluate_native_release
from src.metadata import build_metadata
from src.physics_governance import official_entry_guard, official_world_config


def advance_braking_state(train, controller, controls, steps):
    """Naturally delay release; preserve pressure and integration history."""
    train.max_steps = max(train.max_steps, train.steps + steps + 1)
    original_release = controller.cyclic_release_kmh
    original_probe = getattr(controller, '_release_probe_active', False)
    controller._release_probe_active = True
    try:
        for _ in range(steps):
            if not controller._cyclic_braking or not any(controller._ab_on):
                raise ValueError('A delayed release requires an active native brake cycle')
            step_controls = dict(controls)
            ceiling = controls['v_max']
            cap = min(ceiling, float(train.dynamics.vel[0]) + TrainFleetEnv.LEAD_TAIL_OFFSET_MPS)
            step_controls['v_max_adj'] = cap - ceiling
            controller.cyclic_release_kmh = max(
                controls['v_min'] * 3.6,
                float(train.dynamics.vel[0]) * 3.6 - controller.AB_SUPPRESS_MARGIN_MPS * 3.6)
            action, _ = controller.get_action_decomposed(
                train, np.zeros((controller.num_locomotives, 2)), **step_controls)
            _, _, terminated, truncated, info = train.step(action)
            controller.record_executed_ed(info['actual_loco_ed'])
            if terminated or truncated:
                raise RuntimeError('Native delay ended unexpectedly')
    finally:
        controller.cyclic_release_kmh = original_release
        controller._release_probe_active = original_probe


def main():
    logging.basicConfig(level=logging.INFO)
    official_entry_guard(__file__)
    parser = argparse.ArgumentParser()
    parser.add_argument('--state-dir', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--horizon-s', type=float, default=248.5)
    parser.add_argument('--controller-source', type=Path,
                        help='Explicit alternative frozen controller; preserve original state provenance')
    parser.add_argument('--cases', nargs='+', choices=('hold50', 'hold30',
                        'hold30_repeat', 'hold30_delay02', 'hold30_delay04'))
    parser.add_argument('--hold-force-factors', nargs='+', type=float,
                        help='Engineering diagnostic factors for an explicitly parameterized candidate')
    args = parser.parse_args()
    if not np.isfinite(args.horizon_s) or args.horizon_s <= 0:
        parser.error('Positive finite horizon required')
    if args.hold_force_factors is not None and (
            args.controller_source is None or not np.all(np.isfinite(args.hold_force_factors))
            or min(args.hold_force_factors) < 0 or max(args.hold_force_factors) > 1):
        parser.error('Force factors require an explicit candidate and finite values in [0,1]')
    directory = args.state_dir.resolve()
    root = (Path.cwd() / 'outputs/sim_validation/phys_validation').resolve()
    if not directory.is_relative_to(root):
        parser.error('Only our trusted local validation state exports may be loaded')
    manifest = json.loads((directory / 'native_release_state.json').read_text(encoding='utf-8'))
    source = (directory / 'controller_source.py').read_text(encoding='utf-8')
    payload = (directory / 'native_release_state.pkl').read_bytes()
    if (manifest.get('format') != 'trusted-local-native-release-state-v1'
            or hashlib.sha256(payload).hexdigest() != manifest['sha256']
            or hashlib.sha256(source.encode()).hexdigest() != manifest['controller_sha256']
            or native_source_hashes() != manifest['native_source_sha256']
            or manifest['numpy_version'] != np.__version__
            or manifest['python_version'] != list(sys.version_info[:2])):
        raise ValueError('Native state provenance or runtime differs; do not deserialize')
    # Exclusively our own just-generated checkpoint, never external pickle.
    saved = pickle.loads(payload)
    if args.controller_source is not None:
        source = args.controller_source.read_text(encoding='utf-8')
    namespace = {'__name__': 'release_sensitivity_frozen_controller'}
    exec(compile(source, '<release_sensitivity_controller>', 'exec'), namespace)
    cls = namespace['MultiLocoController']
    if (saved['controller_state']['num_locomotives'] != 1
            or not np.isclose(saved['train_env'].dynamics.time, manifest['elapsed_s'])):
        raise ValueError('Single-locomotive checkpoint time or shape differs')
    args.output.mkdir(parents=True, exist_ok=False)
    metadata = build_metadata(str(Path.cwd()), 'official',
        official_world_config(env_cfg=manifest['env_cfg']), 0, __file__, extra={
            'native_state_manifest': manifest,
            'diagnostic_source_sha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
            'forecast_helper_sha256': hashlib.sha256(
                Path('src/evaluation/release_feasibility.py').read_bytes()).hexdigest(),
            'evaluated_controller_sha256': hashlib.sha256(source.encode()).hexdigest(),
            'scope': 'single-train local release sensitivity, not full route or cold-start robustness',
            'protocol': {'state_dir': str(directory), 'horizon_s': args.horizon_s,
                         'perturbation': 'native continued braking for 0.2/0.4s, never velocity edits',
                         'cases': args.cases, 'hold_force_factors': args.hold_force_factors,
                         'alternative_controller': str(args.controller_source) if args.controller_source else None}})
    (args.output / 'evaluated_controller_source.py').write_text(source, encoding='utf-8')
    (args.output / 'diagnostic_source.py').write_bytes(Path(__file__).read_bytes())
    result = {'metadata': metadata, 'cases': []}
    cases = [('hold50', 50.0, 0), ('hold30', 30.0, 0),
             ('hold30_repeat', 30.0, 0), ('hold30_delay02', 30.0, 2),
             ('hold30_delay04', 30.0, 4)]
    cases = [case for case in cases if args.cases is None or case[0] in args.cases]
    expanded = [(name if factor is None else f'{name}_force{factor:.3f}'.replace('.', 'p'),
                 hold, delay, factor) for name, hold, delay in cases
                for factor in (args.hold_force_factors or [None])]
    try:
        for name, hold_s, delay_steps, factor in expanded:
            train = copy.deepcopy(saved['train_env'])
            controller = cls.__new__(cls)
            controller.__dict__.update(copy.deepcopy(saved['controller_state']))
            controls = dict(saved['controls'])
            controller.ed_release_hold_s = hold_s
            if factor is not None:
                controller._release_match_factor = factor
            try:
                advance_braking_state(train, controller, controls, delay_steps)
                initial_speed = float(train.dynamics.vel[0] * 3.6)
                forecast = evaluate_native_release(train, controller, controls,
                    args.horizon_s, singleton_leader_offset_mps=TrainFleetEnv.LEAD_TAIL_OFFSET_MPS)
                rows = forecast.pop('trajectory')
                path = args.output / f'{name}.npz'
                np.savez_compressed(path, rows=rows)
                result['cases'].append({'name': name, 'hold_s': hold_s,
                    'hold_force_factor': factor,
                    'native_delay_steps': delay_steps, 'initial_head_kmh': initial_speed,
                    'min_mean_kmh': float(rows[:, 3].min() * 3.6),
                    'trajectory_sha256': hashlib.sha256(path.read_bytes()).hexdigest(), **forecast})
                print(json.dumps(result['cases'][-1]), flush=True)
                (args.output / 'result.json').write_text(
                    json.dumps(result, indent=2), encoding='utf-8')
            finally:
                train.close()
        if (args.output / 'hold30.npz').exists() and (args.output / 'hold30_repeat.npz').exists():
            first = np.load(args.output / 'hold30.npz')['rows']
            second = np.load(args.output / 'hold30_repeat.npz')['rows']
            result['repeat_exact'] = bool(np.array_equal(first, second))
        (args.output / 'result.json').write_text(json.dumps(result, indent=2), encoding='utf-8')
    finally:
        saved['train_env'].close()


if __name__ == '__main__':
    main()
