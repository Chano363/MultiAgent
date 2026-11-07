# -*- coding: utf-8 -*-
"""Song2026 Tube-MPC 算法插件。

论文式(13)-(19)、(37)-(66)：4 状态增广误差模型 + 终端约束 + Tube 反馈。
本插件只做两件事：
  1. 用 Observation 组装误差状态 x0 = [s_e, v_e, s_e2, v_e2]；
  2. 调 tube_mpc.TubeMPC.solve() + Tube 反馈，输出归一化 û。
空气制动、列间包络、电-空仲裁全部由平台保护层负责，插件不参与。
"""
from __future__ import annotations

import numpy as np

import params as P
from dtwin.contracts import Action, Observation, RunConfig
from dtwin.registry import register_algorithm
from tube_mpc import TubeMPC


@register_algorithm("tube_mpc")
class TubeMPCPlugin:
    name = "tube_mpc"
    display_name = "Tube-MPC 协同控制"
    category = "模型预测控制"
    description = ("论文式(13)-(19)/(37)-(66)：4 状态增广误差模型 + 终端约束 + Tube 反馈，"
                   "输出归一化加速度指令，安全约束交由平台保护层。")
    params = {"kappa": 1.0, "H_pred": 5, "Q": "diag(0.5,0.5)", "P": "diag(0.6,0.4)", "R": 0.1}

    def __init__(self, kappa: float | None = None):
        self.kappa = P.KAPPA if kappa is None else kappa
        self.mpcs = []
        self.xbar = []

    def reset(self, config: RunConfig) -> None:
        self.mpcs = [TubeMPC(idx=i, m_wagon=P.M_WAGON_GROUP,
                             se_lim=P.F_COUPLE_LIM / P.GAMMA)
                     for i in range(config.n_trains)]
        self.xbar = [np.zeros(4) for _ in range(config.n_trains)]

    def act(self, obs: Observation) -> Action:
        # 位置误差项取零：列间间距由参考层 v_ref 律承担（避免代价项把车顶超速）
        x0 = np.array([0.0,
                       obs.v_ref - obs.v_head,
                       obs.intra_dev,
                       obs.v_head - obs.v_group[0]], dtype=float)
        # 与旧脚本同语义：每步把名义状态重置为量测值（z≡0），
        # 保留 Tube 反馈结构但在当前复现口径下不产生额外修正。
        self.xbar[obs.train_id] = x0
        u_star = self.mpcs[obs.train_id].solve(x0, obs.v_ref, obs.a_ref, obs.d2)
        z = x0 - self.xbar[obs.train_id]
        u_hat = u_star + self.kappa * (z[1] - z[3])
        return Action(u_hat=float(u_hat))
