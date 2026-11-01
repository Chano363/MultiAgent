"""Same-state anticipation trial plus the existing .5 m/s control margin."""
import argparse
import hashlib
from pathlib import Path
import runpy
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from src.evaluation import fleet_checkpoint
from src.evaluation.diagnose_etcs_anticipation import enable_anticipation


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--state-dir', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--steps', type=int, required=True)
    args = parser.parse_args()
    original, argv = fleet_checkpoint.load_fleet_checkpoint, sys.argv
    def load_with_margin(directory):
        env, manifest = enable_anticipation(*original(directory))
        margins = []
        for controller in env.multi_loco_controllers:
            controller._following_rule_margin_mps = controller.AB_SUPPRESS_MARGIN_MPS
            margins.append(controller._following_rule_margin_mps)
        manifest['experimental_controller_override']['following_rule_margin_mps'] = margins
        manifest['experimental_controller_override']['scope'] = (
            'Additional restrictive margin versus anticipate_etcs=True comparison; no ATP change')
        for name in ('following_speed_margin', 'diagnose_following_margin'):
            manifest['numerical']['source_sha256'][name] = hashlib.sha256(
                Path('src/evaluation', name+'.py').read_bytes()).hexdigest()
        return env, manifest
    fleet_checkpoint.load_fleet_checkpoint = load_with_margin
    try:
        sys.argv = ['continue_fleet_numerics.py', '--state-dir', str(args.state_dir),
                    '--output', str(args.output), '--steps', str(args.steps)]
        runpy.run_path('src/evaluation/continue_fleet_numerics.py', run_name='__main__')
    finally:
        fleet_checkpoint.load_fleet_checkpoint, sys.argv = original, argv


if __name__ == '__main__':
    main()
