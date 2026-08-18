"""分层第2层模型评估：输出协同调整δ，第1层策略控速。

评估指标：速度区间[40,80]、车钩力、列间间距（避免追尾/拉开）、reward。
"""
import sys
from pathlib import Path
sys.path.append(str(Path(__file__).parent.parent.parent))
import numpy as np
import torch
from src.environments.train_fleet_env import TrainFleetEnv
from src.algorithms.mappo_agent import MAPPOAgent


def make_env(init_speed):
    return TrainFleetEnv({
        'num_trains': 3, 'consist_preset': '10kt_1plus0',
        'grade_profile': 'shuozhou_23800',
        'v_max': 80.0 / 3.6, 'v_min': 40.0 / 3.6,
        'target_gap': 100.0, 'headway_s': 5.0,
        'max_steps': 1500, 'max_accel': 1.0,
        'enable_disturbance': False, 'use_coupler_constraint': True,
        'hierarchical': True,
    })


def run(env, agent, init_speed):
    obs, _ = env.reset(options={'speed': init_speed})
    done = False
    step = 0
    speeds, gaps, peaks = [], [], []
    rewards = []
    while not done and step < 1500:
        flat = obs.flatten()
        a, _ = agent.select_actions(flat, deterministic=True)
        obs, r, term, trunc, info = env.step(a.reshape(3, 1))
        done = term or trunc
        speeds.extend([tr.dynamics.vel[0] for tr in env.trains])
        # 真实列间间距 = 前列尾部 - 本列队首
        if env.num_trains > 1:
            g1 = env.trains[0].dynamics.pos[-1] - env._train_heads[1]
            g2 = env.trains[1].dynamics.pos[-1] - env._train_heads[2]
            gaps.append(min(g1, g2))
        coupler = np.abs(env.trains[0].dynamics._coupler_forces())
        peaks.append(np.max(coupler) / 1e3)
        rewards.append(r)
        step += 1
    speeds = np.array(speeds)
    gaps = np.array(gaps)
    return speeds, gaps, peaks, rewards


def main():
    ckpt = sys.argv[1] if len(sys.argv) > 1 else 'outputs/checkpoints/mappo_fleet_best_cp_seed0.pt'
    agent = MAPPOAgent(num_drones=3, obs_per_drone=11, act_per_drone=1, device='cuda')
    agent.load(ckpt)
    agent.policy.eval()

    for label, init in [('初始65', 65.0/3.6), ('初始55', 55.0/3.6), ('初始75', 75.0/3.6)]:
        env = make_env(init)
        speeds, gaps, peaks, rewards = run(env, agent, init)
        spd = np.array(speeds)
        over = (spd > env.v_max).mean()*100
        under = (spd < env.v_min).mean()*100
        gap_range = (gaps.min(), gaps.max())
        print(f"[{label}] 平均速度={spd.mean()*3.6:.0f}km/h 范围[{spd.min()*3.6:.0f},{spd.max()*3.6:.0f}] "
              f"超上限{over:.1f}% 低于下限{under:.1f}% "
              f"车钩力峰值={max(peaks):.0f}kN 间距范围[{gap_range[0]:.0f},{gap_range[1]:.0f}]m "
              f"累计reward={sum(rewards):.0f} 步数={len(speeds)//3}")


if __name__ == '__main__':
    main()
