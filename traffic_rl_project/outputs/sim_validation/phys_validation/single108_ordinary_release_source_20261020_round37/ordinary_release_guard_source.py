"""Diagnostic ordinary-cycle objective; downstream safety is unchanged."""
import numpy as np


def classify_ordinary_release(result, trajectory):
    """Distinguish safe forecast from one that needs a stronger AB request.

    Requests are not evidence of actual pressure or ATP intervention. Preserve
    every original unsafe outcome; this optional objective only narrows success.
    """
    rows = np.asarray(trajectory)
    stronger = bool(len(rows) and np.any(rows[:, 4] < -0.1))
    result = dict(result, stronger_air_request_forecast=stronger)
    if result['feasible'] and stronger:
        result.update(feasible=False, reason='stronger_air_request_required')
    return result


def ordinary_release_source(source):
    old = "            trace = result.pop('trajectory')\n"
    new = old + '''            from src.evaluation.ordinary_release_guard import classify_ordinary_release
            result = classify_ordinary_release(result, trace)
'''
    if source.count(old) != 1:
        raise ValueError('Expected exactly one release forecast result')
    return source.replace(old, new, 1)
