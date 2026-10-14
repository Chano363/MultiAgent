"""Plot existing controller traces without rerunning the simulator."""
import argparse
from pathlib import Path

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--before', type=Path, required=True)
    ap.add_argument('--after', type=Path, required=True)
    ap.add_argument('--output', type=Path, required=True)
    ap.add_argument('--title', default='Low-level control under constant downhill grade')
    args = ap.parse_args()
    with np.load(args.before / 'trajectory.npz') as data:
        num_trains = data['rows'].shape[1] - 5
    panels = 5 if num_trains > 1 else 4
    fig, axes = plt.subplots(panels, 1, figsize=(10, 2.5 * panels), sharex=True)
    for path, label, color in [(args.before, 'Before', '#d46b32'), (args.after, 'After', '#2576aa')]:
        with np.load(path / 'trajectory.npz') as data:
            rows, cmds = data['rows'], data['commands']
            vehicle_max = data['max_vehicle_speed'].max(axis=1) if 'max_vehicle_speed' in data.files else None
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
    axes[3].axhline(1000, linestyle='--', color='#666666', label='1000 kN')
    if panels > 4:
        axes[4].set_ylabel('Minimum train gap (m)')
        axes[4].axhline(0, linestyle='--', color='#666666')
    axes[-1].set_xlabel('Time (s)')
    axes[0].legend(fontsize=8, ncol=2)
    for ax in axes:
        ax.grid(alpha=0.2)
    fig.suptitle(args.title)
    fig.tight_layout()
    fig.savefig(args.output, dpi=160)
    plt.close(fig)


if __name__ == '__main__':
    main()
