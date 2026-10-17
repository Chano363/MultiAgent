"""An explicit cold-start speed policy changes training, never evaluation."""
from pathlib import Path

import numpy as np
import pytest
import yaml

from src.environments.train_fleet_env import TrainFleetEnv
from src.evaluation.compare_initial_state_history import physical_sample


def config(**options):
    cfg = yaml.safe_load(Path('configs/experiments/single_20kt_coupler_rulecal.yaml')
                         .read_text(encoding='utf-8'))['env_cfg']
    cfg['start_randomization'] = {'enabled': True, 'min_m': 20000, 'max_m': 20000,
                                  'seed': 0, 'cold_start_max_speed_kmh': 70.0}
    cfg.update(options)
    return cfg


def test_training_reset_records_explicit_change_and_replays_validated_native_start():
    env = TrainFleetEnv(config())
    reference = TrainFleetEnv(config(start_randomization={'enabled': False}))
    try:
        _, info = env.reset(seed=0, options={'speed': 80 / 3.6})
        policy = info['cold_start_initialization']
        assert policy['requested_speeds_kmh'] == pytest.approx([80])
        assert policy['actual_speeds_kmh'] == pytest.approx([70])
        assert policy['common_speed_shift_kmh'] == pytest.approx(10)
        assert policy['route_offset_m'] == 20000
        assert not policy['feasibility_guaranteed']
        reference.reset(seed=0, options={'speed': 70 / 3.6})
        d = reference.trains[0].dynamics
        d.set_initial(pos=d.pos + 20000, vel=d.vel.copy())
        reference._train_heads[0] = float(d.pos[0])
        for _ in range(3):
            env.step(np.zeros((2, 2)))
            reference.step(np.zeros((2, 2)))
            for key, a in physical_sample(env).items():
                np.testing.assert_array_equal(a, physical_sample(reference)[key])
    finally:
        env.close()
        reference.close()


@pytest.mark.parametrize('eval_mode,enabled', [(True, True), (False, False)])
def test_evaluation_or_disabled_randomization_preserves_requested_speed(eval_mode, enabled):
    cfg = config(eval_mode=eval_mode)
    cfg['start_randomization']['enabled'] = enabled
    env = TrainFleetEnv(cfg)
    try:
        _, info = env.reset(options={'speed': 80 / 3.6})
        assert info == {}
        assert env.trains[0].dynamics.pos[0] == 0
        np.testing.assert_allclose(env.trains[0].dynamics.vel, 80 / 3.6)
    finally:
        env.close()


def test_lower_requested_speed_is_not_raised():
    env = TrainFleetEnv(config())
    try:
        _, info = env.reset(options={'speed': 60 / 3.6})
        assert info['cold_start_initialization']['common_speed_shift_kmh'] == 0
        np.testing.assert_allclose(env.trains[0].dynamics.vel, 60 / 3.6)
    finally:
        env.close()


def test_common_shift_preserves_relative_formation_speeds_and_gaps():
    formation = {'enabled': True, 'seed': 0, 'speed_offset_kmh': [-5, 5],
                 'gap_offset_m': [0, 0]}
    cfg = config(num_trains=3, formation_start_randomization=formation)
    cfg['start_randomization']['cold_start_max_speed_kmh'] = 60.0
    env = TrainFleetEnv(cfg)
    try:
        _, info = env.reset(seed=0, options={'speed': 65 / 3.6})
        policy = info['cold_start_initialization']
        actual, requested = map(np.array, [policy['actual_speeds_kmh'],
                                           policy['requested_speeds_kmh']])
        np.testing.assert_allclose(np.diff(actual), np.diff(requested), atol=1e-12)
        assert actual.max() == pytest.approx(60)
        assert all(t['gap_m'] > 0 for t in env.get_formation_context()[1:])
    finally:
        env.close()


@pytest.mark.parametrize('value', [True, 0, -1, float('nan'), float('inf'), 81, '70'])
def test_invalid_policy_is_rejected(value):
    cfg = config()
    cfg['start_randomization']['cold_start_max_speed_kmh'] = value
    with pytest.raises(ValueError, match='cold_start_max_speed_kmh'):
        TrainFleetEnv(cfg)


def test_explicit_reset_seed_replays_route_offset_and_observation():
    cfg = config()
    cfg['start_randomization'].pop('min_m')
    cfg['start_randomization'].pop('max_m')
    env = TrainFleetEnv(cfg)
    try:
        first_obs, first_info = env.reset(seed=11, options={'speed': 80 / 3.6})
        _, other_info = env.reset(seed=12, options={'speed': 80 / 3.6})
        repeat_obs, repeat_info = env.reset(seed=11, options={'speed': 80 / 3.6})
        assert first_info == repeat_info
        assert (first_info['cold_start_initialization']['route_offset_m']
                != other_info['cold_start_initialization']['route_offset_m'])
        np.testing.assert_array_equal(first_obs, repeat_obs)
    finally:
        env.close()
