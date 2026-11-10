# -*- coding: utf-8 -*-
"""P12 主视觉：仿真验证与动作预判（①②③ 面板拼图版）。

面板内直接嵌入 images/ 下已归档的真实数据图（不重画、不手绘）：
  ① 高保真仿真：纵向动力学方程（模型方程）＋ fig_mt2_hysteresis.png
     （MT-2 迟滞特性）＋ fig_air_brake_build.png（空气制动建立，
     1+0 口径 brake_build_1plus0_108 归档）＋ fig_profile_49km.png（真实剖面）
  ② 动作预演：predecision_coupler_peak_kn（决策前预演峰值）vs
     coupler_interface_force_n（实测断面力峰值），读自
     single_production_newmark_70kmh_full_20261104/trajectory.npz 归档
  ③ 全程验证：横链 + 控制指令/状态反馈标注

输出：ppt_talk/midterm_20261018/images/示意底稿/fig_v4_verify.png（覆盖）
"""
import os

import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import FancyBboxPatch, Polygon
from PIL import Image

plt.rcParams["font.family"] = "Microsoft YaHei"
plt.rcParams["axes.unicode_minus"] = False

NAVY = "#2F4A7A"
RED = "#C00000"
LBLUE = "#DCE6F2"
LORANGE = "#FDF2E2"
LGRAY = "#F4F6FA"

ROOT = r"D:\Code\MultiAgent\traffic_rl_project"
PPT_IMAGES = os.path.join(ROOT, "ppt_talk", "midterm_20261018", "images")
BASE = os.path.join(ROOT, "outputs", "sim_validation", "phys_validation")
RUN = os.path.join(BASE, "single_production_newmark_70kmh_full_20261104")
OUT = os.path.join(ROOT, "ppt_talk", "midterm_20261018", "images", "示意底稿")

FIG_W, FIG_H = 12.8, 5.3  # 比例约 2.4:1，铺满 16:9 版心


def box(ax, x, y, w, h, fc="white", ec=NAVY, lw=1.8, rounding=0.06):
    ax.add_patch(FancyBboxPatch((x, y), w, h,
                 boxstyle="round,pad=0,rounding_size=%.3f" % rounding,
                 facecolor=fc, edgecolor=ec, linewidth=lw, linestyle="-"))


def place_png(fig, ax, path, x, y, w, h):
    """把现成 png 等比嵌入数据坐标区域（居中 fit），返回嵌入小轴。"""
    img = np.array(Image.open(path))
    ih, iw = img.shape[:2]
    if iw / ih > w / h:
        dw, dh = w, w * ih / iw
    else:
        dh, dw = h, h * iw / ih
    px, py = x + (w - dw) / 2, y + (h - dh) / 2
    pos = ax.get_position()  # ax 在 figure 中的 fraction
    fx0 = pos.x0 + px / FIG_W * pos.width
    fy0 = pos.y0 + py / FIG_H * pos.height
    ax_img = fig.add_axes([fx0, fy0, dw / FIG_W * pos.width,
                           dh / FIG_H * pos.height], zorder=3)
    ax_img.imshow(img)
    ax_img.axis("off")
    return ax_img


def load_run():
    z = np.load(os.path.join(RUN, "trajectory.npz"))
    dt = 0.1  # 917 步 = 91.7 s
    t = np.arange(z["coupler_interface_force_n"].shape[0]) * dt
    force_kn = z["coupler_interface_force_n"][:, 0, :].max(axis=1) / 1000.0
    pre_kn = z["predecision_coupler_peak_kn"][:, 0]  # 本身已是 kN
    return t, force_kn, pre_kn


