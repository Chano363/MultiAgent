"""【诊断】扫描阻尼×步长，验证能否把下坡循环制动峰值压到合理量级。

背景：下坡缓解波瞬态导致无安全层峰值 4540 kN（机车64 vs 尾部46.7 km/h）。
平直轨道仅 810 kN。怀疑阻尼 5e4 太小 + 半隐式 Euler 大阻尼不稳定。
本脚本扫描 (c, dt)，看下坡循环制动峰值能否降到 ~1000 kN 量级。

用法：python src/evaluation/diag_damping_scan.py
"""

import sys
from pathlib import Path

sys.path.append(str(Path(__file__).parent.parent.parent))

import numpy as np

from src.train_dynamics.params import CouplerParams
from src.environments.train_env import TrainFormationEnv


def run_cycle(c, dt, n_steps=3000):
    env = TrainFormationEnv({
        'consist_preset': '10kt_1plus0',
        'grade_profile': 'shuozhou_23800',
        'target_speed': 65.0 / 3.6,
        'dt': dt,
        'max_steps': n_steps,
        'enable_safety': False,
    })
    # 覆盖阻尼
    env.dynamics.coupler = CouplerParams(
        stiffness=5.0e6, damping=c, max_impulse_n=0.0)  # 无饱和，看纯物理
    obs, _ = env.reset(options={'speed': 65.0 / 3.6})

    state = {'last': 0.0}
    vmax, vmin = 80.0/3.6, 40.0/3.6
    peak = 0.0
    v0_log = []
    for step in range(n_steps):
        v = env.dynamics.vel[0]
        if v >= vmax:
            state['last'] = -0.75
        elif v <= vmin:
            state['last'] = 0.0
        actions = np.full(env.num_vehicles, state['last'])
        obs, reward, term, trunc, info = env.step(actions)
        pk = float(np.max(np.abs(env.dynamics._coupler_forces())))
        peak = max(peak, pk)
        v0_log.append(env.dynamics.vel[0])
        if term or trunc:
            break
    return peak, np.array(v0_log)


def main():
    print("=" * 78)
    print("扫描阻尼×步长：下坡循环制动（无饱和）峰值")
    print("=" * 78)
    print(f"  {'c (N·s/m)':<12} {'dt':<6} {'峰值(kN)':<10} {'末速(km/h)':<10}")
    for c in [5.0e4, 2.0e5, 5.0e5, 8.0e5]:
        for dt in [0.1, 0.05, 0.02]:
            try:
                peak, v = run_cycle(c, dt)
                print(f"  {c:<12.0e} {dt:<6} {peak/1e3:<10.1f} {v[-1]*3.6:<10.1f}")
            except (OverflowError, FloatingPointError):
                print(f"  {c:<12.0e} {dt:<6} 爆炸 ❌")
            except ValueError:
                print(f"  {c:<12.0e} {dt:<6} nan ❌")


if __name__ == '__main__':
    main()
