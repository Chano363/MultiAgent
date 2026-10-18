import numpy as np

from src.evaluation.audit_coupler_warning import warning_audit


def test_last_observed_crossing_is_labelled_without_inventing_future():
    force = np.array([0, 0, 0, 0, 3.0])[:, None]
    result = warning_audit(force, np.zeros((5, 2)), 1, 2, 2, lag_s=1)
    assert result['samples'] == 3
    assert result['positive_samples'] == 2
    assert result['known_positive_censored_samples'] == 1
    assert result['observed_first_crossing_s'] == 5


def test_incomplete_safe_tail_is_unknown_not_a_false_warning():
    force = np.array([0, 0, 0, 0, 1.0])[:, None]
    result = warning_audit(force, np.zeros((5, 2)), 1, 2, 2, lag_s=1)
    assert result['samples'] == 2
    assert result['positive_samples'] == 0
    assert result['unknown_censored_samples_excluded'] == 1


def test_future_changes_labels_but_not_the_causal_warning():
    velocity = np.tile([0.0, 1.0], (5, 1))
    safe = warning_audit(np.array([0, 1, 1, 1, 1])[:, None], velocity, 1, 3, 2, lag_s=1)
    unsafe = warning_audit(np.array([0, 1, 1, 1, 3])[:, None], velocity, 1, 3, 2, lag_s=1)
    assert safe['methods']['force_rate']['false_positive'] == 1
    assert unsafe['methods']['force_rate']['true_positive'] == 1
    assert unsafe['methods']['force_rate']['first_observed_crossing_warning_lead_s'] == 3


def test_relative_speed_gate_distinguishes_loading_and_unloading_in_both_signs():
    for sign in (1, -1):
        force = sign * np.array([0, 1, 1, 1, 3])[:, None]
        loading = np.tile([0, sign], (5, 1))
        unloading = -loading
        on = warning_audit(force, loading, 1, 3, 2, lag_s=1)
        off = warning_audit(force, unloading, 1, 3, 2, lag_s=1)
        assert on['methods']['force_rate_relative_speed']['true_positive'] == 1
        assert off['methods']['force_rate_relative_speed']['false_negative'] == 3
