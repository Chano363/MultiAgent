"""【诊断】下坡循环制动（无安全层）扫描阻尼，找能压住峰值到合理量级的 c。

背景：下坡循环制动缓解波瞬态导致峰值打满缓冲器（2270+ kN），
而真实 2 万吨实测仅 929-1021 kN（1 万吨应更低）。强制动受控下
增大阻尼显著降峰值（639→419 kN）。本脚本在下坡循环制动下扫描阻尼。

用法：python src/evaluation/diag_cycle_damping.py
"""

import sys
from pathlib import Path

sys.path.append(str(Path(__file__).parent.parent.parent))

import numpy as np

from src.train_dynamics.params import CouplerParams
from src.environments.train_env import TrainFormationEnv


def run_cycle(c, stiffness=5.0e6, n_steps=3000, saturation=2.27e6, sat_off=False, dt=0.1):
    env = TrainFormationEnv({
        'consist_preset': '10kt_1plus0',
        'grade_profile': 'shuozhou_23800',
        'target_speed': 65.0 / 3.6,
        'dt': dt,
        'max_steps': n_steps,
        'enable_safety': False,
    })
    env.dynamics.coupler = CouplerParams(
        stiffness=stiffness, damping=c,
        max_impulse_n=0.0 if sat_off else saturation)
    obs, _ = env.reset(options={'speed': 65.0 / 3.6})

    state = {'last': 0.0}
    vmax, vmin = 80.0/3.6, 40.0/3.6
    peak = 0.0
    peak_unsat = 0.0
    v_log = []
    prev_brake = False
    cycles = 0
    for step in range(n_steps):
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
        # 单钩断面力（f_adj），与实测 929/1021 kN 同口径
        pos = env.dynamics.pos; vel = env.dynamics.vel
        p = env.dynamics.coupler
        e = (pos[1:] - pos[:-1]) + p.free_length_m
        if p.coupler_gap_m > 0.0:
            e_eff = np.where(e > p.coupler_gap_m, e - p.coupler_gap_m,
                             np.where(e < -p.coupler_gap_m, e + p.coupler_gap_m, 0.0))
        else:
            e_eff = e
        dv = vel[:-1] - vel[1:]
        f_adj = p.stiffness * e_eff - p.damping * dv
        if p.max_impulse_n > 0.0:
            f_adj = np.clip(f_adj, -p.max_impulse_n, p.max_impulse_n)
        peak = max(peak, float(np.max(np.abs(f_adj))))
        v_log.append(env.dynamics.vel[0])
        if term or trunc:
            break
    v = np.array(v_log)
    return {
        'peak_sat_kN': peak/1e3,
        'v_min': np.min(v)*3.6, 'v_max': np.max(v)*3.6, 'v_end': v[-1]*3.6,
        'cycles': cycles,
    }


def main():
    print("=" * 78)
    print("下坡循环制动（无安全层, 1万吨, 单钩断面力）扫描刚度×阻尼")
    print("实测基准: 2万吨 929/1021 kN；1万吨应更低(~500-900 kN 合理)")
    print("=" * 78)
    print("[1] 扫描刚度（c=5e4）:")
    print(f"  {'k':<12} {'峰值(kN)':<10} {'速度范围':<14} {'循环次数':<8}")
    for k in [5.0e6, 1.0e7, 2.0e7, 2.7e7]:
        try:
            r = run_cycle(5.0e4, stiffness=k)
            print(f"  {k:<12.0e} {r['peak_sat_kN']:<10.1f} "
                  f"{r['v_min']:.0f}-{r['v_max']:.0f}(末{r['v_end']:.0f}) "
                  f"{r['cycles']}")
        except Exception as e:
            print(f"  {k:<12.0e} 异常: {type(e).__name__}")

    print("\n[2] 扫描阻尼（k=1e7）:")
    print(f"  {'c':<12} {'峰值(kN)':<10} {'速度范围':<14} {'循环次数':<8}")
    for c in [5.0e4, 1.0e5, 2.0e5, 4.0e5]:
        try:
            r = run_cycle(c, stiffness=1.0e7)
            print(f"  {c:<12.0e} {r['peak_sat_kN']:<10.1f} "
                  f"{r['v_min']:.0f}-{r['v_max']:.0f}(末{r['v_end']:.0f}) "
                  f"{r['cycles']}")
        except Exception as e:
            print(f"  {c:<12.0e} 异常: {type(e).__name__}")

    print("\n[3] 未饱和单钩力峰值（物理冲击真实值，应~500-1500 才合理）:")
    print(f"  {'k':<8} {'c':<10} {'未饱和峰值(kN)':<14} {'速度范围':<12}")
    for k, c in [(5.0e6, 5.0e4), (1.0e7, 2.0e5), (2.0e7, 2.0e5),
                 (2.0e7, 4.0e5), (1.0e7, 5.0e5)]:
        try:
            r = run_cycle(c, stiffness=k, sat_off=True)
            print(f"  {k:<8.0e} {c:<10.0e} {r['peak_sat_kN']:<14.1f} "
                  f"{r['v_min']:.0f}-{r['v_max']:.0f}")
        except Exception as e:
            print(f"  {k:<8.0e} {c:<10.0e} 异常: {type(e).__name__}")

    print("\n[4] 关键验证：dt 对循环制动未饱和峰值的影响（k=5e6,c=5e4）:")
    print(f"  {'dt':<6} {'未饱和峰值(kN)':<14} {'速度范围':<12} {'循环次数':<8}")
    for dt in [0.1, 0.05, 0.02]:
        try:
            r = run_cycle(5.0e4, stiffness=5.0e6, sat_off=True, dt=dt)
            print(f"  {dt:<6} {r['peak_sat_kN']:<14.1f} "
                  f"{r['v_min']:.0f}-{r['v_max']:.0f} {r['cycles']}")
        except Exception as e:
            print(f"  {dt:<6} 异常: {type(e).__name__}")


if __name__ == '__main__':
    main()
