# -*- coding: utf-8 -*-
"""P14 平台建设：机制图（竖版，界面平台居上，小车与交大平台并列其下，无序号）。

结构（用户 2026-11-08 确认）：
  界面平台：统一下发算法、分析对比；小车按指令运行回传车钩力数据；
  交大平台（第二仿真平台）与小车并列，向上提供近实车数据。
输出: ppt_talk/midterm_20261018/images/示意底稿/fig_v4_platform_structure.png
"""
import os
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import FancyBboxPatch, Polygon, Rectangle

plt.rcParams["font.family"] = "Microsoft YaHei"
plt.rcParams["axes.unicode_minus"] = False

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PPT = os.path.join(BASE, "ppt_talk", "midterm_20261018")
OUT = os.path.join(PPT, "images", "示意底稿")

NAVY = "#2F4A7A"
RED = "#C00000"
LGREEN = "#E9F4E9"

W, H = 6.5, 7.2
fig, ax = plt.subplots(figsize=(W, H))
ax.set_xlim(0, W)
ax.set_ylim(0, H)
ax.axis("off")
fig.canvas.draw()

GAP = 0.10   # 箭头与面板的统一间隙


def panel(x, y, w, h, title):
    ax.add_patch(FancyBboxPatch((x, y), w, h,
                 boxstyle="round,pad=0,rounding_size=0.10",
                 facecolor="white", edgecolor=NAVY, linewidth=1.8))
    ax.add_patch(FancyBboxPatch((x, y + h - 0.50), w, 0.50,
                 boxstyle="round,pad=0,rounding_size=0.10",
                 facecolor=NAVY, edgecolor=NAVY, linewidth=1.8))
    ax.add_patch(Rectangle((x, y + h - 0.50), w, 0.25,
                facecolor=NAVY, edgecolor="none"))
    ax.text(x + w / 2, y + h - 0.25, title, fontsize=11.5, color="white",
            fontweight="bold", ha="center", va="center")


def wbox(x, y, w, h, text, fs=10, color="black"):
    ax.add_patch(FancyBboxPatch((x, y), w, h,
                 boxstyle="round,pad=0,rounding_size=0.06",
                 facecolor="white", edgecolor=NAVY, linewidth=1.3))
    ax.text(x + w / 2, y + h / 2, text, fontsize=fs, color=color,
            fontweight="bold", ha="center", va="center")


def arr_v(x, y0, y1, w=0.24, head=0.16, color=NAVY):
    """竖直箭头：y0 起点，y1 箭尖。"""
    up = y1 > y0
    yb = y1 - head if up else y1 + head
    pts = [(x - w / 2, y0), (x + w / 2, y0), (x + w / 2, yb),
           (x + w * 0.8, yb), (x, y1), (x - w * 0.8, yb), (x - w / 2, yb)]
    ax.add_patch(Polygon(pts, closed=True, facecolor=color, edgecolor=color))


# ---- 顶部：界面平台 ----
panel(0.35, 5.45, 5.80, 1.55, "界面平台（数字孪生平台）")
wbox(0.53, 6.00, 5.44, 0.44, "算法管理　仿真运行　数据记录　分析服务", fs=10)
wbox(0.53, 5.52, 5.44, 0.44, "统一下发算法　分析对比", fs=10, color=RED)

# ---- 中部并列：试验小车 ｜ 大连交大仿真平台 ----
panel(0.35, 1.55, 2.80, 2.85, "试验小车（欠驱动系统）")
wbox(0.53, 3.20, 2.44, 0.48, "按平台指令运行", fs=9.5)
wbox(0.53, 2.57, 2.44, 0.48, "无线通信与状态传感", fs=9.5)
wbox(0.53, 1.94, 2.44, 0.48, "传感器回传车钩力数据", fs=9.5, color=RED)

panel(3.40, 1.55, 2.80, 2.85, "列车仿真平台")
wbox(3.58, 3.20, 2.44, 0.48, "第二仿真平台", fs=9.5)
wbox(3.58, 2.57, 2.44, 0.48, "实车数据搭建", fs=9.5)
wbox(3.58, 1.94, 2.44, 0.48, "运行特性接近实车", fs=9.5)

# ---- 箭头（区 4.40–5.45，两端各留 GAP）----
# ② → ③ 算法下发（向下）
arr_v(1.05, 5.45 - GAP, 1.55 + 2.85 + GAP)
ax.text(0.85, 4.93, "算法下发", fontsize=9.5, color=NAVY,
        fontweight="bold", ha="right", va="center")
# ③ → ② 数据回传（向上，红）
arr_v(2.45, 1.55 + 2.85 + GAP, 5.45 - GAP, color=RED)
ax.text(2.65, 4.93, "数据回传", fontsize=9.5, color=RED,
        fontweight="bold", ha="left", va="center")
# ① → ② 数据回传（向上）
arr_v(4.80, 1.55 + 2.85 + GAP, 5.45 - GAP, color=RED)
ax.text(5.02, 4.93, "数据回传", fontsize=9.5, color=RED,
        fontweight="bold", ha="left", va="center")

# ---- 底部绿条 ----
gy, gh = 0.25, 0.70
ax.add_patch(FancyBboxPatch((0.35, gy), 5.80, gh,
             boxstyle="round,pad=0,rounding_size=0.08",
             facecolor=LGREEN, edgecolor="#2E7D32", linewidth=1.4))
ax.text(0.35 + 5.80 / 2, gy + gh / 2, "算法—仿真—实物 完整验证链",
        fontsize=11, color="black", fontweight="bold", ha="center", va="center")

path = os.path.join(OUT, "fig_v4_platform_structure.png")
fig.savefig(path, dpi=300, bbox_inches="tight", facecolor="white")
print("saved:", path)
