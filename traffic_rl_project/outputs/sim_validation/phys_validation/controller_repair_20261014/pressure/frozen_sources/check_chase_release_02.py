import sys
from pathlib import Path
import numpy as np
sys.path.insert(0,r'F:\列车大创xmc\multi-agent\traffic_rl_project')
from src.environments.train_fleet_env import TrainFleetEnv
from src.train_dynamics.braking import AirBrakeNotch
ns={'__name__':'chase_trial_contract'}
exec(compile(Path(r'D:\Codex\Documents\Train\controller_pressure_20261014\chase_release_trial_02.py').read_text(encoding='utf-8-sig'),'<trial>','exec'),ns)
for active in (False,True):
    env=ns['TrainFleetEnv']({'num_trains':2,'consist_preset':'20kt_1plus108_1plus108','grade_profile':'long_downhill','decompose':'loco_ed_ab','max_steps':3})
    env.reset(options={'speed':70/3.6})
    tr=env.trains[1]; tr.dynamics.pos-=1000; env._train_heads[1]=tr.dynamics.pos[0]
    ctrl=env.multi_loco_controllers[1]
    if active:
        tr.dynamics.step_vehicles_ed_ab(np.zeros(tr.num_vehicles),np.zeros(tr.num_vehicles),AirBrakeNotch.SERVICE,ab_sources=[(0,AirBrakeNotch.SERVICE)])
        ctrl._cyclic_braking=True
        assert tr.dynamics._air_brake_active[0] and not tr.dynamics._air_brake_releasing[0]
    captured=[]; original=ctrl.get_action_decomposed
    def record(*args,**kwargs):
        captured.append(kwargs['v_min_adj']); return original(*args,**kwargs)
    ctrl.get_action_decomposed=record
    env.step(np.zeros((env.num_agents,2)))
    assert len(captured)==1
    print("captured offset",active,captured[0]); assert np.isclose(captured[0], env.LEAN_MAX_ADJ) if active else captured[0]>env.LEAN_MAX_ADJ
    print('native chase contract',active,'passed; floor offset',captured[0])
    env.close()


