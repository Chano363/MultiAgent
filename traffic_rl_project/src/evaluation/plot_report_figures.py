"""组会汇报数据图生成（对照 2026-08-31 汇报）。

仅生成**数据图**（结构示意图由汇报人手工绘制）。全部数据来自已落盘产物，
不触发训练、不启动仿真，可在训练进行中安全执行。

产出（outputs/figures/report/）：
  fig_a_profile_49km.png        主训练剖面纵断面（49.6 km 真实，英文标注）
  坡度剖面/fig_grade_shuozhou_ningwuxi_beidaniu_49km.png / fig_grade_long_downhill_35km.png
                                49.6 km 与 35 km 纵断面（策展目录，英文标注）
  fig_b_training_curves.png     5 seed 训练曲线（return / 车钩力峰值 / 超限次数）
  fig_c_coupler_gate_isolation.png  车钩力安全层闸门开/关隔离对照（断面力峰值）
  fig_d_reward_design.png       奖励塑形曲线（领航列速度带 / 跟随列相对锚定 / 列间距）

用法（Windows，base Python 即可）：
    python src/evaluation/plot_report_figures.py
"""
import json
import logging
import re
from pathlib import Path

import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from src.utils.plot_style import setup_cjk_font
from src.train_dynamics.grade_profile import PROFILES

setup_cjk_font(verbose=False)
logging.basicConfig(level=logging.INFO, format='%(message)s')
logger = logging.getLogger('ReportFigures')

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / 'outputs' / 'figures' / 'report'
OUT.mkdir(parents=True, exist_ok=True)

CKPT_DIR = ROOT / 'outputs' / 'checkpoints' / 'formation'
COUPLER_LIMIT_KN = 1000.0


def save(fig, name):
    fig.tight_layout()
    fig.savefig(OUT / name, dpi=170, bbox_inches='tight')
    plt.close(fig)
    logger.info('已生成 %s', name)


# ── 图 A：线路纵断面（53.2 km 真实 / 35 km 设计） ─────────────────────────
PROFILE_DIR = ROOT / 'outputs' / 'sim_validation' / 'figures' / '坡度剖面'

# 剖面图统一风格：白底、细线、四边框、无渐变填充
plt.rcParams.update({
    'font.family': 'DejaVu Sans',
    'font.size': 10,
    'axes.linewidth': 0.8,
    'axes.edgecolor': '#333333',
    'xtick.direction': 'out',
    'ytick.direction': 'out',
})


def _sample_profile(prof, dx=50.0):
    """按里程采样坡度 → 相对首端高程（m）。剖面为分段常值，step 绘制。"""
    length = float(max(s.start_m for s in prof.segments))
    x = np.arange(0.0, length + dx * 0.5, dx)
    g = np.array([prof.grade_at(px) for px in x])            # 无量纲，负=下坡
    elev = np.concatenate([[0.0], np.cumsum(g[1:] * dx)])    # 相对首端高程（m）
    return x / 1000.0, g, elev, length


