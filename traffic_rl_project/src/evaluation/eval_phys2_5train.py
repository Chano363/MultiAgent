"""【2026-08-30 物理基线对齐后】5 列规模扩展评估：共享策略零样本扩列（phys2）。

背景：M-MARL 的 MAPPO 为共享策略（每列同一网络），在第 1 层规则循环制动 +
第 2 层协同阈值下，策略权重与编队列数无关。故可将 phys2 下 3 列训练的策略
权重直接用于 5 列编队，检验方法可扩展性（列数泛化，免重训）。

注意：agent 仅载入 policy_state_dict（value 网输入维度依赖 num_drones，评估不
使用 value，故扩列不载入 value）。评估只走 select_actions → policy 前向。

输出：
  outputs/results_phys2/summary_5train_phys2.md   5列 M-MARL/No-C 汇总（随机初速）
用法：
  python src/evaluation/eval_phys2_5train.py [--steps 3000] [--n_seed 5]
"""
import sys
import argparse
from pathlib import Path


import numpy as np
import torch
from src.algorithms.mappo_agent import MAPPOAgent
from src.evaluation import evaluate_m1_m3_long as ev

CKPT = 'outputs/checkpoints_phys2/mappo_fleet_best_cp_seed0.pt'
OUT = Path('outputs/results_phys2')


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--steps', type=int, default=3000)
    ap.add_argument('--n_seed', type=int, default=5)
    ap.add_argument('--num_trains', type=int, default=5,
                    help='编队列数：3=健壮性（随机初速），5=零样本扩列')
    ap.add_argument('--ckpt', default=CKPT,
                    help='待评估策略检查点（policy_state_dict）')
    ap.add_argument('--out', default='summary_5train_phys2.md',
                    help='输出汇总文件名（results_phys2 下）')
    args = ap.parse_args()

    ev.NUM_TRAINS = args.num_trains
    ev.MAX_STEPS = args.steps
    n_seed = args.n_seed
    OUT.mkdir(parents=True, exist_ok=True)

    # 载入 3 列训练的策略权重到 {num_trains} 列 agent（仅 policy，评估用）。
    # MAPPO 共享策略（每列同一网络），权重与编队列数无关 → 支持零样本扩列。
    agent = MAPPOAgent(num_drones=args.num_trains, obs_per_drone=11,
                       act_per_drone=1, device='cuda')
    ckpt = torch.load(args.ckpt, map_location='cuda')
    agent.policy.load_state_dict(ckpt['policy_state_dict'])
    agent.policy.eval()
    print(f"已载入策略权重: {args.ckpt}  （编队={args.num_trains}列）")

    fleet = f"{args.num_trains} 列"
    lines = ["| 编队 | 方法 | 累计回报 | 追尾步数 | 车钩力峰值(kN) | 最小间距(m) |",
             "|:--|:--|:--|:--|:--|:--|"]
    for mode, hier, adj in [('m1', True, 0.1), ('m3', True, 0.0)]:
        results = []
        for s in range(n_seed):
            env = ev.make_env(65 / 3.6, hierarchical=hier, adj_coef=adj,
                              grade_profile='shuozhou_23800', target_gap=100.0,
                              max_steps=args.steps)
            r = ev.run_episode(env, agent if mode == 'm1' else None, mode, s,
                               deterministic=True, randomize_init=True)
            results.append(r)
            print(f"  [{fleet} {mode} seed{s}] reward={r['reward']:+.0f} "
                  f"峰值={r['coupler_peak']:.0f}kN 追尾={r['collision_steps']} "
                  f"间距min={r['gap_min']:.0f}m")
            sys.stdout.flush()
        ev.summarize(f"{fleet} {mode}（随机初速 58-66km/h，{n_seed} seed）", results)
        rewards = [r['reward'] for r in results]
        colls = [r['collision_steps'] for r in results]
        peaks = [r['coupler_peak'] for r in results]
        gmins = [r['gap_min'] for r in results]
        lines.append(
            f"| {fleet} | {'M-MARL（零样本扩列）' if mode == 'm1' else 'No-C（规则）'} | "
            f"{np.mean(rewards):+.0f} | {np.mean(colls):.1f} | {np.mean(peaks):.0f} | "
            f"{np.mean(gmins):.0f} |")

    md = OUT / args.out
    md.write_text('\n'.join(lines) + '\n', encoding='utf-8')
    print(f"\n汇总已写入 {md}")


if __name__ == '__main__':
    main()