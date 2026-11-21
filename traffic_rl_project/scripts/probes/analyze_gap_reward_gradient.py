#!/usr/bin/env python3
"""干预面③（奖励面）的**零机时量纲分析**：奖励尺度必须标定到本项目的实测散开量级。

**背景（诊断 §19.51.3d / §19.55 / §19.65）**
    奖励面里唯一的"间距效率项"是
        `gap_eff_reward += GAP_EFF_W · max(0, 1 − (actual_gap − d_eff) / GAP_EFF_SCALE_M)`
    其中 `d_eff = 1.1 · d_safe ≈ 141 m`、`GAP_EFF_SCALE_M = 150.0`（**硬编码常量**）。
    第 9 投实测列距 584–940 m ⇒ 散开量 `x = actual_gap − d_eff` = **443–799 m**
    ⇒ `x / 150` = 2.95–5.33 ⇒ **该项全程恒为 0** ⇒ 奖励面看不见"散开"。

**⚠️ 本脚本要回答的两个问题（都会给定量结论）**
    Q1：照抄 Hu2026（PM-MASAC）的公式 `e_d = (Δd − d_target)/(d_target + ε)`、
        `r = 1 − e_d`、越界置零，**在本工况是否可用**？
        ⇒ 关键：`d_target = d_eff ≈ 141 m` ⇒ `e_d` = 3.1–6.7 ⇒ **全部越界 ⇒ 仍恒零**。
    Q2：若保持"有界归一"形状，**衰减尺度 s 取多少**才能让实测区间真正落在有梯度区？

**输出**：`outputs/logs/adr083_gap_primary_metric_sweep/gap_reward_gradient_analysis.json`
（每个候选 s 的"有非零梯度的样本比例""平均奖励""动态范围"）+ stdout 结论。

⚠️ **口径**：本脚本是**奖励面设计的量纲分析**，**不产出任何峰值/安全判据**；样本取自**同源官方整程快评**（`physics_version=c9de4f9f7903` + `consist_preset=10kt_1plus108` + `max_steps=31500` + 主指标字段齐备）。
"""
from __future__ import annotations

import argparse
import glob
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
D_EFF_M = 141.0          # = GAP_EFF_MARGIN(1.1) × d_safe ≈ 141 m（ADR-061 同源）
GAP_EFF_W = 3.0          # 现有权重（每对）
CANDIDATE_S = (150.0, 300.0, 600.0, 900.0, 1200.0, 2000.0, 4000.0)


def _collect_gaps() -> list[dict]:
    rows = []
    for f in sorted(glob.glob(str(ROOT / "outputs/results/decompose/eval_decompose_*.json"))):
        try:
            d = json.loads(Path(f).read_text(encoding="utf-8"))
        except Exception:
            continue
        md = d.get("metadata") or {}
        ea = md.get("eval_args") or {}
        ph = ((md.get("physics") or {}).get("physics") or {})
        r = (d.get("results") or {}).get("decompose_M1_rl") or {}
        if md.get("physics_version") != "c9de4f9f7903":
            continue
        if ph.get("consist_preset") != "10kt_1plus108":
            continue
        if ea.get("max_steps") != 31500:
            continue
        g = r.get("gap_err_mean_abs_m")
        if g is None:
            continue
        rows.append({"file": Path(f).name, "gap_err_mean_abs_m": float(g),
                     "peak_kN": r.get("peak_coupler_kN"), "band_rate": r.get("band_rate"),
                     "schema": (md.get("observation_schema") or {}).get("name")
                     if isinstance(md.get("observation_schema"), dict) else md.get("observation_schema")})
    return rows


def _reward(actual_gap: float, scale: float, d_eff: float = D_EFF_M) -> float:
    """现有形状（有界归一）：x = max(0, gap − d_eff)；r = W·max(0, 1 − x/s)。"""
    if actual_gap < d_eff:
        return 0.0
    x = actual_gap - d_eff
    return GAP_EFF_W * max(0.0, 1.0 - x / scale)


