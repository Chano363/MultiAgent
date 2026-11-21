"""判决性探针（§19.46）：**torch 策略前向对 CPU 指令集路径是否位级敏感**？

为什么必须单独测这一层（补 §19.43 的覆盖缺口）：
    §19.43 的排除性实验只覆盖了 **numba 车钩力内核**的 JIT 目标 ISA
    （generic/skylake/icelake/sapphirerapids 五档 md5 唯一），
    **没有覆盖策略网络（torch CPU 上的 MLP 前向）**。
    而诊断 2026-09 小节-三已把一次跨机偏差归因指向"**CPU 微架构浮点代码生成差异**"
    （并已排除 numpy 版本差异：本地 2.2.5↔2.2.6 切换后偏差 0.0000%）。
    torch 的 CPU GEMM 在 AVX2 与 AVX512 上**可能**采用不同向量化/归约路径
    ⇒ 这是 §19.42 剩余候选（"其它浮点实现细节差异"）里**最具体的一条**。

本探针做法（**同机、同码、同权重、同观测**，只切 CPU 指令集能力档）：
    用子进程 + 环境变量切换 torch/oneDNN/MKL 的 CPU ISA 能力：
      · `ATEN_CPU_CAPABILITY`  ∈ {default, avx2, avx512, sse41}
      · `ONEDNN_MAX_CPU_ISA`   ∈ {DEFAULT, SSE41, AVX2, AVX512}
      · `MKL_ENABLE_INSTRUCTIONS` ∈ {AVX2, AVX, SSE4_2}
    每个档位跑**与评估入口同源**的策略前向（`make_env` + `MAPPOAgent.load` +
    `select_actions(deterministic=True)`，真实 env 观测），打印动作 md5。

判读：
    · 若各档 md5 **唯一** ⇒ 策略前向对 ISA 路径**不敏感** ⇒ 与 §19.43 的 numba 结论
      一致地排除"微架构"这一支（至少在本地能覆盖的档位上）。
    · 若某两档 md5 **不同** ⇒ **策略前向位级依赖指令集路径** ⇒ 云端（AVX512）
      与本地（AVX2）之间**存在一条位级差异的真实通道**，且该通道**未被 §19.43 覆盖**
      ⇒ 这是跨机器 17.7% 差异的**机制层候选**（仍需与放大系数实测合起来才成立）。

⚠️ 口径：本探针**不产出任何峰值/安全判据**，只回答"策略前向是否 ISA 敏感"。
⚠️ 本机为 AVX2（无 AVX512）⇒ **AVX512 档若被回退，其结果只说明"回退后与谁相同"**，
    不能替代云端实测（云端 AVX512 的真实路径须在云端窗口验证）。
⚠️ 需 torch 环境（conda env traffic_rl）⇒ 在 WSL + conda 下运行。
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

# (档位名, 环境变量字典)
CAPS = [
    ("default", {}),
    ("aten_default", {"ATEN_CPU_CAPABILITY": "default"}),
    ("aten_avx2", {"ATEN_CPU_CAPABILITY": "avx2"}),
    ("aten_sse41", {"ATEN_CPU_CAPABILITY": "sse41"}),
    ("aten_avx512", {"ATEN_CPU_CAPABILITY": "avx512"}),
    ("dnnl_avx2", {"ONEDNN_MAX_CPU_ISA": "AVX2"}),
    ("dnnl_sse41", {"ONEDNN_MAX_CPU_ISA": "SSE41"}),
    ("dnnl_avx512", {"ONEDNN_MAX_CPU_ISA": "AVX512"}),
    ("mkl_avx2", {"MKL_ENABLE_INSTRUCTIONS": "AVX2"}),
    ("mkl_sse42", {"MKL_ENABLE_INSTRUCTIONS": "SSE4_2"}),
]


def _child(args) -> int:
    """子进程：跑一次同源策略前向，打印 md5 与动作。"""
    import numpy as np
    import torch

    torch.manual_seed(0)
    np.random.seed(0)

    from src.algorithms.mappo_agent import MAPPOAgent
    from src.evaluation.evaluate_decompose import make_env, probe_critic_mode

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

    with torch.no_grad():
        a, _ = agent.select_actions(np.asarray(obs, dtype=np.float32),
                                     deterministic=True)
    a = np.asarray(a, dtype=np.float32)
    print(json.dumps({
        "md5": hashlib.md5(a.tobytes()).hexdigest(),
        "action": [float(x) for x in a],
        "torch": torch.__version__,
        "numpy": np.__version__,
        "aten_cap": os.environ.get("ATEN_CPU_CAPABILITY", "<unset>"),
        "dnnl_cap": os.environ.get("ONEDNN_MAX_CPU_ISA", "<unset>"),
        "mkl_cap": os.environ.get("MKL_ENABLE_INSTRUCTIONS", "<unset>"),
    }, ensure_ascii=False))
    return 0


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--checkpoint", required=True)
    ap.add_argument("--experiment",
                    default="configs/experiments/formation_ed_ab_3train_1plus108_nincrgatecaprel.yaml")
    ap.add_argument("--out", default=None)
    ap.add_argument("--child", action="store_true")
    args = ap.parse_args()

    if args.child:
        return _child(args)

    env_base = dict(os.environ)
    results = {}
    for name, extra in CAPS:
        e = dict(env_base)
        e.update(extra)
        # 线程数固定（§19.43 已排除线程数这一支，这里排除它的干扰）
        e["OMP_NUM_THREADS"] = "1"
        e["MKL_NUM_THREADS"] = "1"
        p = subprocess.run([sys.executable, __file__, "--child", "--checkpoint", args.checkpoint,
                            "--experiment", args.experiment],
                           env=e, capture_output=True, text=True)
        line = ""
        for ln in (p.stdout or "").strip().splitlines():
            ln = ln.strip()
            if ln.startswith("{"):
                line = ln
        if not line:
            results[name] = {"ok": False,
                             "stderr_tail": (p.stderr or "")[-400:]}
            print(f"[probe] {name}: 子进程失败 rc={p.returncode}")
            continue
        d = json.loads(line)
        results[name] = d
        print(f"[probe] {name}: md5={d['md5'][:16]} "
              f"(aten={d['aten_cap']} dnnl={d['dnnl_cap']} mkl={d['mkl_cap']})")

    ok = {k: v for k, v in results.items() if v.get("ok", True) and "md5" in v}
    uniq = {v["md5"] for v in ok.values()}
    print()
    print(f"[probe] 成功档位 {len(ok)} / {len(CAPS)}；唯一 md5 数 = {len(uniq)}")
    print(f"[probe] 策略前向对 CPU ISA 路径位级敏感: {len(uniq) > 1}")

    base = None
    for k in ("default", "aten_default"):
        if k in ok:
            base = ok[k]
            break
    diffs = {}
    if base is not None:
        import numpy as np
        b = np.asarray(base["action"], dtype=np.float64)
        for k, v in ok.items():
            a = np.asarray(v["action"], dtype=np.float64)
            diffs[k] = {
                "max_abs_diff": float(np.max(np.abs(a - b))) if a.shape == b.shape else None,
                "bit_identical": bool(np.array_equal(a, b)),
            }

    out = {
        "checkpoint": args.checkpoint,
        "n_caps": len(CAPS),
        "n_ok_caps": len(ok),
        "n_unique_md5": len(uniq),
        "isa_sensitive": len(uniq) > 1,
        "results": results,
        "diff_vs_baseline": diffs,
        "note": ("策略前向 ISA 敏感性探针；不产出峰值或安全判据。"
                 "本机 AVX2（无 AVX512）⇒ AVX512 档若被回退，其结果只说明"
                 "'回退后与谁相同'，不能替代云端 AVX512 实测。"),
    }
    out_path = Path(args.out) if args.out else (
        ROOT / "outputs/logs/adr083_float_probe/torch_isa_path_probe.json")
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"[probe] wrote {out_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
