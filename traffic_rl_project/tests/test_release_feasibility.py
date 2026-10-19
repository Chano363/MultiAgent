"""A native prediction must never step the observed live dynamics."""
from pathlib import Path

import numpy as np
import pytest
import yaml

from src.environments.train_fleet_env import TrainFleetEnv
from src.evaluation.release_feasibility import evaluate_native_release


def test_adjacent_force_factors_do_not_overwrite_diagnostic_artifacts():
    from src.evaluation.diagnose_release_state_sensitivity import case_artifact_name
    assert case_artifact_name('hold50', 0.75) != case_artifact_name('hold50', np.nextafter(0.75, 1.0))
    assert case_artifact_name('hold50', None) == 'hold50'


@pytest.mark.parametrize('factor', ['-0.1', '1.1', 'nan'])
def test_invalid_force_factor_rejected_before_reading_checkpoint(monkeypatch, factor):
    import sys
    from src.evaluation.diagnose_release_state_sensitivity import main
    monkeypatch.setattr(sys, 'argv', ['sensitivity', '--state-dir', 'missing',
        '--output', 'unused', '--controller-source', 'missing.py',
        '--hold-force-factors', factor])
    with pytest.raises(SystemExit) as failure:
        main()
    assert failure.value.code == 2


def test_native_release_delay_preserves_fleet_physics_and_restores_threshold():
    from src.evaluation.diagnose_release_state_sensitivity import advance_braking_state
    from src.train_dynamics.grade_profile import GradeProfile, GradeSegment
    cfg = yaml.safe_load(Path('configs/experiments/single_10kt108_coupler_rulecal.yaml')
                         .read_text(encoding='utf-8'))['env_cfg']
    cfg.update(eval_mode=True, start_randomization={'enabled': False})
    actual, reference = TrainFleetEnv(cfg), TrainFleetEnv(cfg)
    try:
        for fleet in (actual, reference):
            fleet.reset(seed=0, options={'speed': 70 / 3.6})
            fleet.trains[0].dynamics.set_grade_profile(
                GradeProfile(segments=[GradeSegment(0, -12)]))
            ctrl = fleet.multi_loco_controllers[0]
            ctrl._cyclic_braking = True
            ctrl._ab_on = [True]
        ctrl = actual.multi_loco_controllers[0]
        original_release = ctrl.cyclic_release_kmh
        reference.multi_loco_controllers[0].cyclic_release_kmh = 40
        advance_braking_state(actual.trains[0], ctrl,
                              {'v_max': actual.v_max, 'v_min': actual.v_min}, 2)
        for _ in range(2):
            reference.step(np.zeros((reference.num_agents, 2)))
        assert ctrl.cyclic_release_kmh == original_release
        assert not ctrl._release_probe_active
        assert ctrl._ab_step == 2
        for key in ('pos', 'vel', '_acc0', '_brake_pressure', '_air_brake_release_frac'):
            np.testing.assert_array_equal(getattr(actual.trains[0].dynamics, key),
                                          getattr(reference.trains[0].dynamics, key))
    finally:
        actual.close()
        reference.close()


def test_native_lookahead_preserves_live_state_and_diagnostic_observer():
    config = yaml.safe_load(Path('configs/experiments/single_10kt108_coupler_rulecal.yaml')
                            .read_text(encoding='utf-8'))['env_cfg']
    env = TrainFleetEnv(config)
    try:
        env.reset(seed=0, options={'speed': 70 / 3.6})
        tr, ctrl = env.trains[0], env.multi_loco_controllers[0]
        tr.max_steps = 1
        before = {key: getattr(tr.dynamics, key).copy() for key in
                  ('pos', 'vel', '_acc0', '_brake_pressure', '_air_brake_release_frac')}
        history = list(tr.safety._peak_hist)
        original = tr.dynamics.step_vehicles_ed_ab
        observed = []

        def record_inputs(*args, **kwargs):
            observed.append(True)
            return original(*args, **kwargs)

        tr.dynamics.step_vehicles_ed_ab = record_inputs
        result = evaluate_native_release(tr, ctrl, {'v_max': 80 / 3.6, 'v_min': 40 / 3.6}, 0.3)
        assert len(result['trajectory']) == 3
        assert result['feasible']
        assert result['prediction_max_steps'] >= 4
        assert tr.max_steps == 1
        assert not observed
        assert tr.dynamics.step_vehicles_ed_ab is record_inputs
        for key, value in before.items():
            np.testing.assert_array_equal(getattr(tr.dynamics, key), value)
        assert ctrl._ab_step == 0
        assert tr.dynamics.time == 0
        assert list(tr.safety._peak_hist) == history
        env.step(np.zeros((env.num_agents, 2)))
        assert len(observed) == 1
    finally:
        env.close()


@pytest.mark.parametrize('horizon', [0, -1, float('nan')])
def test_invalid_horizon_rejected_before_copying(horizon):
    with pytest.raises(ValueError):
        evaluate_native_release(None, None, {}, horizon)


def test_prediction_rejects_speed_ceiling_without_changing_live_safety_counters():
    config = yaml.safe_load(Path('configs/experiments/single_10kt108_coupler_rulecal.yaml')
                            .read_text(encoding='utf-8'))['env_cfg']
    config.update(eval_mode=True, start_randomization={'enabled': False})
    env = TrainFleetEnv(config)
    try:
        env.reset(seed=0, options={'speed': 81 / 3.6})
        tr, ctrl = env.trains[0], env.multi_loco_controllers[0]
        result = evaluate_native_release(tr, ctrl, {'v_max': 80 / 3.6}, 0.3)
        assert not result['feasible']
        assert result['reason'] == 'speed_ceiling'
        assert tr._overspeed_violations == 0
        assert tr._safety_events == 0
        assert ctrl._ab_step == 0
    finally:
        env.close()


def test_singleton_prediction_matches_live_fleet_dynamic_speed_band():
    config = yaml.safe_load(Path('configs/experiments/single_10kt108_coupler_rulecal.yaml')
                            .read_text(encoding='utf-8'))['env_cfg']
    config.update(eval_mode=True, start_randomization={'enabled': False})
    env = TrainFleetEnv(config)
    try:
        env.reset(seed=0, options={'speed': 50 / 3.6})
        tr, ctrl = env.trains[0], env.multi_loco_controllers[0]
        prediction = evaluate_native_release(
            tr, ctrl, {'v_max': env.v_max, 'v_min': env.v_min}, 1.0,
            singleton_leader_offset_mps=env.LEAD_TAIL_OFFSET_MPS)
        bands = []
        original = ctrl.get_action_decomposed

        def observe_control(*args, **kwargs):
            bands.append(kwargs['v_max_adj'])
            return original(*args, **kwargs)

        ctrl.get_action_decomposed = observe_control
        actual = []
        for _ in range(10):
            info = env.step(np.zeros((env.num_agents, 2)))[-1]
            actual.append([np.abs(tr.dynamics.coupler_interface_forces()).max(),
                           tr.dynamics.vel.max(), tr.dynamics.vel.mean(),
                           info['executed_actions'][0, 1], bands[-1]])
        assert np.ptp(bands) > 0
        np.testing.assert_allclose(prediction['trajectory'][:, 1:], actual,
                                   rtol=0, atol=1e-7)
    finally:
        env.close()
