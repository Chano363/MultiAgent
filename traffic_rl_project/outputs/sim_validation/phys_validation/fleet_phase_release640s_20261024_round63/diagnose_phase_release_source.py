"""Single-factor release-phase trial from a trusted full-fleet state."""
import argparse
import copy
import hashlib
from pathlib import Path
import runpy
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from src.evaluation import fleet_checkpoint


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--state-dir', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--steps', type=int, required=True)
    args = parser.parse_args()
    original, argv = fleet_checkpoint.load_fleet_checkpoint, sys.argv
    def load_with_phase(directory):
        env, manifest = original(directory)
        manifest = copy.deepcopy(manifest)
        for controller in env.multi_loco_controllers:
            controller._phase_release_floor_enabled = True
        manifest['experimental_release_phase_override'] = dict(
            enabled=True, scope='Clamp positive chase release offset only while AB source is on; zero RL')
        for name in ('phase_aware_release', 'diagnose_phase_release'):
            manifest['numerical']['source_sha256'][name] = hashlib.sha256(
                Path('src/evaluation', name+'.py').read_bytes()).hexdigest()
        return env, manifest
    fleet_checkpoint.load_fleet_checkpoint = load_with_phase
    try:
        sys.argv = ['continue_fleet_numerics.py', '--state-dir', str(args.state_dir),
                    '--output', str(args.output), '--steps', str(args.steps)]
        runpy.run_path('src/evaluation/continue_fleet_numerics.py', run_name='__main__')
    finally:
        fleet_checkpoint.load_fleet_checkpoint, sys.argv = original, argv


if __name__ == '__main__':
    main()
