"""回归：RL 默认配置（dt=0.1，含中置机车+新缓冲器）短 episode 稳定性。"""
import sys
from pathlib import Path
sys.path.append(str(Path(__file__).parent.parent.parent))

import numpy as np
from src.environments.train_env import TrainFormationEnv

for label, cfg in [
    ("万吨 1+0 (RL默认dt=0.1)", {
        'consist_preset': '10kt_1plus0', 'grade': -0.006,
        'dt': 0.1, 'max_steps': 600, 'enable_safety': True,
    }),
    ("2万吨 1+108+1+108 (dt=0.1)", {
        'consist_preset': '20kt_1plus108_1plus108',
        'grade_profile': 'shuozhou_23800',
        'dt': 0.1, 'max_steps': 600, 'enable_safety': True,
    }),
]:
    try:
        env = TrainFormationEnv(cfg)
        obs, _ = env.reset(options={'speed': 60.0 / 3.6})
        rng = np.random.default_rng(0)
        peak = 0.0
        for _ in range(600):
            acts = rng.uniform(-1.0, 1.0, env.num_vehicles)
            obs, r, term, trunc, info = env.step(acts)
            f = env.dynamics.coupler_interface_forces()
            peak = max(peak, float(np.max(np.abs(f))))
            if term or trunc:
                break
        v = env.dynamics.vel
        finite = np.all(np.isfinite(v)) and np.all(np.isfinite(env.dynamics.pos))
        print(f"[{label}] {'✅稳定' if finite else '❌NaN'} | "
              f"峰值钩力 {peak/1e3:.0f} kN | 末速 {np.max(np.abs(v))*3.6:.1f} km/h")
        env.close()
    except Exception as e:
        print(f"[{label}] ❌异常: {type(e).__name__}: {e}")
