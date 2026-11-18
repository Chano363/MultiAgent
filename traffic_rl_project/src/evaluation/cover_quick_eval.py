"""COVER 投的确定性快评判定（G1 第 4 问"快评协议进脚本"的纯逻辑）。

只读快评 JSON（evaluate_decompose 产物），按 ADR-071/073 判据判断是否破线：
  - 零穿透：rear_end_steps == 0（硬安全门）
  - band >= 0.85（快评停训线，终验才用 ADR-071 的 0.90）
  - peak 较上次快评上行 > 2% 噪声带（退化信号）
  - 安全线 peak <= 1500 kN（硬安全门）
任一破线 → 返回 break_reason（调用方触发 watchdog 停机）。

纯函数，不连云、不改状态，便于单测。JSON 字段来自 evaluate_decompose.py line 455/497/523：
results.peak_coupler_kN / results.band_rate / results.rear_end_steps。
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Optional

BAND_FLOOR = 0.85          # 快评停训线（终验 0.90 见 ADR-071）
PEAK_UPLIMIT_KN = 1500.0   # 硬安全线（ADR-071）
PEAK_RISE_TOL = 0.02       # 相对上次快评上行 2% 噪声带


def parse_eval_json(path: str | Path) -> dict:
    """读 evaluate_decompose 产物，容错 results/metadata 包装与裸 dict。

    【修复 2026-11-18 护栏失明】evaluate_decompose.py L716 实际写出的结构是
    ``{"results": {"decompose_M1_rl": {...}, "decompose_M0_rule": {...}}}``
    （results 以方法名为键）。旧实现直接 results.get("peak_coupler_kN") 永远
    miss → peak/band 解析为 nan → judge 三条比较遇 nan 全为 False →
    护栏从未能真正判破线（ep10/ep20 verdict=PASS||nan 实证）。
    现兼容扁平结构，嵌套结构自动钻取到含指标的方法字典。
    """
    d = json.loads(Path(path).read_text(encoding="utf-8"))
    results = d.get("results", d)
    if isinstance(results, list):
        results = results[0] if results else {}
    if isinstance(results, dict) and "peak_coupler_kN" not in results:
        m1 = results.get("decompose_M1_rl")
        if isinstance(m1, dict):
            results = m1
        else:  # 兕底：任一含指标字段的子字典
            for v in results.values():
                if isinstance(v, dict) and "peak_coupler_kN" in v:
                    results = v
                    break
    peak = results.get("peak_coupler_kN")
    band = results.get("band_rate")
    rear_end = results.get("rear_end_steps")
    return {
        "peak_kN": float(peak) if peak is not None else float("nan"),
        "band": float(band) if band is not None else float("nan"),
        "rear_end": int(rear_end) if rear_end is not None else -1,
    }


def judge(eval_json: str | Path, prev_peak_kN: Optional[float] = None) -> dict:
    """返回 {pass: bool, reason: str, metrics: {...}}。reason 为空表示未破线。

    【fail-closed】peak/band 为 nan（字段缺失/结构漂移）时判不通过——
    杀护栏绝不允许静默放行；调用方（watch）会触发自停机，宁停不赌。
    """
    m = parse_eval_json(eval_json)
    import math

    if math.isnan(m["peak_kN"]) or math.isnan(m["band"]):
        return {
            "pass": False,
            "reason": "metrics 不可解析（peak/band=nan，JSON 结构漂移？）",
            "metrics": m,
        }
    reasons = []
    if m["rear_end"] != 0:
        reasons.append(f"穿透 rear_end_steps={m['rear_end']}")
    if m["peak_kN"] > PEAK_UPLIMIT_KN:
        reasons.append(f"超安全线 peak={m['peak_kN']:.1f}>{PEAK_UPLIMIT_KN}")
    if m["band"] < BAND_FLOOR:
        reasons.append(f"band={m['band']:.4f}<{BAND_FLOOR}")
    if prev_peak_kN is not None and prev_peak_kN > 0:
        rise = (m["peak_kN"] - prev_peak_kN) / prev_peak_kN
        if rise > PEAK_RISE_TOL:
            reasons.append(f"peak上行 {rise:.1%}>{PEAK_RISE_TOL:.0%}")
    return {
        "pass": not reasons,
        "reason": "; ".join(reasons),
        "metrics": m,
    }
