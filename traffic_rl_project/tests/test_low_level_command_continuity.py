"""Contracts for discrete AB, ED protection, speed guards and episode isolation."""
import numpy as np
import pytest

from src.environments.train_fleet_env import TrainFleetEnv  # initialise package
from src.environments.train_env import TrainFormationEnv
from src.controllers.multi_loco_controller import MultiLocoController
from src.train_dynamics.braking import AirBrakeNotch, notch_from_throttle


def setup_controller():
    env = TrainFormationEnv({'consist_preset': '10kt_1plus1'})
    env.reset(options={'speed': 80 / 3.6})
    env.dynamics.set_grade(-0.012)
    ctrl = MultiLocoController(env.num_vehicles, env.loco_indices)
    return env, ctrl


def test_ed_availability_matches_actual_middle_loco_allocation():
    from src.train_dynamics.grade_profile import GradeProfile, GradeSegment
    from src.train_dynamics.resistance import G
    env = TrainFormationEnv({'consist_preset': '20kt_1plus108_1plus108'})
    try:
        env.reset(options={'speed': 80 / 3.6})
        dyn = env.dynamics
        dyn.set_grade_profile(GradeProfile([GradeSegment(0, -4)]))
        ctrl = MultiLocoController(env.num_vehicles, env.loco_indices)
        ctrl.ed_physics_availability = True
        command = np.zeros(env.num_vehicles)
        command[env.loco_indices] = [1.0, 0.7]
        required = dyn.masses_kg.sum() * G * 0.004
        expected = -dyn._electric_braking_forces(command).sum() / required
        assert expected < 0.99
        assert ctrl._ed_ab_price(env) == pytest.approx(expected)
    finally:
        env.close()


@pytest.mark.parametrize('tail_only', [False, True])
def test_prelimit_adds_only_gradual_ed_before_cyclic_air(tail_only):
    env, ctrl = setup_controller()
    try:
        env.dynamics.vel[:] = (65 if tail_only else 79) / 3.6
        if tail_only:
            env.dynamics.vel[-1] = 79 / 3.6
        assert not ctrl.ed_prelimit
        np.testing.assert_array_equal(ctrl.get_action_cyclic_braking(env), 0)
        ctrl.ed_prelimit = True
        action = ctrl.get_action_cyclic_braking(env)
        ramp = (79 / 3.6 - (80 / 3.6 - ctrl.AB_SUPPRESS_MARGIN_MPS)) / ctrl.AB_SUPPRESS_MARGIN_MPS
        np.testing.assert_allclose(action[:, 0], [ramp, 0.7 * ramp])
        np.testing.assert_array_equal(action[:, 1], 0)
        assert not ctrl._cyclic_braking
        env.dynamics.vel[:] = 65 / 3.6
        np.testing.assert_array_equal(ctrl.get_action_cyclic_braking(env), 0)
        env.dynamics.vel[:] = 80 / 3.6
        original = MultiLocoController(env.num_vehicles, env.loco_indices)
        np.testing.assert_array_equal(ctrl.get_action_cyclic_braking(env),
                                      original.get_action_cyclic_braking(env))
    finally:
        env.close()


def test_prelimit_keeps_coupler_reduction_authority():
    env, ctrl = setup_controller()
    try:
        ctrl.ed_prelimit = True
        env.dynamics.vel[:] = 79 / 3.6
        impose_compression(env, 0.1)
        action, _ = ctrl.get_action_decomposed(env, np.zeros((2, 2)))
        np.testing.assert_array_equal(action[:, 0], 0)
    finally:
        env.close()


@pytest.mark.parametrize('speed_kmh', [79.0, 81.0])
@pytest.mark.parametrize('ab_request', [0.0, -0.2, -0.75, -1.0])
def test_line_overspeed_air_execution_has_priority_over_new_source_veto(speed_kmh, ab_request):
    env = TrainFormationEnv({'consist_preset': '20kt_1plus108_1plus108',
                             'decompose': 'loco_ed_ab', 'line_speed_limit_mps': 80 / 3.6})
    try:
        env.reset(options={'speed': speed_kmh / 3.6})
        env.dynamics.pos[1:] += 0.05
        assert env.safety.ab_new_source_veto(env._state_snapshot())
        env._step_decomposed(np.array([[0.0, ab_request], [0.0, 0.0]]))
        if speed_kmh > 80:
            assert any(e['rule'] == 'overspeed' for e in env.safety.last_events)
            expected = AirBrakeNotch.EMERGENCY if ab_request == -1 else AirBrakeNotch.SERVICE
            assert env.dynamics.air_brake_state()[0] == expected
        else:
            assert not any(e['rule'] == 'overspeed' for e in env.safety.last_events)
            assert env.dynamics.air_brake_state()[0] == AirBrakeNotch.RELEASE
    finally:
        env.close()


