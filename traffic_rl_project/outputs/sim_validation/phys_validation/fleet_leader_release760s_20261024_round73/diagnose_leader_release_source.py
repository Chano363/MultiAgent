"""Opt-in leader pacing trial; retain native air, coupler and ATP gates."""
import argparse
import copy
import hashlib
from pathlib import Path
import runpy
import sys

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from src.evaluation import fleet_checkpoint


def set_leader_release(env, manifest, release_kmh):
    if len(env.multi_loco_controllers) < 2:
        raise ValueError('Leader pacing requires a fleet')
    controller = env.multi_loco_controllers[0]
    previous = controller.cyclic_release_kmh
    if (previous is None or not np.isfinite(release_kmh)
            or not max(env.v_min*3.6, previous) < release_kmh < env.v_max*3.6):
        raise ValueError('Trial must raise release within the existing speed band')
    if not any(controller._ab_on):
        raise ValueError('Leader must have an established air source')
    result = copy.deepcopy(manifest)
    result['experimental_leader_release_override'] = dict(
        previous_kmh=float(previous), trial_kmh=float(release_kmh),
        scope='Engineering pacing trial; not calibrated air timing or safety guarantee')
    result['numerical']['source_sha256']['diagnose_leader_release'] = hashlib.sha256(
        Path(__file__).read_bytes()).hexdigest()
    controller.cyclic_release_kmh = float(release_kmh)
    return env, result


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--state-dir', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--steps', type=int, required=True)
    parser.add_argument('--release-kmh', type=float, required=True)
    args = parser.parse_args()
    original, argv = fleet_checkpoint.load_fleet_checkpoint, sys.argv

    def load_with_override(directory):
        return set_leader_release(*original(directory), args.release_kmh)

    fleet_checkpoint.load_fleet_checkpoint = load_with_override
    try:
        sys.argv = ['continue_fleet_numerics.py', '--state-dir', str(args.state_dir),
                    '--output', str(args.output), '--steps', str(args.steps)]
        runpy.run_path('src/evaluation/continue_fleet_numerics.py', run_name='__main__')
    finally:
        fleet_checkpoint.load_fleet_checkpoint, sys.argv = original, argv


if __name__ == '__main__':
    main()
