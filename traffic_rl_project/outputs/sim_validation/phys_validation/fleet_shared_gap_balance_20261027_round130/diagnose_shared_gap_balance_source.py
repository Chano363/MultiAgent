"""Share the existing bounded gap-aware ED allocation with train two.

Opt-in diagnostic only: no new gains, air thresholds or safety changes.
"""
import hashlib
from pathlib import Path
import runpy
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from src.evaluation import fleet_checkpoint


def enable_second_gap_balance(env, manifest):
    if env.num_trains != 3:
        raise ValueError('Requires three recorded trains')
    second, third = env.multi_loco_controllers[1:]
    if (getattr(second, '_gap_aware_air_enabled', False)
            or not getattr(third, '_gap_aware_air_enabled', False)
            or not getattr(second, '_held_air_balance_enabled', False)):
        raise ValueError('Requires original second balance and gap-aware third balance')
    second._gap_aware_air_enabled = True
    manifest['shared_gap_balance_trial'] = {
        'train_one_based': 2,
        'change': 'Enable existing gap-aware ED target on second train',
        'target_bonus_cap_mps': .5,
        'scope': 'Diagnostic candidate; native air cycle and actual ATP untouched',
    }
    name = Path(__file__).stem
    manifest['numerical']['source_sha256'][name] = hashlib.sha256(
        Path(__file__).read_bytes()).hexdigest()
    return env, manifest


def main():
    original = fleet_checkpoint.load_fleet_checkpoint
    output = Path(sys.argv[sys.argv.index('--output')+1])

    def load(directory):
        return enable_second_gap_balance(*original(directory))

    fleet_checkpoint.load_fleet_checkpoint = load
    try:
        runpy.run_path('src/evaluation/diagnose_release_feasibility.py', run_name='__main__')
    finally:
        fleet_checkpoint.load_fleet_checkpoint = original
        if output.exists():
            (output/'diagnose_shared_gap_balance_source.py').write_bytes(Path(__file__).read_bytes())


if __name__ == '__main__':
    main()
