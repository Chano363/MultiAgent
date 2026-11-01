"""Local established-air ED trial, followed by a conditional cycle extension."""
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from src.evaluation.run_lower_release_validation import ROOT, run_stage


def main():
    source = 'fleet_leader_threshold_local760s_54_20261024_round78_79'
    trial = 'fleet_held_air_balance800s_20261025_round81'
    extension = 'fleet_held_air_balance_resume1200s_20261025_round82'
    if not run_stage('diagnose_held_air_balance', source, trial, 400,
                     ('--train-one-based', '3'), stop_on_safety=True):
        return
    for name in ('held_air_speed_balance', 'diagnose_held_air_balance',
                 'run_held_air_balance_validation', 'run_lower_release_validation'):
        (ROOT/trial/(name+'_source.py')).write_bytes(
            Path('src/evaluation', name+'.py').read_bytes())
    run_stage('continue_fleet_numerics', trial, extension, 4000, stop_on_safety=True)


if __name__ == '__main__':
    main()
