"""Same-state post-release ED budget with shared traction slew protection."""
import copy
import hashlib
from pathlib import Path
import runpy
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from src.evaluation import fleet_checkpoint


def main():
    original = fleet_checkpoint.load_fleet_checkpoint

    def load(directory):
        env, manifest = original(directory)
        for c in env.multi_loco_controllers[1:]:
            c._formation_traction_slew_enabled = True
        env.multi_loco_controllers[2]._formation_release_budget_enabled = True
        env.multi_loco_controllers[2]._formation_release_speed_ceiling_mps = env.v_max
        manifest = copy.deepcopy(manifest)
        manifest['formation_release_budget_trial'] = dict(train_one_based=3,
            traction_slew_trains=[2, 3], scope='Zero-RL equilibrium ED cap after full air release/refill')
        for name in ('formation_release_budget', 'diagnose_formation_release_budget'):
            manifest['numerical']['source_sha256'][name] = hashlib.sha256(
                Path('src/evaluation', name+'.py').read_bytes()).hexdigest()
        return env, manifest

    fleet_checkpoint.load_fleet_checkpoint = load
    try:
        runpy.run_path('src/evaluation/diagnose_micropeak.py', run_name='__main__')
    finally:
        fleet_checkpoint.load_fleet_checkpoint = original


if __name__ == '__main__':
    main()
