"""零机时判定：**训练期落盘量**能否预测**评估态主指标（列距/速度带）**？

动机（诊断 §19.47 的触发点）：
    ADR-042/§1.6 定的主 claim 是**编队指标收益**——列距保持（spacing error）与
    列间速度差收敛（band），车钩力 ≤1000 kN 由安全层保证、**不作对比胜出主张**。
    但 §19.41 只对**车钩峰值**做过"训练期标量 vs 评估态"的相关性分析，
    结论是"四个代价型指标与评估 peak 秩相关全为负" ⇒ 该结论**不能外推到主指标**。
    ⇒ 本脚本把同一套分析（Spearman + 留一法 + 单阈值可分性）**对准主指标**重做一遍。

数据源（均为仓内既有产物，零新仿真、零机时零费用）：
    · 训练期（W4 云端窗口落盘，ep1–ep7）：
      `outputs/results/formation_10kt_1plus108/w4nincrgatecaprel_w4full_20261120_cloud/`
        `train_history_dec_ad1_cp_seed0.csv`（11 列，含 **gap_err_mean / gap_min_m**）
        `train_reward_terms_dec_ad1_cp_seed0.csv`（9 分量，含 gap_eff / gap_danger）
    · 评估态（本地官方口径整程快评，ep1–ep7）：
      `outputs/results/decompose/eval_decompose_*_adr083_official_*_ep{N}.json`
        主指标 = `gap_err_mean_abs_m` / `gap_err_peak_abs_m` / `gap_min_m` / `band_rate`

⚠️ 口径纪律（沿用 §19.41，并补充第 4 条）：
    1. 训练期 rollout 与评估态快评**步数不同**（训练期每集 n_steps ≈ 9.2e4，
       评估态 = 31500 整程）⇒ **绝对值不可跨侧比大小**，只做**同侧跨集**的秩比较。
    2. 跨机器绝对值不可互引（§19.42）：评估侧读数取**本地官方口径**。
    3. n = 7 ⇒ 只作**方向性判决**，**不得主张统计显著**；须报留一法（LOO）稳定性。
    4. **本脚本只回答"训练期量能否当在线止损信号"**，不回答"哪个策略更好"，
       也**不产出任何峰值/安全判据**。
"""
from __future__ import annotations

import csv
import glob
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

TRAIN_DIR = ROOT / "outputs/results/formation_10kt_1plus108/w4nincrgatecaprel_w4full_20261120_cloud"
TRAIN_HIST = TRAIN_DIR / "train_history_dec_ad1_cp_seed0.csv"
TRAIN_TERMS = TRAIN_DIR / "train_reward_terms_dec_ad1_cp_seed0.csv"
EVAL_GLOB = "outputs/results/decompose/eval_decompose_*_adr083_official_*_ep{}.json"
EPISODES = [1, 2, 3, 4, 5, 6, 7]


# ------------------------------------------------------------------ 统计

def rank(xs):
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


def spearman(a, b):
    if len(a) != len(b) or len(a) < 3:
        return None
    ra, rb = rank(a), rank(b)
    n = len(a)
    d2 = sum((x - y) ** 2 for x, y in zip(ra, rb))
    if n < 2:
        return None
    return 1.0 - 6.0 * d2 / (n * (n * n - 1))


def loo_spearman(a, b):
    """留一法：逐集剔除后的 rho 列表（看符号是否稳定）。"""
    out = []
    for k in range(len(a)):
        idx = [i for i in range(len(a)) if i != k]
        r = spearman([a[i] for i in idx], [b[i] for i in idx])
        if r is not None:
            out.append(r)
    return out


# ------------------------------------------------------------------ 读入

def load_train():
    rows = list(csv.DictReader(TRAIN_HIST.open(encoding="utf-8")))
    tr = {}
    for r in rows:
        ep = int(r["episode"])
        if ep in EPISODES:
            tr[ep] = r
    if len(tr) != len(EPISODES):
        raise FileNotFoundError(f"训练期落盘缺集（{sorted(tr)}）")
    # 奖励分量（每集一个 sum；按 episode 对齐）
    terms = {}
    if TRAIN_TERMS.exists():
        for r in csv.DictReader(TRAIN_TERMS.open(encoding="utf-8")):
            ep = int(r["episode"])
            if ep in EPISODES:
                terms[ep] = r
    return tr, terms


