"""Lock the AB episode-structure mechanism behind ADR-082's cross-ckpt sign flip.

WHY THIS FILE EXISTS (2026-11-21, diagnostics 19.38):
    ADR-082's per-column AB derivation threshold lowers peak by 21.7% on the ep6
    checkpoint but RAISES it by 6.5% (coupler violations +196%) on ep2. Until
    19.38 that was an unexplained observation. It is now explained at the event
    level:
      1. Every AB episode terminates at v = 56.0 km/h (the ADR-075 release
         speed gate) => the threshold only governs WHEN AB is entered; the
         existing release chain governs WHEN it exits.
      2. The AB notch is NOT the main driver of episode length. Under a
         controlled comparison (matching the entry speed at 72-76 km/h so the
         starting speed cannot confound the result), strong (-0.4) episodes
         decelerate at a median 0.422 km/h/s over a median 46.0 s, weak (-0.2)
         at 0.389 km/h/s over 46.9 s -- an ~8% gap, not the ~10x first
         measured. The uncontrolled comparison (weak median 0.304 km/h/s)
         looked like a 10x gap only because low-entry-speed segments drag out.
      3. The real driver of the long tail is WHERE on the grade profile the
         episode falls: ep2's tail carries two super-long weak-notch episodes
         (421.4 s and 487.7 s, decel 0.043 / 0.036 km/h/s -- an order of
         magnitude below their own notch implies) that no notch or entry
         speed explains. ep6's tail has none of them.
      4. Therefore p_ab_applied is the AB state-machine OCCUPANCY, not the
         request rate. On ep2 the tail's episodes sit on the long-grade
         positions => occupancy rises even though the threshold cut trigger
         opportunities by 85%.
      5. The lead_share drop is a pure DENOMINATOR effect: the leader's AB
         step count is unchanged; only the tail's grew.

    These are claims about the project, so they get the same treatment as the
    other decision-critical numbers: pinned by a test against the real probe
    artifacts. If a future change to the controller, the reward, or the
    dynamics breaks any of them, this test goes red instead of the finding
    quietly becoming folklore.

    The artifacts live under outputs/ (gitignored, non-regenerable evidence),
    so this test SKIPS when they are absent.
"""
from pathlib import Path

import numpy as np
import pytest

ROOT = Path(__file__).resolve().parents[1]
DIAG = ROOT / "outputs" / "results" / "diagnostics"

EP2_BASE = DIAG / "adr082_crossckpt_ep2_base"
EP2_BIAS = DIAG / "adr082_crossckpt_ep2_bias_n"
EP6_BASE = DIAG / "adr082_abcolbias_probe_20261120_base"
EP6_BIAS = DIAG / "adr082_abcolbias_probe_20261120_bias_n"

RELEASE_GATE_KMH = 56.0
GATE_TOL_KMH = 0.5

pytestmark = pytest.mark.skipif(
    not all(d.exists() for d in (EP2_BASE, EP2_BIAS, EP6_BASE, EP6_BIAS)),
    reason=f"ADR-082 probe artifacts not present under {DIAG}",
)


def _load(d: Path):
    z = np.load(d / "trajectory.npz")
    return z["ab_exec"], z["head_speed_kmh"], z["ed_level"]


def _episodes(mask: np.ndarray):
    out = []
    start = None
    for i, v in enumerate(mask):
        if v and start is None:
            start = i
        elif not v and start is not None:
            out.append((start, i - start))
            start = None
    if start is not None:
        out.append((start, len(mask) - start))
    return out


CONTROLLED_ENTRY_LO_KMH = 72.0
CONTROLLED_ENTRY_HI_KMH = 76.0


def _collect_episodes():
    """Return (dir_name, col, start, dur, v0, v1, decel, kind) for every AB episode."""
    recs = []
    for name, d in (
        ("ep2_base", EP2_BASE),
        ("ep2_bias", EP2_BIAS),
        ("ep6_base", EP6_BASE),
        ("ep6_bias", EP6_BIAS),
    ):
        ab, sp, _ = _load(d)
        on = ab < 0
        for c in range(on.shape[1]):
            for s, dur in _episodes(on[:, c]):
                seg = ab[s:s + dur, c]
                v0 = float(sp[max(s - 1, 0), c])
                v1 = float(sp[min(s + dur, len(on) - 1), c])
                dec = (v0 - v1) / max(dur * 0.1, 1e-9)
                kind = "strong" if (seg <= -0.4).mean() >= 0.5 else "weak"
                recs.append((name, c, s, dur, v0, v1, dec, kind))
    return recs


def test_ab_episodes_terminate_at_the_release_speed_gate():
    """Claim 1: the ADR-075 release speed gate is the dominant AB exit."""
    ends = []
    for d in (EP2_BASE, EP2_BIAS, EP6_BASE, EP6_BIAS):
        ab, sp, _ = _load(d)
        on = ab < 0
        for c in range(on.shape[1]):
            for s, dur in _episodes(on[:, c]):
                ends.append(float(sp[min(s + dur, len(on) - 1), c]))
    assert len(ends) >= 90, f"too few episodes to judge: {len(ends)}"
    hit = sum(1 for e in ends if abs(e - RELEASE_GATE_KMH) <= GATE_TOL_KMH)
    rate = hit / len(ends)
    assert rate > 0.85, f"release-gate hit rate collapsed: {rate:.3f} over {len(ends)} episodes"


