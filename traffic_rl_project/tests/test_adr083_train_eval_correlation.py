"""Lock the diagnostics 19.41 verdict: training-time scalar metrics cannot warn
about evaluation-time per-column coupler overload.

WHY THIS FILE EXISTS (2026-11-21, diagnostics 19.41):
    ADR-082 left the 11th-round candidate as "detect ep6-style action-surface
    drift during training and stop early / fall back to the ep4 shape". Its
    first implementation sketch reads the EXISTING training-time logs
    (train_history 11 columns + train_reward_terms 9 components) and trips a
    threshold. 19.41 tested that sketch against the W4 window (ep1-ep7) and
    rejected it:

      1. Every training-time metric that directly measures the COST of the
         break is INVERSED against the evaluation-time peak: train-time
         peak_coupler_kN -0.679, coupler_over -0.536, violations -0.464,
         overspeed -0.393 (gap_err_mean -0.036, i.e. unrelated).
      2. ep6 is among the CLEANEST episodes in training (violations /
         ab_cost / overspeed all the lowest of the seven; ed_cost second
         lowest) yet it is the WORST episode in evaluation (peak 1478.85,
         the highest of the seven).
      3. The episode with the loudest training-time signal is ep7 (violations
         / ab_cost / ed_cost / gap_err_mean all the highest), whose
         evaluation peak is normal (1185.81). A threshold on training
         scalars would MISS ep6 and FALSE-ALARM on ep7 -- the direction is
         reversed, not merely imprecise.
      4. The ONLY sizable positive correlation is the gap_eff reward
         component (+0.571), whose ranking does put the break episode ep6 in
         the top 2 -- but it also puts the normal-peak ep7 in the top 2 and
         the PASS episode ep4 in the top 3, so it cannot serve as a stop
         signal on its own; at most one term of a multi-metric detector, and
         its threshold would have to be re-calibrated per window.
      5. The reason the cost metrics are blind is structural, not a missing
         field: training logs record AGGREGATES (global peak, all-column
         mean ED, cross-column AB count), while the evaluation-time failure
         is a PER-COLUMN local phenomenon (ep6 middle column 4485 violating
         steps vs 376 / 282 for head / tail). Aggregates average the middle
         column's load away.

    Consequence for the 11th-round candidate: the "read scalars, set a
    threshold, stop" version is rejected. The candidate now requires (a)
    per-column training-time logging, (b) PROOF that a per-column signal
    exists on a break episode (needs a retraining window -> owner approval
    under red line 1), and (c) a multi-metric detector with a consequence
    quantity, anchored on the side that moves with the break (must not
    false-alarm on ep3).

    Also pinned here: checkpoint selection / early stopping must NOT use
    training-time scalars (W4's highest training peak, ep1, is the LOWEST
    evaluation peak).

    The W4 training curves live under outputs/ (gitignored, non-regenerable
    evidence), so this test SKIPS when they are absent. The evaluation-side
    numbers are the official-protocol local fast-eval readings recorded in
    diagnostics 19.40 and are inlined as constants.
"""
from pathlib import Path

import pytest

ROOT = Path(__file__).parents[1]
TRAIN_DIR = (
    ROOT / "outputs/results/formation_10kt_1plus108"
    / "w4nincrgatecaprel_w4full_20261120_cloud"
)
HIST_CSV = TRAIN_DIR / "train_history_dec_ad1_cp_seed0.csv"
TERMS_CSV = TRAIN_DIR / "train_reward_terms_dec_ad1_cp_seed0.csv"

pytestmark = pytest.mark.skipif(
    not (HIST_CSV.exists() and TERMS_CSV.exists()),
    reason=f"W4 training curves not present under {TRAIN_DIR}",
)

# Official-protocol local fast-eval readings, diagnostics 19.40 (manual
# transcription of outputs/logs/adr083_official_ep1_ep7_20261121/).
EVAL_PEAK = {1: 1142.46, 2: 1172.94, 3: 1180.05, 4: 1168.79, 5: 1253.75, 6: 1478.85, 7: 1185.81}
EVAL_COL_OVER = {
    1: (384, 1064, 804), 2: (427, 829, 623), 3: (978, 990, 140),
    4: (393, 1767, 489), 5: (389, 2129, 5332), 6: (376, 4485, 282), 7: (435, 1956, 1655),
}


