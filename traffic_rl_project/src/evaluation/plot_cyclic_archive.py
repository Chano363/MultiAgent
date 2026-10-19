"""Draw a single archived cyclic-braking trace; never run a simulation."""
import argparse
import hashlib
import json
from pathlib import Path

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--archive', type=Path, required=True)
    parser.add_argument('--solver-result', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--language', choices=['en', 'zh'], default='en')
    args = parser.parse_args()
    zh = args.language == 'zh'
    if zh:
        plt.rcParams['font.sans-serif'] = ['Microsoft YaHei']
        plt.rcParams['axes.unicode_minus'] = False
    trajectory = args.archive / 'trajectory.npz'
    with np.load(trajectory, allow_pickle=False) as data:
        t = data['rows'][:, 0]
        speed = data['vehicle_speeds_mps'][:, 0, :] * 3.6
        ed = -data['loco_ed_force_n'][:, 0, :].sum(axis=1) / 1000
        air = -data['vehicle_air_force_n'][:, 0, :].sum(axis=1) / 1000
        request = data['commands'][:, 0, 1]
        peak = np.abs(data['coupler_interface_force_n'][:, 0, :]).max(axis=1) / 1000
        head = data['heads'][-1, 0]
    solver = json.loads(args.solver_result.read_text(encoding='utf-8'))
    micro_peak = solver['numerical']['live']['internal_peak_kn']
    # Encode the three requests actually present; zero is not asserted to be a
    # physically completed release. Source admission and pressure can lag.
    if not np.all(np.isin(request, [0.0, -0.05, -0.75])):
        raise ValueError('Unexpected model request; update labels explicitly')
    category = np.where(request == -0.75, 2, np.where(request == -0.05, 1, 0))
    fig, axes = plt.subplots(5, 1, figsize=(12, 13.5), sharex=True,
                             gridspec_kw={'height_ratios': [1.25, 1, 1, 0.85, 1.15]})
    text = lambda chinese, english: chinese if zh else english
    axes[0].plot(t, speed.mean(axis=1), label=text('全列平均速度', 'Train mean'), color='#176ba0')
    axes[0].fill_between(t, speed.min(axis=1), speed.max(axis=1), alpha=.22,
                         color='#176ba0', label=text('各车辆速度范围', 'Vehicle speed range'))
    for limit in (40, 80):
        axes[0].axhline(limit, color='#777', ls='--', lw=1,
                       label=text(f'{limit} km/h参考线', f'{limit} km/h reference'))
    axes[0].set_ylim(35, 84)
    axes[0].set_ylabel(text('速度（km/h）', 'Speed (km/h)'))
    axes[0].legend(loc='upper right', ncol=2, fontsize=9)
    axes[1].plot(t, ed, color='#9366a6')
    axes[1].set_ylabel(text('机车电制动力（kN）', 'Locomotive ED force (kN)'))
    axes[2].plot(t, air, color='#e17c35')
    axes[2].set_ylabel(text('全列空气制动力（kN）', 'Total air brake force (kN)'))
    axes[3].step(t, category, where='post', color='#bb5d32')
    axes[3].set_yticks([0, 1, 2], labels=[text('无制动请求', 'No brake request'),
        text('轻减压 50 kPa', 'Cyclic 50 kPa'), text('常用全制动 140 kPa', 'Service 140 kPa')])
    axes[3].set_ylim(-.2, 2.3)
    axes[3].set_ylabel(text('空气制动请求\n（模型档位）', 'Requested model AB notch'))
    axes[4].plot(t, peak, color='#288872', label=text('控制采样时刻最大断面力', 'Control-sample peak interface force'))
    axes[4].axhline(1000, color='#b34040', ls='--', label=text('1000 kN验收线', '1000 kN acceptance limit'))
    axes[4].set_ylim(0, 1120)
    axes[4].set_ylabel(text('车钩力绝对值（kN）', 'Absolute coupler force (kN)'))
    axes[4].legend(fontsize=9, loc='upper right')
    axes[4].text(.015, .78, text(f'内部细步全段峰值：{micro_peak:.2f} kN（汇总值）',
        f'Internal microstep peak: {micro_peak:.2f} kN (summary)'), transform=axes[4].transAxes, fontsize=10)
    for ax in axes:
        ax.grid(alpha=.23)
        ax.set_xlim(0, t[-1])
    axes[-1].set_xlabel(text('运行时间（s）', 'Elapsed time (s)'))
    fig.suptitle(text('万吨108辆单列循环制动：冷起点试验',
                      'Cyclic braking of a single locomotive with 108 wagons'), fontsize=16, y=.985)
    fig.text(.5, .955, text(f'70 km/h起步 | 已运行{t[-1]:.1f} s | 车头到达{head/1000:.2f} km | 非49.6 km全线结果',
        f'70 km/h cold start | {t[-1]:.1f} s | Head at {head/1000:.2f} km | Partial 49.6 km route'),
        ha='center', fontsize=10)
    fig.text(.5, .015, text('电制动力、空气制动力均为模型输出；请求档位不等于已执行压力。原始数据复用，未重跑仿真。',
        'ED and air forces are model outputs; requested notch is not executed pressure. Archived data only.'),
        ha='center', fontsize=9, color='#555')
    fig.tight_layout(rect=(0, .035, 1, .935))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(args.output, dpi=160)
    plt.close(fig)
    args.output.with_suffix('.json').write_text(json.dumps({
        'trajectory': str(trajectory.resolve()),
        'trajectory_sha256': hashlib.sha256(trajectory.read_bytes()).hexdigest(),
        'solver_result': str(args.solver_result.resolve()), 'duration_s': float(t[-1]),
        'scope': '745.2-second archived cold-start prefix, not whole-route acceptance',
        'internal_microstep_peak_kn': micro_peak, 'language': args.language,
        'force_unit': 'kN; ED is locomotive total; air is entire-train total',
        'simulator_rerun': False}, ensure_ascii=False, indent=2), encoding='utf-8')
    print(args.output)


if __name__ == '__main__':
    main()
