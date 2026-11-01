import numpy as np
import pytest
from types import SimpleNamespace

from src.evaluation.screen_fleet_release import project_full_ed


class Dynamics:
    def __init__(self):
        self.masses_kg = np.array([1000., 3000.])
        self.vel = np.array([10., 10.])
        self.pos = np.array([0., -10.])
        self.num_vehicles = 2
        self.consist = SimpleNamespace(vehicles=[SimpleNamespace(is_locomotive=True),
                                                 SimpleNamespace(is_locomotive=False)])
        self._grade_profile = None

    def _grade_forces(self):
        return np.array([1000., 3000.])

    def _resistance_forces(self):
        return np.array([100., 300.])

    def _electric_braking_forces(self, throttle):
        assert np.array_equal(throttle, [1., 0.])
        return np.array([-2000., 0.])


def test_projection_force_balance_displacement_and_isolation():
    dynamics = Dynamics()
    rows = project_full_ed(dynamics, 2., .3)
    assert rows[-1, 0] == pytest.approx(2.)
    assert rows[-1, 2] == pytest.approx(10.8)
    assert rows[-1, 1] == pytest.approx(20.8)
    assert np.allclose(rows[:, 5], .4)
    assert np.array_equal(dynamics.pos, [0., -10.])
    assert np.array_equal(dynamics.vel, [10., 10.])


@pytest.mark.parametrize('horizon,dt', [(0., .1), (1., 0.), (np.nan, .1), (1., np.inf)])
def test_invalid_projection_budget(horizon, dt):
    with pytest.raises(ValueError):
        project_full_ed(Dynamics(), horizon, dt)
