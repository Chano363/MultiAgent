"""Continue only a successful native handoff test, then audit linked branches."""
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import time


def main():
    base = Path('outputs/sim_validation/phys_validation')
    first = base/'fleet_chase_exit_native_20261031_round165'
    root = base/'fleet_chase_exit_followup_20261031_round166'
    root.mkdir(exist_ok=False)
    status = dict(status='waiting_for_native_handoff_trial', stages=[str(first)])
    started = time.monotonic()
    names = ('pre_release_chase_exit', 'forecast_pre_release_chase_exit',
             'diagnose_pre_release_chase_exit', 'continue_fleet_numerics')
    frozen = {n: hashlib.sha256(Path('src/evaluation', n+'.py').read_bytes()).hexdigest() for n in names}
    for name in names+('finalize_chase_exit_native',):
        (root/(name+'_source.py')).write_bytes(Path('src/evaluation', name+'.py').read_bytes())
    status['frozen_source_sha256'] = frozen

    def save():
        status['wall_s'] = time.monotonic()-started
        (root/'progress.json').write_text(json.dumps(status, indent=2), encoding='utf-8')

    def run(entry, *args):
        subprocess.run([sys.executable, '-u', 'src/evaluation/'+entry, *map(str, args)], check=True)

    save()
    try:
        while not (first/'result.json').exists():
            if (root/'STOP').exists():
                status['status'] = 'requested_audit_stop_native_unchanged'
                return
            if time.monotonic()-started > 43200:
                raise TimeoutError('Native local trial has no result after 12h')
            time.sleep(20)
        summary = json.loads((first/'result.json').read_text(encoding='utf-8'))['summary']
        status.update(status=summary['stop_reason'], first_summary=summary)
        if summary['stop_reason'] == 'step_budget' and not (root/'STOP').exists():
            for name, digest in frozen.items():
                if hashlib.sha256(Path('src/evaluation', name+'.py').read_bytes()).hexdigest() != digest:
                    raise RuntimeError('Frozen source changed')
            status['status'] = 'running_200s_followup'
            save()
            follow = root/'followup'
            run('diagnose_pre_release_chase_exit.py', '--state-dir', first,
                '--output', follow, '--steps', '2000')
            status['stages'].append(str(follow))
            summary = json.loads((follow/'result.json').read_text(encoding='utf-8'))['summary']
            status.update(status='bounded_750s_completed' if summary['stop_reason'] == 'step_budget'
                          else summary['stop_reason'], followup_summary=summary)
        prefix = [base/'fleet_delayed_release_native_20261031_round162'/f'stage_{i:04d}' for i in range(1, 9)]
        candidates = prefix+[Path(s) for s in status['stages']]
        old = [base/'fleet_pace49_native_20261028_round144'/f'stage_{i:04d}' for i in range(1, 9)]
        old += [base/'fleet_pace49_nextcycle_20261031_round145']
        run('compare_fleet_segments.py', '--baseline', *old, '--candidate', *candidates,
            '--reference-gap-m', '183.33305555555555', '--output', root/'native_comparison.json')
        run('audit_linked_air_work.py', '--baseline', *old, '--candidate', *candidates,
            '--output', root/'air_work_comparison.json')
        run('compare_fleet_segments.py', '--baseline', *(prefix+[base/'fleet_delayed_release_native_20261031_round162'/'stage_0009']),
            '--candidate', *candidates, '--reference-gap-m', '183.33305555555555',
            '--output', root/'failed_handoff_common_prefix.json')
        run('compare_native_air_forecast.py', '--forecast', base/'fleet_chase_exit_candidate_forecast_20261031_round164',
            '--baseline', first, '--output', root/'forecast_accuracy.json')
        c = json.loads((root/'native_comparison.json').read_text(encoding='utf-8'))
        report = Path('D:/Codex/Documents/Train/controller_takeover_20261017/编队追赶与缓解保持接口修复_20261031.md')
        lines = ['', '### 原生验证自动回填', '', f"状态：{status['status']}；共同范围：{c['window_s']}秒。",
                 '提前停止时仅比较共同前缀，不能写成750秒通过。', '',
                 '| 指标 | 原49方案 | 相位加接口候选 |', '|---|---:|---:|']
        for key in ('internal_peak_kn', 'min_vehicle_kmh', 'max_vehicle_kmh',
                    'safety_event_count', 'mean_absolute_gap_error_m',
                    'mean_speed_spread_kmh', 'max_speed_spread_kmh'):
            lines.append(f"| {key} | {c['baseline'][key]:.4f} | {c['candidate'][key]:.4f} |")
        lines += ['', '未自动改正式默认值；局部通过不等于全程或长期循环通过。',
                  '接口补丁仅试验本周期，不声称已解决所有起点和循环。', f'原始证据：{root.resolve()}。']
        with report.open('a', encoding='utf-8') as stream:
            stream.write('\n'.join(lines)+'\n')
        status['document'] = str(report)
    except BaseException as exc:
        status.update(status='failed', error=repr(exc))
        raise
    finally:
        save()
        (root/'result.json').write_text(json.dumps(status, indent=2), encoding='utf-8')


if __name__ == '__main__':
    main()
