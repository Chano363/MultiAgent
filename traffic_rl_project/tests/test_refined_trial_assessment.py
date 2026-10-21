import copy
from src.evaluation.assess_refined_trial import assess


def sample():
    return {'summary': {'stop_reason': 'step_budget', 'steps': 4000,
        'last_time_s': 2580., 'internal_microstep_peak_kn': 660.},
        'candidate': {'min_vehicle_kmh': 44., 'max_vehicle_kmh': 75.,
                      'stronger_request_onsets': 0}}


def test_continue_only_after_improvement_and_safety():
    current = sample()
    previous = copy.deepcopy(current)
    previous['candidate']['min_vehicle_kmh'] = 42.6
    previous['summary']['internal_microstep_peak_kn'] = 674.
    assert assess(current, previous)['continue_remaining_route']
    current['summary']['stop_reason'] = 'speed_floor'
    assert not assess(current, previous)['continue_remaining_route']


def test_no_continuation_for_tradeoff_or_unsampled_force_violation():
    current = sample()
    previous = copy.deepcopy(current)
    previous['candidate']['min_vehicle_kmh'] = 42.6
    previous['summary']['internal_microstep_peak_kn'] = 674.
    current['summary']['internal_microstep_peak_kn'] = 1001.
    assert not assess(current, previous)['continue_remaining_route']
    current['summary']['internal_microstep_peak_kn'] = 670.
    current['candidate']['min_vehicle_kmh'] = 41.
    assert not assess(current, previous)['continue_remaining_route']
