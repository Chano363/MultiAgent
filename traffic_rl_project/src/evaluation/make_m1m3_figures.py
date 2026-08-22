"""最终分层架构 M1 vs M3 vs 惰行 —— 论文数据整理 + 可视化（统一口径版）。

复用 evaluate_m1_m3_long.run_episode（return_traj=True），保证 reward / 指标 / 轨迹
全部同一口径（确定性评估、固定初态65、朔黄线3000步、车钩力峰值取累计峰值）。

输出：
- 落盘轨迹 csv（outputs/diagnostics/m1m3_traj_{mode}.csv）
- 对比图（outputs/figures/m1m3_{gap,coupler,speed,reward}_trajectory.png）
- 对比表（outputs/m1m3_comparison.md，含 reward 行，与评估脚本口径一致）
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

from src.evaluation import evaluate_m1_m3_long as ev
from src.algorithms.mappo_agent import MAPPOAgent


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--checkpoint', type=str,
                        default='outputs/checkpoints/mappo_fleet_best_cp_seed0.pt')
    parser.add_argument('--outdir', type=str, default='outputs/figures')
    parser.add_argument('--csvdir', type=str, default='outputs/diagnostics')
    parser.add_argument('--table', type=str, default='outputs/m1m3_comparison.md')
    args = parser.parse_args()

    Path(args.csvdir).mkdir(parents=True, exist_ok=True)
    Path(args.outdir).mkdir(parents=True, exist_ok=True)
    Path(os.path.dirname(args.table)).mkdir(parents=True, exist_ok=True)

    agent = MAPPOAgent(num_drones=ev.NUM_TRAINS, obs_per_drone=11, act_per_drone=1, device='cuda')
    agent.load(args.checkpoint)
    agent.policy.eval()

    dfs = {}
    metrics = {}
    for mode, hier, adj in [('coast', False, 0.0), ('m1', True, 0.1), ('m3', True, 0.0)]:
        env = ev.make_env(65.0 / 3.6, hierarchical=hier, adj_coef=adj)
        res = ev.run_episode(env, agent, mode, 0, deterministic=True, return_traj=True)
        df = res['traj']
        dfs[mode] = df
        df.to_csv(os.path.join(args.csvdir, f'm1m3_traj_{mode}.csv'), index=False)
        # 指标从 run_episode 的 res 取（与 evaluate 同口径），reuse reward
        metrics[mode] = {
            'reward': res['reward'],
            'speed_mean_kmh': res['speed_mean'],
            'speed_max_kmh': res['speed_max'],
            'over80_pct': res['over'],
            'under40_pct': res['under'],
            'coupler_peak_kN': res['coupler_peak'],
            'gap_min_m': res['gap_min'],
            'gap_drift_m': res['gap_drift'],
            'collision_steps': res['collision_steps'],
            'cycles': res['cycles'],
        }
        print(f"[{mode}] reward={res['reward']:+.0f} 车钩力峰值={res['coupler_peak']:.0f}kN "
              f"间距min={res['gap_min']:.0f}m 追尾={res['collision_steps']} 循环制动={res['cycles']}  "
              f"steps={len(df)} 已落盘")

    # 绘制对比图（英文 label，论文用）
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
    plt.axhline(y=0, color='r', linestyle=':', alpha=0.6, label='Rear-end (gap=0)')
    plt.xlabel('Time step')
    plt.ylabel('Min inter-train gap (m)')
    plt.title('Shuozhou line formation gap trajectory (init 65, no disturbance)')
    plt.legend()
    plt.grid(alpha=0.3)
    plt.tight_layout()
    plt.savefig(os.path.join(args.outdir, 'm1m3_gap_trajectory.png'), dpi=150)
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
    plt.savefig(os.path.join(args.outdir, 'm1m3_coupler_trajectory.png'), dpi=150)
    plt.close()

    # 图3：速度轨迹（领航车列0）
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
    plt.savefig(os.path.join(args.outdir, 'm1m3_speed_trajectory.png'), dpi=150)
    plt.close()

    # 图4：累积 reward 轨迹
    plt.figure(figsize=(9, 5))
    for mode, df in dfs.items():
        t = df['step'].values
        plt.plot(t, df['reward_accum'].values, linestyles[mode], color=colors[mode],
                 linewidth=1.8, label=labels[mode])
    plt.xlabel('Time step')
    plt.ylabel('Cumulative reward')
    plt.title('Shuozhou line cumulative reward trajectory (init 65)')
    plt.legend()
    plt.grid(alpha=0.3)
    plt.tight_layout()
    plt.savefig(os.path.join(args.outdir, 'm1m3_reward_trajectory.png'), dpi=150)
    plt.close()
    print(f"图表已生成到 {args.outdir}/: m1m3_gap/coupler/speed/reward_trajectory.png")

    # 生成对比表（markdown，含 reward，与评估口径一致）
    header = '| 指标 | 惰行 | M1(协同) | M3(独立δ=0) |'
    sep = '|:--|:--|:--|:--|'
    coast, m1, m3 = metrics['coast'], metrics['m1'], metrics['m3']
    rows = [
        f"| 累积reward | {coast['reward']:+.0f} | **{m1['reward']:+.0f}** | **{m3['reward']:+.0f}** |",
        f"| 平均速度(km/h) | {coast['speed_mean_kmh']:.1f} | {m1['speed_mean_kmh']:.1f} | {m3['speed_mean_kmh']:.1f} |",
        f"| 最大速度(km/h) | {coast['speed_max_kmh']:.1f} | {m1['speed_max_kmh']:.1f} | {m3['speed_max_kmh']:.1f} |",
        f"| 超80(%) | {coast['over80_pct']:.1f} | {m1['over80_pct']:.1f} | {m3['over80_pct']:.1f} |",
        f"| 低40(%) | {coast['under40_pct']:.1f} | {m1['under40_pct']:.1f} | {m3['under40_pct']:.1f} |",
        f"| 车钩力峰值(kN) | {coast['coupler_peak_kN']:.0f} | {m1['coupler_peak_kN']:.0f} | {m3['coupler_peak_kN']:.0f} |",
        f"| 间距min(m) | {coast['gap_min_m']:.0f} | {m1['gap_min_m']:.0f} | {m3['gap_min_m']:.0f} |",
        f"| 间距漂移(m) | {coast['gap_drift_m']:.0f} | {m1['gap_drift_m']:.0f} | {m3['gap_drift_m']:.0f} |",
        f"| 追尾步数 | {coast['collision_steps']} | **{m1['collision_steps']}** | **{m3['collision_steps']}** |",
        f"| 循环制动次数 | {coast['cycles']} | {m1['cycles']} | {m3['cycles']} |",
    ]
    table = '\n'.join([header, sep] + rows)
    with open(args.table, 'w') as f:
        f.write('# M1 vs M3 vs 惰行 对比表（最终分层架构，固定初态65，无扰动）\n\n')
        f.write(f'> checkpoint: `{args.checkpoint}` | 场景: shuozhou_23800 + 3列 + 限速[40,80]km/h + 3000步\n\n')
        f.write('> 口径：`evaluate_m1_m3_long.run_episode`（确定性 eval_mode，reward=逐步r累积）\n\n')
        f.write(table + '\n')
    print(f"对比表已写入 {args.table}:")
    print(table)


if __name__ == '__main__':
    main()
