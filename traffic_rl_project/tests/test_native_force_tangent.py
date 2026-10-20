"""Independent finite-difference checks of the native nonlinear force tangent."""
from pathlib import Path

import numpy as np
import pytest
import yaml

from src.environments.train_fleet_env import TrainFleetEnv
from src.evaluation.native_force_tangent import interface_tangent, acceleration_jacobian


@pytest.fixture
def dynamics():
    cfg = yaml.safe_load(Path('configs/experiments/single_10kt108_coupler_rulecal.yaml')
                         .read_text(encoding='utf-8'))['env_cfg']
    cfg.update(eval_mode=True, start_randomization={'enabled': False})
    env = TrainFleetEnv(cfg)
    env.reset(seed=0, options={'speed': 70/3.6})
    try:
        yield env.trains[0].dynamics
    finally:
        env.close()


def band_to_dense(band):
    matrix = np.diag(band[1])
    matrix += np.diag(band[0, 1:], 1) + np.diag(band[2, :-1], -1)
    return matrix


def test_interface_derivatives_cover_gap_switch_limit_and_saturation(dynamics):
    dyn = dynamics
    # Independent interfaces let us test tension/compression, dead zone,
    # loading/unloading, velocity switch and rigid contact together.
    e = np.resize([-.13, -.0773, -.0373, -.006, .006, .0273, .0613, .13], 108)
    dv = np.resize([-.007, -.0011, 0, .0013, .008], 108)
    x = np.r_[0.0, np.cumsum(e - dyn.coupler.free_length_m)]
    v = np.r_[20.0, 20.0 - np.cumsum(dv)]
    de, ddv = interface_tangent(dyn, x, v)
    fd_e = (dyn._coupler_interface_forces_vec(e+1e-8, dv)
            - dyn._coupler_interface_forces_vec(e-1e-8, dv))/2e-8
    fd_v = (dyn._coupler_interface_forces_vec(e, dv+1e-8)
            - dyn._coupler_interface_forces_vec(e, dv-1e-8))/2e-8
    np.testing.assert_allclose(de, fd_e, rtol=2e-6, atol=0.2)
    np.testing.assert_allclose(ddv, fd_v, rtol=2e-6, atol=0.2)
    dyn._cp['max_impulse_n'][:] = 100
    saturated_de, saturated_dv = interface_tangent(dyn, x, v)
    expected = (dyn._coupler_interface_forces_vec(e+1e-8, dv)
                - dyn._coupler_interface_forces_vec(e-1e-8, dv))/2e-8
    np.testing.assert_allclose(saturated_de, expected, rtol=2e-6, atol=0.2)
    assert np.max(np.abs(saturated_dv)) == 0


@pytest.mark.parametrize('h', [.0025, .000625])
def test_acceleration_jacobian_matches_full_native_residual(dynamics, h):
    dyn = dynamics
    rng = np.random.default_rng(412)
    e = rng.uniform(.022, .077, dyn.num_vehicles-1)
    x = np.r_[0.0, np.cumsum(e-dyn.coupler.free_length_m)]
    v = 20 + rng.uniform(-.002, .002, dyn.num_vehicles)
    direction = rng.normal(size=dyn.num_vehicles)
    eps = .0001
    # Differentiate the entire native state-force vector, not our formulas.
    derivative = dyn.masses_kg*direction - (
        dyn._state_forces(x+.25*h*h*eps*direction, v+.5*h*eps*direction)
        - dyn._state_forces(x-.25*h*h*eps*direction, v-.5*h*eps*direction))/(2*eps)
    expected = band_to_dense(acceleration_jacobian(dyn, x, v, h)) @ direction
    np.testing.assert_allclose(expected, derivative, rtol=1e-5, atol=.2)


def test_analytic_newton_matches_native_force_equilibrium(dynamics):
    import copy
    from src.evaluation.adaptive_newmark_candidate import advance_mechanics
    a, b = dynamics, copy.deepcopy(dynamics)
    e = np.full(a.num_vehicles-1, .0473)
    a.pos = np.r_[0.0, np.cumsum(e-a.coupler.free_length_m)]
    b.pos = a.pos.copy()
    force = np.linspace(-2000, -1000, a.num_vehicles)
    for dyn, solver in [(a, 'newton'), (b, 'newton_analytic')]:
        stats = advance_mechanics(dyn, force, .01, max_step=.000625,
                                  force_tol_n=.1, solver=solver)
        assert stats['max_force_residual_n'] <= .1
        assert stats['rejected'] == 0
    np.testing.assert_allclose(a.pos, b.pos, rtol=0, atol=1e-9)
    np.testing.assert_allclose(a.vel, b.vel, rtol=0, atol=1e-8)
    np.testing.assert_allclose(a.coupler_interface_forces(),
                               b.coupler_interface_forces(), rtol=0, atol=1)
