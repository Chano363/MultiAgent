"""
展示用：ETCS 目标距离超速防护（真 ATP）曲线演示图。

场景 = 朔黄 53km 真实纵断面上取一段，列车以线路限速（80 km/h）恒速 coast，
前方 6.5 km 远处存在一个「停车目标」（模拟停留列车 / 需停车点）。
若不加 ETCS 前瞻防护 → 以 22.2 m/s 直冲目标（追尾 / 越线）；
有 ETCS → 速度全程压在 EBD（EBI）曲线之下，最终刹停在目标前。

该图突出「反应式 vs 前瞻式」：
  - 反应式（看到超速/逼近才动）拦不住「前方有目标、但此刻速度还合规」的隐忧；
  - ETCS 从前方目标向后算保证制动距离 → 提前把允许速度压下来（EBD 曲线）。

用法（WSL2，conda traffic_rl，cwd=traffic_rl_project）：
    python scripts/gen_atp_etcs_demo.py
输出：outputs/figures/report/fig_atp_etcs_supervision.png

仅依赖 src.train_dynamics（etcs_braking + grade_profile），不依赖训练环境。
为演示清晰，保护区轨迹 = min( 巡航 coast, EBD 允许速度 )（即 ATP 硬性把速度压到
EBD 曲线之下、绝不越 EBI），再标注一次 SBI 触发点。

图中文案均为规范英文（避免中文字体缺失）。
"""

import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

from src.train_dynamics.etcs_braking import (
    EtcsBrakingCurve, EbdTarget, braking_build_up_from_train,
)
from src.train_dynamics.grade_profile import PROFILES

# --------------------------------------------------------------------------- #
# 1) ETCS 曲线（参数对齐项目正式配置）
# --------------------------------------------------------------------------- #
TRAIN_LEN_M = 1221.0                  # 1+0 万吨：机车21m + 100×C80货车12m ≈1221m
BUILD_UP_S = braking_build_up_from_train(TRAIN_LEN_M, propagation_speed_mps=250.0)

curve = EtcsBrakingCurve(
    nominal_emergency_decel=1.6,      # C80 紧急制动量级 a≈1.6 m/s²
    k_dry=1.0, k_wet=0.893,           # 干轨演示（wet_weight=0）
    wet_weight=0.0,
    brake_build_up_s=BUILD_UP_S,      # ~4.9s（波速传播）
    assumed_accel_during_buildup=0.2, # 建立期内最不利正向加速（下坡净加速）
    speed_err_mps=0.35,               # 速度测量误差
    driver_time_i_to_p=9.0, driver_time_p_to_ebi=4.0,  # ETCS 固定
    grade_at=PROFILES["shuozhou_ningwuxi_beidaniu_49km"]().grade_at,
)

# 前方目标：停车点（模拟停留列车 / 需停车），距 x_far 约 6.5km
X_GOAL_M = 24500.0
GOAL = EbdTarget(position_m=X_GOAL_M, speed_mps=0.0, kind="stop")

V_LIM = 22.2                      # 线路限速 80 km/h
X_FAR_M = X_GOAL_M - 6500.0       # 起始里程

# --------------------------------------------------------------------------- #
# 2) 沿里程逐点采样约束曲线（安全层热路径 supervise_targets —— 最真实口径）
# --------------------------------------------------------------------------- #
xs = np.arange(X_FAR_M, X_GOAL_M + 5.0, 25.0)
EBI = {"v": [], "s": []}
SBI = {"v": [], "s": []}
for x in xs:
    out = curve.supervise_targets([GOAL], v_cur=V_LIM, position_m=float(x))
    EBI["v"].append(out["EBI"] if out["EBI"] is not None else np.nan)
    SBI["v"].append(out["SBI"] if out["SBI"] is not None else np.nan)
    EBI["s"].append(float(x))
    SBI["s"].append(float(x))

EBI_v = np.asarray(EBI["v"])
SBI_v = np.asarray(SBI["v"])

# 轨迹1：无 ATP —— 恒 coast 直冲目标
coast_v = np.full(xs.shape, V_LIM)

# 轨迹2：受 ETCS 管制 —— 速度压到 EBD（EBI）曲线之下（不小于 0，刹停即止）
prot_v = np.clip(np.minimum(coast_v, EBI_v - 0.3), 0.0, V_LIM)