def _draw_profile(prof, title, outpaths):
    xkm, g, elev, length = _sample_profile(prof)
    gpm = g * 1000.0
    Lkm = length / 1000.0
    fig, (ax1, ax2) = plt.subplots(
        2, 1, figsize=(10, 5.2), sharex=True,
        gridspec_kw={'height_ratios': [1.25, 1], 'hspace': 0.10})

    def _mark_min(ax, y, text):
        """在曲线最低点标一个点并把说明放在其下方（独占空白区，不压曲线）。"""
        i = int(np.argmin(y))
        ax.plot(xkm[i], y[i], marker='o', ms=3, color='#333333')
        right = xkm[i] > 0.75 * Lkm
        ax.annotate(text, xy=(xkm[i], y[i]),
                    xytext=(-8 if right else 8, -13), textcoords='offset points',
                    fontsize=8.5, color='#333333',
                    ha='right' if right else 'left')

    ax1.plot(xkm, elev, color='#2b4c7e', lw=1.2)
    ax1.set_ylabel('Elevation (m)')
    ax1.set_title(title, fontsize=11.5)
    i1 = int(np.argmin(elev))
    _mark_min(ax1, elev, f'{elev[i1]:.0f} m at {xkm[i1]:.1f} km')
    span1 = float(elev.max() - elev.min()) or 1.0
    ax1.set_ylim(float(elev.min()) - 0.22 * span1, float(elev.max()) + 0.06 * span1)

    ax2.step(xkm, gpm, where='post', color='#2b4c7e', lw=1.0)
    ax2.axhline(0.0, color='#888888', lw=0.7)
    ax2.set_ylabel('Grade (‰)')
    ax2.set_xlabel('Distance (km)')
    ax2.set_xlim(0.0, Lkm)
    i2 = int(np.argmin(gpm))
    _mark_min(ax2, gpm, f'{gpm[i2]:.1f}‰')
    span2 = float(gpm.max() - gpm.min()) or 1.0
    ax2.set_ylim(float(gpm.min()) - 0.22 * span2, max(0.0, float(gpm.max())) + 0.06 * span2)

    for ax in (ax1, ax2):
        ax.grid(alpha=0.18, ls='-', lw=0.5)
        ax.tick_params(top=False, right=False)

    for p in outpaths:
        p.parent.mkdir(parents=True, exist_ok=True)
        fig.savefig(p, dpi=200, bbox_inches='tight')
        logger.info('已生成 %s', p)
    plt.close(fig)


def fig_profile():
    """49.6 km 真实剖面 + 35 km 设计剖面的纵断面图（英文标注，供汇报/论文）。"""
    _draw_profile(
        PROFILES['shuozhou_ningwuxi_beidaniu_49km'](),
        'Shuohuang line longitudinal profile (49.6 km, 50 measured segments)',
        [OUT / 'fig_a_profile_49km.png',
         PROFILE_DIR / 'fig_grade_shuozhou_ningwuxi_beidaniu_49km.png'],
    )
    _draw_profile(
        PROFILES['long_downhill_35km'](),
        'Synthetic long downhill profile (35 km)',
        [PROFILE_DIR / 'fig_grade_long_downhill_35km.png'],
    )


# ── 图 B：5 seed 训练曲线 ────────────────────────────────────────────────
LOG_EP = re.compile(
    r'Ep (\d+)/1400 \| R ([+-]?\d+) \| pkCpl (\d+)kN \| viol ([\d.]+) \| '
    r'loss ([-\d.eE+]+) \| gap_err ([-+]?\d+)m \| gap_min ([\d.]+)m')


def _read_v1_csv(path):
    """v1 训练历史：仅取 4 列行（episode,reward,peak_coupler_kN,violations）。"""
    ep, rw, pk, vi = [], [], [], []
    for line in path.read_text(encoding='utf-8').splitlines()[1:]:
        f = line.strip().split(',')
        if len(f) != 4:
            continue
        try:
            ep.append(int(float(f[0]))); rw.append(float(f[1]))
            pk.append(float(f[2])); vi.append(float(f[3]))
        except ValueError:
            continue
    return np.array(ep), np.array(rw), np.array(pk), np.array(vi)


def _read_v2_log(path):
    """v2 续训段：从进度日志解析逐回合指标（同回合重复行取末次）。"""
    rec = {}
    for line in path.read_text(encoding='utf-8', errors='ignore').splitlines():
        m = LOG_EP.search(line)
        if not m:
            continue
        rec[int(m.group(1))] = (float(m.group(2)), float(m.group(3)),
                                float(m.group(4)), float(m.group(5)))
    if not rec:
        return tuple(np.array([]) for _ in range(4))
    ep = np.array(sorted(rec))
    rw = np.array([rec[e][0] for e in ep])
    pk = np.array([rec[e][1] for e in ep])
    vi = np.array([rec[e][2] for e in ep])
    return ep, rw, pk, vi


