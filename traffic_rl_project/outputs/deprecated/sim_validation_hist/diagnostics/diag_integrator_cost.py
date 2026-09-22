"""量化动力学算力开销：统计 Picard 迭代次数、测试精度/速度权衡。

对比维度：子步长（0.01/0.02）、max_iter（30/12）、tol（1e-5/1e-4）
指标：B基准（万吨全制动，文献634kN）峰值钩力 + 每步耗时。
"""
import sys
import time
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


def run(env_dt: float, substep: float, max_iter: int, tol: float,
        max_time=60.0):
    consist = make_B_consist()
    td = TrainDynamics(consist, coupler=CouplerParams(), dt=env_dt)
    td.newmark_max_iter = max_iter
    td.newmark_tol = tol
    td.brake_rise_time_by_notch[AirBrakeNotch.SERVICE] = 18.0
    td.set_grade(-0.006)
    td.set_initial_speed(60.0 / 3.6)
    n = consist.num_vehicles

    # 统计迭代次数
    orig = td._step_newmark
    iters = []

    def counted(cf, dt, **kw):
        before = kw.get('max_iter') or td.newmark_max_iter
        # 用包装统计：直接调用原始，记录不使用（改为近似：按耗时比例估计）
        return orig(cf, dt, **kw)

    n_sub = max(1, int(np.ceil(td.dt / substep)))
    h = td.dt / n_sub
    peak = 0.0
    t0 = time.time()
    steps = 0
    while td.time < max_time and np.max(np.abs(td.vel)) > 0.02:
        for _ in range(n_sub):
            td._advance_control_once(
                np.zeros(n), np.zeros(n), AirBrakeNotch.SERVICE, 0, None,
                False, False, h, apply_command=(steps == 0))
        f = td.coupler_interface_forces()
        peak = max(peak, float(np.max(np.abs(f))))
        steps += 1
    el = time.time() - t0
    return peak / 1e3, el / max(steps, 1) * 1000.0, steps


if __name__ == '__main__':
    print("B基准：-6‰ 万吨 SERVICE 至停车（文献 634 kN）")
    print(f"{'配置':<42}{'峰值kN':>8}{'ms/控制步':>12}")
    configs = [
        ("子步0.01 / iter30 / tol1e-5（当前）", 0.1, 0.01, 30, 1e-5),
        ("子步0.02 / iter30 / tol1e-5", 0.1, 0.02, 30, 1e-5),
        ("子步0.015 / iter30 / tol1e-5", 0.1, 0.015, 30, 1e-5),
        ("子步0.01 / iter20 / tol1e-5", 0.1, 0.01, 20, 1e-5),
        ("子步0.01 / iter30 / tol1e-4", 0.1, 0.01, 30, 1e-4),
    ]
    for label, edt, sub, mi, tol in configs:
        try:
            p, ms, st = run(edt, sub, mi, tol)
            flag = '' if np.isfinite(p) else ' (发散)'
            print(f"{label:<42}{p:>8.0f}{ms:>12.1f}{flag}")
        except Exception as e:
            print(f"{label:<42} 异常: {type(e).__name__}")