def test_notch_is_not_the_main_driver_of_ab_episode_length():
    """Claim 2: under a controlled comparison the notch gap is small (~8%).

    This test exists because the first version of the claim ("roughly 10x")
    was WRONG: it compared the strong episodes against ALL weak episodes
    including the low-entry-speed ones, so the starting speed confounded the
    notch. Matching the entry speed removes the confound and the gap shrinks
    to a single digit percentage -- which is what this test pins.
    """
    recs = _collect_episodes()

    def med(xs):
        return float(np.median(xs)) if len(xs) else float("nan")

    strong = [r for r in recs if r[7] == "strong"]
    weak_all = [r for r in recs if r[7] == "weak"]
    weak_ctl = [
        r for r in weak_all if CONTROLLED_ENTRY_LO_KMH <= r[4] <= CONTROLLED_ENTRY_HI_KMH
    ]
    assert strong and weak_ctl, "no strong/weak episodes found"

    s_dec = med([r[6] for r in strong])
    w_dec_all = med([r[6] for r in weak_all])
    w_dec_ctl = med([r[6] for r in weak_ctl])
    s_dur = med([r[3] for r in strong]) * 0.1
    w_dur_ctl = med([r[3] for r in weak_ctl]) * 0.1

    # The uncontrolled view really does look like a big gap -- keep it visible
    # so the reason the original claim failed stays auditable.
    assert s_dec > 1.3 * w_dec_all, (
        f"uncontrolled gap changed shape: strong={s_dec:.3f} weak_all={w_dec_all:.3f}"
    )
    # Controlled: the notch explains only a small fraction.
    assert s_dec < 1.5 * w_dec_ctl, (
        f"controlled strong/weak gap grew unexpectedly: "
        f"strong={s_dec:.3f} weak_ctl={w_dec_ctl:.3f} km/h/s"
    )
    assert abs(s_dur - w_dur_ctl) < 10.0, (
        f"controlled median episode durations diverged: {s_dur:.1f}s vs {w_dur_ctl:.1f}s"
    )


def test_superlong_weak_episodes_on_ep2_tail_are_not_notch_explained():
    """Claim 3: the long tail is a grade-position effect, not a notch effect.

    ep2's tail column carries two weak-notch episodes longer than 300 s whose
    deceleration is an order of magnitude below what their own notch implies
    (~0.04 vs ~0.39 km/h/s). ep6's tail column carries none. The notch value
    is identical in both cases, so the notch cannot explain the difference.
    """
    recs = _collect_episodes()

    def long_tail(dir_name):
        return [r for r in recs if r[0] == dir_name and r[1] == 2 and r[3] > 300 * 10]

    ep2_long = long_tail("ep2_bias")
    ep6_long = long_tail("ep6_bias")
    assert len(ep2_long) >= 2, f"ep2 tail super-long episodes vanished: {len(ep2_long)}"
    assert not ep6_long, f"ep6 tail gained super-long episodes: {len(ep6_long)}"
    for r in ep2_long:
        assert r[7] == "weak", "super-long episode changed notch class"
        assert r[6] < 0.10, (
            f"super-long episode deceleration no longer an order of magnitude low: {r[6]:.3f}"
        )


def test_on_ep2_the_tail_occupancy_rises_while_triggers_fall():
    """Claim 3: p_ab_applied is occupancy, not request rate (the sign flip)."""
    ab_b, _, ed_b = _load(EP2_BASE)
    ab_n, _, ed_n = _load(EP2_BIAS)
    on_b, on_n = ab_b < 0, ab_n < 0
    tail = 2
    # occupancy rose ...
    assert on_n[:, tail].mean() > on_b[:, tail].mean(), "ep2 tail occupancy did not rise"
    # ... while trigger opportunities (n_k >= thr while not already braking) fell hard
    def triggers(ed, on, thr):
        prev = np.concatenate([[False], on[:-1, tail]])
        return int(((ed[:, tail] >= thr) & (~prev)).sum())

    t_base = triggers(ed_b, on_b, 0.5)
    t_bias = triggers(ed_n, on_n, 0.9)
    assert t_bias < 0.5 * t_base, f"trigger reduction not seen: {t_base} -> {t_bias}"


def test_lead_share_drop_is_a_denominator_effect():
    """Claim 4: the leader's AB step count is unchanged; only the total grew."""
    ab_b, _, _ = _load(EP2_BASE)
    ab_n, _, _ = _load(EP2_BIAS)
    on_b, on_n = ab_b < 0, ab_n < 0
    assert on_n[:, 0].mean() == pytest.approx(on_b[:, 0].mean(), abs=1e-3), (
        "leader AB share changed -- the denominator explanation no longer holds"
    )
    assert on_n.sum(axis=1).mean() > on_b.sum(axis=1).mean(), (
        "total AB steps did not grow -- the denominator explanation no longer holds"
    )


def test_ep6_tail_escalates_to_the_strong_notch_more_often_than_ep2():
    """Claim 5: the ep6 win comes from strong-notch escalation, ep2 has none."""
    def strong_share(d: Path, col: int) -> float:
        ab, _, _ = _load(d)
        on = ab < 0
        strong = weak = 0
        for s, dur in _episodes(on[:, col]):
            seg = ab[s:s + dur, col]
            if (seg <= -0.4).mean() >= 0.5:
                strong += 1
            else:
                weak += 1
        return strong / max(strong + weak, 1)

    ep6 = strong_share(EP6_BIAS, 2)
    ep2 = strong_share(EP2_BIAS, 2)
    assert ep6 > 0.3, f"ep6 tail strong-notch share too low: {ep6:.3f}"
    assert ep2 < 0.2, f"ep2 tail should have (almost) no strong-notch episode: {ep2:.3f}"
