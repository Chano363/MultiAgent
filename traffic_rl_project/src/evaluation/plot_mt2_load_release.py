"""【2026-10-11】MT-2 缓冲器准静态加载-缓释阻抗曲线：当前模型 vs 于宗泽2025 参考。

导师反馈"车钩装载缓释曲线是错的，做得太理想"——本脚本做定量诊断（只新增绘图脚本，
不修改 src/ 任何物理逻辑）：

    曲线1 当前模型：src/train_dynamics/coupler.py::coupler_force（真实签名），
          参数取 params.py CouplerParams 默认值；含 dir_sm=tanh(s_e·dv/friction_v_eps)、
          fric_mag=-fric_amp·dir_sm 的方向平滑逻辑。
    曲线2 参考模型：于宗泽2025《重载列车车钩缓冲装置纵向动力学精细化模型》式(1)(2)
          字面实现 F = F0 + k·x + sgn(v)·μ(|v|)·FN（docs/papers/01_coupler_physics/于宗泽2025_fulltext.txt
          L132-177）：sgn(v) 加载=+1、|v|=0 取 0、卸载=−1；μ Stribeck：|v|=0→μs、
          0<|v|<ver→μs−(μs−μd)·|v|/ver、|v|>ver→μd。参数与现模型完全相同
          （F0=200kN、k=1.89e7 N/m、μd·FN=500kN、μs·FN=750kN、ver=0.2）；
          无饱和封顶、无非负截断（式(1)(2) 字面，元数据中注明）。

协议（准静态循环，压缩为正）：两车位置/速度使压缩量从接触点（|e|=gap、x=0）以
v=0.01 m/s 匀速压到 83 mm → 停止（v=0）采样 → 以 0.01 m/s 匀速释放回接触点。

量化指标（归档 JSON + 图内注释，全英文）：
    - 加载末段（|v|=0.01 m/s 处）两模型摩擦分量与总阻抗差值（kN）；
    - 加载末端最后 5 mm 内力变化方向（数据说了算，不预写结论）；
    - 运动停止于 83 mm（v=0）瞬间的阻抗变化（检验 dv→0 摩擦消失假设）；
    - 迟滞环面积（加载-卸载围成，kN·mm，1 N·m = 1 kN·mm）。

产出：
    图 → outputs/sim_validation/figures/mt2_coupler/mt2_load_release_comparison.png
         （策展目录，允许覆盖）
    数据 → outputs/sim_validation/phys_validation/mt2_load_release_cmp_<时间戳>/
         mt2_load_release.npz + mt2_load_release.csv + run_meta.json

用法（WSL traffic_rl）：
    python src/evaluation/plot_mt2_load_release.py             # 默认复用最近归档，仅重画
    python src/evaluation/plot_mt2_load_release.py --source new # 强制重算并新建归档（首跑）
"""
import sys
import json
import argparse
import logging
from pathlib import Path
from datetime import datetime

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

from src.train_dynamics.params import CouplerParams
from src.train_dynamics.coupler import coupler_force

logging.basicConfig(level=logging.INFO, format='%(message)s')
logger = logging.getLogger('MT2LoadRelease')

ARCH_ROOT = Path('outputs') / 'sim_validation' / 'phys_validation'
ARCH_PREFIX = 'mt2_load_release_cmp_'
FIG_PATH = (Path('outputs') / 'sim_validation' / 'figures' / 'mt2_coupler'
            / 'mt2_load_release_comparison.png')
NPZ_NAME = 'mt2_load_release.npz'
CSV_NAME = 'mt2_load_release.csv'

V_Q = 0.01        # 准静态加载/释放速度（m/s）
N_HOLD = 3        # 最大压缩处 v=0 停止采样点数
DX = 1e-4         # 压缩量步长（m，0.1 mm）


