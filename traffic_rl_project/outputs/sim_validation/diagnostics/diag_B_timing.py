"""诊断B：峰值出现时刻/行程/是否停车钳位伪影。"""
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
peak = 0.0
peak_t = 0.0
peak_x = 0.0
stopped = False
for step in range(int(120 / dt)):
    td.step_vehicles_ed_ab(
        throttle=np.zeros(n), ed_throttle=np.zeros(n),
        ab_command=AirBrakeNotch.SERVICE,
    )
    f = td.coupler_interface_forces()
    if np.max(np.abs(f)) > peak:
        peak = float(np.max(np.abs(f)))
        peak_t = td.time
        e = (td.pos[1:] - td.pos[:-1]) + p.free_length_m
        peak_x = float(np.max(np.abs(e) - p.coupler_gap_m))
    v_max = float(np.max(np.abs(td.vel)))
    if step % int(5 / dt) == 0:
        fmax = float(np.max(np.abs(td.coupler_interface_forces())))
        print(f"t={td.time:5.1f}s v0={td.vel[0]*3.6:5.2f} v末={td.vel[-1]*3.6:5.2f} "
              f"峰|f|={fmax/1e3:6.0f} kN")
    if v_max < 0.05 and not stopped:
        stopped = True
        print(f"--- 全列停于 t={td.time:.1f}s ---")
    if stopped and td.time > peak_t + 2.0 and step % int(1 / dt) == 0:
        # 停车后继续看 2s：若峰值在停车后 → 钳位/回弹伪影
        pass
    if v_max < 0.02 and td.time > 55:
        break
print(f"\n峰值 {peak/1e3:.0f} kN @ t={peak_t:.1f}s，"
      f"当时行程占用 {peak_x*1e3:.0f}mm，停车时刻 {'之后' if stopped and peak_t > 21 else '之前/中'}")
