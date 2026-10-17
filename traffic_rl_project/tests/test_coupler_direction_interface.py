"""Check the force coordinate convention at the physics/safety boundary."""
import numpy as np
import pytest

from src.safety_layer import SafetyLayer
from src.train_dynamics.params import TrainConsist, VehicleParams
from src.train_dynamics.train import TrainDynamics


@pytest.mark.parametrize('spacing,tension', [(12.04, True), (11.96, False)])
def test_real_coupler_direction_reaches_safety_layer(spacing, tension):
    dynamics = TrainDynamics(TrainConsist([VehicleParams(), VehicleParams()]))
    dynamics.pos[:] = [0.0, -spacing]
    dynamics.vel[:] = 20.0
    raw = dynamics.coupler_interface_forces().copy()
    # A stretched link pulls the front vehicle backwards; compression pushes it.
    assert (raw[0] < 0.0) == tension
    np.testing.assert_allclose(dynamics._coupler_forces(), [raw[0], -raw[0]])
    signed = dynamics.coupler_interface_forces_per_vehicle_signed()
    np.testing.assert_allclose(signed, [-raw[0], -raw[0]])
    np.testing.assert_allclose(np.abs(signed),
                               dynamics.coupler_interface_forces_per_vehicle())
    safety = SafetyLayer(2, coupler_force_limit_n=0.8 * abs(raw[0]),
                         coupler_override='direction')
    state = {
        'vel': dynamics.vel,
        'coupler_forces': dynamics.coupler_interface_forces_per_vehicle(),
        'coupler_forces_signed': signed,
        'gaps': np.full(2, spacing),
    }
    corrected = safety.protect(np.array([-0.8, -0.8]), state)
    np.testing.assert_allclose(corrected, 0.0 if tension else -0.3)
    # Reading the safety view must not change the force used by the integrator.
    np.testing.assert_array_equal(dynamics.coupler_interface_forces(), raw)


def test_signed_view_chooses_larger_adjacent_force_in_mixed_chain():
    dynamics = TrainDynamics(TrainConsist([VehicleParams()] * 3))
    dynamics.pos[:] = [0.0, -12.04, -24.02]
    raw = dynamics.coupler_interface_forces()
    signed = dynamics.coupler_interface_forces_per_vehicle_signed()
    assert raw[0] < 0.0 < raw[1]
    assert signed[0] > 0.0 > signed[-1]
    expected_middle = -raw[np.argmax(np.abs(raw))]
    assert signed[1] == pytest.approx(expected_middle)
    np.testing.assert_allclose(np.abs(signed),
                               dynamics.coupler_interface_forces_per_vehicle())


@pytest.mark.parametrize('mode', ['min_brake', 'release'])
def test_nondirectional_modes_ignore_signed_convention(mode):
    safety = SafetyLayer(2, coupler_force_limit_n=500000.0, coupler_override=mode)
    state = {'vel': np.full(2, 20.0), 'gaps': np.full(2, 12.0),
             'coupler_forces': np.full(2, 650000.0)}
    action = np.full(2, -0.8)
    before = safety.protect(action, dict(state, coupler_forces_signed=np.full(2, 650000.0)))
    after = safety.protect(action, dict(state, coupler_forces_signed=np.full(2, -650000.0)))
    np.testing.assert_array_equal(before, after)
