# -*- coding: utf-8 -*-
"""图2/图4风格结果图：速度跟踪、速度/间距误差、车钩力"""
import os
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from scenarios import target_speed

plt.rcParams["font.sans-serif"] = ["SimHei", "Microsoft YaHei"]
plt.rcParams["axes.unicode_minus"] = False

CASES = ["gentle_coupler_on", "gentle_coupler_off",
         "downhill_coupler_on", "downhill_coupler_off"]
OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "outputs")


def load(tag):
    d = np.genfromtxt(os.path.join(OUT, f"sim_{tag}.csv"),
                      delimiter=",", names=True)
    return d


def fig_case(tag):
    d = load(tag)
    sc = tag.split("_")[0]
    t = d["t"]
    fig, axs = plt.subplots(3, 1, figsize=(10, 9), sharex=True)
    # (a) 各机车速度
    ax = axs[0]
    tv = np.linspace(t[0], t[-1], 2000)
    ax.plot(tv, [target_speed(x, sc) for x in tv], "k--", lw=1.2,
            label="目标速度曲线")
    for i, c in enumerate(["C0", "C1", "C2"]):
        ax.plot(t, d[f"v{i}0"], color=c, lw=1.0, label=f"机车{i+1}")
    ax.set_ylabel("速度 (m/s)")
    ax.set_title(f"{'平缓坡道' if sc=='gentle' else '长大下坡'}场景 "
                 f"（车钩力{'开启' if tag.endswith('on') else '关闭'}）")
    ax.legend(loc="lower left", ncol=4, fontsize=8)
    ax.grid(alpha=0.3)
    # (b) 速度误差
    ax = axs[1]
    for i, c in enumerate(["C0", "C1", "C2"]):
        if i == 0:
            vr = np.array([target_speed(x, sc) for x in t])
            err = np.abs(vr - d["v00"])
        else:
            err = np.abs(d[f"v{i-1}0"] - d[f"v{i}0"])
        ax.plot(t, err, color=c, lw=0.9, label=f"机车{i+1}")
    ax.set_ylabel("速度误差 (m/s)")
    ax.legend(loc="upper right", ncol=3, fontsize=8)
    ax.grid(alpha=0.3)
    # (c) 车钩力（每列车的机车-货车组1 钩）
    ax = axs[2]
    for i, c in enumerate(["C0", "C1", "C2"]):
        ax.plot(t, d[f"fc{i}0"], color=c, lw=0.8, label=f"列车{i+1} 车钩1")
    ax.axhline(1500, color="r", ls="--", lw=1, label="安全限值 ±1500 kN")
    ax.axhline(-1500, color="r", ls="--", lw=1)
    ax.set_ylabel("车钩力 (kN)")
    ax.set_xlabel("时间 (s)")
    ax.legend(loc="upper right", ncol=4, fontsize=8)
    ax.grid(alpha=0.3)
    fig.tight_layout()
    p = os.path.join(OUT, f"fig_{tag}.png")
    fig.savefig(p, dpi=150)
    plt.close(fig)
    return p


if __name__ == "__main__":
    for tag in CASES:
        f = os.path.join(OUT, f"sim_{tag}.csv")
        if os.path.exists(f):
            print("saved:", fig_case(tag))
        else:
            print("missing:", f)
