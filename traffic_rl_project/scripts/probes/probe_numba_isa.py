"""判决性探针（Q4）：**numba JIT 目标 ISA** 是否改变车钩力内核的**位级输出**？

背景（诊断 §19.42 未闭合项：跨机器 17.7% 差异的机制层未定位）：
    本地两次跑逐位复现、云端那次差 17.7% ⇒ 差异必然来自浮点层。
    §19.43 探针 A（probe_float_order.py）已判：**线程数不是放大层**
    （1/2/4/8/16/默认 六种线程下策略前向 md5 唯一）。
    本探针问下一个候选：**JIT 目标 ISA**（本地 i5-13420H = AVX2 无 AVX512；
    云端 ecs.c9i.2xlarge = Xeon Ice Lake/Sapphire Rapids = AVX512）。

    numba 的 `njit(cache=True)` 按**当前 CPU 特性**生成机器码（LLVM 目标三元组），
    不同 ISA ⇒ 可能启用/禁用 FMA 收缩、不同向量宽度 ⇒ 同一数学式子的
    **舍入次序不同** ⇒ 位级输出不同（1 ULP 级）。
    1 ULP 级差异在 31500 步闭环编组动力学里被混沌放大 ⇒ 峰值差 17.7%、
    且"哪一列承压"会翻转（§19.42 已实测形态跨机器翻转）。

本探针做法（**同机、同权重、同输入，只改 JIT 目标**）：
    用 numba 官方环境变量 `NUMBA_CPU_NAME` 强制不同目标 CPU 编同一内核，
    逐目标比较车钩力输出的 md5 与逐元素最大差。
    目标清单覆盖：无 SIMD 基线（generic）→ Skylake(AVX2,FMA) → Ice Lake(AVX512)
    → Sapphire Rapids(AVX512+AMX) ⇒ 本地默认目标（raptorlake）在其中。

    ⚠️ 口径：本探针**不产出任何峰值/安全判据**，只回答"ISA 是否改变内核位级输出"。
    ⚠️ `NUMBA_CPU_NAME` 会改变 numba 的 cache 索引 ⇒ 每个目标必须用独立
    `NUMBA_CACHE_DIR`，否则会复用上一个目标的 .nbc 缓存（假阴性）。
    ⚠️ 需 conda env traffic_rl ⇒ 在 WSL + conda 下运行。
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

# 子进程里跑的内核片段：固定输入 → 固定输出 → 打印 md5 与逐元素摘要。
CHILD_SNIPPET = r"""
import hashlib, json, os, sys
import numpy as np

TARGETS_OUT = os.environ["PROBE_OUT"]

# 确定性合成输入（覆盖三种状态：间隙内 / 接触渐入 / 刚性限位）
n = 64
rng = np.random.default_rng(12345)
e = rng.uniform(-0.06, 0.06, n)
dv = rng.uniform(-0.05, 0.05, n)
gap = np.full(n, 0.005)
v_eps = np.full(n, 0.002)
rigid_k = np.full(n, 8.0e6)
stroke = np.full(n, 0.02)
gain = np.full(n, 1.0)
max_impulse = np.full(n, 1.0e6)
xs = np.linspace(0.0, 0.08, 41)
fl_tab = np.linspace(0.0, 2.0e5, 41)
fu_tab = np.linspace(0.0, 1.5e5, 41)

from src.train_dynamics.train import _coupler_force_kernel, _HAS_NUMBA

out = np.asarray(_coupler_force_kernel(e, dv, gap, v_eps, rigid_k, stroke,
                                       gain, max_impulse, xs, fl_tab, fu_tab))
b = np.ascontiguousarray(out, dtype=np.float64).tobytes()
res = {
    "numba_available": bool(_HAS_NUMBA),
    "md5": hashlib.md5(b).hexdigest(),
    "out_first8": [float(x) for x in out[:8]],
    "out_sum": float(np.sum(out)),
    "out_max": float(np.max(out)),
    "cpu_name_env": os.environ.get("NUMBA_CPU_NAME", "(default)"),
}
with open(TARGETS_OUT, "w", encoding="utf-8") as f:
    json.dump(res, f)
