"""守卫：环境指纹采集器 `collect_env_fingerprint.py` 的契约。

钉住：
    1. 采集内容覆盖**浮点相关**的关键维度（依赖版本 / torch 构建 BLAS+oneDNN /
       CPU capability / CPU flags / glibc / 线程环境变量 / pip freeze）——
       这些是把"剩余候选：其它浮点实现细节"收窄成**可判定清单**的唯一依据；
    2. 比对函数 `compare()` 给出**分档**结果（watch = 可能影响数值 / ignore = 无关）
       且带"差异≠因果"的免责；
    3. 比对器必须把 **BLAS / CPU capability / 版本** 这些关键项算进 watch，
       而不是笼统地"一切相同就没事"。

⚠️ 本守卫**不**验证任何跨机结论（那需要两机各采一次指纹 + 上云窗口）。
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts" / "probes"))

import collect_env_fingerprint as fp_mod  # noqa: E402


def test_collect_covers_float_relevant_dimensions():
    fp = fp_mod.collect()
    for k in ("versions", "torch_config", "env", "cpu_flags_subset", "glibc",
              "pip_freeze", "python", "platform"):
        assert k in fp, f"指纹缺关键维度 {k}"
    assert "numpy" in fp["versions"] and "torch" in fp["versions"]
    # torch 构建信息必须是一段文本（无 torch 的环境会退化成 "<error: ...>" 文本，
    # 具体内容断言放在"已采集的本地指纹"那条用例里——它固定在有 torch 的机器上采的）


def test_collect_is_read_only_and_json_serialisable():
    import json
    fp = fp_mod.collect()
    json.dumps(fp, ensure_ascii=False)  # 不得含不可序列化对象


def _fake(torch_line: str, ver_a: str, ver_b: str, flags_a, flags_b):
    def mk(cfg_line, ver, flags, host):
        return {
            "hostname": host, "platform": "Linux", "cwd": "/tmp", "collected_at": "t",
            "versions": {"numpy": ver, "torch": "2.5.1"},
            "torch_config": cfg_line,
            "cpu_model": "CPU X", "cpu_flags_subset": flags,
            "glibc": "ldd (GLIBC 2.39)", "env": {},
        }
    return mk(torch_line, ver_a, flags_a, "h1"), mk(torch_line, ver_b, flags_b, "h2")


def test_compare_flags_version_and_blas_differences():
    a, b = _fake("  - Intel(R) MKL-DNN v3.5.3\n  - CPU capability usage: AVX2\n"
                 "  - Build settings: BLAS_INFO=mkl",
                 "2.2.5", "2.2.6", ["avx2"], ["avx2", "avx512f"])
    res = fp_mod.compare(a, b)
    assert res["watch"]["versions"], "版本差异必须进 watch"
    assert "numpy" in res["watch"]["versions"]
    assert res["watch"]["cpu_flags_diff"] == ["avx512f"]
    assert res["n_watch_diffs"] >= 2


def test_compare_ignores_non_numeric_dimensions():
    same = _fake("  - CPU capability usage: AVX2", "2.2.5", "2.2.5", ["avx2"], ["avx2"])
    res = fp_mod.compare(*same)
    assert res["watch"]["versions"] == {}
    assert res["watch"]["cpu_flags_diff"] == []
    assert res["n_watch_diffs"] == 0
    # 主机名/路径差异属 ignore 档，不计入 watch
    assert res["ignore"]["hostname"] == ("h1", "h2")


def test_compare_carries_caveat():
    a, b = _fake("  - CPU capability usage: AVX2", "2.2.5", "2.2.5", ["avx2"], ["avx2"])
    res = fp_mod.compare(a, b)
    assert "相关性≠因果" in res["caveat"] or "相关性≠因果" in res["caveat"].replace(" ", "")


def test_shipped_local_fingerprint_is_valid():
    """已采集的本地指纹必须结构完整（否则比对器无从下手）。"""
    cands = sorted((ROOT / "outputs/logs/env_fingerprint").glob("local_*.json"))
    assert cands, "缺本地环境指纹（应已采集）"
    import json
    d = json.loads(cands[-1].read_text(encoding="utf-8"))
    for k in ("versions", "torch_config", "env", "cpu_flags_subset", "glibc"):
        assert k in d
    assert d["versions"]["torch"].startswith("2.5.1")
    # 指纹必须带 BLAS / oneDNN / CPU capability 三类构建信息（浮点相关的核心维度）
    cfg = d.get("torch_config") or ""
    assert "BLAS_INFO=" in cfg or "MKL-DNN" in cfg or "oneAPI" in cfg
    assert "CPU capability" in cfg
