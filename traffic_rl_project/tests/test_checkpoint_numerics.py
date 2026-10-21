"""Experimental restart cannot silently fall back to native mechanics."""
import copy
import json
from contextlib import contextmanager
from pathlib import Path
from types import SimpleNamespace

import pytest

from src.evaluation import checkpoint_numerics as module
from src.train_dynamics.train import TrainDynamics


def manifest():
    path = Path('outputs/sim_validation/phys_validation/') / (
        'single108_pressure_ready_cold70_cycle_20261019_round29/run/native_release_state.json')
    return json.loads(path.read_text(encoding='utf-8'))


def test_matches_frozen_numerics():
    settings = module.verify_checkpoint_numerics(manifest())
    assert settings['air_step_s'] == .0025
    assert settings['max_step_s'] == .000625
    assert settings['ramp_air_force'] is True


@pytest.mark.parametrize('component', ['solver_sha256', 'native_force_tangent', 'fractional_air_timing'])
def test_changed_implementation_is_rejected(component):
    value = copy.deepcopy(manifest())
    record = value['experimental_numerical_solver']
    if component == 'solver_sha256':
        record[component] = 'different'
    else:
        record['frozen_sources_sha256'][component] = 'different'
    with pytest.raises(ValueError, match='implementation differs'):
        module.verify_checkpoint_numerics(value)


def test_native_manifest_is_not_experimental():
    with pytest.raises(ValueError, match='explicitly experimental'):
        module.verify_checkpoint_numerics({})


def test_context_setup_failure_restores_already_installed_hooks(monkeypatch):
    @contextmanager
    def failing(*args, **kwargs):
        raise RuntimeError('setup failed')
        yield

    before = (TrainDynamics._advance_control_once, TrainDynamics._step_newmark,
              TrainDynamics._advance_air_brake_propagation)
    monkeypatch.setattr(module, 'coupled_candidate', failing)
    with pytest.raises(RuntimeError, match='setup failed'):
        module.checkpoint_numerical_context(manifest(), SimpleNamespace(dynamics=object()), [])
    assert before == (TrainDynamics._advance_control_once, TrainDynamics._step_newmark,
                       TrainDynamics._advance_air_brake_propagation)
