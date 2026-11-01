"""Finalize already-running bounded trials; never start training or adopt rules."""
import json
from pathlib import Path
import subprocess
import sys
import time


def main():
    base = Path('outputs/sim_validation/phys_validation')
    actual = base/'fleet_pace49_nextcycle_20261031_round145'
    forecast = base/'fleet_pace49_nextcycle_forecast_20261031_round146'
    root = base/'fleet_pace49_followup_audit_20261031_round147'
    root.mkdir(exist_ok=False)
    (root/'entry_source.py').write_bytes(Path(__file__).read_bytes())
    started = time.monotonic()
    status = dict(status='waiting_for_existing_trials', native=str(actual), forecast=str(forecast))

    def save():
        status['wall_s'] = time.monotonic()-started
        (root/'progress.json').write_text(json.dumps(status, indent=2), encoding='utf-8')

    def run(entry, *args):
        subprocess.run([sys.executable, 'src/evaluation/'+entry, *map(str, args)], check=True)

    save()
    try:
        while not all((p/'result.json').exists() for p in (actual, forecast)):
            if (root/'STOP').exists():
                status['status'] = 'requested_audit_stop_trials_unchanged'
                return
            if time.monotonic()-started > 43200:
                raise TimeoutError('Trials did not produce results within 12h; inspect processes')
            time.sleep(20)
        status['status'] = 'auditing_completed_trials'
        save()
        run('compare_native_air_forecast.py', '--forecast', forecast, '--baseline', actual,
            '--output', root/'forecast_accuracy.json')
        old = [base/'fleet_release50_cycle_20261027_round124'/f'stage_{i:04d}' for i in range(1, 9)]
        old += [base/'fleet_restored54_nextcycle_20261027_round125',
                base/'fleet_restored54_match350_20261027_round128']
        new = [base/'fleet_pace49_native_20261028_round144'/f'stage_{i:04d}' for i in range(1, 9)]
        new += [actual]
        run('compare_fleet_segments.py', '--baseline', *old, '--candidate', *new,
            '--reference-gap-m', '183.33305555555555', '--output', root/'native_comparison.json')
        run('audit_linked_air_work.py', '--baseline', *old, '--candidate', *new,
            '--output', root/'air_work_comparison.json')
        c = json.loads((root/'native_comparison.json').read_text(encoding='utf-8'))
        work = json.loads((root/'air_work_comparison.json').read_text(encoding='utf-8'))
        summary = json.loads((actual/'result.json').read_text(encoding='utf-8'))['summary']
        status.update(status='audit_completed', native_stop_reason=summary['stop_reason'],
                      native_last_time_s=summary['last_time_s'])
        report = Path('D:/Codex/Documents/Train/controller_takeover_20261017/领航49缓解_后续联合核验_20261031.md')
        lines = ['# 领航49缓解后续联合核验', '',
            '本轮无强化学习、无正式默认值修改；222秒与安全接管保持原语义。',
            f"后续原生仿真停止原因：{summary['stop_reason']}。",
            f"共同采样范围：{c['window_s']}秒，{c['samples']}点；提前停止时仅比较共同前缀。", '',
            '| 指标 | 原50方案 | 49候选 |', '|---|---:|---:|']
        for key in ('internal_peak_kn', 'min_vehicle_kmh', 'max_vehicle_kmh',
                    'safety_event_count', 'mean_absolute_gap_error_m',
                    'mean_speed_spread_kmh', 'max_speed_spread_kmh'):
            lines.append(f"| {key} | {c['baseline'][key]:.4f} | {c['candidate'][key]:.4f} |")
        lines += ['', f"机械空气制动做功/MJ：{work['baseline']['air_work_mj_total']:.3f} → "
                  f"{work['candidate']['air_work_mj_total']:.3f}；不能据此判断轮温。",
                  f"末态列距/m：{c['candidate']['end_gaps_m']}。",
                  f"末态列均速/(km/h)：{c['candidate']['end_mean_kmh']}。",
                  '本轮只验证局部相位候选，不是全程或训练就绪验收，不自动采纳。',
                  '若停止原因为安全或数值异常，先核对接受微步峰值、空气相位与安全事件，禁止从失败状态继续推进。',
                  f'原始证据、来源SHA与预测误差：{root.resolve()}。']
        with report.open('x', encoding='utf-8') as stream:
            stream.write('\n'.join(lines)+'\n')
        status['document'] = str(report)
    except BaseException as exc:
        status.update(status='audit_failed', error=repr(exc))
        raise
    finally:
        save()
        (root/'result.json').write_text(json.dumps(status, indent=2), encoding='utf-8')


if __name__ == '__main__':
    main()
