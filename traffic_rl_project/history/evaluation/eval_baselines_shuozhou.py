"""
临时评估脚本：真实剖面（shuozhou_23800）+ 1500 步下的 baseline 完整指标基准。

建立 M1 群组 MAPPO 收敛判断的对比基准（E3 前置）：
- 惰行（actions=0）：证明真实剖面下需要控制（超速/无法保持）
- 单列独立 PID（无协同）：协同增量价值的基准
- 规则循环制动：论文循环制动物理参考

输出：每个 baseline 的完整指标 + 逐列明细 + 累计 reward，落盘带时间戳 csv。
（临时脚本，结论留痕后由用户决定是否删除）
"""
import os
import sys
import time
import numpy as np
from pathlib import Path

sys.path.append(str(Path(__file__).parent.parent.parent))

from src.environments.train_fleet_env import TrainFleetEnv
from src.evaluation.evaluate_fleet import (
    run_episode, baseline_single_train_pid,
)

OUT_DIR = Path('outputs/diagnostics')
OUT_DIR.mkdir(parents=True, exist_ok=True)


def make_env():
    return TrainFleetEnv({
        'num_trains': 3, 'consist_preset': '10kt_1plus0',
        'grade_profile': 'shuozhou_23800',
        'v_max': 80.0 / 3.6, 'v_min': 40.0 / 3.6,  # V5.24：限速[40,80]对齐Zhang2024朔黄线
        'target_gap': 100.0, 'max_steps': 1500,
        'max_accel': 1.0, 'enable_disturbance': False,
        'use_coupler_constraint': True,
    })


def coast_policy(env):
    """纯惰行：动作恒 0（不牵引不制动）。"""
    def policy_fn(obs):
        return np.zeros(env.num_trains)
    return policy_fn


def cyclic_braking_policy(env):
    """规则循环制动：基于本列速度，超上限制动/低下限缓解。
    （用 get_action_accel 执行，参考论文循环制动物理）
    """
    def policy_fn(obs):
        actions = np.zeros(env.num_trains)
        for i, tr in enumerate(env.trains):
            v = tr.dynamics.vel[0]
            if v > env.v_max:          # 超上限 → 制动
                actions[i] = -0.8
            elif v < env.v_min:        # 低于下限 → 牵引
                actions[i] = 0.5
            else:
                actions[i] = 0.0       # 区间内惰行
        return actions
    return policy_fn


def run_all():
    ts = time.strftime('%Y%m%d_%H%M%S')
    out_csv = OUT_DIR / f'baselines_shuozhou_{ts}.csv'
    print("=" * 80)
    print("Baseline 完整指标（真实剖面 shuozhou_23800，1500 步）")
    print("=" * 80)

    rows = []
    configs = [
        ('coast', coast_policy, '惰行'),
        ('single_pid', baseline_single_train_pid, '单列独立PID'),
        ('cyclic', cyclic_braking_policy, '规则循环制动'),
    ]
    for name, make_policy, label in configs:
        env = make_env()
        policy = make_policy(env)
        m, traj = run_episode(env, policy, record=True)
        # 累计 reward（重跑一步拿累加值）
        env2 = make_env()
        policy2 = make_policy(env2)
        obs, _ = env2.reset(options={'speed': 65.0 / 3.6})
        cum_reward = 0.0
        done = False
        while not done:
            a = policy2(obs)
            obs, r, term, trunc, info = env2.step(a)
            cum_reward += r
            done = term or trunc

        row = {
            'method': name, 'label': label,
            'reward_final_step': m['reward'],
            'reward_cumulative': cum_reward,
            'speed_mean': m['speed_mean'],
            'speed_std_across': m['speed_std_across'],
            'speed_over_vmax_frac': m['speed_over_vmax_frac'],
            'speed_under_vmin_frac': m['speed_under_vmin_frac'],
            'gap_err_mean': m['gap_err_mean'],
            'gap_err_max': m['gap_err_max'],
            'coupler_peak_kN': m['coupler_peak_kN'],
            'coupler_violations': m['coupler_violations'],
            'energy_kwh': m['energy_kwh'],
            'collision': m['collision'],
            'steps': m['steps'],
            'coupler_peak_per_train': m['metrics_per_train']['coupler_peak_kN'],
            'speed_mean_per_train': m['metrics_per_train']['speed_mean'],
        }
        rows.append(row)
        print(f"\n[{label}]")
        print(f"  累计reward={cum_reward:+.0f} | 末步reward={m['reward']:+.1f}")
        print(f"  平均速度={m['speed_mean']:.2f}m/s | 列间速度std={m['speed_std_across']:.2f}")
        print(f"  超速占比={m['speed_over_vmax_frac']*100:.1f}% | 低速占比={m['speed_under_vmin_frac']*100:.1f}%")
        print(f"  间距误差mean={m['gap_err_mean']:.1f}m / max={m['gap_err_max']:.1f}m")
        print(f"  车钩力峰值={m['coupler_peak_kN']:.0f}kN (逐列{m['metrics_per_train']['coupler_peak_kN']}) | 超限={m['coupler_violations']}")
        print(f"  能耗={m['energy_kwh']:.2f}kWh | 碰撞={m['collision']} | 步数={m['steps']}")

    import pandas as pd
    df = pd.DataFrame(rows)
    df.to_csv(out_csv, index=False)
    print("\n" + "=" * 80)
    print(f"已落盘: {out_csv}")
    print("=" * 80)


if __name__ == '__main__':
    run_all()
