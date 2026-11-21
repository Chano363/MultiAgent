"""零机时探针：第 11 投候选前提②的**评估态侧**可分性判定——逐列量能否区分 ep6 与 ep7？

背景（诊断 §19.41/§19.42/§19.43）：
    第 11 投方向候选 = "训练中检测到 ep6 式动作面漂移时及时止损 / 回退到 ep4 形态"。
    §19.41 已把候选成立条件收敛为三条：
      ① 训练期新增**逐列**指标落盘（env 侧零额外仿真成本）；
      ② **先证明逐列量在评估态破线集上确有信号，且能区分 ep6 与 ep7**；
      ③ 判据以后果量为主、形态量为辅。
    前提②此前**完全未验证**（训练期逐列量需重训窗口才能拿到）。
    本探针给出**前提②的评估态侧对应物**：若"逐列量"在**评估态**都无法把
    破线集 ep6 与评估态 peak 正常的 ep7 分开，则前提②在任何口径下都不成立
    ⇒ **候选可当场否决，不必等 owner 批复重训窗口**；反之则说明前提②
    值得用一次重训窗口去验证。

判定内容（全部基于本地官方口径 ep1–ep7 的既有产物，零机时）：
    对每个逐列量（逐列 peak / 逐列超限步 / 逐列越线车·步 等），检查：
      · **方向性**：破线集 ep6 在该量上是否确为最差（或明确靠前）；
      · **可分性**：是否存在单阈值，把 ep6 与 ep7 分开（ep6 命中、ep7 不命中），
        且**不在 ep3 上误杀**（§19.40 的硬约束）——"误杀"定义为：
        该阈值下 ep3（评估态 peak 正常的集）也被判为破线；
      · **排序矛盾检查**：该量的排序是否与评估态总 peak 的排序冲突。

⚠️ 口径：本探针是**评估态**逐列量的可分性判定，**不是**训练期落盘设计，
    也**不产出任何峰值/安全判据**；结论只用于判断"前提②是否值得用一次
    重训窗口去验证"。跨机器不可互引（§19.42）。
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

# 本地官方口径 ep1–ep7 的产物（§19.41 用的同一批）
DEFAULT_GLOB = "outputs/results/decompose/eval_decompose_decompose_m1_ms31500_adr083_official_ep1_ep7_20261121_det_ep*.json"

EPISODES = [1, 2, 3, 4, 5, 6, 7]
BREAK_EP = 6      # 破线集（评估态 peak 最高）
NORMAL_EP = 7     # 评估态 peak 正常、但训练期信号最响的集（§19.41）
FALSE_POS_EP = 3  # §19.40 硬约束：不得在该集上误杀


def load_series(glob_pattern: str) -> dict:
    """读本地官方口径 ep1–ep7 产物，抽取逐列量。"""
    series = {ep: {} for ep in EPISODES}
    meta = {}
    for ep in EPISODES:
        cands = sorted(Path(ROOT).glob(glob_pattern.replace("*", f"*{ep}")))
        # 精确匹配 ep{N}.json，避免 ep1 命中 ep10 之类
        cands = [c for c in cands if c.name.endswith(f"_ep{ep}.json")]
        if not cands:
            raise FileNotFoundError(f"缺 ep{ep} 的官方口径产物（glob={glob_pattern}）")
        d = json.loads(cands[0].read_text(encoding="utf-8"))
        r = d["results"]["decompose_M1_rl"]
        meta[ep] = {
            "file": cands[0].name,
            "peak_coupler_kN": float(r["peak_coupler_kN"]),
            "train_peak_coupler_kN": [float(x) for x in r.get("train_peak_coupler_kN", [])],
            "train_coupler_viol": [float(x) for x in r.get("train_coupler_viol", [])],
            "train_overspeed_car_steps": [float(x) for x in r.get("train_overspeed_car_steps", [])],
            "train_speed_max_kmh": [float(x) for x in r.get("train_speed_max_kmh", [])],
            "viol": float(r.get("viol", 0.0)),
            "band_rate": float(r.get("band_rate", 0.0)),
        }
    return meta


def _candidates(meta: dict) -> list:
    """构造候选判据量：(名称, 取值函数, 是否为全局量的别名)。

    ⚠️ **别名标注是本探针的关键设计**：`max_col_peak_kN` ≡ 总 peak、
    `sum_col_viol_steps` ≡ 总 viol —— 它们**不是**逐列分解带来的新信息，
    只是全局量的另一种写法。若不标注，结论会误导向"必须新增逐列落盘"。
    真正携带新信息的只有**逐列分解本身**（col_i_*）与**列间离散度**（spread_*）。
    """
    cands = []
    n_col = len(meta[EPISODES[0]]["train_peak_coupler_kN"])
    for ci in range(n_col):
        cands.append((f"col{ci}_peak_kN",
                      lambda m, ci=ci: m["train_peak_coupler_kN"][ci], False))
        cands.append((f"col{ci}_viol_steps",
                      lambda m, ci=ci: m["train_coupler_viol"][ci], False))
        cands.append((f"col{ci}_overspeed_car_steps",
                      lambda m, ci=ci: m["train_overspeed_car_steps"][ci], False))
    # 派生量
    cands.append(("max_col_viol_steps",
                  lambda m: max(m["train_coupler_viol"]), False))
    cands.append(("max_col_peak_kN", lambda m: max(m["train_peak_coupler_kN"]), True))
    cands.append(("sum_col_viol_steps", lambda m: sum(m["train_coupler_viol"]), True))
    cands.append(("spread_col_peak_kN",
                  lambda m: max(m["train_peak_coupler_kN"]) - min(m["train_peak_coupler_kN"]),
                  False))
    cands.append(("spread_col_viol_steps",
                  lambda m: max(m["train_coupler_viol"]) - min(m["train_coupler_viol"]), False))
    # 【基线】全局量：用来回答"逐列分解到底带来了什么增量"
    cands.append(("GLOBAL_total_peak_kN", lambda m: m["peak_coupler_kN"], True))
    cands.append(("GLOBAL_total_viol", lambda m: m["viol"], True))
    return cands


def judge(name: str, fn, meta: dict, is_global_alias: bool = False) -> dict:
    vals = {ep: fn(meta[ep]) for ep in EPISODES}
    order = sorted(EPISODES, key=lambda e: vals[e], reverse=True)  # 代价型：越大越差
    rank_break = order.index(BREAK_EP) + 1
    rank_normal = order.index(NORMAL_EP) + 1

    # 单阈值可分性：阈值取"ep6 值"与"ep7 值"之间（若 ep6 值 > ep7 值 ⇒ 存在分离阈值）
    # 判"命中"= 值 > 阈值（代价型）。取阈值 t 使 ep6 命中、ep7 不命中：
    #   若 vals[6] > vals[7]，可取 t ∈ [vals[7], vals[6])，取中点即可。
    #   若 vals[6] <= vals[7] ⇒ 无任何阈值能同时命中 ep6 而放过 ep7。
    separable = vals[BREAK_EP] > vals[NORMAL_EP]
    fp = None
    if separable:
        t = (vals[BREAK_EP] + vals[NORMAL_EP]) / 2.0
        fp = [ep for ep in EPISODES
              if ep != BREAK_EP and vals[ep] > t]
    return {
        "metric": name,
        "is_global_alias": bool(is_global_alias),
        "values": {str(ep): vals[ep] for ep in EPISODES},
        "worst_order_desc": order,
        "rank_of_break_ep6": rank_break,
        "rank_of_normal_ep7": rank_normal,
        "break_ep6_is_worst": order[0] == BREAK_EP,
        "single_threshold_can_isolate_ep6": separable,
        "false_positive_eps_at_that_threshold": fp,
        "false_positive_includes_ep3": (fp is not None and FALSE_POS_EP in fp),
        "usable": bool(separable and fp is not None and not (FALSE_POS_EP in fp)),
    }


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--glob", default=DEFAULT_GLOB)
    ap.add_argument("--out", default=None)
    args = ap.parse_args()

    meta = load_series(args.glob)
    results = [judge(name, fn, meta, alias) for name, fn, alias in _candidates(meta)]

    usable = [r for r in results if r["usable"]]
    usable_new = [r for r in usable if not r["is_global_alias"]]
    print(f"[probe] 评估态候选量 {len(results)} 个；"
          f"单阈值可把 ep6 与 ep7 分开且不误杀 ep3 的候选：{len(usable)} 个"
          f"（其中**非全局别名**（逐列分解真正带来的新信息）：{len(usable_new)} 个）")
    print("  标记说明：G=全局量别名（无新增信息），P=逐列分解新增信息")
    for r in results:
        mark = "✔" if r["usable"] else ("~" if r["single_threshold_can_isolate_ep6"] else "✘")
        tag = "G" if r["is_global_alias"] else "P"
        print(f"  {mark} [{tag}] {r['metric']:<28} ep6排名={r['rank_of_break_ep6']} "
              f"ep7排名={r['rank_of_normal_ep7']} "
              f"可分={r['single_threshold_can_isolate_ep6']} "
              f"误杀集={r['false_positive_eps_at_that_threshold']}")

    print()
    print("[probe] 评估态总 peak 排序（参考）:")
    for ep in sorted(EPISODES, key=lambda e: -meta[e]["peak_coupler_kN"]):
        print(f"    ep{ep}: peak={meta[ep]['peak_coupler_kN']:.2f} kN")

    out = {
        "glob": args.glob,
        "break_ep": BREAK_EP,
        "normal_ep": NORMAL_EP,
        "false_positive_constraint_ep": FALSE_POS_EP,
        "n_candidates": len(results),
        "n_usable": len(usable),
        "usable_metrics": [r["metric"] for r in usable],
        "n_usable_non_global_alias": len(usable_new),
        "usable_metrics_non_global_alias": [r["metric"] for r in usable_new],
        "results": results,
        "per_episode": meta,
        "note": ("评估态逐列量可分性判定（零机时）；用于判断第 11 投候选前提②"
                 "是否值得用一次重训窗口验证；不是峰值/安全判据，跨机器不可互引。"),
    }
    out_path = Path(args.out) if args.out else (
        ROOT / "outputs/logs/adr083_percolumn_discrim/percolumn_discrim.json")
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"[probe] wrote {out_path}")


if __name__ == "__main__":
    main()
