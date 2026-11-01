"""Bounded leader pacing trial on the successful 720s state, not the failed branch."""
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from src.evaluation.run_lower_release_validation import ROOT, run_stage


def main():
    source = 'fleet_early_phase_resume720s_20261024_round68'
    trial = 'fleet_leader_release760s_20261024_round73'
    extension = 'fleet_leader_release_resume945s_20261024_round74'
    if not run_stage('diagnose_leader_release', source, trial, 400,
                     ('--release-kmh', '56.1'), stop_on_safety=True):
        return
    for name in ('diagnose_leader_release', 'run_leader_release_validation',
                 'run_lower_release_validation'):
        (ROOT/trial/(name+'_source.py')).write_bytes(
            Path('src/evaluation', name+'.py').read_bytes())
    run_stage('continue_fleet_numerics', trial, extension, 1850, stop_on_safety=True)


if __name__ == '__main__':
    main()