def test_fleet_recovery_history_uses_post_safety_ed():
    from src.train_dynamics.etcs_braking import EbdTarget
    env = TrainFleetEnv({'num_trains': 1, 'consist_preset': '10kt_1plus1',
                         'grade_profile': 'long_downhill', 'decompose': 'loco_ed_ab'})
    try:
        env.reset(options={'speed': 70 / 3.6})
        ctrl = env.multi_loco_controllers[0]
        ctrl.ed_recovery_rate_per_s = 2.0
        env.trains[0].set_etcs_targets([EbdTarget(50.0, 0.0, kind='gap')])
        env.step(np.zeros((env.num_agents, 2)))
        assert any(e['rule'] == 'etcs_ebi' for e in env.trains[0].safety.last_events)
        np.testing.assert_array_equal(ctrl._previous_ed, [1.0, 1.0])
        env.reset(options={'speed': 70 / 3.6})
        assert ctrl._previous_ed is None
    finally:
        env.close()


@pytest.mark.parametrize('ed_request', [0.0, -0.5])
@pytest.mark.parametrize('ab_request', [0.0, -0.2, -1.0])
@pytest.mark.parametrize('sync', [False, True])
@pytest.mark.parametrize('rule,target,speed,depth', [
    ('etcs_ebi', 50.0, 70.0, 1.0),
    ('etcs_permitted', 480.0, 70.0, 0.75),
])
def test_etcs_intervention_reaches_ed_and_air_actuators(monkeypatch, ed_request,
                                                     ab_request, sync, rule, target, speed, depth):
    from src.train_dynamics.etcs_braking import EtcsBrakingCurve, EbdTarget

    env, _ = setup_controller()
    env.sync_loco_brake = sync
    env.dynamics.vel[:] = speed / 3.6
    if target is not None:
        env.etcs_curve = EtcsBrakingCurve(nominal_emergency_decel=0.4)
        env.etcs_targets = [EbdTarget(target, 0.0, kind='gap')]
    captured = {}
    original = env.dynamics.step_vehicles_ed_ab

    def record(throttle, ed_throttle, ab_command, *args, **kwargs):
        captured['ed'] = np.asarray(ed_throttle).copy()
        captured['traction'] = np.asarray(throttle).copy()
        captured['ab'] = ab_command
        captured['sources'] = kwargs.get('ab_sources')
        return original(throttle, ed_throttle, ab_command, *args, **kwargs)

    monkeypatch.setattr(env.dynamics, 'step_vehicles_ed_ab', record)
    action = np.zeros((env.num_locomotives, 2))
    action[:, 0] = ed_request
    action[:, 1] = ab_request
    try:
        step_info = env._step_decomposed(action)[-1]
        assert any(ev['rule'] == rule for ev in env.safety.last_events)
        if rule == 'etcs_ebi' or ab_request == -1.0:
            assert captured['ab'] == AirBrakeNotch.EMERGENCY
        else:
            assert captured['ab'] == AirBrakeNotch.SERVICE
        # Ordinary-mode synchronization does not replace the decompose ATP
        # path with multiple sources: the trial increased mixed-case violations.
        assert not captured['sources']
        np.testing.assert_array_equal(step_info['actual_loco_ed'],
                                      captured['ed'][env.loco_indices])
        np.testing.assert_array_equal(captured['ed'][env.loco_indices],
                                      1.0 if ab_request == -1.0 and ed_request >= 0 else depth)
        np.testing.assert_array_equal(captured['traction'], 0.0)
    finally:
        env.close()


def impose_compression(env, compression):
    d = env.dynamics
    d.pos = -np.arange(d.num_vehicles) * (d.coupler.free_length_m - compression)
    d.vel = 80 / 3.6 + np.arange(d.num_vehicles) * 0.01


