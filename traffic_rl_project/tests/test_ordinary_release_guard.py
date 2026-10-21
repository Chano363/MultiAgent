import numpy as np
import pytest
from src.evaluation.ordinary_release_guard import classify_ordinary_release


@pytest.mark.parametrize('command,stronger', [(0., False), (-.05, False), (-.75, True)])
def test_separate_ordinary_success_from_stronger_request(command, stronger):
    rows = np.zeros((1, 6))
    rows[0, 4] = command
    original = dict(feasible=True, reason='horizon_completed')
    result = classify_ordinary_release(original, rows)
    assert result['feasible'] == (not stronger)
    assert result['stronger_air_request_forecast'] == stronger
    assert original['feasible']


def test_original_safety_failure_is_not_reclassified():
    rows = np.zeros((1, 6))
    rows[0, 4] = -.75
    result = classify_ordinary_release(dict(feasible=False, reason='speed_ceiling'), rows)
    assert not result['feasible']
    assert result['reason'] == 'speed_ceiling'
