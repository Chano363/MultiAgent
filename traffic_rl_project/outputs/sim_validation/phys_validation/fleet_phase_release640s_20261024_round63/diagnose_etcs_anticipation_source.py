"""Recorded one-factor opt-in ATP anticipation from a trusted fleet state."""
import argparse
import copy
import hashlib
from pathlib import Path
import runpy
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from src.evaluation import fleet_checkpoint


def enable_anticipation(env, manifest):
    manifest = copy.deepcopy(manifest)
    previous = [bool(c.anticipate_etcs) for c in env.multi_loco_controllers]
    for controller in env.multi_loco_controllers:
        controller.anticipate_etcs = True
    manifest['experimental_controller_override'] = dict(
        anticipate_etcs=True, previous_flags=previous,
        scope='Single-factor rule anticipation trial; ATP constraints unchanged')
    source = Path(__file__).read_bytes()
    manifest['numerical']['source_sha256']['diagnose_etcs_anticipation'] = hashlib.sha256(source).hexdigest()
    return env, manifest


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--state-dir', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--steps', type=int, required=True)
    args = parser.parse_args()
    original = fleet_checkpoint.load_fleet_checkpoint
    original_argv = sys.argv
    def load_with_override(directory):
        return enable_anticipation(*original(directory))
    fleet_checkpoint.load_fleet_checkpoint = load_with_override
    try:
        sys.argv = ['continue_fleet_numerics.py', '--state-dir', str(args.state_dir),
                    '--output', str(args.output), '--steps', str(args.steps)]
        runpy.run_path('src/evaluation/continue_fleet_numerics.py', run_name='__main__')
    finally:
        fleet_checkpoint.load_fleet_checkpoint = original
        sys.argv = original_argv


if __name__ == '__main__':
    main()
