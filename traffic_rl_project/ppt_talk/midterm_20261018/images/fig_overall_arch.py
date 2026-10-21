# -*- coding: utf-8 -*-
"""页 7 整体架构框图（中期答辩）：决策层 → 规则层 → 物理层，反馈闭环。

简约版（负责人拍板：框图只保留六要素——状态空间 / 动作 / 输出 / 规则层 / 物理层 / 反馈；
细节由页面文案承载，不上框图）。

用法：D:/Anaconda/python.exe fig_overall_arch.py
"""
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import FancyArrowPatch, FancyBboxPatch

plt.rcParams["font.sans-serif"] = ["Microsoft YaHei"]
plt.rcParams["axes.unicode_minus"] = False

OUT = Path(__file__).resolve().parent / "fig_overall_arch.png"

BLUE = "#2b5d8a"


def _box(ax, x, y, w, h, text, fs=14.5):
    ax.add_patch(FancyBboxPatch((x, y), w, h,
                                boxstyle="round,pad=0.02,rounding_size=0.06",
                                fc="#eef4fb", ec=BLUE, lw=1.6))
    ax.text(x + w / 2, y + h / 2, text, ha="center", va="center", fontsize=fs,
            color="#1a1a1a", linespacing=1.5)


def _arrow(ax, p1, p2, color="#444444", lw=1.9):
    ax.add_patch(FancyArrowPatch(p1, p2, arrowstyle="-|>", mutation_scale=19,
                                 lw=lw, color=color, shrinkA=2, shrinkB=2))


fig, ax = plt.subplots(figsize=(10.0, 7.2), dpi=200)
ax.set_xlim(-0.3, 10.6)
ax.set_ylim(1.6, 10.0)
ax.axis("off")

BX, BW = 1.75, 7.7

# 三层（简约：层名 + 一句身份）
_box(ax, BX, 7.95, BW, 1.45, "决策层：多智能体强化学习（MAPPO）")
_box(ax, BX, 5.25, BW, 1.45, "规则层：规则循环制动 · 列车自动防护（ATP）")
_box(ax, BX, 2.55, BW, 1.45, "物理层：列车纵向动力学（三列编组仿真）")

# 向下：动作 / 输出
_arrow(ax, (5.6, 7.95), (5.6, 6.70))
ax.text(5.92, 7.32, "动作", ha="left", va="center", fontsize=14, color="#333333")
_arrow(ax, (5.6, 5.25), (5.6, 4.00))
ax.text(5.92, 4.62, "输出", ha="left", va="center", fontsize=14, color="#333333")

# 向上反馈：状态空间（闭环）
_arrow(ax, (1.05, 3.28), (1.05, 8.68), color=BLUE, lw=2.0)
ax.text(0.42, 5.98, "反馈（状态空间）", rotation=90, ha="center", va="center",
        fontsize=13, color=BLUE)

fig.tight_layout()
fig.savefig(OUT, dpi=200, bbox_inches="tight")
print("saved:", OUT)
