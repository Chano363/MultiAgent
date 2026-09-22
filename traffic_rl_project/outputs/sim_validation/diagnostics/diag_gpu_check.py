import time
import torch
from pathlib import Path
import sys
sys.path.append(str(Path(__file__).parent.parent.parent))

print("cuda available:", torch.cuda.is_available())
if torch.cuda.is_available():
    print("device:", torch.cuda.get_device_name(0))

import numpy as np
from src.environments.train_fleet_env import TrainFleetEnv

t0 = time.time()
env = TrainFleetEnv({
    'num_trains': 3, 'consist_preset': '10kt_1plus0',
    'grade_profile': 'shuozhou_23800',
    'v_max': 80.0 / 3.6, 'v_min': 40.0 / 3.6,
    'target_gap': 100.0, 'headway_s': 5.0,
    'max_steps': 100, 'max_accel': 1.0,
    'use_coupler_constraint': True, 'hierarchical': False,
    'adj_coef': 0.0, 'eval_mode': True,
})
obs, _ = env.reset()
rng = np.random.default_rng(0)
for i in range(100):
    obs, r, term, trunc, info = env.step(rng.uniform(-0.2, 0.2, 3))
    if term or trunc:
        break
dt = time.time() - t0
print(f"100 步耗时 {dt:.1f}s → 每步 {dt/100*1000:.0f} ms")
print("末速:", np.max(np.abs(env.dynamics.vel)) * 3.6 if hasattr(env, 'dynamics') else 'n/a')
