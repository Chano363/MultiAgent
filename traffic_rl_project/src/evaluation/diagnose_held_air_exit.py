"""Isolate tail held-air speed balancing; preserve native release and safety.

This is an ablation, not an accepted controller change. The inherited ordinary
ED handback limiter remains enabled, and only the tail balancing enable flag
is changed. Full checkpoints and numerical source checks remain in force.
"""
import hashlib
from pathlib import Path
import runpy
import sys

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from src.evaluation import fleet_checkpoint


def disable_tail_balance(env, manifest):
    if env.num_trains != 3:
        raise ValueError('Requires the recorded three-train checkpoint')
    controller = env.multi_loco_controllers[2]
    if not getattr(controller, '_held_air_balance_enabled', False):
        raise ValueError('Tail balancing must initially be enabled')
    if not getattr(controller, '_held_air_smooth_handoff_enabled', False):
        raise ValueError('Inherited smooth ED handback must remain enabled')
    previous = getattr(controller, '_held_air_handoff_previous_ed', None)
    if previous is None or not np.isfinite(previous):
        raise ValueError('A real recorded ED handback anchor is required')
    controller._held_air_balance_enabled = False
    # Disabled balancing returns early and cannot clear its old active latch.
    # Explicitly hand the recorded ED level to the existing smooth limiter.
    controller._held_air_balance_active = False
    controller._held_air_handoff_pending = True
    manifest['held_air_exit_ablation'] = {
        'train_one_based': 3,
        'change': 'Disable held-air speed balancing only',
        'handoff': 'Clear balance latch and arm inherited limiter at recorded ED anchor',
        'recorded_ed_anchor': float(previous),
        'unchanged': 'Native cyclic release, refill, ED capacity, ATP and smooth handback',
        'scope': 'Causal ablation; not a selected production fix',
    }
    name = Path(__file__).stem
    manifest['numerical']['source_sha256'][name] = hashlib.sha256(
        Path(__file__).read_bytes()).hexdigest()
    return env, manifest


def main():
    original = fleet_checkpoint.load_fleet_checkpoint
    output = Path(sys.argv[sys.argv.index('--output')+1])

    def load(directory):
        return disable_tail_balance(*original(directory))

    fleet_checkpoint.load_fleet_checkpoint = load
    try:
        runpy.run_path('src/evaluation/diagnose_release_feasibility.py', run_name='__main__')
    finally:
        fleet_checkpoint.load_fleet_checkpoint = original
        if output.exists():
            (output/'diagnose_held_air_exit_source.py').write_bytes(Path(__file__).read_bytes())


if __name__ == '__main__':
    main()
