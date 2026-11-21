#!/usr/bin/env python3
"""第 11 投 **A/B 差值判决器**（窗口 A 干预侧 vs 窗口 B 同机同协议对照侧）。

**判决规则（前置写死，来源：ADR-084 票据 §6 + 诊断 §19.59/§19.60）**

| 读数组合 | 判决 |
| :--- | :--- |
| A 列距 ≤130 m 且 A 峰值 ≤ B×1.02 | **干预面②成立** |
| A 列距 ≤130 m 但 A 峰值明显劣于 B | **部分成立**（用峰值换几何） |
| A 列距与 B 差异 ≤ 噪声门槛（5%） | **干预面②被证伪** |
| A 列距比 B 更差 | **反向**（立即停 + 复核根因链） |

**阈值（写死）**
- `GAP_TARGET_MAX = 130.0` m（列距绝对量级目标带 ~50–130 m 的上沿）
- `PEAK_NOT_WORSE_TOL = 0.02`（峰值容差 2%，与快评护栏的 peak 噪声带一致）
- `GAP_NOISE_TOL = 0.05`（"可区分差异"门槛 = 5%；依据 §19.59 实测 1 ULP 漂移仅 1.69% ⇒ 5% 是其 ~3 倍）
- `VIOL_CAP = 5143` 步（超限步不得超过第 9 投窗口量级；依据 §19.60：ed_ab 族 19384 步被判"用超限换几何"）

**用法**
    python scripts/probes/judge_window_ab.py --a-glob "outputs/results/decompose/eval_decompose_*_w5colgap_abphys_20261121_det_ep*.json" \
                                            --b-glob "outputs/results/decompose/eval_decompose_*_w5colgap_abphys_ctrl_20261121_det_ep*.json"

⚠️ **口径**：只做**同机同协议**的 A/B 比较（云端快评产物）⇒ 跨机读数**不得**参与本判决（§19.42 纪律①）。
⚠️ 本判决器**不产出峰值/安全判据**，只输出干预实验的归因结论。
"""
from __future__ import annotations

import argparse
import glob
import json
import re
from pathlib import Path

GAP_TARGET_MAX = 130.0
PEAK_NOT_WORSE_TOL = 0.02
GAP_NOISE_TOL = 0.05
VIOL_CAP = 5143.0


def _read_metrics(path: str) -> dict:
    d = json.loads(Path(path).read_text(encoding="utf-8"))
    res = d.get("results") or {}
    m = res.get("decompose_M1_rl")
    if not isinstance(m, dict):
        for v in res.values():
            if isinstance(v, dict) and "peak_coupler_kN" in v:
                m = v
                break
    if not isinstance(m, dict):
        return {}
    ep = re.search(r"_ep(\d+)", Path(path).name)
    return {
        "ep": int(ep.group(1)) if ep else None,
        "file": Path(path).name,
        "peak_kN": m.get("peak_coupler_kN"),
        "viol": m.get("viol"),
        "band_rate": m.get("band_rate"),
        "gap_mean": m.get("gap_err_mean_abs_m"),
        "gap_peak": m.get("gap_err_peak_abs_m"),
        "gap_min": m.get("gap_min_m"),
        "rear_end": m.get("rear_end_steps"),
    }


