"""DQN baseline 多列评估：每列独立 DQN 学循环制动（无协同），对比 M1/M3。

DQN（Zhang2024 式）在单列学循环制动，多列场景中每列独立 DQN（无列间协同）→
对标"忽略协同的单列强化学习"，对比 M1（MAPPO 协同）。
支持 --num_trains 参数（3列/5列）。
"""
import sys
import argparse
from pathlib import Path
import numpy as np
sys.path.append(str(Path(__file__).parent.parent.parent))

from src.algorithms.dqn_agent import DQNAgent
from src.trainer.train_cyclic_braking import cyclic_obs


def eval_dqn(ckpt, num_trains, target_gap=100.0, n_seed=1):
    dqn = DQNAgent(obs_dim=4, num_actions=4, device='cuda')
    dqn.load(ckpt)
    dqn.eps = 0.0  # 评估无探索

    # 动态导入 make_env 并设 num_trains
    from src.evaluation import evaluate_m1_m3_long as ev
    ev.NUM_TRAINS = num_trains

    results = []
    for s in range(n_seed):
        env = ev.make_env(65.0 / 3.6, hierarchical=False, target_gap=target_gap)
        np.random.seed(s)
        obs, _ = env.reset(options={'speed': 65.0 / 3.6})
        done = False
        step = 0
        rewards = []
        peaks = []
        gaps = []
        while not done and step < 3000:
            actions = np.zeros((env.num_trains, 1), dtype=np.float32)
            for i, tr in enumerate(env.trains):
                o = cyclic_obs(tr).flatten()
                ai = dqn.select_action(o, eval_mode=True)
                actions[i, 0] = dqn.action_to_throttle(ai)
            obs, r, term, trunc, info = env.step(actions)
            done = term or trunc
            rewards.append(r)
            peaks.append(info['coupler_force_peak'] / 1e3)
            if env.num_trains > 1:
                gs = []
                for k in range(1, env.num_trains):
                    gs.append(env.trains[k - 1].dynamics.pos[-1] - env._train_heads[k])
                gaps.append(min(gs))
            step += 1
        gap_arr = np.array(gaps)
        results.append({
            'reward': float(sum(rewards)),
            'coupler_peak': float(max(peaks)),
            'gap_min': float(gap_arr.min()) if len(gap_arr) else None,
            'collision_steps': int((gap_arr < 5.0).sum()) if len(gap_arr) else 0,
        })
    return results


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--checkpoint', default='outputs/checkpoints/dqn_cyclic_best_seed0.pt')
    ap.add_argument('--num_trains', type=int, default=3)
    ap.add_argument('--target_gap', type=float, default=100.0)
    args = ap.parse_args()
    print(f"DQN baseline（每列独立 DQN 学循环制动，无协同），{args.num_trains}列，target_gap={args.target_gap}m")
    res = eval_dqn(args.checkpoint, args.num_trains, target_gap=args.target_gap, n_seed=1)
    r = res[0]
    gm = r['gap_min'] if r['gap_min'] is not None else float('nan')
    print(f"  reward={r['reward']:+.0f} 车钩力={r['coupler_peak']:.0f}kN "
          f"间距min={gm:.0f}m 追尾={r['collision_steps']}")


if __name__ == '__main__':
    main()
