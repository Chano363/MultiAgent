# -*- coding: utf-8 -*-
"""朔黄线真实线路复现结果图：速度跟踪、车间距、车钩力、指令与线路剖面"""
import os
import sys

import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

plt.rcParams["font.sans-serif"] = ["SimHei", "Microsoft YaHei"]
plt.rcParams["axes.unicode_minus"] = False

sys.path.insert(0, r"d:\Z\first station\multi-agent-main\traffic_rl_project")
from src.train_dynamics.grade_profile import (PROFILES,                  # noqa: E402
                                              SHUOZHOU_REAL_SPEED_LIMIT)

BASE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(BASE, "outputs_shuohuang")
D_DES = 2000.0
CASES = ["shuohuang_coupler_on", "shuohuang_coupler_off"]
NAMES = {"shuohuang_coupler_on": "车钩力开启", "shuohuang_coupler_off": "车钩力物理关闭"}


def load(tag):
    return np.genfromtxt(os.path.join(OUT, f"sim_{tag}.csv"),
                         delimiter=",", names=True)


def line_context(ax_s):
    """在给定横轴为里程(km)的坐标轴上画真实纵断面(右轴)与限速。"""
    s = np.arange(0.0, 53600.0, 50.0)
    g = np.array([PROFILES["shuozhou_real_53km"]().grade_at(x) * 1000
                  for x in s])
    v = np.array([SHUOZHOU_REAL_SPEED_LIMIT.limit_at(x) for x in s])
    return s / 1000.0, g, v


def compare_fig(data):
    """改进前(v1) vs 改进后(v2) 对比图：间距、车钩力、速度误差。"""
    v1 = {tag: np.genfromtxt(os.path.join(OUT, f"sim_{tag}_v1.csv"),
                             delimiter=",", names=True) for tag in CASES}
    fig, axs = plt.subplots(2, 2, figsize=(12, 7.5))

    # (a) 开启组：头对头间距
    ax = axs[0, 0]
    for lab, dd, c in [("改进前", v1["shuohuang_coupler_on"], "0.6"),
                       ("改进后", data["shuohuang_coupler_on"], "C1")]:
        ax.plot(dd["t"] / 60, dd["s_head0"] - dd["s_head1"], color=c, lw=1.0,
                label=lab)
    ax.axhline(D_DES, color="k", ls="--", lw=0.8)
    ax.set_title("(a) 开启组 头对头间距 1-2")
    ax.set_ylabel("间距 (m)")
    ax.legend(fontsize=8)

    # (b) 开启组：三列车车钩力峰值的最大值
    ax = axs[0, 1]
    for lab, dd, c in [("改进前", v1["shuohuang_coupler_on"], "0.6"),
                       ("改进后", data["shuohuang_coupler_on"], "C1")]:
        ax.plot(dd["t"] / 60, np.max(np.vstack([dd[f"fc_peak{i}"] for i in range(3)]),
                                     axis=0), color=c, lw=0.8, label=lab)
    ax.axhline(1500, color="r", ls="--", lw=0.9, label="限值 1500 kN")
    ax.set_title("(b) 开启组 车钩力峰值（三列车取大）")
    ax.set_ylabel("车钩力 (kN)")
    ax.legend(fontsize=8)

    # (c) 开启组：机车1 速度跟踪误差
    ax = axs[1, 0]
    for lab, dd, c in [("改进前", v1["shuohuang_coupler_on"], "0.6"),
                       ("改进后", data["shuohuang_coupler_on"], "C1")]:
        ax.plot(dd["t"] / 60, dd["v_ref0"] * 3.6 - dd["v_head0"] * 3.6,
                color=c, lw=0.8, label=lab)
    ax.axhline(0, color="k", lw=0.8)
    ax.set_title("(c) 开启组 机车1 速度跟踪误差")
    ax.set_ylabel("v_ref - v (km/h)")
    ax.set_xlabel("时间 (min)")
    ax.legend(fontsize=8)

    # (d) 关闭组：头对头间距（安全性）
    ax = axs[1, 1]
    for lab, dd, c in [("改进前", v1["shuohuang_coupler_off"], "0.6"),
                       ("改进后", data["shuohuang_coupler_off"], "C0")]:
        ax.plot(dd["t"] / 60, dd["s_head0"] - dd["s_head1"], color=c, lw=1.0,
                label=lab)
    ax.axhline(0, color="r", ls="-", lw=0.9, label="穿越边界 0 m")
    ax.set_title("(d) 关闭组 头对头间距 1-2（消融安全性）")
    ax.set_ylabel("间距 (m)")
    ax.set_xlabel("时间 (min)")
    ax.legend(fontsize=8)

    for ax in axs.ravel():
        ax.grid(alpha=0.3)
    fig.suptitle("循环制动改进前后对比（γ=500 kN/m，朔黄线真实线路）")
    fig.tight_layout()
    fig.savefig(os.path.join(OUT, "fig_sh_compare.png"), dpi=150)