@pytest.mark.parametrize('ed_request', [0.0, -0.5])
def test_line_overspeed_executes_ed_only_at_supervised_locomotive(monkeypatch, ed_request):
    env, _ = setup_controller()
    env.safety.max_speed_mps = 80 / 3.6
    env.dynamics.vel[:] = 70 / 3.6
    env.dynamics.vel[env.loco_indices[0]] = 81 / 3.6
    original = env.dynamics.step_vehicles_ed_ab
    captured = {}

    def record(throttle, ed_throttle, *args, **kwargs):
        captured['ed'] = np.asarray(ed_throttle).copy()
        captured['traction'] = np.asarray(throttle).copy()
        return original(throttle, ed_throttle, *args, **kwargs)

    monkeypatch.setattr(env.dynamics, 'step_vehicles_ed_ab', record)
    action = np.zeros((env.num_locomotives, 2))
    action[:, 0] = ed_request
    try:
        env._step_decomposed(action)
        assert any(e['rule'] == 'overspeed' and e['vehicle'] == env.loco_indices[0]
                   for e in env.safety.last_events)
        np.testing.assert_allclose(captured['ed'][env.loco_indices], [0.75, 0.0])
        assert captured['traction'][env.loco_indices[0]] == 0.0
    finally:
        env.close()


def test_experimental_etcs_ceiling_starts_rule_braking_before_line_limit():
    from src.train_dynamics.etcs_braking import EtcsBrakingCurve, EbdTarget

    env, ctrl = setup_controller()
    env.dynamics.vel[:] = 70 / 3.6
    env.etcs_curve = EtcsBrakingCurve(nominal_emergency_decel=0.4)
    env.etcs_targets = [EbdTarget(480.0, 0.0, kind='gap')]
    try:
        assert not ctrl.anticipate_etcs
        ctrl.get_action_cyclic_braking(env)
        assert not ctrl._cyclic_braking
        ctrl.anticipate_etcs = True
        ctrl.get_action_cyclic_braking(env)
        assert ctrl._cyclic_braking
        assert ctrl._operating_ceiling(env, 80 / 3.6, 0) < 70 / 3.6
        env.etcs_targets = [EbdTarget(-50.0, 0.0, kind='gap')]
        # A passed stop target remains restrictive in the real supervisor.
        assert ctrl._operating_ceiling(env, 80 / 3.6, 2) == 0.0
        env.etcs_targets = []
        assert ctrl._operating_ceiling(env, 80 / 3.6, 2) == 80 / 3.6
    finally:
        env.close()


def test_zero_modulation_applies_same_ed_projection_as_cyclic_interface():
    env, ctrl = setup_controller()
    ctrl.ed_baseline_projection = 'single'
    impose_compression(env, 0.035)
    assert 0 < ctrl._coupler_throttle_scale(env) < 1
    cyclic = ctrl.get_action_cyclic_braking(env)
    final, _ = ctrl.get_action_decomposed(env, np.zeros((2, 2)))
    np.testing.assert_allclose(final[:, 0], cyclic[:, 0])


def test_established_ab_notch_does_not_follow_instantaneous_force_scale():
    env, ctrl = setup_controller()
    first, _ = ctrl.get_action_decomposed(env, np.zeros((2, 2)))
    assert all(notch_from_throttle(x) == AirBrakeNotch.SERVICE for x in first[:, 1])
    for compression in [0.035, 0.040, 0.050, 0.030]:
        impose_compression(env, compression)
        final, _ = ctrl.get_action_decomposed(env, np.zeros((2, 2)))
        assert all(notch_from_throttle(x) == AirBrakeNotch.SERVICE for x in final[:, 1])


def test_legacy_baseline_projection_preserves_original_ed_protection():
    env, ctrl = setup_controller()
    assert ctrl.ed_baseline_projection == 'legacy'
    impose_compression(env, 0.035)
    scale = ctrl._coupler_throttle_scale(env)
    assert 0 < scale < 1
    protected_baseline = ctrl.get_action_cyclic_braking(env)
    final, _ = ctrl.get_action_decomposed(env, np.zeros((2, 2)))
    np.testing.assert_allclose(final[:, 0], protected_baseline[:, 0] * scale)


def test_reset_reproduces_fresh_controller_after_apply_release_history():
    env, ctrl = setup_controller()
    ctrl.get_action_decomposed(env, np.zeros((2, 2)))
    env.dynamics.vel[:] = 60 / 3.6
    ctrl.get_action_decomposed(env, np.ones((2, 2)))
    assert ctrl._ab_step > 0
    ctrl.reset()
    fresh = MultiLocoController(env.num_vehicles, env.loco_indices)
    env.dynamics.vel[:] = 80 / 3.6
    actual, _ = ctrl.get_action_decomposed(env, np.zeros((2, 2)))
    expected, _ = fresh.get_action_decomposed(env, np.zeros((2, 2)))
    np.testing.assert_array_equal(actual, expected)
    assert ctrl._ab_step == fresh._ab_step
    assert ctrl._ab_on == fresh._ab_on
    assert ctrl._ab_last_release_step == fresh._ab_last_release_step


