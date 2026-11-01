"""Finite staged local trial; stop at a failed stage, never launch training."""
import json
from pathlib import Path
import subprocess
import sys

import numpy as np


ROOT = Path('outputs/sim_validation/phys_validation')


def run_stage(script, state, output, steps, extra=(), stop_on_safety=False):
    command = [sys.executable, '-u', 'src/evaluation/'+script+'.py',
               '--state-dir', str(ROOT/state), '--output', str(ROOT/output),
               '--steps', str(steps), *extra]
    process = subprocess.Popen(command, stdout=subprocess.PIPE, text=True,
                               encoding='utf-8', errors='replace')
    for line in process.stdout:
        print(line, end='', flush=True)
        if stop_on_safety and 'safety_delta=' in line:
            delta = int(line.split('safety_delta=')[1].split()[0])
            if delta > 0:
                (ROOT/output/'STOP').write_text('New ATP event; end bounded trial', encoding='utf-8')
    if process.wait() != 0:
        raise RuntimeError('Stage process failed: '+output)
    result = json.loads((ROOT/output/'result.json').read_text(encoding='utf-8'))['summary']
    print('STAGE_RESULT '+json.dumps(result), flush=True)
    return result['stop_reason'] == 'step_budget' and result['safety_event_count'] == 0


def main():
    source = 'fleet_early_phase526s_20261024_round67'
    recovered = 'fleet_prerelease590s_20261024_round70'
    trial = 'fleet_lower_release630s_20261024_round71'
    extension = 'fleet_lower_release_resume850s_20261024_round72'
    if not run_stage('continue_fleet_numerics', source, recovered, 641):
        return
    with np.load(ROOT/recovered/'trajectory.npz') as current, np.load(
            ROOT/'fleet_early_phase_resume720s_20261024_round68'/'trajectory.npz') as reference:
        differences = {k: float(np.max(np.abs(current[k]-reference[k][:len(current[k])])))
                       for k in current.files}
    (ROOT/recovered/'prefix_comparison.json').write_text(json.dumps(differences, indent=2), encoding='utf-8')
    if any(differences.values()):
        raise RuntimeError('Recovered prefix differs from original trial')
    (ROOT/recovered/'orchestrator_source.py').write_bytes(Path(__file__).read_bytes())
    print('PREFIX_IDENTICAL '+json.dumps(differences), flush=True)
    if not run_stage('diagnose_lower_release', recovered, trial, 400,
                     ('--train-one-based', '2', '--release-kmh', '48'), True):
        return
    (ROOT/trial/'diagnose_lower_release_source.py').write_bytes(
        Path('src/evaluation/diagnose_lower_release.py').read_bytes())
    run_stage('continue_fleet_numerics', trial, extension, 2191, stop_on_safety=True)


if __name__ == '__main__':
    main()
