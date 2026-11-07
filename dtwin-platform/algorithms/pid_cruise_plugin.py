# -*- coding: utf-8 -*-
"""PID 巡航算法插件（对照实验用）。

朴素速度环 PID：只跟踪参考速度 v_ref，不使用车钩/间距前馈项，
用于展示"平台更换算法不改动物理层与保护层"的对照效果。
"""
from __future__ import annotations

from dtwin.contracts import Action, Observation, RunConfig
from dtwin.registry import register_algorithm


@register_algorithm("pid_cruise")
class PIDCruisePlugin:
    name = "pid_cruise"
    display_name = "PID 速度巡航"
    category = "经典控制"
    description = ("单回路速度 PID：误差 e = v_ref - v，比例+积分+速度前馈，"
                   "不含车钩力前馈与间距协同项，作为基线对照。")
    params = {"kp": 0.22, "ki": 0.05, "i_max": 0.6, "a_feedforward": 1.0}

    def __init__(self, kp: float = 0.22, ki: float = 0.05, i_max: float = 0.6,
                 a_feedforward: float = 1.0):
        self.kp, self.ki, self.i_max = kp, ki, i_max
        self.a_ff = a_feedforward
        self._int = []

    def reset(self, config: RunConfig) -> None:
        self._int = [0.0] * config.n_trains

    def act(self, obs: Observation) -> Action:
        i = obs.train_id
        err = obs.v_ref - obs.v_head
        self._int[i] = max(-self.i_max, min(self.i_max, self._int[i] + self.ki * err))
        u = self.kp * err + self._int[i] + self.a_ff * obs.a_ref
        return Action(u_hat=float(max(-0.12, min(0.12, u))))
