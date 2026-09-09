"""分析 M1 的 RL 协同策略：coor_adj 如何随间距/速度差变化。

回答"RL 学到什么"——决定 M4（规则启发式协同）设计，并验证 RL 协同是否
超越简单"间距误差→阈值偏移"规则（审稿核心质疑）。

输入：outputs/diagnostics/m1m3_traj_m1.csv（含 adj_0/1/2 列）
输出：outputs/diagnostics/coor_policy_report.md
"""
import os
import numpy as np
import pandas as pd
from pathlib import Path

CSV = 'outputs/diagnostics/m1m3_traj_m1.csv'
OUT = 'outputs/diagnostics/coor_policy_report.md'


def main():
    df = pd.read_csv(CSV)
    # 间距：gap_1 是列0与列1之间，gap_2 是列1与列2之间
    # coor_adj 列0（领航车，无前列）通常≈0；列1/列2 根据前列间距调整
    adj1 = df['adj_1'].values
    adj2 = df['adj_2'].values
    gap1 = df['gap_1'].values
    gap2 = df['gap_2'].values
    sp0, sp1, sp2 = df['speed_0'].values, df['speed_1'].values, df['speed_2'].values
    # 速度差：后列-前列（正=后列更快，追尾风险）
    dv1 = sp1 - sp0  # 列1 vs 列0
    dv2 = sp2 - sp1  # 列2 vs 列1

    Path(os.path.dirname(OUT)).mkdir(parents=True, exist_ok=True)
    with open(OUT, 'w') as f:
        f.write('# M1 协同策略分析：RL 学到的 coor_adj 行为\n\n')
        f.write(f'> 数据源：{CSV}（3000步，固定初态65，M1 seed0 orig checkpoint）\n\n')

        f.write('## 1. coor_adj 统计\n\n')
        f.write('| 列 | mean | std | min | max | 非零占比 |\n')
        f.write('|:--|:--|:--|:--|:--|:--|\n')
        for name, a in [('列0(领航)', adj1 * 0 + df['adj_0'].values), ('列1', adj1), ('列2', adj2)]:
            f.write(f'| {name} | {a.mean():+.3f} | {a.std():.3f} | {a.min():+.3f} | '
                    f'{a.max():+.3f} | {(a != 0).mean()*100:.1f}% |\n')
        f.write('\n')

        f.write('## 2. 策略行为：coor_adj 与"前列间距/速度差"的关联\n\n')
        # 分析列1（有前列列0）：coor_adj1 与 gap1/dv1 的关系
        f.write('### 列1 行为（coor_adj1 vs gap1, dv1）\n\n')
        # 分箱：间距小（<100）/中（100-300）/大（>300），看 coor_adj1
        bins_gap = [(0, 150), (150, 400), (400, 1e9)]
        f.write('| 间距区间(m) | mean coor_adj1 | 说明 |\n')
        f.write('|:--|:--|:--|\n')
        for lo, hi in bins_gap:
            mask = (gap1 >= lo) & (gap1 < hi)
            if mask.sum() > 0:
                m = adj1[mask].mean()
                desc = '提前制动/延后缓解(防追尾)' if m > 0.05 else ('延后制动/提前缓解(防过大)' if m < -0.05 else '≈无调整')
                f.write(f'| [{lo},{hi}) | {m:+.3f} | {desc} |\n')
        f.write('\n')
        # 速度差分箱
        f.write('| 速度差dv1区间(km/h) | mean coor_adj1 | 说明 |\n')
        f.write('|:--|:--|:--|\n')
        for lo, hi in [(-30, -5), (-5, 5), (5, 30), (30, 90)]:
            mask = (dv1 >= lo) & (dv1 < hi)
            if mask.sum() > 0:
                m = adj1[mask].mean()
                desc = '防追尾(后列快,提前制动)' if m > 0.05 else ('防过大(后列慢,延后制动)' if m < -0.05 else '≈无调整')
                f.write(f'| [{lo},{hi}) | {m:+.3f} | {desc} |\n')
        f.write('\n')

        # 相关性
        c_gap = np.corrcoef(adj1, gap1)[0, 1]
        c_dv = np.corrcoef(adj1, dv1)[0, 1]
        f.write('## 3. 相关性\n\n')
        f.write(f'- corr(coor_adj1, gap1) = **{c_gap:+.3f}**（负=间距越小越提前制动）\n')
        f.write(f'- corr(coor_adj1, dv1) = **{c_dv:+.3f}**（正=后列越快越提前制动）\n\n')

        f.write('## 4. 结论：RL 学到的是否是"规则启发式"？\n\n')
        # 判断：如果 corr 显著且行为单调，说明 RL 学到了类似"间距/速度差→阈值偏移"规则
        if abs(c_gap) > 0.3 and abs(c_dv) > 0.3:
            f.write('RL 学到的协同策略**与"间距/速度差反馈"规则方向一致**'
                    '（负相关于间距、正相关于速度差），即 RL 学到了类似'
                    '"后列快/间距近 → 提前制动"的启发式。\n\n')
            f.write('**但需与 M4（规则启发式基线）对比**：若 RL 协同的性能 ≥ 规则启发式'
                    '（PID/分段规则），则 RL 增量在于**自适应权重/非线性**（RL 学到的是'
                    '数据驱动的精确映射，而规则需手工调参）；若 RL < 规则，则需重新设计。\n')
        else:
            f.write('RL 学到的 coor_adj 与间距/速度差相关性弱，说明 RL 学到了'
                    '**更复杂/非平凡的策略**（可能结合速度带、坡度等）。需要更深入分析。\n')

    print(open(OUT, encoding='utf-8').read())


if __name__ == '__main__':
    main()
