# -*- coding: utf-8 -*-
"""三列虚拟耦合编组·长大下坡示意图（中期答辩 页 3 研究对象）。

布局：同一条逐段下降的轨道上三列首尾相接——虚拟耦合本义即同轨追踪编组。
每列 = 1 台 HXD3B 机车（实心黑、受电弓）+ C80 货车（白框，前 8 节 +
省略点 + 后 3 节），大括号标"108 节 C80 货车"；列间双向虚线箭头 =
虚拟耦合；轨道逐段下降、末端下坡箭头 = 长大下坡运行方向。
黑白，文字仅 HXD3B / 108 节 C80 货车 / 虚拟耦合 / 长大下坡。
"""
import math

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import Rectangle

plt.rcParams["font.sans-serif"] = ["Microsoft YaHei"]
plt.rcParams["axes.unicode_minus"] = False

WAGON_W = 1.0      # 货车宽
WAGON_H = 1.0      # 货车高
LOCO_W = 1.7       # 机车宽
LOCO_H = 1.35      # 机车高
PITCH = 1.12       # 节距
N_HEAD = 8         # 省略号前货车节数
N_TAIL = 3         # 省略号后货车节数
GAP = 5.5          # 列间空档（虚拟耦合箭头 + 下坡轨道段）
STEP_Y = 3.4       # 每列下降量
TRACK_L = 1.2      # 轨道向列车前方延伸量
OUT = r"d:\Code\MultiAgent\traffic_rl_project\ppt_talk\midterm_20261018\images\fig_formation_schematic.png"

fig, ax = plt.subplots(figsize=(12.5, 2.5), dpi=200)

rows = []  # (x0, y, x_tail) 供轨道与列间箭头使用
x0 = 0.0
for row in range(3):
    y = -row * STEP_Y
    # 机车：实心黑 + 受电弓 + 型号
    ax.add_patch(Rectangle((x0, y), LOCO_W, LOCO_H, facecolor="black", edgecolor="black"))
    ax.plot(
        [x0 + 0.45 * LOCO_W, x0 + 0.75 * LOCO_W],
        [y + LOCO_H, y + LOCO_H + 0.35],
        color="black", lw=1.6,
    )
    ax.text(x0 + LOCO_W / 2, y + 2.15, "HXD3B", ha="center", va="center",
            fontsize=12, color="black")
    # 货车：前 8 节 + 省略点 + 后 3 节
    x = x0 + LOCO_W + 0.12
    xb0 = x
    for _ in range(N_HEAD):
        ax.add_patch(Rectangle((x, y), WAGON_W, WAGON_H, facecolor="white",
                               edgecolor="black", lw=1.1))
        x += PITCH
    x_dots = x + 0.35
    for k in range(3):
        ax.plot([x_dots + k * 0.6], [y + WAGON_H / 2], marker="o",
                markersize=4, color="black")
    x += 2.0
    for _ in range(N_TAIL):
        ax.add_patch(Rectangle((x, y), WAGON_W, WAGON_H, facecolor="white",
                               edgecolor="black", lw=1.1))
        x += PITCH
    xb1 = x - 0.12
    x_tail = x
    # 大括号（开口朝下、中尖朝上）+ 节数标注
    yb = y + 1.9
    mid = (xb0 + xb1) / 2
    ax.plot([xb0, xb0], [yb, yb - 0.28], color="black", lw=1.3)
    ax.plot([xb1, xb1], [yb, yb - 0.28], color="black", lw=1.3)
    ax.plot([xb0, mid - 0.5, mid, mid + 0.5, xb1],
            [yb, yb, yb + 0.22, yb, yb], color="black", lw=1.3)
    ax.text(mid, yb + 0.62, "108 节 C80 货车", ha="center", va="center",
            fontsize=12.5, color="black")
    rows.append((x0, y, x_tail))
    x0 = x_tail + GAP

# 轨道：每列水平段 + 列间下坡斜段；末端延续下坡并加方向箭头
for i, (rx0, ry, rx_tail) in enumerate(rows):
    ax.plot([rx0 - TRACK_L, rx_tail + 0.8], [ry - 0.22] * 2, color="black", lw=1.2)
    ax.plot([rx0 - TRACK_L, rx_tail + 0.8], [ry - 0.40] * 2, color="black", lw=1.2)
    if i < 2:
        xn, yn = rows[i + 1][0], rows[i + 1][1]
        ax.plot([rx_tail + 0.8, xn - TRACK_L], [ry - 0.31, yn - 0.31],
                color="black", lw=1.2)
    else:
        xa, ya = rx_tail + 0.8, ry - 0.31
        xb, yb2 = xa + 2.6, ya - 2.0
        ax.annotate("", xy=(xb, yb2), xytext=(xa, ya),
                    arrowprops=dict(arrowstyle="-|>", color="black", lw=1.8))
        ang = math.degrees(math.atan2(yb2 - ya, xb - xa))
        dx, dy = xb - xa, yb2 - ya
        L = math.hypot(dx, dy)
        # 文字与箭头平行，置于箭头左下方（法线偏移 1.15，靠箭头上段）
        nx, ny = dy / L, -dx / L
        tx = xa + 0.42 * dx + nx * 1.15
        ty = ya + 0.42 * dy + ny * 1.15
        ax.text(tx, ty, "长大下坡", rotation=ang, ha="center", va="center",
                fontsize=11.5, color="black")

# 列间虚拟耦合：双向虚线箭头（本列尾 → 下一列头），首空档加标注
for i in range(2):
    _, ry, rx_tail = rows[i]
    xn, yn = rows[i + 1][0], rows[i + 1][1]
    p1 = (rx_tail + 0.15, ry + 0.55)
    p2 = (xn - 0.15, yn + 0.55)
    ax.annotate("", xy=p2, xytext=p1,
                arrowprops=dict(arrowstyle="<->", linestyle="--",
                                color="black", lw=1.6))
    if i == 0:
        # 水平标注置于首空档上方（第一列大括号右侧、箭头上方），避开下一列 HXD3B
        ax.text(p1[0] + 2.4, 1.0, "虚拟耦合", ha="center", va="center",
                fontsize=11.5, color="black")

x_last = rows[-1][2]
ax.set_xlim(-1.6, x_last + 5.2)
ax.set_ylim(-2 * STEP_Y - 0.31 - 2.0 - 1.8, 3.2)
ax.set_aspect("equal")
ax.axis("off")

fig.savefig(OUT, bbox_inches="tight", pad_inches=0.05)
print("saved:", OUT)
