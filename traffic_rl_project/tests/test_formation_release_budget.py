from types import SimpleNamespace as S
import numpy as np
import pytest
from src.evaluation.formation_release_budget import coordinated_floor, candidate


def state():
    c = S(_formation_release_budget_enabled=True, _ab_on=[False], _ab_step=3000,
          _ab_last_release_step=[0], dt=.1, ab_min_refill_s=222.,
          _held_air_gap_reference_m=183., AB_SUPPRESS_MARGIN_MPS=.5,
          _formation_release_speed_ceiling_mps=22., _operating_ceiling=lambda t,v,adj:v)
    t = S(dynamics=S(pos=np.array([0.]), vel=np.array([13.]),
                    _air_braking_forces=lambda: np.array([0.])),
          etcs_targets=[S(kind='gap',position_m=300.,speed_mps=16.)], etcs_curve=object(),
          safety=S(_etcs_check=lambda *args: (20., 19.)))
    return c, t


def test_only_removes_deceleration_margin_not_add_traction():
    c,t=state()
    assert coordinated_floor(c,t,np.zeros((1,2)),11.) == 13.
    assert t.etcs_targets[0].speed_mps == 16.


@pytest.mark.parametrize('case',['refill','air','source','close','slow_front','sbi','rl'])
def test_native_budget_fallback(case):
    c,t=state()
    rl=np.zeros((1,2))
    if case=='refill': c._ab_step=100
    if case=='air': t.dynamics._air_braking_forces=lambda: np.array([-10.])
    if case=='source': c._ab_on=[True]
    if case=='close': t.etcs_targets[0].position_m=100.
    if case=='slow_front': t.etcs_targets[0].speed_mps=12.
    if case=='sbi': t.safety._etcs_check=lambda *args: (14.,13.4)
    if case=='rl': rl[0,0]=.1
    assert coordinated_floor(c,t,rl,11.) == 11.


def test_context_restores_on_error():
    from src.evaluation import release_budget_guard as g
    original=g.limit_release_request
    with pytest.raises(RuntimeError):
        with candidate(): raise RuntimeError('scope')
    assert g.limit_release_request is original
