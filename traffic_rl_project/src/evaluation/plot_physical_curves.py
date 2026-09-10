"""【2026-09-05】仿真器物理曲线验证图（向导师展示，不跑 RL）。

用脚本驱动真实仿真（TrainFormationEnv + TrainDynamics），把空气制动波传播、
制动力建立、长大下坡循环制动速度-时间、缓解后车钩力冲击、MT-2 缓冲器迟滞环等物理
机制画成论文范式曲线。对齐赵紫宁2022《重载列车空气制动精细建模与操纵优化》图2-1/2-2/2-5/3-4/3-6/3-18。

产出 7 图到 outputs/phys_validation/run_{时间戳}/：
    fig_phys1_brake_wave.png        制动波时空传播（制动波 + 缓解波）
    fig_phys2_brake_build.png       空气制动力建立过程（响应/暂态/稳态）
    fig_phys3_cyclic_shuozhou.png   朔黄线长大下坡循环制动（速度-时间/速度-里程/车钩力）
    fig_phys4_release_impulse.png   缓解后车钩力冲击放大窗
    fig_phys5_release_curve.png     缓解（缓释）曲线：制动力衰减 + 缓解后车钩力最大
    fig_phys6_hysteresis.png  MT-2 缓冲器加载-卸载迟滞环（R0 统一 MT-2，QKX100 已移除）
    fig_phys7_loco_characteristics.png  机车牵引/电制动特性外包络

用法（WSL traffic_rl）：
    python src/evaluation/plot_physical_curves.py
"""
import sys
import os
import json
import logging
from pathlib import Path
from datetime import datetime


import numpy as np

from src.utils.seed import set_seed
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

from src.utils.plot_style import setup_cjk_font
from src.train_dynamics.braking import AirBrakeNotch
from src.train_dynamics.tractive import tractive_force
from src.train_dynamics.coupler import coupler_force
import src.train_dynamics.braking as brak

setup_cjk_font(verbose=True)
logging.basicConfig(level=logging.INFO, format='%(message)s')
logger = logging.getLogger('PhysCurves')

SEED = 0




def make_env(consist_preset='10kt_1plus0', grade=None, grade_profile=None,
             max_steps=100000, init_speed=0.0):
    from src.environments.train_env import TrainFormationEnv
    cfg = {
        'consist_preset': consist_preset,
        'dt': 0.1,
        'max_steps': max_steps,
        'enable_safety': True,
        'sync_loco_brake': True,
    }
    if grade_profile:
        cfg['grade_profile'] = grade_profile
    elif grade is not None:
        cfg['grade'] = grade
    env = TrainFormationEnv(cfg)
    env.reset(options={'speed': init_speed})
    return env


def save_fig(fig, path):
    try:
        fig.tight_layout()
    except Exception:
        pass
    fig.savefig(path, dpi=150, bbox_inches='tight')
    plt.close(fig)
    logger.info('已生成 %s', path.name)


# ---------------------------------------------------------------------------
# 图1/图2/图5 共用场景：平坡，SERVICE 制动建立 -> 缓解波释放
# ---------------------------------------------------------------------------
def run_brake_release(init_speed=70.0 / 3.6, brake_s=35.0, release_s=50.0,
                      brake_throttle=-0.5, release_throttle=0.0, dt=0.1):
    env = make_env(grade=0.0, init_speed=init_speed)
    n_b = int(brake_s / dt)
    n_r = int(release_s / dt)
    n_steps = n_b + n_r
    n_veh = env.num_vehicles
    t = np.zeros(n_steps)
    forces = np.zeros((n_steps, n_veh))      # 逐节空气制动力（含符号）
    active = np.zeros((n_steps, n_veh), dtype=int)
    coupler = np.zeros((n_steps, n_veh - 1))  # 单钩断面力
    for k in range(n_steps):
        th = brake_throttle if k < n_b else release_throttle
        t[k] = env.dynamics.time
        forces[k] = env.dynamics._air_braking_forces()
        active[k] = [1 if nr != AirBrakeNotch.RELEASE else 0
                     for nr in env.dynamics.air_brake_state()]
        coupler[k] = env.dynamics.coupler_interface_forces()
        env.step(np.full(n_veh, th))
    return dict(t=t, forces=forces, active=active, coupler=coupler)


