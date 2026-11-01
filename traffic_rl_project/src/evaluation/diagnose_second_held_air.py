"""Bounded second-follower allocation trial from a preserved fleet state."""
import argparse
import copy
import hashlib
import logging
from pathlib import Path
import runpy
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from src.evaluation import fleet_checkpoint


def main():
    logging.basicConfig(level=logging.INFO)
    parser = argparse.ArgumentParser()
    parser.add_argument('--state-dir', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--steps', type=int, required=True)
    args = parser.parse_args()
    original, argv = fleet_checkpoint.load_fleet_checkpoint, sys.argv

    def override(directory):
        env, manifest = original(directory)
        ctrl = env.multi_loco_controllers[1]
        if not any(ctrl._ab_on):
            raise ValueError('Second train must already have an air source')
        ctrl._held_air_balance_enabled = True
        ctrl._held_air_smooth_handoff_enabled = True
        ctrl._held_air_gap_reference_m = env._dynamic_gap()
        manifest = copy.deepcopy(manifest)
        manifest['experimental_second_held_air'] = {
            'train_one_based': 2, 'scope': 'Zero-RL local ED-only diagnostic; '
            'no change to air timing, pressure, ATP or thermal parameters'}
        for name in ('held_air_speed_balance', 'held_air_smooth_handoff',
                     'diagnose_second_held_air'):
            manifest['numerical']['source_sha256'][name] = hashlib.sha256(
                Path('src/evaluation', name+'.py').read_bytes()).hexdigest()
        return env, manifest

    fleet_checkpoint.load_fleet_checkpoint = override
    try:
        sys.argv = ['continue_fleet_numerics.py', '--state-dir', str(args.state_dir),
                    '--output', str(args.output), '--steps', str(args.steps)]
        runpy.run_path('src/evaluation/continue_fleet_numerics.py', run_name='__main__')
    finally:
        fleet_checkpoint.load_fleet_checkpoint, sys.argv = original, argv


if __name__ == '__main__':
    main()
