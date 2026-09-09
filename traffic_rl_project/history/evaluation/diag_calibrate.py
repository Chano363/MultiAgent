"""【标定】Newmark + MT-2 刚度(2.7e7)下扫描阻尼 c，找使峰值落入合理区间的值。

目标：1 万吨下坡循环制动峰值 ~500-900 kN（低于 2 万吨实测 929-1021）。
实测 2 万吨正常循环制动 929-1021 kN，1 万吨应更低。
"""

import sys
from pathlib import Path

sys.path.append(str(Path(__file__).parent.parent.parent))

import numpy as np

from src.environments.train_env import TrainFormationEnv
from src.train_dynamics.params import CouplerParams


def run_cycle(damping, stiffness=2.7e7, init_kmh=65.0, max_steps=3000):
    env = TrainFormationEnv({
        'consist_preset': '10kt_1plus0',
        'grade_profile': 'shuozhou_23800',
        'target_speed': init_kmh / 3.6,
        'dt': 0.1,
        'max_steps': max_steps,
        'enable_safety': False,
    })
    env.dynamics.coupler = CouplerParams(stiffness=stiffness, damping=damping)
    obs, _ = env.reset(options={'speed': init_kmh / 3.6})

    state = {'last': 0.0}
    vmax, vmin = 80.0/3.6, 40.0/3.6
    peak = 0.0
    v_log = []
    cycles = 0
    prev_brake = False
    for step in range(max_steps):
        v = env.dynamics.vel[0]
        if v >= vmax:
            state['last'] = -0.75
        elif v <= vmin:
            state['last'] = 0.0
        actions = np.full(env.num_vehicles, state['last'])
        is_brake = state['last'] < -0.1
        if is_brake and not prev_brake:
            cycles += 1
        prev_brake = is_brake
        obs, reward, term, trunc, info = env.step(actions)
        f_adj = env.dynamics.coupler_interface_forces()
        peak = max(peak, float(np.max(np.abs(f_adj))))
        v_log.append(env.dynamics.vel[0])
        if term or trunc:
            break
    v = np.array(v_log)
    return {
        'peak_kN': peak/1e3,
        'v_min': np.min(v)*3.6, 'v_max': np.max(v)*3.6, 'v_end': v[-1]*3.6,
        'cycles': cycles,
    }


def main():
    print("=" * 78)
    print("标定：扫描阻尼 c（k=2.7e7 MT-2 等效，Newmark-β）")
    print("目标：1 万吨下坡循环制动峰值 ~500-900 kN（2 万吨实测 929-1021）")
    print("=" * 78)
    print(f"  {'c (N·s/m)':<12} {'峰值(kN)':<10} {'速度范围':<14} {'循环':<5}")
    for c in [5.0e4, 1.0e5, 2.0e5, 3.0e5, 5.0e5, 8.0e5]:
        try:
            r = run_cycle(c)
            print(f"  {c:<12.0e} {r['peak_kN']:<10.1f} "
                  f"{r['v_min']:.0f}-{r['v_max']:.0f}(末{r['v_end']:.0f}) {r['cycles']}")
        except Exception as e:
            print(f"  {c:<12.0e} 异常: {type(e).__name__}")


if __name__ == '__main__':
    main()
