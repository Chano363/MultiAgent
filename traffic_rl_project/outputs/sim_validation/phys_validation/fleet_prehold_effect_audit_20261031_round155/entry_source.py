"""Finish an already-started screening pair without adopting a controller."""
import json
from pathlib import Path
import subprocess
import sys
import time


def main():
    base = Path('outputs/sim_validation/phys_validation')
    baseline = base/'fleet_prehold_baseline_forecast_20261031_round152'
    trial = base/'fleet_prehold350_active_forecast_20261031_round154'
    root = base/'fleet_prehold_effect_audit_20261031_round155'
    root.mkdir(exist_ok=False)
    (root/'entry_source.py').write_bytes(Path(__file__).read_bytes())
    began = time.monotonic()
    status = dict(status='waiting_for_existing_forecast', candidate=str(trial))
    try:
        (root/'progress.json').write_text(json.dumps(status), encoding='utf-8')
        while not (trial/'result.json').exists():
            if (root/'STOP').exists():
                status['status'] = 'requested_audit_stop'
                return
            if time.monotonic()-began > 43200:
                raise TimeoutError('Forecast did not finish within 12h')
            time.sleep(20)
        subprocess.run([sys.executable, 'src/evaluation/compare_air_phase_candidates.py',
            '--origin', str(base/'fleet_pace49_native_20261028_round144'/'stage_0007'),
            '--baseline', str(baseline), '--candidate', str(trial),
            '--output', str(root/'comparison.json')], check=True)
        c = json.loads((root/'comparison.json').read_text(encoding='utf-8'))
        for name in ('pre_release_fixed_ed', 'forecast_pre_release_fixed_ed',
                     'compare_air_phase_candidates'):
            (root/(name+'_source.py')).write_bytes(Path('src/evaluation', name+'.py').read_bytes())
        report = Path('D:/Codex/Documents/Train/controller_takeover_20261017/单机电制动能力与相位受力核对_20261031.md')
        lines = ['', '### 有效门控修正后的预测结果（自动补记）', '',
            f"共同窗口：{c['window_s']}秒；动作变化采样数：{c['changed_action_samples']}。",
            f"成本与动作有效性预筛：{c['passes_effect_and_cost_screen']}。", '',
            '| 指标 | 原方案预测 | 候选预测 |', '|---|---:|---:|']
        for key in ('gap_mae_m', 'mean_speed_spread_kmh', 'air_work_mj_total',
                    'min_predicted_mean_kmh', 'max_predicted_mean_kmh', 'native_safety_events'):
            lines.append(f"| {key} | {c['baseline'][key]:.4f} | {c['candidate'][key]:.4f} |")
        lines += ['', '这仍是质心预测：即使预筛改善，也不等于车钩安全通过，不自动改正式配置。',
            '预筛不改善则不启动昂贵原生多体试验；改善则另行核查保持段、交接平滑及原生多体安全。',
            f'原始证据：{root.resolve()}。']
        with report.open('a', encoding='utf-8') as stream:
            stream.write('\n'.join(lines)+'\n')
        status.update(status='forecast_audit_completed',
            passes_effect_and_cost_screen=c['passes_effect_and_cost_screen'], document=str(report))
    except BaseException as exc:
        status.update(status='audit_failed', error=repr(exc))
        raise
    finally:
        (root/'result.json').write_text(json.dumps(status, indent=2), encoding='utf-8')
        (root/'progress.json').write_text(json.dumps(status, indent=2), encoding='utf-8')


if __name__ == '__main__':
    main()
