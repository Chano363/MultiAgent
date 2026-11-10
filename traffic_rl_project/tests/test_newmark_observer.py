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
    # 【ADR-060 联动解耦】shuozhou 剖面的分段限速联动会让起步 70 km/h 在 70 段
    # 触发安全层强制制动与自适应步长细分（与本测试要验证的 observer 采样/恢复
    # 机制无关），故用无限速表的 long_downhill 剖面，保持机制断言的原语义。
    cfg['grade_profile'] = 'long_downhill'
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
        # 【ADR-048 力学细分对齐】_step_newmark 按 mechanical_max_step=0.0025 细分，
        # h=0.1 → 40 个 mech substep，observer 每 substep 采 1 行（pre-existing
        # 断言 10 为细分前旧值，2026-11-09 对齐）。
        assert len(samples) == 40
        for key in ('pos', 'vel', '_acc0', '_brake_pressure', '_air_brake_release_frac'):
            np.testing.assert_array_equal(getattr(first.trains[0].dynamics, key),
                                          getattr(second.trains[0].dynamics, key))
        if force_fallback:
            assert all(row[2] == 1 and row[5] == 0 for row in samples)
        replay = replay_fixed_mechanics(capture, (1, 2))
        assert replay[0]['native_replay_exact']
        # 【ADR-048 对齐】重放按捕获的 mech substep 粒度：1 步=40、2 步=80
        assert replay[0]['substeps'] == 40
        assert replay[1]['substeps'] == 80
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
    cfg['grade_profile'] = 'long_downhill'   # 【ADR-060 联动解耦】见上测试注释
    first, second = TrainFleetEnv(cfg), TrainFleetEnv(cfg)
    methods = TrainDynamics._step_newmark, TrainDynamics._advance_control_once
    try:
        for env in (first, second):
            env.reset(seed=0, options={'speed': 70 / 3.6})
        first.step(np.zeros((first.num_agents, 2)))
        samples = []
        with coupled_candidate(samples, max_step=0.000625, force_tol_n=10):
            second.step(np.zeros((second.num_agents, 2)))
        assert len(samples) == 40   # 【ADR-048 对齐】40 mech substep，同上
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
