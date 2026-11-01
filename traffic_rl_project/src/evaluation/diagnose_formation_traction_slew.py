"""Enable second train traction slew in an established complete fleet state."""
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
        env.multi_loco_controllers[1]._formation_traction_slew_enabled = True
        manifest = copy.deepcopy(manifest)
        manifest['formation_traction_slew_trial'] = dict(train_one_based=2,
            rise_per_s=.05, scope='Zero-RL engineering traction-request slew; no braking restriction')
        for name in ('formation_traction_slew', 'diagnose_formation_traction_slew'):
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
