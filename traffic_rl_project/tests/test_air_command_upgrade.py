"""Production air-wave contracts for upgrades of established brake sources."""
import numpy as np
import pytest

from src.environments.train_fleet_env import TrainFleetEnv
from src.environments.train_env import TrainFormationEnv
from src.train_dynamics.braking import AirBrakeNotch as Notch


@pytest.fixture
def dynamics():
    env = TrainFormationEnv({'consist_preset': '20kt_1plus108_1plus108'})
    env.reset(options={'speed': 70 / 3.6})
    yield env.dynamics
    env.close()


def test_native_active_service_source_accepts_emergency(dynamics):
    zeros = np.zeros(dynamics.num_vehicles)
    dynamics.step_vehicles_ed_ab(zeros, zeros, Notch.SERVICE)
    dynamics.step_vehicles_ed_ab(zeros, zeros, Notch.EMERGENCY)
    assert dynamics.air_brake_state()[0] == Notch.EMERGENCY


def test_upgrade_propagates_and_repeated_commands_do_not_restart(dynamics):
    dynamics._apply_air_brake_command(Notch.SERVICE, 0)
    dynamics._advance_air_brake_propagation(20)
    dynamics._apply_air_brake_command(Notch.EMERGENCY, 0)
    assert dynamics.air_brake_state()[-1] == Notch.SERVICE
    for _ in range(160):
        dynamics._apply_air_brake_command(Notch.EMERGENCY, 0)
        dynamics._advance_air_brake_propagation(0.1)
    assert all(n == Notch.EMERGENCY for n in dynamics.air_brake_state())


def test_old_wave_cannot_downgrade_an_upgraded_middle_source(dynamics):
    dynamics._apply_air_brake_command(Notch.SERVICE, 0)
    dynamics._apply_air_brake_command(Notch.EMERGENCY, 109, bidirectional=True)
    dynamics._advance_air_brake_propagation(20)
    assert all(n == Notch.EMERGENCY for n in dynamics.air_brake_state())


def test_release_cancels_pending_upgrade(dynamics):
    dynamics._apply_air_brake_command(Notch.SERVICE, 0)
    dynamics._advance_air_brake_propagation(20)
    dynamics._apply_air_brake_command(Notch.EMERGENCY, 0)
    dynamics._reset_air_brake_command()
    dynamics._advance_air_brake_propagation(100)
    assert not np.any(dynamics._air_brake_active)


def test_earlier_service_wave_is_preserved_before_later_upgrade(dynamics):
    dynamics._apply_air_brake_command(Notch.SERVICE, 0)
    dynamics._advance_air_brake_propagation(5.0)
    dynamics._apply_air_brake_command(Notch.EMERGENCY, 0)
    dynamics._advance_air_brake_propagation(2.0)
    assert dynamics.air_brake_state()[109] == Notch.SERVICE
    dynamics._advance_air_brake_propagation(10.0)
    assert dynamics.air_brake_state()[109] == Notch.EMERGENCY


def test_fleet_ebi_upgrades_an_established_service_source():
    from src.train_dynamics.etcs_braking import EbdTarget
    env = TrainFleetEnv({'num_trains': 1, 'consist_preset': '20kt_1plus108_1plus108',
                         'decompose': 'loco_ed_ab'})
    try:
        env.reset(options={'speed': 70 / 3.6})
        tr = env.trains[0]
        zeros = np.zeros(tr.num_vehicles)
        tr.dynamics.step_vehicles_ed_ab(zeros, zeros, Notch.SERVICE)
        tr.set_etcs_targets([EbdTarget(50.0, 0.0, kind='gap')])
        env.step(np.zeros((env.num_agents, 2)))
        assert any(e['rule'] == 'etcs_ebi' for e in tr.safety.last_events)
        assert tr.dynamics.air_brake_state()[0] == Notch.EMERGENCY
    finally:
        env.close()


