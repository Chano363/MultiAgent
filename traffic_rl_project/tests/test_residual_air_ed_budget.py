"""The residual-air experiment must preserve source, refill and RL authority."""
from types import SimpleNamespace

import numpy as np
import pytest

from src.evaluation.residual_air_ed_budget import limit_residual


def fixture():
    dyn = SimpleNamespace(vel=np.array([50./3.6]), masses_kg=np.array([1.e7]),
        _grade_forces=lambda: np.array([1.e6]),
        _resistance_forces=lambda: np.array([1.e5]),
        _air_braking_forces=lambda: np.array([-2.e6]))
    controller = SimpleNamespace(_residual_air_budget_enabled=True,
        num_locomotives=1, _cyclic_braking=False, _ab_on=[False], dt=.1,
        _ed_frac_for_total_kn=lambda train, kn: min(1., kn/500.))
    return controller, SimpleNamespace(dynamics=dyn)


def test_residual_force_budget_reduces_ed_gradually_without_touching_air():
    c, train = fixture()
    before = np.array([[1., 0.]])
    first = limit_residual(c, train, np.zeros((1, 2)), before, 40./3.6)
    second = limit_residual(c, train, np.zeros((1, 2)), before, 40./3.6)
    assert first[0, 0] == pytest.approx(.995)
    assert second[0, 0] == pytest.approx(.990)
    assert np.array_equal(before, [[1., 0.]])
    assert first[0, 1] == 0 and c._ab_on == [False]


@pytest.mark.parametrize('case', ['disabled', 'source_on', 'cyclic', 'rl', 'no_air', 'high_speed', 'brake_request'])
def test_ineligible_requests_are_preserved(case):
    c, train = fixture()
    rl, final = np.zeros((1, 2)), np.array([[1., 0.]])
    if case == 'disabled':
        c._residual_air_budget_enabled = False
    elif case == 'source_on':
        c._ab_on = [True]
    elif case == 'cyclic':
        c._cyclic_braking = True
    elif case == 'rl':
        rl[0, 0] = .1
    elif case == 'no_air':
        train.dynamics._air_braking_forces = lambda: np.zeros(1)
    elif case == 'high_speed':
        train.dynamics.vel[:] = 60./3.6
    elif case == 'brake_request':
        final[0, 1] = -.75
    assert np.array_equal(limit_residual(c, train, rl, final, 40./3.6), final)
