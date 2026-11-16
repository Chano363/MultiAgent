"""Short zero-RL fleet experiment with labelled local time-error indicators.

The default solver is production Newmark. The error-controlled analytic Newton
solver remains available only through an explicit ``--solver`` opt-in.
"""
import argparse
import hashlib
import json
from pathlib import Path
import runpy
import sys
import time
import math
from contextlib import nullcontext

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from src.evaluation.solver_registry import (
    PRODUCTION_SOLVER, SOLVERS, active_solver_label, assert_active_solver,
    solver_context)
from src.environments.train_fleet_env import TrainFleetEnv

# Ladder variants used to attribute the coupler-peak overestimate one change
# at a time. Every row keeps the same controller and cold start.
VARIANTS = {
    'production': (PRODUCTION_SOLVER, {}),
    'fine': ('native_newmark_fine', dict(max_step=.0025, tol=1e-5, max_iter=30)),
    'picard_force': ('newmark_picard_force', dict(force_tol_n=.01, max_iter=100)),
    'newton_displacement': ('newmark_newton_displacement', dict(tol=1e-5, max_iter=30)),
    'error_controlled': ('newton_analytic_time_error', dict(
        max_step=.0025, min_step=.0000001, force_atol_n=1000.,
        velocity_atol=1e-5, position_atol=1e-6,
        tol=1e-9, max_iter=100, force_tol_n=.01)),
}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--steps', type=int, default=70)
    parser.add_argument('--config', default='configs/experiments/formation_ed_ab_3train_1plus108.yaml')
    parser.add_argument('--trains', type=int, default=3)
    parser.add_argument('--speed', type=float, default=70)
    parser.add_argument('--finish-m', type=float)
    parser.add_argument('--start-m', type=float, default=0.0,
                        help='Shift the whole formation forward along the route '
                             '(ADR-049: keep follower heads inside ETCS coverage)')
    parser.add_argument('--gap-offset-m', type=float, default=0.0,
                        help='Additional initial gap per adjacent train pair (ADR-049 addendum)')
    parser.add_argument('--stop-on-coupler-kn', type=float, default=1000.0,
                        help='Diagnostic early-stop threshold; 0 disables the stop '
                             'to observe the full-route peak')
    parser.add_argument('--profile', default='shuozhou_ningwuxi_beidaniu_49km')
    parser.add_argument('--variant', choices=sorted(VARIANTS),
                        help='Ladder variant; overrides --solver and settings')
    parser.add_argument('--solver', choices=SOLVERS, default=None,
                        help='production_newmark = unmodified production path')
    parser.add_argument('--error-scale', type=float, default=1.)
    parser.add_argument('--save-fleet-state', action='store_true')
    parser.add_argument('--release-budget-guard', action='store_true')
    parser.add_argument('--override', action='append', default=[], metavar='KEY=VALUE',
                        help='Env-config override forwarded to the diagnostic entry')
    args = parser.parse_args()
    if args.steps < 3:
        parser.error('At least three control steps required')
    if not math.isfinite(args.error_scale) or args.error_scale <= 0:
        parser.error('Positive finite error scale required')
    if args.variant:
        args.solver, settings = VARIANTS[args.variant]
        settings = dict(settings)
    else:
        if args.solver is None:
            args.solver = PRODUCTION_SOLVER
        settings = (dict(max_step=.0025, min_step=.0000001, force_atol_n=1000.,
                         velocity_atol=1e-5, position_atol=1e-6,
                         tol=1e-9, max_iter=100, force_tol_n=.01)
                    if args.solver == 'newton_analytic_time_error' else {})
    experimental = args.solver != PRODUCTION_SOLVER
    args.output.mkdir(parents=True, exist_ok=False)
    if experimental and args.solver == 'newton_analytic_time_error':
        for key in ('force_atol_n', 'velocity_atol', 'position_atol'):
            settings[key] *= args.error_scale
    hashes = {}
    if experimental:
        for name in ('error_controlled_mechanics', 'adaptive_newmark_candidate',
                     'newton_mechanics_candidate', 'native_force_tangent'):
            raw = Path('src/evaluation', name+'.py').read_bytes()
            (args.output/(name+'_source.py')).write_bytes(raw)
            hashes[name] = hashlib.sha256(raw).hexdigest()
    if args.release_budget_guard:
        for name in ('release_budget_guard', 'release_low_speed_controller'):
            raw = Path('src/evaluation', name+'.py').read_bytes()
            (args.output/(name+'_source.py')).write_bytes(raw)
            hashes[name] = hashlib.sha256(raw).hexdigest()
    (args.output/'entry_source.py').write_bytes(Path(__file__).read_bytes())
    samples, argv = [], sys.argv
    active_label = args.solver
    original_close = TrainFleetEnv.close
    def close_with_checkpoint(env):
        from src.evaluation.fleet_checkpoint import save_fleet_checkpoint
        save_fleet_checkpoint(env, args.output/'run', dict(
            solver=args.solver, settings=settings, source_sha256=hashes))
        return original_close(env)
    if args.save_fleet_state:
        TrainFleetEnv.close = close_with_checkpoint
    started, status, error = time.perf_counter(), 'completed', None
    try:
        sys.argv = ['diagnose_low_level_control.py', '--config', args.config,
                    '--trains', str(args.trains), '--speed', str(args.speed),
                    '--profile', args.profile, '--steps', str(args.steps),
                    '--output', str(args.output/'run')]
        if args.stop_on_coupler_kn:
            sys.argv += ['--stop-on-coupler-kn', str(args.stop_on_coupler_kn)]
        if args.finish_m is not None:
            sys.argv += ['--finish-m', str(args.finish_m)]
        if args.start_m:
            sys.argv += ['--start-m', str(args.start_m)]
        if args.gap_offset_m:
            sys.argv += ['--gap-offset-m', str(args.gap_offset_m)]
        for item in args.override:
            sys.argv += ['--override', item]
        guard = nullcontext()
        if args.release_budget_guard:
            from src.evaluation.release_budget_guard import candidate as release_candidate
            guard = release_candidate()
        observe = nullcontext()
        if args.solver == PRODUCTION_SOLVER:
            # Read-only residual observation of the unmodified production step.
            from src.evaluation.newmark_observer import observe_newmark
            observe = observe_newmark(samples)
        with solver_context(args.solver, samples, **(settings or {})), guard, observe:
            assert_active_solver(args.solver)
            active_label = active_solver_label()
            runpy.run_path('src/evaluation/diagnose_low_level_control.py', run_name='__main__')
    except BaseException as exc:
        status, error = 'failed', repr(exc)
        raise
    finally:
        sys.argv = argv
        TrainFleetEnv.close = original_close
        dict_samples = [s for s in samples if isinstance(s, dict)]
        observed = np.asarray([s for s in samples if not isinstance(s, dict)],
                              dtype=float)
        summary = dict(status=status, error=error, settings=settings or None,
                       solver=args.solver, source_sha256=hashes,
                       elapsed_wall_s=time.perf_counter()-started,
                       experimental=experimental, production_default_changed=False,
                       release_budget_guard=args.release_budget_guard,
                       accepted_microsteps=sum(s.get('accepted', 0) for s in dict_samples),
                       newton_calls=sum(s.get('newton_calls', 0) for s in dict_samples),
                       rejected_trials=sum(s.get('rejected', 0) for s in dict_samples),
                       internal_peak_kn=max(
                           (s.get('peak_interface_n', 0) for s in dict_samples), default=0)/1000,
                       max_force_residual_n=max(
                           (s.get('max_force_residual_n', 0) for s in dict_samples), default=0),
                       statistics_scope='Completed native mechanical intervals only; failed interval trials excluded',
                       scope='Local engineering error indicators; not route acceptance')
        if observed.size:
            summary.update(mechanical_substeps=int(len(observed)),
                           unconverged_substeps=int(np.sum(observed[:, 5] == 0)),
                           max_displacement_residual_m=float(observed[:, 3].max()),
                           mean_iterations=float(observed[:, 2].mean()))
        elif dict_samples:
            accepted = sum(s.get('accepted', 0) for s in dict_samples)
            if accepted:
                # Error-controlled intervals accept two half steps each.
                summary.update(
                    mechanical_substeps=int(accepted),
                    unconverged_substeps=int(sum(s.get('rejected', 0) for s in dict_samples)),
                    mean_force_residual_n=float(np.mean(
                        [s.get('max_force_residual_n', 0) for s in dict_samples])))
            else:
                summary.update(
                    mechanical_substeps=int(sum(s.get('substeps', 1) for s in dict_samples)),
                    unconverged_substeps=int(sum(
                        s.get('substeps', 1) for s in dict_samples if not s.get('converged', True))),
                    mean_iterations=float(np.mean([s.get('iterations', 0) for s in dict_samples])),
                    mean_force_residual_n=float(np.mean(
                        [s.get('force_residual_n', 0) for s in dict_samples])))
        (args.output/'numerical_summary.json').write_text(json.dumps(summary, indent=2), encoding='utf-8')
        (args.output/'intervals.json').write_text(json.dumps(samples), encoding='utf-8')
        result_file = args.output/'run/result.json'
        if result_file.exists():
            result = json.loads(result_file.read_text(encoding='utf-8'))
            control_steps = result['summary'].get('steps')
            summary['control_steps'] = control_steps
            if control_steps:
                summary['wall_per_control_step_s'] = summary['elapsed_wall_s'] / control_steps
                summary['accepted_half_steps_per_control_step'] = (
                    summary['accepted_microsteps'] / control_steps)
                summary['newton_calls_per_control_step'] = (
                    summary['newton_calls'] / control_steps)
                summary['rejected_trials_per_control_step'] = (
                    summary['rejected_trials'] / control_steps)
            (args.output/'numerical_summary.json').write_text(
                json.dumps(summary, indent=2), encoding='utf-8')
            result['metadata']['experimental_time_error_control'] = summary
            result['metadata']['solver'] = active_label
            result_file.write_text(json.dumps(result, indent=2), encoding='utf-8')
        print(json.dumps(summary), flush=True)


if __name__ == '__main__':
    main()
