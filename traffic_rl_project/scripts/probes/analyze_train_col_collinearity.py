"""第 11 投候选前提②的**训练期同向性**判定工具（窗口数据到位后一条命令出结论）。

背景（诊断 §19.41 / §19.44 / §19.45）：
    第 11 投方向候选 = "训练中检测到 ep6 式动作面漂移时及时止损 / 回退到 ep4 形态"。
    §19.44 已证：逐列车钩力量在**评估态侧**确有信号（`col1_peak_kN` /
    `col1_viol_steps` / `spread_col_peak_kN` 能把破线集 ep6 排第 1、ep7 排第 3–4、
    误杀集为空），但**评估态侧逐列分解相对总 peak 无可用增量** ⇒ 真正的未知项是
    **训练期的同向性**：训练期落盘的逐列量是否与评估态同口径量**同向**、且能区分 ep6 与 ep7。
    §19.45 已把训练期逐列落盘通道建好（纯观测、零物理改动）⇒ 本工具是**判据执行器**：
    一次带落盘的重训窗口产出 `train_history_*.json` 后，直接跑它即可出判决。

输入：
    · 训练侧：`train_history_{tag}.json`（§19.45 新增键 `col_peak_coupler_kN` /
      `col_violations`，形状 [n_ep][n_cols]）；
    · 评估侧：本地官方口径 ep1–ep7 产物（与 §19.44 同一批，glob 传入）。

输出：
    · 逐集对照表（训练期逐列 peak/超限 ↔ 评估态总 peak / 评估态逐列 peak）；
    · Spearman 秩相关（训练期逐列量 vs 评估态量；**n 小时不主张显著性**）；
    · 单阈值可分性判定：命中破线集 ep6？放过 ep7？误杀集（**含 ep3 硬约束**）？
    · 列身份 vs 离散度：是否与 §19.42「形态量跨机器会翻转」相容
      （⇒ 只建议使用**离散度/后果量**型判据，不建议绑死某一列）。

⚠️ 口径纪律：
    · 本工具**只做"训练期 ↔ 评估态"的相关性/可分性判定**，**不产出任何峰值或安全判据**；
    · 训练期量与评估态量必须**同口径**（断面力 max|abs|、同一 coupler_force_limit_n），
      本工具在读入时**校验**这一点，不一致即报错退出；
    · 跨机器读数不可互引（§19.42）；n 很小（默认 7 集）⇒ **不得主张统计显著**。

用法：
    python scripts/probes/analyze_train_col_collinearity.py \
        --train-history outputs/results/<run>/train_history_<tag>.json \
        --eval-glob "outputs/results/decompose/eval_decompose_*_ep*.json"
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

DEFAULT_EVAL_GLOB = ("outputs/results/decompose/"
                     "eval_decompose_decompose_m1_ms31500_adr083_official_ep1_ep7_20261121_det_ep*.json")
EPISODES = [1, 2, 3, 4, 5, 6, 7]
BREAK_EP = 6      # 破线集（评估态 peak 最高）
NORMAL_EP = 7     # 评估态 peak 正常、但训练期信号最响的集（§19.41）
FALSE_POS_EP = 3  # §19.40 硬约束：不得在该集上误杀


# ------------------------------------------------------------------ 基础统计

def _rank(x):
    """平均秩（并列取均值）。"""
    order = sorted(range(len(x)), key=lambda i: x[i])
    ranks = [0.0] * len(x)
    i = 0
    while i < len(order):
        j = i
        while j + 1 < len(order) and x[order[j + 1]] == x[order[i]]:
            j += 1
        avg = (i + j) / 2.0 + 1.0
        for k in range(i, j + 1):
            ranks[order[k]] = avg
        i = j + 1
    return ranks


def spearman(a, b):
    """Spearman 秩相关；任一序列为常量 ⇒ 返回 None（无区分度）。"""
    if len(a) != len(b) or len(a) < 3:
        return None
    ra, rb = _rank(a), _rank(b)
    ma, mb = sum(ra) / len(ra), sum(rb) / len(rb)
    num = sum((x - ma) * (y - mb) for x, y in zip(ra, rb))
    den = (sum((x - ma) ** 2 for x in ra) ** 0.5 *
           sum((y - mb) ** 2 for y in rb) ** 0.5)
    if den == 0:
        return None
    return num / den


# ------------------------------------------------------------------ 读入

def load_eval(glob_pattern: str) -> dict:
    """读评估侧官方口径产物（§19.44 同一批）。"""
    series = {}
    for ep in EPISODES:
        cands = [c for c in sorted(Path(ROOT).glob(glob_pattern))
                 if c.name.endswith(f"_ep{ep}.json")]
        if not cands:
            raise FileNotFoundError(f"缺 ep{ep} 的评估态产物（glob={glob_pattern}）")
        d = json.loads(cands[0].read_text(encoding="utf-8"))
        r = d["results"]["decompose_M1_rl"]
        series[ep] = {
            "file": cands[0].name,
            "peak_coupler_kN": float(r["peak_coupler_kN"]),
            "train_peak_coupler_kN": [float(x) for x in r.get("train_peak_coupler_kN", [])],
            "train_coupler_viol": [float(x) for x in r.get("train_coupler_viol", [])],
        }
    return series


def load_train(history_path: Path, n_eps: int) -> dict:
    """读训练期落盘（含 §19.45 新增的逐列两键），并**校验口径与形状**。"""
    if not history_path.exists():
        raise FileNotFoundError(
            f"训练期逐列落盘不存在：{history_path}\n"
            "⇒ 需先跑一次**带逐列落盘**的训练窗口（§19.45 通道已就位）；"
            "本工具在窗口数据到位前无法出判决（属预期，不是故障）。")
    h = json.loads(history_path.read_text(encoding="utf-8"))
    for k in ("col_peak_coupler_kN", "col_violations"):
        if k not in h:
            raise KeyError(
                f"训练期落盘缺键 {k} ⇒ 该窗口未带 §19.45 逐列通道（或 ckpt/产物版本过旧）")
    cp = h["col_peak_coupler_kN"]
    cv = h["col_violations"]
    if len(cp) != len(cv):
        raise ValueError(f"逐列两键长度不一致：{len(cp)} vs {len(cv)}")
    n_cols = len(cp[0])
    for row in cp + cv:
        if len(row) != n_cols:
            raise ValueError(f"逐列行长不一致：期望 {n_cols}，实际 {len(row)}")
    if n_cols != 3:
        raise ValueError(f"期望 3 列，实际 {n_cols}")
    if len(cp) < n_eps:
        raise ValueError(f"训练期集数 {len(cp)} < 需要的 {n_eps}")
    return {
        "file": str(history_path),
        "col_peak_kN": [[float(x) for x in row] for row in cp[:n_eps]],
        "col_viol": [[float(x) for x in row] for row in cv[:n_eps]],
    }


# ------------------------------------------------------------------ 判据

def _best_single_threshold(values, break_ep, normal_ep, false_pos_ep):
    """代价型单阈值（越大越差）：命中 break_ep、放过 normal_ep、误杀集尽量小。"""
    eps = sorted(values)
    cands = []
    for t in eps:
        hit = {ep for ep, v in values.items() if v > t}
        if break_ep not in hit or normal_ep in hit:
            continue
        fp = sorted(ep for ep in hit if ep == false_pos_ep)
        cands.append((t, sorted(hit), fp))
    if not cands:
        return None
    # 优先：误杀集小 → 命中集小 → 阈值大
    cands.sort(key=lambda c: (len(c[2]), len(c[1]), -c[0]))
    return cands[0]


def analyze(train: dict, ev: dict) -> dict:
    n_eps = len(EPISODES)
    rows = []
    for i, ep in enumerate(EPISODES):
        rows.append({
            "ep": ep,
            "train_col_peak_kN": train["col_peak_kN"][i],
            "train_col_viol": train["col_viol"][i],
            "train_total_peak_kN": max(train["col_peak_kN"][i]),
            "train_spread_peak_kN": max(train["col_peak_kN"][i]) - min(train["col_peak_kN"][i]),
            "eval_peak_kN": ev[ep]["peak_coupler_kN"],
            "eval_col_peak_kN": ev[ep]["train_peak_coupler_kN"],
        })

    eval_total = [r["eval_peak_kN"] for r in rows]
    eval_col1 = [r["eval_col_peak_kN"][1] if len(r["eval_col_peak_kN"]) > 1 else float("nan")
                 for r in rows]
    eval_spread = [(max(r["eval_col_peak_kN"]) - min(r["eval_col_peak_kN"]))
                   if r["eval_col_peak_kN"] else float("nan") for r in rows]

    targets = {
        "eval_total_peak": eval_total,
        "eval_col1_peak": eval_col1,
        "eval_spread_peak": eval_spread,
    }

    cand = {}
    for ci in range(3):
        cand[f"train_col{ci}_peak_kN"] = [r["train_col_peak_kN"][ci] for r in rows]
        cand[f"train_col{ci}_viol"] = [r["train_col_viol"][ci] for r in rows]
    cand["train_total_peak_kN"] = [r["train_total_peak_kN"] for r in rows]
    cand["train_spread_peak_kN"] = [r["train_spread_peak_kN"] for r in rows]

    corr = {}
    for cname, cvec in cand.items():
        for tname, tvec in targets.items():
            corr[f"{cname}~{tname}"] = spearman(cvec, tvec)

    # 单阈值可分性（代价型）：训练期量 > t ⇒ 判"破线"
    sep = {}
    for cname, cvec in cand.items():
        vmap = {r["ep"]: v for r, v in zip(rows, cvec)}
        best = _best_single_threshold(vmap, BREAK_EP, NORMAL_EP, FALSE_POS_EP)
        sep[cname] = None if best is None else {
            "threshold": best[0], "hit_eps": best[1], "false_positive_eps": best[2],
        }

    return {
        "episodes": EPISODES,
        "break_ep": BREAK_EP, "normal_ep": NORMAL_EP, "false_positive_eps": FALSE_POS_EP,
        "rows": rows,
        "spearman": corr,
        "separability": sep,
        "caveats": [
            f"n={n_eps} ⇒ 不得主张统计显著（§19.41 纪律）",
            "训练期↔评估态相关**不能**替代因果；形态量跨机器会翻转（§19.42）",
            "本工具不产出任何峰值/安全判据",
        ],
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--train-history", required=True,
                    help="带逐列落盘的 train_history_*.json（§19.45 通道）")
    ap.add_argument("--eval-glob", default=DEFAULT_EVAL_GLOB)
    ap.add_argument("--out", default=None, help="JSON 产物路径（默认打印摘要）")
    args = ap.parse_args()

    ev = load_eval(args.eval_glob)
    train = load_train(Path(args.train_history), len(EPISODES))
    res = analyze(train, ev)

    print(f"[训练期逐列源] {train['file']}")
    print(f"[评估态源]      {len(ev)} 集")
    print("\n=== 逐集对照 ===")
    for r in res["rows"]:
        print(f"ep{r['ep']}: 训练期逐列 peak {[round(x, 1) for x in r['train_col_peak_kN']]} kN "
              f"| spread {r['train_spread_peak_kN']:.1f} "
              f"|| 评估态总 peak {r['eval_peak_kN']:.2f} kN "
              f"| 评估态逐列 {[round(x, 1) for x in r['eval_col_peak_kN']]}")
    print("\n=== Spearman 秩相关（训练期量 ~ 评估态量）===")
    for k, v in res["spearman"].items():
        if v is not None and abs(v) >= 0.3:
            print(f"  {k}: {v:+.3f}")
    print("\n=== 单阈值可分性（命中 ep6 / 放过 ep7 / 不误杀 ep3）===")
    for k, v in res["separability"].items():
        if v is None:
            print(f"  {k}: 无满足条件的阈值")
        else:
            print(f"  {k}: thr={v['threshold']:.4g} hit={v['hit_eps']} 误杀={v['false_positive_eps']}")
    print("\n⚠️ " + " | ".join(res["caveats"]))

    if args.out:
        outp = Path(args.out)
        outp.parent.mkdir(parents=True, exist_ok=True)
        outp.write_text(json.dumps(res, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"\n[写出] {outp}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
