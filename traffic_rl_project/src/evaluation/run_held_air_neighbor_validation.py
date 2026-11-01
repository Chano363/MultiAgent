"""Finite alternate-history check, same settings as the primary smooth candidate."""
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from src.evaluation.run_lower_release_validation import ROOT, run_stage


def main():
    source = 'fleet_leader_release760s_20261024_round73'
    trial = 'fleet_held_air_neighbor800s_20261025_round86'
    extension = 'fleet_held_air_neighbor_resume1200s_20261025_round87'
    if not run_stage('diagnose_held_air_neighbor', source, trial, 400, stop_on_safety=True):
        return
    for name in ('held_air_speed_balance', 'held_air_smooth_handoff',
                 'diagnose_held_air_neighbor', 'run_held_air_neighbor_validation'):
        (ROOT/trial/(name+'_source.py')).write_bytes(Path('src/evaluation', name+'.py').read_bytes())
    run_stage('continue_fleet_numerics', trial, extension, 4000, stop_on_safety=True)


if __name__ == '__main__':
    main()
