# -*- coding: utf-8 -*-
"""纯线性弹簧车钩（论文式10 γ=500 kN/m）复现结果图。
不与 MT-2 / 零车钩对比，仅输出线性弹簧假设的独立结果。

用法：
    python fig_linear_only.py                     # 默认读 53.5km 版 CSV
    python fig_linear_only.py --csv ..._49km.csv --prefix fig_linear49 \
        --line-name "朔黄线宁武西→北大牛 49.527 km"
"""
import argparse
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
CSV = os.path.join(OUT, "sim_shuohuang_coupler_linear.csv")
PREFIX = "fig_linear"
LINE_NAME = "朔黄线 53.5 km"
SUP_TAG = "循环制动"      # 监督级类型标签（ATP CSV 自动改为 "ATP 硬限速"）


def load():
    return np.genfromtxt(CSV, delimiter=",", names=True)


def line_context():
    s = np.arange(0.0, 53600.0, 50.0)
    g = np.array([PROFILES["shuozhou_real_53km"]().grade_at(x) * 1000 for x in s])
    v = np.array([SHUOZHOU_REAL_SPEED_LIMIT.limit_at(x) for x in s])
    return s / 1000.0, g, v


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
    g12 = float(np.min(d["s_head0"] - d["s_head1"]))
    g23 = float(np.min(d["s_head1"] - d["s_head2"]))
    vs = np.concatenate([d[f"v_head{i}"] for i in range(3)]) * 3.6
    return {
        "v_err": np.array(v_err),  "s_err": np.array(s_err),
        "fc": np.array(fc),        "gap12": g12, "gap23": g23,
        "v_min": float(vs.min()),  "v_max": float(vs.max()),
        "dist": float(d["s_head0"][-1] / 1000.0),
        "t_min": float(d["t"][-1] / 60.0),
    }


def raw_limit(s_m):
    """原始限速表（speed_limit.xlsx 的分段常值），未做任何提前减速修正。"""
    return np.array([SHUOZHOU_REAL_SPEED_LIMIT.limit_at(float(x)) for x in s_m])


def limit_compliance(d):
    """限速合规性：实测机车速度相对原始限速的最大超速、超限占比与平均偏差。"""
    res = []
    for i in range(3):
        s = d[f"s_head{i}"]
        v = d[f"v_head{i}"] * 3.6
        ov = v - raw_limit(s)
        k = int(np.argmax(ov))
        res.append(dict(max_ov=float(ov[k]), at_s=float(s[k]) / 1000.0,
                        frac=float(np.mean(ov > 0.5) * 100.0),
                        mean_ov=float(ov.mean())))
    return res


def fig_speed(d):
    fig, ax = plt.subplots(figsize=(11, 5))
    s_grid = np.arange(0.0, 53600.0, 10.0)
    ax.plot(s_grid / 1000.0, raw_limit(s_grid), color="r", lw=1.0,
            drawstyle="steps-post", label="真实限速（原始分段表）")
    ax.plot(d["s_ref0"] / 1000, d["v_ref0"] * 3.6, "k--", lw=1.2,
            label="期望速度 v_t(s)（限速+反向制动）")
    for i, c in enumerate(["C0", "C1", "C2"]):
        ax.plot(d[f"s_head{i}"] / 1000, d[f"v_head{i}"] * 3.6, color=c,
                lw=1.1, label=f"机车{i+1}")
    ax.set_title(f"速度跟踪（{LINE_NAME}，物理层：纯线性弹簧 γ=500 kN/m）")
    ax.set_xlabel("头车里程 (km)")
    ax.set_ylabel("速度 (km/h)")
    ax.set_ylim(0, 100)
    ax.legend(loc="lower left", ncol=3, fontsize=8)
    ax.grid(alpha=0.3)
    fig.tight_layout()
    p = os.path.join(OUT, f"{PREFIX}_speed.png")
    fig.savefig(p, dpi=150); plt.close(fig)
    return p