def load_eval():
    ev = {}
    for ep in EPISODES:
        cands = [Path(p) for p in glob.glob(str(ROOT / EVAL_GLOB.format(ep)))
                 if p.endswith(f"_ep{ep}.json")]
        if not cands:
            raise FileNotFoundError(f"缺评估态 ep{ep} 官方口径产物")
        d = json.loads(cands[0].read_text(encoding="utf-8"))
        ev[ep] = d["results"]["decompose_M1_rl"]
    return ev


# ------------------------------------------------------------------ 分析

def build_vectors(tr, terms, ev):
    """训练期候选量 → 评估态主指标。"""
    eps = EPISODES

    def T(col):
        return [float(tr[ep][col]) for ep in eps]

    def TERM(col):
        if not terms or any(ep not in terms for ep in eps):
            return None
        return [float(terms[ep][col]) for ep in eps]

    def V(col):
        return [float(ev[ep][col]) for ep in eps]

    train_cands = {
        "gap_err_mean": T("gap_err_mean"),
        "gap_min_m": T("gap_min_m"),
        "peak_coupler_kN": T("peak_coupler_kN"),
        "violations": T("violations"),
        "overspeed_car_steps": T("overspeed_car_steps"),
        "speed_mean_kmh": T("speed_mean_kmh"),
        "reward": T("reward"),
    }
    for name, col in (("gap_eff_sum", "gap_eff_sum"),
                      ("gap_danger_sum", "gap_danger_sum"),
                      ("coupler_peak_sum", "coupler_peak_sum"),
                      ("speed_band_sum", "speed_band_sum")):
        v = TERM(col)
        if v is not None:
            train_cands[f"term_{name}"] = v

    eval_main = {
        "gap_err_mean_abs_m": V("gap_err_mean_abs_m"),
        "gap_err_peak_abs_m": V("gap_err_peak_abs_m"),
        "gap_min_m": V("gap_min_m"),
        "band_rate": V("band_rate"),
    }
    # 工程口径对照组（非主指标）：车钩峰值 / 超限步 —— 用于回答
    # "谁能把 peak 最差集 ep6 挑出来"（在线止损候选的原目标）
    eval_eng = {
        "peak_coupler_kN": V("peak_coupler_kN"),
        "viol": V("viol"),
    }
    return train_cands, eval_main, eval_eng


def analyze(train_cands, eval_main, eval_eng=None):
    corr = {}
    for tn, tv in train_cands.items():
        for vn, vv in list(eval_main.items()) + list((eval_eng or {}).items()):
            r = spearman(tv, vv)
            loo = loo_spearman(tv, vv)
            corr[f"{tn}~{vn}"] = {
                "rho": None if r is None else round(r, 4),
                "loo_min": None if not loo else round(min(loo), 4),
                "loo_max": None if not loo else round(max(loo), 4),
                "loo_sign_stable": None if not loo else (all(x > 0 for x in loo)
                                                       or all(x < 0 for x in loo)),
                "n": len(tv),
            }
    return corr


def best_threshold(values, eps, target_ep, false_pos_eps, bigger_is_worse=True):
    """单阈值可分性：把某个集（target_ep）判为"差"，且不在 false_pos_eps 上误杀。"""
    uniq = sorted(set(values))
    best = None
    for t in uniq:
        hit = {ep for ep, v in zip(eps, values)
               if (v > t if bigger_is_worse else v < t)}
        if target_ep not in hit:
            continue
        fp = sorted(ep for ep in hit if ep in false_pos_eps)
        cand = (len(fp), len(hit), -t, t, sorted(hit), fp)
        if best is None or cand[:3] < best[:3]:
            best = cand
    if best is None:
        return None
    return {"threshold": best[3], "hit_eps": best[4], "false_positive_eps": best[5]}


