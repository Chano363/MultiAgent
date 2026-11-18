"""COVER 快评判据单测（G1 第 4 问的协议正确性）。"""
import json

from src.evaluation.cover_quick_eval import judge, parse_eval_json


def _write(tmp_path, peak=1300.0, band=0.88, rear_end=0):
    p = tmp_path / "eval.json"
    p.write_text(json.dumps({
        "metadata": {},
        "args": {},
        "results": {"peak_coupler_kN": peak, "band_rate": band,
                    "rear_end_steps": rear_end},
    }), encoding="utf-8")
    return p


def test_parse_wrapper(tmp_path):
    m = parse_eval_json(_write(tmp_path, peak=1234.5, band=0.87, rear_end=3))
    assert m == {"peak_kN": 1234.5, "band": 0.87, "rear_end": 3}


def test_pass(tmp_path):
    r = judge(_write(tmp_path, peak=1300, band=0.88))
    assert r["pass"] and r["reason"] == ""


def test_band_break(tmp_path):
    r = judge(_write(tmp_path, peak=1300, band=0.84))
    assert not r["pass"] and "band" in r["reason"]


def test_rear_end_break(tmp_path):
    r = judge(_write(tmp_path, peak=1300, band=0.90, rear_end=5))
    assert not r["pass"] and "穿透" in r["reason"]


def test_peak_safety_break(tmp_path):
    r = judge(_write(tmp_path, peak=1501, band=0.90))
    assert not r["pass"] and "安全线" in r["reason"]


def test_peak_rise_break(tmp_path):
    r = judge(_write(tmp_path, peak=1100, band=0.90), prev_peak_kN=1000)
    assert not r["pass"] and "上行" in r["reason"]


def test_peak_rise_within_tolerance(tmp_path):
    r = judge(_write(tmp_path, peak=1015, band=0.90), prev_peak_kN=1000)
    assert r["pass"], r["reason"]


def test_multiple_reasons(tmp_path):
    r = judge(_write(tmp_path, peak=1600, band=0.80, rear_end=2), prev_peak_kN=1000)
    assert not r["pass"]
    for kw in ("穿透", "安全线", "band", "上行"):
        assert kw in r["reason"]
