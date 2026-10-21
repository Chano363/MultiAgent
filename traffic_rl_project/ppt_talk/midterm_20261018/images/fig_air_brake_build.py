# -*- coding: utf-8 -*-
"""页 6 空气制动机制图（中期答辩）：制动波传播 + 整列制动力建立 + 缓解。

场景（复刻 src/evaluation/plot_physical_curves.py::run_brake_release，换 PPT 编组口径）：
    平坡、初速 70 km/h、1 台 HXD3B + 108 节 C80（10kt_1plus108，约 10988 t），
    单机车 = 单一波源，制动波从头向尾传播（与上幻灯文案"向尾车传播"一致）。
    SERVICE 常用制动（throttle=-0.5）35 s → 缓解（throttle=0）50 s，dt=0.1。
    不设 sync_loco_brake / eot（1+1 双向波专用，1+0 必须单向）。

数据/绘图分离（生图规范）：
    原始数据 → outputs/sim_validation/phys_validation/brake_build_1plus0_108_<时间戳>/
               （scene_air_brake.npz + run_meta.json，不覆盖）
    图       → images/fig_air_brake_build.png（PPT 策展，允许覆盖）

用法：
    Windows: D:/Anaconda/python.exe fig_air_brake_build.py             # 无归档则仿真+画图
    Windows: D:/Anaconda/python.exe fig_air_brake_build.py --plot-only # 只用最新归档重画
    WSL(traffic_rl)（Windows 缺依赖时）: python fig_air_brake_build.py --sim-only
"""
import sys
import json
import argparse
import logging
from pathlib import Path
from datetime import datetime

import numpy as np
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt

plt.rcParams["font.sans-serif"] = ["Microsoft YaHei"]
plt.rcParams["axes.unicode_minus"] = False

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))

ARCH_ROOT = ROOT / "outputs" / "sim_validation" / "phys_validation"
PREFIX = "brake_build_1plus0_108_"
OUT_PNG = Path(__file__).resolve().parent / "fig_air_brake_build.png"

BRAKE_S, RELEASE_S = 35.0, 50.0
DT = 0.1

logging.basicConfig(level=logging.INFO, format="%(message)s")
logger = logging.getLogger("AirBrakeFig")


def find_latest_archive():
    if not ARCH_ROOT.exists():
        return None
    cands = sorted(ARCH_ROOT.glob(f"{PREFIX}*"))
    cands = [d for d in cands if d.is_dir() and "superseded" not in d.name
             and (d / "scene_air_brake.npz").exists()]
    return cands[-1] if cands else None


