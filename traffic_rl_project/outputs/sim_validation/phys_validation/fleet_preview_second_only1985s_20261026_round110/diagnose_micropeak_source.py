"""Same-state trace and optional maximum mechanical step refinement."""
import argparse
import copy
import hashlib
import logging
from pathlib import Path
import runpy
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from src.evaluation import fleet_checkpoint
from src.evaluation.micropeak_observer import observe


def main():
    logging.basicConfig(level=logging.INFO)
    p = argparse.ArgumentParser()
    p.add_argument('--state-dir', type=Path, required=True)
    p.add_argument('--output', type=Path, required=True)
    p.add_argument('--steps', type=int, required=True)
    p.add_argument('--step-factor', type=float, default=1.)
    args = p.parse_args()
    if args.step_factor not in (1., .5, .25):
        p.error('Only original, half and quarter maximum step supported')
    original, argv, live_ids = fleet_checkpoint.load_fleet_checkpoint, sys.argv, {}

    def load(directory):
        env, manifest = original(directory)
        live_ids.update({id(t.dynamics): i+1 for i, t in enumerate(env.trains)})
        manifest = copy.deepcopy(manifest)
        settings = manifest['numerical']['settings']
        previous = settings['max_step']
        settings['max_step'] *= args.step_factor
        manifest['micropeak_diagnostic'] = dict(previous_max_step_s=previous,
            trial_max_step_s=settings['max_step'], trace_only=args.step_factor == 1.)
        for name in ('micropeak_observer', 'diagnose_micropeak'):
            manifest['numerical']['source_sha256'][name] = hashlib.sha256(
                Path('src/evaluation', name+'.py').read_bytes()).hexdigest()
        return env, manifest

    fleet_checkpoint.load_fleet_checkpoint = load
    try:
        sys.argv = ['continue_fleet_numerics.py', '--state-dir', str(args.state_dir),
                    '--output', str(args.output), '--steps', str(args.steps)]
        with observe(args.output, live_ids):
            runpy.run_path('src/evaluation/continue_fleet_numerics.py', run_name='__main__')
    finally:
        fleet_checkpoint.load_fleet_checkpoint, sys.argv = original, argv
        if args.output.exists():
            for name in ('micropeak_observer', 'diagnose_micropeak'):
                (args.output/(name+'_source.py')).write_bytes(
                    Path('src/evaluation', name+'.py').read_bytes())


if __name__ == '__main__':
    main()
