from types import SimpleNamespace
import numpy as np
import pytest
from src.evaluation.release_budget_guard import limit_release_request


def setup_case():
    dyn = SimpleNamespace(vel=np.full(2, 45/3.6), masses_kg=np.full(2, 1e5),
                          _grade_forces=lambda: np.zeros(2),
                          _resistance_forces=lambda: np.zeros(2),
                          _air_braking_forces=lambda: np.zeros(2))
    ctrl = SimpleNamespace(num_locomotives=1, _cyclic_braking=False,
                           _ab_on=[False], dt=.1,
                           _ed_frac_for_total_kn=lambda tr, kn: kn/1000)
    return ctrl, SimpleNamespace(dynamics=dyn)


def test_release_ramp_accumulates_even_when_original_requests_stay_full():
    c, t = setup_case()
    c._release_budget_previous_request = np.ones(1)
    for _ in range(10):
        out = limit_release_request(c, t, np.zeros((1, 2)), [[1, 0]], 40/3.6)
    assert out[0, 0] == pytest.approx(.95)
    assert c._previous_ed[0] == pytest.approx(.95)


@pytest.mark.parametrize('reason', ['cyclic', 'air', 'rl', 'requested_air'])
def test_guard_preserves_other_control_modes(reason):
    c, t = setup_case()
    rl, request = np.zeros((1, 2)), np.array([[1., 0.]])
    if reason == 'cyclic':
        c._cyclic_braking = True
    elif reason == 'air':
        t.dynamics._air_braking_forces = lambda: np.array([-100., 0.])
    elif reason == 'rl':
        rl[:] = .1
    else:
        request[0, 1] = -.05
    np.testing.assert_array_equal(limit_release_request(c, t, rl, request, 40/3.6), request)


def test_guard_never_raises_original_ed_request():
    c, t = setup_case()
    c._release_budget_previous_request = np.ones(1)
    result = limit_release_request(c, t, np.zeros((1, 2)), [[.1, 0]], 40/3.6)
    assert result[0, 0] == .1


def test_restart_reinstalls_recorded_guard_and_restores_method():
    from src.controllers.multi_loco_controller import MultiLocoController
    from src.evaluation.continue_fleet_numerics import recorded_context
    original = MultiLocoController.get_action_decomposed
    with recorded_context([], dict(solver='newton_analytic_time_error', settings={},
                                  source_sha256={'release_budget_guard': 'verified-by-loader'})):
        assert MultiLocoController.get_action_decomposed is not original
    assert MultiLocoController.get_action_decomposed is original
