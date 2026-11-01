"""Trace exact pre-spike history, then refine only a shared short restart."""
import json
from pathlib import Path
import subprocess
import sys

import numpy as np

ROOT = Path('outputs/sim_validation/phys_validation')


def stage(source, name, steps, factor=1.):
    destination = ROOT/name
    subprocess.run([sys.executable, '-u', 'src/evaluation/diagnose_micropeak.py',
        '--state-dir', str(source), '--output', str(destination), '--steps', str(steps),
        '--step-factor', str(factor)], check=True)
    summary = json.loads((destination/'result.json').read_text(encoding='utf-8'))['summary']
    print('STAGE '+name+' '+json.dumps(summary), flush=True)
    return destination, summary


def main():
    prefix, summary = stage(ROOT/'fleet_fixed_candidate_fullroute_20261025_round94/stage_0074',
        'fleet_micropeak_prefix1870s_20261026_round96', 200)
    if summary['stop_reason'] != 'step_budget':
        raise RuntimeError('Prefix did not reach requested restart')
    old = ROOT/'fleet_fixed_candidate_fullroute_20261025_round94/stage_0075'
    diffs = {}
    for filename in ('trajectory.npz', 'telemetry.npz'):
        with np.load(prefix/filename) as a, np.load(old/filename) as b:
            for key in a.files:
                diffs[filename+'/'+key] = float(np.max(np.abs(
                    a[key].astype(float)-b[key][:len(a[key])].astype(float))))
    (prefix/'prefix_comparison.json').write_text(json.dumps(diffs, indent=2), encoding='utf-8')
    if any(diffs.values()):
        raise RuntimeError('Trace observer changed the replayed prefix')
    results = []
    for factor, tag in ((1., 'original'), (.5, 'half'), (.25, 'quarter')):
        directory, summary = stage(prefix, 'fleet_micropeak_'+tag+'_20261026_round97', 30, factor)
        trace = json.loads((directory/'accepted_micropeaks.json').read_text(encoding='utf-8'))
        peak = max(trace['records'], key=lambda x: x['peak_kn'], default=None)
        results.append(dict(factor=factor, directory=str(directory), summary=summary, peak=peak))
    (prefix/'refinement_comparison.json').write_text(json.dumps(dict(
        scope='Same 1870s full state; different maximum mechanical step, '
              'threshold stops may produce different final windows',
        runs=results), indent=2), encoding='utf-8')


if __name__ == '__main__':
    main()