def main():
    data = {tag: load(tag) for tag in CASES}
    prof = PROFILES["shuozhou_real_53km"]()
    s_ctx, g_ctx, v_ctx = line_context(None)

    # ---- 图1：速度跟踪（两组） ----
    fig, axs = plt.subplots(2, 1, figsize=(11, 7.5), sharex=True)
    for r, tag in enumerate(CASES):
        d = data[tag]
        ax = axs[r]
        ax.plot(d["s_ref0"] / 1000, d["v_ref0"] * 3.6, "k--", lw=1.2,
                label="目标速度(真实限速)")
        for i, c in enumerate(["C0", "C1", "C2"]):
            ax.plot(d["s_head0"] / 1000, d[f"v_head{i}"] * 3.6, color=c,
                    lw=1.0, label=f"机车{i+1}")
        ax.set_title(f"朔黄线 53.5 km 真实线路（{NAMES[tag]}）")
        ax.set_ylabel("速度 (km/h)")
        ax.legend(loc="lower left", ncol=4, fontsize=8)
        ax.grid(alpha=0.3)
        ax.set_ylim(0, 100)
    axs[1].set_xlabel("头车里程 (km)")
    fig.tight_layout()
    fig.savefig(os.path.join(OUT, "fig_sh_speed.png"), dpi=150)

    # ---- 图2：车间距（两组） ----
    fig, axs = plt.subplots(2, 1, figsize=(11, 7.5), sharex=True)
    for r, tag in enumerate(CASES):
        d = data[tag]
        ax = axs[r]
        for i, c in enumerate(["C1", "C2"]):
            gap = d[f"s_head{i}"] - d[f"s_head{i+1}"]
            ax.plot(d["t"] / 60, gap, color=c, lw=1.0, label=f"机车{i+1}-机车{i+2}")
        ax.axhline(D_DES, color="k", ls="--", lw=1.0, label="期望间距 2000 m")
        ax.set_title(f"列车头对头间距（{NAMES[tag]}）")
        ax.set_ylabel("头对头间距 (m)")
        ax.legend(loc="lower left", ncol=3, fontsize=8)
        ax.grid(alpha=0.3)
    axs[1].set_xlabel("时间 (min)")
    fig.tight_layout()
    fig.savefig(os.path.join(OUT, "fig_sh_gap.png"), dpi=150)

    # ---- 图3：车钩力（开启组；关闭组应为 0） ----
    fig, axs = plt.subplots(2, 1, figsize=(11, 7), sharex=True)
    for r, tag in enumerate(CASES):
        d = data[tag]
        ax = axs[r]
        for i in range(3):
            ax.plot(d["t"] / 60, d[f"fc_peak{i}"], lw=0.8, label=f"列车{i+1}")
        ax.axhline(1500, color="r", ls="--", lw=1.0, label="安全限值 1500 kN")
        ax.set_title(f"各列车最大车钩力（{NAMES[tag]}）")
        ax.set_ylabel("车钩力峰值 (kN)")
        ax.legend(loc="upper left", ncol=4, fontsize=8)
        ax.grid(alpha=0.3)
    axs[1].set_xlabel("时间 (min)")
    fig.tight_layout()
    fig.savefig(os.path.join(OUT, "fig_sh_coupler.png"), dpi=150)

    # ---- 图4：指令与监督制动（开启组） ----
    d = data["shuohuang_coupler_on"]
    fig, axs = plt.subplots(2, 1, figsize=(11, 7), sharex=True)
    for i in range(3):
        axs[0].plot(d["t"] / 60, d[f"b{i}"], lw=0.8,
                    label=f"列车{i+1} 循环制动减压量")
        axs[1].plot(d["t"] / 60, d[f"uhat{i}"], lw=0.8, label=f"列车{i+1} u_hat")
    axs[0].set_ylabel("减压量 (kPa)")
    axs[0].legend(ncol=3, fontsize=8)
    axs[0].grid(alpha=0.3)
    axs[0].set_title("监督级空气制动与 Tube-MPC 机车指令（车钩力开启）")
    axs[1].axhline(0, color="k", lw=0.8)
    axs[1].set_ylabel("机车归一化加速度 u_hat (m/s^2)")
    axs[1].set_xlabel("时间 (min)")
    axs[1].legend(ncol=3, fontsize=8)
    axs[1].grid(alpha=0.3)
    fig.tight_layout()
    fig.savefig(os.path.join(OUT, "fig_sh_cmd.png"), dpi=150)

    # ---- 图5：线路剖面与运行轨迹（开启组） ----
    fig, ax1 = plt.subplots(figsize=(11, 5.5))
    d = data["shuohuang_coupler_on"]
    for i in range(3):
        ax1.plot(d[f"s_head{i}"] / 1000, d[f"v_head{i}"] * 3.6, lw=1.0,
                 label=f"机车{i+1}")
    ax1.plot(s_ctx, v_ctx, "k--", lw=1.2, label="真实限速")
    ax1.set_xlabel("里程 (km)")
    ax1.set_ylabel("速度 (km/h)")
    ax1.set_ylim(0, 100)
    ax2 = ax1.twinx()
    ax2.plot(s_ctx, g_ctx, color="0.6", lw=0.8)
    ax2.set_ylabel("坡度 (‰)", color="0.4")
    ax2.tick_params(axis="y", colors="0.4")
    ax1.set_title("朔黄线 53.5 km 真实纵断面/限速与 Tube-MPC 运行轨迹（车钩力开启）")
    ax1.legend(loc="lower left", ncol=4, fontsize=8)
    ax1.grid(alpha=0.3)
    fig.tight_layout()
    fig.savefig(os.path.join(OUT, "fig_sh_profile.png"), dpi=150)

    if os.path.exists(os.path.join(OUT, f"sim_{CASES[0]}_v1.csv")):
        compare_fig(data)

    print("图已保存至", OUT)


if __name__ == "__main__":
    main()