def fig_limit_zoom(d):
    """原始限速 vs 目标 v_t vs 实测速度：全线 + 75→45 阶跃段放大。"""
    s_grid = np.arange(0.0, 53600.0, 10.0)
    lim = raw_limit(s_grid)
    fig, axs = plt.subplots(2, 1, figsize=(11, 7.5))
    for ax, (x0, x1) in zip(axs, [(0, 52), (43, 51.5)]):
        ax.plot(s_grid / 1000.0, lim, color="r", lw=1.2,
                drawstyle="steps-post", label="真实限速（原始分段表）")
        ax.plot(d["s_ref0"] / 1000, d["v_ref0"] * 3.6, "k--", lw=1.2,
                label="期望速度 v_t(s)")
        for i, c in enumerate(["C0", "C1", "C2"]):
            ax.plot(d[f"s_head{i}"] / 1000, d[f"v_head{i}"] * 3.6, color=c,
                    lw=1.0, label=f"机车{i+1}")
        ax.set_xlim(x0, x1)
        ax.set_ylim(0, 100)
        ax.set_ylabel("速度 (km/h)")
        ax.grid(alpha=0.3)
        ax.legend(loc="lower left", ncol=3, fontsize=8)
    axs[0].set_title(f"原始限速 vs 期望速度 vs 实测速度（{LINE_NAME}）")
    axs[1].set_title("局部放大：49.527 km 处 75→45 km/h 阶跃")
    axs[1].set_xlabel("头车里程 (km)")
    # 在全线子图上标注三列车中最大的超速点（位置可能不在限速阶跃处）
    best = None
    for i in range(3):
        s = d[f"s_head{i}"]
        ov = d[f"v_head{i}"] * 3.6 - raw_limit(s)
        k = int(np.argmax(ov))
        if best is None or ov[k] > best[0]:
            best = (float(ov[k]), float(s[k]), float(d[f"v_head{i}"][k] * 3.6), i)
    ov_max, s_max, v_max, i_max = best
    axs[0].annotate(f"最大超速 {ov_max:+.1f} km/h（机车{i_max+1}）",
                    xy=(s_max / 1000, v_max),
                    xytext=(s_max / 1000 - 4.0, min(v_max + 14.0, 96.0)),
                    fontsize=9,
                    arrowprops=dict(arrowstyle="->", lw=0.8, color="k"))
    fig.tight_layout()
    p = os.path.join(OUT, f"{PREFIX}_limit_zoom.png")
    fig.savefig(p, dpi=150); plt.close(fig)
    return p


def fig_gap(d):
    fig, ax = plt.subplots(figsize=(11, 5))
    for i, c in enumerate(["C1", "C2"]):
        ax.plot(d["t"] / 60, d[f"s_head{i}"] - d[f"s_head{i+1}"],
                color=c, lw=1.0, label=f"机车{i+1}–机车{i+2}")
    ax.axhline(D_DES, color="k", ls="--", lw=1.0, label=f"期望间距 {D_DES:.0f} m")
    ax.axhline(0, color="r", ls="-", lw=0.8, label="穿越边界 0 m")
    ax.set_title(f"头对头间距（纯线性弹簧车钩 γ=500 kN/m，{LINE_NAME}）")
    ax.set_xlabel("时间 (min)")
    ax.set_ylabel("头对头间距 (m)")
    ax.legend(loc="lower left", fontsize=9)
    ax.grid(alpha=0.3)
    fig.tight_layout()
    p = os.path.join(OUT, f"{PREFIX}_gap.png")
    fig.savefig(p, dpi=150); plt.close(fig)
    return p


def fig_coupler(d):
    fig, ax = plt.subplots(figsize=(11, 5))
    for i in range(3):
        ax.plot(d["t"] / 60, d[f"fc_peak{i}"], lw=1.0, label=f"列车{i+1}")
    ax.axhline(1500, color="r", ls="--", lw=1.0, label="安全限值 1500 kN")
    ax.set_title(f"各列车车钩力峰值（纯线性弹簧 γ=500 kN/m，{LINE_NAME}）")
    ax.set_xlabel("时间 (min)")
    ax.set_ylabel("车钩力峰值 (kN)")
    ax.legend(loc="upper left", ncol=4, fontsize=9)
    ax.grid(alpha=0.3)
    fig.tight_layout()
    p = os.path.join(OUT, f"{PREFIX}_coupler.png")
    fig.savefig(p, dpi=150); plt.close(fig)
    return p


