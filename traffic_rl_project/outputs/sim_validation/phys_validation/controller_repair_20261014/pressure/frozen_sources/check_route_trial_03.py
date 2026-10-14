import sys
from pathlib import Path
import numpy as np
sys.path.insert(0,r'F:\列车大创xmc\multi-agent\traffic_rl_project')
from src.environments.train_fleet_env import TrainFleetEnv
ns={'__name__':'route_contract'}
exec(compile(Path(r'D:\Codex\Documents\Train\controller_pressure_20261014\route_limits_baseline_03.py').read_text(encoding='utf-8'),'<trial>','exec'),ns)
e=ns['TrainFleetEnv']({'num_trains':2,'consist_preset':'20kt_1plus108_1plus108','grade_profile':'shuozhou_ningwuxi_beidaniu_49km','decompose':'loco_ed_ab','max_steps':20})
e.reset(options={'speed':65/3.6})
for i,tr in enumerate(e.trains):
    tr.dynamics.set_initial(pos=tr.dynamics.pos+16000,vel=tr.dynamics.vel)
    e._train_heads[i]=tr.dynamics.pos[0]
    cap,targets=ns['_route_limits'](tr,e.v_max)
    assert cap==75/3.6
    assert any(t.speed_mps==70/3.6 for t in targets)
for _ in range(3): e.step(np.zeros((e.num_agents,2)))
assert sum(t.kind=='gap' for t in e.trains[1].etcs_targets)==1
assert all(tr.line_speed_limit_mps==75/3.6 for tr in e.trains)
count=len(e.trains[0].etcs_targets)
e.step(np.zeros((e.num_agents,2)))
assert len(e.trains[0].etcs_targets)==count
print('Native route contracts passed: units, 75 km/h limit, future 70 target, gap preservation, no target accumulation')
e.close()
