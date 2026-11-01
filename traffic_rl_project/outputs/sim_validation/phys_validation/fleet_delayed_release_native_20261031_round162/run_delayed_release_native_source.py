"""Bounded native phase validation, then one follow-up if all gates pass."""
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import time


def main():
    base = Path('outputs/sim_validation/phys_validation')
    root = base/'fleet_delayed_release_native_20261031_round162'
    root.mkdir(exist_ok=False)
    state = base/'fleet_leader_prerelease55_20261027_round116'
    names = ('continue_fleet_numerics', 'diagnose_delayed_leader_release',
             'diagnose_release_feasibility', 'delayed_leader_release', 'ready_cycle_pacing',
             'run_delayed_release_native')
    frozen = {}
    for name in names:
        file = Path('src/evaluation', name+'.py')
        frozen[name] = hashlib.sha256(file.read_bytes()).hexdigest()
        (root/(name+'_source.py')).write_bytes(file.read_bytes())
    result = dict(status='running', scope='Native 400s phase trial plus 350s follow-up, not full-route acceptance',
                  origin=str(state), stages=[], frozen_entry_sha256=frozen)
    began = time.monotonic()

    def save():
        result['wall_s'] = time.monotonic()-began
        (root/'progress.json').write_text(json.dumps(result, indent=2), encoding='utf-8')

    def run(entry, *args):
        subprocess.run([sys.executable, '-u', 'src/evaluation/'+entry, *map(str, args)], check=True)

    save()
    try:
        for i, steps in enumerate([500]*8+[3500]):
            if (root/'STOP').exists():
                result['status'] = 'requested_stop_between_stages'
                break
            for name, digest in frozen.items():
                if hashlib.sha256(Path('src/evaluation', name+'.py').read_bytes()).hexdigest() != digest:
                    raise RuntimeError('Frozen diagnostic implementation changed')
            output = root/f'stage_{i+1:04d}'
            args = ['--state-dir', state, '--output', output, '--steps', steps]
            if i == 0:
                args.append('--arm-delayed')
            run('diagnose_delayed_leader_release.py', *args)
            summary = json.loads((output/'result.json').read_text(encoding='utf-8'))['summary']
            result['stages'].append(dict(directory=str(output), summary=summary))
            result['last_time_s'] = summary['last_time_s']
            save()
            if summary['stop_reason'] != 'step_budget':
                result['status'] = summary['stop_reason']
                break
            state = output
        else:
            result['status'] = 'bounded_750s_completed'
        if result['stages']:
            baseline = [base/'fleet_pace49_native_20261028_round144'/f'stage_{i:04d}' for i in range(1, 9)]
            baseline.append(base/'fleet_pace49_nextcycle_20261031_round145')
            candidates = [Path(s['directory']) for s in result['stages']]
            run('compare_fleet_segments.py', '--baseline', *baseline, '--candidate', *candidates,
                '--reference-gap-m', '183.33305555555555', '--output', root/'native_comparison.json')
            run('audit_linked_air_work.py', '--baseline', *baseline, '--candidate', *candidates,
                '--output', root/'air_work_comparison.json')
            run('compare_native_air_forecast.py', '--forecast',
                base/'fleet_delayed_leader_release_forecast_20261031_round159',
                '--baseline', *candidates[:8], '--output', root/'forecast_accuracy.json')
            c = json.loads((root/'native_comparison.json').read_text(encoding='utf-8'))
            report = Path('D:/Codex/Documents/Train/controller_takeover_20261017/领航延后缓解_联合相位验证_20261031.md')
            lines = ['', '### 原生多体自动验收结果', '',
                f"状态：{result['status']}；共同采样范围：{c['window_s']}秒。",
                '提前停止时只比较共同前缀，不能写成750秒通过。', '',
                '| 指标 | 原49方案 | 延后缓解候选 |', '|---|---:|---:|']
            for key in ('internal_peak_kn', 'min_vehicle_kmh', 'max_vehicle_kmh',
                        'safety_event_count', 'mean_absolute_gap_error_m',
                        'mean_speed_spread_kmh', 'max_speed_spread_kmh'):
                lines.append(f"| {key} | {c['baseline'][key]:.4f} | {c['candidate'][key]:.4f} |")
            lines += ['', '本轮不自动采纳，不代表全程、热安全或训练就绪。',
                      f'完整状态、接受微步、原始数组和SHA：{root.resolve()}。']
            with report.open('a', encoding='utf-8') as stream:
                stream.write('\n'.join(lines)+'\n')
            result['document'] = str(report)
    except BaseException as exc:
        result.update(status='failed', error=repr(exc))
        raise
    finally:
        save()
        (root/'result.json').write_text(json.dumps(result, indent=2), encoding='utf-8')


if __name__ == '__main__':
    main()
