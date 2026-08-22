"""论文图：5列编队 M1 vs M3 vs M-DQN 间距轨迹对比（可扩展性可视化）。

跑 5 列 M1（MAPPO协同）/M3（独立）/M-DQN（每列独立DQN）的间距轨迹。
输出：outputs/figures/fig_5train_gap_trajectory.png
"""
import os
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from pathlib import Path

import sys
sys.path.append(str(Path(__file__).parent.parent.parent))

from src.evaluation import evaluate_m1_m3_long as ev
from src.algorithms.mappo_agent import MAPPOAgent
from src.algorithms.dqn_agent import DQNAgent
from src.trainer.train_cyclic_braking import cyclic_obs

NUM_TRAINS = 5


def run_m1(env, agent):
    obs, _ = env.reset(options={'speed': 65.0 / 3.6})
    done = False
    step = 0
    gaps = []
    while not done and step < 3000:
        a, _ = agent.select_actions(obs.flatten(), deterministic=True)
        a = a.reshape(NUM_TRAINS, 1)
        obs, r, term, trunc, info = env.step(a)
        done = term or trunc
        gs = [env.trains[k - 1].dynamics.pos[-1] - env._train_heads[k] for k in range(1, NUM_TRAINS)]
        gaps.append(min(gs))
        step += 1
    return gaps


def run_m3(env):
    obs, _ = env.reset(options={'speed': 65.0 / 3.6})
    done = False
    step = 0
    gaps = []
    while not done and step < 3000:
        a = np.zeros((NUM_TRAINS, 1), dtype=np.float32)
        obs, r, term, trunc, info = env.step(a)
        done = term or trunc
        gs = [env.trains[k - 1].dynamics.pos[-1] - env._train_heads[k] for k in range(1, NUM_TRAINS)]
        gaps.append(min(gs))
        step += 1
    return gaps


def run_dqn(env, dqn):
    obs, _ = env.reset(options={'speed': 65.0 / 3.6})
    done = False
    step = 0
    gaps = []
    while not done and step < 3000:
        actions = np.zeros((NUM_TRAINS, 1), dtype=np.float32)
        for i, tr in enumerate(env.trains):
            o = cyclic_obs(tr).flatten()
            ai = dqn.select_action(o, eval_mode=True)
            actions[i, 0] = dqn.action_to_throttle(ai)
        obs, r, term, trunc, info = env.step(actions)
        done = term or trunc
        gs = [env.trains[k - 1].dynamics.pos[-1] - env._train_heads[k] for k in range(1, NUM_TRAINS)]
        gaps.append(min(gs))
        step += 1
    return gaps


def main():
    ev.NUM_TRAINS = NUM_TRAINS
    # M1 (5列 MAPPO 协同)
    agent = MAPPOAgent(num_drones=NUM_TRAINS, obs_per_drone=11, act_per_drone=1, device='cuda')
    agent.load('outputs/checkpoints/mappo_fleet_best_cp_seed0.pt')  # 当前是5列
    agent.policy.eval()
    # M-DQN
    dqn = DQNAgent(obs_dim=4, num_actions=4, device='cuda')
    dqn.load('outputs/checkpoints/dqn_cyclic_best_seed0.pt')
    dqn.eps = 0.0

    env1 = ev.make_env(65.0 / 3.6, hierarchical=True, adj_coef=0.1)
    gaps_m1 = run_m1(env1, agent)
    env3 = ev.make_env(65.0 / 3.6, hierarchical=True, adj_coef=0.0)
    gaps_m3 = run_m3(env3)
    envd = ev.make_env(65.0 / 3.6, hierarchical=False)
    gaps_dqn = run_dqn(envd, dqn)

    os.makedirs('outputs/figures', exist_ok=True)
    plt.figure(figsize=(10, 5.5))
    t = np.arange(len(gaps_m1))
    plt.plot(t, gaps_m1, '-', color='blue', linewidth=1.8, label='M1 (coop)')
    plt.plot(t, gaps_m3, '--', color='red', linewidth=1.8, label='M3 (independent)')
    plt.plot(t, gaps_dqn, ':', color='green', linewidth=1.8, label='M-DQN (per-train)')
    plt.axhline(y=100, color='k', linestyle=':', alpha=0.5, label='Target gap 100m')
    plt.axhline(y=0, color='r', linestyle=':', alpha=0.6, label='Rear-end (gap=0)')
    plt.xlabel('Time step')
    plt.ylabel('Min inter-train gap (m)')
    plt.title('5-train platoon: M1 (coop) vs M3 (indep) vs M-DQN gap trajectory')
    plt.legend()
    plt.grid(alpha=0.3)
    plt.tight_layout()
    plt.savefig('outputs/figures/fig_5train_gap_trajectory.png', dpi=150)
    plt.close()
    print('已生成 outputs/figures/fig_5train_gap_trajectory.png')
    print(f'M1 gap_min={min(gaps_m1):.0f}m, M3 gap_min={min(gaps_m3):.0f}m, DQN gap_min={min(gaps_dqn):.0f}m')


if __name__ == '__main__':
    main()