# 触发点：无防护 coast 首次触到 SBI（=ATP 应提前介入处）
trig_idx = np.where(coast_v >= SBI_v)[0]
trig_x, trig_v = (float(xs[trig_idx[0]]), float(SBI_v[trig_idx[0]])) if trig_idx.size else (np.nan, np.nan)

# --------------------------------------------------------------------------- #
# 3) 坡度剖面（下图为背景，体现 EBD 受坡道影响）
# --------------------------------------------------------------------------- #
grades_kmh_free = np.array([PROFILES["shuozhou_ningwuxi_beidaniu_49km"]().grade_at(float(x)) * 1000.0 for x in xs])

# --------------------------------------------------------------------------- #
# 4) 绘图
# --------------------------------------------------------------------------- #
KM = 1000.0
fig, (ax1, ax2) = plt.subplots(
    2, 1, figsize=(10, 7.2), sharex=True,
    gridspec_kw={"height_ratios": [3.2, 1.0], "hspace": 0.08},
)

# -- 上图：速度-里程 --
ax1.axhspan(0.0, V_LIM, color="0.93", zorder=0)          # 合规区
ax1.plot([x / KM for x in xs], coast_v, "--", color="#c0392b", lw=2.2,
         label="unprotected coast: no ATP")
ax1.plot([x / KM for x in xs], prot_v, "-", color="#1e8449", lw=2.6,
         label="protected: ETCS keeps v under EBD")
ax1.plot([x / KM for x in EBI["s"]], EBI_v, "-", color="#e74c3c", lw=1.6,
         label="EBD / EBI (hard supervision)")
ax1.plot([x / KM for x in SBI["s"]], SBI_v, "--", color="#e67e22", lw=1.2,
         label="SBI (service-brake warning)")
ax1.axhline(V_LIM, color="#34495e", lw=1.2, ls=":", label="line limit 80 km/h")
ax1.axvline(X_GOAL_M / KM, color="k", lw=1.4, ls="-.")
ax1.annotate("stop target\n(front train / stop point)",
             xy=(X_GOAL_M / KM, 0), xytext=(X_GOAL_M / KM - 0.9, 4.2),
             arrowprops=dict(arrowstyle="->", color="k"), fontsize=8, ha="center")

if np.isfinite(trig_x):
    ax1.plot(trig_x / KM, trig_v, marker="v", ms=10, color="#d35400", zorder=5)
    ax1.annotate(f"SBI triggered at {trig_x / KM:.2f} km", xy=(trig_x / KM, trig_v),
                 xytext=(trig_x / KM + 0.9, trig_v + 2.0),
                 arrowprops=dict(arrowstyle="->", color="#d35400"), fontsize=9)

ax1.set_ylabel("speed (m/s)")
ax1.set_ylim(0, 30)
ax1.legend(loc="lower left", fontsize=8, framealpha=0.95)
ax1.set_title("ETCS target-distance speed supervision on Shuohuang 53-km long downhill "
              "(1+0 heavy-haul, brake build-up 4.9 s)", fontsize=11)
ax1.grid(True, alpha=0.3)

# -- 下图：坡度剖面 --
ax2.plot([x / KM for x in xs], grades_kmh_free, color="#16a085", lw=1.4)
ax2.set_ylabel("grade (‰)")
ax2.set_xlabel("distance along line (km)")
ax2.grid(True, alpha=0.3)
ax2.axhline(0.0, color="k", lw=0.6)

plt.tight_layout()
out = "outputs/figures/report/fig_atp_etcs_supervision.png"
plt.savefig(out, dpi=220)
print(f"saved: {out}")

# 打印关键数值，便于核对
print(f"brake build-up: {BUILD_UP_S:.2f} s | line limit {V_LIM:.1f} m/s "
      f"({V_LIM*3.6:.0f} km/h)")
print(f"unprotected coast at goal: {coast_v[-1]:.1f} m/s  -> would collide/overspeed")
print(f"protected speed at goal:   {prot_v[-1]:.1f} m/s  -> stopped before target")
print(f"SBI first-touch: {trig_x / KM:.2f} km (ATP intervenes there)")