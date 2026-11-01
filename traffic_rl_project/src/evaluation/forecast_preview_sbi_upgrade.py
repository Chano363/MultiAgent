"""Screen a model-response preview; no changes to the actual SBI boundary."""
import copy
import hashlib
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from src.evaluation import native_air_centroid_forecast as predictor
from src.evaluation.forecast_terminal_evidence import capture


def arm(env, manifest):
    result = copy.deepcopy(manifest)
    for ctrl in env.multi_loco_controllers[1:]:
        ctrl._preview_sbi_upgrade_enabled = True
        ctrl._preview_sbi_previous = None
    result['preview_sbi_upgrade_trial'] = dict(trains=[2, 3],
        scope='Local trend extrapolation using native wave/fill/ED-ramp times; not a safety guarantee')
    for name in ('preview_sbi_upgrade', 'forecast_preview_sbi_upgrade', 'forecast_terminal_evidence'):
        result['numerical']['source_sha256'][name] = hashlib.sha256(
            Path('src/evaluation', name+'.py').read_bytes()).hexdigest()
    return env, result


def main():
    original = predictor.load_fleet_checkpoint

    def load(directory):
        return arm(*original(directory))

    predictor.load_fleet_checkpoint = load
    try:
        with capture(predictor):
            predictor.main()
    finally:
        predictor.load_fleet_checkpoint = original


if __name__ == '__main__':
    main()
