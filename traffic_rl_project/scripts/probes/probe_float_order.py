"""判决性探针：跨机器 17.7% 差异的**机制层**定位——是不是"BLAS/线程归约顺序"这类
纯浮点层面的差异？

背景（诊断 §19.42）：
    同一 ckpt、同一参数、同一份代码（`src/` 数值路径自 b14e2bd 起只改了
    `src/metadata.py`，纯 provenance），本地两次跑**逐位一致**
    （peak 1478.8515764313422），云端那次是 1256.72（差 17.7%，且峰值列从
    "中列"翻成"尾列"）⇒ 差异必然发生在**浮点求和顺序**这一层。

本探针走**与评估入口完全同源**的路径（`make_env` + `MAPPOAgent.load` +
`select_actions(deterministic=True)`），分三问：

    Q1（线程数）：同一台机器、同一份权重、同一批观测，仅改变 torch/BLAS 线程数，
        策略输出是否**位级不同**？⇒ 归约顺序是否足以改变策略输出。
    Q2（重复确定性）：线程数固定时，重复前向是否位级稳定？
    Q3（观测取自真实 env）：前两问用真实 env 的初始观测（不是随机向量）。

    只要策略输出出现**位级差异**，在下游阈值化/量化的连续动作上就会被放大成
    不同的动作序列 ⇒ 沿 31500 步轨迹发散 ⇒ 这正是"微差放大成 17.7%"的机制。

    ⚠️ 口径：本探针**不产出任何峰值/安全判据**，只回答"浮点层是否足以改变策略输出"。
    ⚠️ 需 torch 环境（conda env traffic_rl）⇒ 在 WSL + conda 下运行。
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))


def _build(args):
    """与 evaluate_decompose.py 同源：make_env + MAPPOAgent.load。"""
    import numpy as np
    import torch

    from src.algorithms.mappo_agent import MAPPOAgent
    from src.evaluation.evaluate_decompose import make_env, probe_critic_mode

    # 【与官方入口对齐】max_steps / num_trains / target_speed 是 make_env 必读字段，
    # 取值与 §19.41 官方口径批次（run_official_ep1_ep7.sh）逐项一致：
    #   --max_steps 31500 --num_trains 3 --init_speed_kmh 60.0 --decision_interval 10
    ns = argparse.Namespace(
        mode="decompose_m1",
        checkpoint=args.checkpoint,
        experiment=args.experiment,
        num_trains=3,
        max_steps=31500,
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
    env = make_env("decompose", ns)
    critic = probe_critic_mode(args.checkpoint)
    agent = MAPPOAgent(num_drones=env.num_agents, obs_per_drone=env.obs_dim,
                       act_per_drone=env.act_dim, device="cpu",
                       critic=critic, decision_interval=10,
                       physics_dt=float(getattr(env, "dt", 0.1)))
    agent.load(args.checkpoint)
    obs = env._get_obs_decomposed().flatten()
    env.close()
    return agent, obs, env.num_agents, env.obs_dim, env.act_dim, critic


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--checkpoint", required=True)
    ap.add_argument("--experiment",
                    default="configs/experiments/formation_ed_ab_3train_1plus108_nincrgatecaprel.yaml")
    ap.add_argument("--out", default=None)
    ap.add_argument("--repeats", type=int, default=3)
    args = ap.parse_args()

    import numpy as np
    import torch

    torch.manual_seed(0)
    np.random.seed(0)

    agent, obs, n_agents, obs_dim, act_dim, critic = _build(args)
    print(f"[probe] agents={n_agents} obs_dim={obs_dim} act_dim={act_dim} critic={critic}")
    print(f"[probe] obs md5={hashlib.md5(np.ascontiguousarray(obs, dtype=np.float32).tobytes()).hexdigest()[:16]}")

    def forward():
        with torch.no_grad():
            a, _ = agent.select_actions(np.asarray(obs, dtype=np.float32),
                                         deterministic=True)
        a = np.asarray(a, dtype=np.float32)
        return a, hashlib.md5(a.tobytes()).hexdigest()

    threads_tried = []
    per_thread = {}
    for t in [1, 2, 4, 8, 16, torch.get_num_threads()]:
        t = max(1, int(t))
        if t in threads_tried:
            continue
        threads_tried.append(t)
        torch.set_num_threads(t)
        hashes, arrays = [], []
        for _ in range(args.repeats):
            a, h = forward()
            hashes.append(h)
            arrays.append(a)
        per_thread[f"threads_{t}"] = {
            "torch_num_threads": torch.get_num_threads(),
            "md5_per_repeat": hashes,
            "identical_within_thread": len(set(hashes)) == 1,
            "action_max_abs_diff_within": float(np.max(np.abs(arrays[0] - arrays[-1]))),
            "action": arrays[0].tolist(),
        }
        print(f"[probe] threads={t:>2} md5={hashes[0][:16]} "
              f"within-thread identical={len(set(hashes)) == 1}")

    uniq = {v["md5_per_repeat"][0] for v in per_thread.values()}
    across_identical = len(uniq) == 1
    print()
    print(f"[probe] Q1 跨线程前向位级相同: {across_identical}（unique md5={len(uniq)}）")
    print(f"[probe] Q2 各线程内重复稳定: "
          f"{ {k: v['identical_within_thread'] for k, v in per_thread.items()} }")
    if not across_identical:
        base_key = sorted(per_thread)[0]
        base = np.array(per_thread[base_key]["action"])
        for k, v in per_thread.items():
            a = np.array(v["action"])
            print(f"    {k}: max|Δaction| vs {base_key} = {np.max(np.abs(a - base)):.3e}  "
                  f"bit_identical={np.array_equal(a, base)}")

    out = {
        "checkpoint": args.checkpoint,
        "critic": critic,
        "n_agents": n_agents,
        "obs_dim": obs_dim,
        "act_dim": act_dim,
        "threads_tried": threads_tried,
        "across_threads_bit_identical": across_identical,
        "n_unique_action_hashes": len(uniq),
        "within_thread_stable": {k: v["identical_within_thread"]
                                 for k, v in per_thread.items()},
        "per_thread": {k: {kk: vv for kk, vv in v.items() if kk != "action"}
                       for k, v in per_thread.items()},
        "note": "纯浮点/归约顺序层探针；不产出峰值或安全判据。",
    }
    out_path = Path(args.out) if args.out else (
        ROOT / "outputs/logs/adr083_float_probe/thread_order_probe.json")
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"[probe] wrote {out_path}")


if __name__ == "__main__":
    main()
