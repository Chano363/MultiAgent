"""
论文可视化：生成间距轨迹、车钩力轨迹对比图。

用法：
    python src/evaluation/make_figures.py \
        --checkpoint outputs/checkpoints/mappo_fleet_ep60.pt \
        --outdir outputs/figures
"""

import os
import sys
import argparse
import numpy as np
from pathlib import Path
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

sys.path.append(str(Path(__file__).parent.parent.parent))

from src.environments.train_fleet_env import TrainFleetEnv
from src.algorithms.mappo_agent import MAPPOAgent
from src.evaluation.evaluate_fleet import (
    run_episode, baseline_single_train_pid, baseline_no_coupler_mar, policy_learned_marl,
)


def make_env():
    return TrainFleetEnv({
        'num_trains': 3, 'consist_preset': '10kt_1plus0',
        'grade_profile': 'long_downhill', 'target_speed': 20.0,
        'target_gap': 100.0, 'max_steps': 300,
        'max_accel': 1.0, 'enable_disturbance': True,
        'disturbance_step': 150, 'disturbance_target_accel': -0.5,
    })


def generate(checkpoint, outdir):
    Path(outdir).mkdir(parents=True, exist_ok=True)

    # 加载 MAPPO
    env = make_env()
    agent = MAPPOAgent(num_drones=env.num_trains, obs_per_drone=env.obs_dim,
                       act_per_drone=1, device='cuda')
    agent.load(checkpoint)
    agent.policy.eval()

    # 跑三种方法的轨迹
    env_m = make_env(); _, traj_m = run_episode(env_m, policy_learned_marl(agent, env_m))
    env_s = make_env(); _, traj_s = run_episode(env_s, baseline_single_train_pid(env_s))
    env_n = make_env(); _, traj_n = run_episode(env_n, baseline_no_coupler_mar(env_n))

    t = np.array(traj_m['t'])

    # 图1：间距轨迹对比
    plt.figure(figsize=(9, 5))
    plt.plot(t, traj_m['gap'], 'b-', linewidth=2, label='MAPPO (考虑车钩力)')
    plt.plot(t, traj_s['gap'], 'r--', linewidth=1.5, label='单列独立控制')
    plt.plot(t, traj_n['gap'], 'g-.', linewidth=1.5, label='忽略车钩力群组')
    plt.axhline(y=100, color='k', linestyle=':', alpha=0.6, label='目标间距 100m')
    plt.xlabel('Time step')
    plt.ylabel('列间间距 (m)')
    plt.title('列车群组编队间距轨迹对比（领航车 150 步突发减速）')
    plt.legend()
    plt.grid(alpha=0.3)
    plt.tight_layout()
    plt.savefig(os.path.join(outdir, 'gap_trajectory.png'), dpi=150)
    plt.close()

    # 图2：车钩力轨迹对比
    plt.figure(figsize=(9, 5))
    plt.plot(t, traj_m['coupler_peak'], 'b-', linewidth=2, label='MAPPO (考虑车钩力)')
    plt.plot(t, traj_s['coupler_peak'], 'r--', linewidth=1.5, label='单列独立控制')
    plt.plot(t, traj_n['coupler_peak'], 'g-.', linewidth=1.5, label='忽略车钩力群组')
    plt.axhline(y=1000, color='k', linestyle=':', alpha=0.8, label='车钩力上限 1000kN')
    plt.xlabel('Time step')
    plt.ylabel('车钩力峰值 (kN)')
    plt.title('列车群组车钩力峰值轨迹对比')
    plt.legend()
    plt.grid(alpha=0.3)
    plt.tight_layout()
    plt.savefig(os.path.join(outdir, 'coupler_trajectory.png'), dpi=150)
    plt.close()

    # 图3：速度轨迹
    plt.figure(figsize=(9, 5))
    plt.plot(t, traj_m['speed'], 'b-', linewidth=2, label='MAPPO (考虑车钩力)')
    plt.plot(t, traj_s['speed'], 'r--', linewidth=1.5, label='单列独立控制')
    plt.plot(t, traj_n['speed'], 'g-.', linewidth=1.5, label='忽略车钩力群组')
    plt.axhline(y=20, color='k', linestyle=':', alpha=0.6, label='目标速度 20m/s')
    plt.xlabel('Time step')
    plt.ylabel('速度 (m/s)')
    plt.title('领航车速度轨迹（扰动后协同制动响应）')
    plt.legend()
    plt.grid(alpha=0.3)
    plt.tight_layout()
    plt.savefig(os.path.join(outdir, 'speed_trajectory.png'), dpi=150)
    plt.close()

    print(f"图表已生成到 {outdir}/:")
    print(f"  - gap_trajectory.png")
    print(f"  - coupler_trajectory.png")
    print(f"  - speed_trajectory.png")


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--checkpoint', type=str, required=True)
    parser.add_argument('--outdir', type=str, default='outputs/figures')
    args = parser.parse_args()
    generate(args.checkpoint, args.outdir)