def main() -> int:
    tr, terms = load_train()
    ev = load_eval()
    train_cands, eval_main, eval_eng = build_vectors(tr, terms, ev)
    corr = analyze(train_cands, eval_main, eval_eng)

    print("=== 逐集对照（训练期 → 评估态主指标）===")
    hdr = ("ep", "tr_gapMean", "tr_gapMin", "tr_peak", "ev_gapMean", "ev_gapPeak",
           "ev_gapMin", "ev_band", "ev_peak")
    print("{:<3}{:>11}{:>10}{:>9}{:>11}{:>11}{:>10}{:>10}{:>9}".format(*hdr))
    for ep in EPISODES:
        print("{:<3}{:>11.1f}{:>10.1f}{:>9.1f}{:>11.1f}{:>11.1f}{:>10.1f}{:>10.4f}{:>9.1f}".format(
            ep, float(tr[ep]["gap_err_mean"]), float(tr[ep]["gap_min_m"]),
            float(tr[ep]["peak_coupler_kN"]),
            float(ev[ep]["gap_err_mean_abs_m"]), float(ev[ep]["gap_err_peak_abs_m"]),
            float(ev[ep]["gap_min_m"]), float(ev[ep]["band_rate"]),
            float(ev[ep]["peak_coupler_kN"])))

    print("\n=== Spearman：训练期量 ~ 评估态主指标（n=7，含留一法稳定性）===")
    for k, v in corr.items():
        if v["rho"] is None:
            continue
        mark = ""
        if abs(v["rho"]) >= 0.5:
            mark = "  ←"
        print(f"  {k:<52} rho={v['rho']:+.3f}  LOO[{v['loo_min']:+.3f},{v['loo_max']:+.3f}] "
              f"符号稳定={v['loo_sign_stable']}{mark}")

    print("\n=== 单阈值可分性（能否把评估态最差集挑出来）===")
    # 评估态 gap_err_mean_abs_m 最大者 = 最差集；gap_err_peak_abs_m 最大者同理
    for vname, vv in eval_main.items():
        worst_ep = EPISODES[max(range(len(vv)), key=lambda i: vv[i])]
        best_ep = EPISODES[min(range(len(vv)), key=lambda i: vv[i])]
        print(f"  [{vname}] 最差集 = ep{worst_ep}（{max(vv):.3f}），最好集 = ep{best_ep}（{min(vv):.3f}）")
        for tn, tv in train_cands.items():
            res = best_threshold(tv, EPISODES, worst_ep, [best_ep])
            if res:
                print(f"     {tn:<28} thr={res['threshold']:.4g} hit={res['hit_eps']} "
                      f"误杀={res['false_positive_eps']}")

    out = {
        "train_source": str(TRAIN_HIST.relative_to(ROOT)),
        "eval_source": EVAL_GLOB,
        "episodes": EPISODES,
        "table": {
            str(ep): {
                "train_gap_err_mean": float(tr[ep]["gap_err_mean"]),
                "train_gap_min_m": float(tr[ep]["gap_min_m"]),
                "train_peak_kN": float(tr[ep]["peak_coupler_kN"]),
                "eval_gap_err_mean_abs_m": float(ev[ep]["gap_err_mean_abs_m"]),
                "eval_gap_err_peak_abs_m": float(ev[ep]["gap_err_peak_abs_m"]),
                "eval_gap_min_m": float(ev[ep]["gap_min_m"]),
                "eval_band_rate": float(ev[ep]["band_rate"]),
                "eval_peak_kN": float(ev[ep]["peak_coupler_kN"]),
            } for ep in EPISODES
        },
        "spearman": corr,
        "eval_main_metrics": list(eval_main.keys()),
        "eval_eng_metrics": list(eval_eng.keys()),
        "caveats": [
            "n=7 ⇒ 方向性判决，不得主张统计显著",
            "训练期与评估态步数不同（~9.2e4 vs 31500）⇒ 绝对值不可跨侧比大小",
            "跨机器绝对值不可互引（§19.42）：评估侧取本地官方口径",
            "只回答'训练期量能否当在线止损信号'，不产出峰值/安全判据",
        ],
    }
    outp = ROOT / "outputs/logs/adr083_primary_metric_corr/primary_metric_corr.json"
    outp.parent.mkdir(parents=True, exist_ok=True)
    outp.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n[写出] {outp}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