def test_ed_recovers_gradually_but_safety_reductions_are_immediate():
    env, ctrl = setup_controller()
    ctrl.ed_recovery_rate_per_s = 1.0  # Experimental opt-in, not production default.
    ctrl.get_action_decomposed(env, np.zeros((2, 2)))
    impose_compression(env, 0.05)  # force above limit: immediate ED withdrawal
    protected, _ = ctrl.get_action_decomposed(env, np.zeros((2, 2)))
    np.testing.assert_array_equal(protected[:, 0], 0)
    impose_compression(env, 0)
    env.dynamics.vel[:] = 70 / 3.6
    recovered, _ = ctrl.get_action_decomposed(env, np.zeros((2, 2)))
    np.testing.assert_allclose(recovered[:, 0], 0.1)


@pytest.mark.parametrize('scope', ['all', 'coupler'])
def test_ed_recovery_limit_does_not_delay_overspeed_braking(scope):
    env, ctrl = setup_controller()
    ctrl.ed_recovery_scope = scope
    ctrl.ed_recovery_rate_per_s = 1.0
    impose_compression(env, 0.05)
    ctrl.get_action_decomposed(env, np.zeros((2, 2)))
    impose_compression(env, 0)
    env.dynamics.vel[:] = 80 / 3.6
    final, _ = ctrl.get_action_decomposed(env, np.zeros((2, 2)))
    np.testing.assert_allclose(final[:, 0], [1, 0.7])


def test_coupler_only_recovery_keeps_normal_brake_application_fast():
    env, ctrl = setup_controller()
    ctrl.ed_recovery_scope = 'coupler'
    ctrl.ed_recovery_rate_per_s = 2.0
    try:
        env.dynamics.vel[:] = 60 / 3.6
        ctrl.get_action_decomposed(env, np.zeros((2, 2)))
        # A lower coordination ceiling starts a new cycle below the line limit.
        final, _ = ctrl.get_action_decomposed(env, np.zeros((2, 2)), v_max_adj=-8)
        np.testing.assert_allclose(final[:, 0], [1, 0.7])
        impose_compression(env, 0.05)
        protected, _ = ctrl.get_action_decomposed(env, np.zeros((2, 2)))
        np.testing.assert_array_equal(protected[:, 0], 0)
        impose_compression(env, 0)
        env.dynamics.vel[:] = 60 / 3.6
        recovered, _ = ctrl.get_action_decomposed(env, np.zeros((2, 2)))
        np.testing.assert_allclose(recovered[:, 0], 0.2)
        assert ctrl._ed_recovery_pending.all()
        ctrl.reset()
        assert not ctrl._ed_recovery_pending.any()
    finally:
        env.close()


def test_coupler_recovery_release_ends_pending_episode():
    env, ctrl = setup_controller()
    ctrl.ed_recovery_scope = 'coupler'
    ctrl.ed_recovery_rate_per_s = 2.0
    try:
        impose_compression(env, 0.05)
        ctrl.get_action_decomposed(env, np.zeros((2, 2)))
        impose_compression(env, 0)
        env.dynamics.vel[:] = 35 / 3.6
        released, _ = ctrl.get_action_decomposed(env, np.zeros((2, 2)))
        np.testing.assert_array_equal(released[:, 0], 0)
        assert not ctrl._ed_recovery_pending.any()
        env.dynamics.vel[:] = 70 / 3.6
        final, _ = ctrl.get_action_decomposed(env, np.zeros((2, 2)), v_max_adj=-4)
        np.testing.assert_allclose(final[:, 0], [1, 0.7])
    finally:
        env.close()


def test_default_does_not_delay_ed_recovery_below_speed_ceiling():
    env, ctrl = setup_controller()
    assert ctrl.ed_recovery_rate_per_s == 0.0
    impose_compression(env, 0.05)
    ctrl.get_action_decomposed(env, np.zeros((2, 2)))
    impose_compression(env, 0)
    env.dynamics.vel[:] = 70 / 3.6
    final, _ = ctrl.get_action_decomposed(env, np.zeros((2, 2)))
    np.testing.assert_allclose(final[:, 0], [1, 0.7])


