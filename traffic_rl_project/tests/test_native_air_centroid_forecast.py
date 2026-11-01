from types import SimpleNamespace as S

import numpy as np
import pytest

from src.evaluation.native_air_centroid_forecast import centroid_mechanics, forecast


def test_centroid_preserves_spacing_and_obeys_external_momentum_balance():
    dyn = S(masses_kg=np.array([4., 6.]), vel=np.array([2., 4.]),
            pos=np.array([20., 10.]), num_vehicles=2, time=7.,
            _grade_forces=lambda: np.zeros(2),
            _resistance_forces=lambda: np.zeros(2))
    momentum = float(np.dot(dyn.masses_kg, dyn.vel))
    centroid_mechanics(dyn, np.array([-5., -5.]), .1)
    assert float(np.dot(dyn.masses_kg, dyn.vel))-momentum == pytest.approx(-1.)
    assert dyn.pos[0]-dyn.pos[1] == pytest.approx(10.)
    np.testing.assert_allclose(dyn.vel, [3.1, 3.1])
    assert dyn.time == pytest.approx(7.1)


@pytest.mark.parametrize('speed', [80., 81., 39., float('nan')])
def test_does_not_count_an_already_unsafe_origin_as_a_prediction(speed):
    env = S(v_min=40./3.6, v_max=80./3.6,
            trains=[S(dynamics=S(vel=np.array([speed/3.6])))])
    with pytest.raises(ValueError, match='origin'):
        forecast(env, {}, 1)