def _read_csv(path: Path) -> dict:
    import csv
    with open(path, encoding="utf-8") as f:
        return {int(r["episode"]): r for r in csv.DictReader(f)}


def _rank(xs):
    order = sorted(range(len(xs)), key=lambda i: xs[i])
    r = [0.0] * len(xs)
    i = 0
    while i < len(order):
        j = i
        while j + 1 < len(order) and xs[order[j + 1]] == xs[order[i]]:
            j += 1
        avg = (i + j) / 2.0 + 1.0
        for k in range(i, j + 1):
            r[order[k]] = avg
        i = j + 1
    return r


def _spearman(a, b):
    ra, rb = _rank(a), _rank(b)
    n = len(a)
    d2 = sum((x - y) ** 2 for x, y in zip(ra, rb))
    return 1.0 - 6.0 * d2 / (n * (n * n - 1))


def _train_series():
    hist = _read_csv(HIST_CSV)
    terms = _read_csv(TERMS_CSV)
    eps = sorted(hist)
    assert eps == sorted(terms) == list(range(1, 8))
    series = {
        "peak_coupler_kN": [float(hist[e]["peak_coupler_kN"]) for e in eps],
        "violations": [float(hist[e]["violations"]) for e in eps],
        "gap_err_mean": [float(hist[e]["gap_err_mean"]) for e in eps],
        "overspeed_car_steps": [float(hist[e]["overspeed_car_steps"]) for e in eps],
        "ab_cost_abs": [abs(float(terms[e]["ab_cost_sum"])) for e in eps],
        "ed_cost_abs": [abs(float(terms[e]["ed_cost_sum"])) for e in eps],
        "coupler_over_abs": [abs(float(terms[e]["coupler_over_sum"])) for e in eps],
        "gap_eff_abs": [abs(float(terms[e]["gap_eff_sum"])) for e in eps],
    }
    return eps, series


def test_break_cost_metrics_have_no_positive_correlation_with_eval_peak():
    """Claim 1: every training-time metric that DIRECTLY measures the cost of
    the break (train-time peak, coupler-over cost, violations, overspeed) has
    a NON-POSITIVE rank correlation with the evaluation-time peak. A positive
    correlation would mean the 'stop-early on training scalars' sketch could
    work at all.

    Note (self-correction recorded in diagnostics 19.41): the blanket claim
    "no metric correlates positively" was WRONG -- gap_eff (+0.571),
    ab_cost (+0.143), total (+0.071) and reward (+0.071) are positive. The
    positive ones are checked separately below: the strongest of them points
    at the BEST evaluation episodes, so it is useless as a break alarm too."""
    eps, series = _train_series()
    eval_peak = [EVAL_PEAK[e] for e in eps]
    for name in ("peak_coupler_kN", "coupler_over_abs", "violations",
                 "overspeed_car_steps", "gap_err_mean"):
        rho = _spearman(series[name], eval_peak)
        assert rho <= 0.0, f"{name} unexpectedly correlates positively with eval peak (rho={rho:.4f})"


def test_the_only_positive_metric_points_at_the_break_episodes_but_not_cleanly():
    """Claim 1, second half: gap_eff is the only sizable positive correlation
    (+0.571), and its worst episodes are ep7 / ep6 -- the break episode ep6 IS
    among them. But the ranking is not clean:
      - top-2 = {ep7, ep6}: ep7's evaluation peak is NORMAL (would be a
        false alarm),
      - top-3 additionally contains ep4, a PASS episode.
    So gap_eff alone is not a usable stop signal; it can only be one term of a
    multi-metric detector.
    (Self-correction: an earlier draft of this test had the gap_eff ranking
    inverted and asserted it pointed at the BEST episodes. The permanent
    guard caught it against the real artifact.)"""
    eps, series = _train_series()
    eval_peak = [EVAL_PEAK[e] for e in eps]
    rho = _spearman(series["gap_eff_abs"], eval_peak)
    assert rho > 0.3, f"gap_eff correlation changed unexpectedly ({rho:.4f})"
    ranked = sorted(eps, key=lambda e: series["gap_eff_abs"][eps.index(e)], reverse=True)
    assert ranked[:2] == [7, 6], f"gap_eff top-2 changed: {ranked[:2]}"
    assert 4 in ranked[:3], f"gap_eff top-3 changed: {ranked[:3]}"
    # ep6 (the break episode) is caught; ep7 (normal peak) is a false alarm
    assert EVAL_PEAK[6] == max(EVAL_PEAK.values())
    assert EVAL_PEAK[7] < EVAL_PEAK[5] < EVAL_PEAK[6]