# ---------------------------------------------------------------------------
# 协议：两车位置/速度序列（前车静止，后车推进=压缩）
# ---------------------------------------------------------------------------
def build_protocol(stroke_m, gap_m, free_length_m):
    """返回 compression(x_el, m)、v_back(m/s)、phase、t(s)。

    e = (x_back - x_front) + free_length；x_front=0 固定，x_back = e - free_length。
    压缩加深 ⟺ e 增大 ⟺ v_back>0（此时 dv=v_front-v_back<0，s_e·dv<0 → 加载）。
    """
    n = int(round(stroke_m / DX)) + 1
    x_load = np.linspace(0.0, stroke_m, n)             # 接触点 → 83 mm
    x_un = x_load[::-1]                                # 83 mm → 接触点
    x = np.concatenate([x_load, np.full(N_HOLD, stroke_m), x_un])
    v_back = np.concatenate([np.full(n, V_Q), np.zeros(N_HOLD), np.full(n, -V_Q)])
    phase = np.array(['load'] * n + ['hold'] * N_HOLD + ['unload'] * n)
    dt = DX / V_Q
    t_load = np.arange(n) * dt
    t_hold = t_load[-1] + (np.arange(1, N_HOLD + 1) * 0.05)
    t_un = t_hold[-1] + (stroke_m - x_un) / V_Q
    t = np.concatenate([t_load, t_hold, t_un])
    return x, v_back, phase, t


# ---------------------------------------------------------------------------
# 两模型逐步取力（压缩为正）
# ---------------------------------------------------------------------------
def coupler_kwargs(p: CouplerParams) -> dict:
    """CouplerParams → coupler_force 关键字（真实签名）。"""
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


def evaluate_current(x_el, v_back, p: CouplerParams):
    """当前模型：coupler_force 总阻抗 + 摩擦分量（N，压缩为正）。

    摩擦分量 = F(全参数) − F(摩擦置零)；其余项（contact、k_eff、preload）在两次
    调用中完全相同（k_eff 只依赖 load_factor=0.5·(1−dir_sm)，与摩擦参数无关）。
    """
    kw = coupler_kwargs(p)
    kw0 = dict(kw)
    kw0['friction_n'] = 0.0
    kw0['friction_static_n'] = 0.0
    free, gap = p.free_length_m, p.coupler_gap_m
    tot = np.empty(len(x_el))
    fric = np.empty(len(x_el))
    for i, (xi, vi) in enumerate(zip(x_el, v_back)):
        x_back = (xi + gap) - free          # e = xi + gap（前车 x_front=0, v_front=0）
        f_tot = coupler_force(0.0, 0.0, x_back, float(vi), **kw)
        f_f0 = coupler_force(0.0, 0.0, x_back, float(vi), **kw0)
        tot[i] = f_tot
        fric[i] = f_tot - f_f0
    return tot, fric


def evaluate_reference(x_el, v_back, p: CouplerParams):
    """于宗泽2025 式(1)(2) 字面实现：F = F0 + k·x + sgn(v)·μ(|v|)·FN（N，压缩为正）。"""
    sgn = np.sign(v_back)                    # 加载=+1、|v|=0→0、卸载=−1
    av = np.abs(v_back)
    mu = np.where(
        av == 0.0, p.friction_static_n,
        np.where(av < p.friction_v_er,
                 p.friction_static_n
                 + (p.friction_n - p.friction_static_n) * av / p.friction_v_er,
                 p.friction_n))
    fric = sgn * mu
    tot = p.preload_n + p.stiffness * x_el + fric
    return tot, fric


# ---------------------------------------------------------------------------
# 量化指标（kN / kN·mm）
# ---------------------------------------------------------------------------
def _trapz(y, x):
    trap = getattr(np, 'trapezoid', None) or np.trapz
    return float(trap(y, x))


