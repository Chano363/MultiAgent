"""Plot existing controller traces without rerunning the simulator."""
import argparse
import json
from pathlib import Path

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--before', type=Path, required=True)
    ap.add_argument('--after', type=Path, required=True)
    ap.add_argument('--before-label', default='Before')
    ap.add_argument('--after-label', default='After')
    ap.add_argument('--output', type=Path, required=True)
    ap.add_argument('--title', default='Low-level control under constant downhill grade')
    ap.add_argument('--target-coupler-kn', type=float,
                    help='Optional diagnostic target, distinct from the configured limit')
    ap.add_argument('--max-steps', type=int,
                    help='Plot the same initial sample window from each archive')
    args = ap.parse_args()
    if args.target_coupler_kn is not None and (
            not np.isfinite(args.target_coupler_kn) or args.target_coupler_kn <= 0):
        ap.error('target-coupler-kn must be finite and positive')
    if args.max_steps is not None and args.max_steps < 3:
        ap.error('max-steps must be at least 3')
    with np.load(args.before / 'trajectory.npz') as data:
        num_trains = data['rows'].shape[1] - 5
    panels = 5 if num_trains > 1 else 4
    fig, axes = plt.subplots(panels, 1, figsize=(10, 2.5 * panels), sharex=True)
    limits = set()
    for path, label, color in [(args.before, args.before_label, '#d46b32'),
                               (args.after, args.after_label, '#2576aa')]:
        result_path = path / 'result.json'
        if result_path.exists():
            metadata = json.loads(result_path.read_text(encoding='utf-8'))['metadata']
            limit = metadata.get('env_cfg', {}).get('coupler_force_limit_n')
            if limit is not None:
                limits.add(float(limit) / 1000.0)
        with np.load(path / 'trajectory.npz') as data:
            rows, cmds = data['rows'], data['commands']
            vehicle_max = data['max_vehicle_speed'].max(axis=1) if 'max_vehicle_speed' in data.files else None
        if args.max_steps is not None:
            rows, cmds = rows[:args.max_steps], cmds[:args.max_steps]
            if vehicle_max is not None:
                vehicle_max = vehicle_max[:args.max_steps]
        t = rows[:, 0]
        trains = rows.shape[1] - 5
        for train_i in range(trains):
            velocity = rows[:, 1 + train_i]
            style = ('-', '--', ':')[train_i % 3]
            axes[0].plot(t, velocity * 3.6,
                         label=f'{label}: train {train_i + 1} mean',
                         color=color, linestyle=style)
            axes[1].plot(t[1:], np.diff(velocity) / np.diff(t),
                         color=color, linestyle=style, alpha=0.75)
        if vehicle_max is not None:
            axes[0].plot(t, vehicle_max * 3.6, label=f'{label}: vehicle maximum',
                         color=color, linestyle='-.', alpha=0.65)
        for loco_i in range(cmds.shape[1]):
            axes[2].plot(t, cmds[:, loco_i, 1], color=color,
                         linestyle=('-', '--', ':')[loco_i % 3], alpha=0.65)
        axes[3].plot(t, rows[:, 1 + trains] / 1000, color=color)
        if panels > 4:
            axes[4].plot(t, rows[:, -1], color=color)
    axes[0].set_ylabel('Speed (km/h)')
    axes[0].axhline(80, linestyle=':', color='#666666', label='80 km/h reference')
    axes[1].set_ylabel('Acceleration (m/s²)')
    axes[2].set_ylabel('Requested AB command')
    axes[3].set_ylabel('Peak coupler force (kN)')
    for limit in sorted(limits):
        axes[3].axhline(limit, linestyle='--', color='#666666',
                       label=f'Configured limit: {limit:g} kN')
    if args.target_coupler_kn is not None:
        axes[3].axhline(args.target_coupler_kn, linestyle=':', color='#888888',
                       label=f'Diagnostic target: {args.target_coupler_kn:g} kN')
    if limits or args.target_coupler_kn is not None:
        axes[3].legend(fontsize=8)
    if panels > 4:
        axes[4].set_ylabel('Minimum train gap (m)')
        axes[4].axhline(0, linestyle='--', color='#666666')
    axes[-1].set_xlabel('Time (s)')
    handles, labels = axes[0].get_legend_handles_labels()
    fig.legend(handles, labels, fontsize=8, ncol=2, frameon=False,
               loc='upper center', bbox_to_anchor=(0.5, 0.97))
    for ax in axes:
        ax.grid(alpha=0.2)
    fig.suptitle(args.title, y=0.995)
    fig.tight_layout(rect=(0, 0, 1, 0.91))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(args.output, dpi=160)
    plt.close(fig)


if __name__ == '__main__':
    main()
