"""Join a cold prefix and its explicitly linked complete-state continuation."""
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
    parser.add_argument('--prefix', type=Path, required=True)
    parser.add_argument('--continuation', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    result = json.loads((args.continuation/'result.json').read_text(encoding='utf-8'))
    prefix_manifest = json.loads((args.prefix/'run/native_release_state.json').read_text(encoding='utf-8'))
    if result['metadata']['initial_native_manifest']['sha256'] != prefix_manifest['sha256']:
        raise ValueError('Continuation is not linked to this complete prefix state')
    with np.load(args.prefix/'run/trajectory.npz', allow_pickle=False) as p, np.load(
            args.continuation/'trajectory.npz', allow_pickle=False) as c:
        if not len(c['rows']):
            raise ValueError('No completed continuation samples')
        t = np.r_[p['rows'][:, 0], c['rows'][:, 0]]
        speed = np.concatenate((p['vehicle_speeds_mps'][:, 0, :], c['vehicle_speeds_mps']))*3.6
        ed = -np.r_[p['loco_ed_force_n'][:, 0, :].sum(axis=1), c['loco_ed_force_n'].sum(axis=1)]/1000
        pressure = np.concatenate((p['effective_pressure_coefficient'][:, 0, :], c['effective_pressure_coefficient']))
        request = np.r_[p['commands'][:, 0, 1], c['commands'][:, 0, 1]]
        force = np.r_[np.abs(p['coupler_interface_force_n'][:, 0, :]).max(axis=1),
                      np.abs(c['coupler_interface_force_n']).max(axis=1)]/1000
        head, tail = c['vehicle_positions_m'][-1, [0, -1]]/1000
    if not np.all(np.diff(t) > 0):
        raise ValueError('Non-monotonic joined time; do not join unrelated trajectories')
    plt.rcParams['font.sans-serif'] = ['Microsoft YaHei']
    plt.rcParams['axes.unicode_minus'] = False
    fig, axes = plt.subplots(5, 1, figsize=(12, 13), sharex=True)
    axes[0].plot(t, speed.mean(axis=1), label='全列平均速度')
    axes[0].fill_between(t, speed.min(axis=1), speed.max(axis=1), alpha=.2, label='车辆速度范围')
    for limit in (40, 80):
        axes[0].axhline(limit, ls='--', color='#777', lw=1)
    axes[0].legend(loc='lower right', bbox_to_anchor=(1, 1.015),
                   ncol=2, borderaxespad=0, frameon=False)
    axes[0].set_ylabel('速度（km/h）')
    axes[1].plot(t, ed, color='#9366a6')
    axes[1].set_ylabel('机车电制动力（kN）')
    for i, label in [(0, '机车'), (54, '第54辆货车'), (-1, '尾车')]:
        axes[2].plot(t, pressure[:, i], label=label)
    axes[2].legend(loc='lower right', bbox_to_anchor=(1, 1.015),
                   ncol=3, borderaxespad=0, frameon=False)
    axes[2].set_ylabel('有效压力系数\n（无量纲）')
    axes[3].step(t, request, where='post', color='#c57930')
    axes[3].set_ylabel('空气制动请求\n（模型编码）')
    axes[4].plot(t, force, color='#288872')
    axes[4].axhline(1000, ls='--', color='#b34040', label='1000 kN目标')
    axes[4].legend(loc='lower right', bbox_to_anchor=(1, 1.015),
                   borderaxespad=0, frameon=False)
    axes[4].set_ylabel('采样最大断面力（kN）')
    axes[4].set_xlabel('时间（s）')
    for ax in axes:
        ax.grid(alpha=.2)
        ax.set_xlim(0, t[-1])
    complete = result['summary']['full_route_completed']
    fig.suptitle('1机车＋108货车循环制动', fontsize=15)
    fig.tight_layout(rect=(0, 0, 1, .96), h_pad=1.6)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(args.output, dpi=160)
    plt.close(fig)
    paths = [args.prefix/'run/trajectory.npz', args.prefix/'run/native_release_state.json',
             args.continuation/'trajectory.npz', args.continuation/'result.json']
    args.output.with_suffix('.json').write_text(json.dumps({
        'source_sha256': {str(p): hashlib.sha256(p.read_bytes()).hexdigest() for p in paths},
        'full_route_completed': complete,
        'stop_reason': result['summary']['stop_reason'],
        'head_km': float(head), 'tail_km': float(tail),
        'continuation_boundary_s': prefix_manifest['elapsed_s'],
        'scope': 'same complete online history; not fleet or physical calibration'},
        ensure_ascii=False, indent=2), encoding='utf-8')
    print(args.output)


if __name__ == '__main__':
    main()
