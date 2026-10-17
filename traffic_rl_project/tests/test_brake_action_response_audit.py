import itertools

import numpy as np
import pytest

from src.evaluation.audit_brake_action_response import interpolate_corners, summarize_prediction


def test_affine_action_response_is_recovered_at_unseen_intermediate_actions():
    def response(x):
        return np.array([4 + 2*x[0] - 3*x[1], 8 - x[0] + x[1]])
    corners = {x: response(x) for x in itertools.product((0, 1), repeat=2)}
    np.testing.assert_allclose(interpolate_corners(corners, [0.25, 0.75]), response([0.25, 0.75]))


def test_interior_nonlinear_peak_must_be_counted_as_false_safe():
    corners = {(0,): np.array([1200.0]), (1,): np.array([1200.0])}
    predicted = interpolate_corners(corners, [0.5])
    result = summarize_prediction([1600.0], predicted)
    assert result['limits']['1500']['false_safe'] == 1
    assert result['maximum_underprediction_kn'] == 400


def test_extrapolation_and_missing_corners_are_rejected():
    with pytest.raises(ValueError):
        interpolate_corners({(0,): np.zeros(1), (1,): np.ones(1)}, [1.1])
    with pytest.raises(ValueError):
        interpolate_corners({(0, 0): np.zeros(1)}, [0.5, 0.5])
