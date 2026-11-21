"""守卫：跨机漂移带分析器 `analyze_cross_machine_band.py` 的契约。

钉住：
    1. 工具必须做**配对比较**（同一 ckpt 的云端 vs 本地读数），而不是拿
       两批互不对应的读数相减——否则得到的"漂移带"是假的。
    2. **主指标口径与工程口径必须分列**（§19.49 的核心发现：主指标内部
       稳健性极不均匀，`band_rate` ±0.15% vs `gap_err_mean_abs_m` ±53.5%）。
    3. 必须输出**集间秩稳定性**（最好→最差的排序在跨机下是否保持）——
       这是"能不能用评估态读数挑 ckpt"的真正判据，比绝对值稳不稳更硬。
    4. 判决必须区分**两条威胁**：跨机差异（§19.49）vs 同机受控扰动（§19.48），
       **不得互相替代**。
    5. 取数必须走**产物的真实嵌套结构**（`results.decompose_M1_rl`），
       不得假设指标在顶层——否则会静默产出"全 None"的假结果。

⚠️ 本守卫**不跑仿真**，只锁工具契约；实数结果由产物回放得出。
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts" / "probes"))

import analyze_cross_machine_band as cmb  # noqa: E402


def test_metrics_table_separates_engineering_and_primary_calibers():
    """METRICS 必须同时含两套口径，且主指标三个量齐全。"""
    cal = {}
    for key, _ck, _u, _d, caliber in cmb.METRICS:
        cal.setdefault(caliber, []).append(key)
    assert "工程口径" in cal and "主指标口径" in cal
    for k in ("band_rate", "gap_err_mean_abs_m", "gap_err_peak_abs_m", "gap_min_m"):
        assert k in cal["主指标口径"], f"主指标口径缺 {k}"
    for k in ("peak_coupler_kN", "viol"):
        assert k in cal["工程口径"], f"工程口径缺 {k}"


def test_get_reads_real_nested_result_structure():
    """_get 必须能穿透 results.decompose_M1_rl 取到指标（不得静默返回 None）。"""
    d = {"metadata": {}, "args": {},
         "results": {"decompose_M1_rl": {"band_rate": 0.9067, "viol": 5143}}}
    assert cmb._get(d, "band_rate") == 0.9067
    assert cmb._get(d, "viol") == 5143
    # 顶层直挂也要支持
    assert cmb._get({"peak_coupler_kN": 1.0}, "peak_coupler_kN") == 1.0
    # 缺失键返回 None（不抛异常）
    assert cmb._get(d, "not_a_key") is None


def test_tool_is_paired_by_episode_not_unpaired_batches():
    """必须按 ep 配对（本地 epN ↔ 云端 epN），且配对集固定为有双侧产物的三个 ckpt。"""
    import inspect
    src = inspect.getsource(cmb.main)
    assert "for ep in (2, 4, 6)" in src
    # 本地与云端都按同一个 ep 取，再逐指标配对
    assert "_local_path(ep)" in src and "_cloud_path(ep)" in src


def test_outputs_both_band_and_rank_stability():
    """必须同时产出漂移带（幅度）与秩稳定性（排序）。"""
    import inspect
    src = inspect.getsource(cmb.main)
    assert "cross_machine_bands" in src
    assert "rank_stability" in src
    assert '"stable"' in src


def test_verdict_distinguishes_two_threat_branches():
    """判决必须区分"跨机"与"同机受控扰动"两条威胁，不得互相替代。"""
    doc = cmb.__doc__ or ""
    assert "跨机" in doc and "同机" in doc
    import inspect
    src = inspect.getsource(cmb.main)
    assert "不可互相替代" in src or "不可互相替代" in doc


def test_no_criterion_boundary_is_declared():
    """必须声明不产出峰值/安全判据、读数不得互引。"""
    doc = cmb.__doc__ or ""
    assert "不产出任何峰值/安全判据" in doc
    assert "不得互引" in doc


def test_signal_reference_points_to_19_47():
    """必须锚定 §19.47 的信号幅度，作为判决的参照。"""
    assert any("term_speed_band_sum" in k for k in cmb.SIGNAL)
    assert any("gap_err_mean_abs_m" in k for k in cmb.SIGNAL)
    assert any("band_rate" in k for k in cmb.SIGNAL)
    doc = cmb.__doc__ or ""
    assert "19.47" in doc
