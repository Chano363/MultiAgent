"""最终分层架构 M1 vs M3 vs 惰行 —— 论文数据整理 + 可视化。

针对最终架构（第1层规则循环制动 + 第2层 RL 阈值协同），在朔黄线真实剖面
shuozhou_23800 + 3列 + 固定初态65 + 限速[40,80] 场景，确定性评估三种方法：
- 惰行（throttle=0 baseline）
- M1（群组协同 + 车钩力，加载 cp checkpoint）
- M3（δ=0 独立，规则循环制动不协同）

输出：
- 落盘轨迹 csv（outputs/diagnostics/m1m3_traj_{mode}.csv）
- 对比图（outputs/figures/m1m3_{gap,coupler,speed}_trajectory.png）
- 对比表（输出到 stdout + outputs/results/m1m3_comparison.md）
"""
import os
import sys
import argparse
import numpy as np
import pandas as pd
from pathlib import Path
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

sys.path.append(str(Path(__file__).parent.parent.parent))

from src.environments.train_fleet_env import TrainFleetEnv
from src.algorithms.mappo_agent import MAPPOAgent

V_MAX = 80.0 / 3.6
V_MIN = 40.0 / 3.6
MAX_STEPS = 3000
NUM_TRAINS = 3


def make_env(hierarchical, adj_coef=0.0):
    return TrainFleetEnv({
        'num_trains': NUM_TRAINS, 'consist_preset': '10kt_1plus0',
        'grade_profile': 'shuozhou_23800',
        'v_max': V_MAX, 'v_min': V_MIN,
        'target_gap': 100.0, 'headway_s': 5.0,
        'max_steps': MAX_STEPS, 'max_accel': 1.0,
        'enable_disturbance': False, 'use_coupler_constraint': True,
        'hierarchical': hierarchical, 'adj_coef': adj_coef,
        'eval_mode': True,
    })


def run_traj(env, agent, mode, seed=0):
    """确定性跑一条轨迹，记录逐步数据。"""
    np.random.seed(seed)
    init = 65.0 / 3.6
    obs, _ = env.reset(options={'speed': init})
    done = False
    step = 0
    rows = []
    while not done and step < MAX_STEPS:
        if mode == 'coast':
            a = np.zeros((NUM_TRAINS, 1), dtype=np.float32)
        elif mode == 'm1':
            flat = obs.flatten()
            a, _ = agent.select_actions(flat, deterministic=True)
            a = a.reshape(NUM_TRAINS, 1)
        else:  # m3
            a = np.zeros((NUM_TRAINS, 1), dtype=np.float32)
        obs, r, term, trunc, info = env.step(a)
        done = term or trunc
        # 各列速度（km/h）与列间间距
        speeds = [float(tr.dynamics.vel[0]) * 3.6 for tr in env.trains]
        gaps = []
        if env.num_trains > 1:
            g1 = env.trains[0].dynamics.pos[-1] - env._train_heads[1]
            g2 = env.trains[1].dynamics.pos[-1] - env._train_heads[2]
            gaps = [g1, g2]
        rows.append({
            'step': step,
            'speed_0': speeds[0], 'speed_1': speeds[1], 'speed_2': speeds[2],
            'speed_mean': float(np.mean(speeds)),
            'gap_1': gaps[0] if gaps else None,
            'gap_2': gaps[1] if gaps else None,
            'gap_min': min(gaps) if gaps else None,
            'coupler_peak_kN': info['coupler_force_peak'] / 1e3,
        })
        step += 1
    return pd.DataFrame(rows)


def summarize_metrics(df):
    """从轨迹计算汇总指标（对照 evaluate_m1_m3_long 口径）。"""
    speed_all = np.concatenate([df['speed_0'].values, df['speed_1'].values, df['speed_2'].values])
    gap = df['gap_min'].dropna().values
    return {
        'reward': None,  # 此脚本不累计 reward（由 evaluate_m1_m3_long 报告）
        'speed_mean_kmh': float(speed_all.mean()),
        'speed_max_kmh': float(speed_all.max()),
        'over80_pct': float((speed_all > V_MAX * 3.6).mean()) * 100,
        'under40_pct': float((speed_all < V_MIN * 3.6).mean()) * 100,
        'coupler_peak_kN': float(df['coupler_peak_kN'].max()),
        'gap_min_m': float(gap.min()) if len(gap) else None,
        'gap_drift_m': float(gap.max() - gap.min()) if len(gap) else 0.0,
        'collision_steps': int((gap < 5.0).sum()) if len(gap) else 0,
    }


