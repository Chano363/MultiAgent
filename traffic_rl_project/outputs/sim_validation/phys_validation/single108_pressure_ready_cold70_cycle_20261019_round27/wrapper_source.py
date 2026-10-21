"""Run the native diagnostic under an explicit experimental numerical solver."""
import argparse
import hashlib
import json
import logging
import re
from pathlib import Path
import runpy
import sys
import weakref

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from src.environments.train_fleet_env import TrainFleetEnv
from src.evaluation.adaptive_newmark_candidate import coupled_candidate
from src.evaluation.fractional_air_timing import fractional_air_timing, fractional_advance_source
from src.evaluation.refine_pneumatic_interval import refined_pneumatic_interval


def relocate_forecast_archive(controller_text, target):
    """Change only the frozen diagnostic output location, never its policy."""
    expression = r"(?m)^            directory = _PredictionPath\('[^']+/release_predictions'\)"
    redirected, replacements = re.subn(expression,
        lambda _: "            directory = _PredictionPath(" + repr(
            (target / 'release_predictions').as_posix()) + ")", controller_text)
    if replacements != 1:
        raise ValueError('Expected exactly one frozen forecast archive directory')
    return redirected


def main():
    logging.basicConfig(level=logging.INFO)
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--steps', type=int, default=36000)
    parser.add_argument('--controller-source', type=Path, required=True)
    parser.add_argument('--solver', choices=['balanced', 'newton_analytic'], default='balanced')
    parser.add_argument('--force-tolerance-n', type=float, default=10)
    parser.add_argument('--air-step', type=float)
    parser.add_argument('--fractional-air-timing', action='store_true')
    parser.add_argument('--ramp-air-force', action='store_true')
    args = parser.parse_args()
    if args.ramp_air_force and not args.fractional_air_timing:
        parser.error('Force interpolation requires fractional air timing')
    if not np.isfinite(args.force_tolerance_n) or args.force_tolerance_n <= 0:
        parser.error('Positive finite force tolerance required')
    if args.air_step is not None and (not np.isfinite(args.air_step) or not 0 < args.air_step <= .01):
        parser.error('Air step must lie in (0, .01]')
    args.output.mkdir(parents=True, exist_ok=False)
    source = Path('src/evaluation/adaptive_newmark_candidate.py').read_bytes()
    (args.output / 'candidate_source.py').write_bytes(source)
    (args.output / 'wrapper_source.py').write_bytes(Path(__file__).read_bytes())
    frozen_sources = {}
    for name in ('newton_mechanics_candidate', 'native_force_tangent',
                 'fractional_air_timing', 'refine_pneumatic_interval'):
        payload = Path('src/evaluation', name + '.py').read_bytes()
        (args.output / (name + '_source.py')).write_bytes(payload)
        frozen_sources[name] = hashlib.sha256(payload).hexdigest()
    (args.output / 'fractional_advance_source.py').write_text(fractional_advance_source(), encoding='utf-8')
    # The existing archive entry creates a fresh output directory itself.
    # Keep wrapper provenance at this parent and native data in run/.
    target = args.output / 'run'
    controller_text = args.controller_source.read_text(encoding='utf-8')
    redirected = relocate_forecast_archive(controller_text, target)
    relocated = args.output / 'controller_source.py'
    relocated.write_text(redirected, encoding='utf-8')
    live = weakref.WeakSet()
    original_reset = TrainFleetEnv.reset

    def reset(self, *a, **kw):
        value = original_reset(self, *a, **kw)
        for train in self.trains:
            live.add(train.dynamics)
        return value

    argv = sys.argv
    samples = []
    status, error = 'completed', None
    TrainFleetEnv.reset = reset
    try:
        sys.argv = ['diagnose_low_level_control.py', '--output', str(target),
            '--config', 'configs/experiments/single_10kt108_coupler_rulecal.yaml',
            '--controller-source', str(relocated), '--steps', str(args.steps),
            '--speed', '70', '--trains', '1', '--profile', 'shuozhou_ningwuxi_beidaniu_49km',
            '--finish-m', '49600', '--stop-on-coupler-kn', '1000',
            '--stop-on-infeasible-release', '--save-native-release-state',
            '--stop-file', str(args.output / 'STOP')]
        with fractional_air_timing(args.fractional_air_timing), refined_pneumatic_interval(
                args.air_step, hold_coarse_grade=args.air_step is not None), coupled_candidate(
                samples, live_dynamics=live, max_step=0.000625,
                force_tol_n=args.force_tolerance_n, numerical_solver=args.solver,
                ramp_air_force=args.ramp_air_force):
            runpy.run_path('src/evaluation/diagnose_low_level_control.py', run_name='__main__')
    except BaseException as exc:
        status, error = 'failed', repr(exc)
        raise
    finally:
        sys.argv = argv
        TrainFleetEnv.reset = original_reset
        numerical = {}
        for label in ('live', 'forecast'):
            chosen = [s for s in samples if bool(s.get('live')) == (label == 'live')]
            numerical[label] = {
                'mechanical_intervals': len(chosen),
                'accepted_microsteps': sum(s['accepted'] for s in chosen),
                'rejected_trials': sum(s['rejected'] for s in chosen),
                'internal_peak_kn': max((s['peak_interface_n'] for s in chosen), default=0) / 1000,
                'max_force_residual_n': max((s['max_force_residual_n'] for s in chosen), default=0)}
        result = {'status': status, 'error': error, 'numerical': numerical,
            'experimental_numerical_solver': True, 'production_default_changed': False,
            'solver_sha256': hashlib.sha256(source).hexdigest(),
            'frozen_sources_sha256': frozen_sources,
            'original_controller_sha256': hashlib.sha256(controller_text.encode()).hexdigest(),
            'controller_change': 'forecast archive directory relocation only',
            'settings': {'max_step_s': 0.000625, 'force_tolerance_n': args.force_tolerance_n,
                         'solver': args.solver, 'air_step_s': args.air_step or .01,
                         'fractional_air_timing': args.fractional_air_timing,
                         'ramp_air_force': args.ramp_air_force,
                         'displacement_tolerance_m': 1e-9, 'max_iter': 100},
            'numpy_version': np.__version__}
        (args.output / 'solver_result.json').write_text(json.dumps(result, indent=2), encoding='utf-8')
        native = target / 'result.json'
        if native.exists():
            archived = json.loads(native.read_text(encoding='utf-8'))
            archived['metadata']['experimental_numerical_solver'] = result
            archived['metadata']['purpose'] += '; experimental solver; not native production numerics'
            native.write_text(json.dumps(archived, indent=2), encoding='utf-8')
        state_manifest = target / 'native_release_state.json'
        if state_manifest.exists():
            manifest = json.loads(state_manifest.read_text(encoding='utf-8'))
            manifest['experimental_numerical_solver'] = result
            state_manifest.write_text(json.dumps(manifest, indent=2), encoding='utf-8')
        print(json.dumps(result), flush=True)


if __name__ == '__main__':
    main()
