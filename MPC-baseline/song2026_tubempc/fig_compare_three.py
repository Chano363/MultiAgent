# -*- coding: utf-8 -*-
"""三种物理车钩假设的对比图：MT-2迟滞 / 线性弹簧(γ=500) / 全部置零"""
import os
import sys

import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

plt.rcParams["font.sans-serif"] = ["SimHei", "Microsoft YaHei"]
plt.rcParams["axes.unicode_minus"] = False

sys.path.insert(0, r"d:\Z\first station\multi-agent-main\traffic_rl_project")
from src.train_dynamics.grade_profile import (PROFILES, SHUOZHOU_REAL_SPEED_LIMIT)

BASE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(BASE, "outputs_shuohuang")
D_DES = 2000.0
CASES = {
    "mt2":    ("MT-2 迟滞车钩", "C0"),
    "linear": ("纯线性弹簧 γ=500 kN/m", "C2"),
    "zero":   ("全部阻抗置零",       "0.6"),
}


def load(tag):
    return np.genfromtxt(os.path.join(OUT, f"sim_shuohuang_coupler_{tag}.csv"),
                         delimiter=",", names=True)


def line_context():
    s = np.arange(0.0, 53600.0, 50.0)
    g = np.array([PROFILES["shuozhou_real_53km"]().grade_at(x) * 1000 for x in s])
    v = np.array([SHUOZHOU_REAL_SPEED_LIMIT.limit_at(x) for x in s])
    return s / 1000.0, g, v


def fig_three_speed():
    """速度跟踪对比（三组叠画在同一张图）"""
    fig, ax = plt.subplots(figsize=(12, 5.5))
    s_ctx, _, v_ctx = line_context()
    ax.plot(s_ctx, v_ctx, "k--", lw=1.5, label="真实限速", zorder=0)
    for tag, (name, c) in CASES.items():
        d = load(tag)
        ax.plot(d["s_head0"] / 1000, d["v_head0"] * 3.6, color=c,
                lw=1.0, label=name, zorder=1)
    ax.set_title("三种车钩假设下机车1速度跟踪对比（朔黄线 53.5 km）")
    ax.set_xlabel("头车里程 (km)")
    ax.set_ylabel("速度 (km/h)")
    ax.legend(loc="lower left", ncol=3, fontsize=9)
    ax.grid(alpha=0.3)
    ax.set_ylim(0, 100)
    fig.tight_layout()
    p = os.path.join(OUT, "fig_compare_speed.png")
    fig.savefig(p, dpi=150); plt.close(fig)
    return p


def fig_three_gap():
    """头对头间距对比"""
    fig, ax = plt.subplots(figsize=(12, 5.5))
    for tag, (name, c) in CASES.items():
        d = load(tag)
        ax.plot(d["t"] / 60, d["s_head0"] - d["s_head1"],
                color=c, lw=1.0, label=f"{name} (1-2)")
        ax.plot(d["t"] / 60, d["s_head1"] - d["s_head2"],
                color=c, lw=1.0, ls=":", alpha=0.5)
    ax.axhline(D_DES, color="k", ls="--", lw=1.0, label=f"期望 {D_DES:.0f} m")
    ax.axhline(0, color="r", ls="-", lw=0.8, label="穿越边界 0 m")
    ax.set_title("三种车钩假设下头对头间距对比（实线 1–2，虚线 2–3）")
    ax.set_xlabel("时间 (min)")
    ax.set_ylabel("头对头间距 (m)")
    ax.legend(loc="lower left", fontsize=9)
    ax.grid(alpha=0.3)
    fig.tight_layout()
    p = os.path.join(OUT, "fig_compare_gap.png")
    fig.savefig(p, dpi=150); plt.close(fig)
    return p


def fig_three_coupler():
    """车钩力对比（开启组才有，zero 全为 0）"""
    fig, ax = plt.subplots(figsize=(12, 5.5))
    for tag, (name, c) in CASES.items():
        d = load(tag)
        max_fc = np.max(np.vstack([d[f"fc_peak{i}"] for i in range(3)]), axis=0)
        ax.plot(d["t"] / 60, max_fc, color=c, lw=1.0, label=name)
    ax.axhline(1500, color="r", ls="--", lw=0.9, label="安全限值 1500 kN")
    ax.set_title("三种车钩假设下三列车车钩力峰值对比（取最大值）")
    ax.set_xlabel("时间 (min)")
    ax.set_ylabel("车钩力峰值 (kN)")
    ax.legend(loc="upper left", fontsize=9)
    ax.grid(alpha=0.3)
    fig.tight_layout()
    p = os.path.join(OUT, "fig_compare_coupler.png")
    fig.savefig(p, dpi=150); plt.close(fig)
    return p


def fig_bar_metrics():
    """指标柱状图对比"""
    fig, axs = plt.subplots(1, 3, figsize=(14, 4.5))

    def metrics(d):
        v_err = []
        for i in range(3):
            if i == 0:
                v_err.append(float(np.max(np.abs(d["v_ref0"] - d["v_head0"]))))
            else:
                v_err.append(float(np.max(np.abs(d[f"v_head{i-1}"] - d[f"v_head{i}"]))))
        s_err = []
        for i in range(3):
            if i == 0:
                s_err.append(float(np.max(np.abs(d["s_ref0"] - d["s_head0"]))))
            else:
                s_err.append(float(np.max(np.abs(
                    (d[f"s_head{i-1}"] - d[f"s_head{i}"]) - D_DES))))
        fc = [float(d[f"fc_peak{i}"].max()) for i in range(3)]
        return np.mean(v_err), np.mean(s_err), max(fc)

    xs = [0, 1, 2]
    names = [CASES[k][0] for k in ["mt2", "linear", "zero"]]
    colors = [CASES[k][1] for k in ["mt2", "linear", "zero"]]
    data = {tag: metrics(load(tag)) for tag in ["mt2", "linear", "zero"]}

    for col, idx, title in [(0, 0, "平均最大速度误差 (m/s)"),
                             (1, 1, "平均最大间距误差 (m)"),
                             (2, 2, "车钩力峰值 max (kN)")]:
        ax = axs[col]
        vals = [data[tag][idx] for tag in ["mt2", "linear", "zero"]]
        ax.bar(xs, vals, color=colors, edgecolor="k", lw=0.5)
        ax.set_xticks(xs); ax.set_xticklabels(names, rotation=15, fontsize=9)
        ax.set_title(title, fontsize=11)
        ax.grid(alpha=0.3, axis="y")
        for x, v in zip(xs, vals):
            ax.text(x, v, f"{v:.1f}", ha="center", va="bottom", fontsize=9)

    fig.suptitle("三种物理车钩假设的关键指标对比", fontsize=13)
    fig.tight_layout()
    p = os.path.join(OUT, "fig_compare_metrics.png")
    fig.savefig(p, dpi=150); plt.close(fig)
    return p


def main():
    pics = [fig_three_speed(), fig_three_gap(), fig_three_coupler(), fig_bar_metrics()]
    print("对比图已生成：")
    for p in pics:
        print(f"  {os.path.basename(p)}")
    print(f"路径：{OUT}")


if __name__ == "__main__":
    main()