def run_sim():
    """平坡常用制动→缓解场景，记录逐车制动力与档位状态，落新归档。"""
    from src.environments.train_env import TrainFormationEnv
    from src.train_dynamics.braking import AirBrakeNotch

    cfg = {
        "consist_preset": "10kt_1plus108",
        "dt": DT,
        "max_steps": 100000,
        "enable_safety": True,
        # 单机车 1+0：单一波源，制动/缓解波均从头向尾传播（勿设 1+1 的双向波开关）
        "sync_loco_brake": False,
        "grade": 0.0,
    }
    env = TrainFormationEnv(cfg)
    env.reset(options={"speed": 70.0 / 3.6})

    n_b = int(BRAKE_S / DT)
    n_r = int(RELEASE_S / DT)
    n_steps = n_b + n_r
    n_veh = env.num_vehicles
    t = np.zeros(n_steps)
    forces = np.zeros((n_steps, n_veh))       # 逐节空气制动力
    active = np.zeros((n_steps, n_veh), dtype=int)
    for k in range(n_steps):
        th = -0.5 if k < n_b else 0.0         # -0.5 → SERVICE 常用档
        t[k] = env.dynamics.time
        forces[k] = env.dynamics._air_braking_forces()
        active[k] = [1 if nr != AirBrakeNotch.RELEASE else 0
                     for nr in env.dynamics.air_brake_state()]
        env.step(np.full(n_veh, th))

    train_length = float(sum(v.length_m for v in env.dynamics.consist.vehicles))

    # 自检：波达时刻 / 有效波速 / 整列峰值 / 缓解衰减
    first_act = np.array([
        t[np.argmax(active[:, i] > 0)] if active[:, i].max() > 0 else np.nan
        for i in range(n_veh)])
    wave_dt = float(np.nanmax(first_act) - np.nanmin(first_act))
    wave_speed = train_length / wave_dt
    # 制动力为负值（阻碍运动），整列制动力量级 = 逐节取绝对值求和
    total = np.abs(forces).sum(axis=1) / 1e3
    peak = float(total.max())
    post = total[n_b:]
    t50 = float(t[n_b + int(np.argmax(post < 0.5 * peak))])
    t90 = float(t[n_b + int(np.argmax(post < 0.1 * peak))])
    logger.info("[self-check] 编组长度 = %.0f m（1×21 + 108×12）", train_length)
    logger.info("[self-check] 制动波传至尾车 Δt = %.2f s，有效波速 = %.0f m/s（配置 200 m/s，判据 B1）",
                wave_dt, wave_speed)
    logger.info("[self-check] 整列 SERVICE 制动力峰值 = %.0f kN", peak)
    logger.info("[self-check] 缓解后制动力降至 50%% / 10%% 时刻 = %.1f s / %.1f s", t50, t90)

    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    arch = ARCH_ROOT / f"{PREFIX}{stamp}"
    arch.mkdir(parents=True, exist_ok=True)
    np.savez_compressed(arch / "scene_air_brake.npz", t=t, forces=forces, active=active)
    meta = {
        "timestamp": stamp,
        "purpose": "中期答辩页 6 空气制动机制图（复刻 run_brake_release 场景，1+0×108 PPT 口径）",
        "scenario": {
            "consist_preset": "10kt_1plus108", "n_vehicles": n_veh,
            "grade": 0.0, "init_speed_kmh": 70.0, "brake_s": BRAKE_S,
            "release_s": RELEASE_S, "throttle": -0.5, "dt": DT,
            "sync_loco_brake": False, "eot": False, "enable_safety": True,
            "train_length_m": train_length,
        },
        "metrics": {
            "wave_travel_s": round(wave_dt, 3),
            "wave_speed_eff_mps": round(wave_speed, 1),
            "total_brake_peak_kn": round(peak, 1),
            "release_t50_s": round(t50, 2), "release_t90_s": round(t90, 2),
        },
        "figure": str(OUT_PNG),
        "plot": f'D:/Anaconda/python.exe "{Path(__file__)}" --plot-only',
    }
    (arch / "run_meta.json").write_text(
        json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
    logger.info("归档 → %s", arch)
    return arch


def plot(arch):
    d = np.load(arch / "scene_air_brake.npz")
    t, forces, active = d["t"], d["forces"], d["active"]
    n_veh = forces.shape[1]
    total = np.abs(forces).sum(axis=1) / 1e3
    peak = total.max()
    n_b = int(np.argmax(t >= BRAKE_S - DT / 2))  # 制动/缓解分界索引
    release_t = t[n_b]

    first_act = np.array([
        t[np.argmax(active[:, i] > 0)] if active[:, i].max() > 0 else np.nan
        for i in range(n_veh)])
    wave_dt = float(np.nanmax(first_act) - np.nanmin(first_act))
    # 缓解前沿实际传播较慢：取最后一节车解除制动的时刻，标注放其右侧空白区
    rel_end = max((float(t[np.flatnonzero(active[:, i] > 0)[-1]])
                   for i in range(n_veh) if active[:, i].max() > 0),
                  default=release_t)

    fig, (ax1, ax2) = plt.subplots(
        2, 1, figsize=(10, 7.2), sharex=True,
        gridspec_kw={"height_ratios": [1.15, 1.0]})

    # 上：制动/缓解波沿列车传播时空图（对角波前 = 有限波速）
    im = ax1.imshow(active.T, aspect="auto", origin="lower", cmap="Blues",
                    extent=[t[0], t[-1], 0, n_veh], interpolation="nearest",
                    vmin=0, vmax=1)
    cb = fig.colorbar(im, ax=ax1, pad=0.012)
    cb.set_label("空气制动状态（1 = 施加）", fontsize=10.5)
    ax1.set_ylabel("车辆序号（0 = 机车，108 = 尾车）", fontsize=11)
    ax1.set_title("常用制动下空气制动沿列车的传播与整列建立", fontsize=13, pad=10)
    ax1.text(max(0.6, wave_dt * 0.22), n_veh * 0.72, "制动波（约 200 m/s）",
             fontsize=10.5, color="black")
    ax1.text(rel_end + 1.5, n_veh * 0.48, "缓解波（两段式排气）",
             fontsize=10.5, color="black")

    # 下：整列总制动力（建立 + 稳态 + 缓解衰减）
    ax2.plot(t, total, color="#c0504d", lw=1.8)
    ax2.set_ylabel("整列空气制动力（kN）", fontsize=11)
    ax2.set_xlabel("时间（s）", fontsize=11)
    ax2.set_ylim(0, peak * 1.12)
    ax2.axvline(release_t, color="black", ls=":", lw=1.0)
    ax2.text(release_t + 0.6, peak * 0.97, "开始缓解", fontsize=10, color="black")
    ax2.text(wave_dt + 1.6, peak * 0.42, "制动建立", fontsize=10, color="black")
    ax2.text(21.0, peak * 0.90, "稳态", fontsize=10, color="black")
    ax2.grid(alpha=0.3)

    fig.tight_layout()
    fig.savefig(OUT_PNG, dpi=200, bbox_inches="tight")
    plt.close(fig)
    logger.info("已生成 %s", OUT_PNG)


def main():
    ap = argparse.ArgumentParser(description="页 6 空气制动机制图（数据/绘图分离）")
    ap.add_argument("--sim-only", action="store_true", help="只跑仿真并归档，不出图（WSL 用）")
    ap.add_argument("--plot-only", action="store_true", help="只用最新归档重画，不跑仿真")
    args = ap.parse_args()

    if not args.plot_only:
        arch = run_sim()
        if args.sim_only:
            return
    else:
        arch = find_latest_archive()
        if arch is None:
            raise FileNotFoundError(f"缺 {PREFIX}* 归档，先运行本脚本（仿真）")
        logger.info("复用归档 %s", arch)
    plot(arch)


if __name__ == "__main__":
    main()
