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

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from src.evaluation.solver_registry import (
    PRODUCTION_SOLVER, SOLVERS, active_solver_label, assert_active_solver,
    solver_context)
from src.environments.train_fleet_env import TrainFleetEnv


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--steps', type=int, default=70)
    parser.add_argument('--solver', choices=SOLVERS, default=PRODUCTION_SOLVER,
                        help='production_newmark = unmodified production path')
    parser.add_argument('--error-scale', type=float, default=1.)
    parser.add_argument('--save-fleet-state', action='store_true')
    parser.add_argument('--release-budget-guard', action='store_true')
    args = parser.parse_args()
    if args.steps < 3:
        parser.error('At least three control steps required')
    if not math.isfinite(args.error_scale) or args.error_scale <= 0:
        parser.error('Positive finite error scale required')
    args.output.mkdir(parents=True, exist_ok=False)
    experimental = args.solver == 'newton_analytic_time_error'
    settings = None
    if experimental:
        settings = dict(max_step=.0025, min_step=.0000001, force_atol_n=1000.,
                        velocity_atol=1e-5, position_atol=1e-6,
                        tol=1e-9, max_iter=100, force_tol_n=.01)
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
        sys.argv = ['diagnose_low_level_control.py', '--config',
                    'configs/experiments/formation_ed_ab_3train_1plus108.yaml',
                    '--trains', '3', '--speed', '70', '--profile',
                    'shuozhou_ningwuxi_beidaniu_49km', '--steps', str(args.steps),
                    '--stop-on-coupler-kn', '1000', '--output', str(args.output/'run')]
        guard = nullcontext()
        if args.release_budget_guard:
            from src.evaluation.release_budget_guard import candidate as release_candidate
            guard = release_candidate()
        with solver_context(args.solver, samples, **(settings or {})), guard:
            assert_active_solver(args.solver)
            active_label = active_solver_label()
            runpy.run_path('src/evaluation/diagnose_low_level_control.py', run_name='__main__')
    except BaseException as exc:
        status, error = 'failed', repr(exc)
        raise
    finally:
        sys.argv = argv
        TrainFleetEnv.close = original_close
        summary = dict(status=status, error=error, settings=settings,
                       solver=args.solver, source_sha256=hashes, elapsed_wall_s=time.perf_counter()-started,
                       experimental=experimental, production_default_changed=False,
                       release_budget_guard=args.release_budget_guard,
                       accepted_microsteps=sum(s['accepted'] for s in samples),
                       newton_calls=sum(s.get('newton_calls', 0) for s in samples),
                       rejected_trials=sum(s['rejected'] for s in samples),
                       internal_peak_kn=max((s['peak_interface_n'] for s in samples), default=0)/1000,
                       max_force_residual_n=max((s['max_force_residual_n'] for s in samples), default=0),
                       statistics_scope='Completed native mechanical intervals only; failed interval trials excluded',
                       scope='Local engineering error indicators; not route acceptance')
        (args.output/'numerical_summary.json').write_text(json.dumps(summary, indent=2), encoding='utf-8')
        (args.output/'intervals.json').write_text(json.dumps(samples), encoding='utf-8')
        result_file = args.output/'run/result.json'
        if result_file.exists():
            result = json.loads(result_file.read_text(encoding='utf-8'))
            result['metadata']['experimental_time_error_control'] = summary
            result['metadata']['solver'] = active_label
            result_file.write_text(json.dumps(result, indent=2), encoding='utf-8')
        print(json.dumps(summary), flush=True)


if __name__ == '__main__':
    main()
