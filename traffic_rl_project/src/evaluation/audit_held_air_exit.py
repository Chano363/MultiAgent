"""Finish a bounded two-branch diagnostic without requiring manual polling.

Only reads completed archives and writes an audit; never changes controllers,
parameters or acceptance thresholds, and never adopts a candidate automatically.
"""
import argparse
import hashlib
import json
from pathlib import Path
import sys
import time

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from src.evaluation.compare_fleet_segments import read_segments, score
from src.evaluation.compare_air_allocation_cost import load


def completed(directory):
    names = ('result.json', 'metadata.json', 'trajectory.npz', 'telemetry.npz')
    if not all((directory/n).is_file() for n in names):
        return False
    try:
        return 'summary' in json.loads((directory/'result.json').read_text(encoding='utf-8'))
    except json.JSONDecodeError:
        return False  # A writer can still be closing result.json.


def air_cost(directory, indices):
    arrays = load(directory)
    power = np.maximum(0., -arrays['vehicle_air_force_n'][indices]
                       * arrays['vehicle_speeds_mps'][indices])
    return {
        'air_work_mj_by_train': (power.sum(axis=(0, 2))*.1/1e6).tolist(),
        'source_on_s_by_train': (arrays['ab_source_on'][indices]
            .reshape(len(indices), 3, -1).any(axis=2).sum(axis=0)*.1).tolist(),
        'head_displacement_m_by_train': (arrays['heads'][indices[-1]]
                                        - arrays['heads'][indices[0]]).tolist(),
    }


def source_edges(directory):
    arrays = load(directory)
    times = arrays['rows'][:, 0]
    on = arrays['ab_source_on'].reshape(len(times), 3, -1).any(axis=2)
    means = arrays['vehicle_speeds_mps'].mean(axis=2)*3.6
    result = []
    for j in range(3):
        indices = np.flatnonzero(on[1:, j] != on[:-1, j])+1
        result.append([{'time_s': float(times[i]), 'on': bool(on[i, j]),
                        'mean_kmh': float(means[i, j])} for i in indices])
    return result


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--baseline', type=Path, required=True)
    parser.add_argument('--candidate', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--document', type=Path, required=True)
    parser.add_argument('--timeout-s', type=float, default=14400.)
    args = parser.parse_args()
    if args.document.drive.upper() != 'D:':
        parser.error('User requires generated documents on D:')
    args.output.mkdir(parents=True, exist_ok=False)
    (args.output/'entry_source.py').write_bytes(Path(__file__).read_bytes())
    began = time.monotonic()
    while not all(completed(d) for d in (args.baseline, args.candidate)):
        if (args.output/'STOP').exists() or time.monotonic()-began > args.timeout_s:
            (args.output/'status.json').write_text(json.dumps({
                'status': 'stopped_waiting', 'scope': 'No simulation process was stopped'}),
                encoding='utf-8')
            return
        time.sleep(10.)
    a, ak, ah, ap = read_segments([args.baseline])
    b, bk, bh, bp = read_segments([args.candidate])
    summaries = []
    manifests = []
    for directory in (args.baseline, args.candidate):
        summaries.append(json.loads((directory/'result.json').read_text(
            encoding='utf-8'))['summary'])
        manifests.append(json.loads((directory/'metadata.json').read_text(
            encoding='utf-8'))['initial_fleet_manifest'])
    if ah != bh or manifests[0]['sha256'] != manifests[1]['sha256']:
        raise ValueError('Branches must share native model and exact initial state')
    if manifests[0]['numerical']['settings'] != manifests[1]['numerical']['settings']:
        raise ValueError('Numerical settings differ')
    shared, ai, bi = np.intersect1d(ak, bk, return_indices=True)
    if len(shared) < 2 or np.any(np.diff(shared) != 1):
        raise ValueError('Contiguous common samples required')
    result = {
        'scope': 'Common-window diagnostic audit; no automatic adoption or full-route claim',
        'window_s': [float(shared[0]/10), float(shared[-1]/10)],
        'samples': len(shared), 'initial_state_sha256': manifests[0]['sha256'],
        'baseline': score(a[ai], 100+5*16.6666111111),
        'candidate': score(b[bi], 100+5*16.6666111111),
        'baseline_air_cost': air_cost(args.baseline, ai),
        'candidate_air_cost': air_cost(args.candidate, bi),
        'full_branch_summaries': summaries,
        'source_edges_full_branch': {
            'baseline': source_edges(args.baseline),
            'candidate': source_edges(args.candidate)},
        'source_sha256': {**ap, **bp},
        'entry_sha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        'decision': 'Requires review of safety, gap and cycling together; production unchanged',
    }
    (args.output/'result.json').write_text(json.dumps(result, indent=2), encoding='utf-8')
    lines = ['# 尾列退出持压保速：自动对照结果', '',
             '本报告仅整理已完成数据，不自动采纳候选，不代表全程验收。', '',
             f"共同时间窗：{result['window_s']}秒；样本{len(shared)}个。", '']
    for label, title, summary in zip(('baseline', 'candidate'), ('原策略', '退出保速候选'), summaries):
        values = result[label]
        lines += [f'## {title}', '',
                  f"整支停止原因：{summary['stop_reason']}；末时刻：{summary['last_time_s']:.1f}秒。",
                  f"共同窗：车钩微步峰值{values['internal_peak_kn']:.3f} kN；"
                  f"车辆速度{values['min_vehicle_kmh']:.3f}—{values['max_vehicle_kmh']:.3f} km/h；"
                  f"新增安全接管{values['safety_event_count']}次。",
                  f"列距平均绝对误差{values['mean_absolute_gap_error_m']:.3f}米；"
                  f"平均列间速度极差{values['mean_speed_spread_kmh']:.3f} km/h。",
                  f"三列空气制动功(MJ)：{result[label+'_air_cost']['air_work_mj_by_train']}。",
                  f"三列源开启时间(s)：{result[label+'_air_cost']['source_on_s_by_train']}。", '']
    lines += ['空气制动功不是轮温；候选多出的100秒不能算作共同窗收益。',
              '若候选减少持压但增加列距误差，属于权衡，不能报告全面改善。',
              '本轮没有改变222秒、ED能力、1000 kN门槛或ATP。', '',
              f'完整来源、哈希、源切换时刻及独立分支摘要见：{args.output.resolve() / "result.json"}']
    args.document.parent.mkdir(parents=True, exist_ok=True)
    with args.document.open('x', encoding='utf-8') as stream:
        stream.write('\n'.join(lines)+'\n')
    print(json.dumps({'status': 'audit_completed', 'document': str(args.document)}), flush=True)


if __name__ == '__main__':
    main()
