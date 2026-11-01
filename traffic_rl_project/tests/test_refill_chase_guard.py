from types import SimpleNamespace
import numpy as np
import pytest
from src.evaluation.refill_chase_guard import waiting_for_refill, candidate


def test_exact_refill_boundary_and_established_source():
    c = SimpleNamespace(_refill_chase_pause_enabled=True, _ab_on=[False],
                        _ab_step=2219, _ab_last_release_step=[0], dt=.1,
                        ab_min_refill_s=222.)
    assert waiting_for_refill(c)
    c._ab_step = 2220
    assert not waiting_for_refill(c)
    c._ab_step = 20
    c._ab_on = [True]
    assert not waiting_for_refill(c)
    c._ab_on = [False]
    c._refill_chase_pause_enabled = False
    assert not waiting_for_refill(c)


def test_chase_clamp_preserves_negative_adjustments_and_restores(monkeypatch):
    from src.controllers.multi_loco_controller import MultiLocoController as C
    monkeypatch.setattr(C, 'coordination_adj', lambda self: (1., -.4, .2))
    c = C.__new__(C)
    c._refill_chase_pause_enabled = True
    c._ab_on, c._ab_step, c._ab_last_release_step = [False], 10, [0]
    c.dt, c.ab_min_refill_s = .1, 222.
    original = C.coordination_adj
    with pytest.raises(RuntimeError):
        with candidate():
            assert c.coordination_adj() == (0., -.4, 0.)
            c._ab_on = [True]
            assert c.coordination_adj() == (1., -.4, .2)
            raise RuntimeError('deliberate')
    assert C.coordination_adj is original


def test_explicit_fleet_chase_offset_is_removed_during_refill(monkeypatch):
    from src.controllers.multi_loco_controller import MultiLocoController as C
    seen = []
    def original(self, train, rl, *args, **kwargs):
        seen.append(args[4] if len(args) > 4 else kwargs['v_min_adj'])
        return np.zeros((1, 2)), np.zeros((1, 2))
    monkeypatch.setattr(C, 'get_action_decomposed', original)
    c = C.__new__(C)
    c._refill_chase_pause_enabled = True
    c._ab_on, c._ab_step, c._ab_last_release_step = [False], 10, [0]
    c.dt, c.ab_min_refill_s = .1, 222.
    train = SimpleNamespace(etcs_targets=[SimpleNamespace(kind='gap')])
    with candidate():
        c.get_action_decomposed(train, np.zeros((1, 2)), v_min_adj=3.)
        c.get_action_decomposed(train, np.zeros((1, 2)), 22., 11., .5, 0., 3.)
        c._ab_on = [True]
        c.get_action_decomposed(train, np.zeros((1, 2)), v_min_adj=3.)
    assert seen == [0., 0., 3.]
