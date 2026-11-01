"""Native bounded handoff repair from a safe full checkpoint, not failed state."""
import argparse
import hashlib
from pathlib import Path
import runpy
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from src.evaluation import fleet_checkpoint
from src.evaluation.forecast_pre_release_chase_exit import arm


def main():
    p = argparse.ArgumentParser(add_help=False)
    p.add_argument('--arm-chase-exit', action='store_true')
    options, remaining = p.parse_known_args()
    original, argv = fleet_checkpoint.load_fleet_checkpoint, sys.argv

    def load(directory):
        env, manifest = original(directory)
        if options.arm_chase_exit:
            env, manifest = arm(env, manifest)
        elif 'pre_release_chase_exit' not in manifest['numerical']['source_sha256']:
            raise ValueError('No recorded chase-exit trial in checkpoint')
        manifest['numerical']['source_sha256']['diagnose_pre_release_chase_exit'] = hashlib.sha256(
            Path(__file__).read_bytes()).hexdigest()
        return env, manifest

    fleet_checkpoint.load_fleet_checkpoint = load
    sys.argv = ['diagnose_release_feasibility.py', *remaining]
    try:
        runpy.run_path('src/evaluation/diagnose_release_feasibility.py', run_name='__main__')
    finally:
        fleet_checkpoint.load_fleet_checkpoint, sys.argv = original, argv


if __name__ == '__main__':
    main()
