"""Same-state release-phase plus refill-aware chase isolation, zero RL only."""
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
    def load_with_guard(directory):
        env, manifest = original(directory)
        manifest = copy.deepcopy(manifest)
        for controller in env.multi_loco_controllers:
            controller._phase_release_floor_enabled = True
            controller._refill_chase_pause_enabled = True
        manifest['experimental_refill_chase_override'] = dict(
            phase_release_floor_enabled=True, refill_chase_pause_enabled=True,
            comparison='Versus phase-release trial from same 520s state; zero RL only')
        for name in ('phase_aware_release', 'refill_chase_guard', 'diagnose_refill_chase'):
            manifest['numerical']['source_sha256'][name] = hashlib.sha256(
                Path('src/evaluation', name+'.py').read_bytes()).hexdigest()
        return env, manifest
    fleet_checkpoint.load_fleet_checkpoint = load_with_guard
    try:
        sys.argv = ['continue_fleet_numerics.py', '--state-dir', str(args.state_dir),
                    '--output', str(args.output), '--steps', str(args.steps)]
        runpy.run_path('src/evaluation/continue_fleet_numerics.py', run_name='__main__')
    finally:
        fleet_checkpoint.load_fleet_checkpoint, sys.argv = original, argv


if __name__ == '__main__':
    main()
