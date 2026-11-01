"""Reproduce the pre-jump state, test handback, extend only with lower jerk."""
import json
from pathlib import Path
import sys

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from src.evaluation.run_lower_release_validation import ROOT, run_stage


def main():
    source = 'fleet_held_air_balance800s_20261025_round81'
    recovery = 'fleet_held_air_prereturn900s_20261025_round83'
    trial = 'fleet_held_air_smooth940s_20261025_round84'
    extension = 'fleet_held_air_smooth_resume1200s_20261025_round85'
    reference = ROOT/'fleet_held_air_balance_resume1200s_20261025_round82'/'trajectory.npz'
    if not run_stage('continue_fleet_numerics', source, recovery, 1000):
        return
    with np.load(ROOT/recovery/'trajectory.npz') as a, np.load(reference) as b:
        differences = {k: float(np.max(abs(a[k]-b[k][:len(a[k])]))) for k in a.files}
    (ROOT/recovery/'prefix_comparison.json').write_text(json.dumps(differences, indent=2), encoding='utf-8')
    if any(differences.values()):
        raise RuntimeError('Pre-handback replay differs')
    if not run_stage('diagnose_smooth_held_air', recovery, trial, 400, stop_on_safety=True):
        return
    with np.load(ROOT/trial/'trajectory.npz') as a, np.load(reference) as b:
        mask = (b['rows'][:, 0] > 900.01) & (b['rows'][:, 0] < 940.01)
        old = b['vehicle_speeds_mps'][mask, 2, 0]
        new = a['vehicle_speeds_mps'][:, 2, 0]
        old_jerk = float(np.max(abs(np.diff(old, n=2)/.01)))
        new_jerk = float(np.max(abs(np.diff(new, n=2)/.01)))
    comparison = dict(window_s=[900.1, 940.], baseline_head_peak_jerk_mps3=old_jerk,
                      candidate_head_peak_jerk_mps3=new_jerk)
    (ROOT/trial/'handoff_comparison.json').write_text(json.dumps(comparison, indent=2), encoding='utf-8')
    print('HANDOFF_COMPARISON '+json.dumps(comparison), flush=True)
    for name in ('held_air_smooth_handoff', 'diagnose_smooth_held_air',
                 'run_smooth_handoff_validation', 'run_lower_release_validation'):
        (ROOT/trial/(name+'_source.py')).write_bytes(Path('src/evaluation', name+'.py').read_bytes())
    if new_jerk >= old_jerk:
        print('No jerk improvement: do not extend', flush=True)
        return
    run_stage('continue_fleet_numerics', trial, extension, 2600, stop_on_safety=True)


if __name__ == '__main__':
    main()
