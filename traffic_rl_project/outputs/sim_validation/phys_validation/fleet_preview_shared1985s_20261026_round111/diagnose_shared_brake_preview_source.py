"""Apply the existing tested traction preview to both follower trains."""
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
        if env.num_trains != 3 or any(not getattr(c, '_formation_traction_slew_enabled', False)
                                     for c in env.multi_loco_controllers[1:]):
            raise ValueError('Requires three trains with both follower traction slew guards')
        for ctrl in env.multi_loco_controllers[1:]:
            ctrl._traction_brake_preview_enabled = True
        manifest = copy.deepcopy(manifest)
        manifest['shared_brake_preview_trial'] = dict(trains_one_based=[2, 3],
            scope='Same preview logic and parameters, extended to the third train')
        manifest['numerical']['source_sha256']['diagnose_shared_brake_preview'] = hashlib.sha256(
            Path(__file__).read_bytes()).hexdigest()
        return env, manifest

    fleet_checkpoint.load_fleet_checkpoint = load
    try:
        runpy.run_path('src/evaluation/diagnose_micropeak.py', run_name='__main__')
    finally:
        fleet_checkpoint.load_fleet_checkpoint = original


if __name__ == '__main__':
    main()
