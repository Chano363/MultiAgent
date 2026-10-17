"""Native middle-DP fleet contracts; no pressure-model changes."""
import json

import numpy as np
import pytest

from src.environments.train_fleet_env import TrainFleetEnv


@pytest.fixture
def fleet():
    env = TrainFleetEnv({
        'num_trains': 3, 'consist_preset': '20kt_1plus108_1plus108',
        'grade_profile': 'shuozhou_ningwuxi_beidaniu_49km',
        'decompose': 'loco_ed_ab', 'max_steps': 5,
    })
    env.reset(seed=0, options={'speed': 65 / 3.6})
    yield env
    env.close()


def test_snapshot_gap_matches_actual_tail_to_head_positions(fleet):
    context = fleet.get_formation_context()
    assert len(context) == 3
    assert context[0]['preceding_train_index'] is None
    assert context[0]['gap_m'] is None
    assert context[0]['tail_closing_speed_mps'] is None
    for i in (1, 2):
        expected = fleet.trains[i - 1].dynamics.pos[-1] - fleet.trains[i].dynamics.pos[0]
        assert context[i]['gap_m'] == pytest.approx(expected)
        assert context[i]['gap_error_m'] == pytest.approx(expected - fleet._dynamic_gap())
        assert expected > 0
    json.dumps(context, allow_nan=False)


def test_head_relative_speed_and_tail_closing_speed_are_distinct(fleet):
    fleet.trains[0].dynamics.vel[0] = 15.0
    fleet.trains[0].dynamics.vel[-1] = 14.0
    fleet.trains[1].dynamics.vel[0] = 17.0
    follower = fleet.get_formation_context()[1]
    assert follower['head_relative_speed_mps'] == 2.0
    assert follower['tail_closing_speed_mps'] == 3.0
    fleet.trains[0].dynamics.vel[:] = 18.0
    assert fleet.get_formation_context()[1]['tail_closing_speed_mps'] == -1.0


def test_snapshot_uses_current_positions_and_is_detached(fleet):
    before = fleet.get_formation_context()
    fleet.trains[1].dynamics.pos[:] -= 25.0
    after = fleet.get_formation_context()
    assert after[1]['gap_m'] == pytest.approx(before[1]['gap_m'] + 25.0)
    assert after[2]['gap_m'] == pytest.approx(before[2]['gap_m'] - 25.0)
    after[1]['gap_m'] = -999.0
    assert fleet.get_formation_context()[1]['gap_m'] > 0


def test_snapshot_does_not_change_controller_or_physical_state(fleet):
    positions = [tr.dynamics.pos.copy() for tr in fleet.trains]
    velocities = [tr.dynamics.vel.copy() for tr in fleet.trains]
    modes = [c._cyclic_braking for c in fleet.multi_loco_controllers]
    obs = fleet._get_obs_decomposed().copy()
    fleet.get_formation_context()
    fleet.get_formation_context()
    for i, tr in enumerate(fleet.trains):
        np.testing.assert_array_equal(tr.dynamics.pos, positions[i])
        np.testing.assert_array_equal(tr.dynamics.vel, velocities[i])
    assert modes == [c._cyclic_braking for c in fleet.multi_loco_controllers]
    np.testing.assert_array_equal(fleet._get_obs_decomposed(), obs)


def test_step_snapshot_matches_returned_observation_and_gap_metrics(fleet):
    obs, _, _, _, info = fleet.step(np.zeros((6, 2)))
    assert obs.shape == (6, 12)
    context = info['formation_context']
    assert info['gap_min_m'] == pytest.approx(min(c['gap_m'] for c in context[1:]))
    for i in (1, 2):
        np.testing.assert_allclose(obs[2 * i:2 * i + 2, 10], context[i]['gap_error_m'], atol=1e-4)
    assert info['executed_actions'].shape == (6, 2)


def test_preceding_deceleration_reaches_current_safety_target(fleet, monkeypatch):
    fleet.trains[0].dynamics.vel[:] = 50 / 3.6
    captured = []
    ctrl = fleet.multi_loco_controllers[1]
    original = ctrl.get_action_decomposed

    def record(tr, *args, **kwargs):
        target = tr.etcs_targets[0]
        preceding = fleet.trains[0].dynamics
        captured.append((target.position_m, target.speed_mps,
                         float(preceding.pos[-1]), float(preceding.vel[0])))
        return original(tr, *args, **kwargs)

    monkeypatch.setattr(ctrl, 'get_action_decomposed', record)
    fleet.step(np.zeros((6, 2)))
    assert len(captured) == 1
    position, speed, actual_tail, actual_speed = captured[0]
    assert position == actual_tail
    assert speed == actual_speed
    assert speed < 65 / 3.6
