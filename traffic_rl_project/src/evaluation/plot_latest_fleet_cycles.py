"""Plot a verified contiguous lineage of archived fleet diagnostics."""
import argparse
import hashlib
import json
from pathlib import Path

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--output', type=Path, required=True)
    args = p.parse_args()
    names = [
        'fleet_prerelease486s_margin_20261024_round66',
        'fleet_early_phase526s_20261024_round67',
        'fleet_early_phase_resume720s_20261024_round68',
        'fleet_leader_threshold_local760s_54_20261024_round78_79',
        'fleet_held_air_balance800s_20261025_round81',
        'fleet_held_air_prereturn900s_20261025_round83',
        'fleet_held_air_smooth940s_20261025_round84',
        'fleet_second_held_air960s_20261025_round88',
        'fleet_second_held_air980s_20261025_round89',
        'fleet_second_held_air1000s_20261025_round90']
    root = Path('outputs/sim_validation/phys_validation')
    blocks, hashes, previous, native = [], {}, None, None
    for name in names:
        d = root/name
        m = json.loads((d/'metadata.json').read_text(encoding='utf-8'))
        initial = m['initial_fleet_manifest']
        if previous is not None and initial['sha256'] != previous['sha256']:
            raise ValueError('Different checkpoint lineage: '+name)
        if native is not None and native != initial['native_source_sha256']:
            raise ValueError('Different native model: '+name)
        native = initial['native_source_sha256']
        previous = json.loads((d/'fleet_state.json').read_text(encoding='utf-8'))
        with np.load(d/'trajectory.npz') as a, np.load(d/'telemetry.npz') as b:
            t = a['rows'][:, 0]
            blocks.append(dict(t=t, speed=a['vehicle_speeds_mps'].mean(axis=2)*3.6,
                ed=b['physical_loco_ed'].reshape(len(t), 3),
                air=-b['vehicle_air_force_n'].sum(axis=2)/1000,
                source=b['ab_source_on'].reshape(len(t), 3),
                gap=b['last_vehicle_centers'][:, :-1]-b['heads'][:, 1:],
                force=np.abs(a['coupler_interface_force_n']).max(axis=2)/1000,
                micro=a['rows'][:, 5]/1000))
        for f in ('trajectory.npz', 'telemetry.npz', 'metadata.json', 'fleet_state.json'):
            hashes[str((d/f).resolve())] = hashlib.sha256((d/f).read_bytes()).hexdigest()
    data = {key: np.concatenate([x[key] for x in blocks]) for key in blocks[0]}
    t = data['t']
    if np.any(abs(np.diff(t)-.1) > 1e-6):
        raise ValueError('Archives must form a unique contiguous history')
    plt.rcParams.update({'font.sans-serif': ['Microsoft YaHei'],
        'axes.unicode_minus': False, 'font.size': 11})
    fig, axes = plt.subplots(6, 1, figsize=(13, 16), sharex=True)
    colors = ['#2878b5', '#e0782b', '#369b75']
    for i, color in enumerate(colors):
        label = f'第{i+1}列'
        for ax, key in ((axes[0], 'speed'), (axes[1], 'ed'), (axes[2], 'air'), (axes[5], 'force')):
            ax.plot(t, data[key][:, i], color=color, lw=1.25, label=label)
        axes[3].fill_between(t, i, i+.65*data['source'][:, i], step='post', color=color, alpha=.75)
    for v in (40, 80):
        axes[0].axhline(v, color='#888', ls='--', lw=.9)
    axes[0].set_ylabel('平均速度（km/h）')
    axes[1].set_ylabel('机车电制动比例')
    axes[1].set_ylim(-.04, 1.08)
    axes[2].set_ylabel('全列空气制动力（kN）')
    axes[3].set_yticks([.32, 1.32, 2.32], ['第1列', '第2列', '第3列'])
    axes[3].set_ylim(-.1, 2.85)
    axes[3].set_ylabel('空气制动源开启')
    axes[4].plot(t, data['gap'][:, 0], color=colors[0], label='第1—2列')
    axes[4].plot(t, data['gap'][:, 1], color=colors[1], label='第2—3列')
    axes[4].axhline(183.3330556, color='#777', ls='--', lw=1, label='目标列距')
    axes[4].set_ylabel('列间距（m）')
    axes[5].plot(t, data['micro'], color='#333', lw=.6, alpha=.65, label='全队内部细步峰值')
    axes[5].axhline(1000, color='#b84040', ls='--', lw=1, label='1000 kN目标')
    axes[5].set_ylabel('最大车钩力绝对值（kN）')
    axes[5].set_ylim(0, max(1070, float(data['micro'].max())*1.08))
    for ax in axes:
        ax.grid(alpha=.18)
        ax.set_xlim(t[0], t[-1])
        if ax.get_legend_handles_labels()[0]:
            ax.legend(loc='lower right', bbox_to_anchor=(1, 1.015),
                      ncol=3, frameon=False, fontsize=10, borderaxespad=0)
    axes[-1].set_xlabel('运行时间（s）')
    fig.suptitle('三列循环制动（420—1000秒）', fontsize=17, y=.992)
    fig.tight_layout(rect=(0, 0, 1, .975), h_pad=1.7)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(args.output, dpi=160)
    plt.close(fig)
    result = dict(window_s=[float(t[0]), float(t[-1])], samples=len(t),
        simulator_rerun=False, full_route_completed=False,
        scope='Verified contiguous experimental lineage with recorded controller interventions; '
              'not a fixed-configuration full-route evaluation. Air-source state is not cylinder pressure.',
        branch_names=names, source_sha256=hashes,
        plot_source_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest())
    args.output.with_suffix('.json').write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps({'output': str(args.output), 'window_s': result['window_s'], 'samples': len(t)}))


if __name__ == '__main__':
    main()
