"""Forecast a current observed release event, never output a live restart."""
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from src.evaluation import native_air_centroid_forecast as predictor
from src.evaluation.release_event_sync import arm, candidate


def main():
    original = predictor.load_fleet_checkpoint

    def load(directory):
        return arm(*original(directory))

    predictor.load_fleet_checkpoint = load
    try:
        with candidate():
            predictor.main()
    finally:
        predictor.load_fleet_checkpoint = original


if __name__ == '__main__':
    main()
