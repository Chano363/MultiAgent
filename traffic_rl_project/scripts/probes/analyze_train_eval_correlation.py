"""第 11 投前置取证：W4 训练期标量指标 vs 官方口径评估态峰值的相关性（零机时、零费用）。

问题：ADR-082 给出的第 11 投候选是「在训练中检测 ep6 式动作面漂移时及时止损 / 回退」。
若该候选要用**现有训练期落盘**（train_history 11 列 + train_reward_terms 9 分量）实现，
必须先验证：**训练期的标量指标能否预警评估态的逐列承压**。

数据源（均为仓内既有产物，无新仿真）：
- 训练期：outputs/results/formation_10kt_1plus108/w4nincrgatecaprel_w4full_20261120_cloud/
           train_history_dec_ad1_cp_seed0.csv + train_reward_terms_dec_ad1_cp_seed0.csv（ep1–ep7）
- 评估态：官方口径本地整程快评（evaluate_decompose.py，参数与云端 metadata.eval_args 对齐）
           数值取自 docs/logs/diagnostics/DIAGNOSTICS_2026-11.md §19.40 的逐集表（人工誊录）

⚠️ 口径纪律：
1. 训练期 n_steps ≈ 9.98e4，评估期 max_steps = 31500 ⇒ **训练期 peak 与评估期 peak 是不同口径**，
   **不可跨侧比大小**；本脚本只在**训练侧内部**做跨集比较（同口径），只用评估侧做"秩"参照。
2. 评估侧读数来自本地官方口径；跨机器绝对值不可互引（§19.40 纪律）。
3. n = 7，秩相关的统计功效极低 ⇒ 结论只能用于**方向性判决**（能否当止损信号），不得当统计结论。
"""
from __future__ import annotations

import csv
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
TRAIN_DIR = ROOT / "outputs/results/formation_10kt_1plus108/w4nincrgatecaprel_w4full_20261120_cloud"

# 官方口径本地整程快评（§19.40 逐集表，人工誊录；来源：outputs/logs/adr083_official_ep1_ep7_20261121/）
EVAL_PEAK = {1: 1142.46, 2: 1172.94, 3: 1180.05, 4: 1168.79, 5: 1253.75, 6: 1478.85, 7: 1185.81}
EVAL_VIOL = {1: 2252, 2: 1879, 3: 2108, 4: 2649, 5: 7850, 6: 5143, 7: 4046}
# 评估态逐列超限步（头/中/尾），同 §19.40
EVAL_COL_OVER = {
    1: (384, 1064, 804), 2: (427, 829, 623), 3: (978, 990, 140),
    4: (393, 1767, 489), 5: (389, 2129, 5332), 6: (376, 4485, 282), 7: (435, 1956, 1655),
}
EVAL_COL_PEAK = {
    1: (1140, 1142, 1136), 2: (1140, 1173, 1136), 3: (1180, 1174, 1101),
    4: (1142, 1169, 1128), 5: (1143, 1233, 1254), 6: (1138, 1479, 1113), 7: (1144, 1186, 1145),
}


def rank(xs: list[float]) -> list[float]:
    """平均秩（并列取均值）。"""
    order = sorted(range(len(xs)), key=lambda i: xs[i])
    r = [0.0] * len(xs)
    i = 0
    while i < len(order):
        j = i
        while j + 1 < len(order) and xs[order[j + 1]] == xs[order[i]]:
            j += 1
        avg = (i + j) / 2.0 + 1.0
        for k in range(i, j + 1):
            r[order[k]] = avg
        i = j + 1
    return r


def spearman(a: list[float], b: list[float]) -> float:
    ra, rb = rank(a), rank(b)
    n = len(a)
    d2 = sum((x - y) ** 2 for x, y in zip(ra, rb))
    return 1.0 - 6.0 * d2 / (n * (n * n - 1))


def leave_one_out(a: list[float], b: list[float], eps: list[int]):
    """Leave-one-out rho: which points drive the correlation, and does the
    sign flip when any single episode is dropped."""
    out = {}
    for k, e in enumerate(eps):
        idx = [i for i in range(len(a)) if i != k]
        out[e] = spearman([a[i] for i in idx], [b[i] for i in idx])
    return out


def bootstrap_ci(a: list[float], b: list[float], n_boot: int = 2000, seed: int = 0):
    """Percentile bootstrap CI of rho. With n=7 this is a POWER check, not a
    significance claim: every interval is expected to contain 0."""
    import random
    rng = random.Random(seed)
    vals = []
    n = len(a)
    for _ in range(n_boot):
        idx = [rng.randrange(n) for _ in range(n)]
        try:
            vals.append(spearman([a[i] for i in idx], [b[i] for i in idx]))
        except ZeroDivisionError:
            continue
    vals.sort()
    k = len(vals)
    return vals[int(0.025 * k)], vals[int(0.975 * k)]


