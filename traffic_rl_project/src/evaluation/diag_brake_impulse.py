"""【诊断】制动冲击物理：固定制动场景下扫描阻尼/刚度，隔离车钩力峰值偏高的原因。

背景：无安全层循环制动验证发现车钩力打满缓冲器饱和值 2270 kN，
而实测正常循环制动 ~1000 kN。本脚本做受控实验：
- 平直轨道（grade=0），消除坡度影响
- 初始 20 m/s，施加 full service brake（-0.75），跑 60s
- 扫描阻尼 c 与刚度 k，记录峰值车钩力、是否振荡

用法：python src/evaluation/diag_brake_impulse.py
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


def run_brake(stiffness, damping, max_impulse, n_steps=600, speed=20.0,
              ab=AirBrakeNotch.SERVICE):
    """平直轨道强制动，返回峰值车钩力（饱和后）与未饱和峰值、最终速度。"""
    consist = make_10kt()
    td = TrainDynamics(
        consist,
        coupler=CouplerParams(stiffness=stiffness, damping=damping,
                              max_impulse_n=max_impulse),
        dt=0.1,
    )
    td.set_initial_speed(speed)
    n = consist.num_vehicles
    peak = 0.0
    peak_unsat = 0.0
    for _ in range(n_steps):
        td.step_vehicles_ed_ab(
            throttle=np.zeros(n),
            ed_throttle=np.zeros(n),
            ab_command=ab,
        )
        # 读动力学实际车钩力（含饱和）
        peak = max(peak, float(np.max(np.abs(td._coupler_forces()))))
    return peak, float(np.max(np.abs(td.vel)))


def main():
    print("=" * 78)
    print("诊断：平直轨道强制动（service brake, 20 m/s, 60s），扫描阻尼/刚度")
    print("=" * 78)

    # 固定刚度 5e6，扫描阻尼
    print("\n[1] 扫描阻尼（k=5e6, 饱和 2270kN）:")
    print(f"  {'c (N·s/m)':<12} {'峰值(kN)':<12} {'是否达饱和':<10}")
    for c in [5.0e4, 2.0e5, 5.0e5, 1.0e6, 2.0e6]:
        peak, v = run_brake(5.0e6, c, 2.27e6)
        print(f"  {c:<12.0e} {peak/1e3:<12.1f} {'✅' if peak < 2.27e6-1 else '⚠️饱和'}")

    # 固定阻尼 5e5，扫描刚度
    print("\n[2] 扫描刚度（c=5e5, 饱和 2270kN）:")
    print(f"  {'k (N/m)':<12} {'峰值(kN)':<12} {'是否达饱和':<10}")
    for k in [1.0e6, 5.0e6, 1.0e7, 2.0e7]:
        peak, v = run_brake(k, 5.0e5, 2.27e6)
        print(f"  {k:<12.0e} {peak/1e3:<12.1f} {'✅' if peak < 2.27e6-1 else '⚠️饱和'}")

    # 关键：无饱和时真实冲击峰值（判断阻尼够不够）
    print("\n[3] 无饱和时峰值（k=5e6, 看阻尼能否压住振荡）:")
    print(f"  {'c (N·s/m)':<12} {'无饱和峰值(kN)':<16}")
    for c in [5.0e4, 2.0e5, 5.0e5, 1.0e6, 2.0e6]:
        peak, v = run_brake(5.0e6, c, 0.0)
        print(f"  {c:<12.0e} {peak/1e3:<16.1f}")


if __name__ == '__main__':
    main()
