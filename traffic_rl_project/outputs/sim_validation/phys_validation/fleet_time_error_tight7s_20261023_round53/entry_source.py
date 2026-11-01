"""Short zero-RL fleet experiment with local time-error indicators."""
import argparse
import hashlib
import json
from pathlib import Path
import runpy
import sys
import time
import math

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from src.evaluation.error_controlled_mechanics import candidate


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--steps', type=int, default=70)
    parser.add_argument('--error-scale', type=float, default=1.)
    args = parser.parse_args()
    if args.steps < 3:
        parser.error('At least three control steps required')
    if not math.isfinite(args.error_scale) or args.error_scale <= 0:
        parser.error('Positive finite error scale required')
    args.output.mkdir(parents=True, exist_ok=False)
    settings = dict(max_step=.0025, min_step=.0000001, force_atol_n=1000.,
                    velocity_atol=1e-5, position_atol=1e-6,
                    tol=1e-9, max_iter=100, force_tol_n=.01)
    for key in ('force_atol_n', 'velocity_atol', 'position_atol'):
        settings[key] *= args.error_scale
    hashes = {}
    for name in ('error_controlled_mechanics', 'adaptive_newmark_candidate',
                 'newton_mechanics_candidate', 'native_force_tangent'):
        raw = Path('src/evaluation', name+'.py').read_bytes()
        (args.output/(name+'_source.py')).write_bytes(raw)
        hashes[name] = hashlib.sha256(raw).hexdigest()
    (args.output/'entry_source.py').write_bytes(Path(__file__).read_bytes())
    samples, argv = [], sys.argv
    started, status, error = time.perf_counter(), 'completed', None
    try:
        sys.argv = ['diagnose_low_level_control.py', '--config',
                    'configs/experiments/formation_ed_ab_3train_1plus108.yaml',
                    '--trains', '3', '--speed', '70', '--profile',
                    'shuozhou_ningwuxi_beidaniu_49km', '--steps', str(args.steps),
                    '--stop-on-coupler-kn', '1000', '--output', str(args.output/'run')]
        with candidate(samples, **settings):
            runpy.run_path('src/evaluation/diagnose_low_level_control.py', run_name='__main__')
    except BaseException as exc:
        status, error = 'failed', repr(exc)
        raise
    finally:
        sys.argv = argv
        summary = dict(status=status, error=error, settings=settings,
                       source_sha256=hashes, elapsed_wall_s=time.perf_counter()-started,
                       experimental=True, production_default_changed=False,
                       accepted_microsteps=sum(s['accepted'] for s in samples),
                       newton_calls=sum(s['newton_calls'] for s in samples),
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
            result_file.write_text(json.dumps(result, indent=2), encoding='utf-8')
        print(json.dumps(summary), flush=True)


if __name__ == '__main__':
    main()
