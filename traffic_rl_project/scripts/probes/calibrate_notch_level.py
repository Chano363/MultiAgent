#!/usr/bin/env python
"""ADR-082 配套工具：级位 n_k 分布标定 + 阈值区分度预判。

【为什么需要】§19.35 实证：逐列 AB 派生阈值的判定式是 `want_on = n_k >= thr`，
而 n_k 被 `ed_notch_cap` 顶在 0.75 ⇒ 任何 <= 0.72 的阈值与默认 0.5 判定完全等价
（扫描"扫不开"是设计错误，不是机制无效）。

【本工具做什么】给定 ckpt，量出该策略的 n_k 分布，并直接算出：
  - 每个候选阈值下的"理论 AB 请求率"（n_k >= thr 的比例）
  - 该阈值相对参考阈值的**区分度**（两者理论请求率之差；= 0 ⇒ 该阈值无效）
⇒ 训练前据此选阈值，避免在饱和区空扫。

【用法】
  python scripts/probes/calibrate_notch_level.py <ckpt路径> [参考阈值=0.5]
"""
import json
import os
import sys

import numpy as np
import torch

sys.path.insert(0, os.getcwd())

from types import SimpleNamespace  # noqa: E402

from src.algorithms.mappo_agent import MAPPOAgent  # noqa: E402
from src.evaluation.evaluate_decompose import make_env  # noqa: E402

YAML_PATH = "tmp_adr082_yaml/base.yaml"
N_STEPS = int(os.environ.get("LG10_STEPS", "31500"))
CANDIDATES = [0.28, 0.35, 0.42, 0.5, 0.58, 0.65, 0.72, 0.75, 0.78, 0.80,
               0.82, 0.85, 0.88, 0.90, 0.91, 0.93, 0.95, 0.99]


def run(ckpt: str, yaml_path: str = YAML_PATH):
    args = SimpleNamespace(
        mode="decompose_m1", checkpoint=ckpt, experiment=yaml_path,
        formation_relative_speed_obs=None, consist_preset=None,
        grade="shuozhou_ningwuxi_beidaniu_49km", max_steps=N_STEPS,
        num_trains=3, n_seed=1, eval_seed=0, init_speed_kmh=None,
        target_speed=None, random_init_speed=False, decision_interval=10,
        mask_lever="none", hetero=False, hetero_seed=0)
    env = make_env("decompose", args)
    agent = MAPPOAgent(num_drones=env.num_agents, obs_per_drone=env.obs_dim,
                        act_per_drone=env.act_dim, device="cpu",
                        critic="per_agent", decision_interval=args.decision_interval,
                        physics_dt=float(getattr(env, "dt", 0.1)))
    agent.load(ckpt)
    env.reset(options={"speed": 60.0 / 3.6})
    na = env.num_agents
    acts = None
    nk = {k: [] for k in range(na)}
    for i in range(N_STEPS):
        if acts is None or i % args.decision_interval == 0:
            flat = env._get_obs_decomposed().flatten()
            with torch.no_grad():
                acts, _ = agent.select_actions(flat, deterministic=True)
            acts = acts.reshape(env.num_agents, env.act_dim)
        _, _, term, trunc, _ = env.step(acts)
        for k, c in enumerate(env.multi_loco_controllers):
            lvl = getattr(c, "_notch_level", None)
            if lvl is not None and len(lvl):
                nk[k].append(float(lvl[0]))
        if term or trunc:
            break
    return {k: np.asarray(v, dtype=float) for k, v in nk.items()}


def main():
    ckpt = sys.argv[1]
    ref_thr = float(sys.argv[2]) if len(sys.argv) > 2 else 0.5
    print("ckpt=%s ref_thr=%.2f steps=%d" % (ckpt, ref_thr, N_STEPS))
    dists = run(ckpt)
    out = {"ckpt": ckpt, "ref_thr": ref_thr, "columns": []}
    for k, v in dists.items():
        row = {
            "col": k,
            "n_k_min": round(float(v.min()), 4),
            "n_k_p50": round(float(np.percentile(v, 50)), 4),
            "n_k_p95": round(float(np.percentile(v, 95)), 4),
            "n_k_max": round(float(v.max()), 4),
            "frac_at_cap": round(float((v >= 0.7499).mean()), 6),
            "req_rate_by_thr": {},
            "discrimination_vs_ref": {},
        }
        for thr in CANDIDATES:
            rr = float((v >= thr).mean())
            row["req_rate_by_thr"]["%.2f" % thr] = round(rr, 6)
            row["discrimination_vs_ref"]["%.2f" % thr] = round(
                abs(rr - float((v >= ref_thr).mean())), 6)
        out["columns"].append(row)
        print("col=%d n_k[min=%.4f p50=%.4f p95=%.4f max=%.4f] frac_at_cap=%.4f"
              % (k, row["n_k_min"], row["n_k_p50"], row["n_k_p95"],
                 row["n_k_max"], row["frac_at_cap"]))
        # 有区分度的阈值（与参考阈值请求率之差 > 0.005）
        useful = [t for t, d in row["discrimination_vs_ref"].items() if d > 0.005]
        print("     有区分度的阈值(>0.005): %s" % (useful if useful else "无 ⇒ 全部阈值无效"))
    tag = os.environ.get("LG10_TAG", "adr082_calib")
    os.makedirs("outputs/results/diagnostics", exist_ok=True)
    path = "outputs/results/diagnostics/%s_%s.json" % (
        tag, os.path.basename(ckpt).replace(".pt", ""))
    with open(path, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=2)
    print("wrote %s" % path)


if __name__ == "__main__":
    main()
