"""论文 Fig.1：最终分层架构示意图（规则循环制动 + RL 阈值协同 + 车钩力安全层）。

用 matplotlib 绘制流程框图，展示两层分层结构如何协同。
输出：outputs/figures/fig1_architecture.png
"""
import os
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.patches import FancyBboxPatch, FancyArrowPatch


def box(ax, x, y, w, h, text, fc, ec='k', fs=10, lw=1.5, tcol='k'):
    p = FancyBboxPatch((x, y), w, h, boxstyle='round,pad=0.03',
                       fc=fc, ec=ec, lw=lw, alpha=0.95)
    ax.add_patch(p)
    ax.text(x + w / 2, y + h / 2, text, ha='center', va='center', fontsize=fs,
            color=tcol, wrap=True)


def arrow(ax, x1, y1, x2, y2, color='k', lw=2.0, style='-|>'):
    a = FancyArrowPatch((x1, y1), (x2, y2), arrowstyle=style, mutation_scale=18,
                        color=color, lw=lw)
    ax.add_patch(a)


def main():
    fig, ax = plt.subplots(figsize=(11, 7))
    ax.set_xlim(0, 10)
    ax.set_ylim(0, 7)
    ax.axis('off')

    # ===== 第2层：群组协同（Platoon Level, MAPPO）=====
    box(ax, 0.3, 5.4, 3.4, 1.3, 'Layer 2 — Platoon Level\nMAPPO (3 agents)\ncooperative threshold adjustment\n$c_{adj} \\in [-1,1]$',
        '#dbe8fb', lw=2, fs=10)
    # 三列智能体
    for i, x in enumerate([0.7, 1.8, 2.9]):
        ax.text(x, 4.85, f'Train {i}', ha='center', fontsize=9, color='navy')
    arrow(ax, 2.0, 5.4, 2.0, 4.6, color='navy', lw=2)

    # ===== 阈值偏移 → 第1层 =====
    box(ax, 0.3, 3.4, 3.4, 0.9, 'threshold offsets\n$v_{max}^{adj}, v_{min}^{adj}$ (lim ±5 km/h)',
        '#e8f0e3', fs=9)
    arrow(ax, 2.0, 3.4, 2.0, 3.15, color='teal', lw=2.5)

    # ===== 第1层：规则循环制动（Coupler Level）=====
    box(ax, 0.3, 2.0, 3.4, 1.0, 'Layer 1 — Coupler Level\nRule-based cyclic braking\n(brake if v≥v_max, release if v≤v_min)',
        '#fdeeda', lw=2, fs=10)
    # 车钩力安全层
    box(ax, 0.3, 0.6, 3.4, 0.9, 'Coupler-force safety layer\nenforce |F| ≤ 1000 kN',
        '#f9d7d7', lw=2, fs=10)
    arrow(ax, 2.0, 2.0, 2.0, 1.55, color='red', lw=2.5)

    # ===== 列车物理 =====
    box(ax, 0.3, -0.4, 3.4, 0.7, 'Train physics (10kt, 100 wagons,\nShuozhou −10.9‰ long downhill)',
        '#dcdcdc', fs=9)
    arrow(ax, 2.0, 0.6, 2.0, 0.35, color='k', lw=2)

    # ===== 反馈回路（右侧）=====
    # 状态/奖励反馈
    box(ax, 5.6, 3.4, 3.8, 1.0, 'State / reward feedback:\nspeed, gap error, coupler force,\nprev-train speed, tail grade',
        '#fdf6c9', fs=9)
    arrow(ax, 5.6, 3.9, 3.7, 5.4, color='purple', lw=2, style='-|>')
    arrow(ax, 3.7, 2.5, 5.6, 3.4, color='gray', lw=1.5, style='-|>')

    # 车钩力观测
    box(ax, 5.6, 0.6, 3.8, 1.0, 'Coupler force observation\n(feeds Layer 2 state/reward)',
        '#f1e3f7', fs=9)
    arrow(ax, 3.7, 1.05, 5.6, 1.1, color='magenta', lw=1.8, style='-|>')

    # ===== 标题/标注 =====
    ax.text(5, 6.75, 'Proposed hierarchical framework: rule-based cyclic braking (micro)\n'
                     '+ RL cooperative threshold adjustment (macro)',
            ha='center', fontsize=12, weight='bold')

    ax.text(5, -0.85, 'Multi-train virtually-coupled platoon keeps inter-train gap (100 m target)\n'
                      'and each train stays within coupler-force limit (1000 kN).',
            ha='center', fontsize=9, style='italic', color='gray')

    os.makedirs('outputs/figures', exist_ok=True)
    out = 'outputs/figures/fig1_architecture.png'
    plt.tight_layout()
    plt.savefig(out, dpi=150, bbox_inches='tight')
    plt.close()
    print(f'Fig.1 架构图已生成: {out}')


if __name__ == '__main__':
    main()
