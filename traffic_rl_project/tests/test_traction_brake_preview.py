from types import SimpleNamespace as S
import pytest
from src.evaluation.traction_brake_preview import preview_limit, candidate


def state(speed):
    return S(_traction_brake_preview_enabled=True, _formation_traction_slew_zero_rl=True,
             _traction_preview_speed_mps=speed, _traction_preview_ceiling_mps=18.,
             _traction_preview_maximum=.5, AB_SUPPRESS_MARGIN_MPS=.5)


@pytest.mark.parametrize('speed,expected', [(17.,.5),(17.5,.5),(17.75,.25),(18.,0.),(19.,0.)])
def test_tapers_before_braking_without_changing_offsets(speed,expected):
    c=state(speed)
    assert preview_limit(c,(1.,2.,.5)) == (1.,2.,expected)
    assert c._formation_traction_slew_last == expected


def test_never_raises_reduced_request():
    assert preview_limit(state(17.75),(0.,0.,.1))[2] == .1


def test_nonzero_rl_is_unchanged():
    c=state(18.)
    c._formation_traction_slew_zero_rl=False
    assert preview_limit(c,(0.,0.,.5))[2] == .5


def test_context_restores_after_error():
    from src.evaluation import formation_traction_slew as s
    from src.environments.train_fleet_env import TrainFleetEnv as E
    old=s.limited_coordination,E._step_decomposed_fleet
    with pytest.raises(RuntimeError):
        with candidate(): raise RuntimeError('scope')
    assert (s.limited_coordination,E._step_decomposed_fleet) == old
