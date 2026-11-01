"""Opt in to ordinary ED handback smoothing, preserving the balance model."""
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

    def load_with_override(directory):
        env, manifest = original(directory)
        enabled = [c for c in env.multi_loco_controllers
                   if getattr(c, '_held_air_balance_enabled', False)]
        if len(enabled) != 1:
            raise ValueError('Requires the single-follower held-air trial')
        enabled[0]._held_air_smooth_handoff_enabled = True
        manifest = copy.deepcopy(manifest)
        manifest['experimental_smooth_handoff_override'] = dict(
            enabled=True, ordinary_ed_rise_per_s=.05,
            scope='Rate-limited ordinary handback only; no safety-layer bypass')
        for name in ('held_air_smooth_handoff', 'diagnose_smooth_held_air'):
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