def compute_metrics(x_el, phase, cur_tot, cur_fric, ref_tot, ref_fric):
    li = np.flatnonzero(phase == 'load')
    hi = np.flatnonzero(phase == 'hold')
    i_end = li[-1]
    i_5mm = li[x_el[li] >= x_el[i_end] - 0.005][0]
    i_hold = hi[0]

    d5_cur = (cur_tot[i_end] - cur_tot[i_5mm]) / 1e3
    d5_ref = (ref_tot[i_end] - ref_tot[i_5mm]) / 1e3
    dstop_cur = (cur_tot[i_hold] - cur_tot[i_end]) / 1e3
    dstop_ref = (ref_tot[i_hold] - ref_tot[i_end]) / 1e3

    # 迟滞环面积：加载支 − 卸载支（同一压缩量网格上积分），1 N·m = 1 kN·mm
    ui = np.flatnonzero(phase == 'unload')
    x_u = x_el[ui][::-1]
    assert np.allclose(x_el[li], x_u)          # 加载/卸载支同一压缩量网格
    area_cur = _trapz(cur_tot[li] - cur_tot[ui][::-1], x_el[li])
    area_ref = _trapz(ref_tot[li] - ref_tot[ui][::-1], x_el[li])

    def direction(d):
        return 'rise' if d > 0 else ('fall' if d < 0 else 'flat')

    return {
        'loading_end_v_abs_mps': V_Q,
        'loading_end_friction_kn': {
            'current': float(cur_fric[i_end] / 1e3),
            'reference': float(ref_fric[i_end] / 1e3),
            'reference_minus_current': float((ref_fric[i_end] - cur_fric[i_end]) / 1e3),
        },
        'loading_end_total_kn': {
            'current': float(cur_tot[i_end] / 1e3),
            'reference': float(ref_tot[i_end] / 1e3),
            'reference_minus_current': float((ref_tot[i_end] - cur_tot[i_end]) / 1e3),
        },
        'last_5mm_of_loading_delta_kn': {
            'current': float(d5_cur), 'current_direction': direction(d5_cur),
            'reference': float(d5_ref), 'reference_direction': direction(d5_ref),
            'note': 'F(83mm) - F(78mm) on the loading branch, |v| = 0.01 m/s',
        },
        'stop_at_83mm_v0_delta_kn': {
            'current': float(dstop_cur), 'current_direction': direction(dstop_cur),
            'reference': float(dstop_ref), 'reference_direction': direction(dstop_ref),
            'note': 'F(v=0 hold) - F(last loading point, |v|=0.01 m/s); '
                    'tests the dv->0 friction-vanishing hypothesis',
        },
        'hysteresis_area_kn_mm': {
            'current': float(area_cur), 'reference': float(area_ref),
            'reference_over_current': float(area_ref / area_cur) if area_cur else None,
        },
    }


# ---------------------------------------------------------------------------
# 图（策展目录，允许覆盖；图内文字全英文）
# ---------------------------------------------------------------------------
def make_figure(x_el, phase, cur_tot, ref_tot, metrics, out: Path):
    out.parent.mkdir(parents=True, exist_ok=True)
    li = np.flatnonzero(phase == 'load')
    ui = np.flatnonzero(phase == 'unload')
    hi = np.flatnonzero(phase == 'hold')
    x_mm = x_el * 1000.0

    fig, ax = plt.subplots(figsize=(9.5, 6.5))
    ax.plot(x_mm[li], cur_tot[li] / 1e3, color='#1f77b4', lw=1.8,
            label='Current model, loading')
    ax.plot(x_mm[ui], cur_tot[ui] / 1e3, color='#1f77b4', lw=1.8, ls='--',
            label='Current model, release')
    ax.plot(x_mm[li], ref_tot[li] / 1e3, color='#d62728', lw=1.8,
            label='Yu2025 Eq.(1)-(2) reference, loading')
    ax.plot(x_mm[ui], ref_tot[ui] / 1e3, color='#d62728', lw=1.8, ls='--',
            label='Yu2025 Eq.(1)-(2) reference, release')
    ax.plot([x_mm[hi[0]]], [cur_tot[hi[0]] / 1e3], marker='x', ms=8, mew=2.0,
            color='#1f77b4', ls='none',
            label='Held at maximum compression, zero speed')
    ax.plot([x_mm[hi[0]]], [ref_tot[hi[0]] / 1e3], marker='x', ms=8, mew=2.0,
            color='#d62728', ls='none')

    ax.axhline(1000, color='red', ls='--', lw=1.0)
    ax.text(55.0, 1030, '1000 kN coupler force limit', color='red', fontsize=8)
    ax.axhline(0, color='k', lw=0.6)
    ax.axvline(0, color='k', lw=0.6)

    m = metrics
    lines = [
        'Loading and release speed 0.01 m/s',
        'Friction at loading end: %.1f kN current, %.1f kN reference'
        % (m['loading_end_friction_kn']['current'],
           m['loading_end_friction_kn']['reference']),
        'Total resistance at loading end: %.1f kN current, %.1f kN reference'
        % (m['loading_end_total_kn']['current'],
           m['loading_end_total_kn']['reference']),
        'Change over last 5 mm of loading: %+.1f kN current, %+.1f kN reference'
        % (m['last_5mm_of_loading_delta_kn']['current'],
           m['last_5mm_of_loading_delta_kn']['reference']),
        'Change when motion stops at 83 mm: %+.1f kN current, %+.1f kN reference'
        % (m['stop_at_83mm_v0_delta_kn']['current'],
           m['stop_at_83mm_v0_delta_kn']['reference']),
        'Hysteresis loop area: %.0f kN mm current, %.0f kN mm reference'
        % (m['hysteresis_area_kn_mm']['current'],
           m['hysteresis_area_kn_mm']['reference']),
    ]
    ax.text(0.015, 0.985, '\n'.join(lines), transform=ax.transAxes, va='top',
            ha='left', fontsize=8.2,
            bbox=dict(boxstyle='round', facecolor='white', alpha=0.88, edgecolor='0.7'))

    ax.set_xlabel('Compression (mm)')
    ax.set_ylabel('Resistance (kN)')
    ax.set_title('Quasi-static Loading and Release Resistance of the MT-2 Buffer',
                 fontsize=12)
    ax.legend(fontsize=8.5, loc='lower right')
    ax.grid(alpha=0.3)
    fig.tight_layout()
    fig.savefig(out, dpi=150, bbox_inches='tight')
    plt.close(fig)
    logger.info('已生成 %s', out)


