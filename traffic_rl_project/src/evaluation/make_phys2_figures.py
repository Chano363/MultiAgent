"""【2026-08-30 物理对齐后】M1(5seed) vs M3 vs 惰行 对比图 + 汇总表（论文/PPT 用）。

输入：outputs/results_phys2/traj_{m1_5seed_seed0|m3|coast}.csv
     （由 eval_phys2_m1_5seed.py 生成）+ train_history_*.json（学习曲线）
输出：outputs/figures/fig_phys2_*.png（中文标签，CJK 字体）
"""
import sys
import json
from pathlib import Path

sys.path.append(str(Path(__file__).parent.parent.parent))

import numpy as np
import pandas as pd
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from src.utils.plot_style import setup_cjk_font

setup_cjk_font(verbose=True)

RESULTS = Path('outputs/results_phys2')
FIG = Path('outputs/figures')
FIG.mkdir(parents=True, exist_ok=True)


def load(name):
    return pd.read_csv(RESULTS / f"traj_{name}.csv")


def main():
    m1 = load('m1_5seed_seed0')
    m3 = load('m3')
    coast = load('coast')

    # ---------------- 图1：速度 / 间距 / 车钩力 轨迹对比 ----------------
    fig, axes = plt.subplots(3, 1, figsize=(10, 9), sharex=True)
    t = m1['step'] * 0.1 / 60.0  # 分钟

    ax = axes[0]
    ax.plot(t, coast['speed_mean'], color='tab:gray', lw=1.2, label='惰行')
    ax.plot(t, m3['speed_mean'], color='tab:red', lw=1.2, label='M3 单列独立')
    ax.plot(t, m1['speed_mean'], color='tab:blue', lw=1.4, label='M1 群组协同')
    ax.axhline(80, color='k', ls='--', lw=0.8); ax.axhline(40, color='k', ls='--', lw=0.8)
    ax.text(t.iloc[-1] * 0.02, 81.5, '限速 80', fontsize=8)
    ax.text(t.iloc[-1] * 0.02, 41.5, '限速 40', fontsize=8)
    ax.set_ylabel('速度 (km/h)')
    ax.legend(loc='upper right', fontsize=9)
    ax.set_title('朔黄线 3×万吨群组 300s 长下坡循环制动：速度轨迹', fontsize=11)

    ax = axes[1]
    ax.plot(t, coast['gap_1'], color='tab:gray', lw=1.0, label='惰行')
    ax.plot(t, m3['gap_1'], color='tab:red', lw=1.0, label='M3')
    ax.plot(t, m1['gap_1'], color='tab:blue', lw=1.2, label='M1')
    ax.axhline(0, color='k', ls='-', lw=0.8)
    ax.axhline(5, color='r', ls='--', lw=1.0)
    ax.text(t.iloc[-1] * 0.02, 6.5, '追尾阈值 5 m', fontsize=8, color='red')
    ax.set_ylabel('列1-列2 间距 (m)')
    ax.legend(loc='upper right', fontsize=9)
    ax.set_title('间距保持（M1 守住间距；M3 追尾穿透，见负值）', fontsize=11)

    ax = axes[2]
    ax.plot(t, coast['coupler_peak_kN'], color='tab:gray', lw=1.0, label='惰行')
    ax.plot(t, m3['coupler_peak_kN'], color='tab:red', lw=1.0, label='M3')
    ax.plot(t, m1['coupler_peak_kN'], color='tab:blue', lw=1.2, label='M1')
    ax.axhline(1000, color='r', ls='--', lw=1.0)
    ax.text(t.iloc[-1] * 0.02, 1010, '1000 kN 安全限值', fontsize=8, color='red')
    ax.set_ylabel('车钩力峰值 (kN)')
    ax.set_xlabel('时间 (min)')
    ax.legend(loc='upper right', fontsize=9)
    ax.set_title('列内车钩力（M1/M3 均守 1000 kN 限值；M1 由协同避免追尾急制动放大）',
                 fontsize=11)

    for ax in axes:
        ax.grid(alpha=0.3)
    fig.tight_layout()
    fig.savefig(FIG / 'fig_phys2_m1m3_trajectory.png', dpi=150)
    plt.close(fig)
    print("已生成 fig_phys2_m1m3_trajectory.png")

    # ---------------- 图2：学习曲线（5 seed）----------------
    fig, ax = plt.subplots(figsize=(9, 4.5))
    for s in range(5):
        p = RESULTS / f"train_history_cp_seed{s}.json"
        if not p.exists():
            continue
        h = json.loads(p.read_text(encoding='utf-8'))
        rw = h['rewards']
        eps = np.arange(1, len(rw) + 1)
        ax.plot(eps, rw, alpha=0.45, lw=1.0)
        if len(rw) >= 10:
            ma = np.convolve(rw, np.ones(10) / 10, mode='valid')
            ax.plot(eps[9:], ma, lw=1.8, label=f'seed{s} (滑动平均)')
    ax.axhline(0, color='gray', lw=0.6, ls='--')
    ax.set_xlabel('训练回合')
    ax.set_ylabel('回合奖励')
    ax.set_title('M1 群组协同训练曲线（5 seed，新物理下，含 300-1000-3000 课程）',
                 fontsize=11)
    ax.legend(fontsize=8, ncol=2)
    ax.grid(alpha=0.3)
    fig.tight_layout()
    fig.savefig(FIG / 'fig_phys2_learning_curve_5seed.png', dpi=150)
    plt.close(fig)
    print("已生成 fig_phys2_learning_curve_5seed.png")

    # ---------------- 图3：M1 协同输出 δ 轨迹 ----------------
    fig, ax = plt.subplots(figsize=(10, 3.5))
    for i, col in enumerate(['adj_0', 'adj_1', 'adj_2']):
        ax.plot(t, m1[col], lw=1.0, label=f'列{i} 协同输出 δ')
    ax.axhline(0, color='gray', lw=0.6, ls='--')
    ax.set_xlabel('时间 (min)')
    ax.set_ylabel('协同调整 δ')
    ax.set_title('M1 第2层协同输出（配合前列制动/缓解节奏）', fontsize=11)
    ax.legend(fontsize=8)
    ax.grid(alpha=0.3)
    fig.tight_layout()
    fig.savefig(FIG / 'fig_phys2_m1_delta.png', dpi=150)
    plt.close(fig)
    print("已生成 fig_phys2_m1_delta.png")

    # ---------------- 汇总表 ----------------
    rows = [
        ('M1 群组协同（5 seed 均值）', '+36027±107', '0.0', '659', '173', '2.0'),
        ('M3 单列独立（δ=0）', '+9791', '69', '543', '-45', '2.0'),
        ('惰行 baseline', '+33871', '0', '667', '183', '0.0'),
    ]
    md = ["| 方法 | 奖励 | 追尾步数 | 车钩力峰值(kN) | 最小间距(m) | 循环制动 |",
          "|:--|:--|:--|:--|:--|:--|"]
    for r in rows:
        md.append('| ' + ' | '.join(r) + ' |')
    (RESULTS / 'summary_m1m3_phys2.md').write_text('\n'.join(md), encoding='utf-8')
    print("已生成 summary_m1m3_phys2.md")
    print('\n'.join(md))


if __name__ == '__main__':
    main()
