"""Finite single-threshold comparison on the same trusted 720s fleet state."""
import argparse
from pathlib import Path
import re
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from src.evaluation.run_lower_release_validation import ROOT, run_stage


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--release-kmh', type=float, required=True)
    parser.add_argument('--tag', required=True)
    args = parser.parse_args()
    if re.fullmatch(r'[a-z0-9_]+', args.tag) is None:
        parser.error('Archive tag must contain lowercase letters, digits and underscores')
    source = 'fleet_early_phase_resume720s_20261024_round68'
    trial = 'fleet_leader_threshold_local760s_'+args.tag
    extension = 'fleet_leader_threshold_resume1000s_'+args.tag
    if not run_stage('diagnose_leader_release', source, trial, 400,
                     ('--release-kmh', str(args.release_kmh)), stop_on_safety=True):
        return
    for name in ('diagnose_leader_release', 'run_leader_threshold_validation',
                 'run_lower_release_validation'):
        (ROOT/trial/(name+'_source.py')).write_bytes(
            Path('src/evaluation', name+'.py').read_bytes())
    run_stage('continue_fleet_numerics', trial, extension, 2400, stop_on_safety=True)


if __name__ == '__main__':
    main()
