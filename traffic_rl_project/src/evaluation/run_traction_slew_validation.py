"""Restore before electrical reversal, verify history, then test traction slew."""
from pathlib import Path
import json
import subprocess
import sys
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from src.evaluation.run_lower_release_validation import ROOT, run_stage


def main():
    source = 'fleet_fixed_candidate_fullroute_20261025_round94/stage_0074'
    prefix = 'fleet_traction_prereversal1865s_20261026_round99'
    trial = 'fleet_traction_slew1875s_20261026_round100'
    if not run_stage('continue_fleet_numerics', source, prefix, 150, stop_on_safety=True):
        raise RuntimeError('Recovery did not reach intended restart')
    baseline = ROOT/'fleet_fixed_candidate_fullroute_20261025_round94/stage_0075'
    diffs = {}
    for filename in ('trajectory.npz', 'telemetry.npz'):
        with np.load(ROOT/prefix/filename) as a, np.load(baseline/filename) as b:
            for key in a.files:
                diffs[filename+'/'+key] = float(np.max(abs(
                    a[key].astype(float)-b[key][:len(a[key])].astype(float))))
    (ROOT/prefix/'prefix_comparison.json').write_text(json.dumps(diffs, indent=2), encoding='utf-8')
    if any(diffs.values()):
        raise RuntimeError('Recovery differs from original full-route history')
    (ROOT/prefix/'orchestrator_source.py').write_bytes(Path(__file__).read_bytes())
    run_stage('diagnose_formation_traction_slew', prefix, trial, 100, stop_on_safety=True)
    for script, options, name in (
        ('compare_fleet_segments', ['--reference-gap-m', '183.3330556'], 'comparison.json'),
        ('compare_air_allocation_cost', [], 'air_cost_comparison.json')):
        subprocess.run([sys.executable, 'src/evaluation/'+script+'.py', '--baseline', str(baseline),
            '--candidate', str(ROOT/trial), '--output', str(ROOT/trial/name), *options], check=True)


if __name__ == '__main__':
    main()