def test_same_service_reapplication_interrupts_release_without_pressure_jump(dynamics):
    dynamics._apply_air_brake_command(Notch.SERVICE, 0)
    dynamics._advance_air_brake_propagation(20)
    dynamics._brake_pressure[:] = 0.8
    dynamics._reset_air_brake_command()
    dynamics._advance_air_brake_propagation(1.0)
    effective = dynamics._brake_pressure[0] * dynamics._air_brake_release_frac[0]
    assert effective < 0.8
    dynamics._apply_air_brake_command(Notch.SERVICE, 0)
    assert not dynamics._air_brake_releasing[0]
    assert dynamics._brake_pressure[0] * dynamics._air_brake_release_frac[0] == pytest.approx(effective)


def test_remote_reapplication_waits_for_wave_and_preserves_pressure(dynamics):
    dynamics._apply_air_brake_command(Notch.SERVICE, 0)
    dynamics._advance_air_brake_propagation(20)
    dynamics._brake_pressure[:] = 0.8
    dynamics._reset_air_brake_command()
    dynamics._advance_air_brake_propagation(12.0)
    dynamics._apply_air_brake_command(Notch.SERVICE, 0)
    assert dynamics._air_brake_releasing[-1]
    assert dynamics._air_brake_upgrade_pending[-1] == Notch.SERVICE
    dynamics._advance_air_brake_propagation(0.1)
    assert dynamics._air_brake_releasing[-1]
    dynamics._advance_air_brake_propagation(20.0)
    assert not dynamics._air_brake_releasing[-1]
    assert dynamics.air_brake_state()[-1] == Notch.SERVICE


def test_reapplication_wave_does_not_downgrade_new_emergency_source(dynamics):
    dynamics._apply_air_brake_command(Notch.SERVICE, 0)
    dynamics._advance_air_brake_propagation(20)
    dynamics._reset_air_brake_command()
    dynamics._advance_air_brake_propagation(1)
    dynamics._apply_air_brake_command(Notch.SERVICE, 0)
    dynamics._apply_air_brake_command(Notch.EMERGENCY, 109, bidirectional=True)
    dynamics._advance_air_brake_propagation(20)
    assert all(n == Notch.EMERGENCY for n in dynamics.air_brake_state())


def test_native_same_service_reapplication_stops_source_exhaust(dynamics):
    zeros = np.zeros(dynamics.num_vehicles)
    dynamics.step_vehicles_ed_ab(zeros, zeros, Notch.SERVICE)
    dynamics.step_vehicles_ed_ab(zeros, zeros, Notch.RELEASE)
    assert dynamics._air_brake_releasing[0]
    dynamics.step_vehicles_ed_ab(zeros, zeros, Notch.SERVICE)
    assert not dynamics._air_brake_releasing[0]
    assert dynamics.air_brake_state()[0] == Notch.SERVICE


def test_second_release_does_not_restore_remote_brake_pressure(dynamics):
    dynamics._apply_air_brake_command(Notch.SERVICE, 0)
    dynamics._advance_air_brake_propagation(20)
    dynamics._brake_pressure[:] = 0.8
    dynamics._reset_air_brake_command()
    for _ in range(140):
        dynamics._advance_air_brake_propagation(0.1)
    dynamics._apply_air_brake_command(Notch.SERVICE, 0)
    effective = dynamics._brake_pressure[-1] * dynamics._air_brake_release_frac[-1]
    release_delay = dynamics._air_brake_delay_remaining[-1]
    assert 0 < effective < 0.8
    dynamics._reset_air_brake_command()
    assert dynamics._brake_pressure[-1] * dynamics._air_brake_release_frac[-1] == pytest.approx(effective)
    assert dynamics._air_brake_delay_remaining[-1] == pytest.approx(release_delay)
    assert dynamics._air_brake_upgrade_pending[-1] is None


@pytest.mark.parametrize('resumed', [Notch.SERVICE, Notch.EMERGENCY])
def test_hold_does_not_start_another_braking_segment(dynamics, resumed):
    zeros = np.zeros(dynamics.num_vehicles)
    dynamics.step_vehicles_ed_ab(zeros, zeros, Notch.SERVICE)
    assert dynamics._brake_segment == 1
    dynamics.step_vehicles_ed_ab(zeros, zeros, None)
    assert dynamics._air_brake_active[0]
    dynamics.step_vehicles_ed_ab(zeros, zeros, resumed)
    assert dynamics._brake_segment == 1