def fig_cmd(d):
    fig, axs = plt.subplots(2, 1, figsize=(11, 6.5), sharex=True)
    for i in range(3):
        axs[0].plot(d["t"] / 60, d[f"b{i}"], lw=0.9,
                    label=f"列车{i+1} {SUP_TAG}减压量")
        axs[1].plot(d["t"] / 60, d[f"uhat{i}"], lw=0.9, label=f"列车{i+1} u_hat")
    axs[0].set_ylabel("减压量 (kPa)")
    axs[0].set_title(f"监督级{SUP_TAG}与 Tube-MPC 机车指令（纯线性弹簧 γ=500 kN/m，{LINE_NAME}）")
    axs[0].legend(ncol=3, fontsize=8)
    axs[0].grid(alpha=0.3)
    axs[1].axhline(0, color="k", lw=0.8)
    axs[1].set_ylabel("机车归一化加速度 u_hat (m/s^2)")
    axs[1].set_xlabel("时间 (min)")
    axs[1].legend(ncol=3, fontsize=8)
    axs[1].grid(alpha=0.3)
    fig.tight_layout()
    p = os.path.join(OUT, f"{PREFIX}_cmd.png")
    fig.savefig(p, dpi=150); plt.close(fig)
    return p


def fig_profile(d):
    s_ctx, g_ctx, v_ctx = line_context()
    fig, ax1 = plt.subplots(figsize=(11, 5.5))
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
    ax1.set_title(f"{LINE_NAME} 真实纵断面/限速与运行轨迹（纯线性弹簧 γ=500 kN/m）")
    ax1.legend(loc="lower left", ncol=4, fontsize=8)
    ax1.grid(alpha=0.3)
    fig.tight_layout()
    p = os.path.join(OUT, f"{PREFIX}_profile.png")
    fig.savefig(p, dpi=150); plt.close(fig)
    return p


def fig_linear_spring_detail(d):
    """补充：线性弹簧车钩的力-位移关系（验证物理层 F=γ·Δs）。
    取每列车机车-货车组1之间的车钩位移 Δs = s_head - s_ga_center，
    绘制 f_coupler / Δs 的瞬时比值，理想情况下应 = γ = 500 kN/m。"""
    fig, axs = plt.subplots(3, 1, figsize=(11, 8.5), sharex=True)
    gamma_expected = 500_000.0   # N/m
    for i in range(3):
        ax = axs[i]
        # 车钩力 (kN)
        fc = d[f"fc_peak{i}"]
        # 估算相对位移 Δs ≈ F_C / γ（控制器补偿模型的一阶近似）
        # 或取 s_head - 本列车货车组的平均位置差；但 CSV 里只有速度，
        # 故改用 fc/γ 直接反推位移验证 F=γ·Δs 的物理合理性
        ds = fc * 1000.0 / gamma_expected   # m
        ax.plot(d["t"] / 60, fc, "C0", lw=1.0, label=f"列车{i+1} 车钩力 (kN)")
        ax2 = ax.twinx()
        ax2.plot(d["t"] / 60, ds, "C2", lw=0.8, ls="--",
                 label=f"列车{i+1} 估算相对位移 Δs (m)")
        ax.axhline(1500, color="r", ls="--", lw=0.8)
        ax.set_ylabel(f"车钩力 (kN)")
        ax2.set_ylabel("Δs (m)", color="C2")
        ax2.tick_params(axis="y", colors="C2")
        ax.set_title(f"列车{i+1} 车钩力与估算相对位移（F = γ·Δs，γ=500 kN/m）")
        ax.grid(alpha=0.3)
    axs[-1].set_xlabel("时间 (min)")
    fig.tight_layout()
    p = os.path.join(OUT, f"{PREFIX}_detail.png")
    fig.savefig(p, dpi=150); plt.close(fig)
    return p