# ---------------------------------------------------------------------------
# 归档读写（数据/绘图分离：默认复用，--source new 才重算）
# ---------------------------------------------------------------------------
def find_latest_archive():
    if not ARCH_ROOT.exists():
        return None
    cands = [d for d in ARCH_ROOT.iterdir()
             if d.is_dir() and d.name.startswith(ARCH_PREFIX)
             and 'superseded' not in d.name
             and (d / NPZ_NAME).exists()]
    return max(cands, key=lambda d: d.name) if cands else None


def load_archive(archdir):
    d = np.load(archdir / NPZ_NAME, allow_pickle=False)
    return dict(x_el=d['compression_m'], v_back=d['v_back_mps'],
                phase=d['phase'], t=d['t_s'],
                cur_tot=d['current_n'], cur_fric=d['current_friction_n'],
                ref_tot=d['reference_n'], ref_fric=d['reference_friction_n'])


def save_archive(archdir, data, metrics, p: CouplerParams, stamp: str):
    import pandas as pd
    archdir.mkdir(parents=True, exist_ok=True)
    np.savez_compressed(
        archdir / NPZ_NAME,
        compression_m=data['x_el'], v_back_mps=data['v_back'], phase=data['phase'],
        t_s=data['t'], current_n=data['cur_tot'], current_friction_n=data['cur_fric'],
        reference_n=data['ref_tot'], reference_friction_n=data['ref_fric'])
    pd.DataFrame({
        'phase': data['phase'],
        't_s': data['t'],
        'compression_mm': data['x_el'] * 1000.0,
        'v_back_mps': data['v_back'],
        'current_kn': data['cur_tot'] / 1e3,
        'current_friction_kn': data['cur_fric'] / 1e3,
        'reference_kn': data['ref_tot'] / 1e3,
        'reference_friction_kn': data['ref_fric'] / 1e3,
    }).to_csv(archdir / CSV_NAME, index=False)
    meta = {
        'timestamp': stamp,
        'section': 'MT-2 缓冲器准静态加载-缓释阻抗曲线：当前模型 vs 于宗泽2025 参考',
        'protocol': {
            'type': 'quasi-static load-hold-release, compression positive',
            'compression_m': 'contact point (|e|=gap, x=0) to stroke 83 mm and back',
            'speed_mps': V_Q, 'hold_samples': N_HOLD, 'hold_speed_mps': 0.0,
            'dx_m': DX,
            'vehicle_setup': 'x_front=0, v_front=0 fixed; x_back=e-free_length, '
                             'v_back=+0.01 loading / 0 hold / -0.01 release',
        },
        'params': {k: float(getattr(p, k)) for k in
                   ['stiffness', 'preload_n', 'friction_n', 'friction_static_n',
                    'friction_v_er', 'friction_v_eps', 'unload_stiffness_ratio',
                    'coupler_gap_m', 'stroke_m', 'rigid_stiffness_nm',
                    'max_impulse_n', 'free_length_m', 'damping']},
        'models': {
            'current': 'src/train_dynamics/coupler.py::coupler_force (scalar, real '
                       'signature): dir_sm=tanh(s_e*dv/friction_v_eps), '
                       'fric_mag=-fric_amp*dir_sm, contact=tanh ramp, clip [0, 2270 kN]; '
                       'friction component isolated by re-evaluating with friction_n=0 '
                       'and friction_static_n=0',
            'reference': 'Yu2025 Eq.(1)-(2) literal: F = F0 + k*x + sgn(v)*mu(|v|)*FN; '
                         'sgn: loading=+1, |v|=0 -> 0, release=-1; mu Stribeck '
                         '(|v|=0 -> mu_s, linear to mu_d at v_er); same F0/k/mu as '
                         'current model; NO saturation clamp and NO non-negativity '
                         'clamp (literal Eqs. (1)-(2))',
        },
        'metrics': metrics,
        'figure': str(FIG_PATH),
        'note': '回应导师"装载缓释曲线太理想"的定量诊断；仅新增绘图脚本，'
                '未修改 src/ 物理逻辑。',
    }
    (archdir / 'run_meta.json').write_text(
        json.dumps(meta, ensure_ascii=False, indent=2), encoding='utf-8')
    logger.info('归档 → %s', archdir)


