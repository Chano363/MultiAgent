"""Earlier intervention test followed by same-window scoring, never adoption."""
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import time


def main():
    base = Path('outputs/sim_validation/phys_validation')
    root = base/'fleet_early_shared_gap_20261027_round133'
    root.mkdir(parents=True, exist_ok=False)
    state = base/'fleet_preview_shared2005s_20261026_round115'
    baseline = base/'fleet_leader_prerelease55_20261027_round116'
    candidate = root/'run'
    document = Path('D:/Codex/Documents/Train/controller_takeover_20261017/'
                    '第二列提前介入_116秒同工况对照_20261027.md')
    (root/'entry_source.py').write_bytes(Path(__file__).read_bytes())
    result = dict(status='running', scope='Earlier activation of unchanged bounded gap allocation; '
                  'not full-route acceptance or a production change',
                  state=str(state), baseline=str(baseline), candidate=str(candidate),
                  source_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest())
    began = time.monotonic()

    def save():
        result['wall_s'] = time.monotonic()-began
        (root/'status.json').write_text(json.dumps(result, indent=2), encoding='utf-8')

    save()
    try:
        subprocess.run([sys.executable, '-u', 'src/evaluation/diagnose_shared_gap_balance.py',
            '--state-dir', str(state), '--output', str(candidate), '--steps', '1161'], check=True)
        manifests = [json.loads((p/'metadata.json').read_text(encoding='utf-8'))
                     ['initial_fleet_manifest'] for p in (baseline, candidate)]
        if manifests[0]['sha256'] != manifests[1]['sha256']:
            raise ValueError('Branches do not share exact initial state')
        subprocess.run([sys.executable, 'src/evaluation/compare_fleet_segments.py',
            '--baseline', str(baseline), '--candidate', str(candidate),
            '--reference-gap-m', '183.33305555555555',
            '--output', str(root/'comparison.json')], check=True)
        subprocess.run([sys.executable, 'src/evaluation/compare_air_allocation_cost.py',
            '--baseline', str(baseline), '--candidate', str(candidate),
            '--output', str(root/'air_cost.json')], check=True)
        comparison = json.loads((root/'comparison.json').read_text(encoding='utf-8'))
        cost = json.loads((root/'air_cost.json').read_text(encoding='utf-8'))
        summary = json.loads((candidate/'result.json').read_text(encoding='utf-8'))['summary']
        result.update(status='scored_requires_review', candidate_stop_reason=summary['stop_reason'],
                      candidate_last_time_s=summary['last_time_s'])
        lines = ['# 第二列提前介入：同工况局部对照', '',
                 '从2005秒完整状态提前启用既有第二列列距分配，无新增增益或物理参数。',
                 '原基准来自round116，候选来自round133/run，校验起点SHA一致。',
                 f"共同时间窗：{comparison['window_s']}秒；样本数：{comparison['samples']}。",
                 f"候选停止原因：{summary['stop_reason']}。若提前失败，指标只覆盖共同前缀。", '',
                 '| 指标 | 原策略 | 候选 |', '|---|---:|---:|']
        for key, label in [('internal_peak_kn', '接受微步峰值/kN'),
                           ('min_vehicle_kmh', '最低车辆速度/(km/h)'),
                           ('max_vehicle_kmh', '最高车辆速度/(km/h)'),
                           ('safety_event_count', '新增安全接管/次'),
                           ('mean_absolute_gap_error_m', '列距平均绝对误差/m'),
                           ('mean_speed_spread_kmh', '平均列间均速极差/(km/h)')]:
            lines.append(f"| {label} | {comparison['baseline'][key]:.4f} | "
                         f"{comparison['candidate'][key]:.4f} |")
        for label, title in [('baseline', '原策略'), ('candidate', '候选')]:
            lines += ['', f"{title}末态列距：{comparison[label]['end_gaps_m']}米。",
                      f"{title}空气制动功：{cost[label]['air_mechanical_work_mj_by_train']} MJ。"]
        lines += ['', '安全、列距、速度差和机械制动功共同评估；不自动采纳候选。',
                  '空气功不是轮温；局部成功不代表完整循环或全程验收。',
                  '222秒、1000 kN、气动模型和ATP不变；没有运行强化学习训练。',
                  f'完整来源与SHA：{root.resolve()}。']
        document.parent.mkdir(parents=True, exist_ok=True)
        with document.open('x', encoding='utf-8') as stream:
            stream.write('\n'.join(lines)+'\n')
        result['document'] = str(document)
    except BaseException as exc:
        result.update(status='failed', error=repr(exc))
        raise
    finally:
        save()
    print(json.dumps(result), flush=True)


if __name__ == '__main__':
    main()
