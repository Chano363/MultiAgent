"""Same candidate on a real alternate operating history; no kinematic edits."""
import argparse
import copy
import hashlib
from pathlib import Path
import runpy
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from src.evaluation import fleet_checkpoint


def enable_neighbor(env, manifest):
    if env.num_trains != 3 or not any(env.multi_loco_controllers[2]._ab_on):
        raise ValueError('Requires the three-train pre-existing third air source')
    if any(c.cyclic_release_kmh != 50. for c in env.multi_loco_controllers[1:]):
        raise ValueError('Follower release settings differ from primary candidate')
    result = copy.deepcopy(manifest)
    previous = env.multi_loco_controllers[0].cyclic_release_kmh
    env.multi_loco_controllers[0].cyclic_release_kmh = 54.
    ctrl = env.multi_loco_controllers[2]
    ctrl._held_air_balance_enabled = True
    ctrl._held_air_gap_reference_m = env._formation_ref_gap()
    ctrl._held_air_smooth_handoff_enabled = True
    result['experimental_alternate_state_override'] = dict(
        previous_leader_release_kmh=previous, leader_release_kmh=54., follower_release_kmh=50.,
        held_air_train_one_based=3, smooth_handoff=True,
        scope='Alternate real operating history; positions, velocities, pressures and clocks unedited')
    for name in ('held_air_speed_balance', 'held_air_smooth_handoff', 'diagnose_held_air_neighbor'):
        result['numerical']['source_sha256'][name] = hashlib.sha256(
            Path('src/evaluation', name+'.py').read_bytes()).hexdigest()
    return env, result


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--state-dir', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--steps', type=int, required=True)
    args = parser.parse_args()
    original, argv = fleet_checkpoint.load_fleet_checkpoint, sys.argv

    def load_with_override(directory):
        return enable_neighbor(*original(directory))

    fleet_checkpoint.load_fleet_checkpoint = load_with_override
    try:
        sys.argv = ['continue_fleet_numerics.py', '--state-dir', str(args.state_dir),
                    '--output', str(args.output), '--steps', str(args.steps)]
        runpy.run_path('src/evaluation/continue_fleet_numerics.py', run_name='__main__')
    finally:
        fleet_checkpoint.load_fleet_checkpoint, sys.argv = original, argv


if __name__ == '__main__':
    main()
