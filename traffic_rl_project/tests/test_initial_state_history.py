"""History comparisons must use native physics and preserve matched kinematics."""
import copy

import numpy as np

from src.environments.train_fleet_env import TrainFleetEnv
from src.evaluation.compare_initial_state_history import cold_from_kinematics, physical_sample, record
from src.train_dynamics.grade_profile import GradeProfile, GradeSegment


def config():
    return {'num_trains': 1, 'consist_preset': '20kt_1plus108_1plus108',
            'grade_profile': 'long_downhill', 'decompose': 'loco_ed_ab',
            'max_steps': 100, 'cyclic_notch_50': True,
            'cyclic_brake_trigger_kmh': 65.0, 'cyclic_release_kmh': 50.0,
            'cyclic_ab_upgrade_kmh': 76.0, 'ed_grade_feedforward': True,
            'coupler_force_limit_n': 1500000.0}


def run(env, count):
    for _ in range(count):
        env.step(np.zeros((env.num_agents, 2)))


def test_cold_branch_matches_every_vehicle_but_clears_physical_history():
    warm = TrainFleetEnv(config())
    cold = None
    try:
        warm.reset(seed=0, options={'speed': 77 / 3.6})
        warm.trains[0].dynamics.set_grade_profile(GradeProfile([GradeSegment(-10000, -12)]))
        run(warm, 30)
        cold = cold_from_kinematics(warm, config())
        a, b = physical_sample(warm), physical_sample(cold)
        np.testing.assert_array_equal(a['positions_m'], b['positions_m'])
        np.testing.assert_array_equal(a['velocities_mps'], b['velocities_mps'])
        assert a['pressure_coefficient'].max() > 0
        assert not b['pressure_coefficient'].any()
        assert not b['air_active'].any()
        assert warm.trains[0].dynamics.time > cold.trains[0].dynamics.time
        assert warm.multi_loco_controllers[0]._cyclic_braking
        assert not cold.multi_loco_controllers[0]._cyclic_braking
        assert not np.shares_memory(a['positions_m'], b['positions_m'])
    finally:
        warm.close()
        if cold is not None:
            cold.close()


def test_full_live_copy_replays_pressure_waves_and_coupler_history_exactly():
    warm = TrainFleetEnv(config())
    replay = None
    try:
        warm.reset(seed=0, options={'speed': 77 / 3.6})
        warm.trains[0].dynamics.set_grade_profile(GradeProfile([GradeSegment(-10000, -12)]))
        run(warm, 20)
        replay = copy.deepcopy(warm)
        for _ in range(3):
            a = warm.step(np.zeros((warm.num_agents, 2)))
            b = replay.step(np.zeros((replay.num_agents, 2)))
            np.testing.assert_array_equal(a[0], b[0])
            for key, value in physical_sample(warm).items():
                np.testing.assert_array_equal(value, physical_sample(replay)[key])
    finally:
        warm.close()
        if replay is not None:
            replay.close()


def test_positional_warmup_reaches_target_without_teleport_or_reset():
    env = TrainFleetEnv(config())
    try:
        env.reset(seed=0, options={'speed': 60 / 3.6})
        positions = env.trains[0].dynamics.pos.copy()
        trace, summary = record(env, 10, 1350, finish_head_m=float(positions[0] + 3))
        assert summary['stop_reason'] == 'head_target'
        assert 1 <= summary['steps'] < 10
        np.testing.assert_array_equal(trace['positions_m'][0, 0], positions)
        assert trace['positions_m'][-1, 0, 0] >= positions[0] + 3
        assert summary['elapsed_s'] == summary['steps'] * env.dt
    finally:
        env.close()
