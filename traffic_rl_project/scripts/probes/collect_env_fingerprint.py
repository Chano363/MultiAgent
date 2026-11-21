"""环境指纹采集器（ADR-083 / §19.46）：把"跨机器差异"的可疑维度**结构化**留痕。

为什么需要：
    §19.42/§19.43 把跨机 17.7% 差异收敛到"浮点实现细节"层，并排除了
    线程序、numba JIT 目标 ISA 两项；但**尚未**逐项核对两机的
    **BLAS/MKL 实现、oneDNN 版本、CPU capability、glibc/libm、numpy/numba 版本**。
    这些是**可以逐项比对**的客观事实，且**采集成本近乎为零**（一行 `pip freeze` 级），
    却能把"剩余候选"从模糊的"其它浮点实现细节"收窄成**可判定清单**。

采集内容（全部为**只读**环境事实，不触碰训练/评估路径）：
    · 解释器与依赖版本（python / numpy / numba / torch / gym 等）
    · `torch.__config__.show()`（**BLAS 是 MKL 还是 OpenBLAS**、oneDNN 版本、
      CPU capability、编译选项）—— 这是 GEMM 归约顺序差异的主要来源
    · CPU 型号与 flags（AVX2 / AVX512 / FMA）
    · glibc 版本（libm 实现差异）
    · 线程与并行环境变量（OMP / MKL / OPENBLAS）
    · numba 目标与缓存目录

用法（本地或云端均可，输出 JSON）：
    python scripts/probes/collect_env_fingerprint.py --label local --out <path>.json

⚠️ 口径：本工具**不产出任何峰值/安全判据**，只留痕环境事实。
⚠️ **纪律**：指纹**只可用于"两机是否同源"的核对**；
    环境不同**不等于**已定位差异来源（相关性 ≠ 因果，见 §19.41/§19.43 纪律）。
"""
from __future__ import annotations

import argparse
import json
import os
import platform
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

ENV_KEYS = [
    "OMP_NUM_THREADS", "MKL_NUM_THREADS", "OPENBLAS_NUM_THREADS",
    "MKL_ENABLE_INSTRUCTIONS", "ONEDNN_MAX_CPU_ISA", "ATEN_CPU_CAPABILITY",
    "NUMBA_CPU_NAME", "NUMBA_CACHE_DIR", "PYTHONHASHSEED", "CUDA_VISIBLE_DEVICES",
]


def _run(cmd) -> str:
    try:
        p = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=30)
        return (p.stdout or "").strip()
    except Exception as e:  # noqa: BLE001
        return f"<error: {e}>"


def collect() -> dict:
    fp: dict = {
        "collected_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "hostname": platform.node(),
        "platform": platform.platform(),
        "machine": platform.machine(),
        "python": sys.version.split()[0],
        "python_full": sys.version,
        "executable": sys.executable,
        "cwd": os.getcwd(),
        "env": {k: os.environ.get(k) for k in ENV_KEYS},
    }
    # CPU
    fp["cpu_model"] = _run("grep -m1 'model name' /proc/cpuinfo | cut -d: -f2-").strip()
    flags = _run("grep -m1 ^flags /proc/cpuinfo | cut -d: -f2-").split()
    fp["cpu_flags_subset"] = sorted(f for f in flags if f in (
        "avx", "avx2", "avx512f", "avx512bw", "avx512vl", "fma", "sse4_2", "amx_bf16"))
    # glibc / libm
    fp["glibc"] = _run("ldd --version | head -1")
    # 依赖版本
    versions = {}
    for mod in ("numpy", "numba", "torch", "gym", "gymnasium", "scipy", "pandas"):
        try:
            m = __import__(mod)
            versions[mod] = getattr(m, "__version__", "<no __version__>")
        except Exception as e:  # noqa: BLE001
            versions[mod] = f"<not importable: {type(e).__name__}>"
    fp["versions"] = versions
    # torch 构建细节（BLAS / oneDNN / CPU capability）
    try:
        import torch
        fp["torch_config"] = torch.__config__.show()
        fp["torch_num_threads"] = torch.get_num_threads()
        fp["torch_num_interop_threads"] = torch.get_num_interop_threads()
    except Exception as e:  # noqa: BLE001
        fp["torch_config"] = f"<error: {e}>"
    # numba 目标 / 缓存
    try:
        import numba
        fp["numba_threading_layer"] = _run(
            "python -c \"import numba; print(numba.threading_layer())\"")
        fp["numba_version"] = numba.__version__
    except Exception:  # noqa: BLE001
        pass
    # pip freeze（完整依赖清单，便于事后逐项比对）
    fp["pip_freeze"] = _run("pip freeze")
    return fp


