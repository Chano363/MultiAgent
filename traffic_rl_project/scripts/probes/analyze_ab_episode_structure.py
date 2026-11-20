"""AB 事件结构分析：解释"逐列 AB 派生阈值"为何在不同 ckpt 上效果反号。

为什么需要这个工具（2026-11-21，诊断 §19.38）：
    ADR-082 的逐列 AB 派生阈值在 ep6 上把 peak 降了 21.7%，在 ep2 上反而升了
    6.5%、车钩超限 +196%。原先只记录了读数（§19.35.7 标为"未解释观测"），
    没查机理。本脚本从探针产物（trajectory.npz）里把 AB 的**事件结构**拆开，
    给出可复算的机理证据。

核心量（全部来自逐步记录，零重跑、零机时）：
    ab_exec  : (T, n_col) 每步每列的 AB 执行指令幅值（-0.4 强 / -0.2 弱 / 0 无）
    head_speed_kmh : (T, n_col) 每列头车速度
    ed_level : (T, n_col) 每列级位 n_k（AB 派生阈值的判定标量）

三个关键事实（本脚本每次运行都会重算并打印）：
    ① AB 段一律终止于 **56.0 km/h**（ADR-075 的 AB 释放速度门）——147 段样本中
       93.2% 精确命中 [55.5, 56.5] 区间。
    ② 因此 AB 段的时长 = "触发时车速 → 56 km/h"的减速过程时长；阈值抬高把
       触发点推迟到**更高车速** ⇒ 每段要刹掉的速度区间更大。
    ③ `p_ab_applied` 是 **AB 状态机占据率**，不是请求率。ep2 上触发次数降了
       85%（15139 → 2285），占据率反而从 0.307 升到 0.452 ⇒ 尾列的 AB 从
       "碎片化多次短刹"变成"少数几次长刹"⇒ 与前列的速度差/相位差被拉大
       ⇒ 车钩超限暴涨。

用法：
    python scripts/probes/analyze_ab_episode_structure.py \
        outputs/results/diagnostics/adr082_crossckpt_ep2_base \
        outputs/results/diagnostics/adr082_crossckpt_ep2_bias_n
    # 阈值按变体名推断：base → 全列 0.5；bias_n → 领航 0.5 / 后列 0.9
    # 也可用 --lead-thr/--foll-thr 显式指定。
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np

RELEASE_GATE_KMH = 56.0   # ADR-075 AB 释放速度门（目标释放点）
GATE_TOL_KMH = 0.5        # 命中判定的容差


def episodes(mask: np.ndarray) -> list[tuple[int, int]]:
    """返回 (起始下标, 长度) 列表——mask 中每一段连续 True。"""
    out: list[tuple[int, int]] = []
    start = None
    for i, v in enumerate(mask):
        if v and start is None:
            start = i
        elif not v and start is not None:
            out.append((start, i - start))
            start = None
    if start is not None:
        out.append((start, len(mask) - start))
    return out


def analyze(tag: str, path: Path, lead_thr: float, foll_thr: float) -> dict:
    z = np.load(path / "trajectory.npz")
    ab = z["ab_exec"]
    sp = z["head_speed_kmh"]
    ed = z["ed_level"]
    on = ab < 0.0
    T, n_col = on.shape
    thr = [lead_thr] + [foll_thr] * (n_col - 1)

    per_col = []
    for c in range(n_col):
        eps = episodes(on[:, c])
        durs = [d for _, d in eps]
        prev_on = np.concatenate([[False], on[:-1, c]])
        # 触发机会：级位越阈且上一拍未在 AB（近似"请求"）
        trig = int(((ed[:, c] >= thr[c]) & (~prev_on)).sum())
        end_speeds = []
        start_speeds = []
        for s, d in eps:
            end_speeds.append(float(sp[min(s + d, T - 1), c]))
            start_speeds.append(float(sp[max(s - 1, 0), c]))
        per_col.append({
            "col": c,
            "thr": thr[c],
            "applied_rate": round(float(on[:, c].mean()), 4),
            "episodes": len(eps),
            "ep_mean_steps": int(np.mean(durs)) if durs else 0,
            "ep_max_steps": int(max(durs)) if durs else 0,
            "trigger_opportunities": trig,
            "mean_ed": round(float(ed[:, c].mean()), 4),
            "start_speeds_kmh": [round(x, 1) for x in start_speeds],
            "end_speeds_kmh": [round(x, 2) for x in end_speeds],
        })

    all_end = [s for c in per_col for s in c["end_speeds_kmh"]]
    hit = sum(1 for e in all_end if abs(e - RELEASE_GATE_KMH) <= GATE_TOL_KMH)
    res = {
        "tag": tag,
        "path": str(path),
        "steps": int(T),
        "lead_thr": lead_thr,
        "follower_thr": foll_thr,
        "per_col": per_col,
        "release_gate": {
            "gate_kmh": RELEASE_GATE_KMH,
            "episodes": len(all_end),
            "hit_rate": round(hit / len(all_end), 4) if all_end else None,
        },
    }
    rp = path / "result.json"
    if rp.exists():
        r = json.loads(rp.read_text(encoding="utf-8"))
        res["headline"] = {
            "peak_kN": r.get("peak_coupler_kN"),
            "viol_total": r.get("viol_steps_total"),
            "lead_share": r.get("ab_alloc_lead_share"),
            "p_ab_applied": r.get("p_ab_applied_per_agent"),
        }
    return res


def _infer_thresholds(tag: str, lead: float | None, foll: float | None):
    if lead is not None and foll is not None:
        return lead, foll
    # bias_* 变体：只压后列；base：全列默认 0.5
    if "_bias" in tag:
        return (0.5 if lead is None else lead), (0.90 if foll is None else foll)
    return (0.5 if lead is None else lead), (0.5 if foll is None else foll)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("dirs", nargs="+", help="探针产物目录（含 result.json + trajectory.npz）")
    ap.add_argument("--lead-thr", type=float, default=None)
    ap.add_argument("--foll-thr", type=float, default=None)
    ap.add_argument("--json-out", default=None)
    args = ap.parse_args()

    out = []
    for d in args.dirs:
        p = Path(d)
        tag = p.name
        lead, foll = _infer_thresholds(tag, args.lead_thr, args.foll_thr)
        res = analyze(tag, p, lead, foll)
        out.append(res)
        print("=" * 78)
        print(f"{tag}  steps={res['steps']}  lead_thr={lead}  foll_thr={foll}")
        if "headline" in res:
            h = res["headline"]
            print(f"  peak={h['peak_kN']} kN  viol={h['viol_total']}  lead_share={h['lead_share']}")
        for c in res["per_col"]:
            print(
                f"  col{c['col']} thr={c['thr']:.2f} applied={c['applied_rate']:.4f} "
                f"eps={c['episodes']} dur(mean/max)={c['ep_mean_steps']}/{c['ep_max_steps']} "
                f"trig={c['trigger_opportunities']} mean_ed={c['mean_ed']}"
            )
            print(f"       start_kmh={c['start_speeds_kmh']}")
            print(f"       end_kmh  ={c['end_speeds_kmh']}")
        g = res["release_gate"]
        print(f"  AB 释放速度门 {g['gate_kmh']} km/h 命中 {g['hit_rate']}  ({g['episodes']} 段)")

    if args.json_out:
        Path(args.json_out).write_text(
            json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        print(f"\njson -> {args.json_out}")


if __name__ == "__main__":
    main()
