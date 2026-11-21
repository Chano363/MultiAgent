"""守卫：训练期同向性判定工具 `analyze_train_col_collinearity.py` 的契约。

钉住：
    1. 工具存在且可导入，`analyze()` 对**合成数据**能出结构完整的判决
       （对照表 / Spearman / 单阈值可分性 / 边界声明）；
    2. **缺逐列键的落盘必须显式报错**（而不是静默产出空判决）——
       否则窗口没带 §19.45 通道时会被误读成"无相关"；
    3. 边界声明不得被删（n 小不得主张显著、形态量跨机器翻转、不产出峰值判据）。

⚠️ 本守卫用**合成数据**只验工具逻辑，**不构成任何证据**；
    真实判决须等带落盘的重训窗口（须 owner 按红线 1 批复四件套）。
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts" / "probes"))

import analyze_train_col_collinearity as tool  # noqa: E402


def _synthetic():
    """合成"训练期"逐列量（与评估态同向），仅用于验工具逻辑。"""
    ev = {
        ep: {
            "file": f"synthetic_ep{ep}.json",
            "peak_coupler_kN": 1000.0 + 10 * ep,
            "train_peak_coupler_kN": [900.0 + 10 * ep, 910.0 + 10 * ep, 905.0 + 10 * ep],
            "train_coupler_viol": [0.0, 0.0, 0.0],
        }
        for ep in tool.EPISODES
    }
    train = {
        "file": "synthetic.json",
        "col_peak_kN": [[900.0 + 10 * ep, 910.0 + 10 * ep, 905.0 + 10 * ep]
                        for ep in tool.EPISODES],
        "col_viol": [[0.0, 0.0, 0.0] for _ in tool.EPISODES],
    }
    return train, ev


def test_tool_module_exposes_expected_entrypoints():
    assert hasattr(tool, "analyze")
    assert hasattr(tool, "load_train")
    assert hasattr(tool, "spearman")
    assert tool.BREAK_EP == 6 and tool.NORMAL_EP == 7 and tool.FALSE_POS_EP == 3


def test_spearman_basic_behaviour():
    a = [1, 2, 3, 4, 5]
    b = [2, 4, 6, 8, 10]
    assert abs(tool.spearman(a, b) - 1.0) < 1e-9
    assert abs(tool.spearman(a, list(reversed(b))) + 1.0) < 1e-9
    # 常量序列无区分度 ⇒ None（不得当 0 用）
    assert tool.spearman(a, [1, 1, 1, 1, 1]) is None


def test_analyze_returns_complete_verdict_structure():
    train, ev = _synthetic()
    res = tool.analyze(train, ev)
    assert res["episodes"] == tool.EPISODES
    assert len(res["rows"]) == len(tool.EPISODES)
    for r in res["rows"]:
        assert len(r["train_col_peak_kN"]) == 3
        assert len(r["eval_col_peak_kN"]) == 3
        assert r["train_total_peak_kN"] == max(r["train_col_peak_kN"])
    # 相关性表必须覆盖"训练期逐列量 × 评估态量"
    assert "train_col1_peak_kN~eval_total_peak" in res["spearman"]
    assert "train_spread_peak_kN~eval_total_peak" in res["spearman"]
    # 可分性表存在
    assert "train_total_peak_kN" in res["separability"]
    # 边界声明必须在
    joined = " ".join(res["caveats"])
    assert "不得主张统计显著" in joined
    assert "跨机器" in joined
    assert "不产出任何峰值/安全判据" in joined


def test_load_train_rejects_history_without_column_keys(tmp_path):
    p = tmp_path / "train_history_x.json"
    p.write_text('{"rewards": [1.0], "peak_coupler_kN": [1.0], "violations": [0.0]}',
                 encoding="utf-8")
    with pytest.raises(KeyError) as ei:
        tool.load_train(p, len(tool.EPISODES))
    assert "col_peak_coupler_kN" in str(ei.value)


def test_load_train_rejects_missing_file(tmp_path):
    with pytest.raises(FileNotFoundError) as ei:
        tool.load_train(tmp_path / "nope.json", len(tool.EPISODES))
    assert "带逐列落盘" in str(ei.value)


def test_load_train_rejects_ragged_rows(tmp_path):
    import json
    p = tmp_path / "train_history_x.json"
    p.write_text(json.dumps({
        "col_peak_coupler_kN": [[1.0, 2.0, 3.0], [1.0, 2.0]],
        "col_violations": [[0.0, 0.0, 0.0], [0.0, 0.0, 0.0]],
    }), encoding="utf-8")
    with pytest.raises(ValueError):
        tool.load_train(p, len(tool.EPISODES))