def compare(a: dict, b: dict) -> dict:
    """逐键比对两份指纹，给出**差异清单**（含"值得追"与"无关"两档）。

    分档判据（**可解释**，不是黑箱）：
      · `watch`：浮点相关维度（版本 / BLAS / oneDNN / CPU capability / glibc / 线程环境变量）
        —— 这些不同**可能**影响数值结果 ⇒ 需逐项排查；
      · `ignore`：与数值无关的维度（主机名、路径、时间戳、pip freeze 里的非数值包等）
        —— 不同**不影响**数值结果。
    ⚠️ 差异 ≠ 已定位差异来源（相关性 ≠ 因果）；本函数只做**事实比对**。
    """
    def _ver(fp):
        return fp.get("versions", {})

    def _blaspick(fp):
        out = {}
        for line in (fp.get("torch_config") or "").splitlines():
            s = line.strip()
            for key in ("oneAPI Math Kernel Library", "MKL-DNN", "CPU capability usage",
                        "BLAS_INFO=", "LAPACK_INFO="):
                if key in s:
                    out[key] = s[:200]
        return out

    watch = {}
    watch["versions"] = ({k: v for k, v in _ver(a).items() if _ver(b).get(k) != v})
    watch["torch_build"] = ({k: (v, _blaspick(b).get(k)) for k, v in _blaspick(a).items()
                             if _blaspick(b).get(k) != v})
    watch["cpu_model"] = None if a.get("cpu_model") == b.get("cpu_model") else (
        a.get("cpu_model"), b.get("cpu_model"))
    watch["cpu_flags"] = {
        "a": a.get("cpu_flags_subset"), "b": b.get("cpu_flags_subset"),
        "diff": sorted(set(a.get("cpu_flags_subset") or []) ^ set(b.get("cpu_flags_subset") or [])),
    }
    watch["glibc"] = None if a.get("glibc") == b.get("glibc") else (
        a.get("glibc"), b.get("glibc"))
    watch["thread_env"] = {k: (a.get("env", {}).get(k), b.get("env", {}).get(k))
                           for k in ENV_KEYS if a.get("env", {}).get(k) != b.get("env", {}).get(k)}
    ignore = {
        "hostname": None if a.get("hostname") == b.get("hostname") else (a.get("hostname"), b.get("hostname")),
        "platform": None if a.get("platform") == b.get("platform") else (a.get("platform"), b.get("platform")),
        "cwd": None if a.get("cwd") == b.get("cwd") else (a.get("cwd"), b.get("cwd")),
        "collected_at": None if a.get("collected_at") == b.get("collected_at") else "diff",
    }
    watch_diff = {
        "versions": watch["versions"],
        "torch_build": watch["torch_build"],
        "cpu_model": watch["cpu_model"],
        "cpu_flags_diff": watch["cpu_flags"]["diff"],
        "glibc": watch["glibc"],
        "thread_env_diff": watch["thread_env"],
    }
    return {
        "watch": watch_diff,
        "ignore": ignore,
        "n_watch_diffs": sum(1 for v in watch_diff.values() if v),
        "caveat": "差异≠已定位差异来源（相关性≠因果）；仅用于把'剩余候选'收窄成可判定清单。",
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--label", default="local")
    ap.add_argument("--out", default=None)
    ap.add_argument("--compare", default=None,
                    help="与另一份指纹 JSON 比对（给出差异清单）")
    args = ap.parse_args()

    if args.compare:
        a = json.loads(Path(args.out).read_text(encoding="utf-8")) if args.out else collect()
        b = json.loads(Path(args.compare).read_text(encoding="utf-8"))
        res = compare(a, b)
        print(json.dumps(res, ensure_ascii=False, indent=2))
        return 0

    fp = collect()
    fp["label"] = args.label
    out = Path(args.out) if args.out else (
        ROOT / "outputs/logs/env_fingerprint" / f"{args.label}_{time.strftime('%Y%m%d_%H%M%S')}.json")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(fp, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"[fingerprint] label={args.label} host={fp['hostname']} → {out}")
    print(f"[fingerprint] torch={fp['versions'].get('torch')} numpy={fp['versions'].get('numpy')} "
          f"numba={fp['versions'].get('numba')} glibc={fp['glibc'][:40]}")
    for line in fp.get("torch_config", "").splitlines():
        if any(k in line for k in ("oneAPI", "MKL-DNN", "CPU capability", "BLAS_INFO")):
            print("   ", line.strip())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
