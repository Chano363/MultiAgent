"""【诊断】Newmark-β 下动力学内部的实际车钩位移 e / 速度差 dv / 加速度，定位 12 万 kN 来源。"""

import sys
from pathlib import Path

sys.path.append(str(Path(__file__).parent.parent.parent))

import numpy as np

from src.environments.train_env import TrainFormationEnv


def main():
    env = TrainFormationEnv({
        'consist_preset': '10kt_1plus0',
        'grade_profile': 'shuozhou_23800',
        'target_speed': 65.0 / 3.6,
        'dt': 0.1,
        'max_steps': 3000,
        'enable_safety': False,
    })
    obs, _ = env.reset(options={'speed': 65.0 / 3.6})
    state = {'last': 0.0}
    vmax, vmin = 80.0/3.6, 40.0/3.6
    p = env.dynamics.coupler
    max_e, max_dv, max_a = 0.0, 0.0, 0.0
    e_peak_step, dv_peak_step, a_peak_step = 0, 0, 0
    v_log = []
    for step in range(3000):
        v = env.dynamics.vel[0]
        if v >= vmax:
            state['last'] = -0.75
        elif v <= vmin:
            state['last'] = 0.0
        actions = np.full(env.num_vehicles, state['last'])
        obs, reward, term, trunc, info = env.step(actions)
        pos = env.dynamics.pos
        vel = env.dynamics.vel
        e = np.abs((pos[1:] - pos[:-1]) + p.free_length_m)
        dv = np.abs(vel[:-1] - vel[1:])
        em = float(np.max(e)) if len(e) else 0.0
        dvm = float(np.max(dv)) if len(dv) else 0.0
        am = float(np.max(np.abs(env.dynamics._acc0)))
        if em > max_e: max_e, e_peak_step = em, step
        if dvm > max_dv: max_dv, dv_peak_step = dvm, step
        if am > max_a: max_a, a_peak_step = am, step
        v_log.append(vel[0])
        if term or trunc:
            break
    v = np.array(v_log)
    print("=" * 70)
    print("Newmark-β 下坡循环制动：动力学内部状态诊断")
    print("=" * 70)
    print(f"速度范围: {np.min(v)*3.6:.1f}~{np.max(v)*3.6:.1f} km/h | 末速 {v[-1]*3.6:.1f}")
    print(f"最大|车钩位移 e|: {max_e:.4f} m @ step {e_peak_step}  "
          f"(缓冲器行程 0.083m)")
    print(f"最大|速度差 dv|: {max_dv:.2f} m/s @ step {dv_peak_step}  "
          f"({max_dv*3.6:.0f} km/h)")
    print(f"最大|加速度 a|: {max_a:.1f} m/s² @ step {a_peak_step}  "
          f"({max_a/9.8:.1f} g)")


if __name__ == '__main__':
    main()
