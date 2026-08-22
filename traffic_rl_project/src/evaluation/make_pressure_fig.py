"""论文图：更强压力场景消融（target_gap 100→40m，协同增量随压力增大）。

数据来自 sweep_pressure_gap.py 的结果（M1 100m训练，评估不同 target_gap）。
输出：outputs/figures/fig_pressure_ablation.png
"""
import os
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

# 压力消融数据（sweep_pressure_gap.py 实测）
GAPS = [100.0, 80.0, 60.0, 50.0, 40.0]
M1_REWARD = [36446, 36477, 36507, 36524, 36542]
M3_REWARD = [-31151, -38630, -46191, -49772, -53046]
M3_COLL = [202, 226, 264, 285, 305]
M4_REWARD = [-33991, -41504, -49054, -52655, -55924]
COOP_GAIN = [m1 - m3 for m1, m3 in zip(M1_REWARD, M3_REWARD)]

os.makedirs('outputs/figures', exist_ok=True)

# 图1：reward vs target_gap（双轴：M1/M3/M4 reward + 协同增量）
fig, ax1 = plt.subplots(figsize=(9, 5.5))
ax1.plot(GAPS, M1_REWARD, 'o-', color='blue', linewidth=2, markersize=7, label='M1 (coop)')
ax1.plot(GAPS, M3_REWARD, 's--', color='red', linewidth=2, markersize=6, label='M3 (independent)')
ax1.plot(GAPS, M4_REWARD, '^--', color='purple', linewidth=2, markersize=6, label='M4 (rule heuristic)')
ax1.axhline(y=0, color='k', linestyle=':', alpha=0.5)
ax1.set_xlabel('Target inter-train gap (m)')
ax1.set_ylabel('Cumulative reward')
ax1.legend(loc='upper left')
ax1.grid(alpha=0.3)

# 协同增量（右轴）
ax2 = ax1.twinx()
ax2.plot(GAPS, COOP_GAIN, 'D-', color='green', linewidth=2.5, markersize=8,
         label='Cooperative gain (M1−M3)')
ax2.set_ylabel('Cooperative gain')
ax2.legend(loc='upper right')

plt.title('Stronger-pressure ablation: cooperative gain grows as gap shrinks (3-train)')
fig.tight_layout()
fig.savefig('outputs/figures/fig_pressure_ablation.png', dpi=150)
plt.close()
print('已生成 outputs/figures/fig_pressure_ablation.png')

# 图2：M3 追尾步数 vs target_gap
plt.figure(figsize=(9, 5))
plt.plot(GAPS, M3_COLL, 'o-', color='red', linewidth=2, markersize=7, label='M3 (independent)')
plt.plot(GAPS, [0]*len(GAPS), 's--', color='blue', linewidth=2, markersize=6, label='M1 (coop, always 0)')
plt.xlabel('Target inter-train gap (m)')
plt.ylabel('Rear-end collision steps')
plt.title('M3 collisions increase under pressure; M1 never collides')
plt.legend()
plt.grid(alpha=0.3)
plt.tight_layout()
plt.savefig('outputs/figures/fig_pressure_collision.png', dpi=150)
plt.close()
print('已生成 outputs/figures/fig_pressure_collision.png')