def fig_training_curves():
    seeds = [0, 1, 2, 3, 4]
    colors = plt.cm.viridis(np.linspace(0.12, 0.85, len(seeds)))
    fig, axes = plt.subplots(3, 1, figsize=(11, 9.8), sharex=True)
    plotted = 0

    for s, c in zip(seeds, colors):
        v1 = CKPT_DIR / f'final_seed{s}' / 'results' / f'train_history_dec_ad2_cp_seed{s}.csv'
        lg = ROOT / 'outputs' / 'logs' / 'final_v2' / f'seed{s}.log'
        segs = []
        if v1.exists():
            segs.append(('v1', _read_v1_csv(v1)))
        if lg.exists():
            segs.append(('v2', _read_v2_log(lg)))
        if not segs:
            logger.warning('seed%d 无可用数据，跳过', s)
            continue
        plotted += 1
        last_ep = 0
        for tag, (ep, rw, pk, vi) in segs:
            if len(ep) == 0:
                continue
            last_ep = max(last_ep, int(ep.max()))
            ls = '-' if tag == 'v1' else '--'
            lab = f'seed{s}（至 Ep{last_ep}）' if tag == 'v2' or len(segs) == 1 else None
            axes[0].plot(ep, rw, lw=0.9, ls=ls, color=c, alpha=0.85, label=lab)
            axes[1].plot(ep, pk, lw=0.9, ls=ls, color=c, alpha=0.85)
            axes[2].plot(ep, vi, lw=0.9, ls=ls, color=c, alpha=0.85)

    if not plotted:
        logger.error('无可用训练数据')
        plt.close(fig)
        return

    axes[0].set_ylabel('单集回报', fontsize=11)
    axes[0].set_title('5 seed 训练曲线（实线 = 首段 CSV；虚线 = 续训段日志；训练进行中）',
                      fontsize=12.5, fontweight='bold')
    axes[0].legend(fontsize=8.5, ncol=2, loc='lower right')
    axes[0].grid(alpha=0.3, ls='--', lw=0.6)

    axes[1].axhline(COUPLER_LIMIT_KN, color='#a5281a', lw=1.4, ls='--')
    axes[1].text(2, COUPLER_LIMIT_KN + 22, '车钩力安全上限 1000 kN', fontsize=9, color='#a5281a')
    axes[1].set_ylabel('车钩力峰值 (kN)', fontsize=11)
    axes[1].grid(alpha=0.3, ls='--', lw=0.6)

    axes[2].set_ylabel('超限次数', fontsize=11)
    axes[2].set_xlabel('训练回合 episode', fontsize=11)
    axes[2].grid(alpha=0.3, ls='--', lw=0.6)

    save(fig, 'fig_b_training_curves.png')


