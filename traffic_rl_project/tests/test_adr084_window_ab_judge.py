"""守卫：第 11 投 A/B 差值判决器（阈值前置写死 + 五种判决分支正确）。

⚠️ 本守卫不判科学结论，只钉：
  ① 阈值写死在脚本里（不得事后调）；
  ② 五种判决分支在合成数据上**逐一命中**（防止符号写反这类实现 bug——
     实现时确实踩过：REVERSED 的 rel_gap 符号写反过）。
"""
import json
import pathlib
import subprocess
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "probes" / "judge_window_ab.py"


def _mk(d, name, gap, peak, viol, band=0.906):
    p = pathlib.Path(d) / name
    p.write_text(json.dumps({"results": {"decompose_M1_rl": {
        "peak_coupler_kN": peak, "viol": viol, "band_rate": band,
        "gap_err_mean_abs_m": gap, "gap_err_peak_abs_m": gap * 2,
        "gap_min_m": 127.0, "rear_end_steps": 0}}}), encoding="utf-8")
    return p


def _run(tmp_path, a, b):
    _mk(tmp_path, "eval_decompose_decompose_m1_ms31500_wA_det_ep2.json", *a)
    _mk(tmp_path, "eval_decompose_decompose_m1_ms31500_wB_det_ep2.json", *b)
    r = subprocess.run(
        [sys.executable, str(SCRIPT),
         "--a-glob", str(tmp_path / "*_wA_det_ep*.json"),
         "--b-glob", str(tmp_path / "*_wB_det_ep*.json")],
        capture_output=True, text=True)
    line = [l for l in r.stdout.splitlines() if "VERDICT" in l]
    return line[0].split("=")[-1].strip() if line else "NONE"


def test_thresholds_are_hardcoded():
    src = SCRIPT.read_text(encoding="utf-8")
    assert "GAP_TARGET_MAX = 130.0" in src
    assert "PEAK_NOT_WORSE_TOL = 0.02" in src
    assert "GAP_NOISE_TOL = 0.05" in src
    assert "VIOL_CAP = 5143.0" in src


def test_verdict_branches(tmp_path):
    cases = [
        ("INTERVENTION_CONFIRMED", (60, 1150, 3000), (612, 1169, 2649)),
        ("PARTIAL_TRADE_OFF", (60, 1400, 3000), (612, 1169, 2649)),
        ("REVERSED", (900, 1160, 2600), (612, 1169, 2649)),
        ("INTERVENTION_NOT_CONFIRMED", (610, 1170, 2600), (612, 1169, 2649)),
        ("PARTIAL_VIOL_BLOWUP", (60, 1150, 20000), (612, 1169, 2649)),
    ]
    for want, a, b in cases:
        got = _run(tmp_path, a, b)
        assert got == want, f"期望 {want}，实得 {got}（A={a} B={b}）"


def test_aborts_without_matched_episodes(tmp_path):
    _mk(tmp_path, "eval_decompose_decompose_m1_ms31500_wA_det_ep2.json", 60, 1150, 3000)
    _mk(tmp_path, "eval_decompose_decompose_m1_ms31500_wB_det_ep4.json", 612, 1169, 2649)
    r = subprocess.run(
        [sys.executable, str(SCRIPT),
         "--a-glob", str(tmp_path / "*_wA_det_ep*.json"),
         "--b-glob", str(tmp_path / "*_wB_det_ep*.json")],
        capture_output=True, text=True)
    assert r.returncode == 2 and "ABORT" in r.stdout, "集号不配对应 ABORT"


def test_ticket_and_diag_reference_the_thresholds():
    brief = (ROOT / "docs" / "reports" / "adr084_window_open_checklist.md").read_text(encoding="utf-8")
    diag = (ROOT / "docs" / "logs" / "diagnostics" / "DIAGNOSTICS_2026-11.md").read_text(encoding="utf-8")
    assert "5143" in brief, "票据须写明超限步上限"
    assert "5%" in brief, "票据须写明可区分差异门槛"
    assert "judge_window_ab.py" in diag or "A/B" in diag
