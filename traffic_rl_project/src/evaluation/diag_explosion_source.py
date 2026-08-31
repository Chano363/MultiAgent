"""【决定性诊断】爆炸来源：是车钩位移 e 异常（结构/位置问题）还是速度差 dv 异常（阻尼/参数问题）？

判定逻辑：
- 若爆炸时 max|e| >> 缓冲器行程(0.083m) → 位置/位移异常（结构问题：积分或传播建模）
- 若爆炸时 max|dv| >> 物理可能速度差 → 速度异常（参数问题：阻尼不足或欠阻尼振荡）

记录爆炸时刻 e、dv、力、对应位置、制动状态。
"""

import sys
from pathlib import Path

sys.path.append(str(Path(__file__).parent.parent.parent))

import numpy as np

from src.environments.train_env import TrainFormationEnv


def diagnose(dt=0.05, damping=5.0e4, stiffness=5.0e6, n_steps=7000, sat=0.0):
    env = TrainFormationEnv({
        'consist_preset': '10kt_1plus0',
        'grade_profile': 'shuozhou_23800',
        'target_speed': 65.0 / 3.6,
        'dt': dt,
        'max_steps': n_steps,
        'enable_safety': False,
    })
    from src.train_dynamics.params import CouplerParams
    env.dynamics.coupler = CouplerParams(
        stiffness=stiffness, damping=damping, max_impulse_n=sat)
    obs, _ = env.reset(options={'speed': 65.0 / 3.6})

    p = env.dynamics.coupler
    state = {'last': 0.0}
    vmax, vmin = 80.0/3.6, 40.0/3.6
    record = None
    for step in range(n_steps):
        v = env.dynamics.vel[0]
        if v >= vmax:
            state['last'] = -0.75
        elif v <= vmin:
            state['last'] = 0.0
        actions = np.full(env.num_vehicles, state['last'])
        obs, reward, term, trunc, info = env.step(actions)

        pos = env.dynamics.pos
        vel = env.dynamics.vel
        e = (pos[1:] - pos[:-1]) + p.free_length_m
        # 带间隙死区（与动力学内部一致，可复现爆炸）
        e_eff = e if p.coupler_gap_m <= 0 else np.where(
            e > p.coupler_gap_m, e - p.coupler_gap_m,
            np.where(e < -p.coupler_gap_m, e + p.coupler_gap_m, 0.0))
        dv = vel[:-1] - vel[1:]
        f_adj = p.stiffness * e_eff - p.damping * dv   # 未饱和，含间隙
        pk = float(np.max(np.abs(f_adj)))
        if pk > 5.0e6 and record is None:          # 首次超过 5000 kN
            imax = int(np.argmax(np.abs(f_adj)))
            record = {
                'step': step, 't': step*dt,
                'max_e': float(np.max(np.abs(e))),
                'max_dv': float(np.max(np.abs(dv))),
                'e_at': float(e[imax]), 'e_eff_at': float(e_eff[imax]),
                'dv_at': float(dv[imax]),
                'F_at': float(f_adj[imax])/1e3,
                'braking': state['last'],
                'v_front': vel[imax]*3.6, 'v_back': vel[imax+1]*3.6,
                'pos_front': pos[imax], 'pos_back': pos[imax+1],
                'grade': env.dynamics.grade[imax]*1000,
            }
            break
        if term or trunc:
            break
    return record


def main():
    print("=" * 78)
    print("决定性诊断：爆炸来源 = 车钩位移 e 异常 还是 速度差 dv 异常？")
    print(f"缓冲器行程参考: 0.083 m (MT-2)；列车最高速度 ~22 m/s (80 km/h)")
    print(f"物理可能的最大 dv ~ 44 m/s (前车倒车+后车全速，极端)；正常 < 10 m/s")
    print("=" * 78)

    for dt, c, k, sat in [(0.05, 5.0e4, 5.0e6, 0.0),     # 无饱和（力连续）
                          (0.05, 5.0e4, 5.0e6, 2.27e6),  # 有饱和（力不连续）
                          (0.05, 2.0e5, 5.0e6, 2.27e6),  # 有饱和+大阻尼
                          (0.05, 5.0e5, 5.0e6, 2.27e6)]: # 有饱和+临界附近阻尼
        r = diagnose(dt=dt, damping=c, stiffness=k, sat=sat)
        print(f"\n[dt={dt}, c={c:.0e}, k={k:.0e}, sat={sat:.0e}]")
        if r is None:
            print("  全程未超过 5000 kN ✅ (物理合理)")
            continue
        print(f"  爆炸时刻: t={r['t']:.1f}s, 制动={'是' if r['braking']<0 else '否'}")
        print(f"  最大|e|: {r['max_e']:.3f} m  (缓冲器行程 0.083m, "
              f"合理范围 <0.1m)  → {'❌ 位置异常(结构问题)' if r['max_e']>0.1 else '✅ 位移合理'}")
        print(f"  最大|dv|: {r['max_dv']:.1f} m/s  ({r['max_dv']*3.6:.0f} km/h, "
              f"物理合理 <10 m/s)  → {'❌ 速度异常(参数/阻尼问题)' if r['max_dv']>10 else '✅ 速度合理'}")
        print(f"  峰值车钩: e={r['e_at']:.3f}m, e_eff={r['e_eff_at']:.3f}m, "
              f"dv={r['dv_at']:.1f}m/s, F={r['F_at']:.0f}kN, 坡度{r['grade']:.1f}‰")
        print(f"  前车 v={r['v_front']:.1f}km/h, 后车 v={r['v_back']:.1f}km/h, "
              f"位置 {r['pos_front']:.1f}/{r['pos_back']:.1f}m")


if __name__ == '__main__':
    main()
