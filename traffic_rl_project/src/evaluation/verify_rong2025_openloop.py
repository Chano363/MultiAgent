"""【2026-10-11】容嘉欣2025 图8/图9 开环对照（12‰ 长大下坡）。

文献：《更大牵引质量重载列车动力学建模与仿真分析》（机械 2025, 52(7):57-64），
图8/图9 给出 3万/2万吨列车在 12‰ 长大下坡「采用最小常用制动进行制动缓解」的
两个对照口径：
  (a) 最大车钩力沿车位分布（蓝=最大拉钩力，红=最大压钩力）
  (b) 纵向加速度时程（0–200 s：稳态段贴 0，仅制动/缓解时刻出现衰减脉冲）

本脚本判别「车速/车钩力震荡」的锅在物理模型还是底层控制器：

  mode=openloop_min   纯开环固定时序 MIN 档（-0.2 = 文献「最小常用制动」口径）
  mode=openloop_emg   纯开环固定时序 EMERGENCY 档（-0.8 = 历史验证脚本口径）
  mode=rule           现有闭环规则（预缓和缩放 + 双层安全钳制 = 当前用户现状）

判读：
  openloop 平滑 + rule 震荡 → 锅在控制器（反馈/钳制环节）
  两者都震荡              → 锅在物理模型或数值积分

用法（WSL traffic_rl）：
    python src/evaluation/verify_rong2025_openloop.py --source new   # 跑仿真
    python src/evaluation/verify_rong2025_openloop.py                # 复用归档重画
"""
import sys
import json
import argparse
import logging
from pathlib import Path
from datetime import datetime

import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

from src.utils.plot_style import setup_cjk_font  # noqa: F401  保证字体环境一致
from src.train_dynamics.braking import AirBrakeNotch
from src.train_dynamics.grade_profile import GradeProfile, GradeSegment

logging.basicConfig(level=logging.INFO, format='%(message)s')
logger = logging.getLogger('Rong2025')

# ---------------------------------------------------------------- 工况常量
GRADE_PERMILLE = -12.0     # 文献表1 长大下坡 K304+750~K314+750，坡度 -12‰
DT = 0.1
MAX_STEPS = 4000           # 400 s（文献图(b) 横轴 0–200 s，取两倍以覆盖两个循环）
INIT_SPEED_KMH = 65.0      # 与既有剖面验证脚本一致（文献未给初速）
V_MAX, V_MIN = 80.0 / 3.6, 40.0 / 3.6   # 规则模式速度带（km/h 40–80）
CONSIST = '10kt_1plus0'    # 1 机车 + 100 货车 = 101 车（文献 2 万吨为 210 车位）

BRAKE_MIN, BRAKE_SVC, BRAKE_EMG = -0.2, -0.5, -0.8
# notch_from_throttle: 0.2→MIN, 0.5→SERVICE, 0.8→EMERGENCY

# 开环固定操纵时序（秒）：(起, 止, throttle) —— 与状态无关，纯时间函数
OPENLOOP_SCHEDULE = [
    (0, 60, 0.0),        # 惰行（12‰ 下坡自然加速）
    (60, 140, None),     # 制动（档位由 mode 决定）
    (140, 240, 0.0),     # 缓解
    (240, 320, None),    # 再制动
    (320, 400, 0.0),     # 缓解
]

MODES = ['openloop_min', 'openloop_emg', 'rule_emg', 'rule_service', 'rule_min']
MODE_LABEL = {
    'openloop_min': 'Open-loop, MIN notch (-0.2)',
    'openloop_emg': 'Open-loop, EMERGENCY notch (-0.8)',
    'rule_emg': 'Rule, EMERGENCY notch (-0.8) [current default]',
    'rule_service': 'Rule, SERVICE notch (-0.5)',
    'rule_min': 'Rule, MIN notch (-0.2)',
}
BRAKE_OF = {
    'openloop_min': BRAKE_MIN, 'rule_min': BRAKE_MIN,
    'rule_service': BRAKE_SVC,
    'openloop_emg': BRAKE_EMG, 'rule_emg': BRAKE_EMG,
}


def rong_profile() -> GradeProfile:
    """文献表1 长大下坡工况：全段 -12‰（局部构造，不改 train_dynamics）。"""
    return GradeProfile(segments=[GradeSegment(0.0, GRADE_PERMILLE)])


