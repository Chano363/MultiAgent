"""Check response-preview direction without asserting a safety certificate."""
import pytest

from src.evaluation.preview_sbi_upgrade import predicted_ceiling


def test_falling_limit_with_constant_speed_requests_earlier_braking():
    assert predicted_ceiling(21., 20., 1., (0., 22., 20.), 5.) == pytest.approx(16.)


def test_self_deceleration_faster_than_limit_decline_needs_no_extra_margin():
    assert predicted_ceiling(21., 18., 1., (0., 22., 20.), 5.) == 21.


def test_initial_sample_or_duplicate_clock_does_not_invent_derivative():
    assert predicted_ceiling(21., 20., 1., None, 5.) == 21.
    assert predicted_ceiling(21., 20., 1., (1., 22., 20.), 5.) == 21.


def test_preview_is_bounded_below_zero():
    assert predicted_ceiling(2., 20., 1., (0., 22., 20.), 5.) == 0.
