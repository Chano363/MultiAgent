"""收集 N-seed 追尾数据（支持分段运行 + 落盘），用于 Fisher 精确检验。

用法：
  python stat_collect_collision.py <mode> <start_seed> <n_seed> <outfile>
    mode: m1 或 m3
    start_seed: 起始 seed（支持分段，如 0/10/20）
    n_seed: 本次运行的 seed 数
    outfile: 追尾步数落盘文件（每行一个 seed 的 collision_steps）

 例：分 5 段跑 50-seed M1：
   for s in 0 10 20 30 40; do python stat_collect_collision.py m1 $s 10 m1_coll.txt; done
"""
import sys
import numpy as np
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))
sys.path.insert(0, str(Path(__file__).parent))
import evaluate_m1_m3_long as ev
from src.algorithms.mappo_agent import MAPPOAgent

CKPT = "outputs/checkpoints/mappo_fleet_best_cp_seed0_orig.pt"
MODE = sys.argv[1]
START = int(sys.argv[2])
N = int(sys.argv[3])
OUT = sys.argv[4]

colls = []
for s in range(START, START + N):
    if MODE == 'm1':
        env = ev.make_env(65 / 3.6, hierarchical=True, adj_coef=0.1)
        agent = MAPPOAgent(num_drones=ev.NUM_TRAINS, obs_per_drone=11, act_per_drone=1, device='cpu')
        agent.load(CKPT)
        agent.policy.eval()
        r = ev.run_episode(env, agent, 'm1', s, True, True)
    else:
        env = ev.make_env(65 / 3.6, hierarchical=True, adj_coef=0.0)
        r = ev.run_episode(env, None, 'm3', s, True, True)
    colls.append(int(r['collision_steps']))
    print(f"seed{s}: collision={colls[-1]} reward={r['reward']:.0f}", flush=True)

# 追加到输出文件（分段运行时用 append）
with open(OUT, 'a') as f:
    for c in colls:
        f.write(f"{c}\n")
print(f"[{MODE}] done: {len(colls)} seeds appended to {OUT}")
