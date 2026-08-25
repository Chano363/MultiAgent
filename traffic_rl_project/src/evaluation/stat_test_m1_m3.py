"""统计显著性检验：M1 vs M3 的 10-seed reward 差异（t-test + Wilcoxon）。

从 evaluate_m1_m3_long 复用 run_episode/make_env，随机化初态 10 seed，
比较 M1（MAPPO 协同）与 M3（独立）的 reward，报告 t-test p 值。
"""
import sys
import numpy as np
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))
sys.path.insert(0, str(Path(__file__).parent))
import evaluate_m1_m3_long as ev
from scipy import stats

CKPT = "outputs/checkpoints/mappo_fleet_best_cp_seed0_orig.pt"
N_SEED = 30
from src.algorithms.mappo_agent import MAPPOAgent

def get_rewards(mode):
    rws = []
    coll = []
    for s in range(N_SEED):
        if mode == 'm1':
            env = ev.make_env(65 / 3.6, hierarchical=True, adj_coef=0.1)
            agent = MAPPOAgent(num_drones=ev.NUM_TRAINS, obs_per_drone=11, act_per_drone=1, device='cpu')
            agent.load(CKPT)
            agent.policy.eval()
            r = ev.run_episode(env, agent, 'm1', s, True, True)
        else:
            # M3 = 同架构 δ=0（与论文 evaluate_m1_m3_long 的 m3 模式一致）
            env = ev.make_env(65 / 3.6, hierarchical=True, adj_coef=0.0)
            r = ev.run_episode(env, None, 'm3', s, True, True)
        rws.append(r['reward'])
        coll.append(r.get('collision_steps', r.get('rear_end_steps', 0)))
    return np.array(rws), np.array(coll)

print(f"== {N_SEED}-seed 随机化初态 ==")
m1, m1c = get_rewards('m1')
m3, m3c = get_rewards('m3')
print(f"M1: reward mean={m1.mean():.0f} std={m1.std():.0f}  追尾={m1c.mean():.1f}±{m1c.std():.1f}")
print(f"M3: reward mean={m3.mean():.0f} std={m3.std():.0f}  追尾={m3c.mean():.1f}±{m3c.std():.1f}")

# t-test（方差不齐时用 Welch）—— 比较均值
t, p = stats.ttest_ind(m1, m3, equal_var=False)
print(f"\nWelch t-test (均值): t={t:.3f}, p={p:.4f}, 显著(p<0.05)={'是' if p<0.05 else '否'}")

# Mann-Whitney U（非参数，均值/中位数）
U, p2 = stats.mannwhitneyu(m1, m3, alternative='two-sided')
print(f"Mann-Whitney U: U={U:.0f}, p={p2:.4f}, 显著(p<0.05)={'是' if p2<0.05 else '否'}")

# Levene 方差齐性检验（核心：稳健性 = 方差显著更小）
lev_stat, lev_p = stats.levene(m1, m3)
print(f"Levene 方差检验: F={lev_stat:.3f}, p={lev_p:.4f}, M1方差显著小于M3={'是' if lev_p<0.05 else '否'}")

# F-test 方差比（M3 方差 / M1 方差）
var_ratio = np.var(m3, ddof=1) / np.var(m1, ddof=1)
print(f"方差比 M3/M1 = {var_ratio:.1f}x")

# 追尾步数检验（M1 恒 0 vs M3 部分追尾）
print(f"\n== 追尾步数检验 ==")
t3, p3 = stats.ttest_ind(m1c, m3c, equal_var=False)
print(f"追尾 Welch t-test: t={t3:.3f}, p={p3:.4f}, 显著={'是' if p3<0.05 else '否'}")
U3, p4 = stats.mannwhitneyu(m1c, m3c, alternative='two-sided')
print(f"追尾 Mann-Whitney U: p={p4:.4f}, 显著={'是' if p4<0.05 else '否'}")
print(f"M1 追尾 seed 数: {(m1c>0).sum()}/{N_SEED}, M3 追尾 seed 数: {(m3c>0).sum()}/{N_SEED}")
