"""Single follower ED-allocation intervention from a trusted whole-fleet state."""
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
    parser.add_argument('--train-one-based', type=int, default=3)
    args = parser.parse_args()
    original, argv = fleet_checkpoint.load_fleet_checkpoint, sys.argv

    def load_with_override(directory):
        env, manifest = original(directory)
        if not 2 <= args.train_one_based <= env.num_trains:
            raise ValueError('Select a follower')
        ctrl = env.multi_loco_controllers[args.train_one_based-1]
        if not any(ctrl._ab_on):
            raise ValueError('Start with an established air source')
        ctrl._held_air_balance_enabled = True
        ctrl._held_air_gap_reference_m = env._dynamic_gap()
        manifest = copy.deepcopy(manifest)
        manifest['experimental_held_air_override'] = dict(
            train_one_based=args.train_one_based, gap_reference_m=env._dynamic_gap(),
            scope='ED-only engineering trial; source pressure, refill and ATP unchanged')
        for name in ('held_air_speed_balance', 'diagnose_held_air_balance'):
            manifest['numerical']['source_sha256'][name] = hashlib.sha256(
                Path('src/evaluation', name+'.py').read_bytes()).hexdigest()
        return env, manifest

    fleet_checkpoint.load_fleet_checkpoint = load_with_override
    try:
        sys.argv = ['continue_fleet_numerics.py', '--state-dir', str(args.state_dir),
                    '--output', str(args.output), '--steps', str(args.steps)]
        runpy.run_path('src/evaluation/continue_fleet_numerics.py', run_name='__main__')
    finally:
        fleet_checkpoint.load_fleet_checkpoint, sys.argv = original, argv


if __name__ == '__main__':
    main()
