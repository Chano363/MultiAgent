"""Plot two completed same-state forecasts; do not run or modify physics."""
import argparse
import hashlib
import json
from pathlib import Path

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--baseline', type=Path, required=True)
    parser.add_argument('--candidate', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    results = [json.loads((p/'result.json').read_text(encoding='utf-8'))
               for p in (args.baseline, args.candidate)]
    if results[0]['metadata']['native_state_manifest'] != results[1]['metadata']['native_state_manifest']:
        raise ValueError('Comparison requires identical initial state')
    plt.rcParams['font.sans-serif'] = ['Microsoft YaHei']
    plt.rcParams['axes.unicode_minus'] = False
    fig, axes = plt.subplots(4, 1, figsize=(11, 10), sharex=True)
    provenance = {}
    traces = []
    ready_time = None
    for path, label, color in [(args.baseline, '原候选：持续25%限制', '#d67936'),
                               (args.candidate, '修正候选：建压后缓慢恢复电制动', '#2478a5')]:
        with np.load(path/'balanced.npz', allow_pickle=False) as data:
            rows = data['rows'].copy()
        with np.load(path/'interface_trace.npz', allow_pickle=False) as data:
            t = data['elapsed_s'].copy()
            force = data['force_n'].copy()
            ready = np.flatnonzero((data['effective_pressure_coefficient'] >= 1-1e-12).all(axis=1))
        if len(ready):
            ready_time = float(t[ready[0]])
        traces.append(rows)
        axes[0].plot(rows[:, 0], rows[:, 3]*3.6, label=label, color=color)
        axes[1].plot(rows[1:, 0], np.diff(rows[:, 3])/np.diff(rows[:, 0]), color=color)
        axes[2].step(rows[:, 0], rows[:, 4], where='post', color=color, alpha=.7)
        axes[3].plot(t, np.abs(force).max(axis=1)/1000, color=color)
        for name in ('balanced.npz', 'interface_trace.npz', 'result.json', 'controller_source.py'):
            provenance[str(path/name)] = hashlib.sha256((path/name).read_bytes()).hexdigest()
    np.testing.assert_array_equal(traces[0][:, 0], traces[1][:, 0])
    for ax in axes:
        ax.grid(alpha=.2)
        if ready_time is not None:
            ax.axvline(ready_time, ls=':', color='#777', lw=1)
        ax.set_xlim(traces[0][0, 0], traces[0][-1, 0])
    axes[0].legend(fontsize=9)
    axes[0].set_ylabel('全列平均速度（km/h）')
    axes[1].set_ylabel('平均速度变化率（m/s²）')
    axes[1].axhline(0, color='#777', lw=.8)
    axes[2].set_ylabel('空气制动请求\n（模型编码）')
    axes[2].set_yticks([-.05, 0], labels=['50 kPa', '无制动请求'])
    axes[3].set_ylabel('最大断面力（kN）')
    axes[3].axhline(1000, ls='--', color='#aa3333', label='1000 kN目标')
    axes[3].legend()
    axes[3].set_xlabel('窗口内时间（s）')
    fig.suptitle('电制动恢复修正：同起点100秒对照（预测分支，非完整循环）', fontsize=14)
    fig.text(.5, .935, '竖虚线：尾车当前档位制动力建立；不代表副风缸充风完成', ha='center', fontsize=10)
    fig.tight_layout(rect=(0, .01, 1, .925))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(args.output, dpi=160)
    plt.close(fig)
    args.output.with_suffix('.json').write_text(json.dumps(
        {'source_sha256': provenance, 'simulator_rerun_by_plot': False,
         'scope': 'same-state copied forecasts, not cold/full-route acceptance'},
        ensure_ascii=False, indent=2), encoding='utf-8')
    print(args.output)


if __name__ == '__main__':
    main()
