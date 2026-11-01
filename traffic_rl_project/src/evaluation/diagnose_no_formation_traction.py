"""Short causal ablation: disable formation-injected traction, not native ATP."""
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
        previous = env.LEAN_MAX_TRACTION
        env.LEAN_MAX_TRACTION = 0.
        manifest = copy.deepcopy(manifest)
        manifest['formation_traction_ablation'] = dict(previous_max_traction=previous,
            trial_max_traction=0., scope='Causal diagnostic only; all other requests and ATP unchanged')
        manifest['numerical']['source_sha256']['diagnose_no_formation_traction'] = hashlib.sha256(
            Path(__file__).read_bytes()).hexdigest()
        return env, manifest

    fleet_checkpoint.load_fleet_checkpoint = load
    try:
        runpy.run_path('src/evaluation/diagnose_micropeak.py', run_name='__main__')
    finally:
        fleet_checkpoint.load_fleet_checkpoint = original


if __name__ == '__main__':
    main()
