# -*- coding: utf-8 -*-
"""P10 右栏：MARL 机车级决策框架图（仿学姐总体框架图风格：编号色块 + 白底小框 + 实心箭头 + 绿条评价）"""
import os
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import FancyBboxPatch, FancyArrowPatch, Polygon
plt.rcParams["font.family"] = "Microsoft YaHei"
plt.rcParams["axes.unicode_minus"] = False

NAVY = "#2F4A7A"; RED = "#C00000"; GREEN = "#2E7D32"
LBLUE = "#EAF1FB"; LORANGE = "#FDF2E2"; LGRAY = "#F7F9FC"; LGREEN = "#E9F4E9"
OB = "#B8862A"  # 橙块描边

OUT = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                   "ppt_talk", "midterm_20261018", "images", "示意底稿")


def panel(ax, x, y, w, h, fc, ec, lw=1.4):
    ax.add_patch(FancyBboxPatch((x, y), w, h, boxstyle="round,pad=0.004,rounding_size=0.03",
                                fc=fc, ec=ec, lw=lw, mutation_aspect=0.55))


def wbox(ax, x, y, w, h, lines, fs=9.5):
    """白底小框，lines: [ (text, color, bold), ... ] 居中多行"""
    ax.add_patch(FancyBboxPatch((x, y), w, h, boxstyle="round,pad=0.004,rounding_size=0.02",
                                fc="white", ec=NAVY, lw=1.1, mutation_aspect=0.55))
    n = len(lines)
    for i, (t, c, b) in enumerate(lines):
        ax.text(x + w / 2, y + h * (n - i - 0.5) / n, t, fontsize=fs, color=c,
                fontweight="bold" if b else "normal", ha="center", va="center")


def arr_r(ax, x0, x1, yc, w=0.13, head=0.14):
    """藏青实心块箭头（向右）"""
    body = w * 0.42
    ax.add_patch(Polygon([(x0, yc - body / 2), (x1 - head, yc - body / 2),
                          (x1 - head, yc - w / 2), (x1, yc),
                          (x1 - head, yc + w / 2), (x1 - head, yc + body / 2),
                          (x0, yc + body / 2)], fc=NAVY, ec=NAVY, lw=0.5))


def arr_d(ax, xc, y0, y1, w=0.16, head=0.16):
    body = w * 0.42
    ax.add_patch(Polygon([(xc - body / 2, y0), (xc - body / 2, y1 - head),
                          (xc - w / 2, y1 - head), (xc, y1),
                          (xc + w / 2, y1 - head), (xc + body / 2, y1 - head),
                          (xc + body / 2, y0)], fc=NAVY, ec=NAVY, lw=0.5))


