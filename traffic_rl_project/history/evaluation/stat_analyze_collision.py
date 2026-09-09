"""分析 50-seed 追尾数据：Fisher 精确检验（追尾比例差异）+ 追尾步数检验。"""
import numpy as np
from pathlib import Path
from scipy import stats

def load(p):
    return np.array([int(x) for x in Path(p).read_text().split() if x.strip()], dtype=float)

m1 = load("outputs/diagnostics/m1_coll.txt")
m3 = load("outputs/diagnostics/m3_coll.txt")
print(f"加载 seed 数: M1={len(m1)}, M3={len(m3)}")

# 追尾比例（collision > 0）
m1_coll = (m1 > 0).sum()
m3_coll = (m3 > 0).sum()
print(f"\nM1 追尾: {m1_coll}/{len(m1)} = {100*m1_coll/len(m1):.0f}%")
print(f"M3 追尾: {m3_coll}/{len(m3)} = {100*m3_coll/len(m3):.0f}%")

# Fisher 精确检验（2x2 列联表：方法 x 是否追尾）
table = [[m1_coll, len(m1)-m1_coll],
         [m3_coll, len(m3)-m3_coll]]
odds, p_fisher = stats.fisher_exact(table)
print(f"\nFisher 精确检验: odds={odds:.2f}, p={p_fisher:.6f}, 显著={'是' if p_fisher<0.05 else '否'}")

# 卡方检验
chi2, p_chi, dof, _ = stats.chi2_contingency(table)
print(f"卡方检验: chi2={chi2:.2f}, p={p_chi:.6f}, 显著={'是' if p_chi<0.05 else '否'}")

# 追尾步数均值检验
print(f"\n追尾步数 mean±std: M1={m1.mean():.1f}±{m1.std():.1f}  M3={m3.mean():.1f}±{m3.std():.1f}")
t, p_t = stats.ttest_ind(m1, m3, equal_var=False)
print(f"追尾步数 Welch t-test: p={p_t:.6f}, 显著={'是' if p_t<0.05 else '否'}")
U, p_u = stats.mannwhitneyu(m1, m3, alternative='two-sided')
print(f"追尾步数 Mann-Whitney: p={p_u:.6f}, 显著={'是' if p_u<0.05 else '否'}")

# 保存分析结果
with open("outputs/diagnostics/collision_stats_50seed.txt", "w") as f:
    f.write(f"M1 collision seeds: {m1_coll}/{len(m1)}\n")
    f.write(f"M3 collision seeds: {m3_coll}/{len(m3)}\n")
    f.write(f"Fisher p: {p_fisher:.6f}\n")
    f.write(f"Chi2 p: {p_chi:.6f}\n")
    f.write(f"collision mean: M1={m1.mean():.1f} M3={m3.mean():.1f}\n")
print("\n结果已保存到 outputs/diagnostics/collision_stats_50seed.txt")
