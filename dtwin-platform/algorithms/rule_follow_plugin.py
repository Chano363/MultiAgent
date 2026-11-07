# -*- coding: utf-8 -*-
"""规则型跟随算法插件（对照实验用）。

"速度阈值 + 间距规则"：高于参考速度即电制动，低于即牵引，
间距偏差按比例叠加到参考速度上。无优化求解、无模型，属规则基线。
"""
from __future__ import annotations

from dtwin.contracts import Action, Observation, RunConfig
from dtwin.registry import register_algorithm


@register_algorithm("rule_follow")
class RuleFollowPlugin:
    name = "rule_follow"
    display_name = "规则跟随控制"
    category = "规则基线"
    description = ("参考速度 + 间距偏差比例修正，按速度死区切换牵引/电制动，"
                   "不求解优化问题，用于验证平台算法可插拔性与基线对比。")
    params = {"deadband_mps": 0.3, "k_gap": 0.004, "gain_traction": 0.9,
              "gain_brake": 0.9, "u_cap": 0.1}

    def __init__(self, deadband_mps: float = 0.3, k_gap: float = 0.004,
                 gain_traction: float = 0.9, gain_brake: float = 0.9,
                 u_cap: float = 0.1):
        self.deadband = deadband_mps
        self.k_gap = k_gap
        self.gain_traction = gain_traction
        self.gain_brake = gain_brake
        self.u_cap = u_cap
        self.d_des = 2000.0

    def reset(self, config: RunConfig) -> None:
        self.d_des = config.d_des

    def act(self, obs: Observation) -> Action:
        v_tgt = obs.v_ref
        if not obs.is_leader:
            v_tgt += self.k_gap * (obs.gap_lead - self.d_des)
        err = v_tgt - obs.v_head
        if err > self.deadband:
            u = self.gain_traction * min(err, 1.0)
        elif err < -self.deadband:
            u = -self.gain_brake * min(-err, 1.0)
        else:
            u = 0.0
        return Action(u_hat=float(max(-self.u_cap, min(self.u_cap, u))))
