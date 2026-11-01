from types import SimpleNamespace
import numpy as np
import pytest
from src.evaluation.formation_traction_slew import limited_coordination, candidate


def state():
    return SimpleNamespace(_formation_traction_slew_enabled=True,
        _formation_traction_slew_zero_rl=True, _previous_ed=np.array([0.]),
        _cyclic_braking=False, _ab_on=[False], dt=.1)


def test_traction_rises_gradually_and_offsets_unchanged():
    c = state()
    old = 0.
    for _ in range(120):
        a, b, v = limited_coordination(c, (1., 2., .5))
        assert (a, b) == (1., 2.)
        assert 0 <= v <= .5 and v-old <= .005+1e-12
        old = v
    assert old == .5


@pytest.mark.parametrize('reason', ['ed', 'air', 'cycle'])
def test_block_and_reset_traction_while_braking(reason):
    c = state()
    c._formation_traction_slew_last = .4
    if reason == 'ed': c._previous_ed[:] = .1
    if reason == 'air': c._ab_on = [True]
    if reason == 'cycle': c._cyclic_braking = True
    assert limited_coordination(c, (0., 0., .5))[2] == 0.
    assert c._formation_traction_slew_last == 0.


def test_native_traction_reduction_is_immediate():
    c = state()
    c._formation_traction_slew_last = .4
    assert limited_coordination(c, (0., 0., .1))[2] == .1
    assert limited_coordination(c, (0., 0., 0.))[2] == 0.


def test_nonzero_rl_preserves_native_coordination():
    c = state()
    c._formation_traction_slew_zero_rl = False
    assert limited_coordination(c, (1., 2., .5)) == (1., 2., .5)


def test_context_restores_even_on_error():
    from src.controllers.multi_loco_controller import MultiLocoController as C
    from src.environments.train_fleet_env import TrainFleetEnv as E
    original = C.coordination_adj, E._step_decomposed_fleet
    with pytest.raises(RuntimeError):
        with candidate(): raise RuntimeError('scope')
    assert (C.coordination_adj, E._step_decomposed_fleet) == original
