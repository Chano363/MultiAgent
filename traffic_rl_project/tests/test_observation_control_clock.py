"""Observation reads cannot consume physical controller time."""
import pickle

import numpy as np

from src.environments.train_fleet_env import TrainFleetEnv
from src.train_dynamics.grade_profile import GradeProfile, GradeSegment


def _make_fleet(**options):
    config = {'num_trains': 1, 'consist_preset': '20kt_1plus108_1plus108',
              'grade_profile': 'long_downhill', 'decompose': 'loco_ed_ab',
              'max_steps': 20, 'cyclic_brake_trigger_kmh': 65.0,
              'cyclic_release_kmh': 50.0, 'cyclic_ab_upgrade_kmh': 76.0,
              'ed_upgrade_ramp_s': 0.6, 'ed_upgrade_ramp_scale': 0.7}
    config.update(options)
    return TrainFleetEnv(config)


def test_repeated_observation_reads_preserve_all_controller_state():
    env = _make_fleet(ed_release_coordination=True)
    try:
        env.reset(seed=0, options={'speed': 77.0 / 3.6})
        ctrl = env.multi_loco_controllers[0]
        ctrl._ed_hold_steps = 9
        ctrl._ed_ramp_steps_left = 4
        before = pickle.dumps(ctrl.__dict__)
        obs = env._get_obs_decomposed()
        for _ in range(5):
            np.testing.assert_array_equal(env._get_obs_decomposed(), obs)
            assert pickle.dumps(ctrl.__dict__) == before
    finally:
        env.close()


def test_ramp_clock_advances_once_per_actual_environment_step():
    env = _make_fleet(cyclic_notch_50=True)
    try:
        env.reset(seed=0, options={'speed': 77.0 / 3.6})
        # Exercise a genuine CYCLIC -> SERVICE upgrade with an ED shortfall.
        # The old mild-grade ED-only case must no longer start this ramp.
        env.trains[0].dynamics.set_grade_profile(
            GradeProfile([GradeSegment(-10000.0, -12.0)]))
        ctrl = env.multi_loco_controllers[0]
        assert ctrl._ed_ramp_steps_left == 0
        for expected in (5, 4, 3, 2, 1, 0):
            env.step(np.zeros((env.num_agents, 2)))
            assert ctrl._ed_ramp_steps_left == expected
            env._get_obs_decomposed()
            assert ctrl._ed_ramp_steps_left == expected
    finally:
        env.close()


def test_release_hold_uses_configured_simulation_duration():
    env = _make_fleet(ed_release_coordination=True, ed_release_hold_s=0.5)
    try:
        env.reset(seed=0, options={'speed': 49.0 / 3.6})
        ctrl = env.multi_loco_controllers[0]
        ctrl._cyclic_braking = True
        for expected in (4, 3, 2, 1, 0):
            _, _, _, _, info = env.step(np.zeros((env.num_agents, 2)))
            assert ctrl._ed_hold_steps == expected
            assert np.any(info['executed_actions'][:, 0] > 0.0)
        _, _, _, _, info = env.step(np.zeros((env.num_agents, 2)))
        np.testing.assert_array_equal(info['executed_actions'][:, 0], 0.0)
    finally:
        env.close()


def test_extra_observation_reads_do_not_change_executed_trajectory():
    plain, observed = _make_fleet(), _make_fleet()
    try:
        for env in (plain, observed):
            env.reset(seed=0, options={'speed': 77.0 / 3.6})
        action = np.zeros((plain.num_agents, 2))
        for _ in range(10):
            for _ in range(3):
                observed._get_obs_decomposed()
            a = plain.step(action)[-1]
            b = observed.step(action)[-1]
            np.testing.assert_array_equal(a['executed_actions'], b['executed_actions'])
            np.testing.assert_array_equal(plain.trains[0].dynamics.pos,
                                          observed.trains[0].dynamics.pos)
            np.testing.assert_array_equal(plain.trains[0].dynamics.vel,
                                          observed.trains[0].dynamics.vel)
    finally:
        plain.close()
        observed.close()
