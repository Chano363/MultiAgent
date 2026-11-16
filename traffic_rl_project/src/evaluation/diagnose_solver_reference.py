"""Numerical reference sequence: fixed recorded inputs, refined mechanical step.

This is a convergence study, not a controller or route acceptance run. The
production controller is executed once; its recorded force/grade inputs are
then replayed with the same production Newmark formula at h, h/2, h/4, ...
"""
import argparse
import json
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from src.evaluation.newmark_observer import observe_newmark, replay_fixed_mechanics
from src.environments.train_fleet_env import TrainFleetEnv


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--steps', type=int, default=100)
    parser.add_argument('--subdivisions', default='1,2,4,8')
    parser.add_argument('--config', default='configs/experiments/formation_ed_ab_3train_1plus108.yaml')
    parser.add_argument('--trains', type=int, default=1)
    parser.add_argument('--speed', type=float, default=70)
    parser.add_argument('--profile', default='shuozhou_ningwuxi_beidaniu_49km')
    args = parser.parse_args()
    subdivisions = tuple(int(v) for v in args.subdivisions.split(',') if v)
    if args.steps < 3 or not subdivisions or min(subdivisions) < 1:
        parser.error('At least three steps and positive subdivisions required')
    args.output.mkdir(parents=True, exist_ok=False)

    capture = {}
    samples = []
    argv = sys.argv
    try:
        sys.argv = ['diagnose_low_level_control.py', '--config', args.config,
                    '--trains', str(args.trains), '--speed', str(args.speed),
                    '--profile', args.profile, '--steps', str(args.steps),
                    '--output', str(args.output/'run')]
        with observe_newmark(samples, capture=capture):
            import runpy
            runpy.run_path('src/evaluation/diagnose_low_level_control.py', run_name='__main__')
    finally:
        sys.argv = argv

    results = replay_fixed_mechanics(capture, subdivisions=subdivisions,
                                     tol=1e-5, max_iter=30)
    summary = []
    for row in results:
        summary.append(dict(
            subdivision=row['subdivision'],
            step_s=float(capture['dt'][0] / row['subdivision']),
            substeps=row['substeps'],
            unconverged_substeps=row['unconverged_substeps'],
            max_residual_m=row['max_residual_m'],
            peak_kn=row['peak_kn'],
            native_replay_exact=row['native_replay_exact']))
    summary[-1]['role'] = 'reference_candidate'
    for row in summary:
        row['deviation_from_finest_pct'] = (
            (row['peak_kn'] - summary[-1]['peak_kn']) / summary[-1]['peak_kn'] * 100.0)
    (args.output/'convergence.json').write_text(
        json.dumps(dict(recorded_control_steps=len(capture['dt']),
                        control_dt_s=float(capture['dt'][0]),
                        subdivisions=list(subdivisions),
                        sequence=summary), indent=2), encoding='utf-8')
    print(json.dumps(summary, indent=2), flush=True)


if __name__ == '__main__':
    main()
