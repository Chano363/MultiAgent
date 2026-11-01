"""Bounded staged real-pneumatic test; never turn a passing screen into acceptance."""
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import time


def main():
    root = Path('outputs/sim_validation/phys_validation/fleet_release50_cycle_20261027_round124')
    root.mkdir(parents=True, exist_ok=False)
    state = Path('outputs/sim_validation/phys_validation/fleet_leader_prerelease55_20261027_round116')
    entry = Path('src/evaluation/diagnose_release_feasibility.py')
    digest = hashlib.sha256(entry.read_bytes()).hexdigest()
    (root/'orchestrator_source.py').write_bytes(Path(__file__).read_bytes())
    started = time.time()
    result = dict(status='running', scope='One-cycle 50km/h candidate from 2121.1s, '
        'real native pneumatic evolution, 400s maximum; not full-route acceptance',
        initial_state=str(state), stages=[])

    def save():
        result['elapsed_wall_s'] = time.time()-started
        (root/'progress.json').write_text(json.dumps(result, indent=2), encoding='utf-8')

    save()
    try:
        for i in range(8):
            if (root/'STOP').exists():
                result['status'] = 'requested_stop_between_stages'
                break
            if hashlib.sha256(entry.read_bytes()).hexdigest() != digest:
                raise RuntimeError('Entry changed while diagnostic was running')
            out = root/f'stage_{i+1:04d}'
            command = [sys.executable, '-u', str(entry), '--state-dir', str(state),
                       '--output', str(out), '--steps', '500']
            if i == 0:
                command += ['--arm-release-kmh', '50']
            subprocess.run(command, check=True)
            summary = json.loads((out/'result.json').read_text(encoding='utf-8'))['summary']
            result['stages'].append(dict(directory=str(out), summary=summary))
            result['last_time_s'] = summary['last_time_s']
            save()
            if summary['stop_reason'] != 'step_budget':
                result['status'] = summary['stop_reason']
                break
            state = out
        else:
            result['status'] = 'bounded_window_completed'
    except BaseException as exc:
        result.update(status='failed', error=repr(exc))
        raise
    finally:
        save()
        (root/'result.json').write_text(json.dumps(result, indent=2), encoding='utf-8')


if __name__ == '__main__':
    main()