def openloop_action(t_sec: float, n_veh: int, brake: float) -> np.ndarray:
    """纯时间函数的开环指令（不读任何状态）。"""
    throttle = 0.0
    for t0, t1, val in OPENLOOP_SCHEDULE:
        if t0 <= t_sec < t1:
            throttle = brake if val is None else val
            break
    return np.full(n_veh, throttle, dtype=float)


def run_one(mode: str) -> dict:
    """跑单个模式，返回逐步轨迹（含每车速度与逐断面车钩力）。"""
    from src.environments.train_env import TrainFormationEnv

    enable_safety = mode.startswith('rule')
    env = TrainFormationEnv({
        'consist_preset': CONSIST,
        'grade_profile': None,          # 剖面在 reset 后用局部对象注入（不改 train_dynamics）
        'dt': DT,
        'max_steps': MAX_STEPS,
        'enable_safety': enable_safety,
        'sync_loco_brake': True,
    })
    env.reset(options={'speed': INIT_SPEED_KMH / 3.6})
    env.dynamics.set_grade_profile(rong_profile())   # 文献 12‰ 长大下坡工况

    n_veh = env.num_vehicles
    ctrl = None
    if mode.startswith('rule'):
        from src.controllers.low_level_controller import TrainLowLevelController
        ctrl = TrainLowLevelController(
            num_vehicles=n_veh, dt=DT,
            coupler_force_limit_n=env.coupler_force_limit_n,
            enforce_coupler=True,
        )
        ctrl.reset()

    brake = BRAKE_OF[mode]
    vel_all = np.zeros((MAX_STEPS, n_veh))
    coupler = np.zeros((MAX_STEPS, n_veh - 1))
    t_arr = np.zeros(MAX_STEPS)
    cmd_sent = np.zeros(MAX_STEPS)      # 实际送进动力学的动作（列首值）
    cmd_raw = np.zeros(MAX_STEPS)       # 控制器/开环的原始意图（未经安全钳制）
    ab_active = np.zeros(MAX_STEPS, dtype=int)
    terminated = False

    for k in range(MAX_STEPS):
        t_arr[k] = env.dynamics.time
        vel_all[k] = env.dynamics.vel
        coupler[k] = env.dynamics.coupler_interface_forces()
        st = env.dynamics.air_brake_state()
        ab_active[k] = int(any(nr != AirBrakeNotch.RELEASE for nr in st))

        if ctrl is not None:
            actions = ctrl.get_action_cyclic_braking(
                env, V_MAX, V_MIN, brake_notch=brake, release_throttle=0.0)
            cmd_raw[k] = brake
        else:
            actions = openloop_action(t_arr[k], n_veh, brake)
            cmd_raw[k] = float(actions[0])
        cmd_sent[k] = float(actions[0])

        _, _, term, trunc, info = env.step(actions)
        cmd_sent[k] = float(info['executed_actions'][0])   # 安全层修正后的实际执行
        if term or trunc:
            terminated = True
            logger.info('[%s] 第 %d 步终止（term=%s trunc=%s）', mode, k, term, trunc)
            break

    n = k + 1
    return dict(mode=mode, t=t_arr[:n], vel_all=vel_all[:n], coupler=coupler[:n],
                cmd_raw=cmd_raw[:n], cmd_sent=cmd_sent[:n], ab_active=ab_active[:n],
                terminated=terminated, n_veh=n_veh)