def plot_comparison(dfs, outdir):
    Path(outdir).mkdir(parents=True, exist_ok=True)
    labels = {'coast': 'Coast', 'm1': 'M1 (Coop)', 'm3': 'M3 (No Coop)'}
    colors = {'coast': 'gray', 'm1': 'blue', 'm3': 'red'}
    linestyles = {'coast': ':', 'm1': '-', 'm3': '--'}

    # 图1：间距轨迹
    plt.figure(figsize=(9, 5))
    for mode, df in dfs.items():
        t = df['step'].values
        plt.plot(t, df['gap_min'].values, linestyles[mode], color=colors[mode],
                 linewidth=1.8, label=labels[mode])
    plt.axhline(y=100, color='k', linestyle=':', alpha=0.5, label='Target gap 100m')
    plt.xlabel('Time step')
    plt.ylabel('Min inter-train gap (m)')
    plt.title('Shuozhou line formation gap trajectory (init 65, no disturbance)')
    plt.legend()
    plt.grid(alpha=0.3)
    plt.tight_layout()
    plt.savefig(os.path.join(outdir, 'm1m3_gap_trajectory.png'), dpi=150)
    plt.close()

    # 图2：车钩力峰值轨迹
    plt.figure(figsize=(9, 5))
    for mode, df in dfs.items():
        t = df['step'].values
        plt.plot(t, df['coupler_peak_kN'].values, linestyles[mode], color=colors[mode],
                 linewidth=1.8, label=labels[mode])
    plt.axhline(y=1000, color='k', linestyle=':', alpha=0.8, label='Coupler limit 1000kN')
    plt.xlabel('Time step')
    plt.ylabel('Peak coupler force (kN)')
    plt.title('Shuozhou line coupler force trajectory (init 65)')
    plt.legend()
    plt.grid(alpha=0.3)
    plt.tight_layout()
    plt.savefig(os.path.join(outdir, 'm1m3_coupler_trajectory.png'), dpi=150)
    plt.close()

    # 图3：速度轨迹（列0领航车）
    plt.figure(figsize=(9, 5))
    for mode, df in dfs.items():
        t = df['step'].values
        plt.plot(t, df['speed_0'].values, linestyles[mode], color=colors[mode],
                 linewidth=1.8, label=f'{labels[mode]} lead')
    plt.axhline(y=80, color='k', linestyle=':', alpha=0.6, label='Limit 80km/h')
    plt.axhline(y=40, color='k', linestyle=':', alpha=0.6, label='Limit 40km/h')
    plt.xlabel('Time step')
    plt.ylabel('Lead train speed (km/h)')
    plt.title('Shuozhou line lead train speed trajectory (init 65)')
    plt.legend()
    plt.grid(alpha=0.3)
    plt.tight_layout()
    plt.savefig(os.path.join(outdir, 'm1m3_speed_trajectory.png'), dpi=150)
    plt.close()

    print(f"图表已生成到 {outdir}/: m1m3_gap/coupler/speed_trajectory.png")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--checkpoint', type=str,
                        default='outputs/checkpoints/mappo_fleet_best_cp_seed0.pt')
    parser.add_argument('--outdir', type=str, default='outputs/figures')
    parser.add_argument('--csvdir', type=str, default='outputs/diagnostics')
    parser.add_argument('--table', type=str, default='outputs/m1m3_comparison.md')
    args = parser.parse_args()

    Path(args.csvdir).mkdir(parents=True, exist_ok=True)
    Path(os.path.dirname(args.table)).mkdir(parents=True, exist_ok=True)

    agent = MAPPOAgent(num_drones=NUM_TRAINS, obs_per_drone=11, act_per_drone=1, device='cuda')
    agent.load(args.checkpoint)
    agent.policy.eval()

    dfs = {}
    metrics = {}
    for mode, hier, adj in [('coast', False, 0.0), ('m1', True, 0.1), ('m3', True, 0.0)]:
        env = make_env(hier, adj)
        df = run_traj(env, agent, mode)
        dfs[mode] = df
        csv_path = os.path.join(args.csvdir, f'm1m3_traj_{mode}.csv')
        df.to_csv(csv_path, index=False)
        metrics[mode] = summarize_metrics(df)
        print(f"[{mode}] 已落盘 {csv_path}，steps={len(df)}")

    plot_comparison(dfs, args.outdir)

    # 生成对比表（markdown）
    header = ('| 指标 | 惰行 | M1(协同) | M3(独立δ=0) |')
    sep = ('|:--|:--|:--|:--|')
    rows = []
    m1, m3, coast = metrics['m1'], metrics['m3'], metrics['coast']
    rows.append(f"| 平均速度(km/h) | {coast['speed_mean_kmh']:.1f} | {m1['speed_mean_kmh']:.1f} | {m3['speed_mean_kmh']:.1f} |")
    rows.append(f"| 最大速度(km/h) | {coast['speed_max_kmh']:.1f} | {m1['speed_max_kmh']:.1f} | {m3['speed_max_kmh']:.1f} |")
    rows.append(f"| 超80(%) | {coast['over80_pct']:.1f} | {m1['over80_pct']:.1f} | {m3['over80_pct']:.1f} |")
    rows.append(f"| 低40(%) | {coast['under40_pct']:.1f} | {m1['under40_pct']:.1f} | {m3['under40_pct']:.1f} |")
    rows.append(f"| 车钩力峰值(kN) | {coast['coupler_peak_kN']:.0f} | {m1['coupler_peak_kN']:.0f} | {m3['coupler_peak_kN']:.0f} |")
    rows.append(f"| 间距min(m) | {coast['gap_min_m']:.0f} | {m1['gap_min_m']:.0f} | {m3['gap_min_m']:.0f} |")
    rows.append(f"| 间距漂移(m) | {coast['gap_drift_m']:.0f} | {m1['gap_drift_m']:.0f} | {m3['gap_drift_m']:.0f} |")
    rows.append(f"| 追尾步数 | {coast['collision_steps']} | {m1['collision_steps']} | {m3['collision_steps']} |")
    table = '\n'.join([header, sep] + rows)
    with open(args.table, 'w') as f:
        f.write('# M1 vs M3 vs 惰行 对比表（最终分层架构，固定初态65，无扰动）\n\n')
        f.write(f'> checkpoint: `{args.checkpoint}` | 场景: shuozhou_23800 + 3列 + 限速[40,80]km/h + 3000步\n\n')
        f.write(table + '\n')
    print(f"对比表已写入 {args.table}:")
    print(table)


if __name__ == '__main__':
    main()
