"""诊断A：2万吨循环制动峰值性质（压/拉、位置、时刻、缓解还是制动段）。"""
import sys
from pathlib import Path
sys.path.append(str(Path(__file__).parent.parent.parent))

import numpy as np
from src.environments.train_env import TrainFormationEnv

env = TrainFormationEnv({
    'consist_preset': '20kt_1plus108_1plus108',
    'grade_profile': 'shuozhou_23800',
    'target_speed': 65.0 / 3.6,
    'dt': 0.01,
    'max_steps': 30000,
    'enable_safety': False,
})
obs, _ = env.reset(options={'speed': 65.0 / 3.6})
v_max, v_min = 80.0 / 3.6, 40.0 / 3.6
last = 0.0
peak = 0.0
peak_info = None
for step in range(30000):
    v = env.dynamics.vel[0]
    if v >= v_max:
        last = -0.75
    elif v <= v_min:
        last = 0.0
    obs, reward, term, trunc, info = env.step(np.full(env.num_vehicles, last))
    f = env.dynamics.coupler_interface_forces()
    idx = int(np.argmax(np.abs(f)))
    if float(np.max(np.abs(f))) > peak:
        peak = float(np.max(np.abs(f)))
        grade_here = env.dynamics.grade[idx] * 1000
        peak_info = (env.dynamics.time, idx, f[idx] / 1e3, grade_here,
                     '制动' if last < 0 else '缓解/牵引')
    if term or trunc:
        break
t, idx, fk, grade, phase = peak_info
print(f"A峰值: {peak/1e3:.0f} kN @ t={t:.1f}s, 车钩#{idx} "
      f"({'压' if fk > 0 else '拉'}钩), 当地坡度 {grade:.1f}‰, {phase}段")
# 各时刻概览
