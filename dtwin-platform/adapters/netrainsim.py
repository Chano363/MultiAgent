# -*- coding: utf-8 -*-
"""NeTrainSim 物理适配器：把第三方 TrainDynamics 包装成 PlantAdapter。

硬约束：物理层不改一行。本文件只做
  1. 构造/重置被控对象（3 列单元列车，各自独立 TrainDynamics）；
  2. 把内部状态翻译成平台 TrainState；
  3. 把保护层给出的 Action（归一化 û + 空气制动指令）反解成机车手柄并 ZOH 推进。
"""
from __future__ import annotations

from typing import List, Sequence

import numpy as np

import params as P
from dtwin.contracts import ActuatorReport, Action, PlantAdapter, RunConfig, TrainState
from dtwin.registry import register_plant

from src.train_dynamics.train import TrainDynamics                       # noqa: E402
from src.train_dynamics.params import (TrainConsist, LocomotiveParams,   # noqa: E402
                                       VehicleParams, CouplerParams)
from src.train_dynamics.grade_profile import PROFILES                   # noqa: E402
from src.train_dynamics.braking import (AirBrakeNotch,                   # noqa: E402
                                        electric_brake_force_n)
from src.train_dynamics.tractive import tractive_force                   # noqa: E402

from .couplers import make_couplers                                      # noqa: E402

N_WAGON = 54
GA = (1, 27)      # 货车组1 = 第 1..27 辆
GB = (28, 54)     # 货车组2 = 第 28..54 辆
V_STATIC = 0.5    # m/s 极低速阈值：车钩力由静态摩擦锁定，不纳入前馈


def make_consist() -> TrainConsist:
    """HXD1（8 轴 200 t）+ 54×C80（100 t、12.1 m）≈ 5600 t。"""
    loco = LocomotiveParams(
        mass_t=200.0, no_of_axles=8, frontal_area_m2=11.5, drag_coef=1.4,
        length_m=35.3, max_power_kw=9600.0, transmission_efficiency=0.85,
        max_speed_mps=33.3, n_notches=8,
    )
    car = VehicleParams(mass_t=100.0, no_of_axles=4, frontal_area_m2=10.0,
                        drag_coef=1.0, length_m=12.1)
    return TrainConsist([loco] + [car] * N_WAGON)


def make_train(coupler_model: str, head_pos: float, v_init: float, profile,
               dt_dyn: float) -> TrainDynamics:
    dyn = TrainDynamics(make_consist(), dt=dt_dyn, simcase="official")
    couplers = make_couplers(coupler_model, dyn.num_vehicles - 1)
    if couplers is not None:
        dyn.set_couplers(couplers)
    dyn.set_grade_profile(profile)
    fl = float(CouplerParams().free_length_m)
    pos = head_pos - np.arange(dyn.num_vehicles) * fl
    dyn.set_initial(pos=pos, vel=np.full(dyn.num_vehicles, float(v_init)))
    return dyn


def _grp_mean(dyn: TrainDynamics, a: int, b: int, field: str = "vel") -> float:
    return float(np.mean(getattr(dyn, field)[a:b + 1]))


def force_to_handle(dyn: TrainDynamics, u_hat: float, ed_cap: float):
    """式11/13 前馈 + û·m_loco -> 机车牵引/电制动手柄（力按功率限幅反解）。"""
    v_abs = abs(dyn.vel[0])
    cpl = 0.0 if v_abs < V_STATIC else dyn._coupler_forces()[0]
    f_non = (dyn._air_braking_forces()[0] - dyn._resistance_forces()[0]
             + dyn._grade_forces()[0] + cpl)
    u_n = u_hat * P.M_LOCO * 1000.0 - f_non
    v = max(v_abs, 0.5)
    loco = dyn.consist.vehicles[0]
    if u_n >= 0.0:
        f_max = tractive_force(loco.max_power_kw, loco.transmission_efficiency,
                               1.0, v, loco.mass_t)
        return float(np.clip(u_n / max(f_max, 1.0), 0.0, 1.0)), 0.0
    f_ed = electric_brake_force_n(loco.mass_t, v, 1.0, loco.max_power_kw,
                                 loco.transmission_efficiency)
    return 0.0, float(np.clip(-u_n / max(f_ed, 1.0), 0.0, ed_cap))


@register_plant("netrainsim")
class NeTrainSimPlant(PlantAdapter):
    def __init__(self, cfg: RunConfig):
        self.cfg = cfg
        self.dyns: List[TrainDynamics] = []
        self._profile = None

    # ------------------------------------------------------------------
    def reset(self, v_init: float) -> Sequence[TrainState]:
        self._profile = PROFILES[self.cfg.line]()
        self.dyns = [
            make_train(self.cfg.coupler_model,
                       self.cfg.s_start - self.cfg.train_head_gap * i,
                       v_init, self._profile, self.cfg.dt_dyn)
            for i in range(self.cfg.n_trains)
        ]
        return self.observe()

    def observe(self) -> Sequence[TrainState]:
        out: List[TrainState] = []
        for i, dyn in enumerate(self.dyns):
            lead = self.dyns[i - 1] if i > 0 else None
            out.append(TrainState(
                train_id=i,
                s_head=float(dyn.pos[0]),
                v_head=float(dyn.vel[0]),
                v_group=(_grp_mean(dyn, *GA), _grp_mean(dyn, *GB)),
                s_group=(_grp_mean(dyn, *GA, "pos"), _grp_mean(dyn, *GB, "pos")),
                gap_lead=(float(lead.pos[0] - dyn.pos[0]) if lead else float("inf")),
                v_lead=(float(lead.vel[0]) if lead else float("inf")),
            ))
        return out

    def step(self, commands: Sequence[Action],
             sub_steps: int) -> Sequence[ActuatorReport]:
        reports: List[ActuatorReport] = []
        held = []
        for dyn, cmd in zip(self.dyns, commands):
            thr, ed = force_to_handle(dyn, cmd.u_hat, cmd.ed_cap)
            held.append((dyn, thr, ed, cmd.brake_apply, cmd.brake_kpa))
            reports.append(ActuatorReport(throttle=thr, ed=ed))
        for _ in range(sub_steps):
            for dyn, thr, ed, b_app, b in held:
                thr_arr = np.zeros(dyn.num_vehicles)
                ed_arr = np.zeros(dyn.num_vehicles)
                thr_arr[0], ed_arr[0] = thr, ed
                if b_app:
                    dyn.step_vehicles_ed_ab(thr_arr, ed_arr, AirBrakeNotch.SERVICE,
                                            brake_origin=1, reduction_kpa=b)
                else:
                    dyn.step_vehicles_ed_ab(thr_arr, ed_arr, AirBrakeNotch.RELEASE,
                                            brake_origin=1)
        return reports

    # ------------------------------------------------------------------
    def coupler_peak_forces(self) -> Sequence[float]:
        out = []
        for dyn in self.dyns:
            fc = np.abs(dyn.coupler_interface_forces())
            out.append(float(fc.max()) / 1e3 if fc.size else 0.0)
        return out

    def energy_kwh(self) -> Sequence[float]:
        return [float(d.energy_kwh) for d in self.dyns]

    @property
    def train_length(self) -> float:
        """由编组常量直接给出（构造前即可用，参考层初始化需要它）。"""
        return N_WAGON * float(CouplerParams().free_length_m) + 12.1
