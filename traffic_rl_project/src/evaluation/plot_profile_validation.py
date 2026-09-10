"""【2026-09-05】线路剖面物理验证图（35km 设计剖面 + 朔黄线真实剖面）。

对每个剖面输出：
  - fig_grade_{name}.png      坡度(‰)-里程(km) 剖面图
  - fig_cyclic_{name}.png     循环制动物理曲线（速度-时间+AB阴影 / 速度-里程 / 车钩力峰值）

范式同 src/evaluation/plot_physical_curves.py 的 fig_phys3（赵紫宁2022 图3-18）。
输出到 outputs/phys_validation/profiles_{时间戳}/。

用法（WSL traffic_rl）：
    python src/evaluation/plot_profile_validation.py
"""
import sys
import json
import logging
from pathlib import Path
from datetime import datetime


import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

from src.utils.plot_style import setup_cjk_font
from src.train_dynamics.braking import AirBrakeNotch
from src.train_dynamics.grade_profile import PROFILES

setup_cjk_font(verbose=True)
logging.basicConfig(level=logging.INFO, format='%(message)s')
logger = logging.getLogger('ProfileCurves')

SEED = 0
PROFILES_TO_RUN = ['shuozhou_23800', 'long_downhill_35km', 'long_downhill_50km']
# 各剖面循环制动仿真步数（秒×10）。50km 加长跑更远以覆盖全程/出坡剧变点。
RUNTIME_STEPS = {'long_downhill_50km': 25000, 'default': 8000}
LABELS = {
    'shuozhou_23800': '朔黄线 23.8km（真实剖面）',
    'long_downhill_35km': '35km 设计剖面（synthetic）',
    'long_downhill_50km': '50km 设计剖面（synthetic·剧变点/边界）',
}


def save_fig(fig, path):
    try:
        fig.tight_layout()
    except Exception:
        pass
    fig.savefig(path, dpi=150, bbox_inches='tight')
    plt.close(fig)
    logger.info('已生成 %s', path.name)


def make_env(grade_profile, init_speed, max_steps):
    from src.environments.train_env import TrainFormationEnv
    cfg = {
        'consist_preset': '10kt_1plus0',
        'grade_profile': grade_profile,
        'dt': 0.1,
        'max_steps': max_steps,
        'enable_safety': True,
        'sync_loco_brake': True,
    }
    env = TrainFormationEnv(cfg)
    env.reset(options={'speed': init_speed})
    return env


def fig_grade(profile, name, out):
    """纵断面示意图（论文图5-1 范式）：X=公里标(km)，Y=相对高程(m)，蓝色填充+变坡点标注。"""
    segs = profile.segments
    seg_starts = [s.start_m for s in segs]
    L = float(max(seg_starts))
    dx = 100.0
    x = np.arange(0.0, L + dx * 0.5, dx)
    g = np.array([profile.grade_at(px) for px in x])          # 无量纲坡度（负=下坡）
    elev = np.concatenate([[0.0], np.cumsum(g[1:] * dx)])     # 相对首端高程（下坡为负）
    xkm = x / 1000.0
    fig, ax = plt.subplots(figsize=(9, 4))
    ax.plot(xkm, elev, color='#1f3b73', lw=1.4)
    ax.fill_between(xkm, elev, elev.min() - 40, color='#7ba3d6', alpha=0.35)
    # 变坡点里程标记
    for s in segs[1:]:
        xi = s.start_m / 1000.0
        ei = elev[int(round(s.start_m / dx))]
        ax.plot(xi, ei, 'o', color='#c0392b', ms=4)
        ax.axvline(xi, color='gray', lw=0.5, ls=':', alpha=0.5)
        ax.annotate(f'K{xi:.1f} km', (xi, ei), xytext=(xi, elev.min() - 55),
                    fontsize=7, ha='center', color='#444')
    # 每段坡度‰标注（线段中点上方）
    for i, s in enumerate(segs):
        x0 = s.start_m
        x1 = segs[i + 1].start_m if i + 1 < len(segs) else L
        if x1 - x0 < dx:          # 跳过零/超短段（如出坡尾段），避免标注重叠
            continue
        xm = (x0 + x1) / 2.0
        em = elev[int(round(x0 / dx))] + 0.5 * (elev[int(round(x1 / dx))] - elev[int(round(x0 / dx))])
        ax.annotate(f'{s.grade_permille:.1f}‰', (xm / 1000.0, em - 10),
                    fontsize=7, ha='center', color='#0b3d91')
    ax.set_xlim(0, L / 1000.0)
    ax.set_ylim(elev.min() - 120, elev.max() + 60)
    ax.set_xlabel('公里标 (km)')
    ax.set_ylabel('相对高程 (m)')
    ax.set_title(f'{LABELS.get(name, name)}长大下坡区段纵断面示意图')
    ax.grid(alpha=0.2)
    save_fig(fig, out)


