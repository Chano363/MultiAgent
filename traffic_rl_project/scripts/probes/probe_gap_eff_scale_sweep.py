"""干预面③ 的**权重标定**（零机时，一次整程拿到所有候选尺度的量级）。

**要回答的问题**：把 `gap_eff_scale_m` 从 150 提到 900–1200 m（§19.66 量纲分析）后，
**间距效率项在总奖励面里占多大比例**？会不会把"看不见散开"变成"只看散开"？

**方法（一次整程、离线重算所有候选尺度 ⇒ 零额外机时）**
    用第 9 投 ep6 ckpt 跑**整程**（评估口径，同机同参），逐步记录：
      · `info['gap_err_mean']`（= 列距相对 `d_eff` 的误差均值）
      · `env.reward_term_sums`（各奖励分量的整程累计量级）
    然后**离线**对每个候选尺度 s 重算间距项总量
        Σ_t  GAP_EFF_W · n_pairs · max(0, 1 − x_t/s)
    并与其它分量的量级并列 ⇒ 给出**权重标定建议**（该占多少比例算健康）。

⚠️ **口径与近似**
    · `gap_err_mean` 是**各列对误差的均值**（不是逐对值）⇒ 重算的间距项总量是**近似**
      （用于**量级标定**，不作为判据）；
    · 本探针跑在**本地机** ⇒ 绝对量级不可搬到云端（跨机漂移，§19.49）⇒ 但**比例关系**
      是同机同参内部的对比 ⇒ 可用于标定；最终权重仍须在**云端**窗口复核；
    · **不产出任何峰值/安全判据**。

用法（conda env traffic_rl，项目根）：
    python scripts/probes/probe_gap_eff_scale_sweep.py
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

import numpy as np  # noqa: E402

DEFAULT_EXPERIMENT = ("configs/experiments/"
                      "formation_ed_ab_3train_1plus108_nincrgatecaprel.yaml")
DEFAULT_CKPT = ("outputs/checkpoints/formation_10kt_1plus108/"
                "w4nincrgatecaprel_w4full_20261120_cloud/"
                "mappo_fleet_last_ep6_dec_ad1_cp_seed0_seed0.pt")
CANDIDATE_S = (150.0, 600.0, 900.0, 1200.0, 2000.0)
D_EFF_M = 141.0
GAP_EFF_W = 3.0


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--experiment", default=DEFAULT_EXPERIMENT)
    ap.add_argument("--checkpoint", default=DEFAULT_CKPT)
    ap.add_argument("--max-steps", type=int, default=31500)
    ap.add_argument("--decision-interval", type=int, default=10)
    ap.add_argument("--grade", default="shuozhou_ningwuxi_beidaniu_49km")
    ap.add_argument("--out", default=str(ROOT / "outputs/logs/adr083_float_probe"
                                         / "gap_eff_scale_sweep.json"))
    args = ap.parse_args()

    from src.trainer.config_schema import parse_experiment_yaml
    from src.environments.train_fleet_env import TrainFleetEnv
    from src.algorithms.mappo_agent import MAPPOAgent
    from src.evaluation.evaluate_decompose import probe_critic_mode

    cfg = dict(parse_experiment_yaml(ROOT / args.experiment).env_cfg)
    cfg["grade_profile"] = args.grade
    cfg["max_steps"] = args.max_steps
    cfg["eval_mode"] = True
    env = TrainFleetEnv(cfg)
    agent = MAPPOAgent(num_drones=env.num_agents, obs_per_drone=env.obs_dim,
                       act_per_drone=env.act_dim, device="cpu",
                       critic=probe_critic_mode(str(ROOT / args.checkpoint)),
                       decision_interval=args.decision_interval,
                       physics_dt=float(getattr(env, "dt", 0.1)))
    agent.load(str(ROOT / args.checkpoint))

    n_cols = int(getattr(env, "num_trains", 3))
    n_pairs = max(1, n_cols - 1)
    env.reset(options={"speed": 60.0 / 3.6})
    xs, act = [], None
    for i in range(args.max_steps):
        if act is None or i % args.decision_interval == 0:
            flat = env._get_obs_decomposed().flatten().astype(np.float32)
            a, _ = agent.select_actions(flat, deterministic=True)
            act = a.reshape(env.num_agents, env.act_dim)
        _o, _r, term, trunc, info = env.step(act)
        g = info.get("gap_err_mean")
        if g is not None:
            xs.append(abs(float(g)))
        if term or trunc:
            break

    terms = dict(getattr(env, "reward_term_sums", {}) or {})
    total = sum(v for k, v in terms.items() if k not in ("total",))
    out = {
        "checkpoint": args.checkpoint,
        "steps_run": len(xs),
        "gap_err_mean_abs_m": {
            "mean": (sum(xs) / len(xs)) if xs else None,
            "max": max(xs) if xs else None,
        },
        "measured_terms_sum": {k: float(v) for k, v in terms.items()},
        "measured_total": float(total),
        "scale_sweep": [],
    }
    for s in CANDIDATE_S:
        acc = 0.0
        for x in xs:
            x_excess = max(0.0, x - D_EFF_M)
            acc += max(0.0, 1.0 - x_excess / s)
        est = GAP_EFF_W * n_pairs * acc
        out["scale_sweep"].append({
            "scale_m": s,
            "estimated_gap_eff_sum": est,
            "share_of_total": (est / total) if total else None,
            "nonzero_step_frac": (sum(1 for x in xs
                                       if max(0.0, x - D_EFF_M) < s) / len(xs)) if xs else None,
        })

    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    Path(args.out).write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"[sweep] steps={len(xs)}  gap_err_mean 均值={out['gap_err_mean_abs_m']['mean']:.1f} m "
          f"最大={out['gap_err_mean_abs_m']['max']:.1f} m")
    print(f"[sweep] 实测各分量总量（scale=150）：")
    for k, v in sorted(terms.items(), key=lambda kv: -abs(float(kv[1]))):
        print(f"[sweep]    {k:20s} {float(v):>14.1f}")
    print("[sweep] 候选尺度下间距项的估计量级与占比：")
    for c in out["scale_sweep"]:
        print(f"[sweep]    s={c['scale_m']:>6.0f}m  est_gap_eff_sum={c['estimated_gap_eff_sum']:>12.1f}  "
              f"占 total≈{100*(c['share_of_total'] or 0):>6.2f}%  非零步占比={100*(c['nonzero_step_frac'] or 0):>5.1f}%")
    print(f"[sweep] wrote {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
