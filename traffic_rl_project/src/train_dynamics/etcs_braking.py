"""
ETCS 目标距离超速防护曲线（"真 ATP"）实现。

依据：欧洲铁路局 ERTMS《Introduction to ETCS Braking Curves》
(ERA_ERTMS_040026 Version 1.5, 2020)，见 docs/papers/ERA_2020_Introduction_to_ETCS_Braking_Curves.pdf。

本模块为**车载超速/限速防护曲线（速度监督）**：

- EBD / 制动距离模型：给定前方目标点（降速/EOA 停车/间距约束），计算"从当前速度沿
  A_safe(v,d) 保证制动到目标所需距离"。A_safe(v,d) = A_brake_safe(v) + A_gradient(d)，
  A_gradient(d) = g·grade(d)：下坡(grade<0)为负 → 减小有效减速度 → 曲线更平、制动距离更长
  （长大下坡正好命中）。
- 制动建立时间最不利假设：紧急制动在建立时间 t_build_up 内尚未全制动力，按最不利加速度
  a_assumed 继续加速，之后才完全制动 —— 已并入制动距离模型（对应 PDF §3.1.1"worst case"）。
- 五级监督 I→P→W→SBI→EBI：由司机反应/服务制动时间换算成"距离预算"，提前量越大限速越低，
  层级严格单调；EBI 为硬介入（最宽松、最后触发）。
- 实时单点：只看当前速度对应的单个限位（非一次性整条曲线）。

诚实边界：本复现只做车载超速/限速监督，不做闭塞/信号层的进场授权（Movement Authority）；
"防追尾属信号级 ATP 职权，我们补充车钩力 + 缩短安全间隔"的叙事据此成立。
"""

import math
from dataclasses import dataclass
from typing import Callable, List, Optional, Tuple

import numpy as np


G_RAIL = 9.8066


@dataclass
class EbdTarget:
    """一个前方目标点。"""
    position_m: float   # 目标位置（线路里程，m）
    speed_mps: float    # 目标速度（停车=0，限速=限速值，间距约束=跟随速度）
    kind: str = "speed"  # 'stop' | 'speed' | 'gap'