def fig_brake_wave(data, out):
    t, active = data['t'], data['active']
    fig, ax = plt.subplots(figsize=(10, 4.5))
    im = ax.imshow(active.T, aspect='auto', origin='lower', cmap='Blues',
                   extent=[t[0], t[-1], 0, active.shape[1]], interpolation='nearest')
    ax.set_xlabel('Time (s)')
    ax.set_ylabel('Vehicle index (0=loco, %d=tail)' % (active.shape[1] - 1))
    ax.set_title('Air-brake / release wave propagation (10 kt 1+0, 200 m/s)')
    ax.text(t[0] + 1, 0.4, 'brake wave', color='#08306b', fontsize=10, fontweight='bold')
    ax.annotate('release wave (head → tail)', xy=(t[0] + 0.8, 60),
                xytext=(0.02, 0.96), textcoords='axes fraction',
                color='#08519c', fontsize=10)
    fig.colorbar(im, ax=ax, label='Air brake active (0/1)')
    ax.grid(alpha=0.3)
    save_fig(fig, out)


def fig_brake_build(data, out):
    t = data['t']
    forces = data['forces']
    subset = [0, 1, 10, 25, 50, 75, data['forces'].shape[1] - 1]
    labels = {0: ' (loco)', subset[-1]: f' (tail #{subset[-1]})'}
    fig, axes = plt.subplots(2, 1, figsize=(10, 7), sharex=True)
    ax = axes[0]
    for i in subset:
        ax.plot(t, forces[:, i] / 1e3, lw=1.4, label=f'Car #{i}' + labels.get(i, ''))
    ax.set_ylabel('Per-vehicle brake force (kN)')
    ax.set_title('Air-brake build-up: wave arrival → cylinder pressure → saturation (SERVICE)')
    ax.legend(fontsize=8, ncol=2)
    ax.grid(alpha=0.3)
    ax = axes[1]
    total = np.sum(forces, axis=1) / 1e3
    ax.plot(t, total, color='#c0504d', lw=1.8)
    ax.set_ylabel('Total brake force (kN)')
    ax.set_xlabel('Time (s)')
    ax.axvspan(t[0], t[0] + 2.0, color='gray', alpha=0.12)
    ax.text(t[0] + 0.4, total.max() * 0.95, 'response', fontsize=9, color='dimgray')
    ax.axvline(t[int(0.35 * len(t))], color='k', ls=':', lw=1.0)
    ax.text(t[int(0.35 * len(t))] + 1, total.max() * 0.95, 'transient', fontsize=9, color='dimgray')
    ax.text(t[int(0.7 * len(t))], total.max() * 0.95, 'steady', fontsize=9, color='dimgray')
    ax.grid(alpha=0.3)
    build = np.sum(np.abs(forces), axis=1)
    build_peak = float(np.max(build)) / 1e3
    logger.info('[self-check] total SERVICE brake force peak = %.0f kN (theory 31/N×100 ≈ 3100)', build_peak)
    save_fig(fig, out)


