"""Forecast-only leader residual-air ED trial; no restart checkpoint output."""
import copy
import hashlib
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from src.evaluation import native_air_centroid_forecast as predictor
from src.evaluation.residual_air_ed_budget import candidate


def main():
    original = predictor.load_fleet_checkpoint

    def load(directory):
        env, manifest = original(directory)
        env.multi_loco_controllers[0]._residual_air_budget_enabled = True
        result = copy.deepcopy(manifest)
        result['residual_air_ed_budget_trial'] = dict(train_one_based=1,
            scope='Forecast-only; native mechanical validation required')
        for name in ('residual_air_ed_budget', 'forecast_residual_air_budget'):
            result['numerical']['source_sha256'][name] = hashlib.sha256(
                Path('src/evaluation', name+'.py').read_bytes()).hexdigest()
        return env, result

    # Call the imported module main so the replaced loader is actually used.
    predictor.load_fleet_checkpoint = load
    try:
        with candidate():
            predictor.main()
    finally:
        predictor.load_fleet_checkpoint = original


if __name__ == '__main__':
    main()
