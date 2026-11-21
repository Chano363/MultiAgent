#!/usr/bin/env python3
"""P1 判读器：主指标口径的**浮点噪声带 vs §19.47 信号幅度**（判读规则**已前置量化**）。

**为什么需要这个脚本**：§19.48(c) 写死了判读规则——"主指标漂移 ≫ §19.47 的信号幅度 ⇒
§19.47 结论不可用、须另找抗噪信号；≪ ⇒ 不受威胁、可继续作靶子"——但当时**没有量化
"≫ / ≪"的阈值** ⇒ 数据到手后必然出现事后解释风险。⇒ 本脚本把两个量放在**同一可比
尺度**上比较，并把阈值**写死在代码里**（见下方常量），先跑规则、后看数据。

**两个量的定义（写死）**

| 量 | 定义 | 来源 |
| :--- | :--- | :--- |
| **漂移带 drift(M)** | 1 ULP 扰动（+1 与 −1 取绝对值较大者）造成的**相对变化** `|ΔM|/|M₀|` | `primary_metric_sensitivity.json`（P1 探针，0/1/−1 ULP 三档整程） |
| **信号幅度 signal(M)** | §19.47 标定集（n=7 集）内该主指标的**相对极差** `(max−min)/median` —— 即"这个量在集与集之间本来能差多少" | `primary_metric_corr.json` 的 `table`（ep1–ep7 评估态读数） |

⇒ 若 **drift(M) ≳ signal(M)** ⇒ 1 ULP 的浮点微差就能吃掉整个集间差异 ⇒ §19.47 在该量上的
相关性**是在量噪声** ⇒ 该量的靶子资格作废；反之若 drift ≪ signal ⇒ 该量上的相关性站得住。

**判决阈值（前置写死，见常量）**
- 比值 `r = drift / signal`：**r ≥ 1.0 ⇒ 噪声主导**（该量的 §19.47 相关性不可用）；
  **r ≤ 0.3 ⇒ 信号主导**（可用）；**0.3 < r < 1.0 ⇒ 边缘**（须降级表述：只能作弱先验）。

**输出**：`outputs/logs/adr083_float_probe/primary_metric_sensitivity_verdict.json` +
stdout 判决文本（可直接粘进诊断日志）。

⚠️ **口径边界**：本脚本只做**同一台机器、同一 ckpt、同一协议**内的比较 ⇒ 不涉及跨机
（跨机漂移带是 §19.49 的另一件事，**不得混引**）；本脚本**不产出任何峰值/安全判据**。
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

# ---- 前置写死的判决阈值（先定规则，后看数据）----
RATIO_NOISE = 1.0        # drift/signal ≥ 此值 ⇒ 噪声主导
RATIO_SIGNAL = 0.3       # drift/signal ≤ 此值 ⇒ 信号主导
METRICS = ("gap_err_mean_abs_m", "gap_err_peak_abs_m", "band_rate", "gap_min_m")


def _median(xs):
    xs = sorted(xs)
    n = len(xs)
    if not n:
        return None
    return xs[n // 2] if n % 2 else 0.5 * (xs[n // 2 - 1] + xs[n // 2])


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--sens", default=str(ROOT / "outputs/logs/adr083_float_probe"
                                           / "primary_metric_sensitivity.json"))
    ap.add_argument("--corr", default=str(ROOT / "outputs/logs/adr083_primary_metric_corr"
                                           / "primary_metric_corr.json"))
    ap.add_argument("--out", default=str(ROOT / "outputs/logs/adr083_float_probe"
                                         / "primary_metric_sensitivity_verdict.json"))
    args = ap.parse_args()

    sens_p, corr_p = Path(args.sens), Path(args.corr)
    if not sens_p.is_file():
        print(f"[judge] ABORT: 探针产物缺失 {sens_p}（P1 未完成 ⇒ 不得判决）")
        return 2
    if not corr_p.is_file():
        print(f"[judge] ABORT: 标定产物缺失 {corr_p}")
        return 2

    sens = json.loads(sens_p.read_text(encoding="utf-8"))
    corr = json.loads(corr_p.read_text(encoding="utf-8"))

    by_u = {r.get("ulps"): r for r in sens.get("results", [])}
    if 0 not in by_u:
        print("[judge] ABORT: 探针产物缺 0 ULP 基线档")
        return 2
    base = by_u[0]
    perturbations = [u for u in by_u if u != 0]
    if not perturbations:
        print("[judge] ABORT: 无非零扰动档")
        return 2

    # ---- 集间信号幅度（§19.47 标定集 n=7）----
    table = corr.get("table") or {}
    series = {m: [] for m in METRICS}
    keymap = {"gap_err_mean_abs_m": "eval_gap_err_mean_abs_m",
              "gap_err_peak_abs_m": "eval_gap_err_peak_abs_m",
              "band_rate": "eval_band_rate",
              "gap_min_m": "eval_gap_min_m"}
    for ep in table.values():
        for m, k in keymap.items():
            v = ep.get(k)
            if v is not None:
                series[m].append(float(v))

    rows = []
    for m in METRICS:
        vals = series.get(m) or []
        if not vals:
            continue
        med = _median(vals)
        signal = ((max(vals) - min(vals)) / med) if med else None
        drift = 0.0
        for u in perturbations:
            r = by_u[u]
            b = base.get(m)
            if b in (None, 0) or r.get(m) is None:
                continue
            drift = max(drift, abs(float(r[m]) - float(b)) / abs(float(b)))
        ratio = (drift / signal) if signal else None
        if ratio is None:
            verdict = "UNKNOWN"
        elif ratio >= RATIO_NOISE:
            verdict = "NOISE_DOMINATED"
        elif ratio <= RATIO_SIGNAL:
            verdict = "SIGNAL_DOMINATED"
        else:
            verdict = "MARGINAL"
        rows.append({
            "metric": m,
            "drift_1ulp_rel": drift,
            "signal_ep_spread_rel": signal,
            "ratio": ratio,
            "verdict": verdict,
            "n_episodes": len(vals),
            "base_value": base.get(m),
            "perturbations": {str(u): by_u[u].get(m) for u in perturbations},
        })

    any_noise = any(r["verdict"] == "NOISE_DOMINATED" for r in rows)
    any_signal = any(r["verdict"] == "SIGNAL_DOMINATED" for r in rows)
    if any_noise:
        overall = ("SOME_METRICS_NOISE_DOMINATED",
                   "至少一个主指标上的 1 ULP 漂移 ≥ 集间信号幅度 ⇒ 该指标上的 §19.47 "
                   "相关性不可用；第 11 投的止损判据须改用未被污染的指标（或另找抗噪信号）。")
    elif any_signal:
        overall = ("SIGNAL_DOMINATED",
                   "至少一个主指标的漂移 ≪ 集间信号幅度 ⇒ §19.47 在该指标上的结论"
                   "**不受浮点噪声威胁**，可继续作第 11 投的靶子；其余指标按其分级表述。")
    else:
        overall = ("ALL_MARGINAL",
                   "各指标均落在边缘带（0.3 < ratio < 1.0）⇒ §19.47 结论只能作弱先验，"
                   "窗口内须用云端重标定（§19.49）复核，不得当判据。")

    out = {
        "rule": {
            "drift": "1 ULP 扰动造成的相对变化（+1 与 −1 取较大者）",
            "signal": "§19.47 标定集（n=7）内该量的相对极差 (max−min)/median",
            "ratio_noise": RATIO_NOISE,
            "ratio_signal": RATIO_SIGNAL,
            "source_sens": str(sens_p.relative_to(ROOT)),
            "source_corr": str(corr_p.relative_to(ROOT)),
        },
        "rows": rows,
        "overall": {"code": overall[0], "text": overall[1]},
        "caveat": ("只做同机同 ckpt 同协议的比较，不涉及跨机（跨机漂移带见 §19.49，"
                   "不得混引）；不产出任何峰值/安全判据。"),
    }
    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    Path(args.out).write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")

    print("[judge] ==== P1 判决（规则前置写死：ratio≥1.0 噪声主导 / ≤0.3 信号主导） ====")
    for r in rows:
        print(f"[judge] {r['metric']:24s} drift={r['drift_1ulp_rel']:.4%}  "
              f"signal={r['signal_ep_spread_rel']:.4%}  ratio={r['ratio']:.3f}  → {r['verdict']}")
    print(f"[judge] OVERALL = {overall[0]}")
    print(f"[judge] {overall[1]}")
    print(f"[judge] wrote {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