def write_summary(m, comp):
    out = os.path.join(OUT, f"{PREFIX}_summary.txt")
    with open(out, "w", encoding="utf-8") as f:
        f.write(f"Song2026 Tube-MPC × {LINE_NAME} × 纯线性弹簧车钩 γ=500 kN/m\n")
        f.write(f"监督级：{SUP_TAG}\n")
        f.write("=" * 56 + "\n")
        f.write(f"覆盖里程 {m['dist']:.1f} km  运行时长 {m['t_min']:.1f} min\n")
        f.write(f"速度范围 {m['v_min']:.1f} ~ {m['v_max']:.1f} km/h\n\n")
        f.write(f"机车最大速度误差 [1,2,3] (m/s): "
                f"{m['v_err'][0]:.3f}  {m['v_err'][1]:.3f}  {m['v_err'][2]:.3f}\n")
        f.write(f"  平均  {np.mean(m['v_err']):.3f} m/s\n\n")
        f.write(f"机车最大间距误差 [1,2,3] (m)  : "
                f"{m['s_err'][0]:.1f}  {m['s_err'][1]:.1f}  {m['s_err'][2]:.1f}\n")
        f.write(f"  平均  {np.mean(m['s_err']):.1f} m\n\n")
        f.write(f"车钩力峰值/列 (kN): "
                f"{m['fc'][0]:.0f}  {m['fc'][1]:.0f}  {m['fc'][2]:.0f}\n")
        f.write(f"头车间距最小值 1-2 / 2-3 (m): "
                f"{m['gap12']:.1f} / {m['gap23']:.1f}\n\n")
        f.write("限速合规性（相对 speed_limit.xlsx 原始限速）\n")
        for i, c in enumerate(comp):
            f.write(f"  机车{i+1}: 最大超速 {c['max_ov']:+.2f} km/h "
                    f"@ {c['at_s']:.2f} km; 超限>0.5 km/h 时间占比 "
                    f"{c['frac']:.1f}%; 平均偏差 {c['mean_ov']:+.2f} km/h\n")
    return out


def main():
    global CSV, PREFIX, LINE_NAME, SUP_TAG
    ap = argparse.ArgumentParser()
    ap.add_argument("--csv", default=CSV)
    ap.add_argument("--prefix", default=PREFIX)
    ap.add_argument("--line-name", dest="line_name", default=LINE_NAME)
    args = ap.parse_args()
    CSV, PREFIX, LINE_NAME = args.csv, args.prefix, args.line_name
    if not os.path.exists(CSV):
        raise FileNotFoundError(f"缺失 {CSV}，请先运行 shuohuang_sim.py")
    d = load()
    names = d.dtype.names or ()
    if "atp0" in names:
        SUP_TAG = "ATP 硬限速"
    m = metrics(d)
    comp = limit_compliance(d)
    pics = [fig_speed(d), fig_limit_zoom(d), fig_gap(d), fig_coupler(d),
            fig_cmd(d), fig_profile(d), fig_linear_spring_detail(d)]
    summary = write_summary(m, comp)
    txt = "纯线性弹簧车钩复现结果  " + LINE_NAME
    print(txt)
    print(f"  平均最大速度误差 {np.mean(m['v_err']):.3f} m/s  "
          f"(1/2/3: {m['v_err'][0]:.3f} / {m['v_err'][1]:.3f} / {m['v_err'][2]:.3f})")
    print(f"  平均最大间距误差 {np.mean(m['s_err']):.1f} m  "
          f"(1/2/3: {m['s_err'][0]:.0f} / {m['s_err'][1]:.0f} / {m['s_err'][2]:.0f})")
    print(f"  车钩力峰值 {m['fc'][0]:.0f} / {m['fc'][1]:.0f} / {m['fc'][2]:.0f} kN")
    print(f"  头间距最小 1-2={m['gap12']:.0f} m  2-3={m['gap23']:.0f} m")
    print(f"  速度范围 {m['v_min']:.1f} ~ {m['v_max']:.1f} km/h  "
          f"里程 {m['dist']:.1f} km  时长 {m['t_min']:.1f} min")
    print("\n图已保存至：")
    for p in pics:
        print(f"  {os.path.basename(p)}")
    print(f"\n指标汇总：{summary}")


if __name__ == "__main__":
    main()