# ── 图 C：车钩力安全层闸门隔离对照 ────────────────────────────────────────
def fig_gate_isolation():
    p = ROOT / 'outputs' / 'log_diag_regress_20260930.json'
    if not p.exists():
        logger.error('缺少 %s', p.name)
        return
    data = json.loads(p.read_text(encoding='utf-8'))
    base, res = data['baseline'], data['results']

    order = ['full', 'no_rl', 'no_traction', 'no_ab']
    labels = {'full': '完整策略', 'no_rl': '无 RL（纯规则）',
              'no_traction': '禁牵引', 'no_ab': '禁空气制动'}
    scen = [s for s in order if s in base and s in res]

    # 关闸门对照（仅 full / no_traction 有该组）→ 把「口径统一」与「AB 减权限闸门」
    # 两个改动的贡献拆开；没有这一组，两柱图会把二者混为一谈（无法支撑"减权限有效"）。
    def _off(s, field, scale=1.0):
        k = f'{s}_nogate'
        return res[k][field] / scale if k in res else float('nan')

    before = [base[s]['peak'] for s in scen]
    after = [res[s]['peak_n'] / 1000.0 for s in scen]
    off = [_off(s, 'peak_n', 1000.0) for s in scen]
    over_before = [base[s]['steps_over'] for s in scen]
    over_after = [res[s]['steps_over'] for s in scen]
    over_off = [_off(s, 'steps_over') for s in scen]

    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(13.2, 5.2),
                                   gridspec_kw={'width_ratios': [1.22, 1]})
    xi = np.arange(len(scen))
    w = 0.27
    _labs = ['修复前（旧：净力口径 / 无闸门）', '修复后（断面力口径 + 开闸门）',
             '修复后（断面力口径 + 关闸门）']

    def _draw(ax, series, hot_thresh):
        finite = [v for s in series for v in s if not np.isnan(v)]
        pad = 0.022 * (max(finite) if finite else 1.0)
        for k, (vals, c, lb) in enumerate(zip(series, ('#c0392b', '#2e7d9a', '#d98c2b'),
                                              _labs)):
            ax.bar(xi + (k - 1) * w, vals, w, color=c, alpha=0.88, label=lb)
            for xv, vv in zip(xi + (k - 1) * w, vals):
                if np.isnan(vv):
                    continue
                ax.text(xv, vv + pad, f'{vv:.0f}', ha='center', fontsize=8.5,
                        color='#a5281a' if vv > hot_thresh else '#1f3a5f')

    _draw(ax1, (before, after, off), COUPLER_LIMIT_KN)
    _draw(ax2, (over_before, over_after, over_off), 0.5)

    ax1.axhline(COUPLER_LIMIT_KN, color='#a5281a', lw=1.5, ls='--')
    ax1.text(-0.45, COUPLER_LIMIT_KN + 34, '安全上限 1000 kN', fontsize=9.5, color='#a5281a')
    ax1.set_ylim(0, max([v for s in (before, after, off) for v in s
                         if not np.isnan(v)] + [COUPLER_LIMIT_KN]) * 1.20)
    ax1.set_xticks(xi)
    ax1.set_xticklabels([labels[s] for s in scen], fontsize=10.5)
    ax1.set_ylabel('车钩力峰值（单钩断面力, kN）', fontsize=11)
    ax1.set_title('断面力峰值：口径统一 与 AB 减权限闸门 的贡献拆分',
                  fontsize=12.5, fontweight='bold')
    ax1.legend(fontsize=8.5, loc='upper center')
    ax1.grid(axis='y', alpha=0.3, ls='--', lw=0.6)

    ax2.set_xticks(xi)
    ax2.set_xticklabels([labels[s] for s in scen], fontsize=10.5)
    ax2.set_ylabel('超限步数（> 1000 kN 的步）', fontsize=11)
    ax2.set_title('超限步数：关闸门即复现破线', fontsize=12.5, fontweight='bold')
    ax2.legend(fontsize=8.5, loc='upper center')
    ax2.grid(axis='y', alpha=0.3, ls='--', lw=0.6)

    fig.suptitle(f'车钩力口径统一 + 空气制动减权限（AB 新增源闸门）隔离对照'
                 f'（seed {data.get("seed")}, {data.get("steps")} 步窗口）',
                 fontsize=13, fontweight='bold', y=1.02)

    save(fig, 'fig_c_coupler_gate_isolation.png')


