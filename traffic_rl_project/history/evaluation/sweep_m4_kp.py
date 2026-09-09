"""扫描 M4 规则启发式协同的 kp/kd，找最优（公平对比 RL 协同 M1）。

M1 用 RL 学 coor_adj，M4 用规则（间距误差+速度差）。同架构（分层执行），
只差 coor_adj 来源。扫描 kp 找 M4 能到的最优性能，与 M1 (+33886) 对比。
"""
import sys
from pathlib import Path
import numpy as np
sys.path.append(str(Path(__file__).parent.parent.parent))
from src.evaluation import evaluate_m1_m3_long as ev


def eval_m4(kp, kd, n_seed=1):
    res = []
    for s in range(n_seed):
        env = ev.make_env(65.0 / 3.6, hierarchical=True, adj_coef=0.3)
        env._m4_kp = kp
        env._m4_kd = kd
        r = ev.run_episode(env, None, 'm4', s, deterministic=True)
        res.append(r)
    # 取第一个（确定性相同）
    r = res[0]
    return r


if __name__ == '__main__':
    print(f"{'kp':>8} {'kd':>8} {'reward':>10} {'coupler':>8} {'gap_min':>8} {'coll':>6}")
    for kp in [0.005, 0.01, 0.02, 0.05, 0.1, 0.2]:
        for kd in [0.0, 0.05]:
            r = eval_m4(kp, kd)
            print(f"{kp:>8} {kd:>8} {r['reward']:+10.0f} {r['coupler_peak']:>8.0f} "
                  f"{r['gap_min'] if r['gap_min'] is not None else float('nan'):>8.0f} {r['collision_steps']:>6}")
