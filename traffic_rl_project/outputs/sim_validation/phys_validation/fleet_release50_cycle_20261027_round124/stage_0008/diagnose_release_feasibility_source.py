"""Arm one release candidate once, or continue it with accepted-peak observation."""
import argparse
import hashlib
from pathlib import Path
import runpy
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from src.evaluation import fleet_checkpoint
from src.evaluation.ready_cycle_pacing import arm_current_cycle
from src.evaluation.micropeak_observer import observe


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--state-dir', type=Path, required=True)
    p.add_argument('--output', type=Path, required=True)
    p.add_argument('--steps', type=int, required=True)
    p.add_argument('--arm-release-kmh', type=float)
    args = p.parse_args()
    original, argv, live_ids = fleet_checkpoint.load_fleet_checkpoint, sys.argv, {}

    def load(directory):
        env, manifest = original(directory)
        if args.arm_release_kmh is not None:
            env, manifest = arm_current_cycle(env, manifest, args.arm_release_kmh)
        live_ids.update({id(t.dynamics): i+1 for i,t in enumerate(env.trains)})
        for name in ('ready_cycle_pacing', 'micropeak_observer', 'diagnose_release_feasibility'):
            manifest['numerical']['source_sha256'][name] = hashlib.sha256(
                Path('src/evaluation', name+'.py').read_bytes()).hexdigest()
        return env, manifest

    fleet_checkpoint.load_fleet_checkpoint = load
    try:
        sys.argv = ['continue_fleet_numerics.py', '--state-dir', str(args.state_dir),
            '--output', str(args.output), '--steps', str(args.steps), '--stop-on-safety-event']
        with observe(args.output, live_ids):
            runpy.run_path('src/evaluation/continue_fleet_numerics.py', run_name='__main__')
    finally:
        fleet_checkpoint.load_fleet_checkpoint, sys.argv = original, argv
        if args.output.exists():
            for name in ('ready_cycle_pacing', 'micropeak_observer', 'diagnose_release_feasibility'):
                (args.output/(name+'_source.py')).write_bytes(
                    Path('src/evaluation', name+'.py').read_bytes())


if __name__ == '__main__':
    main()
