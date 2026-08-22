"""DQN baseline 多列评估：每列独立 DQN 学循环制动（无协同），对比 M1/M3。

DQN（Zhang2024 式）在单列学循环制动，多列场景中每列独立 DQN（无列间协同）→
对标"忽略协同的单列强化学习"，对比 M1（MAPPO 协同）。
"""
import sys
from pathlib import Path
import numpy as np
sys.path.append(str(Path(__file__).parent.parent.parent))

from src.environments.train_fleet_env import TrainFleetEnv
from src.algorithms.dqn_agent import DQNAgent
from src.trainer.train_cyclic_braking import cyclic_obs
from src.evaluation.evaluate_m1_m3_long import make_env, run_episode, summarize


def eval_dqn(ckpt, target_gap=100.0, n_seed=1):
    """每列独立 DQN 学循环制动（无协同），多列评估。"""
    from src.environments.train_env import TrainFormationEnv
    dqn = DQNAgent(obs_dim=4, num_actions=4, device='cuda')
    dqn.load(ckpt)
    dqn.eps = 0.0  # 评估无探索

    results = []
    for s in range(n_seed):
        env = make_env(65.0 / 3.6, hierarchical=False, target_gap=target_gap)
        np.random.seed(s)
        obs, _ = env.reset(options={'speed': 65.0 / 3.6})
        done = False
        step = 0
        rewards = []
        peaks = []
        gaps = []
        while not done and step < 3000:
            # 每列用 DQN（单列 obs，不看前列）独立控制
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
                g1 = env.trains[0].dynamics.pos[-1] - env._train_heads[1]
                g2 = env.trains[1].dynamics.pos[-1] - env._train_heads[2]
                gaps.append(min(g1, g2))
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
    ckpt = 'outputs/checkpoints/dqn_cyclic_best_seed0.pt'
    print(f"DQN baseline（每列独立 DQN 学循环制动，无协同），ckpt={ckpt}")
    for gap in [100.0, 60.0, 40.0]:
        res = eval_dqn(ckpt, target_gap=gap, n_seed=1)
        r = res[0]
        print(f"  target_gap={gap:.0f}m: reward={r['reward']:+.0f} 车钩力={r['coupler_peak']:.0f}kN "
              f"间距min={r['gap_min'] if r['gap_min'] else float('nan'):.0f}m 追尾={r['collision_steps']}")


if __name__ == '__main__':
    main()
