"""Compare native and experimental balanced coupled release forecasts."""
import argparse
import copy
import hashlib
import json
import logging
import pickle
import sys
import time
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from src.environments.train_fleet_env import TrainFleetEnv
from src.evaluation.diagnose_actuator_sensitivity import native_source_hashes
from src.evaluation.adaptive_newmark_candidate import coupled_candidate
from src.evaluation.release_feasibility import evaluate_native_release
from src.evaluation.release_feasibility import clone_native_prediction_env
from src.evaluation.refine_pneumatic_interval import refined_pneumatic_interval
from src.evaluation.fractional_air_timing import fractional_air_timing, fractional_advance_source
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
    parser.add_argument('--max-step', type=float, default=0.000625)
    parser.add_argument('--force-tolerance-n', type=float, default=10.0)
    parser.add_argument('--solver', choices=['balanced', 'newton', 'newton_analytic'], default='balanced')
    parser.add_argument('--native-reference-dir', type=Path)
    parser.add_argument('--record-after-s', type=float,
                        help='Archive signed interface force, deflection and relative velocity')
    parser.add_argument('--checkpoint-at-s', type=float,
                        help='Save one complete diagnostic forecast state at a control boundary')
    parser.add_argument('--air-step', type=float,
                        help='Diagnostic native pressure/control-force interval; default .01 s')
    parser.add_argument('--hold-coarse-grade', action='store_true',
                        help='Hold each original .01 s grade during refined pressure intervals')
    parser.add_argument('--fractional-air-timing', action='store_true',
                        help='Experimental exact arrival/fill/exhaust timing inside each interval')
    parser.add_argument('--ramp-air-force', action='store_true',
                        help='Diagnostic air-force interpolation at mechanical endpoints')
    args = parser.parse_args()
    if args.ramp_air_force and not args.fractional_air_timing:
        parser.error('Air-force interpolation requires fractional air timing')
    if not np.isfinite(args.horizon_s) or args.horizon_s <= 0:
        parser.error('Finite observation time and positive horizon required')
    if args.record_after_s is not None and (not np.isfinite(args.record_after_s)
                                           or not 0 <= args.record_after_s < args.horizon_s):
        parser.error('Trace start must lie in the forecast horizon')
    if args.checkpoint_at_s is not None and (not np.isfinite(args.checkpoint_at_s)
                                            or not 0 < args.checkpoint_at_s <= args.horizon_s):
        parser.error('Checkpoint must lie in the forecast horizon')
    if args.air_step is not None and (not np.isfinite(args.air_step) or not 0 < args.air_step <= .01):
        parser.error('Air interval must be in (0, .01]')
    if args.hold_coarse_grade and args.air_step is None:
        parser.error('Grade isolation requires an explicit refined air interval')
    if not np.all(np.isfinite([args.max_step, args.force_tolerance_n])) or min(
            args.max_step, args.force_tolerance_n) <= 0:
        parser.error('Positive finite solver settings required')
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
                       (Path('src/evaluation/newton_mechanics_candidate.py'), 'newton_source.py'),
                       (Path('src/evaluation/native_force_tangent.py'), 'force_tangent_source.py'),
                       (Path('src/evaluation/release_feasibility.py'), 'release_forecast_source.py'),
                       (Path('src/evaluation/refine_pneumatic_interval.py'), 'pneumatic_refinement_source.py'),
                       (Path('src/evaluation/fractional_air_timing.py'), 'fractional_air_source.py'),
                       (args.controller_source, 'controller_source.py')):
        (args.output / name).write_bytes(path.read_bytes())
    (args.output/'fractional_advance_source.py').write_text(fractional_advance_source(), encoding='utf-8')
    samples = []
    outcomes = {}
    traces = []

    def observe(branch, ctrl, row):
        if args.record_after_s is not None and row[0] >= args.record_after_s:
            dyn = branch.dynamics
            traces.append((row[0], dyn.coupler_interface_forces().copy(),
                           (dyn.pos[1:] - dyn.pos[:-1]) + dyn.coupler.free_length_m,
                           dyn.vel[:-1] - dyn.vel[1:], dyn._brake_pressure.copy(),
                           (dyn._brake_pressure*dyn._air_brake_release_frac*dyn._air_brake_active).copy()))
        checkpoint = args.output / 'forecast_checkpoint'
        if (args.checkpoint_at_s is not None and row[0] >= args.checkpoint_at_s - 1e-9
                and not checkpoint.exists()):
            # Entire native pressure/control/mechanical state, never NPZ reconstruction.
            checkpoint.mkdir()
            copied = clone_native_prediction_env(branch)
            try:
                payload = pickle.dumps({'train_env': copied,
                    'controller_state': copy.deepcopy(ctrl.__dict__),
                    'controls': dict(saved['controls'])}, protocol=pickle.HIGHEST_PROTOCOL)
            finally:
                copied.close()
            numerical_sources = {name: hashlib.sha256((args.output/name).read_bytes()).hexdigest()
                for name in ('candidate_source.py', 'newton_source.py', 'force_tangent_source.py',
                             'fractional_air_source.py', 'fractional_advance_source.py',
                             'pneumatic_refinement_source.py')}
            (checkpoint/'native_release_state.pkl').write_bytes(payload)
            (checkpoint/'controller_source.py').write_text(source, encoding='utf-8')
            (checkpoint/'native_release_state.json').write_text(json.dumps({
                'format': 'trusted-local-native-release-state-v1',
                'sha256': hashlib.sha256(payload).hexdigest(),
                'controller_sha256': hashlib.sha256(source.encode()).hexdigest(),
                'native_source_sha256': manifest['native_source_sha256'],
                'elapsed_s': float(branch.dynamics.time), 'env_cfg': manifest['env_cfg'],
                'origin_state_sha256': manifest['sha256'],
                'forecast_elapsed_s': row[0],
                'experimental_numerical_solver': {'method': args.solver,
                    'max_step_s': args.max_step, 'force_tolerance_n': args.force_tolerance_n,
                    'fractional_air_timing': args.fractional_air_timing,
                    'ramp_air_force': args.ramp_air_force,
                    'air_step_s': args.air_step or .01,
                    'source_sha256': numerical_sources},
                'scope': 'complete single-train forecast state; recursive guard bypass active; not online or full-route acceptance',
                'numpy_version': np.__version__, 'python_version': list(sys.version_info[:2])},
                indent=2), encoding='utf-8')

    try:
        for label in ('native', 'balanced'):
            if label == 'native':
                if args.native_reference_dir is not None:
                    reference = json.loads((args.native_reference_dir / 'result.json').read_text(encoding='utf-8'))
                    if (reference['metadata']['native_state_manifest']['sha256'] != manifest['sha256']
                            or reference['metadata']['controller_sha256'] != hashlib.sha256(source.encode()).hexdigest()
                            or reference['outcomes']['native']['horizon_s'] != args.horizon_s):
                        raise ValueError('Native reference state/controller/horizon differs')
                    forecast = copy.deepcopy(reference['outcomes']['native'])
                    with np.load(args.native_reference_dir / 'native.npz', allow_pickle=False) as archive:
                        forecast['trajectory'] = archive['rows'].copy()
                else:
                    forecast = evaluate_native_release(saved['train_env'], controller, saved['controls'],
                        args.horizon_s, singleton_leader_offset_mps=TrainFleetEnv.LEAD_TAIL_OFFSET_MPS)
            else:
                started = time.perf_counter()
                with fractional_air_timing(args.fractional_air_timing), refined_pneumatic_interval(args.air_step, args.hold_coarse_grade), coupled_candidate(samples, max_step=args.max_step,
                                       force_tol_n=args.force_tolerance_n,
                                       numerical_solver=args.solver,
                                       ramp_air_force=args.ramp_air_force):
                    forecast = evaluate_native_release(saved['train_env'], controller, saved['controls'],
                        args.horizon_s, singleton_leader_offset_mps=TrainFleetEnv.LEAD_TAIL_OFFSET_MPS,
                        step_observer=observe)
                forecast['wall_seconds'] = time.perf_counter() - started
                if traces:
                    np.savez_compressed(args.output / 'interface_trace.npz',
                        elapsed_s=np.asarray([t[0] for t in traces]),
                        force_n=np.asarray([t[1] for t in traces]),
                        deflection_m=np.asarray([t[2] for t in traces]),
                        relative_velocity_mps=np.asarray([t[3] for t in traces]),
                        cylinder_pressure_coefficient=np.asarray([t[4] for t in traces]),
                        effective_pressure_coefficient=np.asarray([t[5] for t in traces]))
            np.savez_compressed(args.output / (label + '.npz'), rows=forecast.pop('trajectory'))
            outcomes[label] = forecast
            print(label, json.dumps(forecast), flush=True)
        outcomes['solver'] = {
            'method': args.solver,
            'mechanical_intervals': len(samples),
            'accepted_microsteps': sum(s['accepted'] for s in samples),
            'rejected_trials': sum(s['rejected'] for s in samples),
            'max_accepted_force_residual_n': max(s['max_force_residual_n'] for s in samples),
            'internal_peak_kn': max(s['peak_interface_n'] for s in samples) / 1000,
            'max_step_s': args.max_step, 'force_tolerance_n': args.force_tolerance_n,
            'pressure_control_interval_s': args.air_step or .01,
            'hold_coarse_grade': args.hold_coarse_grade,
            'fractional_air_timing': args.fractional_air_timing,
            'ramp_air_force': args.ramp_air_force,
            'displacement_tolerance_m': 1e-9}
        result = {'outcomes': outcomes, 'metadata': {
            'native_state_manifest': manifest,
            'controller_sha256': hashlib.sha256(source.encode()).hexdigest(),
            'candidate_sha256': hashlib.sha256((args.output/'candidate_source.py').read_bytes()).hexdigest(),
            'newton_sha256': hashlib.sha256((args.output/'newton_source.py').read_bytes()).hexdigest(),
            'force_tangent_sha256': hashlib.sha256((args.output/'force_tangent_source.py').read_bytes()).hexdigest(),
            'release_forecast_sha256': hashlib.sha256((args.output/'release_forecast_source.py').read_bytes()).hexdigest(),
            'pneumatic_refinement_sha256': hashlib.sha256((args.output/'pneumatic_refinement_source.py').read_bytes()).hexdigest(),
            'fractional_air_sha256': hashlib.sha256((args.output/'fractional_air_source.py').read_bytes()).hexdigest(),
            'native_reference_dir': str(args.native_reference_dir) if args.native_reference_dir else None,
            'scope': 'same native state; zero-RL copied release forecast with live pneumatic/control feedback; not full-route acceptance',
            'production_changed': False, 'experimental_numerical_solver': True}}
        result['metadata']['trace_after_s'] = args.record_after_s
        result['metadata']['checkpoint_at_s'] = args.checkpoint_at_s
        result['metadata']['evaluation'] = build_metadata(str(Path.cwd()), 'OFFICIAL',
            official_world_config(env_cfg=manifest['env_cfg']), 0, __file__, extra={
                'args': {k: str(v) if isinstance(v, Path) else v for k, v in vars(args).items()},
                'scope': 'numerical convergence diagnostic; not full-route acceptance'})
        (args.output / 'result.json').write_text(json.dumps(result, indent=2), encoding='utf-8')
    finally:
        saved['train_env'].close()


if __name__ == '__main__':
    main()
