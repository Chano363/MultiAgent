# -*- coding: utf-8 -*-
"""保护层：算法输出之后的二次钳制（与具体算法无关，换算法不丢安全约束）。

三层串联，顺序与旧脚本 shuohuang_sim.py 的执行顺序一致：
  1. SpeedEnvelopeGuard  —— 列间安全包络：超过 v_allow 时禁止加速（û ≤ 0）；
  2. BrakeSupervisor     —— 空气制动监督：ATP 硬限速（比例减压）或文献[22]
                            循环制动（50 kPa 二进制 + 最短充风时间 T_AI）；
  3. ElectricAirArbitration —— 电-空分工仲裁：空气制动已施加且车速接近参考时
                            限制电制动输出率，避免叠加造成近停车。
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Mapping, Sequence

from .contracts import Action, Observation, Protection, RunConfig


class SpeedEnvelopeGuard:
    """列间安全包络（ETCS 式）：v > v_allow 时钳制 û ≤ 0。

    包络本身在参考层按前车尾端与保守减速度反推（数学上排除穿越）。
    """

    def reset(self) -> None:
        pass

    def apply(self, obs: Observation, action: Action) -> Action:
        if obs.v_head > obs.v_allow:
            action.u_hat = min(action.u_hat, 0.0)
        return action


@dataclass
class _BrakeState:
    applied: bool = False
    t_rel: float = -1e9


class _BrakeSupervisor:
    """共同状态机骨架：强制缓解速度 + 充风时间锁。"""

    def __init__(self, t_ai: float, v_release_min: float):
        self.t_ai = t_ai
        self.v_release_min = v_release_min
        self._states: Dict[int, _BrakeState] = {}

    def reset(self) -> None:
        self._states.clear()

    def _state(self, train_id: int) -> _BrakeState:
        st = self._states.get(train_id)
        if st is None:
            st = _BrakeState()
            self._states[train_id] = st
        return st

    def apply(self, obs: Observation, action: Action) -> Action:
        action.brake_apply, action.brake_kpa = self._decide(obs)
        return action

    def _decide(self, obs: Observation) -> tuple:
        raise NotImplementedError


class ATPSupervisor(_BrakeSupervisor):
    """ATP 硬限速：监督速度 = 本车位置线路原始限速 v_sup。

    超速 ≥ 1 km/h 触发常用制动，减压量随超速线性增加（50~170 kPa）；
    低于 v_sup - 0.5 m/s 缓解；缓解后须经 T_AI 才能重施。
    """

    def __init__(self, dv_on: float, dv_off: float, b_base: float, b_gain: float,
                 b_max: float, t_ai: float, v_release_min: float):
        super().__init__(t_ai, v_release_min)
        self.dv_on, self.dv_off = dv_on, dv_off
        self.b_base, self.b_gain, self.b_max = b_base, b_gain, b_max

    def _decide(self, obs: Observation) -> tuple:
        st = self._state(obs.train_id)
        v = obs.v_head
        if v <= self.v_release_min:                 # 式(2-26) 最低缓解速度
            if st.applied:
                st.applied, st.t_rel = False, obs.t
            return False, 0.0
        dv = v - obs.v_sup
        if st.applied:
            if dv <= -self.dv_off:
                st.applied, st.t_rel = False, obs.t
        else:
            if dv >= self.dv_on and (obs.t - st.t_rel) >= self.t_ai:
                st.applied = True
        if not st.applied:
            return False, 0.0
        b = self.b_base + self.b_gain * (dv - self.dv_on)
        return True, float(min(max(b, self.b_base), self.b_max))


class CyclicBrakeSupervisor(_BrakeSupervisor):
    """文献[22] 循环制动：以 v_ref 为中心、固定减压量的二进制施加/缓解。"""

    def __init__(self, reduction_kpa: float, dv_apply: float, dv_release: float,
                 t_ai: float, v_release_min: float):
        super().__init__(t_ai, v_release_min)
        self.reduction_kpa = reduction_kpa
        self.dv_apply, self.dv_release = dv_apply, dv_release

    def _decide(self, obs: Observation) -> tuple:
        st = self._state(obs.train_id)
        v = obs.v_head
        if v <= self.v_release_min:
            if st.applied:
                st.applied, st.t_rel = False, obs.t
            return False, 0.0
        if st.applied:
            if v <= obs.v_ref - self.dv_release:
                st.applied, st.t_rel = False, obs.t
        else:
            if v >= obs.v_ref + self.dv_apply and (obs.t - st.t_rel) >= self.t_ai:
                st.applied = True
        return (True, self.reduction_kpa) if st.applied else (False, 0.0)


class ElectricAirArbitration:
    """电-空分工：空气制动已施加且车速已接近参考速度时压低电制动输出率。"""

    def __init__(self, ed_max: float, ed_air_cap: float, margin: float):
        self.ed_max = ed_max
        self.ed_air_cap = ed_air_cap
        self.margin = margin

    def reset(self) -> None:
        pass

    def apply(self, obs: Observation, action: Action) -> Action:
        if action.brake_apply and obs.v_head < obs.v_ref + self.margin:
            action.ed_cap = self.ed_air_cap
        else:
            action.ed_cap = self.ed_max
        return action


def build_protections(cfg: RunConfig) -> List[Protection]:
    prot: Mapping[str, Any] = cfg.protection
    v_release_min = float(prot.get("v_release_min_kmh", 30.0)) / 3.6
    t_ai = float(prot["t_ai"])
    mode = prot.get("brake_supervisor", "atp")
    if mode == "atp":
        atp = prot["atp"]
        brake: Protection = ATPSupervisor(
            dv_on=float(atp["dv_on_kmh"]) / 3.6,
            dv_off=float(atp["dv_off_mps"]),
            b_base=float(atp["b_base_kpa"]),
            b_gain=float(atp["b_gain_kpa"]),
            b_max=float(atp["b_max_kpa"]),
            t_ai=t_ai,
            v_release_min=v_release_min,
        )
    elif mode == "cyclic":
        cyc = prot["cyclic"]
        brake = CyclicBrakeSupervisor(
            reduction_kpa=float(cyc["reduction_kpa"]),
            dv_apply=float(cyc["dv_apply"]),
            dv_release=float(cyc["dv_release"]),
            t_ai=t_ai,
            v_release_min=v_release_min,
        )
    else:
        raise ValueError(f"未知的 brake_supervisor: {mode}")
    return [
        SpeedEnvelopeGuard(),
        brake,
        ElectricAirArbitration(
            ed_max=float(prot.get("ed_max", 0.8)),
            ed_air_cap=float(prot.get("ed_air_cap", 0.2)),
            margin=float(prot.get("dv_air_cap_margin", 0.3)),
        ),
    ]
