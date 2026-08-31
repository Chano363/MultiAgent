"""【诊断】循环制动掉速：对照 release_sync（同步缓解）vs 缓解波传播。

现象：下坡循环制动末速掉到 9 km/h（物理上 -10.9‰ 缓解后应加速）。
定位：是缓解波传播实现问题，还是制动力/控制器问题。
"""

import sys
from pathlib import Path

sys.path.append(str(Path(__file__).parent.parent.parent))

import numpy as np

from src.environments.train_env import TrainFormationEnv


def run(release_sync, brake=-0.75, max_steps=3000):
    env = TrainFormationEnv({
        'consist_preset': '10kt_1plus0',
        'grade_profile': 'shuozhou_23800',
        'target_speed': 65.0 / 3.6,
        'dt': 0.1,
        'max_steps': max_steps,
        'enable_safety': False,
        'release_sync': release_sync,
    })
    obs, _ = env.reset(options={'speed': 65.0 / 3.6})
    state = {'last': 0.0}
    vmax, vmin = 80.0/3.6, 40.0/3.6
    v_log, brake_log = [], []
    for step in range(max_steps):
        v = env.dynamics.vel[0]
        if v >= vmax:
            state['last'] = brake
        elif v <= vmin:
            state['last'] = 0.0
        actions = np.full(env.num_vehicles, state['last'])
        obs, reward, term, trunc, info = env.step(actions)
        v_log.append(env.dynamics.vel[0])
        brake_log.append(state['last'])
        if term or trunc:
            break
    v = np.array(v_log)
    b = np.array(brake_log)
    braking_frac = np.mean(b < -0.1)
    return {
        'v_min': np.min(v)*3.6, 'v_max': np.max(v)*3.6, 'v_end': v[-1]*3.6,
        'braking_frac': braking_frac,
        'brake_cycles': int(np.sum((b[:-1] >= -0.1) & (b[1:] < -0.1))),
    }


def main():
    print("=" * 78)
    print("对照：release_sync（同步缓解）vs 缓解波传播（物理真实）")
    print("=" * 78)
    for rs, label in [(False, "缓解波传播(默认)"), (True, "同步缓解(release_sync)")]:
        for brk in [-0.75, -0.5]:
            r = run(rs, brake=brk)
            print(f"[{label} 制动{brk}]: 速度 {r['v_min']:.0f}-{r['v_max']:.0f}"
                  f"(末{r['v_end']:.0f}) | 制动占比 {r['braking_frac']*100:.0f}% "
                  f"| 循环 {r['brake_cycles']}次")


if __name__ == '__main__':
    main()
