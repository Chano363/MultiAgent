"""ED conversion follows native physics for the confirmed single-unit consist."""
import pickle
import numpy as np
import pytest
from src.environments.train_env import TrainFormationEnv
from src.controllers.multi_loco_controller import MultiLocoController

@pytest.mark.parametrize("adhesion,target_kn", [(0.9,300.0),(0.05,50.0),(0.05,300.0),(0.9,900.0)])
def test_native_force_inverse(adhesion,target_kn):
    env=TrainFormationEnv({"consist_preset":"10kt_1plus108"})
    try:
        env.reset(options={"speed":55/3.6})
        env.dynamics.friction_coef=adhesion
        ctrl=MultiLocoController(env.num_vehicles,env.loco_indices,ed_native_force_conversion=True)
        before=pickle.dumps(env.dynamics.__dict__)
        level=ctrl._ed_frac_for_total_kn(env,target_kn)
        assert pickle.dumps(env.dynamics.__dict__)==before
        cmd=np.zeros(env.num_vehicles);cmd[env.loco_indices]=level
        actual=-env.dynamics._electric_braking_forces(cmd).sum()
        cmd[env.loco_indices]=1.0
        capacity=-env.dynamics._electric_braking_forces(cmd).sum()
        assert actual==pytest.approx(min(target_kn*1000,capacity),abs=0.1)
    finally:
        env.close()
