"""【2026-08-30 物理基线对齐后】M1 重训模型 5-seed 评估 + M3/惰行对照。

背景：动力学模型完成基线对齐（MT-2 迟滞缓冲器 + 实算法制动力 + 制动波
并行传播），原 M1 模型是在旧（有 bug 的）动力学下训练的，需在新物理下
重训并重新评估，论文/汇报结果一律以本脚本产出为准。

输出：
  outputs/results_phys2/eval_summary.json   汇总指标（增量追加）
  outputs/results_phys2/traj_{mode}_seed{s}.csv  逐步轨迹（出图用）

用法：
  python src/evaluation/eval_phys2_m1_5seed.py --mode m1  --seeds 0,1,2,3,4 --steps 3000
  python src/evaluation/eval_phys2_m1_5seed.py --mode m3  --steps 3000
  python src/evaluation/eval_phys2_m1_5seed.py --mode coast --steps 3000
"""
import sys
import json
import argparse
from pathlib import Path

sys.path.append(str(Path(__file__).parent.parent.parent))

import numpy as np
import torch

from src.environments.train_fleet_env import TrainFleetEnv
from src.algorithms.mappo_agent import MAPPOAgent
from src.evaluation.evaluate_m1_m3_long import make_env, run_episode, summarize

CKPT_DIR = 'outputs/checkpoints_phys2'
OUT_DIR = 'outputs/results_phys2'


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--mode', default='m1', choices=['m1', 'm3', 'coast'])
    ap.add_argument('--seeds', default='0,1,2,3,4')
    ap.add_argument('--steps', type=int, default=3000)
    ap.add_argument('--eval_seed', type=int, default=0,
                    help='评估环境种子（默认固定 0，保证各模型同工况对照）')
    ap.add_argument('--ckpt_dir', default=CKPT_DIR,
                    help='检查点目录（对比不同训练配方时用不同目录）')
    ap.add_argument('--target_gap', type=float, default=100.0,
                    help='目标间距（压力消融用，100→40 压力增大）')
    ap.add_argument('--label', default=None,
                    help='结果标签（默认同 mode，用于区分不同配方的汇总）')
    args = ap.parse_args()
    label = args.label or args.mode

    Path(OUT_DIR).mkdir(parents=True, exist_ok=True)
    summary_path = Path(OUT_DIR) / 'eval_summary.json'
    summary = json.loads(summary_path.read_text(encoding='utf-8')) \
        if summary_path.exists() else {}

    seeds = [int(s) for s in args.seeds.split(',')]
    results = []
    for s in seeds:
        env = make_env(65 / 3.6, hierarchical=(args.mode != 'coast'),
                       adj_coef=0.1, grade_profile='shuozhou_23800',
                       target_gap=args.target_gap, max_steps=args.steps)
        agent = None
        if args.mode == 'm1':
            ckpt = f"{args.ckpt_dir}/mappo_fleet_best_cp_seed{s}.pt"
            if not Path(ckpt).exists():
                print(f"[跳过] 缺少检查点 {ckpt}")
                continue
            agent = MAPPOAgent(num_drones=3, obs_per_drone=11, act_per_drone=1,
                               device='cuda')
            agent.load(ckpt)
            agent.policy.eval()
        res = run_episode(env, agent, args.mode, args.eval_seed,
                          deterministic=True, randomize_init=False,
                          return_traj=True)
        results.append(res)
        traj = res.pop('traj')
        tag = f"{label}_seed{s}" if args.mode == 'm1' else label
        traj.to_csv(Path(OUT_DIR) / f"traj_{tag}.csv", index=False)
        print(f"  [{tag}] reward={res['reward']:+.0f} 车钩力峰值={res['coupler_peak']:.0f}kN "
              f"追尾步数={res['collision_steps']} 间距min={res['gap_min']:.0f}m "
              f"循环制动={res['cycles']}")
        sys.stdout.flush()

    if results:
        summarize(f"{label}（新物理重训后）", results)
        summary[label] = [
            {k: (None if isinstance(v, float) and np.isnan(v) else v)
             for k, v in r.items()} for r in results
        ]
        summary_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2),
                                encoding='utf-8')
        print(f"汇总已写入 {summary_path}")


if __name__ == '__main__':
    main()