"""


def _run_target(target: str, cache_root: Path, out_json: Path) -> dict:
    """在一个独立 NUMBA_CPU_NAME / NUMBA_CACHE_DIR 下跑内核片段。"""
    env = dict(os.environ)
    env["NUMBA_CACHE_DIR"] = str(cache_root / target)
    env["PROBE_OUT"] = str(out_json)
    env["PYTHONPATH"] = str(ROOT) + os.pathsep + env.get("PYTHONPATH", "")
    if target == "(default)":
        env.pop("NUMBA_CPU_NAME", None)
    else:
        env["NUMBA_CPU_NAME"] = target
    # 子进程不允许继承 CONDA_* 之外的东西？不需要；但要清掉可能干扰的变量
    env.pop("TRAIN_RL_NO_NUMBA", None)
    proc = subprocess.run([sys.executable, "-c", CHILD_SNIPPET],
                          cwd=str(ROOT), env=env, capture_output=True, text=True)
    if proc.returncode != 0 or not out_json.is_file():
        return {"target": target, "ok": False,
                "stderr": (proc.stderr or "")[-800:]}
    data = json.loads(out_json.read_text(encoding="utf-8"))
    data["target"] = target
    data["ok"] = True
    return data


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=None)
    ap.add_argument("--targets", default="generic,skylake,icelake,sapphirerapids,(default)")
    args = ap.parse_args()

    import numpy as np

    cache_root = ROOT / "outputs/tmp_numba_isa_cache"
    cache_root.mkdir(parents=True, exist_ok=True)
    work = cache_root / "work"
    work.mkdir(parents=True, exist_ok=True)

    results = []
    for target in [t.strip() for t in args.targets.split(",") if t.strip()]:
        out_json = work / f"res_{target.replace('(', '').replace(')', '')}.json"
        if out_json.is_file():
            out_json.unlink()
        r = _run_target(target, cache_root, out_json)
        results.append(r)
        if r.get("ok"):
            print(f"[probe] target={target:<16} md5={r['md5'][:16]} "
                  f"max={r['out_max']:.12e}")
        else:
            print(f"[probe] target={target:<16} FAILED rc/err（该目标可能不受支持）")
            print("        ", (r.get("stderr") or "").strip().splitlines()[-1][:200])

    ok = [r for r in results if r.get("ok")]
    md5s = {r["md5"] for r in ok}
    identical = len(md5s) == 1

    # 逐元素差（以第一个成功目标为基准）
    diffs = {}
    if ok:
        base = np.array(ok[0]["out_first8"], dtype=float)
        for r in ok:
            a = np.array(r["out_first8"], dtype=float)
            diffs[r["target"]] = {
                "max_abs_diff_vs_first": float(np.max(np.abs(a - base))),
                "bit_identical_vs_first": bool(np.array_equal(a, base)),
            }

    print()
    print(f"[probe] 成功目标数={len(ok)}  唯一 md5={len(md5s)}  "
          f"跨 ISA 位级相同={identical}")
    for k, v in diffs.items():
        print(f"    {k:<16} max|Δ|={v['max_abs_diff_vs_first']:.3e}  "
              f"bit_identical={v['bit_identical_vs_first']}")

    out = {
        "targets_tried": [r["target"] for r in results],
        "targets_ok": [r["target"] for r in ok],
        "n_unique_md5": len(md5s),
        "across_isa_bit_identical": identical,
        "per_target": {r["target"]: {k: v for k, v in r.items() if k != "out_first8"}
                       for r in ok},
        "per_target_diff_vs_first": diffs,
        "note": ("numba JIT 目标 ISA 层的位级探针；不产出峰值或安全判据。"
                 "cache 隔离：每目标独立 NUMBA_CACHE_DIR。"),
    }
    out_path = Path(args.out) if args.out else (
        ROOT / "outputs/logs/adr083_float_probe/numba_isa_probe.json")
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"[probe] wrote {out_path}")

    # 清理临时 cache（不留垃圾）
    try:
        for p in sorted(cache_root.rglob("*"), reverse=True):
            if p.is_file():
                p.unlink()
            elif p.is_dir():
                p.rmdir()
        cache_root.rmdir()
    except Exception as e:  # noqa: BLE001
        print(f"[probe] 临时 cache 清理未完全成功: {type(e).__name__}: {e}")


if __name__ == "__main__":
    main()
