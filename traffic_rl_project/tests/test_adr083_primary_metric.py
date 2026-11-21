"""守卫：§19.47「训练期量 → 评估态主指标（列距/速度带）」相关性判决。

钉住四件事（防止口径被悄悄改掉）：
    1. **代价型训练期标量在主指标上反向**：`gap_err_mean` ~ 评估态 `gap_err_mean_abs_m`
       为负且留一法稳定反号；`gap_min_m` ~ 评估态 `gap_min_m` 同。
    2. **唯一稳定同向信号 = 奖励分量 `speed_band_sum`**：与评估态 gapMean / gapPeak / band_rate
       同向且留一法稳定（这是主指标口径下唯一可用的在线止损信号，且**已在既有落盘里**）。
    3. **`gap_eff` 是"车钩—几何权衡"指示器、不是列距质量指示器**：它与 peak/viol 同向，
       却与列距主指标反向 ⇒ 两者不可互换（§19.41 的"gap_eff 唯一同向"只在峰值口径成立）。
    4. **ep6 在主指标上不是最差集**（真正最差是 ep1）⇒ "ep6 破线"是工程口径事件，
       不得当作主指标退化。

⚠️ n = 7 ⇒ 方向性判决，不得主张统计显著（守卫只锁方向与结构，不锁数值大小）。
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts" / "probes"))

import analyze_primary_metric_correlation as pm  # noqa: E402

OUT = ROOT / "outputs/logs/adr083_primary_metric_corr/primary_metric_corr.json"


def _data():
    assert OUT.exists(), "缺 §19.47 相关性产物（先跑 analyze_primary_metric_correlation.py）"
    return json.loads(OUT.read_text(encoding="utf-8"))


def test_corr_keys_exist():
    d = _data()
    for k in ("gap_err_mean~gap_err_mean_abs_m",
              "gap_min_m~gap_min_m",
              "term_speed_band_sum~gap_err_mean_abs_m",
              "term_speed_band_sum~gap_err_peak_abs_m",
              "term_speed_band_sum~band_rate",
              "term_gap_eff_sum~peak_coupler_kN",
              "term_gap_eff_sum~gap_err_mean_abs_m"):
        assert k in d["spearman"], f"缺相关项 {k}"


def test_cost_like_train_scalars_are_reversed_on_main_metrics():
    d = _data()
    c = d["spearman"]
    for key in ("gap_err_mean~gap_err_mean_abs_m", "gap_min_m~gap_min_m"):
        v = c[key]
        assert v["rho"] < 0, f"{key} 方向被翻转（应反向）"
        assert v["loo_sign_stable"] is True, f"{key} 留一法符号不稳定"
    # 峰值口径的既有结论（§19.41）不得被改写
    assert c["peak_coupler_kN~peak_coupler_kN"]["rho"] < 0


def test_speed_band_sum_is_the_only_stable_same_direction_main_signal():
    d = _data()
    c = d["spearman"]
    for key in ("term_speed_band_sum~gap_err_mean_abs_m",
                "term_speed_band_sum~gap_err_peak_abs_m",
                "term_speed_band_sum~band_rate"):
        v = c[key]
        assert v["rho"] > 0.5, f"{key} 同向性丢失（rho={v['rho']}）"
        assert v["loo_sign_stable"] is True, f"{key} 留一法符号不稳定"


def test_gap_eff_is_tradeoff_indicator_not_spacing_quality():
    d = _data()
    c = d["spearman"]
    assert c["term_gap_eff_sum~peak_coupler_kN"]["rho"] > 0
    assert c["term_gap_eff_sum~gap_err_mean_abs_m"]["rho"] < 0


def test_ep6_is_not_worst_on_main_metrics():
    d = _data()
    t = d["table"]
    # 评估态列距最差 = ep1；ep6 在 gapMean 上排第 4、gapPeak 第 3
    assert t["1"]["eval_gap_err_mean_abs_m"] == max(
        v["eval_gap_err_mean_abs_m"] for v in t.values())
    assert t["1"]["eval_gap_err_peak_abs_m"] == max(
        v["eval_gap_err_peak_abs_m"] for v in t.values())
    assert t["6"]["eval_peak_kN"] == max(v["eval_peak_kN"] for v in t.values())
    # ep6 的主指标必须优于 ep1
    assert t["6"]["eval_gap_err_mean_abs_m"] < t["1"]["eval_gap_err_mean_abs_m"]
    assert t["6"]["eval_gap_err_peak_abs_m"] < t["1"]["eval_gap_err_peak_abs_m"]


def test_single_threshold_separates_worst_main_set_without_false_positive():
    """speed_band_sum 作代价型阈值，须命中主指标最差集 ep1 且不误杀最好集 ep5。"""
    tr, terms = pm.load_train()
    ev = pm.load_eval()
    train_cands, eval_main, _ = pm.build_vectors(tr, terms, ev)
    vals = train_cands["term_speed_band_sum"]
    res = pm.best_threshold(vals, pm.EPISODES, target_ep=1, false_pos_eps=[5])
    assert res is not None, "speed_band_sum 无法把主指标最差集 ep1 分出"
    assert 1 in res["hit_eps"]
    assert res["false_positive_eps"] == []


def test_diagnostic_1947_records_the_verdict():
    p = ROOT / "docs/logs/diagnostics/DIAGNOSTICS_2026-11.md"
    txt = p.read_text(encoding="utf-8")
    assert "§19.47" in txt
    assert "speed_band_sum" in txt
    assert "主指标" in txt
    # 必须写清 n=7 与跨侧不可比大小
    assert "不得主张统计显著" in txt
    assert "不可跨侧比大小" in txt
