"""
论文对比实验：MAPPO（考虑车钩力） vs 单列独立 vs 忽略车钩力群组。

用法：
    python src/evaluation/run_compare.py \
        --checkpoint outputs/checkpoints/mappo_fleet_ep60.pt \
        --num_seeds 3

输出：统一指标对比表（多种子 mean±std）。
"""

import os
import sys
import argparse
import numpy as np
import torch
from pathlib import Path

sys.path.append(str(Path(__file__).parent.parent.parent))

from src.environments.train_fleet_env import TrainFleetEnv
from src.algorithms.mappo_agent import MAPPOAgent
from src.evaluation.evaluate_fleet import (
    run_episode, summarize,
    baseline_single_train_pid, baseline_no_coupler_mar, policy_learned_marl,
)


def make_env(seed=0):
    """构造评估环境。

    seed 用于随机化评估工况（扰动步数/强度），模拟"varied conditions"
    （对齐 Hua2024 用 50 个评估种子），使不同评估工况下的指标有方差。
    """
    rng = np.random.RandomState(seed)
    # 随机扰动步数（100-200）和强度（-0.7~-0.4），模拟不同前方工况
    disturbance_step = int(rng.uniform(100, 200))
    disturbance_accel = float(rng.uniform(-0.7, -0.4))
    env = TrainFleetEnv({
        'num_trains': 3, 'consist_preset': '10kt_1plus0',
        'grade_profile': 'long_downhill', 'target_speed': 20.0,
        'target_gap': 100.0, 'max_steps': 300,
        'max_accel': 1.0, 'enable_disturbance': True,
        'disturbance_step': disturbance_step,
        'disturbance_target_accel': disturbance_accel,
    })
    return env


def load_marl_agent(checkpoint, device='cuda'):
    env = make_env()
    agent = MAPPOAgent(
        num_drones=env.num_trains,
        obs_per_drone=env.obs_dim,
        act_per_drone=1,
        device=device,
    )
    agent.load(checkpoint)
    agent.policy.eval()
    return agent


def run_methods(checkpoints, num_seeds, device):
    """checkpoints: list of checkpoint paths（每个训练种子一个模型）。"""
    env = make_env()

    results = {'marl': [], 'single': [], 'no_coupler': []}
    for seed in range(num_seeds):
        torch.manual_seed(seed); np.random.seed(seed)

        # MAPPO（考虑车钩力）：加载对应 seed 的训练模型
        cp = checkpoints[seed] if seed < len(checkpoints) else checkpoints[-1]
        agent = load_marl_agent(cp, device)
        e = make_env(seed)
        m, _ = run_episode(e, policy_learned_marl(agent, e))
        results['marl'].append(m)

        # Baseline 1: 单列独立
        e = make_env(seed)
        m, _ = run_episode(e, baseline_single_train_pid(e))
        results['single'].append(m)

        # Baseline 2: 忽略车钩力群组
        e = make_env(seed)
        m, _ = run_episode(e, baseline_no_coupler_mar(e))
        results['no_coupler'].append(m)

    # 汇总
    print("\n" + "=" * 78)
    print("对比实验结果（mean ± std）")
    print("=" * 78)
    header = f"{'指标':<22}{'MAPPO(车钩力)':<22}{'单列独立':<20}{'忽略车钩力':<20}"
    print(header)
    print("-" * 78)

    metric_names = ['reward', 'speed_consistency', 'gap_err_mean', 'gap_err_max',
                    'coupler_peak_kN', 'coupler_violations', 'energy_kwh', 'collision']
    labels = {
        'reward': 'Reward', 'speed_consistency': '速度一致性误差(m/s)',
        'gap_err_mean': '间距误差均值(m)', 'gap_err_max': '间距误差最大(m)',
        'coupler_peak_kN': '车钩力峰值(kN)', 'coupler_violations': '车钩力超限次数',
        'energy_kwh': '牵引能耗(kWh)', 'collision': '碰撞次数',
    }
    for k in metric_names:
        row = f"{labels[k]:<22}"
        for method in ['marl', 'single', 'no_coupler']:
            mean, std = summarize(results[method])[k]
            row += f"{mean:8.3f}±{std:<8.3f}  "
        print(row)
    print("=" * 78)
    return results


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--checkpoint', type=str, required=True,
                        help='单模型路径，或含 seed 后缀的 glob 模式（如 outputs/checkpoints/mappo_fleet_ep60_seed*.pt）')
    parser.add_argument('--num_seeds', type=int, default=3)
    parser.add_argument('--device', type=str, default='cuda')
    args = parser.parse_args()

    import glob
    # 若含 seed 后缀，展开为多个模型
    if 'seed' in args.checkpoint:
        checkpoints = sorted(glob.glob(args.checkpoint))
        if not checkpoints:
            print(f"未找到匹配模型: {args.checkpoint}")
            sys.exit(1)
        print(f"加载 {len(checkpoints)} 个种子模型: {[Path(c).name for c in checkpoints]}")
        run_methods(checkpoints, len(checkpoints), args.device)
    else:
        run_methods([args.checkpoint], args.num_seeds, args.device)