def fig_release_curve(data, out):
    t = data['t']
    forces = data['forces']
    coupler = data['coupler']
    n_veh = forces.shape[1]
    # 制动/缓解分界：active 全部归零的时刻
    active = data['active']
    alloff = np.where(np.all(active == 0, axis=1))[0]
    release_start = float(t[alloff[0]]) if len(alloff) else 0.0
    mid = n_veh // 2 - 1  # 中间车钩断面
    mask = (t >= release_start - 2) & (t <= release_start + 25)
    tg = t[mask]
    subset = [0, 1, 10, 25, 50, 75, n_veh - 1]
    fig, axes = plt.subplots(2, 1, figsize=(10, 7), sharex=True)
    ax = axes[0]
    for i in subset:
        ax.plot(tg, forces[:, i][mask] / 1e3, lw=1.3, label=f'Car #{i}')
    ax.axvline(release_start, color='r', ls='--', lw=1.0)
    ax.text(release_start + 0.5, ax.get_ylim()[1] * 0.9, 'release start', color='red', fontsize=9)
    ax.set_ylabel('Per-vehicle brake force (kN)')
    ax.set_title('Release: release wave decays force head → tail')
    ax.legend(fontsize=8, ncol=2)
    ax.grid(alpha=0.3)
    ax = axes[1]
    ax.plot(tg, np.abs(coupler[:, mid][mask]) / 1e3, color='#2d6a9f', lw=1.6,
            label=f'Middle coupler force (car {mid}-{mid+1})')
    peak = np.max(np.abs(coupler[:, mid][mask]))
    ip = int(np.argmax(np.abs(coupler[:, mid][mask])))
    ax.plot(tg[ip], peak / 1e3, 'o', color='#c0504d')
    ax.annotate(f'Peak coupler {peak/1e3:.0f} kN', xy=(tg[ip], peak / 1e3),
                xytext=(0.02, 0.90), textcoords='axes fraction', fontsize=9,
                arrowprops=dict(arrowstyle='->', color='#c0504d'))
    ax.axhline(1000, color='red', ls='--', lw=1.0)
    ax.text(tg.min(), 1015, '1000 kN safe limit', fontsize=8, color='red')
    ax.set_ylim(0, max((peak / 1e3) * 1.25, 1100))
    ax.set_ylabel('Coupler force (kN)')
    ax.set_xlabel('Time (s)')
    ax.legend(fontsize=8)
    ax.grid(alpha=0.3)
    logger.info('[self-check] middle coupler peak during release = %.0f kN', peak / 1e3)
    save_fig(fig, out)