# ── 图 D：奖励塑形曲线（公式直接取自 train_fleet_env._calculate_reward_decomposed）──
def fig_reward_design():
    # 与环境常量一致（formation_ed_ab_3train_1plus1.yaml / train_fleet_env.py）
    v_max = 80.0 / 3.6          # 22.222 m/s，线路限速
    v_min = 40.0 / 3.6          # 11.111 m/s，最小缓解速度
    v_center = 0.5 * (v_min + v_max)
    band_half = 0.5 * (v_max - v_min)
    SPD_SCALE, SPD_W = 3.0, 2.0

    fig, axes = plt.subplots(1, 3, figsize=(15, 4.6))

    # (a) 领航列：绝对速度带（带内 +6→0 线性；越带 -20·(dev-1)）
    ax = axes[0]
    v = np.linspace(30.0 / 3.6, 90.0 / 3.6, 1201)
    r = np.zeros_like(v)
    for i, vi in enumerate(v):
        nd = abs(vi - v_center) / band_half
        r[i] = 6.0 * (1.0 - 0.9 * nd) if nd <= 1.0 else -20.0 * (nd - 1.0)
        if vi > v_max:
            r[i] -= 5.0 * (vi - v_max)
    ax.plot(v * 3.6, r, color='#1f3b73', lw=2)
    ax.axvspan(v_min * 3.6, v_max * 3.6, color='#cfe0f0', alpha=0.5)
    ax.axhline(0, color='#7a8b99', lw=0.9)
    ax.axvline(v_max * 3.6, color='#a5281a', lw=1.2, ls='--')
    ax.text(v_max * 3.6 + 1.5, ax.get_ylim()[0] * 0.75, '线路限速\n80 km/h',
            fontsize=8, color='#a5281a')
    ax.text(v_min * 3.6 + 3, ax.get_ylim()[0] * 0.42, '允许速度带 [40, 80] km/h',
            fontsize=8, color='#1f3a5f')
    ax.set_xlabel('速度 (km/h)', fontsize=10.5)
    ax.set_ylabel('单步奖励分量', fontsize=10.5)
    ax.set_title('(a) 领航列 · 绝对速度带\n带内越近中心奖越大；越带线性硬罚',
                 fontsize=11.5, fontweight='bold')
    ax.grid(alpha=0.3, ls='--', lw=0.6)

    # (b) 跟随列：相对速度锚定（镜像前车，+2·max(0,1-(Δv/3)²)）
    ax = axes[1]
    dv = np.linspace(-8.0, 8.0, 801)
    rl = SPD_W * np.maximum(0.0, 1.0 - (dv / SPD_SCALE) ** 2)
    ax.plot(dv, rl, color='#2e7d32', lw=2)
    ax.fill_between(dv, rl, 0, color='#cfe6d8', alpha=0.6)
    ax.axvline(0, color='#7a8b99', lw=0.9)
    ax.axhline(0, color='#7a8b99', lw=0.9)
    ax.set_xlabel('本列速度 − 前列速度 Δv (m/s)', fontsize=10.5)
    ax.set_ylabel('单步奖励分量', fontsize=10.5)
    ax.set_title('(b) 跟随列 · 相对速度锚定\n镜像前列轨迹，|Δv|>3 m/s 不再奖励',
                 fontsize=11.5, fontweight='bold')
    ax.grid(alpha=0.3, ls='--', lw=0.6)

    # (c) 列间间距：高斯奖 + 过大线性罚 + 追尾势场
    ax = axes[2]
    ge = np.linspace(-100.0, 400.0, 1201)
    rg = np.exp(-(ge / 140.0) ** 2)
    rg = rg - np.where(ge > 150.0, 0.02 * (ge - 150.0), 0.0)
    dyn_gap = 100.0
    actual = dyn_gap + ge
    min_gap = dyn_gap * 0.4
    pot = np.where(actual < min_gap, np.maximum(-200.0, -2.0 * (min_gap - actual) ** 2), 0.0)
    ax.plot(ge, rg, color='#1f3b73', lw=2, label='列距误差项（高斯 + 过大线性罚）')
    ax.plot(ge, pot / 100.0, color='#c0392b', lw=2, ls='--',
            label='追尾势场 / 100（间距 < 40% 动态安全距）')
    ax.axvline(0, color='#7a8b99', lw=0.9, ls='-')
    ax.axhline(0, color='#7a8b99', lw=0.9)
    ax.set_xlabel('列距误差（实际 − 目标, m）', fontsize=10.5)
    ax.set_ylabel('单步奖励分量', fontsize=10.5)
    ax.set_title('(c) 列间间距\n目标距处峰值 +1；过近由势场强罚兜底',
                 fontsize=11.5, fontweight='bold')
    ax.legend(fontsize=8.5, loc='lower left')
    ax.grid(alpha=0.3, ls='--', lw=0.6)

    fig.suptitle('编队奖励塑形（机车级 ED/AB 分解架构；公式直接取自环境实现）',
                 fontsize=13, fontweight='bold', y=1.03)
    save(fig, 'fig_d_reward_design.png')


if __name__ == '__main__':
    fig_profile()
    fig_training_curves()
    fig_gate_isolation()
    fig_reward_design()
    logger.info('全部输出目录：%s', OUT)