def test_training_peak_correlation_is_strongly_negative():
    """Claim 1, sharpest form: the most intuitive stop signal (training peak)
    is INVERSED. If this flips positive, the 19.41 rejection must be revisited."""
    eps, series = _train_series()
    rho = _spearman(series["peak_coupler_kN"], [EVAL_PEAK[e] for e in eps])
    assert rho < -0.5, f"expected strongly negative rho, got {rho:.4f}"


def test_ep6_is_cleanest_in_training_but_worst_in_evaluation():
    """Claim 2: ep6 has the LOWEST training-time violations, ab_cost and
    overspeed of the seven (ed_cost second lowest), yet the HIGHEST
    evaluation peak."""
    eps, series = _train_series()
    i6 = eps.index(6)
    for name in ("violations", "ab_cost_abs", "overspeed_car_steps"):
        assert series[name][i6] == min(series[name]), (
            f"ep6 is no longer the minimum of {name} -- 19.41 claim changed")
    ed = series["ed_cost_abs"]
    assert ed[i6] == sorted(ed)[1], "ep6's ed_cost is no longer second lowest"
    assert EVAL_PEAK[6] == max(EVAL_PEAK.values())


def test_ep7_is_the_loudest_training_episode_but_evaluates_normally():
    """Claim 3: the episode whose training-time signal is loudest is ep7,
    and its evaluation peak is normal. Hence a training-scalar threshold
    would false-alarm on ep7 and miss ep6."""
    eps, series = _train_series()
    i7 = eps.index(7)
    for name in ("violations", "ab_cost_abs", "ed_cost_abs"):
        assert series[name][i7] == max(series[name]), (
            f"ep7 is no longer the maximum of {name} -- 19.41 claim changed")
    # ep7's evaluation peak must stay below the two break episodes (ep5/ep6)
    assert EVAL_PEAK[7] < EVAL_PEAK[5] < EVAL_PEAK[6]


def test_break_is_per_column_local_not_global():
    """Claim 4 (the structural reason): the evaluation failure is a
    PER-COLUMN local phenomenon -- ep6's middle column carries 4485
    violating steps while head/tail carry 376 / 282 -- so global
    aggregates average the signal away."""
    assert EVAL_COL_OVER[6][1] == max(v[1] for v in EVAL_COL_OVER.values())
    assert EVAL_COL_OVER[6][1] > 5 * max(EVAL_COL_OVER[6][0], EVAL_COL_OVER[6][2])
    # ep5 breaks the other way: the TAIL column carries the failure
    assert EVAL_COL_OVER[5][2] == max(v[2] for v in EVAL_COL_OVER.values())


def test_checkpoint_selection_by_training_peak_would_pick_the_worst():
    """Consequence: W4's highest training-time peak (ep1) is the LOWEST
    evaluation peak, and W4's lowest training-time violations (ep6) is the
    HIGHEST evaluation peak. Hence ckpt selection / early stopping must use
    the same-source deterministic full-run fast eval, not training scalars."""
    eps, series = _train_series()
    worst_train_peak = max(eps, key=lambda e: series["peak_coupler_kN"][eps.index(e)])
    best_train_peak = min(eps, key=lambda e: series["peak_coupler_kN"][eps.index(e)])
    assert worst_train_peak == 1 and EVAL_PEAK[1] == min(EVAL_PEAK.values())
    assert best_train_peak == 3
