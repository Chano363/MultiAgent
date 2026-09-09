"""【诊断】受控对比：同一强制动工况下 dt=0.1/0.05/0.02 的数值差异。

背景：dt=0.1 下坡循环制动掉速到 2-3 km/h，dt=0.05 下健康（73 km/h）。
怀疑 dt=0.1 半隐式 Euler 对刚性弹簧+大编组数值失真。
本脚本：固定 -10.9‰ 下坡，初始 65 km/h，service brake(-0.75)，跑 60s，
对比不同 dt 的峰值车钩力、末速度、缓解后冲击。

用法：python src/evaluation/diag_dt_controlled.py
"""

import sys
from pathlib import Path

sys.path.append(str(Path(__file__).parent.parent.parent))

import numpy as np

from src.train_dynamics.params import VehicleParams, LocomotiveParams, TrainConsist, CouplerParams
from src.train_dynamics.train import TrainDynamics
from src.train_dynamics.braking import AirBrakeNotch


def make_10kt():
    loco = LocomotiveParams(
        mass_t=188.0, no_of_axles=6, frontal_area_m2=11.5, drag_coef=1.4,
        length_m=21.0, max_power_kw=9600.0, transmission_efficiency=0.85,
        max_speed_mps=30.0, n_notches=8,
    )
    car = VehicleParams(
        mass_t=100.0, no_of_axles=4, frontal_area_m2=10.0, drag_coef=1.0,
        length_m=12.0,
    )
    return TrainConsist([loco] + [car for _ in range(100)])


def run(dt, t_end=60.0, grade=-0.0109, ab=AirBrakeNotch.SERVICE,
        damping=5.0e4, stiffness=5.0e6):
    n_steps = int(t_end / dt)
    consist = make_10kt()
    td = TrainDynamics(
        consist,
        coupler=CouplerParams(stiffness=stiffness, damping=damping, max_impulse_n=0.0),
        dt=dt,
    )
    td.set_grade(grade)
    td.set_initial_speed(65.0 / 3.6)
    n = consist.num_vehicles
    peak = 0.0
    v_tail_log = []
    for _ in range(n_steps):
        td.step_vehicles_ed_ab(
            throttle=np.zeros(n),
            ed_throttle=np.zeros(n),
            ab_command=ab,
        )
        peak = max(peak, float(np.max(np.abs(td._coupler_forces()))))
        v_tail_log.append(td.vel[-1])
    return {
        'peak_kN': peak / 1e3,
        'v0_final': td.vel[0] * 3.6,
        'v_tail_final': td.vel[-1] * 3.6,
        'v_tail_min': np.min(v_tail_log) * 3.6,
    }


def main():
    print("=" * 78)
    print("受控对比：-10.9‰ 下坡 + service brake(65km/h 起, 60s)")
    print("=" * 78)
    print(f"  {'dt':<6} {'峰值(kN)':<10} {'机车末速':<10} {'尾部末速':<10} {'尾部最低':<10}")
    for dt in [0.1, 0.05, 0.02]:
        try:
            r = run(dt)
            print(f"  {dt:<6} {r['peak_kN']:<10.1f} {r['v0_final']:<10.1f} "
                  f"{r['v_tail_final']:<10.1f} {r['v_tail_min']:<10.1f}")
        except Exception as e:
            print(f"  {dt:<6} 异常: {type(e).__name__}")

    # 阻尼影响（dt=0.05 固定）
    print("\n[dt=0.05] 扫描阻尼:")
    print(f"  {'c':<12} {'峰值(kN)':<10} {'机车末速':<10}")
    for c in [5.0e4, 2.0e5, 5.0e5, 1.0e6]:
        try:
            r = run(0.05, damping=c)
            print(f"  {c:<12.0e} {r['peak_kN']:<10.1f} {r['v0_final']:<10.1f}")
        except Exception as e:
            print(f"  {c:<12.0e} 异常: {type(e).__name__}")


if __name__ == '__main__':
    main()
