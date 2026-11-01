from types import SimpleNamespace as S
import numpy as np
import pytest
from src.evaluation.ready_cycle_pacing import arm_current_cycle, candidate


def state():
    ctrl=[S(cyclic_release_kmh=x,_ab_on=[True],_ab_step=3000,
            _ab_last_release_step=[0],dt=.1,ab_min_refill_s=222.) for x in (54.,50.,50.)]
    trains=[S(dynamics=S(pos=np.array([100.,90.]),_brake_pressure=np.ones(2),
                        _air_brake_release_frac=np.ones(2),
                        _air_braking_forces=lambda: np.array([-1000.,-1000.]))) for _ in ctrl]
    return S(num_trains=3,v_min=40./3.6,multi_loco_controllers=ctrl,trains=trains)


def test_arming_preserves_kinematics_clocks_and_follower_thresholds():
    e=state()
    old=[t.dynamics.pos.copy() for t in e.trains]
    _,m=arm_current_cycle(e,{})
    assert [c.cyclic_release_kmh for c in e.multi_loco_controllers] == [53.,50.,50.]
    assert all(c._ab_step==3000 for c in e.multi_loco_controllers)
    assert all(np.array_equal(p,t.dynamics.pos) for p,t in zip(old,e.trains))
    assert m['ready_cycle_pacing_trial']['restore_after_release']


@pytest.mark.parametrize('condition',['source','pressure','refill','release'])
def test_reject_before_mutating_leader(condition):
    e=state()
    if condition=='source': e.multi_loco_controllers[1]._ab_on=[False]
    if condition=='pressure': e.trains[2].dynamics._brake_pressure[:]=.5
    if condition=='refill': e.multi_loco_controllers[1]._ab_step=100
    if condition=='release': e.trains[2].dynamics._air_brake_release_frac[:]=.5
    with pytest.raises(ValueError): arm_current_cycle(e,{})
    assert e.multi_loco_controllers[0].cyclic_release_kmh==54.


def test_restores_default_after_actual_source_release(monkeypatch):
    from src.controllers.multi_loco_controller import MultiLocoController as C
    def release(self,*args,**kwargs):
        assert self.cyclic_release_kmh==53.
        self._ab_on=[False]
        return 'action'
    monkeypatch.setattr(C,'get_action_decomposed',release)
    e=state()
    arm_current_cycle(e,{})
    ctrl=e.multi_loco_controllers[0]
    with candidate(): assert C.get_action_decomposed(ctrl)=='action'
    assert ctrl.cyclic_release_kmh==54.
    assert not ctrl._ready_cycle_override_active
    assert C.get_action_decomposed is release
