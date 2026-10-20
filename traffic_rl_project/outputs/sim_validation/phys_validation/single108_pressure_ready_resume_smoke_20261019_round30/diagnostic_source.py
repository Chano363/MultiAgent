"""Continue our single-train native state; full-route diagnostic, zero RL."""
import argparse
import copy
import hashlib
import json
import logging
import pickle
import sys
from contextlib import ExitStack
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from src.environments.train_fleet_env import TrainFleetEnv
from src.evaluation.diagnose_actuator_sensitivity import native_source_hashes
from src.metadata import build_metadata
from src.physics_governance import official_entry_guard, official_world_config


def main():
    logging.basicConfig(level=logging.INFO)
    official_entry_guard(__file__)
    parser = argparse.ArgumentParser()
    parser.add_argument('--state-dir', type=Path, required=True)
    parser.add_argument('--controller-source', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--finish-m', type=float, default=49600)
    parser.add_argument('--steps', type=int, default=28345)
    parser.add_argument('--save-native-release-state', action='store_true')
    parser.add_argument('--resume-experimental', action='store_true',
                        help='Require and retain the checkpoint numerical solver and source hashes')
    args = parser.parse_args()
    if args.steps < 1 or not np.isfinite(args.finish_m):
        parser.error('Positive step budget and finite finish position required')
    directory = args.state_dir.resolve()
    if not directory.is_relative_to((Path.cwd() / 'outputs/sim_validation/phys_validation').resolve()):
        parser.error('Use only our trusted local native state export')
    manifest = json.loads((directory / 'native_release_state.json').read_text(encoding='utf-8'))
    if bool(manifest.get('experimental_numerical_solver')) != args.resume_experimental:
        parser.error('Experimental checkpoints require --resume-experimental; native ones must not use it')
    if args.resume_experimental:
        from src.evaluation.checkpoint_numerics import verify_checkpoint_numerics
        verify_checkpoint_numerics(manifest)
    payload = (directory / 'native_release_state.pkl').read_bytes()
    original = (directory / 'controller_source.py').read_text(encoding='utf-8')
    if (manifest.get('format') != 'trusted-local-native-release-state-v1'
            or manifest['sha256'] != hashlib.sha256(payload).hexdigest()
            or manifest['controller_sha256'] != hashlib.sha256(original.encode()).hexdigest()
            or manifest['native_source_sha256'] != native_source_hashes()
            or manifest['numpy_version'] != np.__version__
            or manifest['python_version'] != list(sys.version_info[:2])):
        raise ValueError('Native checkpoint provenance differs; do not deserialize')
    # Only our own hash-verified checkpoint, never external pickle.
    saved = pickle.loads(payload)
    source = args.controller_source.read_text(encoding='utf-8')
    namespace = {'__name__': 'native_continuation_frozen_controller'}
    exec(compile(source, '<native_continuation_controller>', 'exec'), namespace)
    controller = namespace['MultiLocoController'].__new__(namespace['MultiLocoController'])
    controller.__dict__.update(copy.deepcopy(saved['controller_state']))
    if getattr(controller, '_release_probe_active', False):
        raise ValueError('Cannot treat a copied forecast branch as online continuation')
    train, controls = saved['train_env'], saved['controls']
    if (controller.num_locomotives != 1
            or not np.isclose(train.dynamics.time, manifest['elapsed_s'])):
        raise ValueError('Not the expected single-train native state')
    train.max_steps = max(train.max_steps, train.steps + args.steps + 1)
    args.output.mkdir(parents=True, exist_ok=False)
    (args.output / 'controller_source.py').write_text(source, encoding='utf-8')
    (args.output / 'diagnostic_source.py').write_bytes(Path(__file__).read_bytes())
    metadata = build_metadata(str(Path.cwd()), 'official',
        official_world_config(env_cfg=manifest['env_cfg']), 0, __file__, extra={
            'initial_native_manifest': manifest,
            'controller_sha256': hashlib.sha256(source.encode()).hexdigest(),
            'controller_change': 'explicit alternative frozen candidate from same native history',
            'protocol': {'steps': args.steps, 'finish_m': args.finish_m,
                         'state_dir': str(directory), 'zero_RL': True},
            'scope': 'native single-train continuation, not three-train acceptance',
            'singleton_leader_offset_mps': TrainFleetEnv.LEAD_TAIL_OFFSET_MPS})
    data = {key: [] for key in ('rows', 'commands', 'physical_loco_ed',
        'vehicle_positions_m', 'vehicle_speeds_mps', 'coupler_interface_force_n',
        'effective_pressure_coefficient', 'loco_ed_force_n',
        'controller_hold_target_kn', 'controller_ed_hold_steps')}
    reason = 'step_budget'
    error = None
    samples = []
    numerical_context = ExitStack()
    if args.resume_experimental:
        from src.evaluation.checkpoint_numerics import checkpoint_numerical_context
        numerical_context = checkpoint_numerical_context(manifest, train, samples)
        for name in ('adaptive_newmark_candidate', 'newton_mechanics_candidate',
                     'native_force_tangent', 'fractional_air_timing',
                     'refine_pneumatic_interval', 'checkpoint_numerics'):
            (args.output/(name+'_source.py')).write_bytes(
                Path('src/evaluation', name+'.py').read_bytes())
        metadata['experimental_numerical_solver'] = manifest['experimental_numerical_solver']
        metadata['scope'] = 'explicit experimental single-train continuation of complete online history'
    try:
        for step in range(args.steps):
            if (args.output / 'STOP').exists():
                reason = 'requested_stop_file'
                break
            step_controls = dict(controls)
            step_controls['v_max_adj'] = min(controls['v_max'], float(train.dynamics.vel[0])
                + TrainFleetEnv.LEAD_TAIL_OFFSET_MPS) - controls['v_max']
            step_controls['v_min_adj'] = 0.0
            action, _ = controller.get_action_decomposed(
                train, np.zeros((1, 2)), **step_controls)
            mechanical_start = len(samples)
            _, _, terminated, truncated, info = train.step(action)
            controller.record_executed_ed(info['actual_loco_ed'])
            dyn = train.dynamics
            peak = float(np.abs(dyn.coupler_interface_forces()).max())
            data['rows'].append([float(dyn.time), peak, float(dyn.vel.max()), float(dyn.vel.mean())])
            data['commands'].append(action.copy())
            data['physical_loco_ed'].append(np.asarray(info['actual_loco_ed']).copy())
            physical_ed = np.zeros(dyn.num_vehicles)
            physical_ed[train.loco_indices] = info['actual_loco_ed']
            data['loco_ed_force_n'].append(dyn._electric_braking_forces(physical_ed)[train.loco_indices].copy())
            data['controller_hold_target_kn'].append(getattr(controller, '_release_force_hold_kn', np.nan))
            data['controller_ed_hold_steps'].append(controller._ed_hold_steps)
            for key, value in (
                    ('vehicle_positions_m', dyn.pos), ('vehicle_speeds_mps', dyn.vel),
                    ('coupler_interface_force_n', dyn.coupler_interface_forces()),
                    ('effective_pressure_coefficient', dyn._brake_pressure
                     * dyn._air_brake_release_frac * dyn._air_brake_active)):
                data[key].append(value.copy())
            if step % 100 == 0:
                print(f't={dyn.time:.1f} head={dyn.pos[0]:.1f} peak={peak/1000:.1f}', flush=True)
            if not np.all(np.isfinite(data['rows'][-1])):
                reason = 'nonfinite'
                break
            step_micropeak = max((s['peak_interface_n'] for s in samples[mechanical_start:]
                                  if s.get('live')), default=peak)
            if max(peak, step_micropeak) > controller.coupler_force_limit_n:
                reason = 'coupler_limit'
                break
            if dyn.vel.max() >= controls['v_max'] - 1e-6:
                reason = 'speed_ceiling'
                break
            if dyn.vel.mean() < controls['v_min'] - 1e-6:
                reason = 'speed_floor'
                break
            if any(e.get('event') == 'release_feasibility' and e.get('at_floor')
                   and not e.get('feasible', True) for e in getattr(controller, '_ed_guard_events', [])):
                reason = 'release_infeasible_at_floor'
                break
            if dyn.pos[-1] >= args.finish_m:
                reason = 'route_completed'
                break
            if terminated or truncated:
                reason = 'environment_ended'
                break
    except KeyboardInterrupt:
        # Keep only completed recorded steps; this is not a restart checkpoint.
        reason = 'keyboard_interrupt_incomplete'
    except Exception as exc:
        reason, error = 'exception_incomplete', repr(exc)
        raise
    finally:
        numerical_context.close()
        numerical = {}
        for label in ('live', 'forecast'):
            chosen = [s for s in samples if bool(s.get('live')) == (label == 'live')]
            numerical[label] = {'mechanical_intervals': len(chosen),
                'internal_peak_kn': max((s['peak_interface_n'] for s in chosen), default=0)/1000,
                'accepted_microsteps': sum(s['accepted'] for s in chosen),
                'rejected_trials': sum(s['rejected'] for s in chosen)}
        if args.resume_experimental:
            metadata['continuation_numerical'] = numerical
        if args.save_native_release_state and reason not in (
                'keyboard_interrupt_incomplete', 'nonfinite', 'exception_incomplete'):
            from src.evaluation.release_feasibility import clone_native_prediction_env
            branch = clone_native_prediction_env(train)
            try:
                state = pickle.dumps({'train_env': branch,
                    'controller_state': copy.deepcopy(controller.__dict__),
                    'controls': dict(controls)}, protocol=pickle.HIGHEST_PROTOCOL)
            finally:
                branch.close()
            (args.output / 'native_release_state.pkl').write_bytes(state)
            (args.output / 'native_release_state.json').write_text(json.dumps({
                'format': 'trusted-local-native-release-state-v1',
                'sha256': hashlib.sha256(state).hexdigest(),
                'controller_sha256': hashlib.sha256(source.encode()).hexdigest(),
                'native_source_sha256': native_source_hashes(),
                'elapsed_s': float(train.dynamics.time), 'env_cfg': manifest['env_cfg'],
                'origin_native_manifest': manifest,
                **({'experimental_numerical_solver': manifest['experimental_numerical_solver']}
                   if args.resume_experimental else {}),
                'scope': 'single-train sensitivity only, not a complete fleet restart',
                'numpy_version': np.__version__, 'python_version': list(sys.version_info[:2]),
            }, indent=2), encoding='utf-8')
        np.savez_compressed(args.output / 'trajectory.npz',
                            **{key: np.asarray(value) for key, value in data.items()})
        rows = np.asarray(data['rows'])
        summary = {'stop_reason': reason, 'steps': len(rows),
            'error': error,
            'internal_microstep_peak_kn': numerical['live']['internal_peak_kn'] if samples else None,
            'full_route_completed': reason == 'route_completed',
            'peak_kn': float(rows[:, 1].max()/1000) if len(rows) else None,
            'max_vehicle_kmh': float(rows[:, 2].max()*3.6) if len(rows) else None,
            'min_mean_kmh': float(rows[:, 3].min()*3.6) if len(rows) else None,
            'last_time_s': float(rows[-1, 0]) if len(rows) else manifest['elapsed_s']}
        metadata['controller_events'] = getattr(controller, '_ed_guard_events', [])
        (args.output / 'result.json').write_text(json.dumps(
            {'summary': summary, 'metadata': metadata}, indent=2), encoding='utf-8')
        print(json.dumps(summary), flush=True)
        train.close()


if __name__ == '__main__':
    main()