class EtcsBrakingCurve:
    """ETCS 目标距离超速防护曲线计算器（制动距离 + EBI + 五级监督）。

    Args:
        nominal_emergency_decel: 名义紧急制动减速度（m/s²，本项目取 C80 紧急制动量级 a≈1.6，
            也可传 speed_profile 做速度步进）。
        speed_profile: 可选，名义减速度对速度的分段步进 [(v_hi_mps, a_mps2), ...]（升序）。
        k_dry: 干轨滚动校正因子 Kdry_rst（≤1，A_brake_dry = A_brake_emergency · K_dry_rst）。
        k_wet: 湿轨粘着损失校正 Kwet_rst（EN15595，案例 0.893）。
        wet_weight: 湿轨加权（0=纯干轨，1=纯湿轨最不利）。
        brake_build_up_s: 紧急制动建立时间（s；本项目可由空气波速传播算出，对齐
            braking.py 波速传播延迟：车辆累计长度/波速）。
        assumed_accel_during_buildup: 制动建立时间内最不利加速度（m/s²，下坡可为正）。
        speed_err_mps: 速度测量误差（m/s，案例 2.58%~3.49%）。
        driver_time_i_to_p / driver_time_p_to_ebi: 级间司机反应时间（s，ETCS 固定值）。
        service_build_up_s: 服务制动建立时间（s），SBI 级用（可选，默认=紧急建立时间）。
        grade_at: 可调用 position_m -> 无量纲坡度（下坡为负，兼容 GradeProfile.grade_at）。
        g: 重力加速度（m/s²）。
    """

    def __init__(
        self,
        nominal_emergency_decel: float = 1.6,
        speed_profile: Optional[List[Tuple[float, float]]] = None,
        k_dry: float = 1.0,
        k_wet: float = 0.893,
        wet_weight: float = 0.0,
        brake_build_up_s: float = 0.0,
        assumed_accel_during_buildup: float = 0.0,
        speed_err_mps: float = 0.0,
        driver_time_i_to_p: float = 9.0,
        driver_time_p_to_ebi: float = 4.0,
        service_build_up_s: Optional[float] = None,
        grade_at: Optional[Callable[[float], float]] = None,
        g: float = G_RAIL,
    ):
        self.speed_profile = speed_profile
        self._nominal_base = float(nominal_emergency_decel)
        self.k_dry = float(k_dry)
        self.k_wet = float(k_wet)
        self.wet_weight = float(np.clip(wet_weight, 0.0, 1.0))
        self.brake_build_up_s = float(brake_build_up_s)
        self.assumed_accel_during_buildup = float(assumed_accel_during_buildup)
        self.speed_err_mps = float(speed_err_mps)
        self.driver_time_i_to_p = float(driver_time_i_to_p)
        self.driver_time_p_to_ebi = float(driver_time_p_to_ebi)
        self.service_build_up_s = (
            float(brake_build_up_s)
            if service_build_up_s is None else float(service_build_up_s)
        )
        self.grade_at = grade_at if grade_at is not None else (lambda x: 0.0)
        self.g = float(g)

    # ------------------------------------------------------------------
    # 减速度（A_safe = A_brake_safe + A_gradient）
    # ------------------------------------------------------------------
    def nominal_decel(self, v_mps: float) -> float:
        """名义紧急制动减速度 A_brake_emergency（对速度的分段步进）。"""
        if self.speed_profile:
            a = self._nominal_base
            v_abs = abs(v_mps)
            for v_hi, a_step in self.speed_profile:
                if v_abs <= v_hi:
                    return float(a_step)
            return a
        return self._nominal_base

    def guaranteed_decel(self, v_mps: float) -> float:
        """保证紧急制动减速度 A_brake_safe(v) = 名义 × 校正因子（干湿加权最不利）。"""
        a_dry = self.nominal_decel(v_mps) * self.k_dry
        a_wet = a_dry * self.k_wet
        return (1.0 - self.wet_weight) * a_dry + self.wet_weight * a_wet

    def gradient_decel(self, position_m: float) -> float:
        """坡度分量 A_gradient(d) = g·grade(d)。下坡(grade<0) → 负，吃掉减速度。"""
        return self.g * self.grade_at(position_m)

    def effective_decel(self, v_mps: float, position_m: float) -> float:
        """A_safe(v,d) = A_brake_safe(v) + A_gradient(d)（正=减速方向）。"""
        return self.guaranteed_decel(v_mps) + self.gradient_decel(position_m)

    # ------------------------------------------------------------------
    # 制动距离（含制动建立时间最不利假设），EBD 曲线的数值基础
    # ------------------------------------------------------------------
    def braking_distance(self, v0: float, x_start: float, target: EbdTarget) -> float:
        """从速度 v0、位置 x_start 保证制动到目标所需距离（m）。

        含两段：
        - 建立期（t_build_up）内按 a_assumed 继续（最不利）
        - 之后按 A_safe(v, d) 全制动（含坡度分量）
        无法就此速度制动到目标（如制动无效） → 返回 inf。
        """
        v = float(v0)
        x = float(x_start)
        d = 0.0
        t = self.brake_build_up_s
        if t > 0.0:
            # 建立期内速度、位置推进（梯形积分）
            v_end = v + self.assumed_accel_during_buildup * t
            d_phase = 0.5 * (v + v_end) * t
            d += d_phase
            x += d_phase
            v = v_end
        # 全制动阶段（前向积分）
        while v > target.speed_mps + 1e-9 and x < target.position_m:
            a = self.effective_decel(v, x)
            if a <= 1e-9:
                return float('inf')  # 制动无效（下坡过大 / 减速度被吃光）
            # dS = v·dv/a，取小 dv 步进
            dv = 0.05
            vn = max(target.speed_mps, v - dv)
            if vn >= v:
                break
            ds = v * (v - vn) / a
            d += ds
            x += ds
            v = vn
        # 若目标速度不为 0，需检验到达目标位置时已减速到目标速度
        if v > target.speed_mps + 1e-9:
            return float('inf')
        return d

    # ------------------------------------------------------------------
    # 单点允许速度查询（实时单点，非整条曲线）
    # ------------------------------------------------------------------
    def v_allowed(self, target: EbdTarget, position_m: float) -> float:
        """在位置 position_m 处、目标为 target 时允许的最大速度（m/s，含建立时间最不利）。

        二分求解 max v 使 braking_distance(v, position) <= 可用距离（目标位置 - 当前位置）。
        若前方无约束（已过目标）→ 返回放大值 1e9。
        """
        avail = target.position_m - position_m
        if avail <= 0.0:
            return 1.0e9
        # 二分：v 单调增，braking_distance(v) 单调增
        lo, hi = 0.0, 200.0
        for _ in range(60):
            mid = 0.5 * (lo + hi)
            if self.braking_distance(mid, position_m, target) <= avail:
                lo = mid
            else:
                hi = mid
        return float(lo)

    def v_allowed_with_budget(self, target: EbdTarget, position_m: float,
                              budget_m: float) -> float:
        """给定制动距离预算 budget_m 下允许的最大速度（用于层级提前量）。"""
        if budget_m <= 0.0:
            return 0.0
        lo, hi = 0.0, 200.0
        for _ in range(60):
            mid = 0.5 * (lo + hi)
            if self.braking_distance(mid, position_m, target) <= budget_m:
                lo = mid
            else:
                hi = mid
        return float(lo)

    # 兼容旧测试接口：EBD 曲线采样/插值（由 v_allowed 数值构成）
    def compute_ebd(self, target: EbdTarget, max_dist: float = 6000.0,
                    ds: float = 50.0) -> List[Tuple[float, float]]:
        """EBD 曲线采样：[(position, allowed_speed), ...]，从目标位置向后（position 递减）。

        目标点本身（position == target.position_m）的允许速度 = 目标速度。
        """
        x_t = target.position_m
        xs = list(np.arange(x_t, max(0.0, x_t - max_dist), -ds))
        xs = [float(x) for x in xs]
        if not xs or xs[-1] != x_t:
            if xs and xs[-1] < x_t:
                xs.append(x_t)
            elif not xs:
                xs.append(x_t)
        xs = sorted(set(xs), reverse=True)
        curve = []
        for x in xs:
            if abs(x - x_t) <= 1e-9:
                curve.append((x, float(target.speed_mps)))
            else:
                curve.append((x, self.v_allowed(target, x)))
        return curve

    def v_allowed_at(self, curve: List[Tuple[float, float]], position_m: float) -> float:
        """查询 EBD 曲线上给定位置的允许速度（线性插值）。"""
        if not curve:
            return 0.0
        xs = [c[0] for c in curve]
        vs = [c[1] for c in curve]
        if position_m <= min(xs):
            return float(max(vs))
        if position_m >= max(xs):
            return float(min(vs))
        idx = int(np.clip(np.searchsorted(
            [-x for x in xs], -position_m, side='right'), 1, len(xs) - 1))
        x0_, y0_ = xs[idx - 1], vs[idx - 1]
        x1_, y1_ = xs[idx], vs[idx]
        t = (position_m - x0_) / (x1_ - x0_ + 1e-12)
        return float(y0_ + t * (y1_ - y0_))

    def braking_distance_needed(self, target: EbdTarget, v0: float) -> float:
        """从速度 v0 保证制动到目标速度所需距离（m）（独立于当前绝对位置）。

        沿前行方向从参考位置 0 积分，按所在坡度逐点采样 A_gradient（PDF §3.3.1）。
        无法就此速度制动到目标（如下坡过大、减速度被吃光）→ 返回 inf。
        """
        if target.position_m <= 0.0:
            return float('inf')
        return self.braking_distance(v0, 0.0, target)

    # ------------------------------------------------------------------
    # EBI（硬介入）与五级监督
    # ------------------------------------------------------------------
    def _level_distance_budget(self, target: EbdTarget, position_m: float,
                               v_cur: float, lead_s: float) -> float:
        """某监督级的可用制动距离预算 = 可用距离 - 反应时间内的前行距离。"""
        avail = target.position_m - position_m
        d_react = v_cur * lead_s + 0.5 * self.assumed_accel_during_buildup * lead_s * lead_s
        return max(0.0, avail - d_react)

    def supervision_levels(self, target: EbdTarget, v_cur: float,
                           position_m: float) -> dict:
        """返回当前速度/位置下五级监督的允许速度与触发等级。

        提前量：I > P > W > SBI > EBI（I 需最早反应 → 限速最低；EBI 硬介入 → 限速最高）。
        """
        avail = target.position_m - position_m
        if avail <= 0.0:
            return {'allowed': {'I': 1e9, 'P': 1e9, 'W': 1e9, 'SBI': 1e9, 'EBI': 1e9},
                    'active': None}
        # EBI = 硬介入，无额外反应提前量（扣除速度测量误差）
        v_ebi = max(0.0, self.v_allowed(target, position_m) - self.speed_err_mps)
        # 软级按反应时间换算距离预算
        leads = {
            'I':   self.driver_time_i_to_p + self.driver_time_p_to_ebi,
            'P':   self.driver_time_p_to_ebi,
            'W':   0.5 * self.driver_time_p_to_ebi,
            'SBI': 0.25 * self.driver_time_p_to_ebi,
        }
        allowed = {}
        for key, lead in leads.items():
            budget = self._level_distance_budget(target, position_m, v_cur, lead)
            allowed[key] = self.v_allowed_with_budget(target, position_m, budget)
        allowed['EBI'] = v_ebi
        # 保证 EBI 不低于（宽松于）其上游软级
        allowed['EBI'] = max(allowed['EBI'], allowed['SBI'])
        # 触发：速度（含误差）>= 某级阈值，取最先命中的最严级
        order = ['I', 'P', 'W', 'SBI', 'EBI']
        active = None
        for key in order:
            if v_cur + self.speed_err_mps >= allowed[key]:
                active = key
        return {'allowed': allowed, 'active': active}

    def supervise(self, target: EbdTarget, v_cur: float, position_m: float) -> float:
        """便捷：返回建议速度限位（软件监督最严级 = I）。"""
        out = self.supervision_levels(target, v_cur, position_m)
        a = out['allowed']
        return float(min(a['I'], a['P'], a['W'], a['SBI']))

    # ------------------------------------------------------------------
    # 快速路径：安全层只需 EBI/SBI 两级，用"单趟制动距离表"替代
    # 5×60 次二分 ×4000 步积分，速度提升 ~两个数量级，且不改变公共
    # supervision_levels 语义（测试不受影响）。
    # ------------------------------------------------------------------
    def _distance_table(self, target: EbdTarget, position_m: float):
        """构建 v -> braking_distance(v) 的单调表（一次前向积分）。

        与 braking_distance 同一口径（dv=0.05、含建立期内最不利加速、逐点坡度）。
        返回 (vs, fs)：vs 递增、fs=braking_distance(v) 单调递增。
        提前在制动距离已远超最大可用距离处截断（远处无需细查），控制规模。
        """
        t = self.brake_build_up_s
        a_assumed = self.assumed_accel_during_buildup
        v_tgt = float(target.speed_mps)
        avail_max = target.position_m - position_m
        dv = 0.05
        # 1) 纯制动段 g(u) = 从 u 制动到 v_tgt 的距离（向上走，逐点坡度）
        v = v_tgt
        x = float(target.position_m)
        gacc = 0.0
        vs = [v_tgt]
        gs = [0.0]
        # 截断上限：制动距离超过最大可用距离还多留一点 + 速度 200m/s 硬上界
        hard_stop = max(avail_max + 200.0, 0.0)
        while True:
            a = self.effective_decel(v, x)
            if a <= 1e-9:
                break  # 制动无效（下坡过大），后面恒 inf，无需再积累
            vn = v + dv
            ds = v * (v - vn) / a if vn <= v else (v * dv / a)
            gacc += ds
            x -= ds
            vs.append(vn)
            gs.append(gacc)
            v = vn
            if v >= 200.0 or gacc > hard_stop:
                break
        # 2) 补上建立期偏移：braking_distance(v) = 0.5*(v+v_after)*t + g(v_after)
        #    v_after = v + a_assumed*t；g 用线性插值取（建立期内位移很小，误差可忽略）。
        vs_arr = np.asarray(vs, dtype=float)
        gs_arr = np.asarray(gs, dtype=float)
        if t > 0.0:
            v_after = vs_arr + a_assumed * t
            # g(v_after) 插值：超出表尾则取表尾（该处制动距离已足够大）
            g_after = np.interp(v_after, vs_arr, gs_arr, left=0.0, right=gs_arr[-1])
            build = 0.5 * t * (vs_arr + v_after)
            fs = build + g_after
        else:
            fs = gs_arr
        return vs_arr, fs

    def _allowed_at_budget(self, vs, fs, budget_m: float, v_cur: float) -> float:
        """在单调表 (vs,fs) 上二分求 max v（fs<=budget_m）。budget<=0 → 0。"""
        if budget_m <= 0.0:
            return 0.0
        if fs.size == 0 or fs[-1] <= budget_m + 1e-9:
            # 全表都允许 → 取表尾（未受限，够得着全部距离）
            return float(vs[-1])
        lo, hi = 0, int(fs.size) - 1
        # fs 单调不减，找最大 idx 使 fs[idx] <= budget
        # 用并查：二分
        idx = int(np.searchsorted(fs, budget_m, side='right') - 1)
        idx = max(0, idx)
        return float(vs[idx])

    def supervise_targets(self, targets, v_cur: float, position_m: float) -> dict:
        """对前方所有目标求 EBI / SBI 最小允许速度（安全层热路径用）。

        一次计算所有目标的制动距离表，返回 {'EBI': min, 'SBI': min}；
        无前方有效目标时返回 {'EBI': None, 'SBI': None}。
        EBI 无反应提前量（只扣速度误差）；SBI 提前 lead_sbi 反应距离。
        """
        ebi = float('inf')
        sbi = float('inf')
        lead_sbi = 0.25 * self.driver_time_p_to_ebi
        any_target = False
        for tgt in targets:
            # 【2026-09-09 防追尾修复】原 `if position_m >= tgt.position_m: continue`
            # 在"后列越过前列尾"后直接豁免该目标 → 越过瞬间 ETCS 失去保护，后列不受控
            # 穿透前列（53km 长时域实测 gaps→-951m）。现改为越过后**不豁免**：
            # avail<=0 → 允许速度压到目标速度下方（必须减速回 target.speed，堵住穿透）。
            # 仍保留"前方无约束（目标在很后/全在身后另有更远目标）"时不误伤。
            any_target = True
            avail = tgt.position_m - position_m
            if avail <= 0.0:
                # 已到达/越过目标：不允许再以高于目标速度继续逼近 → 压到 target.speed。
                # （对 gap 防追尾，target.speed=前列速度；越过即要求降到前列速度以下，
                #   由后续成本/停止目标进一步收紧。最小干预：避免越过瞬间零约束。）
                V_past = float(tgt.speed_mps)
                if V_past < ebi:
                    ebi = V_past
                if V_past < sbi:
                    sbi = V_past
                continue
            vs, fs = self._distance_table(tgt, position_m)
            # EBI：无额外反应提前量
            v_ebi = self._allowed_at_budget(vs, fs, avail, v_cur) - self.speed_err_mps
            # SBI：扣反应距离，取更严
            d_react = v_cur * lead_sbi + 0.5 * self.assumed_accel_during_buildup * lead_sbi * lead_sbi
            v_sbi = self._allowed_at_budget(vs, fs, max(0.0, avail - d_react), v_cur)
            # 保证 EBI 不严于（低过）SBI（与 supervision_levels 中 EBI>=SBI 一致）
            v_ebi = max(v_ebi, v_sbi)
            if v_ebi < ebi:
                ebi = v_ebi
            if v_sbi < sbi:
                sbi = v_sbi
        if not any_target:
            return {'EBI': None, 'SBI': None}
        return {'EBI': float(ebi), 'SBI': float(sbi)}


def braking_build_up_from_train(
    train_length_m: float,
    propagation_speed_mps: float = 250.0,
) -> float:
    """由空气制动波速传播延迟计算紧急制动等效建立时间（s）。

    对齐 braking.py：空气制动沿车列以有限波速传播，尾车最迟建立全制动力。
    用**车辆累计长度 / 波速**（真实重载数百米→数秒），不要用车钩 free_length。

    Args:
        train_length_m: 车列总长（m，万里 1+0 = 机车长 + 货车节数×车长）。
        propagation_speed_mps: 制动波速（常用 200，紧急 250 m/s，braking.py 口径）。

    Returns:
        尾车达到全制动力所需时间（s）。
    """
    if propagation_speed_mps <= 0:
        return 0.0
    return float(train_length_m) / float(propagation_speed_mps)