"""Screen a joint release phase without saving a native restart state."""
import argparse
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from src.evaluation import native_air_centroid_forecast as predictor
from src.evaluation.joint_release_phase import arm


def main():
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument('--follower-release-kmh', type=float, default=53.)
    options, remaining = parser.parse_known_args()
    original, argv = predictor.load_fleet_checkpoint, sys.argv

    def load(directory):
        env, manifest = original(directory)
        return arm(env, manifest, options.follower_release_kmh)

    predictor.load_fleet_checkpoint = load
    sys.argv = [argv[0], *remaining]
    try:
        predictor.main()
    finally:
        predictor.load_fleet_checkpoint, sys.argv = original, argv


if __name__ == '__main__':
    main()
