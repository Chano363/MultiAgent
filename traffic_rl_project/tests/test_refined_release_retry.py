import pytest
from src.evaluation.refined_release_retry import retry_drop_kmh, refined_retry_source


@pytest.mark.parametrize('reason,speed,expected', [
    ('stronger_air_request_required', 44.58, .3),
    ('stronger_air_request_required', 46.39, 1.8),
    ('speed_ceiling', 44.58, 1.8),
    ('coupler_limit', 44.58, 1.8),
    ('speed_floor', 44.58, 1.8)])
def test_only_optional_strong_request_search_is_refined(reason, speed, expected):
    assert retry_drop_kmh(reason, speed, 1.8) == pytest.approx(expected)


def test_reject_unknown_source():
    with pytest.raises(ValueError):
        refined_retry_source('')
