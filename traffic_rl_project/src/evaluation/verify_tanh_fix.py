"""【验证】tanh 软饱和修复后：下坡循环制动是否已稳定、峰值是否合理。

对比：硬 clip 饱和（之前）→ 爆炸 17 万 kN；
tanh 软饱和（现在）→ 应稳定且峰值合理。
用动力学内部 _coupler_forces() 口径（单钩力）。
"""

import sys
from pathlib import Path

sys.path.append(str(Path(__file__).parent.parent.parent))

import numpy as np

from src.environments.train_env import TrainFormationEnv


def run_cycle(dt, n_steps):
    env = TrainFormationEnv({
        'consist_preset': '10kt_1plus0',
        'grade_profile': 'shuozhou_23800',
        'target_speed': 65.0 / 3.6,
        'dt': dt,
        'max_steps': n_steps,
        'enable_safety': False,
    })
    obs, _ = env.reset(options={'speed': 65.0 / 3.6})
    state = {'last': 0.0}
    vmax, vmin = 80.0/3.6, 40.0/3.6
    peak = 0.0          # 动力学内部（含 tanh 饱和）
    peak_linear = 0.0   # 纯线性（无饱和）参考
    v_log = []
    p = env.dynamics.coupler
    cycles = 0
    prev_brake = False
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
        # 单钩力（与动力学一致，tanh 饱和）
        f = env.dynamics._coupler_forces()
        pos = env.dynamics.pos; vel = env.dynamics.vel
        e = (pos[1:] - pos[:-1]) + p.free_length_m
        g = p.coupler_gap_m
        e_eff = e if g <= 0 else e - g*np.tanh(e/max(g, 1e-9))
        dv = vel[:-1] - vel[1:]
        f_lin = p.stiffness * e_eff - p.damping * dv
        # 单钩力 = 从车厢净力反推困难，直接算 f_lin（饱和后）
        if p.max_impulse_n > 0:
            f_sat = p.max_impulse_n * np.tanh(f_lin / p.max_impulse_n)
        else:
            f_sat = f_lin
        peak = max(peak, float(np.max(np.abs(f_sat))))
        peak_linear = max(peak_linear, float(np.max(np.abs(f_lin))))
        v_log.append(env.dynamics.vel[0])
        if term or trunc:
            break
    v = np.array(v_log)
    return {
        'peak_sat_kN': peak/1e3, 'peak_lin_kN': peak_linear/1e3,
        'v_min': np.min(v)*3.6, 'v_max': np.max(v)*3.6, 'v_end': v[-1]*3.6,
        'cycles': cycles, 'dist_km': env.dynamics.pos[0]/1000,
    }


def main():
    print("=" * 78)
    print("tanh 软饱和修复验证：下坡循环制动（无安全层, 1万吨, 单钩力）")
    print("=" * 78)
    print(f"  {'dt':<6} {'饱和峰值(kN)':<14} {'线性峰值(kN)':<14} {'速度范围':<14} {'循环':<5}")
    for dt, ns in [(0.1, 3000), (0.05, 6000), (0.02, 15000)]:
        try:
            r = run_cycle(dt, ns)
            print(f"  {dt:<6} {r['peak_sat_kN']:<14.1f} {r['peak_lin_kN']:<14.1f} "
                  f"{r['v_min']:.0f}-{r['v_max']:.0f}(末{r['v_end']:.0f}) {r['cycles']}")
            print(f"         位移 {r['dist_km']:.2f} km")
        except Exception as e:
            print(f"  {dt:<6} 异常: {type(e).__name__}")


if __name__ == '__main__':
    main()