def main():
    fig, ax = plt.subplots(figsize=(FIG_W, FIG_H))
    ax.set_xlim(0, FIG_W)
    ax.set_ylim(0, FIG_H)
    ax.axis("off")
    fig.canvas.draw()

    t, force_kn, pre_kn = load_run()

    # ---------- ① 高保真仿真面板（淡蓝） ----------
    p1x, p1y, p1w, p1h = 0.15, 2.95, 8.35, 2.50
    box(ax, p1x, p1y, p1w, p1h, fc=LBLUE)
    ax.text(p1x + 0.20, 5.14, "① 高保真仿真：全列纵向动力学与制动系统建模",
            fontsize=11.5, color=RED, fontweight="bold", va="center")
    bw, bh_, by = 1.85, 1.50, 3.42
    bxs = [p1x + 0.20 + i * (bw + 0.12) for i in range(4)]
    caps = ["单节车辆纵向动力学", "MT-2 缓冲器特性", "空气制动建立", "49.6 km 线路剖面"]
    pngs = [None,
            os.path.join(PPT_IMAGES, "fig_mt2_hysteresis.png"),
            os.path.join(PPT_IMAGES, "fig_air_brake_build.png"),
            os.path.join(PPT_IMAGES, "fig_profile_49km.png")]
    embeds = []
    for i, bx in enumerate(bxs):
        box(ax, bx, by, bw, bh_)
        ax.text(bx + bw / 2, by + 0.14, caps[i], fontsize=8, color="black",
                fontweight="bold", ha="center", va="center")
        if pngs[i]:
            embeds.append(place_png(fig, ax, pngs[i],
                                    bx + 0.08, by + 0.32, bw - 0.16, bh_ - 0.50))
    # (a) 纵向动力学方程（模型真实方程）
    ax.text(bxs[0] + bw / 2, by + 0.90,
            r"$m_i a_i = F_i^{+} - F_i^{-}$" + "\n" + r"$-\ F_{g,i} - F_{\mathrm{air},i}$",
            fontsize=9, color="black", ha="center", va="center")
    ax.text(p1x + p1w / 2, 3.14, "制动波速、缓冲器特性等关键参数与实测对齐",
            fontsize=9.5, color="black", fontweight="bold", ha="center", va="center")

    # ---------- ② 动作预演面板（淡橙） ----------
    p2x, p2w = 8.65, 4.00
    box(ax, p2x, p1y, p2w, p1h, fc=LORANGE)
    ax.text(p2x + 0.20, 5.14, "② 动作预演：下发前预估车钩力",
            fontsize=11.5, color=RED, fontweight="bold", va="center")
    box(ax, p2x + 0.20, by, p2w - 0.40, bh_)
    ax.text(p2x + p2w / 2, by + 0.14, "预演峰值与实测峰值对比（同一次运行）",
            fontsize=8, color="black", fontweight="bold", ha="center", va="center")
    cx0, cy0 = p2x + 0.62, by + 0.55
    cw, ch = p2w - 1.15, 0.66
    cw_curve = cw * 0.66
    tmax = t[-1]
    fmax = max(force_kn.max(), pre_kn.max())
    ax.plot(cx0 + t / tmax * cw_curve, cy0 + force_kn / fmax * ch,
            color=NAVY, lw=3.2, zorder=3)
    ax.plot(cx0 + t / tmax * cw_curve, cy0 + pre_kn / fmax * ch, color=RED,
            lw=1.0, linestyle=(0, (3, 2)), zorder=4)
    lx0 = cx0 + cw_curve + 0.12
    ax.plot([lx0, lx0 + 0.18], [cy0 + ch * 0.82] * 2, color=NAVY, lw=1.3)
    ax.text(lx0 + 0.23, cy0 + ch * 0.82, "实测", fontsize=6.5,
            color=NAVY, fontweight="bold", va="center")
    ax.plot([lx0, lx0 + 0.18], [cy0 + ch * 0.58] * 2, color=RED, lw=1.2,
            linestyle=(0, (4, 2)))
    ax.text(lx0 + 0.23, cy0 + ch * 0.58, "预演", fontsize=6.5,
            color=RED, fontweight="bold", va="center")
    ax.text(cx0 + cw * 0.5, cy0 - 0.05, "时间 (s)", fontsize=6, color="#404040",
            ha="center", va="top")
    ax.text(cx0 - 0.04, cy0 + ch * 0.5, "力 (kN)", fontsize=6, color="#404040",
            ha="right", va="center", rotation=90)
    ax.text(p2x + p2w / 2, 3.14, "预演与实测相符，超限动作提前拦截",
            fontsize=9.5, color="black", fontweight="bold", ha="center", va="center")

    # ---------- ③ 全程验证与部署面板（浅灰蓝） ----------
    p3y, p3h = 0.15, 2.55
    box(ax, 0.15, p3y, 12.50, p3h, fc=LGRAY)
    ax.text(0.35, 2.50, "③ 全程验证：基线运行、指标评价与部署测试",
            fontsize=11.5, color=RED, fontweight="bold", va="center")
    # 左：仿真验证链（三框）
    chain = [("规则控制与安全层", ""), ("49.6 km 全程剖面运行", ""),
             ("指标评价", "列距、列间速度差、车钩力")]
    cbw, cbh, cy = 1.98, 0.86, 1.28
    cxs = [0.45 + i * (cbw + 0.30) for i in range(3)]
    for i, (tt, sub) in enumerate(chain):
        box(ax, cxs[i], cy, cbw, cbh)
        if sub:
            ax.text(cxs[i] + cbw / 2, cy + cbh - 0.28, tt, fontsize=9,
                    color="black", fontweight="bold", ha="center", va="center")
            ax.text(cxs[i] + cbw / 2, cy + 0.26, sub, fontsize=7,
                    color="black", ha="center", va="center")
        else:
            ax.text(cxs[i] + cbw / 2, cy + cbh / 2, tt, fontsize=9,
                    color="black", fontweight="bold", ha="center", va="center")
        if i < 2:
            xb0, xb1 = cxs[i] + cbw + 0.03, cxs[i] + cbw + 0.27
            mid = cy + cbh / 2
            ax.add_patch(Polygon([(xb0, mid - 0.06), (xb1 - 0.13, mid - 0.06),
                                  (xb1 - 0.13, mid - 0.13), (xb1, mid),
                                  (xb1 - 0.13, mid + 0.13), (xb1 - 0.13, mid + 0.06),
                                  (xb0, mid + 0.06)], fc=NAVY, ec=NAVY, lw=0.5))
            if i == 0:
                ax.text((xb0 + xb1) / 2, cy + cbh + 0.06, "控制指令", fontsize=6.5,
                        color="#404040", ha="center", va="bottom")
    # 左链状态反馈虚线
    ry = cy - 0.26
    ax.plot([cxs[2] + cbw / 2, cxs[0] + cbw / 2], [ry, ry], color=NAVY, lw=1.1,
            linestyle=(0, (5, 3)))
    ax.plot([cxs[0] + cbw / 2, cxs[0] + cbw / 2], [ry, cy - 0.04], color=NAVY,
            lw=1.1, linestyle=(0, (5, 3)))
    ax.plot([cxs[2] + cbw / 2, cxs[2] + cbw / 2], [ry, cy - 0.04], color=NAVY,
            lw=1.1, linestyle=(0, (5, 3)))
    ax.annotate("", xy=(cxs[0] + cbw / 2, cy - 0.04),
                xytext=(cxs[0] + cbw / 2, ry),
                arrowprops=dict(arrowstyle="-|>", color=NAVY, lw=1.1))
    ax.text((cxs[0] + cxs[2] + cbw) / 2, ry - 0.02, "状态反馈", fontsize=6.5,
            color="#404040", ha="center", va="top")

    # 右：部署验证闭环（平台管理算法并对比分析；小车按指令运行，
    # 传感器回传车钩力；交大仿真平台为算法的第二仿真平台，实车数据搭建）
    fx, fy, fw, fh = 7.90, 0.72, 4.00, 1.56
    box(ax, fx, fy, fw, fh, ec=NAVY, fc="none", lw=1.4, rounding=0.05)
    ax.text(fx + 0.15, fy + fh - 0.20, "部署验证闭环", fontsize=8.5,
            color="black", fontweight="bold", ha="left", va="center")
    px_, py_, pw2, ph2 = 8.75, 1.66, 2.30, 0.44
    box(ax, px_, py_, pw2, ph2)
    ax.text(px_ + pw2 / 2, py_ + ph2 - 0.15, "验证平台", fontsize=8.5,
            color="black", fontweight="bold", ha="center", va="center")
    ax.text(px_ + pw2 / 2, py_ + 0.13, "算法管理与数据对比分析", fontsize=6.5,
            color="black", ha="center", va="center")
    vx, vy, vw, vh = 8.02, 0.84, 1.72, 0.50
    box(ax, vx, vy, vw, vh)
    ax.text(vx + vw / 2, vy + vh - 0.15, "试验小车", fontsize=8.5,
            color="black", fontweight="bold", ha="center", va="center")
    ax.text(vx + vw / 2, vy + 0.13, "按指令运行", fontsize=6.5,
            color="black", ha="center", va="center")
    jx, jy, jw, jh = 10.08, 0.84, 1.72, 0.50
    box(ax, jx, jy, jw, jh)
    ax.text(jx + jw / 2, jy + jh - 0.15, "交大仿真平台", fontsize=8.5,
            color="black", fontweight="bold", ha="center", va="center")
    ax.text(jx + jw / 2, jy + 0.13, "第二仿真平台，实车数据搭建", fontsize=6,
            color="black", ha="center", va="center")
    # 平台→小车（算法下发，实线）＋小车→平台（车钩力回传，虚线）＋平台→交大
    ax.annotate("", xy=(8.85, vy + vh), xytext=(8.85, py_),
                arrowprops=dict(arrowstyle="-|>", color=NAVY, lw=1.1))
    ax.text(8.77, (vy + vh + py_) / 2, "算法下发", fontsize=6, color="#404040",
            ha="right", va="center")
    ax.annotate("", xy=(9.60, py_), xytext=(9.60, vy + vh),
                arrowprops=dict(arrowstyle="-|>", color=NAVY, lw=1.1,
                                linestyle=(0, (4, 2))))
    ax.text(9.68, (vy + vh + py_) / 2, "车钩力数据回传", fontsize=6,
            color="#404040", ha="left", va="center")
    ax.annotate("", xy=(10.94, jy + jh), xytext=(10.94, py_),
                arrowprops=dict(arrowstyle="-|>", color=NAVY, lw=1.1))
    ax.text(11.02, (jy + jh + py_) / 2, "算法部署", fontsize=6,
            color="#404040", ha="left", va="center")
    ax.text(0.15 + 12.50 / 2, 0.42,
            "规则控制基线完成全程运行，预演把超限动作拦截在决策下发之前",
            fontsize=9.5, color="black", fontweight="bold", ha="center", va="center")

    out = os.path.join(OUT, "fig_v4_verify.png")
    fig.savefig(out, dpi=300, bbox_inches="tight", facecolor="white")
    for e in embeds:
        plt.close(e.figure) if e.figure is not fig else None
    plt.close(fig)
    print("saved:", out)


if __name__ == "__main__":
    main()
