"""The isolated ED candidate preserves AB and caps its own base request."""
import ast
from types import SimpleNamespace

import numpy as np
import pytest

from src.evaluation.pressure_ready_controller import pressure_ready_source


def isolated_action():
    from pathlib import Path
    path = Path('outputs/sim_validation/phys_validation/') / (
        'single108_force_matching_prep10_source_20261019_round10/controller_source.py')
    source = pressure_ready_source(path.read_text(encoding='utf-8'))
    tree = ast.parse(source)
    node = next(n for n in tree.body if isinstance(n, ast.FunctionDef)
                and n.name == '_service_phase_cap_action')
    def base_action(ctrl, *args, **kwargs):
        # The real base controller writes its projected request into this field
        # before returning. Recovery must use the pre-call executed value.
        ctrl._previous_ed[:] = .8
        return np.array([[0.8, -0.05]]), np.zeros((1, 2))
    namespace = {'np': np, '_service_phase_base_action': base_action}
    exec(compile(ast.Module(body=[node], type_ignores=[]), '<isolated-policy>', 'exec'), namespace)
    return namespace['_service_phase_cap_action']


@pytest.mark.parametrize('pressure,active,releasing,expected', [
    (0.99, True, False, .25), (1., True, True, .25),
    (1., False, False, .25), (1., True, False, .255)])
def test_only_ready_pressure_releases_cap_with_slow_slew(pressure, active, releasing, expected):
    dyn = SimpleNamespace(_air_brake_active=np.array([active, active]),
                          _air_brake_releasing=np.array([False, releasing]),
                          _brake_pressure=np.array([1., pressure]))
    ctrl = SimpleNamespace(num_locomotives=1, _release_force_hold_kn=150.,
                           _ab_on=[True], _previous_ed=np.array([.25]), dt=.1)
    final, _ = isolated_action()(ctrl, SimpleNamespace(dynamics=dyn), np.zeros((1, 2)))
    assert final[0, 0] == pytest.approx(expected)
    assert final[0, 1] == -.05


def test_builder_fails_closed():
    with pytest.raises(ValueError, match='phase-cap'):
        pressure_ready_source('unexpected policy')


def test_recovery_slew_uses_executed_history_across_calls():
    action = isolated_action()
    ctrl = SimpleNamespace(num_locomotives=1, _release_force_hold_kn=150.,
                           _ab_on=[True], _previous_ed=np.array([.25]), dt=.1)
    dyn = SimpleNamespace(_air_brake_active=np.ones(2, dtype=bool),
                          _air_brake_releasing=np.zeros(2, dtype=bool),
                          _brake_pressure=np.ones(2))
    history = [.25]
    for _ in range(120):
        final, _ = action(ctrl, SimpleNamespace(dynamics=dyn), np.zeros((1, 2)))
        assert final[0, 1] == -.05
        history.append(float(final[0, 0]))
        # Equivalent to the environment reporting the actually executed ED.
        ctrl._previous_ed = final[:, 0].copy()
    assert np.max(np.diff(history)) <= .005 + 1e-12
    assert history[-1] == pytest.approx(.8)