def test_explicit_release_still_separates_braking_segments(dynamics):
    zeros = np.zeros(dynamics.num_vehicles)
    dynamics.step_vehicles_ed_ab(zeros, zeros, Notch.SERVICE)
    dynamics.step_vehicles_ed_ab(zeros, zeros, Notch.RELEASE)
    dynamics.step_vehicles_ed_ab(zeros, zeros, None)
    dynamics.step_vehicles_ed_ab(zeros, zeros, Notch.SERVICE)
    assert dynamics._brake_segment == 2


@pytest.mark.parametrize('reset_method', ['set_initial', 'set_initial_speed'])
def test_initialization_clears_previous_air_brake_state(dynamics, reset_method):
    zeros = np.zeros(dynamics.num_vehicles)
    dynamics.step_vehicles_ed_ab(zeros, zeros, Notch.EMERGENCY)
    dynamics.step_vehicles_ed_ab(zeros, zeros, Notch.RELEASE)
    if reset_method == 'set_initial':
        dynamics.set_initial(vel=np.full(dynamics.num_vehicles, 70 / 3.6))
    else:
        dynamics.set_initial_speed(70 / 3.6)
    assert not dynamics._air_brake_active.any()
    assert not dynamics._air_brake_releasing.any()
    assert all(n == Notch.RELEASE for n in dynamics.air_brake_state())
    assert np.all(dynamics._air_brake_delay_remaining == 0)
    assert np.all(dynamics._air_brake_delay_total == 0)
    assert np.all(dynamics._air_brake_release_frac == 1)
    dynamics.step_vehicles_ed_ab(zeros, zeros, Notch.SERVICE)
    assert dynamics.air_brake_state()[0] == Notch.SERVICE


def test_fleet_reset_clears_air_brake_state_between_episodes():
    env = TrainFleetEnv({'num_trains': 1, 'consist_preset': '20kt_1plus108_1plus108',
                        'decompose': 'loco_ed_ab'})
    try:
        env.reset(options={'speed': 70 / 3.6})
        d = env.trains[0].dynamics
        zeros = np.zeros(d.num_vehicles)
        d.step_vehicles_ed_ab(zeros, zeros, Notch.EMERGENCY)
        env.reset(options={'speed': 70 / 3.6})
        assert not d._air_brake_active.any()
        assert all(n == Notch.RELEASE for n in d.air_brake_state())
    finally:
        env.close()


def test_reset_service_trajectory_matches_a_fresh_fleet():
    config = {'num_trains': 1, 'consist_preset': '20kt_1plus108_1plus108',
              'decompose': 'loco_ed_ab', 'start_randomization': {'enabled': False}}
    old = TrainFleetEnv(config)
    fresh = TrainFleetEnv(config)
    try:
        old.reset(seed=11, options={'speed': 70 / 3.6})
        d = old.trains[0].dynamics
        zeros = np.zeros(d.num_vehicles)
        for _ in range(10):
            d.step_vehicles_ed_ab(zeros, zeros, Notch.EMERGENCY)
        old.reset(seed=11, options={'speed': 70 / 3.6})
        fresh.reset(seed=11, options={'speed': 70 / 3.6})
        other = fresh.trains[0].dynamics
        for _ in range(10):
            d.step_vehicles_ed_ab(zeros, zeros, Notch.SERVICE)
            other.step_vehicles_ed_ab(zeros, zeros, Notch.SERVICE)
            np.testing.assert_allclose(d.pos, other.pos, rtol=0, atol=1e-10)
            np.testing.assert_allclose(d.vel, other.vel, rtol=0, atol=1e-10)
            np.testing.assert_allclose(d._brake_pressure, other._brake_pressure)
            assert d.air_brake_state()[0] == Notch.SERVICE
    finally:
        old.close()
        fresh.close()