# ---------------------------------------------------------------------------
# 图3/图4 共用场景：朔黄线长大下坡循环制动
# ---------------------------------------------------------------------------
def run_cyclic_shuozhou(max_steps=15000, init_speed=65.0 / 3.6, dt=0.1):
    from src.controllers.low_level_controller import TrainLowLevelController
    env = make_env(grade_profile='shuozhou_23800',
                   max_steps=max_steps, init_speed=init_speed)
    n_veh = env.num_vehicles
    ctrl = TrainLowLevelController(num_vehicles=n_veh, dt=dt,
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
        ab_state = env.dynamics.air_brake_state()
        ab_active[k] = int(any(nr != AirBrakeNotch.RELEASE for nr in ab_state))
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


def fig_cyclic(data, out):
    label = 'Shuohuang Line 23.8 km (real profile)'
    t = data['t']
    v_kmh = data['v_kmh']
    dist = data['dist'] / 1000.0
    ab = data['ab_active'].astype(bool)
    cpk = data['coupler_peak_kn']
    BLUE, GREEN, RED = '#1f77b4', '#2ca02c', '#c0504d'
    fig, axes = plt.subplots(3, 1, figsize=(8.5, 8.5))
    ax = axes[0]
    ax.plot(t / 60.0, v_kmh, color=BLUE, lw=1.4, label='Speed')
    edges = np.flatnonzero(np.diff(np.r_[0, ab.astype(int), 0]))
    ab_plotted = False
    for i in range(0, len(edges), 2):
        ax.axvspan(t[edges[i]] / 60.0, t[edges[i + 1] - 1] / 60.0,
                   color='red', alpha=0.13, label=('Air braking' if not ab_plotted else None))
        ab_plotted = True
    ax.axhline(80, color='k', ls='--', lw=0.9); ax.axhline(40, color='k', ls='--', lw=0.9)
    ax.text(t[0] / 60.0 + 0.2, 81.5, 'Speed limit 80 km/h', fontsize=7)
    ax.text(t[0] / 60.0 + 0.2, 41.5, 'Speed limit 40 km/h', fontsize=7)
    ax.set_xlabel('Time (min)'); ax.set_ylabel('Speed (km/h)')
    ax.set_title('Speed vs time', fontsize=10)
    ax.legend(fontsize=8, loc='upper left'); ax.grid(alpha=0.3)
    ax = axes[1]
    ax.plot(dist, v_kmh, color=GREEN, lw=1.3)
    ax.axhline(80, color='k', ls='--', lw=0.9); ax.axhline(40, color='k', ls='--', lw=0.9)
    ax.set_xlabel('Distance (km)'); ax.set_ylabel('Speed (km/h)')
    ax.set_title('Speed vs distance', fontsize=10)
    ax.grid(alpha=0.3)
    ax = axes[2]
    ax.plot(t / 60.0, cpk, color=RED, lw=1.2, label='Peak coupler force (all sections)')
    cmat = data.get('coupler_mat')
    if cmat is not None and cmat.ndim == 2 and cmat.shape[1] > 0:
        # 断面0 = 机车-货车连挂钩（MT-2，2026-09-07 统一后所有耦合同一模型）
        head_mt2 = np.abs(cmat[:, 0]) / 1e3
        ax.plot(t / 60.0, head_mt2, color='#ff7f0e', lw=1.3, ls='--',
                label='Head coupler (loco-freight)')
        if np.nanmax(head_mt2) > 1e-3:
            ax.text(t[0] / 60.0 + 0.2, np.nanmax(head_mt2) * 0.30,
                    'Head MT-2', color='#ff7f0e', fontsize=8)
    ax.axhline(1000, color='r', ls='--', lw=1.0)
    ax.text(t[0] / 60.0 + 0.2, 1000 * 1.03, '1000 kN safe limit', fontsize=7, color='red')
    ax.set_ylim(0, max(cpk.max() * 1.15, 1100))
    ax.set_xlabel('Time (min)'); ax.set_ylabel('Coupler force peak (kN)')
    ax.set_title('Coupler force peak', fontsize=10)
    ax.legend(fontsize=8, loc='upper right')
    ax.grid(alpha=0.3)
    fig.suptitle(f'{label} · cyclic braking simulation', fontsize=12)
    n_ab_seg = int(np.sum(np.diff(np.r_[0, ab.astype(int)]) > 0))
    logger.info('[self-check] cyclic: v range [%.0f, %.0f] km/h, coupler peak %.0f kN, '
                '%d brake segments, %.1f km', float(v_kmh.min()), float(v_kmh.max()),
                float(cpk.max()), n_ab_seg, float(dist.max()))
    save_fig(fig, out)


def fig_release_impulse(data, out):
    t = data['t']
    ab = data['ab_active'].astype(bool)
    cmat = data['coupler_mat']
    # 全列所有车钩的最大断面力事件
    gi, vi = np.unravel_index(np.argmax(np.abs(cmat)), cmat.shape)
    t0 = t[gi]
    lo = max(gi - 300, 0)
    hi = min(gi + 300, len(t))
    window = np.arange(lo, hi)
    tg = t[window]
    fig, ax = plt.subplots(figsize=(10, 5))
    ax.plot(tg / 60.0, np.abs(cmat[window, vi]) / 1e3, color='#2d6a9f', lw=1.6,
            label=f'Coupler force (car {vi}-{vi+1})')
    peak = float(np.abs(cmat).max()) / 1e3
    ax.plot(t0 / 60.0, peak, 'o', color='#c0504d')
    ax.annotate(f'Peak impact {peak:.0f} kN', xy=(t0 / 60.0, peak),
                xytext=(0.02, 0.90), textcoords='axes fraction', fontsize=9,
                arrowprops=dict(arrowstyle='->', color='#c0504d'))
    # 【2026-09-07 ADR】全列统一 MT-2：头钩（断面0）即普通 MT-2 耦合，
    # 叠加展示该冲击窗内受力响应
    if cmat.ndim == 2 and cmat.shape[1] > 0:
        head_mt2 = np.abs(cmat[window, 0]) / 1e3
        ax.plot(tg / 60.0, head_mt2, color='#ff7f0e', lw=1.3, ls='--',
                label='Head coupler (loco-freight, MT-2)')
        ax.legend(fontsize=9)
    # 空气制动作用段阴影
    abw = ab[window]
    edges = np.flatnonzero(np.diff(np.r_[0, abw.astype(int), 0]))
    for k in range(0, len(edges), 2):
        ax.axvspan(tg[edges[k]] / 60.0, tg[edges[k + 1] - 1] / 60.0, color='red', alpha=0.15)
    ax.axhline(1000, color='r', ls='--', lw=1.0)
    ax.text(tg.min() / 60 + 0.02, 1015, '1000 kN', fontsize=8, color='red')
    ax.set_ylim(0, max(peak * 1.25, 1200))
    ax.set_xlabel('Time (min)'); ax.set_ylabel('Coupler force (kN)')
    ax.set_title('Longitudinal impact window (red = air braking)')
    ax.legend(fontsize=9)
    ax.grid(alpha=0.3)
    logger.info('[self-check] single-train longitudinal impact peak coupler = %.0f kN '
                '(release wave), compare to 1000 kN)', peak)
    save_fig(fig, out)


# ---------------------------------------------------------------------------
# 图6：MT-2 缓冲器加载-卸载迟滞环（静态标量，R0 统一 MT-2）
# ---------------------------------------------------------------------------
def _coupler_force_kwargs(p):
    """把 CouplerParams 字段映射为 coupler_force 关键字（MT-2）。
    【2026-09-07 ADR】QKX100 专属参数（两段刚度/胶泥幂律）已随统一移除。
    """
    return dict(
        stiffness=p.stiffness,
        damping=p.damping,
        free_length=p.free_length_m,
        coupler_gap=p.coupler_gap_m,
        max_impulse=p.max_impulse_n,
        preload_n=p.preload_n,
        friction_n=p.friction_n,
        friction_v_eps=p.friction_v_eps,
        stroke_m=p.stroke_m,
        rigid_stiffness_nm=p.rigid_stiffness_nm,
        unload_stiffness_ratio=p.unload_stiffness_ratio,
        friction_static_n=p.friction_static_n,
        friction_v_er=p.friction_v_er,
    )


def _hysteresis_loop(p):
    """在 |e|<=行程 内扫准静态加载/卸载迟滞环（压缩+拉伸两象限）。

    方向约定（与 coupler_force 语义一致）：
      dv = v_front - v_back；"加载"⟺ s_e·dv<0：
        压缩(e>0, s_e>0)加载 → dv<0 → dv_sign=-1；压缩卸载 → dv_sign=+1。
        拉伸(e<0, s_e<0)加载 → dv>0 → dv_sign=+1；拉伸卸载 → dv_sign=-1。
    F(e,±1) 里 v_back = -dv_sign（前车静止）。
    """
    from src.train_dynamics.coupler import coupler_force
    free = p.free_length_m
    kw = _coupler_force_kwargs(p)
    amp = float(p.stroke_m)          # 扫到缓冲器最大行程（83mm），止于刚性限位前

    def F(e, dv_sign):
        x_back = e - free
        return coupler_force(0.0, 0.0, x_back, -dv_sign, **kw)

    e_c = np.linspace(0.0, amp, 400)          # 压缩：加载 dv<0 / 卸载 dv>0
    load_c = np.array([F(x, -1.0) for x in e_c])
    unload_c = np.array([F(x, 1.0) for x in e_c[::-1]])
    e_t = np.linspace(0.0, -amp, 400)         # 拉伸：加载 dv>0 / 卸载 dv<0
    load_t = np.array([F(x, 1.0) for x in e_t])
    unload_t = np.array([F(x, -1.0) for x in e_t[::-1]])
    return dict(e_c=e_c, e_c_un=e_c[::-1], load_c=load_c, unload_c=unload_c,
                e_t=e_t, e_t_un=e_t[::-1], load_t=load_t, unload_t=unload_t)


def fig_coupler_hysteresis(out):
    """图6：MT-2 缓冲器加载-卸载迟滞环（R0 统一 MT-2，单面板）。

    【2026-09-07 ADR】QKX100 弹胶泥分区已移除，全列统一 MT-2（A 范式）。
    本图展示 MT-2 特征：Stribeck 摩擦迟滞环、预压力 200 kN、2270 kN 饱和上限。
    """
    from src.train_dynamics.params import CouplerParams
    specs = [('MT-2 · 摩擦式弹簧缓冲器（全列统一）', CouplerParams())]
    fig, ax = plt.subplots(figsize=(8, 6.5))
    for title, p in specs:
        lp = _hysteresis_loop(p)
        ax.plot(lp['e_c'] * 1000, lp['load_c'] / 1e3, color='#1f77b4', lw=1.6,
                label='Loading (compression)')
        ax.plot(lp['e_c_un'] * 1000, lp['unload_c'] / 1e3, color='#2ca02c', lw=1.6,
                label='Unloading (recovery)')
        ax.plot(lp['e_t'] * 1000, lp['load_t'] / 1e3, color='#d62728', lw=1.6,
                label='Loading (tension)')
        ax.plot(lp['e_t_un'] * 1000, lp['unload_t'] / 1e3, color='#ff7f0e', lw=1.6,
                label='Unloading (recovery)')
        ax.axhline(0, color='k', lw=0.6); ax.axvline(0, color='k', lw=0.6)
        ax.axvline(p.stroke_m * 1000, color='gray', ls=':', lw=1.0)
        ax.axvline(-p.stroke_m * 1000, color='gray', ls=':', lw=1.0)
        ax.axhline(p.max_impulse_n / 1e3, color='gray', ls='--', lw=1.0, alpha=0.7)
        ax.annotate('Dead zone ±%d mm\n(no force in gap)' % (p.coupler_gap_m * 1000),
                    xy=(p.coupler_gap_m * 1000, 20), xytext=(-105, -2050), fontsize=8,
                    arrowprops=dict(arrowstyle='->'))
        ax.set_xlabel('Displacement (mm)')
        ax.set_ylabel('Coupler force (kN)')
        ax.set_title(title, fontsize=10)
        ax.legend(fontsize=8, loc='upper right')
        ax.grid(alpha=0.3)
        ax.set_xlim(-105, 105); ax.set_ylim(-2600, 2850)
        ax.text(30, p.max_impulse_n / 1e3 + 90,
                'MT-2 max impulse 2270 kN', fontsize=8, color='gray')
        ax.annotate('Preload 200 kN\n(impedance on contact)',
                    xy=(p.coupler_gap_m * 1000 + 2, 200),
                    xytext=(-100, 700), fontsize=8, arrowprops=dict(arrowstyle='->'))
        ax.text(-100, -1500, 'Stribeck friction\n(静 750 / 动 500 kN, v_er=0.2)',
                fontsize=8, color='#2ca02c')
        peak_c = float(np.nanmax(np.abs(lp['load_c']))) / 1e3
        peak_t = float(np.nanmax(np.abs(lp['load_t']))) / 1e3
        logger.info('[self-check] %-7s loading peak: compression %.0f / tension %.0f kN '
                    '(limit %d kN)', 'MT-2', peak_c, peak_t, int(p.max_impulse_n / 1e3))
    fig.suptitle('Coupler buffer loading–unloading hysteresis · MT-2 (unified, R0)', fontsize=12.5)
    save_fig(fig, out)
    logger.info('[self-check] MT-2: dead zone ±10mm, preload 200kN, Stribeck 750/500, '
                'stroke 83mm, limit 2270kN; 全列统一 MT-2（QKX100 已移除）')


# ---------------------------------------------------------------------------
# 图7：机车牵引/电制动特性外包络（静态标量）
# ---------------------------------------------------------------------------
def fig_loco_characteristics(out):
    v = np.linspace(1e-3, 30.0, 300)
    F_tr = np.array([tractive_force(9600.0, 0.85, 1.0, s, 188.0, 0.9) for s in v]) / 1e3
    F_ed = np.array([brak.electric_brake_force_n(188.0, s, 1.0, 9600.0, 0.85, 0.9, 0.85) for s in v]) / 1e3
    fig, ax = plt.subplots(figsize=(8, 5.5))
    ax.plot(v * 3.6, F_tr, color='#1f77b4', lw=2.0, label='Traction (throttle=1)')
    ax.plot(v * 3.6, F_ed, color='#d62728', lw=2.0, label='Electric braking (ED=1)')
    ax.axhline(0.9 * 188.0 * 9.81, color='#1f77b4', ls='--', lw=1.0, alpha=0.6)
    ax.axhline(0.85 * 0.9 * 188.0 * 9.81, color='#d62728', ls='--', lw=1.0, alpha=0.6)
    ax.text(120, 0.9 * 188.0 * 9.81 + 30, 'traction adhesion limit', fontsize=8, color='#1f77b4')
    ax.text(120, 0.85 * 0.9 * 188.0 * 9.81 + 30, 'ED adhesion limit', fontsize=8, color='#d62728')
    ax.text(100, 400, 'F = P_eff / v\n(power-limited)', fontsize=9, color='dimgray', ha='center')
    ax.set_xlabel('Speed (km/h)'); ax.set_ylabel('Traction / braking force (kN)')
    ax.set_title('HXD3B loco traction / electric-braking envelope (9600 kW, 188 t, η=0.85)')
    ax.legend(fontsize=9)
    ax.set_xlim(0, 30 * 3.6)
    ax.grid(alpha=0.3)
    save_fig(fig, out)
    logger.info('[self-check] traction peak %.0f kN / ED peak %.0f kN (adhesion limits)',
                0.9 * 188.0 * 9.81, 0.85 * 0.9 * 188.0 * 9.81)


def main():
    set_seed(SEED)
    stamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    outdir = Path('outputs') / 'phys_validation' / f'run_{stamp}'
    outdir.mkdir(parents=True, exist_ok=True)

    # --- 图1/2/5：制动建立 + 缓解波（平坡） ---
    logger.info('== 场景A：SERVICE 制动建立 -> 缓解波释放（平坡） ==')
    data = run_brake_release()
    n_apply = int(35.0 / 0.1)
    ab_force = np.abs(data['forces'])
    peak_apply = float(np.max(np.sum(ab_force[:, :n_apply], axis=1))) / 1e3
    data['t_apply'] = data['t'][:n_apply]
    fig_brake_wave(data, outdir / '图1-空气制动波传播.png')
    # self-check: brake-wave tail activation delay vs theory L/200 m/s ≈ 6.1 s
    on = np.where(data['active'][:, -1] > 0)[0]
    if len(on):
        logger.info('[self-check] brake-wave tail activation delay = %.2f s (theory L/200 ≈ 6.1 s)',
                    float(data['t'][on[0]]))
    fig_brake_build(data, outdir / '图2-制动力建立.png')
    fig_release_curve(data, outdir / '图5-缓解曲线.png')

    # --- 图3/4：朔黄线循环制动 ---
    logger.info('== 场景B：朔黄线 23.8km 长大下坡循环制动 ==')
    cyc = run_cyclic_shuozhou()
    fig_cyclic(cyc, outdir / '图3-朔黄线循环制动.png')
    fig_release_impulse(cyc, outdir / '图4-纵向冲动时间窗.png')

    # --- 图6/7：静态曲线（图6 = MT-2 迟滞环，2026-09-07 统一后单面板） ---
    fig_coupler_hysteresis(outdir / '图6-缓冲器迟滞环(MT2).png')
    fig_loco_characteristics(outdir / '图7-机车牵引电制动特性.png')

    # --- CSV + 元数据留痕 ---
    import pandas as pd
    pd.DataFrame({
        't': cyc['t'], 'v_kmh': cyc['v_kmh'], 'dist_m': cyc['dist'],
        'ab_active': cyc['ab_active'], 'coupler_peak_kn': cyc['coupler_peak_kn'],
        'throttle': cyc['throttle'],
    }).to_csv(outdir / 'traj_cyclic_shuozhou.csv', index=False)
    np.savez_compressed(outdir / 'coupler_matrix.npz', coupler_mat=cyc['coupler_mat'])
    meta = {
        'seed': SEED,
        'timestamp': stamp,
        'section': '物理曲线验证图',
        'scenarioA': {'consist': '10kt_1plus0', 'grade': 0.0, 'brake': 'SERVICE(-0.5)',
                      'brake_s': 35.0, 'release_s': 50.0},
        'scenarioB': {'consist': '10kt_1plus0', 'grade_profile': 'shuozhou_23800',
                      'max_steps': 15000, 'init_speed_kmh': 65,
                      'v_range_kmh': [40, 80], 'brake_notch': -0.8, 'release_throttle': 0.5},
        'physics': 'R0(2026-09-06)+MT2统一(2026-09-07): 全列MT-2 Stribeck 750/500 + '
                   '卸载刚度(MT-2=1.0) + 牵规β_c制动力 + 并行波速传播 + '
                   '段间衰减(D) + 两段式缓解排气(τ=6s) + Newmark-β 积分',
        'adhesion_limit_kn': float(0.9 * 188.0 * 9.81),
        'figures': [p.name for p in outdir.glob('*.png')],
        'note': '对向导师的物理曲线验证；不改仿真器代码，仅新增展示脚本。',
    }
    (outdir / 'run_meta.json').write_text(json.dumps(meta, ensure_ascii=False, indent=2),
                                          encoding='utf-8')
    logger.info('全部完成，输出目录 %s', outdir)


if __name__ == '__main__':
    main()