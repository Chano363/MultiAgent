"""判决性分析（§19.49，**零机时零成本**）：**主指标口径的跨机差异幅度**。

为什么现在能做这件事（§19.48 之后的缺口）：
    §19.48 实测出"1 ULP 扰动 ⇒ 车钩峰值漂移 −14.9%"，但那是**受控扰动**。
    真正的**跨机差异**另有现成的**配对实测**：同一 ckpt、同一参数、同一份代码，
    在**云端机**与**本地机**各跑一次整程确定性快评 ⇒ 两读数之差 = 跨机差异的
    **真实幅度**（含浮点实现差异 + 一切未排除因素），**不需要任何新机时**。
    §19.42 已记录：ep2 差 0.5%、ep4 差 3.2%、ep6 差 **17.7%**（峰值口径）——
    **但那三个数字只覆盖峰值口径**，主指标口径（列距 / 速度带）**从未做过配对比较**。

    而 §19.47 的核心判决（"`term_speed_band_sum` 是主指标口径唯一稳定同向信号"）
    **完全建立在评估态主指标读数上** ⇒ 必须知道这些读数**跨机漂移多大**。

本工具做法：
    输入：
      · 本地官方口径 ep1–ep7 产物（`outputs/results/decompose/eval_decompose_*_adr083_official_*`）
      · 云端官方口径 ep2/ep4/ep6 快评 json（W4 窗口产物）
      · §19.47 的训练期→评估态相关性结果（`primary_metric_corr.json`）
    输出：
      1. **逐集配对表**：云端 vs 本地，同一 ckpt 同参数的每个口径量的绝对差与相对差；
      2. **跨机漂移带**（每口径的最大相对差）⇒ 与 §19.47 的信号幅度对比；
      3. **判决**：主指标漂移带 ≫ / ≪ §19.47 信号幅度；
      4. **秩稳定性检验**：本地口径下的集间**排序**在云端读数下是否保持
         （这是"能不能用评估态读数挑 ckpt"的真正判据——比绝对值稳不稳更重要）。

判读规则（先定，避免事后解释）：
    · **跨机漂移带 ≥ §19.47 的信号幅度**（`speed_band_sum` 与 gapMean 相关 +0.821，
      端点秩差通常仅 1–3 位 ⇒ 换算成读数幅度约在**个位数到十几个百分点**）
      ⇒ **§19.47 的相关性结论不可用作止损判据**，须另找抗噪信号。
    · **跨机漂移带 ≪ 信号幅度** ⇒ §19.47 结论**不受跨机差异威胁**
      （注意：这**只**解除了"跨机"这一支威胁；**同机内的浮点扰动**威胁
      仍由 §19.48 的 `probe_primary_metric_sensitivity.py` 单独回答——**两者不是一回事**）。
    · **秩不稳定**（云端读数下集间排序改变）⇒ 结论只保留在**同一台机器内部**，
      任何跨窗口 / 跨机的 ckpt 挑选都须在**同一台机器**上重做快评。

⚠️ 口径纪律：
    · 本工具**不跑仿真**、**不产出任何峰值/安全判据**；它只做**跨机读数差异的度量**；
    · 云端读数与本地读数**按 §19.42 纪律不得互引为判据**，本工具正是把这种差异
      **量出来**，以支撑"不可互引"这条纪律；
    · 配对只覆盖 ep2/ep4/ep6 三个 ckpt ⇒ **n=3**，只作幅度量级判断，
      **不得**主张统计显著，也**不得**拟合漂移带随策略离常态距离的关系。
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

LOCAL_DIR = ROOT / "outputs/results/decompose"
CLOUD_DIR = ROOT / "outputs/results/formation_10kt_1plus108/w4nincrgatecaprel_w4full_20261120_cloud"

# 口径量 → (本地键, 云端键, 单位, 方向说明)
#   方向说明："越小越好" / "越大越好"（仅用于秩稳定性方向，不做优劣判断）
METRICS = [
    ("peak_coupler_kN", "peak_coupler_kN", "kN", "越小越好", "工程口径"),
    ("viol", "viol", "步", "越小越好", "工程口径"),
    ("band_rate", "band_rate", "", "越大越好", "主指标口径"),
    ("gap_err_mean_abs_m", "gap_err_mean_abs_m", "m", "越小越好", "主指标口径"),
    ("gap_err_peak_abs_m", "gap_err_peak_abs_m", "m", "越小越好", "主指标口径"),
    ("gap_min_m", "gap_min_m", "m", "越大越好", "主指标口径"),
]

# §19.47 的信号幅度：speed_band_sum 与评估态主指标的相关（留一法稳定）
SIGNAL = {
    "term_speed_band_sum~gap_err_mean_abs_m": 0.821,
    "term_speed_band_sum~gap_err_peak_abs_m": 0.857,
    "term_speed_band_sum~band_rate": 0.670,
}


def _load(path: Path):
    if not path.exists():
        return None
    with path.open(encoding="utf-8") as f:
        return json.load(f)


def _local_path(ep: int) -> Path:
    return (LOCAL_DIR /
            f"eval_decompose_decompose_m1_ms31500_adr083_official_ep1_ep7_20261121_det_ep{ep}.json")


def _cloud_path(ep: int):
    """云端快评 json 与本地同目录，文件名带云端 run_tag
    （`..._w4nincrgatecaprel_w4full_20261120_det_ep<N>.json`）。"""
    hits = sorted(LOCAL_DIR.glob(f"*w4nincrgatecaprel_w4full_20261120_det_ep{ep}.json"))
    return hits[0] if hits else None


def _get(d, key):
    """取指标：产物结构 = {metadata, args, results: {decompose_M1_rl: {<指标键>}}}。

    兼容三种可能位置（顶层 / results.decompose_M1_rl / agg）。
    """
    if d is None:
        return None
    if key in d:
        return d[key]
    results = d.get("results")
    if isinstance(results, dict):
        inner = results.get("decompose_M1_rl")
        if isinstance(inner, dict) and key in inner:
            return inner[key]
        for _k, v in results.items():
            if isinstance(v, dict) and key in v:
                return v[key]
    for container in ("agg", "aggregate", "summary"):
        c = d.get(container)
        if isinstance(c, dict) and key in c:
            return c[key]
    return None


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=None)
    args = ap.parse_args()

    paired = []
    for ep in (2, 4, 6):
        loc = _load(_local_path(ep))
        cld_path = _cloud_path(ep)
        cld = _load(cld_path) if cld_path else None
        if loc is None:
            print(f"[warn] 本地 ep{ep} 产物缺失：{_local_path(ep)}")
        if cld is None:
            print(f"[warn] 云端 ep{ep} 快评产物缺失：{CLOUD_DIR}")
        row = {"ep": ep, "metrics": {}}
        for key, _ck, unit, direction, caliber in METRICS:
            lv = _get(loc, key)
            cv = _get(cld, key)
            rec = {"unit": unit, "direction": direction, "caliber": caliber,
                   "local": lv, "cloud": cv}
            if isinstance(lv, (int, float)) and isinstance(cv, (int, float)):
                rec["abs_diff"] = cv - lv
                rec["rel_diff_pct"] = ((cv - lv) / lv * 100.0) if lv else float("nan")
            row["metrics"][key] = rec
        paired.append(row)

    # ---- 跨机漂移带：每个口径的最大相对差 ----
    bands = {}
    for key, _ck, unit, direction, caliber in METRICS:
        vals = []
        for row in paired:
            rec = row["metrics"][key]
            if isinstance(rec.get("rel_diff_pct"), float):
                vals.append(abs(rec["rel_diff_pct"]))
        if vals:
            bands[key] = {
                "unit": unit, "direction": direction, "caliber": caliber,
                "abs_rel_diff_pct_per_ep": [
                    row["metrics"][key].get("rel_diff_pct") for row in paired
                ],
                "max_abs_rel_diff_pct": max(vals),
                "mean_abs_rel_diff_pct": sum(vals) / len(vals),
            }

    # ---- 秩稳定性：本地排序 vs 云端排序（同一批三个 ckpt）----
    rank_stability = {}
    for key, _ck, unit, direction, caliber in METRICS:
        loc_vals = [(row["ep"], row["metrics"][key].get("local")) for row in paired]
        cld_vals = [(row["ep"], row["metrics"][key].get("cloud")) for row in paired]
        if not all(isinstance(v, (int, float)) for _e, v in loc_vals):
            continue
        if not all(isinstance(v, (int, float)) for _e, v in cld_vals):
            continue
        # "越小越好"的量按值升序排；"越大越好"的量按值降序排
        rev = direction == "越大越好"
        loc_order = [e for e, _v in sorted(loc_vals, key=lambda t: t[1], reverse=rev)]
        cld_order = [e for e, _v in sorted(cld_vals, key=lambda t: t[1], reverse=rev)]
        rank_stability[key] = {
            "caliber": caliber,
            "local_order_best_to_worst": loc_order,
            "cloud_order_best_to_worst": cld_order,
            "stable": loc_order == cld_order,
        }

    # ---- 判决 ----
    primary_band = max(
        (bands[k]["max_abs_rel_diff_pct"] for k in bands
         if bands[k]["caliber"] == "主指标口径"),
        default=float("nan"),
    )
    eng_band = max(
        (bands[k]["max_abs_rel_diff_pct"] for k in bands
         if bands[k]["caliber"] == "工程口径"),
        default=float("nan"),
    )
    # §19.47 信号幅度的可分性当量：Spearman |rho|=0.821 在 n=7 上对应的
    # "端点秩差 1–3 位" ⇒ 用**秩稳定性**判定更硬：若集间排序在跨机下改变，
    # 则任何基于排序的结论不可跨机使用（这与绝对幅度无关）。
    unstable = [k for k, v in rank_stability.items() if not v["stable"]]
    primary_unstable = [k for k in unstable
                        if rank_stability[k]["caliber"] == "主指标口径"]

    verdict = {
        "primary_metric_cross_machine_band_pct": primary_band,
        "engineering_metric_cross_machine_band_pct": eng_band,
        "primary_metric_rank_unstable_metrics": primary_unstable,
        "verdict": None,
        "note": (
            "主指标跨机漂移带是**实测配对差**（n=3 ckpt），不是扰动实验。"
            "它只回答'跨机这一支'对 §19.47 结论的威胁；"
            "**同机内浮点扰动**那一支由 probe_primary_metric_sensitivity.py 回答，"
            "两者不可互相替代。"
        ),
    }
    if primary_unstable:
        verdict["verdict"] = (
            "主指标口径的集间**排序在跨机下改变** ⇒ §19.47 的相关性结论"
            "**不可跨机使用**；且任何基于评估态读数挑 ckpt 的动作"
            "必须在**同一台机器**上重做快评。"
        )
    else:
        verdict["verdict"] = (
            "主指标口径的集间排序在跨机下**保持**（三个配对 ckpt 上） ⇒ "
            "§19.47 的相关性结论**不受跨机差异的排序层面威胁**；"
            "绝对幅度层面的威胁由漂移带数值自行判断。"
        )

    out = {
        "paired": paired,
        "cross_machine_bands": bands,
        "rank_stability": rank_stability,
        "signal_reference_19_47": SIGNAL,
        "verdict": verdict,
        "caveats": [
            "n=3 配对 ckpt ⇒ 只作幅度量级判断，不得主张统计显著。",
            "不得据此拟合漂移带随策略离常态距离的关系（§19.42 已记 ep2/ep4/ep6 差异随漂移放大）。",
            "本工具不产出任何峰值/安全判据；云端读数与本地读数仍不得互引为判据。",
        ],
    }
    out_path = Path(args.out) if args.out else (
        ROOT / "outputs/logs/adr083_primary_metric_corr/cross_machine_band.json")
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")

    # ---- 打印 ----
    print("=== 跨机配对差（云端 vs 本地，同 ckpt 同参数）===")
    for row in paired:
        print(f"-- ep{row['ep']}")
        for key, rec in row["metrics"].items():
            if isinstance(rec.get("rel_diff_pct"), float):
                print(f"   {key:<22} 本地 {rec['local']!s:<14} 云端 {rec['cloud']!s:<14} "
                      f"Δ {rec['abs_diff']:+.4g} ({rec['rel_diff_pct']:+.2f}%)  "
                      f"[{rec['caliber']}]")
    print()
    print("=== 跨机漂移带（最大相对差）===")
    for key, b in bands.items():
        print(f"   {key:<22} max {b['max_abs_rel_diff_pct']:+.3f}%  "
              f"mean {b['mean_abs_rel_diff_pct']:+.3f}%  [{b['caliber']}]")
    print()
    print("=== 集间秩稳定性（本地 vs 云端，best→worst）===")
    for key, r in rank_stability.items():
        flag = "STABLE" if r["stable"] else "**UNSTABLE**"
        print(f"   {key:<22} local {r['local_order_best_to_worst']}  "
              f"cloud {r['cloud_order_best_to_worst']}  {flag}  [{r['caliber']}]")
    print()
    print(f"[verdict] {verdict['verdict']}")
    print(f"[wrote] {out_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
