"""COVER 协方差地板强制重加权（Lu & Jiang 2026, arXiv:2602.06869）。

【文献锚】局部协方差律：某目标的 reward 与其 clipped advantage weight 的协方差符号
决定该目标在一阶意义上是改善还是退化；COVER（COVariance-floor Enforced Reweighting）
是一个**单边**控制器——仅当该协方差低于目标下界时抬高其权重，否则不动。
原文：``raises an objective's weight only when the covariance between its reward and the
clipped advantage weight falls below a target``。

【本仓适配】本仓 reward 是单个标量，11 个 reward term 是该标量的分解项；其中 8 个是
负罚项（常态 0、触发为负），对负罚项“提权”= 罚得更狠，与 COVER“提升被压制正目标”
的语义相反。按 owner 2026-11-18 拍板：**只对 3 个正项（speed_band / rel_anchor /
gap_eff，恰为本次退化项）做 COVER 提权，负罚项权重保持不变**。

【确定性】本模块为纯函数 + 状态类，只做 float 运算，不引入 RNG，不改变 GAE / log_prob
计算顺序。开关关闭时调用方完全不调用本模块 ⇒ 零回归。

【范围】学习 IMPLEMENTATION_LOCKED 语义：仅对正项单边提权，带上下 clip，权重乘子
供调用方回灌 env 的可变权重属性；物理模型 / 判据 / 安全层均不触碰。
"""
from __future__ import annotations

from typing import Dict, Iterable, Mapping, Sequence

import numpy as np

# owner 拍板：只有这 3 个正项参与 COVER 提权（本次退化的同源项）。
# 负罚项（speed_over / gap_danger / coupler_peak / coupler_over / pressure_gradient /
# notch_smooth / ab_cost / ed_cost）权重恒定，不进控制器。
COVER_POSITIVE_TERMS: tuple[str, ...] = ("speed_band", "rel_anchor", "gap_eff")


class CoverController:
    """COVER 单边重加权控制器。

    参数
    ----
    target_cov : float
        协方差地板。当 cov(term_k, clipped_adv) < target_cov 时提权。原文用目标下界；
        默认 0.0（协方差转负 = 该项正在被牺牲 ⇒ 提权）。
    up_factor : float
        每次触发的乘性增幅（>1）。单边：w <- w * up_factor。
    weight_min / weight_max : float
        权重乘子的硬边界，防逐集累乘漂移/爆炸。默认 [1.0, 4.0]（只增不减，最多 4×）。
    terms : tuple
        参与控制的项（默认 owner 锁定的 3 个正项）。
    """

    def __init__(
        self,
        target_cov: float = 0.0,
        up_factor: float = 1.05,
        weight_min: float = 1.0,
        weight_max: float = 4.0,
        terms: Sequence[str] = COVER_POSITIVE_TERMS,
    ):
        if up_factor <= 1.0:
            raise ValueError("up_factor must be > 1.0 for one-sided upweighting")
        if weight_min < 1.0 or weight_max <= weight_min:
            raise ValueError("require 1.0 <= weight_min < weight_max")
        self.target_cov = float(target_cov)
        self.up_factor = float(up_factor)
        self.weight_min = float(weight_min)
        self.weight_max = float(weight_max)
        self.terms = tuple(terms)
        # 权重乘子 w_k，初值 1.0（= 不改变原权重）。
        self.multipliers: Dict[str, float] = {k: 1.0 for k in self.terms}
        # 上一集诊断：cov 值，供日志/快评观察，不参与控制。
        self.last_cov: Dict[str, float] = {k: 0.0 for k in self.terms}
        self.update_count = 0

    @staticmethod
    def covariance(x: Iterable[float], y: Iterable[float]) -> float:
        """总体协方差 E[(x-Ex)(y-Ey)]；样本 <2 或零方差返回 0.0（不触发提权）。"""
        xa = np.asarray(list(x), dtype=np.float64)
        ya = np.asarray(list(y), dtype=np.float64)
        if xa.shape != ya.shape or xa.size < 2:
            return 0.0
        xc = xa - xa.mean()
        yc = ya - ya.mean()
        denom = xa.size  # 总体协方差；符号与样本协方差一致，仅尺度不同
        return float(np.dot(xc, yc) / denom)

    def observe(
        self,
        term_values: Mapping[str, Sequence[float]],
        clipped_adv_weight: Sequence[float],
    ) -> Dict[str, float]:
        """按一批 (per-step 分项值, clipped advantage weight) 更新权重乘子。

        term_values : {term_k: [v_0, ..., v_{T-1}]} —— per decision 步的分项 reward。
        clipped_adv_weight : [min(ratio,1+eps)*adv, ...]（COVER 原文锚的量，长度 T）。

        returns : 本轮各正项的权重乘子（含未触发项），供调用方回灌 env。
        """
        adv = np.asarray(list(clipped_adv_weight), dtype=np.float64)
        for k in self.terms:
            vals = term_values.get(k)
            if vals is None:
                continue
            cov = self.covariance(vals, adv)
            self.last_cov[k] = cov
            if cov < self.target_cov:  # 单边：仅协方差低于地板才提权
                new_w = self.multipliers[k] * self.up_factor
                self.multipliers[k] = float(min(max(new_w, self.weight_min), self.weight_max))
        self.update_count += 1
        return dict(self.multipliers)

    def state_dict(self) -> dict:
        return {
            'multipliers': dict(self.multipliers),
            'last_cov': dict(self.last_cov),
            'update_count': self.update_count,
            'config': {
                'target_cov': self.target_cov,
                'up_factor': self.up_factor,
                'weight_min': self.weight_min,
                'weight_max': self.weight_max,
                'terms': list(self.terms),
            },
        }

    def load_state_dict(self, state: dict) -> None:
        cfg = state.get('config', {})
        self.target_cov = float(cfg.get('target_cov', self.target_cov))
        self.up_factor = float(cfg.get('up_factor', self.up_factor))
        self.weight_min = float(cfg.get('weight_min', self.weight_min))
        self.weight_max = float(cfg.get('weight_max', self.weight_max))
        self.terms = tuple(cfg.get('terms', self.terms))
        self.multipliers = {k: float(v) for k, v in state['multipliers'].items()}
        self.last_cov = {k: float(v) for k, v in state.get('last_cov', {}).items()}
        self.update_count = int(state.get('update_count', 0))
