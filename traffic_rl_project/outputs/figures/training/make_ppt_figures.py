"""【PPT 专用出图】重新生成组会 PPT 引用的 3 张图，保证图内文字在幻灯片上清晰可读。

背景
----
原图按论文排版设计（figsize 窄、字号 10pt），在 1280×720 幻灯片中被缩到 250px 高，
图内文字实际只有 ~4px，完全看不清。

原理
----
图内文字在屏幕上的实际像素高度：

    px = 字号(pt) × 幻灯片显示宽度(px) / (72 × 图宽(inch))

与 dpi 无关（dpi 只影响位图清晰度）。因此要让文字够大，必须：
  1. 缩小 figsize 宽度（让"每 inch 承载的 pt 数"变少 → 相对字号变大）
  2. 把子图改为横排，适配 16:9 幻灯片
  3. 显式调大字号

各图的显示宽度（由 HTML 布局实测反推）：
  追尾机理三联图   ~1036 px   → 系数 1036/(72×12) = 1.199
  主对比双联图     ~586  px   → 系数  586/(72×9)  = 0.904
  压力消融单图     ~578  px   → 系数  578/(72×8)  = 1.003

目标：所有文字 ≥ 13 px。

输出：ppt_talk/train-marl-talk/assets/*.png
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

# ---------- 字体（Windows 中文） ----------
plt.rcParams["font.sans-serif"] = ["Microsoft YaHei", "SimHei", "DejaVu Sans"]
plt.rcParams["axes.unicode_minus"] = False

ASSETS = ROOT / "ppt_talk" / "train-marl-talk" / "assets"
RESULTS = ROOT / "outputs" / "results_phys2"
ASSETS.mkdir(parents=True, exist_ok=True)

# ---------- 配色 ----------
C_M1 = "#1f6fb2"     # M-MARL 蓝
C_M3 = "#c0392b"     # No-C 红
C_OK = "#1e7d43"     # 安全绿
C_WARN = "#a5372f"   # 警示红


def _style_axes(ax, fs_label, fs_tick, fs_title, title, ylabel, xlabel=None):
    ax.set_title(title, fontsize=fs_title, fontweight="bold", pad=10)
    ax.set_ylabel(ylabel, fontsize=fs_label)
    if xlabel:
        ax.set_xlabel(xlabel, fontsize=fs_label)
    ax.tick_params(axis="both", labelsize=fs_tick)
    ax.grid(alpha=0.30, ls="--", lw=0.7)


# ============================================================
# 图 1：追尾机理三联图（速度 / 间距 / 车钩力）— 1 行 3 列横排
# ============================================================
def fig_trajectory():
    m1 = pd.read_csv(RESULTS / "traj_m1_5seed_seed0.csv")
    m3 = pd.read_csv(RESULTS / "traj_m3.csv")
    t = m1["step"] * 0.1 / 60.0  # 分钟

    FS_TITLE, FS_LABEL, FS_TICK, FS_LEG, FS_ANN = 15, 13, 12.5, 12, 12

    fig, axes = plt.subplots(1, 3, figsize=(12, 4.4))

    # (a) 速度
    ax = axes[0]
    ax.plot(t, m3["speed_mean"], color=C_M3, lw=1.8, ls="--", label="No-C（无协同）")
    ax.plot(t, m1["speed_mean"], color=C_M1, lw=2.0, label="M-MARL（本文）")
    ax.axhline(80, color="#555", ls="--", lw=1.0)
    ax.axhline(40, color="#555", ls=":", lw=1.0)
    ax.text(t.iloc[-1] * 0.03, 82.5, "上限 80", fontsize=FS_ANN, color="#555")
    ax.text(t.iloc[-1] * 0.03, 42.0, "下限 40", fontsize=FS_ANN, color="#555")
    _style_axes(ax, FS_LABEL, FS_TICK, FS_TITLE, "(a) 速度轨迹", "速度 (km/h)", "时间 (min)")
    ax.legend(loc="lower left", fontsize=FS_LEG, framealpha=0.95)

    # (b) 最小列间距 —— 本页核心
    ax = axes[1]
    ax.plot(t, m3["gap_min"], color=C_M3, lw=1.8, ls="--", label="No-C（无协同）")
    ax.plot(t, m1["gap_min"], color=C_M1, lw=2.2, label="M-MARL（本文）")
    ax.axhline(0, color=C_WARN, ls="-", lw=1.4)
    ax.text(t.iloc[-1] * 0.03, 12, "追尾线（间距=0）", fontsize=FS_ANN, color=C_WARN)
    # 标注 No-C 崩溃区间
    broken = (m3["gap_min"] < 0)
    if broken.any():
        i0 = int(np.argmax(broken.values))
        ax.axvspan(t.iloc[i0], t.iloc[-1], color=C_WARN, alpha=0.07)
        ax.annotate("No-C 间距跌破零\n（追尾 69 步）",
                    xy=(t.iloc[i0], 0), xytext=(t.iloc[i0] - t.iloc[-1] * 0.42, 150),
                    fontsize=FS_ANN, color=C_WARN, fontweight="bold",
                    arrowprops=dict(arrowstyle="->", color=C_WARN, lw=1.2))
    _style_axes(ax, FS_LABEL, FS_TICK, FS_TITLE, "(b) 最小列间距", "最小列间距 (m)", "时间 (min)")
    ax.legend(loc="upper right", fontsize=FS_LEG, framealpha=0.95)

    # (c) 车钩力
    ax = axes[2]
    ax.plot(t, m3["coupler_peak_kN"], color=C_M3, lw=1.6, ls="--", label="No-C（无协同）")
    ax.plot(t, m1["coupler_peak_kN"], color=C_M1, lw=1.8, label="M-MARL（本文）")
    ax.axhline(1000, color=C_WARN, ls="--", lw=1.3)
    ax.text(t.iloc[-1] * 0.03, 1030, "安全限值 1000 kN", fontsize=FS_ANN, color=C_WARN)
    _style_axes(ax, FS_LABEL, FS_TICK, FS_TITLE, "(c) 峰值车钩力", "峰值车钩力 (kN)", "时间 (min)")
    ax.legend(loc="lower right", fontsize=FS_LEG, framealpha=0.95)

    fig.tight_layout()
    out = ASSETS / "fig_phys2_coop_noc_trajectory.png"
    fig.savefig(out, dpi=200, facecolor="white", bbox_inches="tight")
    plt.close(fig)
    print(f"[OK] {out.name}  {_size(out)}")


# ============================================================
# 图 2：主对比（累计回报 + 峰值车钩力）— 1 行 2 列
# ============================================================
def fig_main_compare():
    methods = ["M-MARL\n(本文)", "No-C\n(无协同)", "DQN-fair", "MPC"]
    reward = [36004, 9791, -15215, -115622]
    coupler = [659, 543, 463, 1178]
    coll = [0, 69, 157, 0]
    colors = ["#2d6a9f", "#c0504d", "#9a8fb5", "#b5893a"]

    FS_TITLE, FS_LABEL, FS_TICK, FS_ANN = 18, 16, 15, 15

    fig, axes = plt.subplots(1, 2, figsize=(9, 4.0))
    x = np.arange(len(methods))

    # (a) 累计回报
    ax = axes[0]
    bars = ax.bar(x, [r / 1000 for r in reward], 0.58, color=colors)
    ax.axhline(0, color="k", lw=1.0)
    ax.set_xticks(x)
    ax.set_xticklabels(methods, fontsize=FS_TICK)
    _style_axes(ax, FS_LABEL, FS_TICK, FS_TITLE, "累计回报", "回报 (×10³)")
    for b, v, c in zip(bars, reward, coll):
        ax.text(b.get_x() + b.get_width() / 2, b.get_height() + 2.5,
                f"+{v/1000:.1f}k" if v > 0 else f"{v/1000:.1f}k",
                ha="center", fontsize=FS_ANN, fontweight="bold")
        if c > 0:
            ax.text(b.get_x() + b.get_width() / 2, 4.0, f"追尾 {c} 步",
                    ha="center", fontsize=FS_ANN - 1, color=C_WARN, fontweight="bold")
    ax.set_ylim(min(reward) / 1000 * 1.15, max(reward) / 1000 * 1.22)

    # (b) 峰值车钩力
    ax = axes[1]
    bars = ax.bar(x, coupler, 0.58, color=colors)
    ax.axhline(1000, color=C_WARN, ls="--", lw=1.6)
    ax.text(0.03, 1035, "上限 1000 kN", fontsize=FS_ANN - 1, color=C_WARN, fontweight="bold")
    ax.set_xticks(x)
    ax.set_xticklabels(methods, fontsize=FS_TICK)
    ax.set_ylim(0, 1380)
    _style_axes(ax, FS_LABEL, FS_TICK, FS_TITLE, "峰值车钩力", "峰值车钩力 (kN)")
    for b, v in zip(bars, coupler):
        color = C_WARN if v > 1000 else "#222"
        ax.text(b.get_x() + b.get_width() / 2, v + 32, f"{v}",
                ha="center", fontsize=FS_ANN, fontweight="bold", color=color)

    fig.tight_layout()
    out = ASSETS / "fig_phys2_main_compare.png"
    fig.savefig(out, dpi=200, facecolor="white", bbox_inches="tight")
    plt.close(fig)
    print(f"[OK] {out.name}  {_size(out)}")


# ============================================================
# 图 3：压力消融（回报 + 协同增益双轴）
# ============================================================
def fig_pressure_ablation():
    gaps = [100, 40]
    m_marl = [36004, 36365]
    m_noc = [9791, -11137]
    gain = [a - b for a, b in zip(m_marl, m_noc)]

    FS_TITLE, FS_LABEL, FS_TICK, FS_LEG, FS_ANN = 15, 14, 13.5, 13, 13

    fig, ax1 = plt.subplots(figsize=(8, 5.2))
    x = np.arange(len(gaps))

    l1 = ax1.plot(x, m_marl, "-o", color=C_M1, lw=2.8, ms=10, label="M-MARL（协同）")[0]
    l2 = ax1.plot(x, m_noc, "--s", color=C_M3, lw=2.4, ms=9, label="No-C（独立）")[0]
    ax1.axhline(0, color="#888", lw=1.0, ls=":")
    ax1.set_xticks(x)
    ax1.set_xticklabels([f"{g} m" for g in gaps], fontsize=FS_TICK)
    _style_axes(ax1, FS_LABEL, FS_TICK, FS_TITLE,
                "压力消融：间距越压缩，协同增益越大", "累计回报", "目标列间距（→ 压力增大）")

    ax2 = ax1.twinx()
    l3 = ax2.plot(x, gain, "-D", color=C_OK, lw=2.8, ms=10, label="协同增益（M-MARL − No-C）")[0]
    ax2.set_ylabel("协同增益", fontsize=FS_LABEL, color=C_OK)
    ax2.tick_params(axis="y", labelsize=FS_TICK, labelcolor=C_OK)

    for xi, g in zip(x, gain):
        ax2.annotate(f"+{g:,}", (xi, g), textcoords="offset points", xytext=(0, 12),
                     ha="center", fontsize=FS_ANN, color=C_OK, fontweight="bold")

    ax1.legend(handles=[l1, l2, l3], loc="center left", fontsize=FS_LEG, framealpha=0.95)
    fig.tight_layout()
    out = ASSETS / "fig_pressure_ablation.png"
    fig.savefig(out, dpi=200, facecolor="white", bbox_inches="tight")
    plt.close(fig)
    print(f"[OK] {out.name}  {_size(out)}")


def _size(p):
    from PIL import Image
    w, h = Image.open(p).size
    return f"{w}×{h}px  {p.stat().st_size // 1024}KB"


if __name__ == "__main__":
    print("重新生成 PPT 图表（大字号 / 横版）…")
    fig_trajectory()
    fig_main_compare()
    fig_pressure_ablation()
    print("完成。")
