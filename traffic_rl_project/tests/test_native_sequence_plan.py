import copy

import numpy as np
import pytest

from src.evaluation.diagnose_actuator_sensitivity import validate_sequence_entries


def example():
    return {'name': 'head_020', 'ED_depths': [[0, 0], [1, 0], [0, 0]],
            'durations_s': [3, 3, 6]}


def test_unequal_blocks_cover_native_horizon_and_preserve_two_actuators():
    value = validate_sequence_entries([example()], 12)['head_020']
    np.testing.assert_array_equal(value[0], [[0, 0], [1, 0], [0, 0]])
    np.testing.assert_array_equal(np.cumsum(value[1] / 0.1), [30, 60, 120])


@pytest.mark.parametrize('name', ['../escape', 'folder/name', ''])
def test_plan_names_cannot_escape_archive(name):
    entry = example()
    entry['name'] = name
    with pytest.raises(ValueError):
        validate_sequence_entries([entry], 12)


@pytest.mark.parametrize('change', ['unbounded', 'nan', 'wrong_horizon', 'missing_actuator'])
def test_invalid_physical_requests_and_incomplete_horizons_rejected(change):
    entry = copy.deepcopy(example())
    if change == 'unbounded':
        entry['ED_depths'][0][0] = 1.1
    elif change == 'nan':
        entry['ED_depths'][0][0] = float('nan')
    elif change == 'wrong_horizon':
        entry['durations_s'] = [3, 3, 5]
    else:
        entry['ED_depths'] = [[0], [1], [0]]
    with pytest.raises(ValueError):
        validate_sequence_entries([entry], 12)


def test_duplicate_names_rejected_instead_of_silently_replacing_a_trial():
    with pytest.raises(ValueError):
        validate_sequence_entries([example(), example()], 12)