def run_cyclic(grade_profile, max_steps=8000, init_speed=65.0 / 3.6):
    env = make_env(grade_profile, init_speed, max_steps)  # 先加载 train_env，解决循环导入
    from src.controllers.low_level_controller import TrainLowLevelController
    n_veh = env.num_vehicles
    ctrl = TrainLowLevelController(num_vehicles=n_veh, dt=0.1,
                                   coupler_force_limit_n=env.coupler_force_limit_n,
                                   enforce_coupler=True)
    ctrl.reset()
    V_MAX = 80.0 / 3.6
    V_MIN = 40.0 / 3.6
    t = np.zeros(max_steps)
    v_kmh = np.zeros(max_steps)
    dist = np.zeros(max_steps)
    ab_active = np.zeros(max_steps, dtype=int)
    coupler_peak_kn = np.zeros(max_steps)
    coupler_mat = np.zeros((max_steps, n_veh - 1))
    throttle = np.zeros(max_steps)
    for k in range(max_steps):
        t[k] = env.dynamics.time
        v_kmh[k] = env.dynamics.vel[0] * 3.6
        dist[k] = env.dynamics.pos[0]
        st = env.dynamics.air_brake_state()
        ab_active[k] = int(any(nr != AirBrakeNotch.RELEASE for nr in st))
        c = env.dynamics.coupler_interface_forces()
        coupler_mat[k] = c
        coupler_peak_kn[k] = float(np.max(np.abs(c))) / 1e3 if len(c) else 0.0
        actions = ctrl.get_action_cyclic_braking(env, V_MAX, V_MIN,
                                                 brake_notch=-0.8, release_throttle=0.5)
        throttle[k] = float(actions[0])
        env.step(actions)
    return dict(t=t, v_kmh=v_kmh, dist=dist, ab_active=ab_active,
                coupler_peak_kn=coupler_peak_kn, coupler_mat=coupler_mat,
                throttle=throttle)


