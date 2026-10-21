# -*- coding: utf-8 -*-
"""文献调研统计柱状图（中期答辩 页 5 进展① 文献调研）。

口径：页 5 文案"三个方向（重载列车运行控制 / 列车纵向动力学 / 多智能体强化学习）
共 50 余篇文献"的分主题展示。四主题计数为建议分布，经用户确认（2026-10-19，
AskUserQuestion 拍板）；无逐篇档案清单，一篇文献可属多主题，故总和 57 > 50。
参考依据：DIAGNOSTICS_2026-10「文献调研-2026-10-12」MPC×空气制动单次检索约 22 篇。

  MARL       = 15（多智能体强化学习为大热方向，含无人机编队 / VCTS / 车队共识等）
  MPC        = 20（MPC×空气制动单次调研即 ~22 篇，取 20）
  车钩力建模 = 10（纵向动力学 / 车钩物理方向）
  多列编组   = 12（虚拟编组 / 群组协同方向）

数字如需调整：改 counts 一行重跑即可；口径改动须与页 5 文案同步。
"""
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.ticker import MaxNLocator

plt.rcParams["font.sans-serif"] = ["Microsoft YaHei"]
plt.rcParams["axes.unicode_minus"] = False

topics = ["MARL", "MPC", "车钩力建模", "多列编组"]
counts = [15, 20, 10, 12]

fig, ax = plt.subplots(figsize=(7.0, 4.2), dpi=200)
ax.bar(topics, counts, width=0.52, color="#4C72B0", edgecolor="white")

ax.set_ylabel("文献篇数", fontsize=14)
ax.set_ylim(0, 22)
ax.yaxis.set_major_locator(MaxNLocator(integer=True))
ax.tick_params(axis="x", labelsize=14)
ax.tick_params(axis="y", labelsize=12)
ax.spines["top"].set_visible(False)
ax.spines["right"].set_visible(False)

fig.tight_layout()
fig.savefig(
    r"d:\Code\MultiAgent\traffic_rl_project\ppt_talk\midterm_20261018\images\fig_lit_survey.png",
    bbox_inches="tight",
)
print("saved: fig_lit_survey.png")
