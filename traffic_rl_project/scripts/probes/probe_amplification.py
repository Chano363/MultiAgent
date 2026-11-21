"""判决性探针（Q5）：**放大系数**——1 ULP 级微差在 31500 步里能放大成多少？

背景（诊断 §19.42 未闭合项 + §19.43 两轮浮点层排除）：
    已排除两个浮点层假设：
      · §19.43-A 线程归约顺序（1/2/4/8/16/默认 六种线程下策略前向 md5 唯一）；
      · §19.43-B numba JIT 目标 ISA（generic/skylake/icelake/sapphirerapids
        /default 五目标下车钩力内核输出 md5 唯一）。
    ⇒ 跨机器 17.7% 差异既非线程序、也非 ISA，而是**别的浮点差异来源**
    （例：numpy/torch 版本不同的实现细节、libm 版本、其它归约次序）。
    但**机制层真正要回答的不是"差在哪一位"，而是"微差要多大才够"**：
      若 1 ULP 级微差在 31500 步后能放大到 ~17% 量级 ⇒ 跨机器差异的**量级**
      完全在"浮点微差 + 闭环混沌放大"的可解释范围内，**无需**再定位到具体位；
      若 1 ULP 级微差几乎不改变峰值 ⇒ 17.7% 不是浮点微差能解释的，
      存在**更大口径的差异**（参数/模型/环境），§19.42 的"差异=跨机器"结论
      需重新审视（可能是同机同码之外的别的原因）。

本探针做法（**同机、同码、同参、同 ckpt、同入口**）：
    走官方入口同源路径（`make_env` + `MAPPOAgent.load` + `select_actions(det=True)`，
    decision_interval=10，max_steps=31500），在**策略输入观测**上注入
    一个极小扰动 ε（默认 1 ULP 量级），其余完全不动，跑整程，量测峰值漂移。

    扰动施加位置：`env._get_obs_decomposed()` 返回的 float32 观测上，
    对**全部元素**加 ε（float32 可表示的最小非零步长 ≈ 1.2e-7 相对量级，
    用 `np.nextafter` 施加"1 ULP"扰动最贴近浮点实现的真实差异）。
    ε 档位：0（对照，应逐位复现 1478.8515764313422）、1 ULP、10 ULP、100 ULP。

    ⚠️ 口径：本探针跑**整程**（31500 步），但**不作为峰值/安全判据**——
    它测的是"扰动 → 峰值漂移"的**敏感度曲线**，属机制层诊断，
    与 §19.40/§19.42 的官方口径读数分属两个口径，不得互相引用为判据。
    ⚠️ 需 conda env traffic_rl ⇒ 在 WSL + conda 下运行（单集整程约 20–40 min）。
"""
from __future__ import annotations

import argparse
import json
import os
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
        if term or trunc:
            break
    env.close()
    return {
        "ulps": ulps,
        "steps": n,
        "peak_coupler_kN": peak / 1e3,
        "coupler_violations": viol,
        "critic": critic,
        "wall_s": time.time() - t0,
    }


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--checkpoint", required=True)
    ap.add_argument("--experiment",
                    default="configs/experiments/formation_ed_ab_3train_1plus108_nincrgatecaprel.yaml")
    ap.add_argument("--max_steps", type=int, default=31500)
    ap.add_argument("--ulps", default="0,1,10,100")
    ap.add_argument("--out", default=None)
    args = ap.parse_args()

    results = []
    for u in [int(x) for x in args.ulps.split(",") if x.strip()]:
        print(f"[probe] === 扰动档位 {u} ULP 开始（整程 {args.max_steps} 步）", flush=True)
        r = run_one(args, u)
        results.append(r)
        print(f"[probe] ulps={u:<4} peak={r['peak_coupler_kN']:.10f} kN  "
              f"viol={r['coupler_violations']:.0f}  steps={r['steps']}  "
              f"({r['wall_s']:.0f}s)", flush=True)

    base = results[0]["peak_coupler_kN"]
    for r in results:
        r["delta_peak_kN_vs_base"] = r["peak_coupler_kN"] - base
        r["rel_delta_peak_vs_base"] = ((r["peak_coupler_kN"] - base) / base
                                       if base else float("nan"))
        r["rel_delta_peak_vs_base_pct"] = r["rel_delta_peak_vs_base"] * 100.0

    print()
    print("[probe] 扰动 → 峰值漂移（放大系数）")
    for r in results:
        print(f"    ulps={r['ulps']:<5} peak={r['peak_coupler_kN']:.6f} kN  "
              f"Δ={r['delta_peak_kN_vs_base']:+.6f} kN  "
              f"({r['rel_delta_peak_vs_base_pct']:+.3f}%)")

    out = {
        "checkpoint": args.checkpoint,
        "max_steps": args.max_steps,
        "baseline_peak_kN": base,
        "results": results,
        "note": ("扰动→峰值漂移敏感度曲线（机制层诊断）；"
                 "不是峰值/安全判据，不得与官方口径读数互引。"),
    }
    out_path = Path(args.out) if args.out else (
        ROOT / "outputs/logs/adr083_float_probe/amplification_probe.json")
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"[probe] wrote {out_path}")


if __name__ == "__main__":
    main()
