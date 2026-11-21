"""探针：**训练态 vs 评估态的列距落差**（零机时，诊断层）。

**为什么做这个探针（2026-11-21，§19.67）**
    §19.51.3d 断言"`gap_eff` 奖励项全程恒零 ⇒ 奖励面看不见散开"，据此把干预面③
    （改奖励尺度）当作下一步主线。⚠️ 但用第 9 投的**训练期落盘**复核发现：
    `gap_eff_sum` **并不恒零**（ep1–ep7 = 4.5万–16.3万，占 total 的 8%–37%），
    反推**训练态平均列距 ≈ 250 m**，而**评估态**（官方整程快评，同 ckpt）是 **725.8 m**
    ⇒ **训练态与评估态之间存在 2.5–3.7 倍的列距落差**。
    ⇒ 若属实，则"奖励面看不见散开"这一前提**只对评估态成立**，
    而**干预面③（改奖励尺度）可能治不了病** ⇒ 必须先把落差来源查清。

**探针设计（同参对照，唯一变量 = `eval_mode`）**
    变体 A：`eval_mode=True`（**评估口径**）—— 期望复现官方读数（gap_err_mean ≈ 725.8 m）⇒ 自检
    变体 B：`eval_mode=False`（**训练口径**）—— 同 ckpt、同配置、同确定性动作、同起点
    ⇒ **A/B 之差 = `eval_mode` 开关的贡献**；剩余落差（若仍有）只能来自
    "训练时是**带探索噪声的采样动作**、评估时是**确定性动作**"（分布偏移）。

**口径纪律**
    · 本探针**只作机制诊断**：短窗（默认 8000 步）时**两变体同长同参 ⇒ 差值仍可比**，
      但**绝对值不作判据**（红线 3）；跑满 31500 步（`--full`）时才是整程口径。
    · **不产出任何峰值/安全判据**；不用于论文口径。
    · 跑在**本地同机** ⇒ 两变体同机同参，差值可归因。

用法（conda env traffic_rl，项目根）：
    python scripts/probes/probe_train_eval_gap_gap.py
    python scripts/probes/probe_train_eval_gap_gap.py --full
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


def _build_env(experiment: str, eval_mode: bool, max_steps: int, grade: str):
    from src.trainer.config_schema import parse_experiment_yaml
    from src.environments.train_fleet_env import TrainFleetEnv

    cfg = dict(parse_experiment_yaml(ROOT / experiment).env_cfg)
    cfg["grade_profile"] = grade
    cfg["max_steps"] = max_steps
    cfg["eval_mode"] = eval_mode
    return TrainFleetEnv(cfg)


def _load_agent(env, ckpt: str, decision_interval: int):
    from src.algorithms.mappo_agent import MAPPOAgent
    from src.evaluation.evaluate_decompose import probe_critic_mode

    critic = probe_critic_mode(str(ROOT / ckpt))
    agent = MAPPOAgent(num_drones=env.num_agents, obs_per_drone=env.obs_dim,
                       act_per_drone=env.act_dim, device="cpu", critic=critic,
                       decision_interval=decision_interval,
                       physics_dt=float(getattr(env, "dt", 0.1)))
    agent.load(str(ROOT / ckpt))
    return agent


def _run(env, agent, steps: int, decision_interval: int) -> dict:
    n_cols = int(getattr(env, "num_trains", 3))
    env.reset(options={"speed": 60.0 / 3.6})
    gaps, speeds, gmins = [], [], []
    act = None
    for i in range(steps):
        if act is None or i % decision_interval == 0:
            flat = env._get_obs_decomposed().flatten().astype(np.float32)
            a, _ = agent.select_actions(flat, deterministic=True)
            act = a.reshape(env.num_agents, env.act_dim)
        _o, _r, term, trunc, info = env.step(act)
        g = info.get("gap_err_mean")
        if g is not None:
            gaps.append(abs(float(g)))
        gm = info.get("gap_min_m")
        if gm is not None:
            gmins.append(float(gm))
        sp = info.get("train_speed_mean_kmh") or info.get("speed_kmh")
        if sp is not None:
            speeds.append(float(sp))
        if term or trunc:
            break
    return {
        "steps_run": len(gaps),
        "gap_err_mean_abs_m_mean": (sum(gaps) / len(gaps)) if gaps else None,
        "gap_err_mean_abs_m_median": (sorted(gaps)[len(gaps) // 2]) if gaps else None,
        "gap_min_m_mean": (sum(gmins) / len(gmins)) if gmins else None,
        "speed_kmh_mean": (sum(speeds) / len(speeds)) if speeds else None,
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--experiment", default=DEFAULT_EXPERIMENT)
    ap.add_argument("--checkpoint", default=DEFAULT_CKPT)
    ap.add_argument("--steps", type=int, default=8000)
    ap.add_argument("--full", action="store_true", help="跑满 31500 步（整程口径）")
    ap.add_argument("--grade", default="shuozhou_ningwuxi_beidaniu_49km")
    ap.add_argument("--decision-interval", type=int, default=10)
    ap.add_argument("--out", default=str(ROOT / "outputs/logs/adr083_float_probe"
                                         / "train_eval_gap_gap.json"))
    args = ap.parse_args()

    steps = 31500 if args.full else args.steps
    out = {"steps": steps, "full_run": bool(args.full),
           "checkpoint": args.checkpoint, "experiment": args.experiment,
           "variants": {}}

    for tag, eval_mode in (("A_eval_mode_true", True), ("B_eval_mode_false", False)):
        env = _build_env(args.experiment, eval_mode, steps, args.grade)
        agent = _load_agent(env, args.checkpoint, args.decision_interval)
        res = _run(env, agent, steps, args.decision_interval)
        res["eval_mode"] = eval_mode
        out["variants"][tag] = res
        print(f"[te-gap] {tag}: gap_err_mean_abs(m) mean={res['gap_err_mean_abs_m_mean']} "
              f"median={res['gap_err_mean_abs_m_median']} gapMin={res['gap_min_m_mean']} "
              f"speed={res['speed_kmh_mean']} steps={res['steps_run']}")
        try:
            env.close()
        except Exception:
            pass

    a = out["variants"]["A_eval_mode_true"]["gap_err_mean_abs_m_mean"]
    b = out["variants"]["B_eval_mode_false"]["gap_err_mean_abs_m_mean"]
    if a and b:
        out["eval_mode_contribution"] = {
            "A_minus_B_m": a - b,
            "ratio_A_over_B": a / b if b else None,
        }
        print(f"[te-gap] eval_mode 贡献：A − B = {a - b:.1f} m（A/B = {a/b:.2f}）")
        print("[te-gap] ⚠️ 若 A/B 仍显著 > 1，则剩余落差**不能**由 eval_mode 解释 ⇒ "
              "只能来自'训练用采样动作 vs 评估用确定性动作'的分布偏移（或其它 eval_mode 附带开关）")
    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    Path(args.out).write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"[te-gap] wrote {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
