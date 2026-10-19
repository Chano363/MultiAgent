"""Run the native diagnostic under an explicit experimental numerical solver."""
import argparse
import hashlib
import json
import logging
from pathlib import Path
import runpy
import sys
import weakref

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from src.environments.train_fleet_env import TrainFleetEnv
from src.evaluation.adaptive_newmark_candidate import coupled_candidate


def main():
    logging.basicConfig(level=logging.INFO)
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--steps', type=int, default=36000)
    parser.add_argument('--controller-source', type=Path, required=True)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=False)
    source = Path('src/evaluation/adaptive_newmark_candidate.py').read_bytes()
    (args.output / 'candidate_source.py').write_bytes(source)
    (args.output / 'wrapper_source.py').write_bytes(Path(__file__).read_bytes())
    # The existing archive entry creates a fresh output directory itself.
    # Keep wrapper provenance at this parent and native data in run/.
    target = args.output / 'run'
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
            '--controller-source', str(args.controller_source), '--steps', str(args.steps),
            '--speed', '70', '--trains', '1', '--profile', 'shuozhou_ningwuxi_beidaniu_49km',
            '--finish-m', '49600', '--stop-on-coupler-kn', '1000',
            '--stop-on-infeasible-release', '--stop-file', str(args.output / 'STOP')]
        with coupled_candidate(samples, live_dynamics=live, max_step=0.000625,
                               force_tol_n=10):
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
            'settings': {'max_step_s': 0.000625, 'force_tolerance_n': 10,
                         'displacement_tolerance_m': 1e-9, 'max_iter': 100},
            'numpy_version': np.__version__}
        (args.output / 'solver_result.json').write_text(json.dumps(result, indent=2), encoding='utf-8')
        native = target / 'result.json'
        if native.exists():
            archived = json.loads(native.read_text(encoding='utf-8'))
            archived['metadata']['experimental_numerical_solver'] = result
            archived['metadata']['purpose'] += '; experimental balanced solver; not native production numerics'
            native.write_text(json.dumps(archived, indent=2), encoding='utf-8')
        print(json.dumps(result), flush=True)


if __name__ == '__main__':
    main()
