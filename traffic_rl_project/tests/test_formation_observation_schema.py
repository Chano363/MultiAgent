"""Optional formation features and explicit checkpoint compatibility."""
from types import SimpleNamespace

import numpy as np
import pytest
import torch

from src.environments.train_fleet_env import TrainFleetEnv
from src.algorithms.mappo_agent import MAPPOAgent


def make_fleet(enabled=False):
    return TrainFleetEnv({
        'num_trains': 3, 'consist_preset': '20kt_1plus108_1plus108',
        'grade_profile': 'shuozhou_ningwuxi_beidaniu_49km',
        'decompose': 'loco_ed_ab', 'max_steps': 3,
        'formation_relative_speed_obs': enabled,
    })


def test_optional_features_detect_preceding_deceleration():
    env = make_fleet(True)
    try:
        obs, _ = env.reset(options={'speed': 65 / 3.6})
        assert obs.shape == (6, 14)
        assert env.observation_space.shape == (6, 14)
        np.testing.assert_array_equal(obs[:, 12:], 0)
        env.trains[0].dynamics.vel[:] = 50 / 3.6
        changed = env._get_obs_decomposed()
        np.testing.assert_array_equal(changed[2:4, :12], obs[2:4, :12])
        np.testing.assert_allclose(changed[2:4, 12:], 15 / 3.6)
        env.trains[0].dynamics.vel[-1] = 45 / 3.6
        assert env._get_obs_decomposed()[2, 13] == pytest.approx(20 / 3.6)
        np.testing.assert_array_equal(changed[:2, 12:], 0)
    finally:
        env.close()


def test_opt_in_does_not_change_base_features_actions_or_physics():
    base, expanded = make_fleet(False), make_fleet(True)
    try:
        a, _ = base.reset(seed=0, options={'speed': 79 / 3.6})
        b, _ = expanded.reset(seed=0, options={'speed': 79 / 3.6})
        np.testing.assert_array_equal(a, b[:, :12])
        for _ in range(2):
            a, ra, _, _, ia = base.step(np.zeros((6, 2)))
            b, rb, _, _, ib = expanded.step(np.zeros((6, 2)))
            np.testing.assert_array_equal(a, b[:, :12])
            np.testing.assert_array_equal(ia['executed_actions'], ib['executed_actions'])
            assert ra == rb
            for ta, tb in zip(base.trains, expanded.trains):
                np.testing.assert_array_equal(ta.dynamics.pos, tb.dynamics.pos)
                np.testing.assert_array_equal(ta.dynamics.vel, tb.dynamics.vel)
        a, _ = expanded.reset(options={'speed': 65 / 3.6})
        np.testing.assert_array_equal(a[:, 12:], 0)
    finally:
        base.close()
        expanded.close()


@pytest.mark.parametrize('config', [
    {'formation_relative_speed_obs': 'false', 'decompose': 'loco_ed_ab'},
    {'formation_relative_speed_obs': True},
])
def test_invalid_observation_configuration_fails_early(config):
    with pytest.raises(ValueError, match='formation_relative_speed_obs'):
        TrainFleetEnv(config)


def test_checkpoint_round_trip_and_dimension_guard(tmp_path):
    source = MAPPOAgent(2, 14, 2, device='cpu')
    path = tmp_path / 'relative.pt'
    source.save(str(path))
    target = MAPPOAgent(2, 14, 2, device='cpu')
    target.load(str(path))
    for a, b in zip(source.policy.parameters(), target.policy.parameters()):
        torch.testing.assert_close(a, b)
    with pytest.raises(ValueError, match='obs_dim=14'):
        MAPPOAgent(2, 12, 2, device='cpu').load(str(path), weights_only=True)
    legacy = MAPPOAgent(2, 12, 2, device='cpu')._checkpoint_payload()
    legacy.pop('model_signature')
    with pytest.raises(ValueError, match='obs_dim=12'):
        target._restore_checkpoint(legacy)
    MAPPOAgent(2, 12, 2, device='cpu')._restore_checkpoint(legacy)


def test_evaluation_recovers_schema_and_consist_and_rejects_conflict(tmp_path):
    from src.evaluation.evaluate_decompose import resolve_policy_environment, make_env
    path = tmp_path / 'relative.pt'
    torch.save({'metadata': {
        'observation_schema': {'name': 'loco_ed_ab_relative_speed_v1', 'dimension': 14},
        'hyperparameters': {'env_cfg': {'consist_preset': '20kt_1plus108_1plus108',
                                       'formation_relative_speed_obs': True}},
    }}, path)
    args = SimpleNamespace(mode='decompose_m1', checkpoint=str(path),
                           formation_relative_speed_obs=None, consist_preset=None,
                           grade='shuozhou_ningwuxi_beidaniu_49km', max_steps=2,
                           num_trains=3, mask_lever='none', hetero=False)
    resolve_policy_environment(args)
    env = make_env('decompose', args)
    try:
        assert env.obs_dim == 14 and env.num_agents == 6
        assert env.consist_preset == '20kt_1plus108_1plus108'
    finally:
        env.close()
    args.formation_relative_speed_obs = False
    with pytest.raises(ValueError, match='observation schema'):
        resolve_policy_environment(args)
