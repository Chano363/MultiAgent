"""Arm a single warm-phase leader release trial from a complete checkpoint."""
import hashlib
from pathlib import Path
import runpy
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from src.evaluation import fleet_checkpoint
from src.evaluation.ready_cycle_pacing import arm_current_cycle


def main():
    original = fleet_checkpoint.load_fleet_checkpoint

    def load(directory):
        env, manifest = arm_current_cycle(*original(directory))
        for name in ('ready_cycle_pacing', 'diagnose_ready_cycle_pacing'):
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
