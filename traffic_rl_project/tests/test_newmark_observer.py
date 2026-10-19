"""Convergence observation must preserve both convergence and fallback paths."""
from pathlib import Path

import numpy as np
import pytest
import yaml

from src.environments.train_fleet_env import TrainFleetEnv
from src.evaluation.newmark_observer import observe_newmark, replay_fixed_mechanics
from src.train_dynamics.train import TrainDynamics
from src.evaluation.adaptive_newmark_candidate import coupled_candidate


@pytest.mark.parametrize('force_fallback', [False, True])
def test_observer_preserves_native_trajectory_and_restores_methods(force_fallback):
    cfg = yaml.safe_load(Path('configs/experiments/single_10kt108_coupler_rulecal.yaml')
                         .read_text(encoding='utf-8'))['env_cfg']
    cfg.update(eval_mode=True, start_randomization={'enabled': False})
    first, second = TrainFleetEnv(cfg), TrainFleetEnv(cfg)
    methods = TrainDynamics._step_newmark, TrainDynamics._state_forces
    samples, capture = [], {}
    try:
        for env in (first, second):
            env.reset(seed=0, options={'speed': 70 / 3.6})
            if force_fallback:
                env.trains[0].dynamics.newmark_max_iter = 1
                env.trains[0].dynamics.newmark_tol = 0
        first.step(np.zeros((first.num_agents, 2)))
        with observe_newmark(samples, capture=capture):
            second.step(np.zeros((second.num_agents, 2)))
        assert (TrainDynamics._step_newmark, TrainDynamics._state_forces) == methods
        assert len(samples) == 10
        for key in ('pos', 'vel', '_acc0', '_brake_pressure', '_air_brake_release_frac'):
            np.testing.assert_array_equal(getattr(first.trains[0].dynamics, key),
                                          getattr(second.trains[0].dynamics, key))
        if force_fallback:
            assert all(row[2] == 1 and row[5] == 0 for row in samples)
        replay = replay_fixed_mechanics(capture, (1, 2))
        assert replay[0]['native_replay_exact']
        assert replay[0]['substeps'] == 10
        assert replay[1]['substeps'] == 20
        assert np.all(np.isfinite(replay[1]['positions']))
        refined = replay_fixed_mechanics(capture, (2,), tol=1e-7, max_iter=60)[0]
        assert refined['tolerance_m'] == 1e-7
        assert refined['max_iter'] == 60
        assert np.all(refined['iterations'][:, 4] == 1e-7)
        assert first.trains[0].dynamics.newmark_max_iter == (1 if force_fallback else 30)
        assert second.trains[0].dynamics.newmark_tol == (0 if force_fallback else 1e-5)
        with pytest.raises(RuntimeError):
            with observe_newmark([]):
                raise RuntimeError('abort')
        assert (TrainDynamics._step_newmark, TrainDynamics._state_forces) == methods
    finally:
        first.close()
        second.close()


@pytest.mark.parametrize('kwargs', [{'tol': 0}, {'tol': float('nan')}, {'max_iter': 0}])
def test_refinement_rejects_invalid_solver_settings(kwargs):
    with pytest.raises(ValueError):
        replay_fixed_mechanics({}, (), **kwargs)


def test_coupled_candidate_preserves_pneumatic_progress_and_restores_on_failure(monkeypatch):
    import src.evaluation.adaptive_newmark_candidate as candidate
    cfg = yaml.safe_load(Path('configs/experiments/single_10kt108_coupler_rulecal.yaml')
                         .read_text(encoding='utf-8'))['env_cfg']
    cfg.update(eval_mode=True, start_randomization={'enabled': False})
    first, second = TrainFleetEnv(cfg), TrainFleetEnv(cfg)
    methods = TrainDynamics._step_newmark, TrainDynamics._advance_control_once
    try:
        for env in (first, second):
            env.reset(seed=0, options={'speed': 70 / 3.6})
        first.step(np.zeros((first.num_agents, 2)))
        samples = []
        with coupled_candidate(samples, max_step=0.000625, force_tol_n=10):
            second.step(np.zeros((second.num_agents, 2)))
        assert len(samples) == 10
        for field in ('_brake_pressure', '_air_brake_release_frac', '_air_brake_active'):
            np.testing.assert_array_equal(getattr(first.trains[0].dynamics, field),
                                          getattr(second.trains[0].dynamics, field))
        dyn = second.trains[0].dynamics
        before = {name: getattr(dyn, name).copy() for name in
                  ('pos', 'vel', '_acc0', '_brake_pressure', '_air_brake_release_frac')}
        time = dyn.time
        def fail(*args, **kwargs):
            raise RuntimeError('injected mechanical failure')
        monkeypatch.setattr(candidate, 'advance_mechanics', fail)
        with pytest.raises(RuntimeError, match='injected'):
            with coupled_candidate([]):
                second.step(np.zeros((second.num_agents, 2)))
        for name, value in before.items():
            np.testing.assert_array_equal(getattr(dyn, name), value)
        assert dyn.time == time
        assert (TrainDynamics._step_newmark, TrainDynamics._advance_control_once) == methods
    finally:
        first.close()
        second.close()
