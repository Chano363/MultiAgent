"""论文/PPT 图：更强压力场景消融（target_gap 100→40m，协同增量随压力放大）。

数据：完整从头训练（checkpoints_full）固定初态实测：
  gap100 = M-MARL 3 收敛 seed 均值 +37342 / gap40 = +37382（本会话重测）。
命名规范：M-MARL（本文协同）/ No-C（无协同）；不含惰行(Coast)。
输出：outputs/figures/fig_pressure_ablation.png
"""
import os
import sys
from pathlib import Path
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

sys.path.append(str(Path(__file__).parent.parent.parent))
from src.utils.plot_style import setup_cjk_font

setup_cjk_font(verbose=False)

# 完整从头训练（checkpoints_full）实测（gap 100/40 两点）
GAPS = [100.0, 40.0]
MMARL_REWARD = [37342, 37382]
NOC_REWARD = [9791, -11137]
NOC_COLL = [69, 179]
COOP_GAIN = [m - n for m, n in zip(MMARL_REWARD, NOC_REWARD)]

os.makedirs('outputs/figures', exist_ok=True)

# 图1：reward vs target_gap（双轴：M-MARL/No-C reward + 协同增量）
fig, ax1 = plt.subplots(figsize=(9, 5.2))
ax1.plot(GAPS, MMARL_REWARD, 'o-', color='#2d6a9f', linewidth=2, markersize=8,
         label='M-MARL（协同，本文）')
ax1.plot(GAPS, NOC_REWARD, 's--', color='#c0504d', linewidth=2, markersize=7,
         label='No-C（无协同）')
ax1.axhline(y=0, color='k', linestyle=':', alpha=0.5)
ax1.set_xlabel('目标间距 (m)（越小 → 压力越大）')
ax1.set_ylabel('累计回报')
ax1.legend(loc='lower center', bbox_to_anchor=(0.26, 0.02), framealpha=0.95)
ax1.grid(alpha=0.3)
ax1.set_xticks(GAPS)

ax2 = ax1.twinx()
ax2.plot(GAPS, COOP_GAIN, 'D-', color='#4a8f4a', linewidth=2.5, markersize=8,
         label='协同增益 (M-MARL−No-C)')
for gx, gv in zip(GAPS, COOP_GAIN):
    ax2.annotate(f'+{gv / 1000:.1f}k', (gx, gv), textcoords='offset points',
                 xytext=(0, 10), ha='center', fontsize=9, color='#2f6b33',
                 fontweight='bold')
ax2.set_ylim(min(COOP_GAIN) - 5000, max(COOP_GAIN) + 9000)
ax2.set_ylabel('协同增益')
ax2.legend(loc='upper left', bbox_to_anchor=(0.02, 0.98), framealpha=0.95)

plt.title('压力消融：间距压缩 → 协同增益放大 (3 列)')
fig.tight_layout()
fig.savefig('outputs/figures/fig_pressure_ablation.png', dpi=150)
plt.close()
print('已生成 outputs/figures/fig_pressure_ablation.png')

# 图2：No-C 追尾步数 vs target_gap
fig, ax = plt.subplots(figsize=(9, 5))
ax.plot(GAPS, NOC_COLL, 'o-', color='#c0504d', linewidth=2, markersize=8,
        label='No-C（无协同）追尾步数')
ax.plot([GAPS[0], GAPS[1]], [0, 0], 's--', color='#2d6a9f', linewidth=2, markersize=8,
        label='M-MARL（协同，恒为 0)')
ax.set_xlabel('目标间距 (m)')
ax.set_ylabel('追尾步数')
ax.set_title('压力下 No-C 追尾增、M-MARL 恒 0 追尾')
ax.set_xticks(GAPS)
ax.legend()
ax.grid(alpha=0.3)
fig.tight_layout()
fig.savefig('outputs/figures/fig_pressure_collision.png', dpi=150)
plt.close()
print('已生成 outputs/figures/fig_pressure_collision.png')