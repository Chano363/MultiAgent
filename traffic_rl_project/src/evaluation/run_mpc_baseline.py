"""MPC 对比基线评估（Regime A，ADR-016 口径）：直接加速公平 MPC。

对齐主线的 MPC baseline 单跑：
- 剖面：shuozhou_real_53km（主表）为主，可用 --grade 换 20/35km 跨线
- 形态：mpc_dir（直接加速）/ mpc_rule（直接加速 + 规则循环制动内层兜底）
- 独立完整剖面单跑（非多段拼接）；每实验落盘 JSON（内嵌 build_metadata + 时间戳归档，不覆盖旧文件）
- 补采集：solve_times 分布（mean/p95/超时率）、级联失败代理（ATP 触发步数）、车钩力峰值/超限、间距破界

用法（在 traffic_rl_project 根目录，PYTHONPATH=项目根）：
    python src/evaluation/run_mpc_baseline.py --mode mpc_rule --grade shuozhou_real_53km --n_seed 1
    python src/evaluation/run_mpc_baseline.py --mode mpc_dir  --grade shuozhou_real_53km --n_seed 1
"""
import argparse
import json
import os
import time
from pathlib import Path

import numpy as np

from src.evaluation.evaluate_m1_m3_long import make_env, run_episode
from src.metadata import build_metadata
from src.physics_governance import official_entry_guard, official_world_config

PROJECT_ROOT = Path(__file__).resolve().parents[2]
V_MAX = 80.0 / 3.6
V_MIN = 40.0 / 3.6


def solve_time_stats(times):
    """SLSQP 求解耗时分布：mean/p95/max + 超时率（>0.5s 记超时）。"""
    if not times:
        return {"n_solves": 0}
    arr = np.asarray(times, dtype=float)
    return {
        "n_solves": int(arr.size),
        "mean_ms": float(arr.mean() * 1000),
        "p95_ms": float(np.percentile(arr, 95) * 1000),
        "max_ms": float(arr.max() * 1000),
        "timeout_rate": float((arr > 0.5).mean()),  # >0.5s 视为超时
    }


def coupler_limits(res_traj_metrics=None):
    """车钩力超限统计（>=1000kN 记一次超限）——由 run_episode 指标按需扩展。"""
    return {}


def run_baseline(mode, grade, n_seed, max_steps, blocks, block_len, horizon, gap_min):
    world_cfg = official_world_config()
    official_entry_guard(__file__)
    # 【2026-09-24】run_episode 的 while 条件是模块级 MAX_STEPS（默认 15000=23.8km 旧协议），
    # 必须同步覆盖为本次 max_steps，否则 53km 只跑一半就截断（覆盖步数 bug）。
    import src.evaluation.evaluate_m1_m3_long as ev
    ev.MAX_STEPS = max_steps
    results_all = []
    for s in range(n_seed):
        env = make_env(65 / 3.6, hierarchical=False, grade_profile=grade,
                       controller=mode, mpc_gap_min=gap_min,
                       mpc_enforce_coupler=True, blocks=blocks, block_len=block_len,
                       max_steps=max_steps)
        res = run_episode(env, None, mode, s, deterministic=True, return_traj=False)
        res["solve_times"] = solve_time_stats(env._mpc_controller.solve_times)
        res["mode"] = mode
        res["grade_profile"] = grade
        res["max_steps"] = max_steps
        res["blocks"] = blocks
        res["block_len"] = block_len
        res["horizon_blocks"] = blocks
        extra = {
            "eval_protocol": "A",
            "no_fine_tuning_declaration": "MPC 逐线重喂 grade_at + b0 在线标定（公平标定，Regime A）",
            "args": {
                "mode": mode, "grade": grade, "n_seed": n_seed,
                "max_steps": max_steps, "blocks": blocks, "block_len": block_len,
                "horizon": horizon, "gap_min": gap_min,
            },
        }
        meta = build_metadata(str(PROJECT_ROOT), case="official", world_cfg=world_cfg,
                              seed=s, entry=__file__, extra=extra)
        out = {"metadata": meta, "results": res}
        results_all.append(out)
        ts = time.strftime("%Y%m%d_%H%M%S")
        fname = f"results_mpc_baseline_{mode}_s{s}_g{grade}_H{blocks}x{block_len}_{ts}.json"
        out_dir = Path(PROJECT_ROOT) / "outputs" / "results_mpc_baseline"
        out_dir.mkdir(parents=True, exist_ok=True)
        path = out_dir / fname
        with open(path, "w", encoding="utf-8") as f:
            json.dump(out, f, ensure_ascii=False, indent=2)
        print(f"[saved] {path}")
    return results_all


def summarize(results_all, mode, grade):
    res = [r["results"] for r in results_all]
    n = len(res)
    if n == 1:
        r = res[0]
        print(f"\n[{mode} @ {grade}] 确定性评估 {n} seed")
        print(f"  reward={r['reward']:+.0f}  speed_mean={r['speed_mean']:.1f}km/h "
              f"超80={r['over']:.1f}% 低40={r['under']:.1f}%")
        print(f"  车钩力峰值={r['coupler_peak']:.0f}kN  间距min={r['gap_min']:.0f}m "
              f"间距漂移={r['gap_drift']:.0f}m")
        print(f"  ATP触发步数={r['atp_brake_steps']}  追尾步数={r['collision_steps']} "
              f"循环制动={r['cycles']}  覆盖步数={r['steps']}")
        st = r.get("solve_times", {})
        if st.get("n_solves"):
            print(f"  SLSQP: mean={st['mean_ms']:.0f}ms p95={st['p95_ms']:.0f}ms "
                  f"max={st['max_ms']:.0f}ms 超时率={st['timeout_rate']*100:.1f}% "
                  f"n={st['n_solves']}")
    else:
        def med(x): return sorted(x)[len(x) // 2]
        print(f"\n[{mode} @ {grade}] {n} seed 汇总 (mean±std)")
        for key, fmt in [("reward", "{:+.0f}"), ("speed_mean", "{:.1f}"),
                         ("over", "{:.1f}"), ("under", "{:.1f}"),
                         ("coupler_peak", "{:.0f}"), ("gap_min", "{:.0f}"),
                         ("gap_drift", "{:.0f}"), ("atp_brake_steps", "{:.0f}"),
                         ("collision_steps", "{:.0f}"), ("cycles", "{:.0f}")]:
            arr = np.array([r[key] for r in res], dtype=float)
            print(f"  {key}: {fmt.format(arr.mean())}±{fmt.format(arr.std())} "
                  f"中位={fmt.format(med(list(arr)))}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--mode", choices=["mpc_dir", "mpc_rule"], default="mpc_rule")
    ap.add_argument("--grade", default="shuozhou_real_53km")
    ap.add_argument("--n_seed", type=int, default=1)
    ap.add_argument("--max_steps", type=int, default=50000)
    ap.add_argument("--blocks", type=int, default=5)
    ap.add_argument("--block_len", type=int, default=10)
    ap.add_argument("--horizon", type=int, default=10)
    ap.add_argument("--gap_min", type=float, default=20.0)
    args = ap.parse_args()
    results = run_baseline(args.mode, args.grade, args.n_seed, args.max_steps,
                           args.blocks, args.block_len, args.horizon, args.gap_min)
    summarize(results, args.mode, args.grade)


if __name__ == "__main__":
    main()
