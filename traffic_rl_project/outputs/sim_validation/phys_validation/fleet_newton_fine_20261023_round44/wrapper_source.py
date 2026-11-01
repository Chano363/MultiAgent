"""Isolated three-train mechanical convergence study; production is unchanged."""
import argparse
import hashlib
import json
from pathlib import Path
import runpy
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from src.evaluation.adaptive_newmark_candidate import coupled_candidate


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--steps', type=int, default=20)
    parser.add_argument('--max-step', type=float, required=True)
    args = parser.parse_args()
    if args.steps < 3 or not 0 < args.max_step <= .01:
        parser.error('At least three steps and a positive mechanical step <= .01 required')
    args.output.mkdir(parents=True, exist_ok=False)
    frozen = {}
    for name in ('adaptive_newmark_candidate', 'newton_mechanics_candidate', 'native_force_tangent'):
        raw = Path('src/evaluation', name+'.py').read_bytes()
        (args.output/(name+'_source.py')).write_bytes(raw)
        frozen[name] = hashlib.sha256(raw).hexdigest()
    (args.output/'wrapper_source.py').write_bytes(Path(__file__).read_bytes())
    argv = sys.argv
    samples = []
    status, error = 'completed', None
    settings = dict(max_step=args.max_step, force_tol_n=.01, tol=1e-9, max_iter=100)
    try:
        sys.argv = ['diagnose_low_level_control.py', '--config',
            'configs/experiments/formation_ed_ab_3train_1plus108.yaml', '--trains', '3',
            '--speed', '70', '--profile', 'shuozhou_ningwuxi_beidaniu_49km',
            '--steps', str(args.steps), '--stop-on-coupler-kn', '1000',
            '--output', str(args.output/'run')]
        # No air-law change, interpolation or different controller. The native
        # outer pneumatic and control clocks remain intact.
        with coupled_candidate(samples, numerical_solver='newton_analytic', **settings):
            runpy.run_path('src/evaluation/diagnose_low_level_control.py', run_name='__main__')
    except BaseException as exc:
        status, error = 'failed', repr(exc)
        raise
    finally:
        sys.argv = argv
        numerical = dict(status=status, error=error, settings=settings,
            numerical_solver='newton_analytic', experimental=True,
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
            result_path.write_text(json.dumps(result, indent=2), encoding='utf-8')
        print(json.dumps(numerical), flush=True)


if __name__ == '__main__':
    main()
