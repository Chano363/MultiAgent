"""Native staged validation after a promising approximate phase screen.

One current-cycle leader release candidate, not a production default change.
Every child retains accepted-microstep, speed, gap and ATP stop conditions.
"""
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import time


def main():
    base = Path('outputs/sim_validation/phys_validation')
    root = base/'fleet_pace49_native_20261028_round144'
    root.mkdir(parents=True, exist_ok=False)
    state = base/'fleet_leader_prerelease55_20261027_round116'
    entry = Path('src/evaluation/diagnose_release_feasibility.py')
    digest = hashlib.sha256(entry.read_bytes()).hexdigest()
    (root/'orchestrator_source.py').write_bytes(Path(__file__).read_bytes())
    result = dict(status='running', current_cycle_release_kmh=49.,
        restore_after_release_kmh=54., origin=str(state),
        scope='Native 400s maximum phase candidate; not full-route acceptance', stages=[])
    began = time.monotonic()

    def save():
        result['wall_s'] = time.monotonic()-began
        (root/'progress.json').write_text(json.dumps(result, indent=2), encoding='utf-8')

    save()
    try:
        for i in range(8):
            if (root/'STOP').exists():
                result['status'] = 'requested_stop_between_stages'
                break
            if hashlib.sha256(entry.read_bytes()).hexdigest() != digest:
                raise RuntimeError('Diagnostic entry changed during validation')
            output = root/f'stage_{i+1:04d}'
            command = [sys.executable, '-u', str(entry), '--state-dir', str(state),
                       '--output', str(output), '--steps', '500']
            if i == 0:
                command += ['--arm-release-kmh', '49']
            subprocess.run(command, check=True)
            summary = json.loads((output/'result.json').read_text(encoding='utf-8'))['summary']
            result['stages'].append(dict(directory=str(output), summary=summary))
            result['last_time_s'] = summary['last_time_s']
            save()
            if summary['stop_reason'] != 'step_budget':
                result['status'] = summary['stop_reason']
                break
            state = output
        else:
            result['status'] = 'bounded_window_completed'
        if result['stages']:
            baseline = [str(base/'fleet_release50_cycle_20261027_round124'/f'stage_{i+1:04d}')
                        for i in range(8)]
            candidate = [s['directory'] for s in result['stages']]
            subprocess.run([sys.executable, 'src/evaluation/compare_fleet_segments.py',
                '--baseline', *baseline, '--candidate', *candidate,
                '--reference-gap-m', '183.33305555555555',
                '--output', str(root/'comparison.json')], check=True)
            comparison = json.loads((root/'comparison.json').read_text(encoding='utf-8'))
            document = Path('D:/Codex/Documents/Train/controller_takeover_20261017/'
                            '领航49缓解_真实多体阶段验证_20261028.md')
            lines = ['# 领航49 km/h缓解：真实多体阶段验证', '',
                '当前一次循环由50降至49，实际缓解后恢复54；222秒与原安全优先级不变。',
                f"停止状态：{result['status']}；共同窗：{comparison['window_s']}秒。",
                '若提前停止，仅比较共同前缀，不能称400秒候选成功。', '',
                '| 指标 | 原50方案 | 49候选 |', '|---|---:|---:|']
            for key, label in [('internal_peak_kn', '接受微步车钩峰值/kN'),
                ('min_vehicle_kmh', '车辆最低速度/(km/h)'),
                ('max_vehicle_kmh', '车辆最高速度/(km/h)'),
                ('safety_event_count', '新增安全接管/次'),
                ('mean_absolute_gap_error_m', '列距平均绝对误差/m'),
                ('mean_speed_spread_kmh', '平均列间均速极差/(km/h)')]:
                lines.append(f"| {label} | {comparison['baseline'][key]:.4f} | "
                             f"{comparison['candidate'][key]:.4f} |")
            lines += ['', f"原方案末态列距：{comparison['baseline']['end_gaps_m']}米。",
                f"候选末态列距：{comparison['candidate']['end_gaps_m']}米。",
                '本报告不自动采纳候选；不等于完整路线、热安全或训练就绪。',
                f'原始数组、元数据与SHA：{root.resolve()}。']
            with document.open('x', encoding='utf-8') as stream:
                stream.write('\n'.join(lines)+'\n')
            result['document'] = str(document)
    except BaseException as exc:
        result.update(status='failed', error=repr(exc))
        raise
    finally:
        save()
        (root/'result.json').write_text(json.dumps(result, indent=2), encoding='utf-8')


if __name__ == '__main__':
    main()
