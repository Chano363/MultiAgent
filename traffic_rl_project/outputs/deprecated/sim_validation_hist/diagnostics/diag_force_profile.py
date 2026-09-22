"""诊断：基准B中车钩力沿车列的空间分布 + 速度/制动状态，定位大力来源。"""
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


consist = make_B_consist()
p = CouplerParams()
dt = 0.01
td = TrainDynamics(consist, coupler=p, dt=dt)
td.set_grade(-0.006)
td.set_initial_speed(60.0 / 3.6)
n = consist.num_vehicles
snapshots = {10, 20, 30, 40, 50, 55, 60, 62, 65, 70}
for step in range(int(80 / dt)):
    td.step_vehicles_ed_ab(
        throttle=np.zeros(n), ed_throttle=np.zeros(n),
        ab_command=AirBrakeNotch.SERVICE,
    )
    t = round(td.time)
    if t in snapshots and (step % int(1 / dt) == 0):
        f = td.coupler_interface_forces() / 1e3
        e = (td.pos[1:] - td.pos[:-1]) + p.free_length_m
        x_el = np.maximum(np.abs(e) - p.coupler_gap_m, 0.0)
        # 分段统计：头部(1-10)、前中(11-30)、中(31-70)、后中(71-95)、尾部(96-106)
        segs = [(0, 10, '头1-10'), (10, 30, '前中'), (30, 70, '中部'),
                (70, 95, '后中'), (95, 106, '尾96-106')]
        seg_str = ' | '.join(
            f"{name}:{np.max(np.abs(f[a:b])):.0f}" for a, b, name in segs)
        act = int(np.sum(td._air_brake_active))
        print(f"t={t:3d}s v0={td.vel[0]*3.6:5.1f} v末={td.vel[-1]*3.6:5.1f} "
              f"制动生效={act:3d} | 峰值|f|={np.max(np.abs(f)):6.0f} kN [{seg_str}] "
              f"| 最大行程={np.max(x_el)*1e3:5.0f}mm")
    if np.max(np.abs(td.vel)) < 0.05:
        print(f"停车 t={td.time:.1f}s，最终峰值")
        f = td.coupler_interface_forces() / 1e3
        idx = np.argsort(np.abs(f))[-5:]
        print("  最大5个车钩位置:", sorted(idx.tolist()),
              "值:", [f"{f[i]:.0f}" for i in sorted(idx.tolist())])
        print(f"  vel分布: 头{td.vel[:3]*3.6} 尾{td.vel[-3:]*3.6}")
        break
