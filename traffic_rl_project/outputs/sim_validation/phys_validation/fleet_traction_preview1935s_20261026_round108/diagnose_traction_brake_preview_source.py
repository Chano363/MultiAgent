"""Same-state second-train ordinary traction withdrawal diagnostic."""
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
        ctrl = env.multi_loco_controllers[1]
        if not getattr(ctrl, '_formation_traction_slew_enabled', False):
            raise ValueError('Requires the existing traction growth guard')
        ctrl._traction_brake_preview_enabled = True
        manifest = copy.deepcopy(manifest)
        manifest['traction_brake_preview_trial'] = dict(train_one_based=2,
            margin_mps=ctrl.AB_SUPPRESS_MARGIN_MPS,
            scope='Engineering traction taper before original brake threshold; no brake delay')
        for name in ('traction_brake_preview', 'diagnose_traction_brake_preview'):
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