def main():
    ap = argparse.ArgumentParser(description='MT-2 加载-缓释准静态阻抗曲线（数据与绘图分离）')
    ap.add_argument('--source', choices=['auto', 'new'], default='auto',
                    help='auto：复用最近归档仅重画（缺则重算）；new：强制重算并新建归档')
    ap.add_argument('--archive', default=None, help='指定归档目录')
    args = ap.parse_args()

    stamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    p = CouplerParams()

    reuse = Path(args.archive) if args.archive else (
        find_latest_archive() if args.source == 'auto' else None)
    if reuse is not None and not (reuse / NPZ_NAME).exists():
        logger.warning('归档 %s 缺 %s，改为重算', reuse, NPZ_NAME)
        reuse = None

    if reuse is not None:
        logger.info('== 复用归档数据 %s（跳过重算） ==', reuse)
        data = load_archive(reuse)
    else:
        logger.info('== 重算：准静态加载(0.01 m/s) → 停止 → 释放 ==')
        x_el, v_back, phase, t = build_protocol(p.stroke_m, p.coupler_gap_m,
                                                p.free_length_m)
        cur_tot, cur_fric = evaluate_current(x_el, v_back, p)
        ref_tot, ref_fric = evaluate_reference(x_el, v_back, p)
        data = dict(x_el=x_el, v_back=v_back, phase=phase, t=t,
                    cur_tot=cur_tot, cur_fric=cur_fric,
                    ref_tot=ref_tot, ref_fric=ref_fric)

    metrics = compute_metrics(data['x_el'], data['phase'], data['cur_tot'],
                              data['cur_fric'], data['ref_tot'], data['ref_fric'])

    fe = metrics['loading_end_friction_kn']
    te = metrics['loading_end_total_kn']
    d5 = metrics['last_5mm_of_loading_delta_kn']
    ds = metrics['stop_at_83mm_v0_delta_kn']
    ha = metrics['hysteresis_area_kn_mm']
    logger.info('[self-check] 加载末段(|v|=0.01) 摩擦分量: 当前 %.1f kN vs 参考 %.1f kN '
                '(差 %.1f kN)', fe['current'], fe['reference'],
                fe['reference_minus_current'])
    logger.info('[self-check] 加载末段总阻抗: 当前 %.1f kN vs 参考 %.1f kN (差 %.1f kN)',
                te['current'], te['reference'], te['reference_minus_current'])
    logger.info('[self-check] 最后5mm: 当前 %+.1f kN (%s) vs 参考 %+.1f kN (%s)',
                d5['current'], d5['current_direction'],
                d5['reference'], d5['reference_direction'])
    logger.info('[self-check] 83mm处停止(v=0): 当前 %+.1f kN (%s) vs 参考 %+.1f kN (%s)',
                ds['current'], ds['current_direction'],
                ds['reference'], ds['reference_direction'])
    logger.info('[self-check] 迟滞环面积: 当前 %.0f vs 参考 %.0f kN·mm (比 %.1f×)',
                ha['current'], ha['reference'],
                ha['reference'] / ha['current'] if ha['current'] else float('nan'))

    make_figure(data['x_el'], data['phase'], data['cur_tot'], data['ref_tot'],
                metrics, FIG_PATH)

    if reuse is None:
        archdir = ARCH_ROOT / f'{ARCH_PREFIX}{stamp}'
        save_archive(archdir, data, metrics, p, stamp)
    logger.info('图 → %s；数据归档 → %s', FIG_PATH,
                reuse if reuse is not None else ARCH_ROOT / f'{ARCH_PREFIX}{stamp}')


if __name__ == '__main__':
    main()
