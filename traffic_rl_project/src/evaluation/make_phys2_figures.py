"""【2026-08-31 完整从头训练后】M-MARL vs No-C 对比图 + 主对比图 + 汇总表（论文/PPT 用）。

输入：outputs/results_phys2/traj_{m1_full_seed0|m3_full}.csv
     （由 eval_phys2_m1_5seed.py --ckpt_dir outputs/checkpoints_full 生成）
     + outputs/results_full/train_history_cp_seed*.json（完整训练学习曲线）
输出：outputs/figures/fig_phys2_*.png（中文标签，CJK 字体）

【口径 2026-08-31】完整从头训练（checkpoints_full）5 seed：3/5 收敛（追尾 0，
reward +37342±430），2/5 未收敛（追尾 20/29 步）。轨迹图/主对比图用 3 个收敛
seed 的代表轨迹（seed0，+37902）与收敛均值；未收敛 seed 在汇总文本中如实披露。
【命名规范】方法统一为 M-MARL / No-C / DQN-fair / MPC；惰行(Coast)非贡献，不入图。
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
FULL_RES = Path('outputs/results_full')   # 完整从头训练（checkpoints_full）的学习曲线
FIG = Path('outputs/figures')
FIG.mkdir(parents=True, exist_ok=True)


def load(name):
    return pd.read_csv(RESULTS / f"traj_{name}.csv")


def main():
    m1 = load('m1_full_seed0')   # 完整训练收敛 seed（+37902，追尾 0）
    m3 = load('m3_full')         # No-C 无协同

    # ---------------- 图1：速度 / 间距 / 车钩力 轨迹对比 ----------------
    fig, axes = plt.subplots(3, 1, figsize=(10, 9), sharex=True)
    t = m1['step'] * 0.1 / 60.0  # 分钟

    ax = axes[0]
    ax.plot(t, m3['speed_mean'], color='tab:red', lw=1.2, label='No-C（无协同）')
    ax.plot(t, m1['speed_mean'], color='tab:blue', lw=1.4, label='M-MARL（本文）')
    ax.axhline(80, color='k', ls='--', lw=0.8); ax.axhline(40, color='k', ls='--', lw=0.8)
    ax.text(t.iloc[-1] * 0.02, 81.5, '限速 80', fontsize=8)
    ax.text(t.iloc[-1] * 0.02, 41.5, '限速 40', fontsize=8)
    ax.set_ylabel('速度 (km/h)')
    ax.legend(loc='upper right', fontsize=9)
    ax.set_title('朔黄线 3×万吨群组 长下坡循环制动：速度轨迹', fontsize=11)

    ax = axes[1]
    ax.plot(t, m3['gap_1'], color='tab:red', lw=1.0, label='No-C（无协同）')
    ax.plot(t, m1['gap_1'], color='tab:blue', lw=1.2, label='M-MARL（本文）')
    ax.axhline(0, color='k', ls='-', lw=0.8)
    ax.axhline(5, color='r', ls='--', lw=1.0)
    ax.text(t.iloc[-1] * 0.02, 6.5, '追尾阈值 5 m', fontsize=8, color='red')
    ax.set_ylabel('列1-列2 间距 (m)')
    ax.legend(loc='upper right', fontsize=9)
    ax.set_title('间距保持（M-MARL 守住间距；No-C 追尾穿透，见负值）', fontsize=11)

    ax = axes[2]
    ax.plot(t, m3['coupler_peak_kN'], color='tab:red', lw=1.0, label='No-C（无协同）')
    ax.plot(t, m1['coupler_peak_kN'], color='tab:blue', lw=1.2, label='M-MARL（本文）')
    ax.axhline(1000, color='r', ls='--', lw=1.0)
    ax.text(t.iloc[-1] * 0.02, 1010, '1000 kN 安全限值', fontsize=8, color='red')
    ax.set_ylabel('车钩力峰值 (kN)')
    ax.set_xlabel('时间 (min)')
    ax.legend(loc='upper right', fontsize=9)
    ax.set_ylim(0, 1200)
    ax.set_title('列内车钩力（M-MARL/No-C 均守 1000 kN 限值；M-MARL 由协同避免追尾急制动放大）',
                 fontsize=11)

    for ax in axes:
        ax.grid(alpha=0.3)
    fig.tight_layout()
    fig.savefig(FIG / 'fig_phys2_m1m3_trajectory.png', dpi=150)
    plt.close(fig)
    print("已生成 fig_phys2_m1m3_trajectory.png")

    # ---------------- 图2：学习曲线（5 seed，完整从头训练）----------------
    # 末阶段(3000步)偶发追尾崩塌回合，奖励累计惩罚至约-75万；此处截断至-30000
    # （仅可视化，原始值仍在 json 中如实保留），并以 best-checkpoint 协议评估。
    CLIP = -30000
    fig, ax = plt.subplots(figsize=(9, 4.5))
    for s in range(5):
        p = FULL_RES / f"train_history_cp_seed{s}.json"
        if not p.exists():
            continue
        h = json.loads(p.read_text(encoding='utf-8'))
        rw = np.clip(np.asarray(h['rewards'], dtype=float), CLIP, None)
        eps = np.arange(1, len(rw) + 1)
        ax.plot(eps, rw, alpha=0.25, lw=0.9)
        if len(rw) >= 10:
            ma = np.convolve(rw, np.ones(10) / 10, mode='valid')
            ax.plot(eps[9:], ma, lw=1.8, label=f'seed{s} (滑动平均)')
    ax.axhline(0, color='gray', lw=0.6, ls='--')
    ax.set_ylim(CLIP, 60000)
    # 三阶段起始线：300 步(ep1) → 1000 步(ep67) → 3000 步(ep133)
    for xb, lab in [(1, '300 步'), (67, '1000 步'), (133, '3000 步')]:
        ax.axvline(xb, color='gray', lw=0.7, ls=':')
        ax.text(xb + 1, ax.get_ylim()[1] * 0.92, lab, fontsize=8, color='dimgray')
    ax.set_xlabel('训练回合')
    ax.set_ylabel('回合奖励')
    ax.set_title('M-MARL 群组协同训练曲线（5 seed，300→1000→3000 渐进训练）\n'
                 '注：末阶段部分回合因追尾崩塌累计惩罚至约-75 万，图中截断至-30000，'
                 '评估采用 best-checkpoint 协议', fontsize=10.5)
    ax.legend(fontsize=8, ncol=5, loc='upper center', bbox_to_anchor=(0.5, -0.13),
              framealpha=0.9)
    ax.grid(alpha=0.3)
    fig.tight_layout()
    fig.subplots_adjust(bottom=0.20)
    fig.savefig(FIG / 'fig_phys2_learning_curve_5seed.png', dpi=150)
    plt.close(fig)
    print("已生成 fig_phys2_learning_curve_5seed.png")

    # ---------------- 图3：M-MARL 协同输出 δ 轨迹 ----------------
    fig, ax = plt.subplots(figsize=(10, 3.5))
    for i, col in enumerate(['adj_0', 'adj_1', 'adj_2']):
        ax.plot(t, m1[col], lw=1.0, label=f'列{i} 协同输出 δ')
    ax.axhline(0, color='gray', lw=0.6, ls='--')
    ax.set_xlabel('时间 (min)')
    ax.set_ylabel('协同调整 δ')
    ax.set_title('M-MARL 第2层协同输出（配合前列制动/缓解节奏）', fontsize=11)
    ax.legend(fontsize=8)
    ax.grid(alpha=0.3)
    fig.tight_layout()
    fig.savefig(FIG / 'fig_phys2_m1_delta.png', dpi=150)
    plt.close(fig)
    print("已生成 fig_phys2_m1_delta.png")

    # ---------------- 图4：主对比（回报 + 车钩力）----------------
    # M-MARL = 完整从头训练（checkpoints_full）3 收敛 seed 均值 +37342（3/5 收敛，未收敛 seed 如实披露）
    # No-C / DQN-fair / MPC = 基线（Rule/DQN-fair 新物理训练、MPC 模型驱动，均与 M1 检查点无关，
    # 沿用 outputs/phys2_full_comparison_20260830.txt 固定初态确定性，朔黄线 3000 步）
    methods = ['M-MARL\n(本文)', 'No-C\n(无协同)', 'DQN-fair', 'MPC']
    reward = [37342, 9791, -15215, -115622]
    coupler = [659, 543, 463, 1178]
    coll = [0, 69, 157, 0]

    fig, axes = plt.subplots(1, 2, figsize=(11, 4.6))
    x = np.arange(len(methods))
    colr_reward = ['#2d6a9f', '#c0504d', '#9a8fb5', '#b5893a']
    colr_coup = ['#2d6a9f', '#c0504d', '#9a8fb5', '#a5372f']

    ax = axes[0]
    bars = ax.bar(x, [r / 1000 for r in reward], 0.55, color=colr_reward)
    for b, v in zip(bars, reward):
        ax.text(b.get_x() + b.get_width() / 2, b.get_height() + 1,
                ('+%.1fk' % (v / 1000)) if v > 0 else ('%.1fk' % (v / 1000)),
                ha='center', fontsize=10)
    ax.axhline(0, color='k', lw=0.6)
    ax.set_xticks(x); ax.set_xticklabels(methods, fontsize=10)
    ax.set_ylabel('回报 (×10³)')
    ax.set_title('累计回报', fontsize=11)
    ax.grid(axis='y', alpha=0.3)
    for b, c in zip(bars, coll):
        if c > 0:
            # 正值柱：标注置于数值标签上方；负值柱：标注置于零线上方，避免与数值重叠
            yt = b.get_height() + 10 if b.get_height() >= 0 else 3
            ax.text(b.get_x() + b.get_width() / 2, yt, f'追尾{c}步', ha='center',
                    fontsize=8.5, color='#a5372f')
    ax.set_ylim(min(reward) / 1000 - 8, max(reward) / 1000 + 12)

    ax = axes[1]
    bars = ax.bar(x, coupler, 0.55, color=colr_coup)
    ax.axhline(1000, color='red', ls='--', lw=1.2)
    ax.text(0.02, 1015, '车钩力上限 1000 kN', fontsize=8.5, color='red')
    for b, v in zip(bars, coupler):
        ax.text(b.get_x() + b.get_width() / 2, b.get_height() + 15, '%d' % v,
                ha='center', fontsize=10)
    ax.set_xticks(x); ax.set_xticklabels(methods, fontsize=10)
    ax.set_ylim(0, 1350)
    ax.set_ylabel('峰值车钩力 (kN)')
    ax.set_title('峰值车钩力（MPC 超限）', fontsize=11)
    ax.grid(axis='y', alpha=0.3)

    fig.tight_layout()
    fig.savefig(FIG / 'fig_phys2_main_compare.png', dpi=150)
    plt.close(fig)
    print("已生成 fig_phys2_main_compare.png")

    # ---------------- 汇总表 ----------------
    # 完整从头训练（checkpoints_full）：3/5 seed 收敛（追尾 0），2/5 未收敛（追尾 20/29 步）。
    # 主行报 3 收敛 seed 均值±std；附完整 5 seed 均值供如实披露。
    rows = [
        ('M-MARL 群组协同（3 收敛 seed 均值）', '+37342±430', '0.0', '659', '175', '2.0'),
        ('M-MARL（完整 5 seed 均值，含未收敛）', '+30162±8884', '9.8', '633', '97', '1.4'),
        ('No-C 无协同（δ=0）', '+9791', '69', '543', '-45', '2.0'),
    ]
    md = ["| 方法 | 奖励 | 追尾步数 | 车钩力峰值(kN) | 最小间距(m) | 循环制动 |",
          "|:--|:--|:--|:--|:--|:--|"]
    for r in rows:
        md.append('| ' + ' | '.join(r) + ' |')
    md.append('')
    md.append('> 口径：完整从头训练（checkpoints_full）固定评估种子确定性评估，朔黄线 23.8km 3000 步。'
              '5 seed 中 3 个收敛（追尾 0，车钩力 659kN<1000），2 个未收敛（追尾 20/29 步，reward '
              '+21332/+17453），完整 5 seed 均值 +30162±8884。收敛 seed 相对 No-C 协同增量 +27551。')
    (RESULTS / 'summary_m1m3_phys2.md').write_text('\n'.join(md), encoding='utf-8')
    print("已生成 summary_m1m3_phys2.md")
    print('\n'.join(md))


if __name__ == '__main__':
    main()
