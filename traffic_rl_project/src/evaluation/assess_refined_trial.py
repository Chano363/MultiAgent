"""Assess a bounded local trial before authorizing the remaining route."""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import time

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from src.evaluation.diagnose_balanced_cold import relocate_forecast_archive


def assess(current, previous):
    summary, metrics = current['summary'], current['candidate']
    old = previous['candidate']
    checks = {
        'local_window_complete': summary['stop_reason'] == 'step_budget'
            and summary['steps'] == 4000 and abs(summary['last_time_s']-2580.) < .001,
        'all_vehicle_speed_safe': metrics['min_vehicle_kmh'] >= 40.
            and metrics['max_vehicle_kmh'] < 80.,
        'internal_coupler_safe': summary['internal_microstep_peak_kn'] is not None
            and summary['internal_microstep_peak_kn'] <= 1000.,
        'no_stronger_request': metrics['stronger_request_onsets'] == 0,
        'minimum_speed_improved': metrics['min_vehicle_kmh'] > old['min_vehicle_kmh'] + .05,
        'internal_coupler_improved': summary['internal_microstep_peak_kn'] is not None
            and previous['summary']['internal_microstep_peak_kn'] is not None
            and summary['internal_microstep_peak_kn']
            < previous['summary']['internal_microstep_peak_kn'] - .1,
    }
    return dict(checks=checks, continue_remaining_route=all(checks.values()),
                scope='local improvement over round36, not full-route acceptance')


def main():
    root = Path('outputs/sim_validation/phys_validation')
    local = root/'single108_ordinary_release_local_20261020_round37'
    report = local/'local_comparison.json'
    deadline = time.monotonic()+7200
    while not report.exists():
        if time.monotonic() > deadline:
            raise TimeoutError('Local trial has not produced a comparison')
        time.sleep(5)
    current = json.loads(report.read_text())
    previous = json.loads((root/'single108_ordinary_release_local_20261020_round36/local_comparison.json').read_text())
    decision = assess(current, previous)
    (local/'acceptance_decision.json').write_text(json.dumps(decision, indent=2))
    print(json.dumps(decision), flush=True)
    if not decision['continue_remaining_route']:
        return
    protocol = json.loads((root/'single108_ordinary_release_source_20261020_round37/protocol.json').read_text())
    for name, digest in protocol['helper_sha256'].items():
        if hashlib.sha256(Path('src/evaluation', name+'.py').read_bytes()).hexdigest() != digest:
            raise ValueError('Candidate helper changed during local run')
    source_dir = root/'single108_refined_remaining_source_20261020_round38'
    output = root/'single108_refined_remaining_route_20261020_round38'
    source_dir.mkdir(exist_ok=False)
    text = relocate_forecast_archive((local/'controller_source.py').read_text(encoding='utf-8'), output)
    source = source_dir/'controller_source.py'
    source.write_text(text, encoding='utf-8')
    command = [sys.executable, '-u', 'src/evaluation/continue_native_release_control.py',
        '--state-dir', str(local), '--controller-source', str(source),
        '--resume-experimental', '--steps', '10000', '--finish-m', '49600',
        '--save-native-release-state', '--output', str(output)]
    (source_dir/'protocol.json').write_text(json.dumps(dict(
        command=command, decision=decision, helper_sha256=protocol['helper_sha256'],
        scope='same full-state history continued from 2580s; no reset and no new figure'), indent=2))
    env = dict(os.environ, OPENBLAS_NUM_THREADS='1', OMP_NUM_THREADS='1',
        MKL_NUM_THREADS='1', PYTHONDONTWRITEBYTECODE='1', PYTHONIOENCODING='utf-8')
    with (source_dir/'stdout.log').open('w', encoding='utf-8') as log:
        subprocess.run(command, check=True, env=env, stdout=log, stderr=subprocess.STDOUT)
    print((output/'result.json').read_text(), flush=True)


if __name__ == '__main__':
    main()
