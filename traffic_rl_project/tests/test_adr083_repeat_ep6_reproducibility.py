"""Lock the diagnostics 19.42 verdict: on this machine the ep6 full-run fast
eval is BIT-IDENTICAL across repeats, so the 17.7% gap against the cloud
reading is a CROSS-MACHINE difference, not a code difference.

WHY THIS FILE EXISTS (2026-11-21, diagnostics 19.42):
    The decisive comparison had three possible explanations for
    "local official ep6 = 1478.85 vs cloud official ep6 = 1256.72 (17.7% apart,
    and even the failing column differs)":
      (a) the local run is not reproducible,
      (b) the cloud ran different code,
      (c) the two ran the same code on different machines.

    The repeat control (scripts/probes/run_repeat_ep6_check.sh, same ckpt, same
    parameters, current code) settled it: EVERY shared numeric field comes out
    bit-identical -- peak_coupler_kN = 1478.8515764313422 in both runs, along
    with viol / ab_steps / band_rate / gap errors. So (a) is excluded and,
    combined with the configuration-side evidence (the eval config was created
    at 15:13 on 2026-11-20, so the cloud code necessarily included
    ADR-076/077/080/081 and the stale metadata.git_commit was a mislabelled
    field), (b) is excluded too. The difference is (c): cross-machine.

    A consequence that matters more than the 17.7% itself: the FAILING COLUMN
    flips across machines (both local runs put the peak in the middle column,
    the cloud run put it in the tail column). Hence "which column fails" is
    NOT a stable feature and must never be used as a fixed target.

    The artifacts live under outputs/ (gitignored, non-regenerable evidence),
    so this test SKIPS when they are absent.
"""
import json
from pathlib import Path

import pytest

ROOT = Path(__file__).parents[1]
DECOMPOSE = ROOT / "outputs/results/decompose"
FIRST = DECOMPOSE / "eval_decompose_decompose_m1_ms31500_adr083_official_ep1_ep7_20261121_det_ep6.json"
REPEAT = DECOMPOSE / "eval_decompose_decompose_m1_ms31500_adr083_repeat_ep6_det_ep6.json"

pytestmark = pytest.mark.skipif(
    not (FIRST.exists() and REPEAT.exists()),
    reason=f"ADR-083 ep6 evaluation artifacts not present under {DECOMPOSE}",
)


def _results(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))["results"]["decompose_M1_rl"]


def test_repeat_is_bit_identical_to_first_run():
    """The decisive fact: every shared numeric metric must match to the last
    bit. If this breaks, the local fast eval is no longer reproducible and
    the 19.42 attribution has to be re-opened."""
    a, b = _results(FIRST), _results(REPEAT)
    shared = [k for k, v in a.items()
              if isinstance(v, (int, float)) and not isinstance(v, bool) and k in b]
    assert shared, "no shared numeric metrics found -- artifact layout changed"
    diffs = {k: (a[k], b[k]) for k in shared if a[k] != b[k]}
    assert not diffs, f"repeat run differs from first run: {diffs}"
    # and the peak must be exactly the recorded value
    assert a["peak_coupler_kN"] == 1478.8515764313422
    assert b["peak_coupler_kN"] == 1478.8515764313422


def test_break_magnitude_is_stable_across_repeats():
    """Both local runs break the coupler limit by a wide margin; the stable
    part of the reading is 'whether it breaks and by how much', NOT which
    column breaks (that flips across machines, see 19.42)."""
    a, b = _results(FIRST), _results(REPEAT)
    assert a["peak_coupler_kN"] > 1200.0 and b["peak_coupler_kN"] > 1200.0
    assert a["viol"] == b["viol"]
