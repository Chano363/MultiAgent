"""Forecast a bounded fixed-force plateau; no native restart output."""
import copy
import hashlib
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from src.evaluation import native_air_centroid_forecast as predictor
from src.evaluation.pre_release_fixed_ed import candidate


def main():
    original = predictor.load_fleet_checkpoint

    def load(directory):
        env, manifest = original(directory)
        env.multi_loco_controllers[0]._pre_release_fixed_ed_enabled = True
        result = copy.deepcopy(manifest)
        result['pre_release_fixed_ed_trial'] = dict(train_one_based=1,
            target_kn=350., preparatory_below_kmh=60.,
            scope='One-cycle forecast, engineering values, not calibrated or a safety certificate')
        for name in ('pre_release_fixed_ed', 'forecast_pre_release_fixed_ed'):
            result['numerical']['source_sha256'][name] = hashlib.sha256(
                Path('src/evaluation', name+'.py').read_bytes()).hexdigest()
        return env, result

    predictor.load_fleet_checkpoint = load
    try:
        with candidate():
            predictor.main()
    finally:
        predictor.load_fleet_checkpoint = original


if __name__ == '__main__':
    main()
