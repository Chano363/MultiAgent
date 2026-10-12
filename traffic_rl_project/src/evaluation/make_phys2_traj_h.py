"""第10页(间距安全机理)轨迹图：改成 1 行 × 3 列横向布局（速度/间距/车钩力）。
输入 outputs/results_phys2/traj_{m1_full_seed0|m3_full}.csv
输出 outputs/figures/fig_phys2_traj_h.png（中文 CJK 字体）。
"""
import sys
from pathlib import Path


import pandas as pd
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import matplotlib.font_manager as fm

# setup_cjk_font 仅查 WSL 路径；本机为 Windows 侧，直接注册 Windows 中文字体
def _ensure_cjk_font():
    cands = [
        (r'C:\Windows\Fonts\msyh.ttc', 'Microsoft YaHei'),
        (r'C:\Windows\Fonts\simhei.ttf', 'SimHei'),
        (r'C:\Windows\Fonts\simsun.ttc', 'SimSun'),
    ]
    known = {f.name for f in fm.fontManager.ttflist}
    for path, name in cands:
        if not Path(path).exists():
            continue
        if name not in known:
            try:
                fm.fontManager.addfont(path)
            except Exception:
                continue
            known = {f.name for f in fm.fontManager.ttflist}
        if name in known:
            plt.rcParams['font.family'] = 'sans-serif'
            plt.rcParams['font.sans-serif'] = [name] + plt.rcParams.get('font.sans-serif', [])
            plt.rcParams['axes.unicode_minus'] = False
            return name
    return None


_FONT = _ensure_cjk_font()
if _FONT:
    print(f"[make_phys2_traj_h] 中文字体: {_FONT}")
else:
    print("[make_phys2_traj_h] 警告：未找到中文字体")

RESULTS = Path('outputs/results_phys2')
FIG = Path('outputs/figures')
FIG.mkdir(parents=True, exist_ok=True)

m1 = pd.read_csv(RESULTS / 'traj_m1_full_seed0.csv')
m3 = pd.read_csv(RESULTS / 'traj_m3_full.csv')
t = m1['step'] * 0.1 / 60.0

fig, axes = plt.subplots(1, 3, figsize=(16, 4.4))

# --- 速度 ---
ax = axes[0]
ax.plot(t, m3['speed_mean'], color='tab:red', lw=1.1, label='No-C（无协同）')
ax.plot(t, m1['speed_mean'], color='tab:blue', lw=1.4, label='M-MARL（本文）')
ax.axhline(80, color='k', ls='--', lw=0.8); ax.axhline(40, color='k', ls='--', lw=0.8)
ax.text(t.iloc[-1] * 0.01, 82.5, '限速 80', fontsize=9)
ax.text(t.iloc[-1] * 0.01, 42.5, '限速 40', fontsize=9)
ax.set_xlabel('时间 (min)'); ax.set_ylabel('速度 (km/h)')
ax.legend(loc='upper right', fontsize=9)
ax.set_title('速度轨迹', fontsize=13)

# --- 间距 ---
ax = axes[1]
ax.plot(t, m3['gap_1'], color='tab:red', lw=1.0, label='No-C（无协同）')
ax.plot(t, m1['gap_1'], color='tab:blue', lw=1.3, label='M-MARL（本文）')
ax.axhline(0, color='k', ls='-', lw=0.8)
ax.axhline(5, color='r', ls='--', lw=1.0)
ax.text(t.iloc[-1] * 0.01, 8.0, '安全间距阈值 5 m', fontsize=9, color='red')
ax.set_xlabel('时间 (min)'); ax.set_ylabel('列1-列2 间距 (m)')
ax.legend(loc='upper right', fontsize=9)
ax.set_title('间距保持', fontsize=13)

# --- 车钩力 ---
ax = axes[2]
ax.plot(t, m3['coupler_peak_kN'], color='tab:red', lw=1.0, label='No-C（无协同）')
ax.plot(t, m1['coupler_peak_kN'], color='tab:blue', lw=1.3, label='M-MARL（本文）')
ax.axhline(1000, color='r', ls='--', lw=1.0)
ax.text(t.iloc[-1] * 0.01, 1020, '1000 kN 安全限值', fontsize=9, color='red')
ax.set_ylim(0, 1200)
ax.set_xlabel('时间 (min)'); ax.set_ylabel('车钩力峰值 (kN)')
ax.legend(loc='upper right', fontsize=9)
ax.set_title('列内车钩力', fontsize=13)

for ax in axes:
    ax.grid(alpha=0.3)
fig.suptitle('朔黄线 3×万吨群组 长下坡循环制动：M-MARL（协同） vs No-C（无协同）', fontsize=12)
fig.tight_layout(rect=[0, 0, 1, 0.94])
fig.savefig(FIG / 'fig_phys2_traj_h.png', dpi=160)
plt.close(fig)
print("已生成 fig_phys2_traj_h.png")