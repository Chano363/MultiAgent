# -*- coding: utf-8 -*-
"""参考层：目标速度曲线 + 跟随车参考律 + 列间安全包络 + 量测派生量。

从 shuohuang_sim.py 原样移植（含两处论文扩展项）：
  - v_t(s)：真实限速 -> 反向制动(a_dec) / 正向牵引(a_acc) 双向扫描；
  - 跟随车：v_ref = min(v_t(s_self), v_lead + clip((gap-D_des)/T_adj, ±v_adj))；
  - 列间包络：v_allow = sqrt(v_lead² + 2 a_eb max(净空 - D_min, 0))。
"""
from __future__ import annotations

from typing import Callable, List, Sequence, Tuple

import numpy as np

from .contracts import Reference, RunConfig, TrainState


class ReferenceGenerator:
    def __init__(self, cfg: RunConfig, speed_limit_fn: Callable[[float], float],
                 train_length_m: float):
        ref = cfg.reference
        self.cfg = cfg
        self.dt = cfg.dt_mpc
        self.d_des = float(ref["d_des"])
        self.ds = float(ref["ds_tbl"])
        self.a_dec = float(ref["a_dec"])
        self.a_acc = float(ref["a_acc"])
        self.v_cap = float(ref.get("v_cap_kmh", 80.0)) / 3.6
        self.t_adj = float(ref["t_adj"])
        self.v_adj = float(ref["v_adj"])
        prot = cfg.protection.get("speed_envelope", {})
        self.a_eb = float(prot.get("a_eb", 0.15))
        self.d_min = float(prot.get("d_min", 150.0))
        self.l_train = train_length_m
        self.v_t = self._target_curve(speed_limit_fn)
        self._prev_v_head: List[float] = []
        self._prev_v_ga: List[float] = []
        self._intra0: List[float] = []

    # ------------------------------------------------------------------
    # 目标速度曲线
    # ------------------------------------------------------------------
    def _target_curve(self, limit_at: Callable[[float], float]) -> np.ndarray:
        n_s = int(self.cfg.line_length / self.ds) + 2
        v = np.array([min(limit_at(i * self.ds), self.v_cap * 3.6) / 3.6
                      for i in range(n_s)])
        # 限速阶跃下降 -> 按服务减速度提前减速
        for i in range(n_s - 2, -1, -1):
            v[i] = min(v[i], np.sqrt(v[i + 1] ** 2 + 2.0 * self.a_dec * self.ds))
        # 限速阶跃上升 -> 按牵引能力限制参考加速度
        for i in range(1, n_s):
            v[i] = min(v[i], np.sqrt(v[i - 1] ** 2 + 2.0 * self.a_acc * self.ds))
        return v

    def initial_speed(self) -> float:
        j = int(np.clip(self.cfg.s_start / self.ds, 0, len(self.v_t) - 1))
        return float(self.v_t[j])

    def reset(self, states: Sequence[TrainState]) -> None:
        self._prev_v_head = [s.v_head for s in states]
        self._prev_v_ga = [s.v_group[0] for s in states]
        self._intra0 = [s.s_head - s.s_group[0] for s in states]

    # ------------------------------------------------------------------
    # 每步参考
    # ------------------------------------------------------------------
    def compute(self, states: Sequence[TrainState]) -> List[Reference]:
        n = len(self.v_t)
        out: List[Reference] = []
        for i, st in enumerate(states):
            intra_dev = (st.s_head - st.s_group[0]) - self._intra0[i]
            d2 = (self._prev_v_ga[i] - st.v_group[0]) / self.dt
            if i == 0:
                j_now = int(np.clip(st.s_head / self.ds, 0, n - 1))
                j_nxt = int(np.clip((st.s_head + st.v_head * self.dt) / self.ds,
                                    0, n - 1))
                v_ref = float(self.v_t[j_now])
                v_sup = v_ref                      # 监督目标 = 本车位置目标速度
                a_ref = float((self.v_t[j_nxt] - self.v_t[j_now]) / self.dt)
                v_allow = float("inf")
            else:
                j_self = int(np.clip(st.s_head / self.ds, 0, n - 1))
                v_lead = max(float(states[i - 1].v_head), 0.0)
                corr = float(np.clip((st.gap_lead - self.d_des) / self.t_adj,
                                     -self.v_adj, self.v_adj))
                v_ref = min(float(self.v_t[j_self]), v_lead + corr)
                v_sup = float(self.v_t[j_self])
                a_ref = float((v_lead - self._prev_v_head[i - 1]) / self.dt)
                v_allow = self._safety_envelope(st, states[i - 1], v_lead)
                if v_ref > v_allow:
                    v_ref = v_allow
            out.append(Reference(v_ref=v_ref, a_ref=a_ref, v_sup=v_sup,
                                 v_allow=v_allow, intra_dev=intra_dev, d2=d2))

        self._prev_v_head = [s.v_head for s in states]
        self._prev_v_ga = [s.v_group[0] for s in states]
        return out

    def _safety_envelope(self, self_state: TrainState, lead: TrainState,
                         v_lead: float) -> float:
        clearance = lead.s_head - self.l_train - self_state.s_head
        room = max(clearance - self.d_min, 0.0)
        return float(np.sqrt(v_lead * v_lead + 2.0 * self.a_eb * room))
