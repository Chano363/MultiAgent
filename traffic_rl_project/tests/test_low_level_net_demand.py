"""Native force budgets and hold handoff for the repaired rule controller."""
import pickle

import numpy as np
import pytest

from src.controllers.multi_loco_controller import MultiLocoController
from src.environments.train_env import TrainFormationEnv
from src.environments.train_fleet_env import TrainFleetEnv
from src.train_dynamics.grade_profile import GradeProfile, GradeSegment


@pytest.fixture
def train():
    env = TrainFormationEnv({'consist_preset': '20kt_1plus108_1plus108'})
    env.reset(options={'speed': 77.0 / 3.6})
    try:
        yield env
    finally:
        env.close()


def controller(train, **options):
    config = dict(cyclic_notch_50=True, cyclic_brake_trigger_kmh=65.0,
                  cyclic_release_kmh=50.0, cyclic_ab_upgrade_kmh=76.0,
                  ed_upgrade_ramp_s=6.0, ed_upgrade_ramp_scale=0.7)
    config.update(options)
    return MultiLocoController(train.num_vehicles, train.loco_indices, **config)


@pytest.mark.parametrize('grade,adhesion,upgrade', [
    (-5.0, 0.9, False),
    (-5.0, 0.05, True),
    (-12.0, 0.9, True),
])
def test_upgrade_uses_whole_train_demand_and_actual_adhesion(
        train, grade, adhesion, upgrade):
    dyn = train.dynamics
    dyn.set_grade_profile(GradeProfile([GradeSegment(-10000, grade)]))
    dyn.friction_coef = adhesion
    ctrl = controller(train)
    before = pickle.dumps(ctrl.__dict__)
    assert ctrl._ed_cannot_hold_speed(train) is upgrade
    assert pickle.dumps(ctrl.__dict__) == before
    action = ctrl.get_action_cyclic_braking(train)
    expected = -0.75 if upgrade else ctrl.CYCLIC_AB_SENTINEL
    np.testing.assert_array_equal(action[:, 1], expected)


def test_one_vehicle_entering_steep_grade_does_not_upgrade_entire_train(train):
    train.dynamics.set_grade_profile(GradeProfile([
        GradeSegment(-10000, 0.0), GradeSegment(0.0, -12.0)]))
    ctrl = controller(train)
    # The conservative AB fallback still sees the steepest car; only the
    # stronger SERVICE upgrade is screened using actual whole-train demand.
    assert ctrl._ed_ab_price(train) < 0.99
    action = ctrl.get_action_cyclic_braking(train)
    np.testing.assert_array_equal(action[:, 1], ctrl.CYCLIC_AB_SENTINEL)
    assert ctrl._ed_ramp_steps_left == 0


def test_feedforward_preserves_hold_then_supplies_ed_without_new_air(train):
    train.dynamics.set_grade_profile(GradeProfile([GradeSegment(-10000, -12.0)]))
    options = dict(ed_release_coordination=True, ed_release_hold_s=0.5)
    legacy = controller(train, **options)
    repaired = controller(train, ed_grade_feedforward=True, **options)
    for ctrl in (legacy, repaired):
        ctrl._cyclic_braking = True
    train.dynamics.vel[:] = 49.0 / 3.6
    for step in range(5):
        if step:
            train.dynamics.vel[:] = 55.0 / 3.6
        np.testing.assert_array_equal(legacy.get_action_cyclic_braking(train),
                                      repaired.get_action_cyclic_braking(train))
    assert legacy._ed_hold_steps == repaired._ed_hold_steps == 0
    before = legacy.get_action_cyclic_braking(train)
    after = repaired.get_action_cyclic_braking(train)
    assert np.all(before[:, 0] == 0.0)
    assert np.all(after[:, 0] > 0.0)
    np.testing.assert_array_equal(after[:, 1], 0.0)
    np.testing.assert_array_equal(before[:, 1], after[:, 1])


def test_feedforward_observation_preview_preserves_physical_and_control_state():
    env = TrainFleetEnv({
        'num_trains': 1, 'consist_preset': '20kt_1plus108_1plus108',
        'decompose': 'loco_ed_ab', 'cyclic_brake_trigger_kmh': 65.0,
        'cyclic_release_kmh': 50.0, 'ed_grade_feedforward': True})
    try:
        env.reset(seed=0, options={'speed': 55.0 / 3.6})
        dyn = env.trains[0].dynamics
        dyn.set_grade_profile(GradeProfile([GradeSegment(-10000, -12.0)]))
        ctrl = env.multi_loco_controllers[0]
        assert not ctrl._cyclic_braking and ctrl._ed_hold_steps == 0
        before = pickle.dumps(ctrl.__dict__)
        fields = ('pos', 'vel', 'grade', '_brake_pressure', '_air_brake_active')
        snapshots = {name: getattr(dyn, name).copy() for name in fields}
        for _ in range(5):
            env._get_obs_decomposed()
            assert pickle.dumps(ctrl.__dict__) == before
            for name in fields:
                np.testing.assert_array_equal(getattr(dyn, name), snapshots[name])
    finally:
        env.close()
