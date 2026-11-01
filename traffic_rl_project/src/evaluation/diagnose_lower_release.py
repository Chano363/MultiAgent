"""Single-controller release-speed trial from a complete fleet checkpoint."""
import argparse
import copy
import hashlib
from pathlib import Path
import runpy
import sys

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from src.evaluation import fleet_checkpoint


def set_lower_release(env, manifest, train_one_based, release_kmh):
    if not 1 <= train_one_based <= len(env.multi_loco_controllers):
        raise ValueError('Train index outside fleet')
    ctrl = env.multi_loco_controllers[train_one_based-1]
    previous = ctrl.cyclic_release_kmh
    if (previous is None or not np.isfinite(release_kmh)
            or not env.v_min*3.6 <= release_kmh < previous):
        raise ValueError('Only a finite restrictive change within the speed band is allowed')
    if not any(ctrl._ab_on):
        raise ValueError('Trial must begin before release, with an established source')
    if not getattr(ctrl, '_phase_release_floor_enabled', False):
        raise ValueError('Requires the recorded phase-isolation candidate')
    result = copy.deepcopy(manifest)
    result['experimental_release_speed_override'] = dict(
        train_one_based=train_one_based, previous_kmh=float(previous),
        trial_kmh=float(release_kmh),
        scope='Engineering trial, not literature calibration; no air timing or ATP change')
    result['numerical']['source_sha256']['diagnose_lower_release'] = hashlib.sha256(
        Path(__file__).read_bytes()).hexdigest()
    ctrl.cyclic_release_kmh = float(release_kmh)
    return env, result


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--state-dir', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--steps', type=int, required=True)
    parser.add_argument('--train-one-based', type=int, required=True)
    parser.add_argument('--release-kmh', type=float, required=True)
    args = parser.parse_args()
    original, argv = fleet_checkpoint.load_fleet_checkpoint, sys.argv

    def load_with_override(directory):
        return set_lower_release(*original(directory), args.train_one_based, args.release_kmh)

    fleet_checkpoint.load_fleet_checkpoint = load_with_override
    try:
        sys.argv = ['continue_fleet_numerics.py', '--state-dir', str(args.state_dir),
                    '--output', str(args.output), '--steps', str(args.steps)]
        runpy.run_path('src/evaluation/continue_fleet_numerics.py', run_name='__main__')
    finally:
        fleet_checkpoint.load_fleet_checkpoint, sys.argv = original, argv


if __name__ == '__main__':
    main()
