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


def make_env(seed=0, use_coupler_constraint=True):
    """构造评估环境（ITSC 论文版：真实剖面 + 无扰动 + 限速区间）。

    seed 用于随机化评估初始速度（对齐 Zhang2024 长大下坡，模拟 varied conditions），
    使不同评估工况下的指标有方差。**不引入人为扰动**（用户确认：真实线路本身驱动协同）。
    use_coupler_constraint=False 时构建"忽略车钩力"环境（消融实验 M2）。
    """
    rng = np.random.RandomState(seed)
    # 评估初始速度随机化：65 km/h 附近 ±5（18.06±1.4 m/s）
    init_speed = (65.0 + rng.uniform(-5, 5)) / 3.6
    env = TrainFleetEnv({
        'num_trains': 3, 'consist_preset': '10kt_1plus0',
        'grade_profile': 'shuozhou_23800',
        'v_max': 80.0 / 3.6, 'v_min': 40.0 / 3.6,  # V5.24：限速[40,80]对齐Zhang2024朔黄线
        'target_gap': 100.0, 'max_steps': 1500,
        'max_accel': 1.0, 'enable_disturbance': False,
        'use_coupler_constraint': use_coupler_constraint,
    })
    env._eval_init_speed = init_speed
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


def run_methods(checkpoints, num_seeds, device, nocoupler_checkpoints=None):
    """checkpoints: list of checkpoint paths（有车钩力，每个训练种子一个模型）。
    nocoupler_checkpoints: list of checkpoint paths（无车钩力消融，可选）。
    """
    results = {'marl': [], 'single': [], 'no_coupler': [], 'marl_nocp': []}
    for seed in range(num_seeds):
        torch.manual_seed(seed); np.random.seed(seed)

        # MAPPO（考虑车钩力）：加载对应 seed 的训练模型，用考虑车钩力的环境
        cp = checkpoints[seed] if seed < len(checkpoints) else checkpoints[-1]
        agent = load_marl_agent(cp, device)
        e = make_env(seed, use_coupler_constraint=True)
        m, _ = run_episode(e, policy_learned_marl(agent, e), init_speed=e._eval_init_speed)
        results['marl'].append(m)

        # 消融：MAPPO（忽略车钩力）：加载无车钩力模型，用忽略车钩力的环境
        if nocoupler_checkpoints:
            nc = nocoupler_checkpoints[seed] if seed < len(nocoupler_checkpoints) else nocoupler_checkpoints[-1]
            agent_nc = load_marl_agent(nc, device)
            e = make_env(seed, use_coupler_constraint=False)
            m, _ = run_episode(e, policy_learned_marl(agent_nc, e), init_speed=e._eval_init_speed)
            results['marl_nocp'].append(m)

        # Baseline 1: 单列独立（同架构消融 M3，用独立单列策略）
        e = make_env(seed)
        m, _ = run_episode(e, baseline_single_train_pid(e), init_speed=e._eval_init_speed)
        results['single'].append(m)

        # Baseline 2: 忽略车钩力群组（规则策略）
        e = make_env(seed)
        m, _ = run_episode(e, baseline_no_coupler_mar(e), init_speed=e._eval_init_speed)
        results['no_coupler'].append(m)

    # 汇总
    print("\n" + "=" * 78)
    print("对比实验结果（mean ± std）")
    print("=" * 78)
    if nocoupler_checkpoints:
        header = f"{'指标':<22}{'MAPPO(车钩力)':<22}{'MAPPO(忽略钩)':<18}{'单列独立':<18}{'规则忽略钩':<18}"
    else:
        header = f"{'指标':<22}{'MAPPO(车钩力)':<22}{'单列独立':<20}{'忽略车钩力':<20}"
    print(header)
    print("-" * 78)

    metric_names = ['reward', 'speed_mean', 'speed_std_across', 'speed_over_vmax_frac',
                    'speed_under_vmin_frac', 'gap_err_mean', 'gap_err_max',
                    'coupler_peak_kN', 'coupler_violations', 'energy_kwh', 'collision']
    labels = {
        'reward': 'Reward', 'speed_mean': '平均速度(m/s)',
        'speed_std_across': '列间速度一致性(m/s)', 'speed_over_vmax_frac': '超速占比',
        'speed_under_vmin_frac': '低速占比', 'gap_err_mean': '间距误差均值(m)',
        'gap_err_max': '间距误差最大(m)',
        'coupler_peak_kN': '车钩力峰值(kN)', 'coupler_violations': '车钩力超限次数',
        'energy_kwh': '牵引能耗(kWh)', 'collision': '碰撞次数',
    }
    for k in metric_names:
        row = f"{labels[k]:<22}"
        methods = ['marl', 'marl_nocp', 'single', 'no_coupler'] if nocoupler_checkpoints \
            else ['marl', 'single', 'no_coupler']
        for method in methods:
            if method == 'marl_nocp' and not nocoupler_checkpoints:
                continue
            mean, std = summarize(results[method])[k]
            row += f"{mean:8.3f}±{std:<8.3f}  "
        print(row)
    print("=" * 78)
    return results


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--checkpoint', type=str, required=True,
                        help='有车钩力模型路径，或含 seed 后缀的 glob 模式（如 mappo_fleet_best_cp_seed*.pt）')
    parser.add_argument('--nocoupler_checkpoint', type=str, default=None,
                        help='无车钩力模型路径/glob（消融实验，如 mappo_fleet_best_nocp_seed*.pt）')
    parser.add_argument('--num_seeds', type=int, default=3)
    parser.add_argument('--device', type=str, default='cuda')
    args = parser.parse_args()

    import glob
    # 展开有车钩力模型
    if 'seed' in args.checkpoint:
        checkpoints = sorted(glob.glob(args.checkpoint))
        if not checkpoints:
            print(f"未找到匹配模型: {args.checkpoint}")
            sys.exit(1)
        print(f"加载 {len(checkpoints)} 个种子模型: {[Path(c).name for c in checkpoints]}")
        num_seeds = len(checkpoints)
    else:
        checkpoints = [args.checkpoint]
        num_seeds = args.num_seeds

    # 展开无车钩力模型（消融）
    nocoupler_checkpoints = None
    if args.nocoupler_checkpoint:
        if 'seed' in args.nocoupler_checkpoint:
            nocoupler_checkpoints = sorted(glob.glob(args.nocoupler_checkpoint))
            if not nocoupler_checkpoints:
                print(f"未找到无车钩力模型: {args.nocoupler_checkpoint}")
                sys.exit(1)
            print(f"加载 {len(nocoupler_checkpoints)} 个无车钩力模型: {[Path(c).name for c in nocoupler_checkpoints]}")
        else:
            nocoupler_checkpoints = [args.nocoupler_checkpoint]

    run_methods(checkpoints, num_seeds, args.device, nocoupler_checkpoints)
