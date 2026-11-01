"""Enable gap-error target on third train only from a complete checkpoint."""
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
    p = argparse.ArgumentParser()
    p.add_argument('--state-dir', type=Path, required=True)
    p.add_argument('--output', type=Path, required=True)
    p.add_argument('--steps', type=int, required=True)
    args = p.parse_args()
    original, argv = fleet_checkpoint.load_fleet_checkpoint, sys.argv

    def override(directory):
        env, manifest = original(directory)
        ctrl = env.multi_loco_controllers[2]
        if not getattr(ctrl, '_held_air_balance_enabled', False):
            raise ValueError('Requires established held-air balance candidate')
        ctrl._gap_aware_air_enabled = True
        manifest = copy.deepcopy(manifest)
        manifest['gap_aware_air_trial'] = dict(train_one_based=3,
            gap_horizon_s=60., bonus_cap_mps=.5, scope='Zero-RL ED-only diagnostic')
        for name in ('gap_aware_air_balance', 'diagnose_gap_aware_air'):
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
