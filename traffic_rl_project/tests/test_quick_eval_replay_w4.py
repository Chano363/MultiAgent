"""Replay the W4 quick-eval guard verdicts against the REAL product JSONs.

WHY (2026-11-21):
    G1 lesson from the 4th window: "判据单测必须用真产物 JSON 回放" -- the
    quick-eval guard was once blind (it parsed a fictional flat structure,
    got nan, and all three comparisons silently passed). It was fixed with
    drill-down + fail-closed + unit tests, but the unit tests use synthetic
    fixtures. Nothing then re-checked that the guard, AS IT STANDS NOW,
    still reproduces the verdicts that were actually recorded for W4 and that
    ended up in the diagnostics and the pipeline as facts.

    If a later edit to parse_eval_json / judge silently changed a verdict
    (e.g. stopped drilling into the nested method dict, or inverted the rise
    comparison), the recorded W4 narrative -- "ep2 PASS, ep4 PASS, ep6 BREAK
    with peak up 11.0%" -- would silently stop matching the artifacts, and
    every downstream attribution built on it would be wrong.

    This test replays the three REAL W4 products through the current guard
    code and pins the verdict chain and the numbers that were written into
    the docs. It is the artifact-level counterpart of the unit tests.

    The products live under outputs/ (gitignored, ~10 GB of non-regenerable
    evidence), so this test SKIPS when they are absent rather than failing.
    On the owner's machine they are present and the guard actually runs.
"""
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
DECOMPOSE = ROOT / "outputs" / "results" / "decompose"
W4 = "w4nincrgatecaprel_w4full_20261120"

PRODUCTS = {
    "ep2": DECOMPOSE / f"eval_decompose_decompose_m1_ms31500_{W4}_det_ep2.json",
    "ep4": DECOMPOSE / f"eval_decompose_decompose_m1_ms31500_{W4}_det_ep4.json",
    "ep6": DECOMPOSE / f"eval_decompose_decompose_m1_ms31500_{W4}_det_ep6.json",
}

pytestmark = pytest.mark.skipif(
    not all(p.exists() for p in PRODUCTS.values()),
    reason=f"real W4 quick-eval products not present under {DECOMPOSE}",
)


def _judge_chain():
    from src.evaluation.cover_quick_eval import judge

    prev = None
    out = {}
    for ep in ("ep2", "ep4", "ep6"):
        v = judge(PRODUCTS[ep], prev)
        out[ep] = v
        prev = v["metrics"]["peak_kN"]
    return out


def test_w4_verdict_chain_is_reproduced():
    """ep2 PASS -> ep4 PASS -> ep6 BREAK, exactly as recorded in the docs."""
    res = _judge_chain()
    assert res["ep2"]["pass"] is True, res["ep2"]
    assert res["ep4"]["pass"] is True, res["ep4"]
    assert res["ep6"]["pass"] is False, res["ep6"]
    assert "peak上行" in res["ep6"]["reason"], res["ep6"]["reason"]
    assert "11.0%" in res["ep6"]["reason"], res["ep6"]["reason"]


def test_w4_metrics_match_the_documented_numbers():
    """Pin the artifact values that the docs quote as W4 facts."""
    res = _judge_chain()
    # PIPELINE.md / DIAGNOSTICS_2026-11.md quote these exact readings.
    assert res["ep2"]["metrics"]["peak_kN"] == pytest.approx(1179.23, abs=0.01)
    assert res["ep4"]["metrics"]["peak_kN"] == pytest.approx(1132.40, abs=0.01)
    assert res["ep6"]["metrics"]["peak_kN"] == pytest.approx(1256.72, abs=0.01)
    for ep in ("ep2", "ep4", "ep6"):
        m = res[ep]["metrics"]
        assert m["rear_end"] == 0, f"{ep} penetration: {m}"
        assert m["band"] > 0.90, f"{ep} band: {m}"


def test_guard_fails_closed_on_structure_drift(tmp_path):
    """The blind-guard failure mode must stay closed: nan => not passing."""
    from src.evaluation.cover_quick_eval import judge

    bad = tmp_path / "drifted.json"
    bad.write_text(
        '{"results": {"decompose_M1_rl": {"totally_unrelated": 1}}}', encoding="utf-8"
    )
    v = judge(bad, None)
    assert v["pass"] is False
    assert "nan" in v["reason"]