def _collect(pat: str) -> dict:
    out = {}
    for f in sorted(glob.glob(pat)):
        m = _read_metrics(f)
        if m and m.get("ep") is not None:
            out[m["ep"]] = m
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--a-glob", required=True)
    ap.add_argument("--b-glob", required=True)
    ap.add_argument("--out", default=None)
    args = ap.parse_args()

    A, B = _collect(args.a_glob), _collect(args.b_glob)
    if not A or not B:
        print(f"[judge-AB] ABORT: 需要两侧读数（A={len(A)} B={len(B)}）")
        return 2
    common = sorted(set(A) & set(B))
    if not common:
        print("[judge-AB] ABORT: 两侧无共同集号")
        return 2

    rows = []
    for ep in common:
        a, b = A[ep], B[ep]
        ga, gb = a.get("gap_mean"), b.get("gap_mean")
        pa, pb = a.get("peak_kN"), b.get("peak_kN")
        va, vb = a.get("viol"), b.get("viol")
        d_gap = ((ga - gb) / gb) if (ga is not None and gb) else None
        d_peak = ((pa - pb) / pb) if (pa is not None and pb) else None
        rows.append({
            "ep": ep,
            "A": a, "B": b,
            "A_minus_B_gap_mean_m": (ga - gb) if (ga is not None and gb is not None) else None,
            "rel_gap_mean": d_gap,
            "rel_peak": d_peak,
            "A_gap_target_met": (ga is not None and ga <= GAP_TARGET_MAX),
            "A_peak_not_worse": (d_peak is not None and d_peak <= PEAK_NOT_WORSE_TOL),
            "A_viol_within_cap": (va is not None and va <= VIOL_CAP),
        })

    # 判决用**配对集的中位读数**（单集易受噪声影响）
    def _med(xs):
        xs = sorted([x for x in xs if x is not None])
        n = len(xs)
        if not n:
            return None
        return xs[n // 2] if n % 2 else 0.5 * (xs[n // 2 - 1] + xs[n // 2])

    a_gap = _med([r["A"]["gap_mean"] for r in rows])
    b_gap = _med([r["B"]["gap_mean"] for r in rows])
    a_peak = _med([r["A"]["peak_kN"] for r in rows])
    b_peak = _med([r["B"]["peak_kN"] for r in rows])
    a_viol = _med([r["A"]["viol"] for r in rows])
    b_viol = _med([r["B"]["viol"] for r in rows])
    rel_gap = ((a_gap - b_gap) / b_gap) if (a_gap is not None and b_gap) else None
    rel_peak = ((a_peak - b_peak) / b_peak) if (a_peak is not None and b_peak) else None

    target_met = a_gap is not None and a_gap <= GAP_TARGET_MAX
    peak_ok = rel_peak is not None and rel_peak <= PEAK_NOT_WORSE_TOL
    viol_ok = a_viol is not None and a_viol <= VIOL_CAP
    distinguishable = rel_gap is not None and abs(rel_gap) > GAP_NOISE_TOL

    # ⚠️ 分支顺序：**先判反向**（最严重、最需立刻停），再判成功/部分成功，最后判证伪。
    #    ⚠️ rel_gap > 0 表示 **A 的列距更大 = 更差**（列距是误差量，不是收益量）。
    if distinguishable and rel_gap > 0:
        code = "REVERSED"
        text = ("反向：开闸后列距比对照**更差**（相对差 > 5% 噪声门槛）⇒ 立即停止该路线，"
                "并复核『领航承担减速 ⇒ 几何收敛』这一根因链在本工况是否成立。")
    elif target_met and peak_ok and viol_ok:
        code = "INTERVENTION_CONFIRMED"
        text = ("干预面②成立：列距达标、峰值不劣于对照、超限步未暴涨 ⇒ 规则物理触发 AB 兜底"
                "在 notch_incr 内有效 ⇒ 可进入论文主线的列距主张（仍须走红线 5 的复跑确认）。")
    elif target_met and not peak_ok:
        code = "PARTIAL_TRADE_OFF"
        text = ("部分成立：列距达标，但峰值明显劣于对照（> 2% 噪声带）⇒ 该机制是『用峰值换列距』"
                "⇒ 论文须如实陈述，或叠加干预面③（奖励面归一化）后再试。")
    elif target_met and not viol_ok:
        code = "PARTIAL_VIOL_BLOWUP"
        text = ("部分成立：列距达标，但车钩超限步超过第 9 投量级（> 5143 步）⇒ "
                "属『用超限换几何』⇒ 按票据 §6 判**失败**（不得因列距达标而放行）。")
    elif not distinguishable:
        code = "INTERVENTION_NOT_CONFIRMED"
        text = ("干预面②被证伪：列距与对照无可区分差异（|Δ| ≤ 5% 噪声门槛）"
                "⇒ 规则物理触发 AB 兜底在该工况下不改变几何 ⇒ 回到归因（AB 通道可能不是主因）。")
    else:
        code = "INCONCLUSIVE"
        text = ("读数不足以下判决（请检查配对集数与字段完整性）。")

    result = {
        "thresholds": {
            "gap_target_max_m": GAP_TARGET_MAX,
            "peak_not_worse_tol": PEAK_NOT_WORSE_TOL,
            "gap_noise_tol": GAP_NOISE_TOL,
            "viol_cap": VIOL_CAP,
        },
        "paired_episodes": common,
        "rows": rows,
        "median": {
            "A_gap_mean": a_gap, "B_gap_mean": b_gap, "rel_gap_mean": rel_gap,
            "A_peak_kN": a_peak, "B_peak_kN": b_peak, "rel_peak": rel_peak,
            "A_viol": a_viol, "B_viol": b_viol,
        },
        "verdict": {"code": code, "text": text},
        "caveat": "只做同机同协议 A/B 比较；跨机读数不得参与；不产出峰值/安全判据。",
    }
    if args.out:
        Path(args.out).parent.mkdir(parents=True, exist_ok=True)
        Path(args.out).write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")

    print("[judge-AB] ==== 第 11 投 A/B 差值判决（阈值前置写死） ====")
    for r in rows:
        print(f"[judge-AB] ep{r['ep']}: A gap={r['A']['gap_mean']:.1f}m peak={r['A']['peak_kN']:.1f} "
              f"viol={r['A']['viol']:.0f} | B gap={r['B']['gap_mean']:.1f}m peak={r['B']['peak_kN']:.1f} "
              f"viol={r['B']['viol']:.0f} | Δgap={r['A_minus_B_gap_mean_m']:+.1f}m "
              f"({(r['rel_gap_mean'] or 0)*100:+.1f}%)")
    print(f"[judge-AB] 中位: A gap={a_gap:.1f} B gap={b_gap:.1f} (Δ{(rel_gap or 0)*100:+.1f}%) | "
          f"A peak={a_peak:.1f} B peak={b_peak:.1f} (Δ{(rel_peak or 0)*100:+.1f}%) | "
          f"A viol={a_viol:.0f} B viol={b_viol:.0f}")
    print(f"[judge-AB] VERDICT = {code}")
    print(f"[judge-AB] {text}")
    if args.out:
        print(f"[judge-AB] wrote {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