def fig_cyclic(data, name, out):
    label = LABELS.get(name, name)
    t = data['t']
    v_kmh = data['v_kmh']
    dist = data['dist'] / 1000.0
    ab = data['ab_active'].astype(bool)
    cpk = data['coupler_peak_kn']
    BLUE, GREEN, RED = '#1f77b4', '#2ca02c', '#c0504d'
    fig, axes = plt.subplots(3, 1, figsize=(8.5, 8.5))
    # 子图1：速度-时间
    ax = axes[0]
    ax.plot(t / 60.0, v_kmh, color=BLUE, lw=1.4, label='速度')
    edges = np.flatnonzero(np.diff(np.r_[0, ab.astype(int), 0]))
    ab_plotted = False
    for i in range(0, len(edges), 2):
        ax.axvspan(t[edges[i]] / 60.0, t[edges[i + 1] - 1] / 60.0,
                   color='red', alpha=0.13, label=('空气制动' if not ab_plotted else None))
        ab_plotted = True
    ax.axhline(80, color='k', ls='--', lw=0.9); ax.axhline(40, color='k', ls='--', lw=0.9)
    ax.text(t[0] / 60.0 + 0.2, 81.5, '限速 80 km/h', fontsize=7)
    ax.text(t[0] / 60.0 + 0.2, 41.5, '限速 40 km/h', fontsize=7)
    ax.set_xlabel('时间 (min)'); ax.set_ylabel('速度 (km/h)')
    ax.set_title('速度-时间', fontsize=10)
    ax.legend(fontsize=8, loc='upper left'); ax.grid(alpha=0.3)
    # 子图2：速度-里程（独立轴）
    ax = axes[1]
    ax.plot(dist, v_kmh, color=GREEN, lw=1.3)
    ax.axhline(80, color='k', ls='--', lw=0.9); ax.axhline(40, color='k', ls='--', lw=0.9)
    ax.set_xlabel('里程 (km)'); ax.set_ylabel('速度 (km/h)')
    ax.set_title('速度-里程', fontsize=10)
    ax.grid(alpha=0.3)
    # 子图3：车钩力峰值-时间
    ax = axes[2]
    ax.plot(t / 60.0, cpk, color=RED, lw=1.2, label='列内车钩力峰值')
    ax.axhline(1000, color='r', ls='--', lw=1.0)
    ax.text(t[0] / 60.0 + 0.2, 1000 * 1.03, '1000 kN 安全限值', fontsize=7, color='red')
    ax.set_ylim(0, max(cpk.max() * 1.15, 1100))
    ax.set_xlabel('时间 (min)'); ax.set_ylabel('车钩力峰值 (kN)')
    ax.set_title('车钩力峰值', fontsize=10)
    ax.grid(alpha=0.3)
    fig.suptitle(f'{label}长大下坡循环制动仿真', fontsize=12)
    n_ab_seg = int(np.sum(np.diff(np.r_[0, ab.astype(int)]) > 0))
    logger.info('[%s] 速度 [%.0f,%.0f] km/h，车钩力峰值 %.0f kN，空气制动段 %d 次，里程 %.1f km',
                name, float(v_kmh.min()), float(v_kmh.max()), float(cpk.max()),
                n_ab_seg, float(dist.max()))
    save_fig(fig, out)


def main():
    import pandas as pd
    np.random.seed(SEED)
    stamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    outdir = Path('outputs') / 'phys_validation' / f'profiles_{stamp}'
    outdir.mkdir(parents=True, exist_ok=True)

    results = {}
    for name in PROFILES_TO_RUN:
        profile = PROFILES[name]()
        fig_grade(profile, name, outdir / f'fig_grade_{name}.png')
        max_steps = RUNTIME_STEPS.get(name, RUNTIME_STEPS['default'])
        logger.info('== 循环制动 %s （%d 步）==', name, max_steps)
        data = run_cyclic(name, max_steps=max_steps)
        fig_cyclic(data, name, outdir / f'fig_cyclic_{name}.png')
        pd.DataFrame({
            't': data['t'], 'v_kmh': data['v_kmh'], 'dist_m': data['dist'],
            'ab_active': data['ab_active'], 'coupler_peak_kn': data['coupler_peak_kn'],
            'throttle': data['throttle'],
        }).to_csv(outdir / f'traj_cyclic_{name}.csv', index=False)
        np.savez_compressed(outdir / f'coupler_matrix_{name}.npz',
                            coupler_mat=data['coupler_mat'])
        results[name] = {
            'steps': len(data['t']),
            'v_min_kmh': round(float(data['v_kmh'].min()), 1),
            'v_max_kmh': round(float(data['v_kmh'].max()), 1),
            'coupler_peak_kn': round(float(data['coupler_peak_kn'].max()), 0),
            'dist_km': round(float(data['dist'].max()) / 1e3, 1),
        }

    meta = {
        'seed': SEED,
        'timestamp': stamp,
        'section': '线路剖面物理验证图',
        'profiles': PROFILES_TO_RUN,
        'labels': LABELS,
        'config': {'consist': '10kt_1plus0', 'dt': 0.1, 'max_steps': 8000,
                   'init_speed_kmh': 65,
                   'v_range_kmh': [40, 80], 'brake_notch': -0.8, 'release_throttle': 0.5},
        'results': results,
        'note': '35km 剖面为 synthetic（设计/外推验证线，非真实线路纵断面）；朔黄线为 Zhang2024 真实线路。',
    }
    (outdir / 'run_meta.json').write_text(json.dumps(meta, ensure_ascii=False, indent=2),
                                          encoding='utf-8')
    logger.info('全部完成，输出目录 %s', outdir)


if __name__ == '__main__':
    main()