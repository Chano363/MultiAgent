import numpy as np
import pytest

from src.evaluation.audit_spatial_phase_reference import match_past_passage


def test_matches_known_delay_without_future_samples():
    time = np.arange(10., dtype=float)
    indices, lo, hi, fraction, passage = match_past_passage(time, time*10, time*10-25)
    assert len(indices) > 0
    np.testing.assert_allclose(time[indices]-passage, 2.5)
    assert np.all(time[hi] <= time[indices])
    np.testing.assert_allclose(fraction, .5)


def test_rejects_future_or_uncovered_passages_instead_of_extrapolating():
    time = np.arange(10., dtype=float)
    assert len(match_past_passage(time, time*10, time*10+5)[0]) == 0
    assert len(match_past_passage(time, time*10, time*10-1000)[0]) == 0


def test_rejects_nonmonotone_predecessor_motion():
    time = np.arange(4., dtype=float)
    with pytest.raises(ValueError):
        match_past_passage(time, np.array([0., 10., 9., 20.]), time)