def test_grade_feedforward_balances_real_force_without_advancing_physics():
    env, ctrl = setup_controller()
    try:
        env.dynamics.vel[:] = 65 / 3.6
        env.dynamics.set_grade(-0.004)
        saved = [env.dynamics.pos.copy(), env.dynamics.vel.copy(), env.dynamics.grade.copy()]
        default = ctrl.get_action_cyclic_braking(env)
        np.testing.assert_array_equal(default, 0)
        ctrl.ed_grade_feedforward = True
        action = ctrl.get_action_cyclic_braking(env)
        command = np.zeros(env.num_vehicles)
        command[env.loco_indices] = action[:, 0]
        net = np.sum(env.dynamics._grade_forces() - env.dynamics._resistance_forces()
                     + env.dynamics._air_braking_forces()
                     + env.dynamics._electric_braking_forces(command))
        assert abs(net) < 1.0  # Numerical inverse precision, in N.
        assert np.any(action[:, 0] > 0)
        np.testing.assert_array_equal(action[:, 1], 0)
        for before, after in zip(saved, [env.dynamics.pos, env.dynamics.vel, env.dynamics.grade]):
            np.testing.assert_array_equal(before, after)
        assert not ctrl._cyclic_braking
    finally:
        env.close()


def test_grade_feedforward_keeps_saturation_and_low_speed_release():
    env, ctrl = setup_controller()
    ctrl.ed_grade_feedforward = True
    try:
        env.dynamics.vel[:] = 65 / 3.6
        env.dynamics.set_grade(-0.03)
        action = ctrl.get_action_cyclic_braking(env)
        np.testing.assert_allclose(action[:, 0], [1.0, 0.7])
        env.dynamics.vel[:] = 35 / 3.6
        released = ctrl.get_action_cyclic_braking(env)
        np.testing.assert_array_equal(released, 0)
        env.dynamics.vel[:] = 65 / 3.6
        env.dynamics.set_grade(0.0)
        np.testing.assert_array_equal(ctrl.get_action_cyclic_braking(env), 0)
    finally:
        env.close()


def test_grade_feedforward_enters_continuously_at_speed_floor():
    env, ctrl = setup_controller()
    ctrl.ed_grade_feedforward = True
    try:
        env.dynamics.set_grade(-0.03)
        values = []
        for delta in [0.0, 0.1, 0.25, 0.5]:
            env.dynamics.vel[:] = 40 / 3.6 + delta
            values.append(ctrl.get_action_cyclic_braking(env)[0, 0])
        np.testing.assert_allclose(values, [0.0, 0.2, 0.5, 1.0])
    finally:
        env.close()


def test_coupler_recovery_remembers_feedforward_removed_by_protection():
    env, ctrl = setup_controller()
    ctrl.ed_grade_feedforward = True
    ctrl.ed_recovery_scope = 'coupler'
    ctrl.ed_recovery_rate_per_s = 2.0
    try:
        impose_compression(env, 0.05)
        env.dynamics.vel -= 15 / 3.6  # Retain the real relative-velocity force.
        assert not ctrl._cyclic_braking
        protected, _ = ctrl.get_action_decomposed(env, np.zeros((2, 2)))
        np.testing.assert_array_equal(protected[:, 0], 0)
        impose_compression(env, 0)
        env.dynamics.vel[:] = 65 / 3.6
        recovered, _ = ctrl.get_action_decomposed(env, np.zeros((2, 2)))
        assert np.all(recovered[:, 0] <= 0.2 + 1e-12)
        assert np.any(recovered[:, 0] > 0)
    finally:
        env.close()


def test_coupler_recovery_does_not_treat_flat_coasting_as_protected_braking():
    env, ctrl = setup_controller()
    ctrl.ed_grade_feedforward = True
    ctrl.ed_recovery_scope = 'coupler'
    ctrl.ed_recovery_rate_per_s = 2.0
    try:
        impose_compression(env, 0.05)
        env.dynamics.vel -= 15 / 3.6
        env.dynamics.set_grade(0.0)
        coast, _ = ctrl.get_action_decomposed(env, np.zeros((2, 2)))
        np.testing.assert_array_equal(coast[:, 0], 0)
        assert not ctrl._ed_recovery_pending.any()
        impose_compression(env, 0)
        env.dynamics.vel[:] = 65 / 3.6
        env.dynamics.set_grade(-0.012)
        new_braking, _ = ctrl.get_action_decomposed(env, np.zeros((2, 2)))
        np.testing.assert_allclose(new_braking[:, 0], [1.0, 0.7])
    finally:
        env.close()