def main():
    fig, ax = plt.subplots(figsize=(6.9, 7.4))
    ax.set_xlim(0, 10); ax.set_ylim(1.95, 10.95); ax.axis("off")
    X, W = 0.25, 8.6   # 面板统一左右边界（右侧留 0.9 给反馈虚线）

    # ---------- ① 编队上下文观测（淡蓝） 8.75..10.80 ----------
    y1, h1 = 8.75, 2.05
    panel(ax, X, y1, W, h1, LBLUE, NAVY)
    ax.text(X + 0.25, y1 + h1 - 0.28, "①", fontsize=13, color=RED, fontweight="bold", va="center")
    ax.text(X + 0.62, y1 + h1 - 0.28, "编队上下文观测", fontsize=12.5, color="black",
            fontweight="bold", va="center")
    bw, bh, by = 2.42, 0.78, y1 + 0.45
    bxs = [X + 0.22, X + 0.22 + 2.72, X + 0.22 + 5.44]
    wbox(ax, bxs[0], by, bw, bh, [("本列状态", "black", True),
                                  ("速度误差·限速裕量", "black", False),
                                  ("车钩力·制动状态", "black", False)], fs=9)
    wbox(ax, bxs[1], by, bw, bh, [("邻列相对量", "black", True),
                                  ("列距·相对速度", "black", False)], fs=9)
    wbox(ax, bxs[2], by, bw, bh, [("线路与列尾", "black", True),
                                  ("前方坡度·坡长", "black", False),
                                  ("列尾充风状态", RED, False)], fs=9)
    for i in range(2):
        arr_r(ax, bxs[i] + bw + 0.04, bxs[i] + bw + 0.26, by + bh / 2, w=0.11, head=0.11)
    ax.text(X + W / 2, y1 + 0.17, "实时感知本列、邻列与线路状态，为协同决策提供信息",
            fontsize=10, color="black", fontweight="bold", ha="center")
    arr_d(ax, X + W / 2, y1 - 0.02, y1 - 0.30)

    # ---------- ② 机车级智能体决策（淡橙） 6.10..8.40 ----------
    y2, h2 = 6.10, 2.30
    panel(ax, X, y2, W, h2, LORANGE, OB)
    ax.text(X + 0.25, y2 + h2 - 0.28, "②", fontsize=13, color=RED, fontweight="bold", va="center")
    ax.text(X + 0.62, y2 + h2 - 0.28, "机车级智能体决策（MAPPO）", fontsize=12.5, color="black",
            fontweight="bold", va="center")
    cw, ch, cy = 3.85, 0.92, y2 + 0.80
    wbox(ax, X + 0.30, cy, cw, ch, [("集中训练", "black", True),
                                    ("共享 Critic 评价三机车联合动作", "black", False)], fs=9.5)
    wbox(ax, X + W - 0.30 - cw, cy, cw, ch, [("分散执行", "black", True),
                                             ("输出电制动连续调节与", "black", False),
                                             ("空气制动离散档位", "black", False)], fs=9.5)
    arr_r(ax, X + 0.30 + cw + 0.05, X + W - 0.30 - cw - 0.05, cy + ch / 2, w=0.13, head=0.14)
    ax.text(X + W / 2, y2 + 0.16, "三台机车各自决策，编队协同目标写入奖励函数",
            fontsize=10, color="black", fontweight="bold", ha="center")
    arr_d(ax, X + W / 2, y2 - 0.02, y2 - 0.25)

    # ---------- ③ 底层执行与安全层（浅灰蓝） 3.55..5.85 ----------
    y3, h3 = 3.55, 2.30
    panel(ax, X, y3, W, h3, LGRAY, NAVY)
    ax.text(X + 0.25, y3 + h3 - 0.28, "③", fontsize=13, color=RED, fontweight="bold", va="center")
    ax.text(X + 0.62, y3 + h3 - 0.28, "底层执行与安全层", fontsize=12.5, color="black",
            fontweight="bold", va="center")
    rw, rh, ry = 3.42, 0.86, y3 + 0.86
    wbox(ax, X + 0.30, ry, rw, rh, [("规则循环制动执行", "black", True),
                                    ("空气制动波沿列传播", "black", False)], fs=9.5)
    wbox(ax, X + W - 0.30 - rw, ry, rw, rh, [("车钩力安全层校验", RED, True),
                                             ("≤1000 kN（硬顶 2250 kN）", "black", False)], fs=9.5)
    arr_r(ax, X + 0.30 + rw + 0.05, X + W - 0.30 - rw - 0.05, ry + rh / 2, w=0.13, head=0.14)
    fb = FancyArrowPatch((X + W - 0.30 - 0.4, ry - 0.20), (X + 0.30 + 0.4, ry - 0.20),
                         arrowstyle="-|>", mutation_scale=11,
                         color=NAVY, lw=1.1, linestyle=(0, (4, 2)))
    ax.add_patch(fb)
    ax.text(X + W / 2, y3 + 0.14, "车钩力红线由规则层保证，不依赖学习策略",
            fontsize=10, color="black", fontweight="bold", ha="center")
    arr_d(ax, X + W / 2, y3 - 0.02, y3 - 0.18)

    # ---------- 底部绿条：训练与评价 2.00..3.33 ----------
    y4, h4 = 2.00, 1.33
    panel(ax, X, y4, W, h4, LGREEN, LGREEN)
    ax.text(X + W / 2, y4 + h4 - 0.24, "训练与评价", fontsize=10.5, color=RED,
            fontweight="bold", ha="center")
    ax.text(X + W / 2, y4 + 0.42, "课程训练（短窗口）→ 49.6 km 全程剖面评估\n"
            "指标：列距误差 · 列间速度差 · 车钩力峰值 · 防护触发次数",
            fontsize=10, color="black", fontweight="bold", ha="center", va="center",
            linespacing=1.6)

    # 右侧绿虚线闭环：评价 → 观测（环境反馈）
    lx = X + W + 0.42
    fb2 = FancyArrowPatch((X + W + 0.05, y4 + h4 / 2), (lx, y4 + h4 / 2),
                          arrowstyle="-", color=GREEN, lw=1.4, linestyle=(0, (5, 3)))
    ax.add_patch(fb2)
    fb3 = FancyArrowPatch((lx, y4 + h4 / 2), (lx, y1 + h1 / 2),
                          arrowstyle="-", color=GREEN, lw=1.4, linestyle=(0, (5, 3)))
    ax.add_patch(fb3)
    fb4 = FancyArrowPatch((lx, y1 + h1 / 2), (X + W + 0.02, y1 + h1 / 2),
                          arrowstyle="-|>", mutation_scale=12, color=GREEN,
                          lw=1.4, linestyle=(0, (5, 3)))
    ax.add_patch(fb4)
    ax.text(lx + 0.16, (y1 + y4) / 2 + h1 / 2 - 0.5, "环境状态反馈", fontsize=9,
            color=GREEN, rotation=90, va="center")

    fig.savefig(os.path.join(OUT, "fig_v4_marl.png"), dpi=300,
                bbox_inches="tight", facecolor="white")
    plt.close(fig)
    print("saved fig_v4_marl.png")


if __name__ == "__main__":
    main()
