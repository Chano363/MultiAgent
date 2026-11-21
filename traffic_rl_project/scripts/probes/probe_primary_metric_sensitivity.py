"""判决性探针（§19.48）：**主指标（列距/速度带）对浮点微差的敏感度**。

为什么必须单独测这一层（§19.47 之后的新缺口）：
    §19.43(4) 的放大系数探针只量了 **车钩峰值** 一个后果量，
    结论是"1 ULP 级扰动 ⇒ 整程峰值漂移 ~15%"。
    而 §19.47 把项目主指标重定位到 **列距 / 速度带**（ADR-042 §1.6：
    论文主 claim = 编队指标收益，车钩力只作工程底线），
    §19.47 的核心判决"训练期 `term_speed_band_sum` 是主指标口径下唯一稳定同向信号"
    **完全建立在评估态读数上** ⇒ 若这些读数本身对 1 ULP 扰动就会漂移十几个百分点，
    则 §19.47 的相关性结论、乃至"单阈值命中 ep1 且误杀集为空"的可分性结论，
    **都可能是在量噪声而不是量信号**。

本探针做法（**同机、同码、同参、同 ckpt、同入口**，只改浮点扰动档位）：
    与 `probe_amplification.py` **同源**的路径（`make_env` + `MAPPOAgent.load` +
    `select_actions(det=True)`，decision_interval=10），在 **策略输入观测** 上用
    `np.nextafter` 施加 ε 个 ULP（全体元素同向），其余全同，跑**整程**。
    与放大探针的差别只有一个：**同时产出主指标口径读数**
    （`band_rate` / `gap_err_mean_abs_m` / `gap_err_peak_abs_m` / `gap_min_m` / 追尾步数）
    ⇒ 一次跑批同时回答"峰值漂移多大"与"主指标漂移多大"。

判读规则（先定，避免事后解释）：
    · **主指标漂移 ≫ 训练期-评估期相关性的信号幅度**（§19.47：`speed_band_sum`
      与 gapMean 相关 +0.821，两端 rank 差通常仅 1–3 位）⇒ 判定
      "**§19.47 的主指标相关性结论不可用**"，第 11 投的止损判据必须另找
      抗噪信号（或改为**多 seed 重复 + 秩稳定性**的读法）。
    · **主指标漂移 ≪ 信号幅度** ⇒ §19.47 结论**不受浮点噪声威胁**，
      §19.47 的"唯一稳定同向信号 = `speed_band_sum`"可继续作为第 11 投靶子。
    · **主指标漂移与峰值漂移不同量级** ⇒ 两条口径必须**分别记、分别判**
      （与 §19.47 判决③同向，不得互相冒充）。

⚠️ 口径：本探针跑**整程**（31500 步），但**不作为峰值/安全判据**——
    它测的是"扰动 → 后果量漂移"的**敏感度**，属机制层诊断，
    与 §19.40/§19.42 的官方口径读数分属两个口径，**不得互相引用为判据**。
⚠️ 需 conda env traffic_rl ⇒ 在 WSL + conda 下运行（单集整程约 18–20 min）。
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))


def _build(args, ns):
    from src.algorithms.mappo_agent import MAPPOAgent
    from src.evaluation.evaluate_decompose import make_env, probe_critic_mode

    env = make_env("decompose", ns)
    critic = probe_critic_mode(args.checkpoint)
    agent = MAPPOAgent(num_drones=env.num_agents, obs_per_drone=env.obs_dim,
                       act_per_drone=env.act_dim, device="cpu",
                       critic=critic, decision_interval=10,
                       physics_dt=float(getattr(env, "dt", 0.1)))
    agent.load(args.checkpoint)
    return env, agent, critic


def _perturb(obs, ulps: int):
    """在 float32 观测上施加 ulps 个 ULP 的正向扰动（全体元素同向）。"""
    import numpy as np

    if ulps <= 0:
        return obs
    out = obs.copy()
    for _ in range(ulps):
        out = np.nextafter(out, np.float32(np.inf))
    return out


def run_one(args, ulps: int) -> dict:
    """跑整程，同时采集【工程口径】（峰值/超限）与【主指标口径】（列距/速度带）。"""
    import numpy as np

    ns = argparse.Namespace(
        mode="decompose_m1",
        checkpoint=args.checkpoint,
        experiment=args.experiment,
        num_trains=3,
        max_steps=args.max_steps,
        target_speed=None,
        formation_relative_speed_obs=False,
        consist_preset="10kt_1plus108",
        grade="shuozhou_ningwuxi_beidaniu_49km",
        random_init_speed=False,
        init_speed_kmh=60.0,
        decision_interval=10,
        mask_lever="none",
        hetero=False,
        hetero_seed=0,
        allow_rear_end=False,
    )
    env, agent, critic = _build(args, ns)

    init = ns.init_speed_kmh / 3.6
    env.reset(options={"speed": init})
    n = 0
    peak = 0.0
    viol = 0.0
    prev_viol = 0.0
    actions = None
    # ---- 主指标口径累计（与 evaluate_decompose.py 的官方实现同源口径）----
    band = 0
    gap_err_abs_sum = 0.0
    gap_err_abs_peak = 0.0
    gap_min_over_ep = float("inf")
    rear_end_steps = 0
    t0 = time.time()
    for i in range(args.max_steps):
        if actions is None or i % 10 == 0:
            flat = env._get_obs_decomposed().flatten().astype(np.float32)
            flat = _perturb(flat, ulps)
            a, _ = agent.select_actions(flat, deterministic=True)
            actions = a.reshape(env.num_agents, env.act_dim)
        _, _, term, trunc, info = env.step(actions)
        n += 1
        peak = max(peak, info["coupler_force_peak"])
        viol += info["coupler_limit_violations"] - prev_viol
        prev_viol = info["coupler_limit_violations"]
        # ---- 主指标（口径与官方 evaluate_decompose.py 一致）----
        vel = float(env.trains[0].dynamics.vel[0])
        band += int(env.v_min <= vel <= env.v_max)
        ge = float(info.get("gap_err_mean", 0.0))
        gm = float(info.get("gap_min_m", float("inf")))
        gap_err_abs_sum += abs(ge)
        gap_err_abs_peak = max(gap_err_abs_peak, abs(ge))
        if np.isfinite(gm):
            gap_min_over_ep = min(gap_min_over_ep, gm)
            rear_end_steps += int(gm <= 0.0)
        if term or trunc:
            break
    env.close()
    return {
        "ulps": ulps,
        "steps": n,
        # 工程口径
        "peak_coupler_kN": peak / 1e3,
        "coupler_violations": viol,
        # 主指标口径
        "band_rate": band / max(n, 1),
        "gap_err_mean_abs_m": gap_err_abs_sum / max(n, 1),
        "gap_err_peak_abs_m": gap_err_abs_peak,
        "gap_min_m": gap_min_over_ep,
        "rear_end_steps": rear_end_steps,
        "critic": critic,
        "wall_s": time.time() - t0,
    }


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--checkpoint", required=True)
    ap.add_argument("--experiment",
                    default="configs/experiments/formation_ed_ab_3train_1plus108_nincrgatecaprel.yaml")
    ap.add_argument("--max_steps", type=int, default=31500)
    ap.add_argument("--ulps", default="0,1")
    ap.add_argument("--out", default=None)
    args = ap.parse_args()

    results = []
    for u in [int(x) for x in args.ulps.split(",") if x.strip()]:
        print(f"[probe] === 扰动档位 {u} ULP 开始（整程 {args.max_steps} 步，主指标口径）",
              flush=True)
        r = run_one(args, u)
        results.append(r)
        print(f"[probe] ulps={u:<4} peak={r['peak_coupler_kN']:.10f} kN  "
              f"viol={r['coupler_violations']:.0f}  "
              f"band={r['band_rate']:.6f}  gapMean={r['gap_err_mean_abs_m']:.4f} m  "
              f"gapPeak={r['gap_err_peak_abs_m']:.4f} m  "
              f"gapMin={r['gap_min_m']:.4f} m  ({r['wall_s']:.0f}s)", flush=True)

    base = results[0]
    for r in results:
        for key in ("peak_coupler_kN", "band_rate", "gap_err_mean_abs_m",
                    "gap_err_peak_abs_m", "gap_min_m"):
            b = base[key]
            r[f"delta_{key}_vs_base"] = r[key] - b
            r[f"rel_delta_{key}_vs_base_pct"] = ((r[key] - b) / b * 100.0
                                                 if b else float("nan"))

    print()
    print("[probe] 扰动 → 后果量漂移（工程口径 vs 主指标口径）")
    for r in results:
        print(f"    ulps={r['ulps']:<5} peak {r['peak_coupler_kN']:.4f} kN "
              f"({r['rel_delta_peak_coupler_kN_vs_base_pct']:+.3f}%)  |  "
              f"band {r['band_rate']:.6f} "
              f"({r['rel_delta_band_rate_vs_base_pct']:+.4f}%)  |  "
              f"gapMean {r['gap_err_mean_abs_m']:.4f} m "
              f"({r['rel_delta_gap_err_mean_abs_m_vs_base_pct']:+.4f}%)  |  "
              f"gapPeak {r['gap_err_peak_abs_m']:.4f} m "
              f"({r['rel_delta_gap_err_peak_abs_m_vs_base_pct']:+.4f}%)  |  "
              f"gapMin {r['gap_min_m']:.4f} m "
              f"({r['rel_delta_gap_min_m_vs_base_pct']:+.4f}%)")

    out = {
        "checkpoint": args.checkpoint,
        "max_steps": args.max_steps,
        "baseline": base,
        "results": results,
        "note": ("扰动→后果量漂移敏感度（机制层诊断）；"
                 "不是峰值/安全判据，不得与官方口径读数互引。"),
    }
    out_path = Path(args.out) if args.out else (
        ROOT / "outputs/logs/adr083_float_probe/primary_metric_sensitivity.json")
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"[probe] wrote {out_path}")


if __name__ == "__main__":
    main()
