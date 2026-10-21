from types import SimpleNamespace
import numpy as np
import pytest
from src.evaluation.release_low_speed_controller import release_ed_cap


def test_terminal_force_budget_removes_excess_ed():
    dyn = SimpleNamespace(vel=np.array([40/3.6]), masses_kg=np.array([10988000.]),
        _grade_forces=lambda: np.array([161632.]),
        _resistance_forces=lambda: np.array([214382.]),
        _air_braking_forces=lambda: np.array([0.]))
    assert release_ed_cap(dyn, 40/3.6) == 0.


def test_air_force_and_downhill_force_enter_with_correct_sign():
    dyn = SimpleNamespace(vel=np.array([15.]), masses_kg=np.array([1000000.]),
        _grade_forces=lambda: np.array([300000.]),
        _resistance_forces=lambda: np.array([100000.]),
        _air_braking_forces=lambda: np.array([-50000.]))
    assert release_ed_cap(dyn, 12., 60.) == pytest.approx(200.)