def archive(runs: dict) -> Path:
    """原始数据 → 时间戳归档（不覆盖）。"""
    stamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    outdir = Path('outputs') / 'sim_validation' / 'phys_validation' / f'rong2025_openloop_{stamp}'
    outdir.mkdir(parents=True, exist_ok=True)
    for mode, d in runs.items():
        np.savez_compressed(
            outdir / f'traj_{mode}.npz',
            t=d['t'], vel_all=d['vel_all'], coupler=d['coupler'],
            cmd_raw=d['cmd_raw'], cmd_sent=d['cmd_sent'], ab_active=d['ab_active'],
            terminated=np.array(d['terminated']), n_veh=np.array(d['n_veh']))
    meta = {
        'section': '容嘉欣2025 图8/图9 开环对照（12‰ 长大下坡）',
        'timestamp': stamp,
        'source_paper': '更大牵引质量重载列车动力学建模与仿真分析, 机械 2025, 52(7):57-64',
        'literature_anchor': {
            'fig9_2w_tension_kN': 1059.8, 'fig9_2w_compression_kN': 1109.1,
            'fig9_2w_max_accel_ms2': 6.06,
            'fig8_3w_tension_kN': 596.6, 'fig8_3w_compression_kN': 503.8,
            'fig8_3w_max_accel_ms2': 3.18,
        },
        'config': {
            'grade_permille': GRADE_PERMILLE, 'dt': DT, 'max_steps': MAX_STEPS,
            'init_speed_kmh': INIT_SPEED_KMH, 'consist': CONSIST,
            'n_vehicles': int(runs[MODES[0]]['n_veh']),
            'brake_min': BRAKE_MIN, 'brake_service': BRAKE_SVC, 'brake_emg': BRAKE_EMG,
            'openloop_schedule': OPENLOOP_SCHEDULE,
            'speed_band_kmh': [40, 80],
        },
        'modes': MODES,
        'note': '开环指令为纯时间函数、不读状态；rule 为现有闭环（预缓和缩放 + env 与控制器双层安全钳制）。',
    }
    (outdir / 'run_meta.json').write_text(
        json.dumps(meta, ensure_ascii=False, indent=2, default=list), encoding='utf-8')
    logger.info('数据归档 → %s', outdir)
    return outdir


def load_latest() -> Path:
    root = Path('outputs') / 'sim_validation' / 'phys_validation'
    cands = sorted(root.glob('rong2025_openloop_*'))
    if not cands:
        sys.exit('未找到归档，请先加 --source new 跑仿真')
    return cands[-1]


def load_runs(src: Path) -> dict:
    runs = {}
    for mode in MODES:
        f = src / f'traj_{mode}.npz'
        if not f.exists():
            continue
        z = np.load(f)
        runs[mode] = {k: z[k] for k in z.files}
    return runs


