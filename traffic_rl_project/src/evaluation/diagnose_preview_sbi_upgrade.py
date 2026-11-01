"""Native diagnostic for response-preview upgrades, preserving exact resumes."""
import argparse
import hashlib
from pathlib import Path
import runpy
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from src.evaluation import fleet_checkpoint
from src.evaluation.forecast_preview_sbi_upgrade import arm


def main():
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument('--arm-preview', action='store_true')
    options, remaining = parser.parse_known_args()
    original, argv = fleet_checkpoint.load_fleet_checkpoint, sys.argv

    def load(directory):
        env, manifest = original(directory)
        if options.arm_preview:
            env, manifest = arm(env, manifest)
        elif 'preview_sbi_upgrade' not in manifest['numerical']['source_sha256']:
            raise ValueError('No recorded preview trial to continue')
        manifest['numerical']['source_sha256']['diagnose_preview_sbi_upgrade'] = hashlib.sha256(
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