def test_coordination_cannot_raise_braking_ceiling_above_line_limit():
    env, ctrl = setup_controller()
    env.dynamics.vel[:] = 81 / 3.6
    ctrl.reset()
    ctrl.get_action_cyclic_braking(env, v_max_adj=2.0)
    assert ctrl._cyclic_braking


def test_overspeed_tail_starts_braking_even_when_head_is_below_limit():
    env, ctrl = setup_controller()
    env.dynamics.vel[:] = 70 / 3.6
    env.dynamics.vel[-1] = 81 / 3.6
    ctrl.reset()
    ctrl.get_action_cyclic_braking(env)
    assert ctrl._cyclic_braking


def test_tail_at_lower_formation_ceiling_starts_braking_without_recovery_delay():
    env, ctrl = setup_controller()
    try:
        env.dynamics.vel[:] = 65 / 3.6
        env.dynamics.vel[-1] = 72 / 3.6
        ctrl.ed_recovery_rate_per_s = 1.0
        ctrl._previous_ed = np.zeros(2)
        final, _ = ctrl.get_action_decomposed(
            env, np.zeros((2, 2)), v_max_adj=-10 / 3.6)
        assert ctrl._cyclic_braking
        np.testing.assert_allclose(final[:, 0], [1.0, 0.7])
    finally:
        env.close()


def test_tail_overspeed_cannot_suppress_ab_or_delay_ed_recovery():
    env, ctrl = setup_controller()
    env.dynamics.vel[:] = 70 / 3.6
    env.dynamics.vel[-1] = 81 / 3.6
    ctrl.reset()
    ctrl.ed_recovery_rate_per_s = 1.0
    ctrl._previous_ed = np.zeros(2)
    # A policy requesting AB release cannot suppress the overspeed baseline.
    final, _ = ctrl.get_action_decomposed(env, np.array([[0, 1], [0, 1]]))
    assert ctrl._cyclic_braking
    assert all(notch_from_throttle(x) == AirBrakeNotch.SERVICE for x in final[:, 1])
    np.testing.assert_allclose(final[:, 0], [1, 0.7])


def test_chase_release_threshold_keeps_a_band_below_braking_ceiling():
    env, ctrl = setup_controller()
    ctrl.get_action_cyclic_braking(env, v_min_adj=40 / 3.6)
    env.dynamics.vel[:] = 79.9 / 3.6
    ctrl.get_action_cyclic_braking(env, v_min_adj=40 / 3.6)
    assert ctrl._cyclic_braking
    env.dynamics.vel[:] = 78 / 3.6
    ctrl.get_action_cyclic_braking(env, v_min_adj=40 / 3.6)
    assert not ctrl._cyclic_braking


def test_chase_does_not_release_while_tail_is_near_braking_ceiling():
    env, ctrl = setup_controller()
    ctrl._cyclic_braking = True
    env.dynamics.vel[:] = 70 / 3.6
    env.dynamics.vel[-1] = 79.9 / 3.6
    ctrl.get_action_cyclic_braking(env, v_min_adj=35 / 3.6)
    assert ctrl._cyclic_braking
    env.dynamics.vel[:] = 70 / 3.6
    ctrl.get_action_cyclic_braking(env, v_min_adj=35 / 3.6)
    assert not ctrl._cyclic_braking


@pytest.mark.parametrize('speed_kmh,mode', [(81.0, False), (35.0, True)])
def test_observation_preview_does_not_commit_controller_state(speed_kmh, mode):
    env = TrainFleetEnv({'num_trains': 3, 'consist_preset': '10kt_1plus1',
                         'decompose': 'loco_ed_ab'})
    env.reset(seed=0, options={'speed': speed_kmh / 3.6})
    positions = [tr.dynamics.pos.copy() for tr in env.trains]
    for ctrl in env.multi_loco_controllers:
        ctrl._cyclic_braking = mode
    env._get_obs_decomposed()
    assert all(ctrl._cyclic_braking == mode for ctrl in env.multi_loco_controllers)
    assert all(np.array_equal(pos, tr.dynamics.pos) for pos, tr in zip(positions, env.trains))
    env.close()