def plot(runs: dict, src: Path, outdir: Path) -> None:
    """文献图8/图9 同款两组图。图内文字一律英文。"""
    outdir.mkdir(parents=True, exist_ok=True)
    BLUE, RED = '#1f77b4', '#d62728'
    colors = {'openloop_min': '#2ca02c', 'openloop_emg': '#ff7f0e',
              'rule_emg': '#d62728', 'rule_service': '#9467bd', 'rule_min': '#17becf'}

    # ---- 图(a)：每车位最大拉/压钩力分布（文献同构：拉在正轴、压在负轴） ----
    fig, ax = plt.subplots(figsize=(8.5, 5.4))
    for mode, d in runs.items():
        c = d['coupler']                      # (steps, n-1)，正=拉，负=压
        tension = c.max(axis=0) / 1e3         # 最大拉钩力 → 正轴
        compression = c.min(axis=0) / 1e3     # 最大压钩力 → 负轴
        x = np.arange(len(tension))
        ax.plot(x, tension, lw=1.8, color=colors[mode], ls='-',
                label=f'{MODE_LABEL[mode]}: max tension')
        ax.plot(x, compression, lw=1.8, color=colors[mode], ls='--',
                label=f'{MODE_LABEL[mode]}: max compression')
    x_hi = float(len(tension)) - 1.0          # 数据坐标：右端
    for y, lab in ((1000, '+1000 kN limit'), (-1000, '\u22121000 kN limit')):
        ax.axhline(y, color='k', ls=':', lw=1.0)
        ax.text(x_hi, y + (55 if y > 0 else -110), lab, fontsize=8, ha='right', color='k')
    # 文献锚（图8，3万吨 12‰ 长大下坡）：拉 596.6 kN @218位、压 503.8 kN @110位
    ax.axhline(596.6, color='0.45', ls='-.', lw=1.0)
    ax.axhline(-503.8, color='0.45', ls='-.', lw=1.0)
    ax.text(x_hi, 625, 'Literature Fig.8 (30 kt): 596.6 kN', fontsize=7.5,
            ha='right', color='0.30')
    ax.text(x_hi, -575, 'Literature Fig.8 (30 kt): \u2212503.8 kN', fontsize=7.5,
            ha='right', color='0.30')
    ax.set_xlabel('Vehicle index')
    ax.set_ylabel('Coupler interface force (kN)')
    ax.set_title('Maximum coupler force distribution along the 12 per mille downgrade')
    ax.grid(alpha=0.3)
    ax.legend(fontsize=8, ncol=2, loc='upper center', bbox_to_anchor=(0.5, -0.13),
              frameon=False)
    fig.tight_layout()
    fig.savefig(outdir / 'rong2025_fig8a_coupler_distribution.png', dpi=160, bbox_inches='tight')
    plt.close(fig)
    logger.info('图(a) → rong2025_fig8a_coupler_distribution.png')

    # ---- 图(b)：纵向加速度时程（每模式一列，文献同款多车叠加） ----
    fig, axes = plt.subplots(len(runs), 1, figsize=(9, 3.4 * len(runs)), sharex=True)
    if len(runs) == 1:
        axes = [axes]
    for ax, (mode, d) in zip(axes, runs.items()):
        v = d['vel_all']
        a = np.gradient(v, DT, axis=0)        # 每车纵向加速度 (steps, n_veh)
        t = d['t']
        for i in range(a.shape[1]):
            ax.plot(t, a[:, i], lw=0.5, alpha=0.55, color=BLUE if i == 0 else '#7ba3d6')
        ax.axhline(0, color='k', lw=0.6)
        lim = max(1.0, float(np.abs(a).max()) * 1.1)
        ax.set_ylim(-lim, lim)
        ax.set_ylabel('Longitudinal\nacceleration (m/s$^2$)')
        ax.set_title(f'{MODE_LABEL[mode]}   (max |a| = {np.abs(a).max():.2f} m/s$^2$)',
                     fontsize=10)
        ax.grid(alpha=0.3)
    axes[-1].set_xlabel('Time (s)')
    fig.suptitle('Longitudinal acceleration time history on the 12 per mille downgrade',
                 fontsize=12)
    fig.tight_layout(rect=[0, 0, 1, 0.97])
    fig.savefig(outdir / 'rong2025_fig8b_acceleration_history.png', dpi=160, bbox_inches='tight')
    plt.close(fig)
    logger.info('图(b) → rong2025_fig8b_acceleration_history.png')

    # ---- 图(c)：车钩力时程（直接回应"车钩力震荡"） ----
    fig, ax = plt.subplots(figsize=(9, 4.6))
    for mode, d in runs.items():
        c = d['coupler'] / 1e3                      # (steps, n-1) kN
        up = c.max(axis=1)                          # 每步全列最大拉钩力
        dn = c.min(axis=1)                          # 每步全列最大压钩力
        ax.plot(d['t'], up, lw=1.1, color=colors[mode],
                label=f'{MODE_LABEL[mode]}: max tension')
        ax.plot(d['t'], dn, lw=1.1, color=colors[mode], ls='--', alpha=0.85,
                label=f'{MODE_LABEL[mode]}: max compression')
    for y, lab in ((1000, '+1000 kN limit'), (-1000, '\u22121000 kN limit')):
        ax.axhline(y, color='k', ls=':', lw=1.0)
        ax.text(5, y + (45 if y > 0 else -85), lab, fontsize=8)
    ax.axhline(0, color='k', lw=0.6)
    ax.set_xlabel('Time (s)')
    ax.set_ylabel('Coupler interface force (kN)')
    ax.set_title('Time history of the extreme coupler force in the train',
                 fontsize=11)
    ax.grid(alpha=0.3)
    ax.legend(fontsize=8, ncol=2, loc='upper center', bbox_to_anchor=(0.5, -0.15),
              frameon=False)
    fig.tight_layout()
    fig.savefig(outdir / 'rong2025_fig8c_coupler_history.png', dpi=160, bbox_inches='tight')
    plt.close(fig)
    logger.info('图(c) → rong2025_fig8c_coupler_history.png')

    # ---- 诊断图：速度时程 + 指令序列（判"车速不符合预期"） ----
    fig, axes = plt.subplots(2, 1, figsize=(9, 6.5), sharex=True)
    for mode, d in runs.items():
        v = d['vel_all'][:, 0] * 3.6
        axes[0].plot(d['t'], v, lw=1.3, color=colors[mode], label=MODE_LABEL[mode])
        axes[1].step(d['t'], d['cmd_sent'], where='post', lw=1.2, color=colors[mode],
                     label=f'{MODE_LABEL[mode]}: executed')
        axes[1].plot(d['t'], d['cmd_raw'], lw=0.8, ls=':', color=colors[mode], alpha=0.7)
    axes[0].axhline(80, color='k', ls='--', lw=0.9)
    axes[0].axhline(40, color='k', ls='--', lw=0.9)
    axes[0].text(5, 81.5, '80 km/h', fontsize=8)
    axes[0].text(5, 41.5, '40 km/h', fontsize=8)
    axes[0].set_ylabel('Head vehicle speed (km/h)')
    axes[0].set_title('Speed response under each control mode', fontsize=10)
    axes[0].legend(fontsize=8)
    axes[0].grid(alpha=0.3)
    axes[1].set_ylabel('Throttle command')
    axes[1].set_xlabel('Time (s)')
    axes[1].set_title('Command sent to dynamics (solid step) vs raw intent (dotted)', fontsize=10)
    axes[1].legend(fontsize=8)
    axes[1].grid(alpha=0.3)
    fig.tight_layout()
    fig.savefig(outdir / 'rong2025_diagnosis_speed_and_command.png', dpi=160, bbox_inches='tight')
    plt.close(fig)
    logger.info('诊断图 → rong2025_diagnosis_speed_and_command.png')


