# -*- coding: utf-8 -*-
"""MT-2 四分支迟滞环（中期答辩 页 6，PPT 版重生成）。

依据用户要求（2026-10-19）：只保留基本图线与图例，不加黑色箭头与文字标注；
中文用 Microsoft YaHei 重画（旧图在 WSL 生成，标题中文回退乱码）。
数据口径与 src/evaluation/plot_physical_curves.py::fig_coupler_hysteresis
完全一致：CouplerParams 准静态扫掠（确定性模型特征，非时域仿真），
MT-2 统一（ADR-011），容嘉欣2025 fl/fu 查表 + 速度法选支。
图 → 本目录（PPT 策展，允许覆盖）。
"""
import sys
from pathlib import Path

import numpy as np
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt

plt.rcParams["font.sans-serif"] = ["Microsoft YaHei"]
plt.rcParams["axes.unicode_minus"] = False

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))

from src.train_dynamics.coupler import coupler_force
from src.train_dynamics.params import CouplerParams

OUT = Path(__file__).resolve().parent / "fig_mt2_hysteresis.png"

p = CouplerParams()
kw = dict(
    stiffness=p.stiffness, damping=p.damping, free_length=p.free_length_m,
    coupler_gap=p.coupler_gap_m, max_impulse=p.max_impulse_n,
    preload_n=p.preload_n, friction_n=p.friction_n,
    friction_v_eps=p.friction_v_eps, stroke_m=p.stroke_m,
    rigid_stiffness_nm=p.rigid_stiffness_nm,
    unload_stiffness_ratio=p.unload_stiffness_ratio,
    friction_static_n=p.friction_static_n, friction_v_er=p.friction_v_er,
)
amp = float(p.stroke_m)  # 83 mm，扫到缓冲器最大行程


def F(e, dv_sign):
    return coupler_force(0.0, 0.0, e - p.free_length_m, -dv_sign, **kw)


e_c = np.linspace(0.0, amp, 400)            # 压缩：加载 dv<0 / 卸载 dv>0
load_c = np.array([F(x, -1.0) for x in e_c])
unload_c = np.array([F(x, 1.0) for x in e_c[::-1]])
e_t = np.linspace(0.0, -amp, 400)           # 拉伸：加载 dv>0 / 卸载 dv<0
load_t = np.array([F(x, 1.0) for x in e_t])
unload_t = np.array([F(x, -1.0) for x in e_t[::-1]])

fig, ax = plt.subplots(figsize=(8, 6.2), dpi=200)
ax.plot(e_c * 1000, load_c / 1e3, color="#1f77b4", lw=2.0, label="加载（压缩）")
ax.plot(e_c[::-1] * 1000, unload_c / 1e3, color="#2ca02c", lw=2.0,
        label="卸载（压缩恢复）")
ax.plot(e_t * 1000, load_t / 1e3, color="#d62728", lw=2.0, label="加载（拉伸）")
ax.plot(e_t[::-1] * 1000, unload_t / 1e3, color="#ff7f0e", lw=2.0,
        label="卸载（拉伸恢复）")
ax.axhline(0, color="k", lw=0.6)
ax.axvline(0, color="k", lw=0.6)
ax.set_xlabel("缓冲器位移 (mm)", fontsize=12)
ax.set_ylabel("车钩力 (kN)", fontsize=12)
ax.set_title("MT-2 车钩缓冲器加载-卸载迟滞环", fontsize=14)
ax.legend(fontsize=11, loc="upper left")
ax.grid(alpha=0.3)
ax.set_xlim(-105, 100)
ax.set_ylim(-2400, 2650)
fig.tight_layout()
fig.savefig(OUT, bbox_inches="tight", pad_inches=0.05)
print("saved:", OUT)
