"""从 `scripts/dump_eval_traj.py` 归档的时程 npz 画对比曲线（数据与绘图分离）。

只读已归档 npz、不跑仿真（生图规范）。默认取每个 tag **最新**的归档目录。

落盘：图 → 策展目录 `outputs/sim_validation/figures/对比曲线/`（允许覆盖）。

用法（Windows base Python 即可）：
    python scripts/plot_eval_traj.py --series "D-Rule=m0_rule_53km" --out rule_53km
"""
import argparse
import sys
from pathlib import Path

import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

ROOT = Path(__file__).resolve().parents[1]
ARCHIVE_ROOT = ROOT / 'outputs' / 'results' / 'decompose'
OUT_DIR = ROOT / 'outputs' / 'sim_validation' / 'figures' / '对比曲线'

plt.rcParams.update({
    'font.family': 'DejaVu Sans', 'font.size': 10,
    'axes.linewidth': 0.8, 'axes.edgecolor': '#333333',
    'xtick.direction': 'out', 'ytick.direction': 'out',
})
COLORS = ['#2b4c7e', '#c0642b', '#3d7a4f', '#8a3d10']


def _latest_npz(tag):
    hits = sorted(ARCHIVE_ROOT.glob(f'traj_{tag}_*/traj_{tag}.npz'))
    if not hits:
        raise FileNotFoundError(f'未找到归档 traj_{tag}_*/traj_{tag}.npz')
    return hits[-1]


def main():
    ap = argparse.ArgumentParser(description='画评估时程对比曲线（复用归档，不重跑）')
    ap.add_argument('--series', action='append', required=True,
                    help='label=tag，可重复，如 "D-Rule=m0_rule_53km"')
    ap.add_argument('--out', required=True, help='输出文件名（不含扩展名）')
    ap.add_argument('--title', default='')
    args = ap.parse_args()

    series = []
    for s in args.series:
        label, _, tag = s.partition('=')
        series.append((label or tag, np.load(_latest_npz(tag))))

    fig, (ax1, ax2, ax3) = plt.subplots(
        3, 1, figsize=(10, 8.4), sharex=True,
        gridspec_kw={'height_ratios': [1.15, 1.15, 1], 'hspace': 0.12})

    ax1.axhspan(40.0, 80.0, color='#d9e4f0', alpha=0.5, zorder=0)
    for k, (label, d) in enumerate(series):
        c = COLORS[k % len(COLORS)]
        t = d['t_s'] / 3600.0
        sp = d['speed_kmh']
        ax1.plot(t, sp[:, 0], color=c, lw=1.2, label=label)
        ax2.plot(t, d['coupler_peak_kN'].max(axis=1), color=c, lw=1.2, label=label)
        ax3.plot(t, d['gap_err_mean_m'], color=c, lw=1.2, label=label)

    ax1.set_ylabel('Speed (km/h)')
    ax1.set_ylim(0, max(100.0, float(max(d['speed_kmh'].max() for _, d in series)) + 10))
    ax1.text(0.995, 0.5, 'allowed band 40–80 km/h', transform=ax1.transAxes,
             ha='right', va='center', fontsize=8.5, color='#4a5a6a')

    ax2.axhline(1000.0, color='#a5281a', lw=0.9, ls='--')
    ax2.set_ylabel('Coupler interface force peak (kN)')
    ax2.text(0.995, 1000.0, ' limit 1000 kN', transform=ax2.get_yaxis_transform(),
             ha='right', va='bottom', fontsize=8.5, color='#a5281a')

    ax3.set_ylabel('Mean gap error (m)')
    ax3.set_xlabel('Time (h)')

    for ax in (ax1, ax2, ax3):
        ax.grid(alpha=0.18, ls='-', lw=0.5)
        ax.tick_params(top=False, right=False)
    ax1.legend(fontsize=9, loc='upper right', frameon=False)
    if args.title:
        ax1.set_title(args.title, fontsize=11.5)

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    out = OUT_DIR / f'{args.out}.png'
    fig.savefig(out, dpi=200, bbox_inches='tight')
    plt.close(fig)
    print(f'已生成 {out}')


if __name__ == '__main__':
    main()
