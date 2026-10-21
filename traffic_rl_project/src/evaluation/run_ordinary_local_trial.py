"""Wait for a verified baseline checkpoint, then run one bounded local trial."""
import hashlib
import argparse
import json
import os
from pathlib import Path
import subprocess
import sys
import time

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from src.evaluation.diagnose_balanced_cold import relocate_forecast_archive
from src.evaluation.ordinary_release_guard import ordinary_release_source


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--refine-retry', action='store_true')
    args = parser.parse_args()
    root = Path('outputs/sim_validation/phys_validation')
    checkpoint = root/'single108_pre_release_state_20261020_round35_retry1'
    baseline = root/'single108_release_low_speed_route_20261020_round33'
    tag = 'round37' if args.refine_retry else 'round36'
    output = root/f'single108_ordinary_release_local_20261020_{tag}'
    source_dir = root/f'single108_ordinary_release_source_20261020_{tag}'
    deadline = time.monotonic() + 7200
    while not (checkpoint/'result.json').exists():
        if time.monotonic() > deadline:
            raise TimeoutError('Baseline checkpoint not completed within two hours')
        time.sleep(5)
    summary = json.loads((checkpoint/'result.json').read_text())['summary']
    if summary['stop_reason'] != 'step_budget' or abs(summary['last_time_s']-2180.) > .001:
        raise ValueError('Pre-release checkpoint ended unexpectedly')
    with np.load(checkpoint/'trajectory.npz') as replay, np.load(baseline/'trajectory.npz') as ref:
        indices = np.searchsorted(ref['rows'][:, 0], replay['rows'][:, 0] - 1e-5)
        errors = {k: float(np.abs(replay[k]-ref[k][indices]).max()) for k in
                  ('rows', 'commands', 'vehicle_positions_m', 'vehicle_speeds_mps',
                   'effective_pressure_coefficient')}
        if max(errors.values()) > 1e-6:
            raise ValueError(f'Baseline replay differs: {errors}')
    source_dir.mkdir(exist_ok=False)
    text = ordinary_release_source((checkpoint/'controller_source.py').read_text(encoding='utf-8'))
    if args.refine_retry:
        from src.evaluation.refined_release_retry import refined_retry_source
        text = refined_retry_source(text)
    text = relocate_forecast_archive(text, output)
    source = source_dir/'controller_source.py'
    source.write_text(text, encoding='utf-8')
    helpers = {}
    names = ['ordinary_release_guard', 'release_low_speed_controller']
    if args.refine_retry:
        names.append('refined_release_retry')
    for name in names:
        raw = Path('src/evaluation', name+'.py').read_bytes()
        (source_dir/(name+'_source.py')).write_bytes(raw)
        helpers[name] = hashlib.sha256(raw).hexdigest()
    command = [sys.executable, '-u', 'src/evaluation/continue_native_release_control.py',
        '--state-dir', str(checkpoint), '--controller-source', str(source),
        '--resume-experimental', '--steps', '4000', '--finish-m', '49600',
        '--save-native-release-state', '--output', str(output)]
    (source_dir/'protocol.json').write_text(json.dumps(dict(
        scope='2180 to 2580 seconds local candidate, not a full-route acceptance',
        helper_sha256=helpers, baseline_replay_errors=errors, command=command), indent=2))
    env = dict(os.environ, OPENBLAS_NUM_THREADS='1', OMP_NUM_THREADS='1',
               MKL_NUM_THREADS='1', PYTHONDONTWRITEBYTECODE='1', PYTHONIOENCODING='utf-8')
    with (source_dir/'trial_stdout.log').open('w', encoding='utf-8') as log:
        subprocess.run(command, check=True, env=env, stdout=log, stderr=subprocess.STDOUT)
    def metrics(path, start, end):
        with np.load(path/'trajectory.npz') as d:
            mask = (d['rows'][:, 0] >= start-1e-4) & (d['rows'][:, 0] <= end+1e-4)
            speed = d['vehicle_speeds_mps'][mask]*3.6
            air = d['commands'][mask, 0, 1]
            return dict(min_vehicle_kmh=float(speed.min()), max_vehicle_kmh=float(speed.max()),
                min_mean_kmh=float(speed.mean(axis=1).min()),
                stronger_request_onsets=int(np.sum((air < -.1) & ~np.r_[False, air[:-1] < -.1])),
                sampled_peak_kn=float(np.abs(d['coupler_interface_force_n'][mask]).max()/1000))
    candidate = json.loads((output/'result.json').read_text())['summary']
    end = candidate['last_time_s']
    comparison = dict(scope='same initial full state and same time window; not full route',
        summary=candidate, baseline=metrics(baseline, 2180.1, end),
        candidate=metrics(output, 2180.1, end), helper_sha256=helpers)
    (output/'local_comparison.json').write_text(json.dumps(comparison, indent=2))
    print(json.dumps(comparison), flush=True)


if __name__ == '__main__':
    main()