def speed_oscillation(v_kmh: np.ndarray) -> dict:
    """速度震荡量化（列首速度，km/h）：带内驻留、超调、穿越次数、摆幅。"""
    in_band = (v_kmh >= 40.0) & (v_kmh <= 80.0)
    # 进出带穿越次数：带内/带外状态翻转次数
    flips = int(np.sum(np.diff(in_band.astype(int)) != 0))
    # 速度方向反转次数（粗略平滑，避免数值微分噪声）
    sm = np.convolve(v_kmh, np.ones(21) / 21.0, mode='same')
    d = np.diff(sm)
    reversals = int(np.sum(np.diff(np.sign(d)) != 0))
    return {
        'band_pct': float(in_band.mean() * 100.0),
        'v_std': float(v_kmh.std()),
        'over_hi': float(max(v_kmh.max() - 80.0, 0.0)),
        'over_lo': float(max(40.0 - v_kmh.min(), 0.0)),
        'swing': float(v_kmh.max() - v_kmh.min()),
        'cross': flips,
        'reversals_per_min': reversals / (len(v_kmh) * DT / 60.0),
    }


def report(runs: dict) -> None:
    """数值锚 + 速度震荡量化（供"车速是否符合预期"判读）。"""
    logger.info('\n== 车钩力/加速度 vs 文献锚（3万吨 拉 596.6 / 压 503.8 kN，a_max 3.18）==')
    logger.info('%-28s %9s %9s %8s %7s %7s %8s',
                'mode', 'tens_kN', 'comp_kN', 'a_max', 'v_min', 'v_max', 'a_std')
    for mode, d in runs.items():
        c = d['coupler'] / 1e3
        a = np.gradient(d['vel_all'], DT, axis=0)
        v = d['vel_all'][:, 0] * 3.6
        logger.info('%-28s %9.1f %9.1f %8.2f %7.1f %7.1f %8.3f',
                    MODE_LABEL[mode], c.max(), -c.min(), np.abs(a).max(),
                    v.min(), v.max(), float(a.std()))

    logger.info('\n== 车速震荡量化（列首速度，速度带 40–80 km/h）==')
    logger.info('%-28s %7s %7s %8s %8s %8s %7s %11s',
                'mode', 'band%', 'v_std', 'over_hi', 'over_lo', 'swing', 'cross', 'rev/min')
    for mode, d in runs.items():
        m = speed_oscillation(d['vel_all'][:, 0] * 3.6)
        logger.info('%-28s %7.1f %7.2f %8.1f %8.1f %8.1f %7d %11.2f',
                    MODE_LABEL[mode], m['band_pct'], m['v_std'], m['over_hi'],
                    m['over_lo'], m['swing'], m['cross'], m['reversals_per_min'])


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--source', default='archive', choices=['new', 'archive'],
                    help='new=重跑仿真并新建归档；archive=复用已有归档重画（默认）')
    args = ap.parse_args()

    if args.source == 'new':
        runs = {m: run_one(m) for m in MODES}
        src = archive(runs)
    else:
        src = load_latest()
        runs = load_runs(src)
        logger.info('复用归档 %s', src)

    outdir = Path('outputs') / 'sim_validation' / 'figures' / 'rong2025_fig8_13_compare'
    plot(runs, src, outdir)
    report(runs)
    logger.info('图目录 → %s', outdir)


if __name__ == '__main__':
    main()
