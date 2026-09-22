"""诊断：缓冲器迟滞模型在不同 dt 下的收敛性 + 状态量追踪。

文献标准 LTD（翟婉明/Cole/于宗泽）缓冲器冲击事件 ~50-100ms，
dt=0.1s 时 1 m/s 相对速度每步位移 100mm > 83mm 全行程 → 无法解析冲击。
测试 dt = 0.1 / 0.02 / 0.01 / 0.005，追踪：力峰值、缓冲器行程占用、
相对速度、饱和占比。
"""
import sys
from pathlib import Path
sys.path.append(str(Path(__file__).parent.parent.parent))

import numpy as np
from src.train_dynamics.params import (VehicleParams, LocomotiveParams,
                                       TrainConsist, CouplerParams)
from src.train_dynamics.train import TrainDynamics
from src.train_dynamics.braking import AirBrakeNotch


def make_B_consist():
    loco = LocomotiveParams(
        mass_t=200.0, no_of_axles=8, frontal_area_m2=11.5, drag_coef=1.4,
        length_m=22.0, max_power_kw=10000.0, transmission_efficiency=0.85,
        max_speed_mps=30.0, n_notches=8,
    )
    car = VehicleParams(mass_t=100.0, no_of_axles=4, frontal_area_m2=10.0,
                        drag_coef=1.0, length_m=12.0)
    return TrainConsist([loco, loco] + [car for _ in range(105)])


def run_B(dt, max_time=140.0):
    consist = make_B_consist()
    p = CouplerParams()
    td = TrainDynamics(consist, coupler=p, dt=dt)
    td.set_grade(-0.006)
    td.set_initial_speed(60.0 / 3.6)
    n = consist.num_vehicles
    peak = 0.0
    peak_x = 0.0        # 缓冲器最大压缩行程占用
    peak_dv = 0.0       # 相邻车最大相对速度
    sat_steps = 0       # 撞到 2270 饱和的车钩·步数
    contact_steps = 0   # 接触中的车钩·步数
    total_steps = 0
    t_log, f_log = [], []
    for step in range(int(max_time / dt)):
        td.step_vehicles_ed_ab(
            throttle=np.zeros(n), ed_throttle=np.zeros(n),
            ab_command=AirBrakeNotch.SERVICE,
        )
        f = td.coupler_interface_forces()
        peak = max(peak, float(np.max(np.abs(f))))
        # 行程/相对速度诊断
        e = (td.pos[1:] - td.pos[:-1]) + p.free_length_m
        d = np.abs(e) - p.coupler_gap_m
        x_el = np.maximum(d, 0.0)
        peak_x = max(peak_x, float(np.max(x_el)))
        dv = td.vel[:-1] - td.vel[1:]
        peak_dv = max(peak_dv, float(np.max(np.abs(dv))))
        total_steps += len(f)
        sat_steps += int(np.sum(np.abs(f) >= 0.999 * p.max_impulse_n))
        contact_steps += int(np.sum(d > 0))
        if step % int(1.0 / dt) == 0:
            t_log.append(td.time)
            f_log.append(float(np.max(np.abs(f))))
        if np.max(np.abs(td.vel)) < 0.05:
            break
    v_end = float(np.max(np.abs(td.vel))) * 3.6
    return {
        'dt': dt, 'peak_kN': peak / 1e3, 'stop_s': td.time, 'v_end': v_end,
        'peak_x_mm': peak_x * 1e3, 'peak_dv': peak_dv,
        'sat_ratio': sat_steps / max(total_steps, 1),
        'contact_ratio': contact_steps / max(total_steps, 1),
        'f_timeline': list(zip(t_log[::5], f_log[::5])),
    }


if __name__ == '__main__':
    print("基准B诊断（-6‰, 万吨, SERVICE, 初速60）: 目标峰值 634 kN（杨敏）")
    for dt in [0.1, 0.02, 0.01, 0.005]:
        r = run_B(dt)
        print(f"\n--- dt={dt}s ---")
        print(f"  峰值单钩力 {r['peak_kN']:.0f} kN | 停车 {r['stop_s']:.0f}s | "
              f"末速 {r['v_end']:.1f} km/h")
        print(f"  最大行程占用 {r['peak_x_mm']:.0f} mm (行程83) | "
              f"最大相对速度 {r['peak_dv']:.2f} m/s")
        print(f"  饱和占比 {r['sat_ratio']*100:.2f}% | 接触占比 {r['contact_ratio']*100:.1f}%")
        tl = ' '.join(f"{t:.0f}s:{f/1e3:.0f}" for t, f in r['f_timeline'][:20])
        print(f"  力时间线(kN): {tl}")
