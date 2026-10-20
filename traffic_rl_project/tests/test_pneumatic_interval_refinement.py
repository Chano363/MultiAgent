"""Refining the pneumatic interval must not reissue a command or duplicate time."""
import pytest
from types import SimpleNamespace

import numpy as np

from src.evaluation.refine_pneumatic_interval import refined_pneumatic_interval
from src.train_dynamics.train import TrainDynamics


def test_refinement_advances_time_once_and_issues_command_once(monkeypatch):
    calls = []
    def original(self, *args, reduction_kpa=None):
        calls.append((args[-2], args[-1], reduction_kpa))
    monkeypatch.setattr(TrainDynamics, '_advance_control_once', original)
    with refined_pneumatic_interval(.0025):
        TrainDynamics._advance_control_once(None, None, None, None, 0, None,
                                           False, .01, True, reduction_kpa=50)
    assert TrainDynamics._advance_control_once is original
    assert sum(row[0] for row in calls) == pytest.approx(.01)
    assert [row[1] for row in calls] == [True, False, False, False]
    assert all(row[2] == 50 for row in calls)


def test_context_restores_after_exception():
    original = TrainDynamics._advance_control_once
    with pytest.raises(RuntimeError):
        with refined_pneumatic_interval(.005):
            raise RuntimeError('abort')
    assert TrainDynamics._advance_control_once is original


def test_grade_is_held_only_inside_original_interval(monkeypatch):
    grades = []
    def native(self, *args, reduction_kpa=None):
        grades.append(self.grade.copy())
        self.grade = self.grade + .001
    monkeypatch.setattr(TrainDynamics, '_advance_control_once', native)
    dyn = SimpleNamespace(grade=np.array([-.012]))
    with refined_pneumatic_interval(.005, hold_coarse_grade=True):
        TrainDynamics._advance_control_once(dyn, None, None, None, 0,
                                           None, False, .01, True)
    np.testing.assert_array_equal(grades[0], grades[1])
    np.testing.assert_allclose(dyn.grade, [-.011])


def test_whole_pneumatic_interval_rolls_back_if_second_refined_part_fails(monkeypatch):
    from src.evaluation.adaptive_newmark_candidate import coupled_candidate
    calls = []
    def native(self, *args, reduction_kpa=None):
        self.time += args[-2]
        self.pressure += 1
        self.history.append(self.time)
        calls.append(True)
        if len(calls) == 2:
            raise RuntimeError('second pressure part failed')
    monkeypatch.setattr(TrainDynamics, '_advance_control_once', native)
    dyn = SimpleNamespace(time=0., pressure=np.array([0.]), history=[])
    with refined_pneumatic_interval(.005), coupled_candidate([]):
        with pytest.raises(RuntimeError, match='second pressure part'):
            TrainDynamics._advance_control_once(dyn, None, None, None, 0,
                                               None, False, .01, True)
    assert dyn.time == 0 and dyn.pressure[0] == 0 and dyn.history == []
    assert len(calls) == 2
    assert TrainDynamics._advance_control_once is native


@pytest.mark.parametrize('h', [0, -.001, .02, float('nan')])
def test_invalid_pneumatic_interval(h):
    with pytest.raises(ValueError):
        with refined_pneumatic_interval(h):
            pass
