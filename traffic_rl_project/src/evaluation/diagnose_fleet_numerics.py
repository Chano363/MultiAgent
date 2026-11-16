"""Isolated three-train mechanical convergence study; production is unchanged.

The default solver is production Newmark. Replacement solvers stay available
as explicit, labelled experimental options and are never installed silently.
"""
import argparse
import hashlib
import json
from pathlib import Path
import runpy
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from src.evaluation.solver_registry import (
    PRODUCTION_SOLVER, SOLVERS, active_solver_label, assert_active_solver,
    solver_context)
from src.environments.train_fleet_env import TrainFleetEnv


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--steps', type=int, default=20)
    parser.add_argument('--max-step', type=float, default=.01,
                        help='Experimental mechanical step; ignored by production')
    parser.add_argument('--solver', choices=SOLVERS, default=PRODUCTION_SOLVER,
                        help='production_newmark = unmodified production path')
    parser.add_argument('--config', default='configs/experiments/formation_ed_ab_3train_1plus108.yaml')
    parser.add_argument('--trains', type=int, default=2)
    parser.add_argument('--speed', type=float, default=70)
    parser.add_argument('--finish-m', type=float)
    parser.add_argument('--save-fleet-state', action='store_true')
    args = parser.parse_args()
    if args.steps < 3 or not 0 < args.max_step <= .01:
        parser.error('At least three steps and a positive mechanical step <= .01 required')
    args.output.mkdir(parents=True, exist_ok=False)
    settings = (None if args.solver == PRODUCTION_SOLVER else
                dict(max_step=args.max_step, force_tol_n=.01, tol=1e-9, max_iter=100))
    frozen = {}
    if settings is not None:
        for name in ('adaptive_newmark_candidate', 'newton_mechanics_candidate',
                     'native_force_tangent'):
            raw = Path('src/evaluation', name+'.py').read_bytes()
            (args.output/(name+'_source.py')).write_bytes(raw)
            frozen[name] = hashlib.sha256(raw).hexdigest()
    (args.output/'wrapper_source.py').write_bytes(Path(__file__).read_bytes())
    argv = sys.argv
    samples = []
    status, error, active_label = 'completed', None, args.solver
    original_close = TrainFleetEnv.close

    def close_with_checkpoint(env):
        from src.evaluation.fleet_checkpoint import save_fleet_checkpoint
        save_fleet_checkpoint(env, args.output/'run', dict(
            solver=args.solver, settings=settings, source_sha256=frozen))
        return original_close(env)

    if args.save_fleet_state:
        TrainFleetEnv.close = close_with_checkpoint
    try:
        sys.argv = ['diagnose_low_level_control.py', '--config', args.config,
            '--trains', str(args.trains), '--speed', str(args.speed),
            '--profile', 'shuozhou_ningwuxi_beidaniu_49km',
            '--steps', str(args.steps), '--stop-on-coupler-kn', '1000',
            '--output', str(args.output/'run')]
        if args.finish_m is not None:
            sys.argv += ['--finish-m', str(args.finish_m)]
        # No air-law change, interpolation or different controller. The native
        # outer pneumatic and control clocks remain intact.
        with solver_context(args.solver, samples, **(settings or {})):
            assert_active_solver(args.solver)
            active_label = active_solver_label()
            runpy.run_path('src/evaluation/diagnose_low_level_control.py', run_name='__main__')
    except BaseException as exc:
        status, error = 'failed', repr(exc)
        raise
    finally:
        sys.argv = argv
        TrainFleetEnv.close = original_close
        numerical = dict(status=status, error=error, settings=settings,
            solver=args.solver, experimental=args.solver != PRODUCTION_SOLVER,
            production_default_changed=False, frozen_source_sha256=frozen,
            intervals=len(samples), accepted_microsteps=sum(s['accepted'] for s in samples),
            rejected_trials=sum(s['rejected'] for s in samples),
            internal_peak_kn=max((s['peak_interface_n'] for s in samples), default=0)/1000,
            max_force_residual_n=max((s['max_force_residual_n'] for s in samples), default=0),
            scope='Short cold-start numerical study; not fleet route acceptance')
        (args.output/'numerical_summary.json').write_text(json.dumps(numerical, indent=2))
        result_path = args.output/'run/result.json'
        if result_path.exists():
            result = json.loads(result_path.read_text(encoding='utf-8'))
            result['metadata']['experimental_mechanical_solver'] = numerical
            result['metadata']['solver'] = active_label
            result_path.write_text(json.dumps(result, indent=2), encoding='utf-8')
        print(json.dumps(numerical), flush=True)


if __name__ == '__main__':
    main()
