"""【2026-08-31 完整从头训练后】规模扩展 3列 vs 5列 汇总图（M-MARL 零样本扩列 对照 No-C）。

输入：outputs/results_phys2/summary_5train_full.md（5列 checkpoints_full 随机初速数据）
  + 3列健壮性数据（summary_robust_full.md，checkpoints_full 随机初速，口径一致）。
输出：outputs/figures/fig_5train_summary.png（中文标签，无 Coast，无 M1/M3）
"""
import sys
from pathlib import Path


import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from src.utils.plot_style import setup_cjk_font

setup_cjk_font(verbose=False)

MD = Path('outputs/results_phys2/summary_5train_full.md')
FIG = Path('outputs/figures')
FIG.mkdir(parents=True, exist_ok=True)

# 3列健壮性（checkpoints_full 随机初速，2026-08-31 实测）
r3 = {'m': 36246, 'nc': 32291}
c3 = {'m': 0.0, 'nc': 28.2}


def parse_5col():
    """解析 5列 md 表 → {label: reward, collision}"""
    txt = MD.read_text(encoding='utf-8')
    out = {}
    for line in txt.splitlines():
        if not line.startswith('| 5 列'):
            continue
        cells = [c.strip() for c in line.split('|')]
        label = cells[2]
        key = 'm' if 'M-MARL' in label else 'nc'
        out[key] = {
            'reward': float(cells[3].replace('+', '').replace(',', '')),
            'coll': float(cells[4]),
            'peak': float(cells[5]),
            'gap': float(cells[6]),
        }
    return out


def main():
    f5 = parse_5col()
    labels = ['3 列', '5 列\n(零样本扩列)']

    reward_m = [r3['m'], f5['m']['reward']]
    reward_nc = [r3['nc'], f5['nc']['reward']]
    gain = [reward_m[i] - reward_nc[i] for i in range(2)]
    coll_nc = [c3['nc'], f5['nc']['coll']]

    ymax = max(reward_m + reward_nc) / 1000
    fig, ax1 = plt.subplots(figsize=(8.6, 5.0))
    x = np.arange(2)
    w = 0.26
    b1 = ax1.bar(x - w, [g / 1000 for g in reward_m], w, color='#2d6a9f', label='M-MARL（协同）')
    b2 = ax1.bar(x, [g / 1000 for g in reward_nc], w, color='#c0504d', label='No-C（无协同）')
    for bb, vals in zip([b1, b2], [reward_m, reward_nc]):
        for b_, v in zip(bb, vals):
            ax1.text(b_.get_x() + b_.get_width() / 2, b_.get_height() + 1.2,
                     ('+%.1fk' % (v / 1000)) if v > 0 else ('%.1fk' % (v / 1000)),
                     ha='center', fontsize=9.5)
    # 安全违约标注（列距<5 m）：置于两柱最高值上方（No-C 两列均 28 步，M-MARL 恒 0）
    # 【口径 2026-10】弃用自造词"追尾"，统一文献口径"安全违约"。
    for i, c in enumerate(coll_nc):
        if c > 0:
            ax1.text(x[i], max(reward_nc[i], reward_m[i]) / 1000 + 4.2,
                     f'No-C 安全违约 {c:.0f} 步', ha='center', fontsize=8.5, color='#a5372f')
    ax1.set_xticks(x); ax1.set_xticklabels(labels, fontsize=11)
    ax1.set_ylabel('累计回报 (×10³)')
    ax1.set_ylim(0, ymax + 8)
    ax1.set_title('规模扩展：3 列 → 5 列（M-MARL 共享策略零样本扩列，朔黄线）', fontsize=11)
    ax1.grid(axis='y', alpha=0.3)
    ax1.legend(loc='upper right', fontsize=9)

    ax2 = ax1.twinx()
    ax2.plot(x, [g / 1000 for g in gain], 'D-', color='#4a8f4a', lw=2.2, ms=7,
             label='协同增益 (M-MARL−No-C)')
    ax2.set_ylim(0, max(gain) / 1000 + 4)
    for i, g in enumerate(gain):
        ax2.text(x[i], g / 1000 + 1.2, '+%.1fk' % (g / 1000), ha='center',
                 fontsize=9, color='#2f6b33', fontweight='bold')
    ax2.set_ylabel('协同增益 (×10³)')
    ax2.legend(loc='lower right', fontsize=9)

    fig.tight_layout()
    fig.savefig(FIG / 'fig_5train_summary.png', dpi=150)
    plt.close(fig)
    print(f"已生成 fig_5train_summary.png  (gain={gain})")
    print(f"  5列 M-MARL coll={f5['m']['coll']}, No-C coll={f5['nc']['coll']}")


if __name__ == '__main__':
    main()
