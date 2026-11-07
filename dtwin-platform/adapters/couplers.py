# -*- coding: utf-8 -*-
"""车钩模型工厂：物理层三种假设（物理参数，不涉及控制器）。

  mt2    仿真器默认 MT-2 迟滞车钩（刚度 2e7 N/m + 预压 + 库仑/静态摩擦 + 限位）
  linear 纯线性弹簧 γ=500 kN/m（论文式10 的被控对象假设）
  zero   全部阻抗置零（物理层消融，用于验证"车钩力是否必要"）
"""
from __future__ import annotations

from src.train_dynamics.params import CouplerParams

GAMMA_NPM = 500_000.0   # N/m  论文反解 γ=500 kN/m


def zero_coupler() -> CouplerParams:
    return CouplerParams(stiffness=0.0, preload_n=0.0, friction_n=0.0,
                         friction_static_n=0.0, friction_v_er=0.0,
                         max_impulse_n=0.0, stroke_m=1e9, rigid_stiffness_nm=0.0)


def linear_spring_coupler(gamma_npm: float = GAMMA_NPM) -> CouplerParams:
    """F = γ · Δs：无预压、无摩擦、无迟滞软化、无行程限位、无游隙。"""
    return CouplerParams(
        stiffness=gamma_npm,
        preload_n=0.0,
        friction_n=0.0,
        friction_static_n=0.0,
        friction_v_er=0.0,
        max_impulse_n=1e12,
        stroke_m=1e9,
        rigid_stiffness_nm=0.0,
        coupler_gap_m=1e-9,
        unload_stiffness_ratio=1.0,
    )


def make_couplers(model: str, n: int) -> list | None:
    """返回 n 个车钩参数；'mt2' 返回 None 表示沿用仿真器默认齐次 MT-2。"""
    if model == "mt2":
        return None
    if model == "linear":
        return [linear_spring_coupler() for _ in range(n)]
    if model == "zero":
        return [zero_coupler() for _ in range(n)]
    raise ValueError(f"未知车钩模型: {model}")