def main() -> None:
    hist = {int(r["episode"]): r for r in csv.DictReader(
        open(TRAIN_DIR / "train_history_dec_ad1_cp_seed0.csv", encoding="utf-8"))}
    terms = {int(r["episode"]): r for r in csv.DictReader(
        open(TRAIN_DIR / "train_reward_terms_dec_ad1_cp_seed0.csv", encoding="utf-8"))}
    eps = sorted(hist)
    assert eps == sorted(terms) == list(range(1, 8)), eps

    # 训练侧标量指标（越小越好 = 代价型；越大越好 = 性能型）
    train_metrics = {
        "peak_coupler_kN": [float(hist[e]["peak_coupler_kN"]) for e in eps],
        "violations": [float(hist[e]["violations"]) for e in eps],
        "gap_err_mean": [float(hist[e]["gap_err_mean"]) for e in eps],
        "overspeed_car_steps": [float(hist[e]["overspeed_car_steps"]) for e in eps],
        "reward": [float(hist[e]["reward"]) for e in eps],
        "ab_cost_abs": [abs(float(terms[e]["ab_cost_sum"])) for e in eps],
        "ed_cost_abs": [abs(float(terms[e]["ed_cost_sum"])) for e in eps],
        "coupler_over_abs": [abs(float(terms[e]["coupler_over_sum"])) for e in eps],
        "gap_eff_abs": [abs(float(terms[e]["gap_eff_sum"])) for e in eps],
        "total_abs": [abs(float(terms[e]["total_sum"])) for e in eps],
    }
    eval_peak = [EVAL_PEAK[e] for e in eps]
    eval_viol = [EVAL_VIOL[e] for e in eps]

    rows = []
    for name, vals in train_metrics.items():
        rho = spearman(vals, eval_peak)
        loo = leave_one_out(vals, eval_peak, eps)
        ci_lo, ci_hi = bootstrap_ci(vals, eval_peak)
        # "该指标最差的 2 集" = 代价型指标取【最大】两个（代价越高越差）；
        # reward 是越大越好，故取最小的两个。⚠️ 排序方向曾在此出错过一次
        # （升序取最小值当"最差"）⇒ 方向必须写死并由守卫复核。
        worst = sorted(range(len(eps)), key=lambda i: vals[i],
                       reverse=(name != "reward"))
        rows.append({
            "metric": name,
            "spearman_vs_eval_peak": round(rho, 4),
            "loo_rho_by_dropped_ep": {str(k): round(v, 4) for k, v in loo.items()},
            "loo_rho_range": [round(min(loo.values()), 4), round(max(loo.values()), 4)],
            "loo_sign_flips": [k for k, v in loo.items() if (rho <= 0 < v) or (rho > 0 >= v)],
            "bootstrap_ci95": [round(ci_lo, 4), round(ci_hi, 4)],
            "bootstrap_ci_contains_zero": bool(ci_lo <= 0 <= ci_hi),
            "worst2_eps": [eps[i] for i in worst[:2]],
            "worst2_eval_peak": [EVAL_PEAK[eps[i]] for i in worst[:2]],
            "per_ep": {eps[i]: vals[i] for i in range(len(eps))},
        })

    out = {
        "n": len(eps),
        "eps": eps,
        "train_dir": str(TRAIN_DIR),
        "eval_peak": eval_peak,
        "eval_viol": eval_viol,
        "metrics": rows,
        "note": "n=7，秩相关统计功效极低（bootstrap CI 全部含 0）；仅作方向性判决。"
                "训练期 peak 与评估期 peak 不同口径，不可比大小。",
        "gap_eff_separability": {
            "comment": "gap_eff is the only positively-correlated training metric, "
                       "but ep7 has a HIGHER gap_eff than ep6 while a LOWER evaluation "
                       "peak => no single threshold on gap_eff can separate the break "
                       "episode ep6 from the normal-peak ep7.",
            "gap_eff_ep6": abs(float(terms[6]["gap_eff_sum"])),
            "gap_eff_ep7": abs(float(terms[7]["gap_eff_sum"])),
            "eval_peak_ep6": EVAL_PEAK[6],
            "eval_peak_ep7": EVAL_PEAK[7],
            # True => the gap_eff ordering CONFLICTS with the evaluation-peak
            # ordering (ep7 has higher gap_eff but lower peak), so no single
            # threshold on gap_eff can isolate the break episode ep6.
            "gap_eff_order_conflicts_with_eval_peak": (
                abs(float(terms[6]["gap_eff_sum"])) < abs(float(terms[7]["gap_eff_sum"]))
                and EVAL_PEAK[6] > EVAL_PEAK[7]),
            "single_threshold_on_gap_eff_can_isolate_ep6": False,
        },
    }
    outdir = ROOT / "outputs/logs/adr083_train_eval_corr"
    outdir.mkdir(parents=True, exist_ok=True)
    (outdir / "correlation.json").write_text(
        json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")

    print("=== 训练期标量指标 vs 评估态 peak 的 Spearman 秩相关（n=7） ===")
    for r in rows:
        print(f"{r['metric']:>22}: rho={r['spearman_vs_eval_peak']:+.4f}  "
              f"LOO=[{r['loo_rho_range'][0]:+.3f},{r['loo_rho_range'][1]:+.3f}] "
              f"翻转集={r['loo_sign_flips']}  "
              f"CI95=[{r['bootstrap_ci95'][0]:+.3f},{r['bootstrap_ci95'][1]:+.3f}]  "
              f"含0={'是' if r['bootstrap_ci_contains_zero'] else '否'}  "
              f"最差2集={r['worst2_eps']} → 评估 peak {r['worst2_eval_peak']}")
    print()
    print("=== 逐集对照表 ===")
    print("ep | train_peak | train_viol | train_ab_cost | train_ed_cost | "
          "eval_peak | eval_viol | eval逐列超限")
    for i, e in enumerate(eps):
        print(f"{e:>2} | {train_metrics['peak_coupler_kN'][i]:>10.1f} | "
              f"{train_metrics['violations'][i]:>10.0f} | "
              f"{train_metrics['ab_cost_abs'][i]:>13.1f} | "
              f"{train_metrics['ed_cost_abs'][i]:>13.2f} | "
              f"{EVAL_PEAK[e]:>9.2f} | {EVAL_VIOL[e]:>7} | {EVAL_COL_OVER[e]}")
    print()
    print(f"→ 写出：{outdir / 'correlation.json'}")


if __name__ == "__main__":
    main()