def _reward_pm_masac(actual_gap: float, d_target: float = D_EFF_M, eps: float = 1.0) -> float:
    """Hu2026（PM-MASAC）写法：e_d = (Δd − d_target)/(d_target + ε)；r = 1 − e_d；e_d ≥ 1 ⇒ 0。"""
    e = (actual_gap - d_target) / (d_target + eps)
    return max(0.0, 1.0 - e)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=str(ROOT / "outputs/logs/adr083_gap_primary_metric_sweep"
                                         / "gap_reward_gradient_analysis.json"))
    args = ap.parse_args()

    rows = _collect_gaps()
    if not rows:
        print("[gap-grad] ABORT: 未取到同源样本")
        return 2
    gaps = [r["gap_err_mean_abs_m"] for r in rows]
    excesses = [max(0.0, g - D_EFF_M) for g in gaps]

    # Q1：照抄 PM-MASAC 的 d_target 归一化 ⇒ 在实测区间上的非零比例
    pm_nonzero = [g for g in gaps if _reward_pm_masac(g) > 0]
    pm_nonzero_frac = len(pm_nonzero) / len(gaps)

    # Q2：各候选尺度的覆盖与动态范围
    cand = []
    for s in CANDIDATE_S:
        rewards = [_reward(g, s) for g in gaps]
        nz = [r for r in rewards if r > 0]
        cand.append({
            "scale_m": s,
            "nonzero_frac": len(nz) / len(rewards),
            "mean_reward": sum(rewards) / len(rewards),
            "max_reward": max(rewards),
            "min_reward": min(rewards),
            "dynamic_range": (max(rewards) - min(rewards)) if rewards else 0.0,
        })

    # ⚠️ "可行尺度"必须按**工作区间**判，而不是按全库样本判：
    #    全库含极端发散样本（最大 7154 m）⇒ 任何有限 s 都覆盖不满 ⇒ 判据会被极端值绑架。
    #    工作区间 = ① 第 9 投族实测列距 584–940 m（要治的病）
    #              ② 早期档列距 25–130 m（已达标，不能被破坏）
    WORK_BAND = (584.0, 940.0)      # 第 9 投族实测列距区间
    GOOD_BAND = (0.0, 130.0)        # 已达标区间（ed_ab 族）
    work = [g for g in gaps if WORK_BAND[0] <= g <= WORK_BAND[1]]
    good = [g for g in gaps if GOOD_BAND[0] <= g <= GOOD_BAND[1]]
    for c in cand:
        s = c["scale_m"]
        c["work_band_nonzero_frac"] = (
            sum(1 for g in work if _reward(g, s) > 0) / len(work)) if work else None
        c["work_band_mean_reward"] = (
            sum(_reward(g, s) for g in work) / len(work)) if work else None
        c["good_band_mean_reward"] = (
            sum(_reward(g, s) for g in good) / len(good)) if good else None
    # 可行 = 工作区间**全部**有梯度（nonzero_frac == 1.0）
    viable = [c["scale_m"] for c in cand if (c["work_band_nonzero_frac"] or 0) >= 1.0]
    # 早达标样本的保护：s 越大越接近满额（不惩罚已达标）⇒ 无上界问题
    min_s_full = max([max(0.0, g - D_EFF_M) for g in work], default=0.0)
    result = {
        "n_samples": len(rows),
        "d_eff_m": D_EFF_M,
        "gap_err_mean_abs_m": {
            "min": min(gaps), "median": sorted(gaps)[len(gaps) // 2], "max": max(gaps),
        },
        "excess_over_d_eff_m": {
            "min": min(excesses), "median": sorted(excesses)[len(excesses) // 2],
            "max": max(excesses),
        },
        "Q1_pm_masac_d_target_normalized": {
            "nonzero_frac": pm_nonzero_frac,
            "conclusion": (
                f"照抄 d_target=d_eff 的 PM-MASAC 归一化：全库非零比例 {pm_nonzero_frac:.1%}，但"
                "**对'已达标'样本（gap 25–130 m ⇒ e_d<0）恒满额、对'散开'样本"
                "（第 9 投族 584–940 m ⇒ e_d=3.1–6.7 ⇒ 全部越界）恒为零**"
                "⇒ 该写法**只奖励已经达标的样本、对正在散开的样本无任何梯度** ⇒ 治不了本病"),
            "note_pm_masac_scope": ("本项目『误差』相对参考线是数倍级（VCTS 是百分之几级）⇒ "
                                    "文献公式的 d_target 归一化在本工况不适用；"
                                    "可迁移的是**有界归一 + 权重占比 + 阶段调度**的方法论，"
                                    "尺度必须按本项目实测散开量级重新标定"),
        },
        "Q2_scale_sweep": cand,
        "viable_scales_m": viable,
        "caveat": ("本分析只回答『奖励尺度是否让散开进入梯度』，不回答『新权重会不会破坏其它奖励项平衡』；"
                   "后者须由训练侧验证（ADR-070）。不产出任何峰值/安全判据。"),
    }
    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    Path(args.out).write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")

    print("[gap-grad] 样本 n =", len(rows))
    print(f"[gap-grad] gap_err_mean_abs_m: min={min(gaps):.1f} "
          f"median={sorted(gaps)[len(gaps)//2]:.1f} max={max(gaps):.1f} m")
    print(f"[gap-grad] 散开量 x = gap − d_eff({D_EFF_M:.0f}m): "
          f"min={min(excesses):.1f} median={sorted(excesses)[len(excesses)//2]:.1f} max={max(excesses):.1f} m")
    print(f"[gap-grad] Q1 照抄 PM-MASAC(d_target=d_eff)：全库非零 {pm_nonzero_frac:.1%} ⇒ "
          "对'已达标'样本恒满额、对'散开'样本恒零 ⇒ 治不了本病")
    print(f"[gap-grad] 工作区间（第 9 投族 {WORK_BAND[0]:.0f}–{WORK_BAND[1]:.0f} m）n={len(work)}；"
          f"早达标区间（{GOOD_BAND[0]:.0f}–{GOOD_BAND[1]:.0f} m）n={len(good)}")
    print("[gap-grad] Q2 尺度扫描（有界归一形状，r = W·max(0, 1 − x/s)）：")
    for c in cand:
        print(f"[gap-grad]   s={c['scale_m']:>6.0f}m  全库非零={c['nonzero_frac']:>6.1%}  "
              f"工作区间非零={(c['work_band_nonzero_frac'] or 0):>6.1%}  "
              f"工作区间均值={c['work_band_mean_reward']:.3f}  早达标均值={c['good_band_mean_reward']:.3f}")
    print(f"[gap-grad] 让工作区间**全部**有梯度所需 s ≥ {min_s_full:.0f} m ⇒ 可行尺度 = {viable} m")
    print(f"[gap-grad] wrote {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
