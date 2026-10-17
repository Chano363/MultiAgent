"""【2026-10-16】MT-2 装载缓释曲线跨文献对照：当前模型 vs 容嘉欣2025 vs 于宗泽2025 解析式。

背景：用户问"有没有其他文献可以对比"。本地文献库（docs/papers/01_coupler_physics/）
可量化对照 = 于宗泽2025《重载列车车钩缓冲装置纵向动力学精细化模型》（中国铁道科学
46(2):192-202）式(1) 解析库仑迟滞：

    加载 fl(x) = F0 + μd·FN + k·x
    卸载 fu(x) = max(F0 − μd·FN + k·x, 0)      （缓冲器仅受压，负值截断）

参数锚（RESEARCH_POSITIONING §1.2 / VALIDATION_BASELINE「诊断-2026-09-06 文献复核」）：
F0=200 kN、μd·FN=500 kN、k=1.89e7 N/m（=18.9 kN/mm，(2270−200−500)/83 反推，
fl(83mm)=2268.7≈2270 kN 额定锚）；μs=750 kN 与 v_er=0.2 为标定值，准静态运动支
用 μd。静摩擦尖峰（式(2) |v|=0 → μs）只在加载末端瞬时出现，不在准静态支上。

不可量化对照（仅图、未数字化，图上文字注明）：马卫华2011 图1（MT-2 动态阻抗）、
杨辉2020 图4（MT-2 数学模型，过渡刚度 80 kN/mm 在正文）、于宗泽2025 图7
（6/8 km/h 冲击试验曲线，冲击速度下加载支整体更高）。

数据/绘图分离（铁律）：当前模型与容嘉欣读点两条曲线**直接复用**
`mt2_load_release_cmp_*` 最近归档（plot_mt2_load_release.py 产物，同一准静态
0.01 m/s 协议），不重算；于宗泽解析支由 CouplerParams 参数闭式计算。

产出：
    图 → outputs/sim_validation/figures/mt2_coupler/mt2_load_release_cross_literature.png
    数据 → outputs/sim_validation/phys_validation/mt2_cross_lit_<时间戳>/
         mt2_cross_literature.npz + .csv + run_meta.json

用法（WSL traffic_rl）：
    python src/evaluation/plot_mt2_cross_literature.py
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

logging.basicConfig(level=logging.INFO, format='%(message)s')
logger = logging.getLogger('MT2CrossLit')

ARCH_ROOT = Path('outputs') / 'sim_validation' / 'phys_validation'
SRC_PREFIX = 'mt2_load_release_cmp_'      # 复用来源归档
OUT_PREFIX = 'mt2_cross_lit_'
FIG_PATH = (Path('outputs') / 'sim_validation' / 'figures' / 'mt2_coupler'
            / 'mt2_load_release_cross_literature.png')
NPZ_NAME = 'mt2_load_release.npz'         # 来源归档数据文件
OUT_NPZ = 'mt2_cross_literature.npz'
OUT_CSV = 'mt2_cross_literature.csv'


def find_latest_source_archive():
    cands = [d for d in ARCH_ROOT.iterdir()
             if d.is_dir() and d.name.startswith(SRC_PREFIX)
             and 'superseded' not in d.name and (d / NPZ_NAME).exists()]
    if not cands:
        raise FileNotFoundError(f'缺 {SRC_PREFIX}* 归档，先运行 plot_mt2_load_release.py')
    return max(cands, key=lambda d: d.name)


def yuzongze2025_branches(x_m, p: CouplerParams):
    """于宗泽2025 式(1) 准静态解析支（N，压缩为正）。

    fl = F0 + μd·FN + k·x；fu = clip(F0 − μd·FN + k·x, 0, ∞)。
    k 用 CouplerParams.stiffness（=1.89e7 N/m 文献锚），x 为缓冲器压缩量。
    """
    x_mm = x_m * 1000.0
    k_kn_per_mm = p.stiffness / 1e6                # 1.89e7 N/m = 18.9 kN/mm
    fl = p.preload_n + p.friction_n + k_kn_per_mm * x_mm * 1e3   # N
    fu = np.clip(p.preload_n - p.friction_n + k_kn_per_mm * x_mm * 1e3,
                 0.0, None)                                       # N
    return fl, fu


def _trapz(y, x):
    trap = getattr(np, 'trapezoid', None) or np.trapz
    return float(trap(y, x))


def main():
    ap = argparse.ArgumentParser(description='MT-2 装载缓释跨文献对照（复用归档数据）')
    ap.add_argument('--archive', default=None, help='指定来源归档目录')
    args = ap.parse_args()

    stamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    p = CouplerParams()
    src = Path(args.archive) if args.archive else find_latest_source_archive()
    d = np.load(src / NPZ_NAME, allow_pickle=False)
    x = d['compression_m']
    phase = d['phase']
    cur = d['current_n']
    lit = d['literature_n']
    li = np.flatnonzero(phase == 'load')
    ui = np.flatnonzero(phase == 'unload')

    yz_fl, yz_fu = yuzongze2025_branches(x, p)
    x_mm = x * 1000.0
    area_cur = _trapz(cur[li] - cur[ui][::-1], x_mm[li]) / 1e3   # N·mm → kN·mm
    area_lit = _trapz(lit[li] - lit[ui][::-1], x_mm[li]) / 1e3
    area_yz = _trapz(yz_fl[li] - yz_fu[li], x_mm[li]) / 1e3
    end_cur = float(cur[li][-1] / 1e3)
    end_lit = float(lit[li][-1] / 1e3)
    end_yz = float(yz_fl[li][-1] / 1e3)
    # 低行程段（0-20 mm）加载支分歧：容嘉欣表缓升 vs 于宗泽解析阶跃
    low = x_mm[li] <= 20.0
    dev_low = float(np.max(np.abs(cur[li][low] - yz_fl[li][low]) / 1e3))
    logger.info('[self-check] 加载末端: 当前 %.1f / 容嘉欣 %.1f / 于宗泽解析 %.1f kN',
                end_cur, end_lit, end_yz)
    logger.info('[self-check] 迟滞环面积: 当前 %.0f / 容嘉欣 %.0f / 于宗泽解析 %.0f kN·mm',
                area_cur, area_lit, area_yz)
    logger.info('[self-check] 0-20mm 加载支 当前 vs 于宗泽解析 最大偏差 %.1f kN', dev_low)

    fig, ax = plt.subplots(figsize=(9.5, 6.5))
    ax.plot(x_mm[li], cur[li] / 1e3, color='#1f77b4', lw=2.0,
            label='Current model (Rong2025 table), loading')
    ax.plot(x_mm[ui], cur[ui] / 1e3, color='#1f77b4', lw=2.0, ls='--',
            label='Current model (Rong2025 table), release')
    ax.plot(x_mm[li], lit[li] / 1e3, color='#2ca02c', lw=1.0,
            label='Rong2025 Fig. 4(b) readpoints, loading')
    ax.plot(x_mm[ui], lit[ui] / 1e3, color='#2ca02c', lw=1.0,
            label='Rong2025 Fig. 4(b) readpoints, release')
    ax.plot(x_mm[li], yz_fl[li] / 1e3, color='#ff7f0e', lw=1.6, ls='-.',
            label='Yu2025 Eq. (1) analytic, loading')
    ax.plot(x_mm[ui], yz_fu[ui] / 1e3, color='#ff7f0e', lw=1.6, ls=':',
            label='Yu2025 Eq. (1) analytic, release')
    ax.axhline(1000, color='red', ls='--', lw=1.0)
    ax.text(55.0, 1030, '1000 kN coupler force limit', color='red', fontsize=8)
    ax.axhline(0, color='k', lw=0.6)
    ax.axvline(0, color='k', lw=0.6)

    lines = [
        'Quasi-static protocol 0.01 m/s (archived), compression positive',
        'Yu2025 analytic: F = F0 +/- mu_d*FN + k*x, '
        'F0=200 kN, mu_d*FN=500 kN, k=18.9 kN/mm',
        'Loading end: %.1f kN current, %.1f kN Rong2025, %.1f kN Yu2025 analytic'
        % (end_cur, end_lit, end_yz),
        'Hysteresis loop area: %.0f kN mm current, %.0f kN mm Rong2025, '
        '%.0f kN mm Yu2025 analytic' % (area_cur, area_lit, area_yz),
        'Low-stroke divergence 0-20 mm loading branch: %.0f kN '
        '(step at contact in analytic vs soft rise in table)' % dev_low,
        'Impact-speed curves (Ma2011 Fig.1, Yang2020 Fig.4, Yu2025 Fig.7) '
        'are image-only, not overlaid',
    ]
    ax.text(0.015, 0.985, '\n'.join(lines), transform=ax.transAxes, va='top',
            ha='left', fontsize=8.2,
            bbox=dict(boxstyle='round', facecolor='white', alpha=0.88, edgecolor='0.7'))

    ax.set_xlabel('Compression (mm)')
    ax.set_ylabel('Resistance (kN)')
    ax.set_title('MT-2 Buffer Load-Release Curve Against Rong2025 and Yu2025 Literature',
                 fontsize=12)
    ax.legend(fontsize=8.0, loc='lower right')
    ax.grid(alpha=0.3)
    fig.tight_layout()
    FIG_PATH.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(FIG_PATH, dpi=150, bbox_inches='tight')
    plt.close(fig)
    logger.info('已生成 %s', FIG_PATH)

    outdir = ARCH_ROOT / f'{OUT_PREFIX}{stamp}'
    outdir.mkdir(parents=True, exist_ok=True)
    np.savez_compressed(outdir / OUT_NPZ, compression_m=x, phase=phase,
                        current_n=cur, literature_n=lit,
                        yuzongze_loading_n=yz_fl, yuzongze_release_n=yz_fu)
    import pandas as pd
    pd.DataFrame({
        'phase': phase,
        'compression_mm': x_mm,
        'current_kn': cur / 1e3,
        'rong2025_kn': lit / 1e3,
        'yuzongze2025_loading_kn': yz_fl / 1e3,
        'yuzongze2025_release_kn': yz_fu / 1e3,
    }).to_csv(outdir / OUT_CSV, index=False)
    meta = {
        'timestamp': stamp,
        'section': 'MT-2 装载缓释跨文献对照：当前模型（容嘉欣表）vs 容嘉欣读点 vs 于宗泽2025 式(1) 解析支',
        'source_archive': str(src),
        'yuzongze2025': {
            'formula': 'FM = F0 + kx + (sgn v)*mu*FN, Eq.(1) 中国铁道科学 46(2):192-202',
            'F0_kn': p.preload_n / 1e3, 'mu_d_FN_kn': p.friction_n / 1e3,
            'k_n_per_mm': p.stiffness / 1e6,
            'anchor_note': 'fl(83mm)=2268.7 kN ≈ 2270 额定锚；'
                           'μs=750/v_er=0.2 为标定值（式(2) 尖峰仅 |v|=0 瞬时），准静态支用 μd',
        },
        'not_overlaid': '马卫华2011 图1 / 杨辉2020 图4 / 于宗泽2025 图7 均为冲击速度动态曲线（仅图像），未数字化',
        'metrics': {
            'loading_end_kn': {'current': end_cur, 'rong2025': end_lit,
                               'yuzongze_analytic': end_yz},
            'hysteresis_area_kn_mm': {'current': area_cur, 'rong2025': area_lit,
                                      'yuzongze_analytic': area_yz},
            'low_stroke_0_20mm_max_dev_kn': dev_low,
        },
        'figure': str(FIG_PATH),
    }
    (outdir / 'run_meta.json').write_text(
        json.dumps(meta, ensure_ascii=False, indent=2), encoding='utf-8')
    logger.info('归档 → %s', outdir)


if __name__ == '__main__':
    main()
