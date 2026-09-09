"""
多机车分布式动力 × 电空双制动分工 列内子控制器（层级二-decompose 模式）。

【2026-09-03 智能体分解重构（ADR-009）】把"整列统一 throttle"改为
"每机车=子控制器，独立决策 电制动(连续) / 空气制动(离散档位)"：

- ED（电制动）：连续可调，仅机车，即时作用（无波速传播延迟）
- AB（空气制动）：离散档位（MIN/SERVICE/EMERGENCY），沿车列以波速向后传播，
  是车钩力（纵向冲动）的主要来源

分工策略（给导师/审稿的"电空分工"核心）：
- 制动时 **首发电制动（ED）打满**：ED 响应快、不产生纵向冲动；
- 仅当 ED 功率不足以维持所需减速度（长大下坡 ED 的 功率/速度 约束）时
  才引入空气制动（AB）源 → 每机车独立错峰开启，最小化车钩力。
- 每机车 ED 独立错峰缓解（ed_frac 逐机车带时移），体现"每机车=独立体"。

输出形状：(num_locomotives, 2)，每行 [ed_frac, ab_frac]
  - ed_frac ∈ [0,1]：该机车电制动
  - ab_frac ∈ [-1,0) → 触发该机车作为 AB 波源（notch_from_throttle(ab_frac)）
  - ab_frac >= 0     → 该机车不作为 AB 源（缓解）

与 TrainLowLevelController.get_action_accel 同接口签名（fleet 无缝替换），
含车钩力 ≤1000kN 的安全钳制（投影到逐车 throttle 后走 SafetyLayer）。
"""

import numpy as np

from src.safety_layer import SafetyLayer
from src.environments.train_env import COUPLER_FORCE_LIMIT_N
from src.train_dynamics.braking import AirBrakeNotch, notch_from_throttle
from src.train_dynamics.etcs_braking import G_RAIL


class MultiLocoController:
    """每机车 (ED,AB) 子控制器：循环制动 / 目标加速度，电空分工 + 车钩力安全钳。"""

    def __init__(
        self,
        num_vehicles: int,
        loco_indices: list,
        dt: float = 0.1,
        max_accel: float = 1.0,
        coupler_force_limit_n: float = COUPLER_FORCE_LIMIT_N,
        enforce_coupler: bool = True,
        ed_priority: bool = True,
        mask_lever: str = 'none',
    ):
        self.num_vehicles = num_vehicles
        self.loco_indices = list(loco_indices)
        self.num_locomotives = len(self.loco_indices)
        self.dt = dt
        self.max_accel = max_accel
        self.coupler_force_limit_n = coupler_force_limit_n
        self.enforce_coupler = enforce_coupler
        self.ed_priority = ed_priority  # 电空分工：ED 优先打满，ED 不足才引 AB
        # 【2026-09-05 杠杆隔离消融】mask_lever∈{'none','ed','ab'}：
        #   - 'none'：两根杠杆（ed_mod/ab_mod）都生效（默认，一致性不变）
        #   - 'ed'  ：禁用 ed_mod（仅 ab_mod 生效）→ 验证"AB 错峰杠杆"的独立贡献
        #   - 'ab'  ：禁用 ab_mod（仅 ed_mod 生效）→ 验证"ED 深度杠杆"的独立贡献
        # 训练与评估须用同一 mask（train_fleet --mask_lever / evaluate_decompose
        # --mask_lever），否则策略与掩码失配。
        self.mask_lever = mask_lever
        self._safety = SafetyLayer(
            num_vehicles=num_vehicles,
            coupler_force_limit_n=coupler_force_limit_n,
            coupler_override='min_brake',
        )
        self._cyclic_braking = False

    # ------------------------------------------------------------------ #
    # 内部工具
    # ------------------------------------------------------------------ #
    def _ed_ab_actions(self, ed_nominal: float, ab_nominal: float) -> np.ndarray:
        """构造 (num_locomotives,2) 动作，电力每机车 [ed_frac, ab_frac]。"""
        act = np.zeros((self.num_locomotives, 2), dtype=float)
        for i in range(self.num_locomotives):
            act[i, 0] = float(np.clip(ed_nominal, 0.0, 1.0))
            act[i, 1] = float(np.clip(ab_nominal, -1.0, 1.0))
        return act

    def _project_to_throttle(self, act) -> np.ndarray:
        """把 (num_locomotives,2) (ED,AB) 投影为整列逐车 throttle（供安全层钳制）。"""
        n = self.num_vehicles
        th = np.full(n, 0.0)
        for i, loco_idx in enumerate(self.loco_indices):
            ed = float(act[i, 0])
            ab = float(act[i, 1])
            # 电空综合制动深度 = ED + AB 深度映射（保守取较大者）
            ab_depth = 0.0
            if ab < 0:
                notch = notch_from_throttle(ab)
                ab_depth = self._notch_depth(notch)
            depth = max(ed, ab_depth)
            th[loco_idx] = -depth
        return th

    @staticmethod
    def _notch_depth(notch: AirBrakeNotch) -> float:
        return {AirBrakeNotch.RELEASE: 0.0, AirBrakeNotch.MIN: 0.2,
                AirBrakeNotch.SERVICE: 0.75, AirBrakeNotch.EMERGENCY: 1.0}.get(notch, 0.0)

    def _coupler_throttle_scale(self, train_env) -> float:
        """车钩力接近上限时按比例缓和（0.8→1.0 时 scale 1→0）。"""
        if not self.enforce_coupler:
            return 1.0
        peak = float(np.max(np.abs(train_env.dynamics._coupler_forces()))) if self.num_vehicles else 0.0
        if peak <= 0:
            return 1.0
        ratio = peak / max(self.coupler_force_limit_n, 1e-6)
        if ratio > 0.8:
            return max(1.0 - (ratio - 0.8) / 0.2, 0.0)
        return 1.0

    def _ed_ab_price(self, train_env) -> float:
        """ED 可用度 ∈ [0,1.5]：功率约束下 ED 可提供的制动力 / 维持速度所需制动力。

        【2026-09-05 物理化（ADR-009.1 门控前置）】原实现 `_ed_ab_price(v)=clip(v/5)`
        使 ED 在循环制动带内（40-80km/h）恒"足够" → 规则基线的 AB 兜底实际永不可达，
        "ED 优先、不足转 AB"无从学起。改为：
        - ED 可用力 F_ed = min(P_ed 总再生制动功率 / v, 粘着上限 m_loco·g·μ)
        - 需求力 F_req = m_total·g·|最陡下坡|（Davis 阻力保守忽略 → 倾向多触发 AB）
        - ed_avail = F_ed / F_req：陡坡高速时 < 1 → 基线真实触发 AB 兜底；
          缓坡/低速时 ≥ 1 → ED 足够、AB 保持缓解（ED 优先）。
        """
        dyn = train_env.dynamics
        v = max(float(dyn.vel[0]), 1.0)
        m_total_kg = sum(float(vp.mass_t) for vp in dyn.consist.vehicles) * 1000.0
        m_loco_kg = sum(
            float(vp.mass_t) for vp in dyn.consist.vehicles if vp.is_locomotive
        ) * 1000.0
        p_ed_w = sum(
            float(vp.max_power_kw) for vp in dyn.consist.vehicles if vp.is_locomotive
        ) * 1000.0
        grades = np.asarray(dyn.grade, dtype=float)
        prof = getattr(dyn, '_grade_profile', None)
        if prof is not None:
            # 坡度从剖面按当前位置实时取（reset 后 dyn.grade 可能尚未刷新）
            grades = prof.grades_for_positions(dyn.pos)
        steepest_down = max(0.0, -float(np.min(grades))) if grades.size else 0.0
        f_ed = min(p_ed_w / v, m_loco_kg * G_RAIL * 0.35)  # 粘着上限 μ=0.35 保守
        f_req = m_total_kg * G_RAIL * steepest_down
        if f_req <= 1e-6:
            return 1.5  # 无下坡需求 → ED 富余
        return float(np.clip(f_ed / f_req, 0.0, 1.5))

    # ------------------------------------------------------------------ #
    # 主接口 1：循环制动
    # ------------------------------------------------------------------ #
    def get_action_cyclic_braking(
        self, train_env, v_max: float = 80.0 / 3.6, v_min: float = 40.0 / 3.6,
        brake_notch: float = -0.75, release_throttle: float = 0.0,
        v_max_adj: float = 0.0, v_min_adj: float = 0.0,
    ) -> np.ndarray:
        """规则循环制动（超速→制动 / 低速→缓解 / 中段维持），输出 (num_loco,2)。

        制动时电空分工：ED 优先打满；ED 可用度不足或坡度极大时才引入 AB 源，
        且每机车错峰（公司主体 = 分布式动力）。
        """
        eff_v_max = v_max + v_max_adj
        eff_v_min = v_min + v_min_adj
        vel = float(train_env.dynamics.vel[0])  # 队首速度

        if vel >= eff_v_max:
            self._cyclic_braking = True
        elif vel <= eff_v_min:
            self._cyclic_braking = False

        if self._cyclic_braking:
            # 制动：ED 优先打满，但**逐机车错峰**（体现"每机车=独立体"分布式动力）：
            # 队首机车先建立电制动，后部机车延迟错峰加入，避免整列同时制动前涌。
            ed_avail = self._ed_ab_price(train_env)
            # 是否需要 AB：ED 可用度不足时才引入空气制动兜底（长大下坡 ED 功率受限）
            ab_nominal = 0.0 if ed_avail >= 0.99 else float(brake_notch)
            scale = self._coupler_throttle_scale(train_env)
            act = np.zeros((self.num_locomotives, 2), dtype=float)
            for i in range(self.num_locomotives):
                # 错峰：越靠后的机车电制动深度略低（由机车 index 偏移量决定），
                # 形成"首机 ED 强、后机 ED 渐弱"的纵向错峰分配，抑制列内同步前涌。
                stagger = self._ed_stagger(i)
                ed = float(np.clip(1.0 - stagger, 0.0, 1.0)) * scale
                act[i, 0] = ed
                act[i, 1] = float(ab_nominal) * scale if ab_nominal != 0.0 else 0.0
            return act
        else:
            ed_nominal = 0.0
            ab_nominal = 0.0

        return self._ed_ab_actions(ed_nominal, ab_nominal)

    def _ed_stagger(self, loco_i: int) -> float:
        """第 loco_i 台机车的 ED 错峰偏移（0=满 ED，越大越弱）。"""
        if self.num_locomotives <= 1:
            return 0.0
        # 队首(0)=强，队尾=稍弱（纵向错峰，抑制同步前涌）
        frac = loco_i / max(self.num_locomotives - 1, 1)
        return 0.3 * frac  # 队尾 ED 为队首的 0.7 倍左右

    # ------------------------------------------------------------------ #
    # 主接口 3：decompose RL 调制（ADR-009.1 空电分工，逐机车 RL 智能体）
    # ------------------------------------------------------------------ #
    # RL 提前触发的 AB 兜底档位（MIN 档，负值 → 该机车成为 AB 波源）
    AB_FALLBACK_NOTCH = -0.4
    # 距 v_max 不足该裕量（m/s）时禁止抑制 AB（AB 兜底不被轻率关闭 → 防 EB 兜不住超速）
    AB_SUPPRESS_MARGIN_MPS = 0.5

    def get_action_decomposed(
        self, train_env, rl_actions, v_max: float = 80.0 / 3.6,
        v_min: float = 40.0 / 3.6, ed_mod_coef: float = 0.5,
        v_max_adj: float = 0.0, v_min_adj: float = 0.0,
    ):
        """规则循环制动基线 + 逐机车 RL 调制 → (final, baseline)，各 (num_loco,2)。

        【ADR-009.1 四层方案】RL 只学宏观分配，不学 AB 连续档位：
        - 基线 = get_action_cyclic_braking（ED 优先打满 + 逐机车错峰 + ED 不足才 AB 兜底）；
        - rl_actions (num_loco,2) 每机车 [ed_mod, ab_mod] ∈ [-1,1]：
          * ed_mod：调整本机车 ED 深度（±ed_mod_coef 绝对量，连续真物理杠杆，
            直接改变电制动力，区别于旧架构 ±0.5km/h 阈值偏移的 1.25% 杠杆）；
          * ab_mod > +0.5：抑制本机车 AB 源（仅当 vel < v_max - AB_SUPPRESS_MARGIN_MPS
            才生效——远离超速才允许关兜底，"ED 优先"可学且安全）；
          * ab_mod < -0.5：提前触发本机车 MIN 档 AB 兜底（错峰/预判性引入）。
        """
        baseline = self.get_action_cyclic_braking(
            train_env, v_max=v_max, v_min=v_min,
            v_max_adj=v_max_adj, v_min_adj=v_min_adj,
        )
        final = baseline.copy()
        vel = float(train_env.dynamics.vel[0])
        rl = np.asarray(rl_actions, dtype=float).reshape(self.num_locomotives, 2)
        for i in range(self.num_locomotives):
            ed_mod = float(np.clip(rl[i, 0], -1.0, 1.0))
            ab_mod = float(np.clip(rl[i, 1], -1.0, 1.0))
            # 【杠杆隔离消融】按 mask 禁用对应调制（值为 0 → 该维度不可改变基线）：
            if self.mask_lever == 'ed':
                ed_mod = 0.0   # 仅 AB 杠杆生效（ab_mod-only）
            elif self.mask_lever == 'ab':
                ab_mod = 0.0   # 仅 ED 杠杆生效（ed_mod-only）
            final[i, 0] = float(np.clip(baseline[i, 0] + ed_mod_coef * ed_mod, 0.0, 1.0))
            if baseline[i, 1] < 0 and ab_mod > 0.5:
                # 抑制本机车 AB 源：仅当远离超速裕量才生效（保住"AB 兜底"安全性）
                if vel < v_max - self.AB_SUPPRESS_MARGIN_MPS:
                    final[i, 1] = 0.0
            elif baseline[i, 1] >= 0 and ab_mod < -0.5:
                # 提前触发 MIN 档兜底（RL 学"何时/哪台机车引入 AB"）
                final[i, 1] = self.AB_FALLBACK_NOTCH
        # 【2026-09-09 修复：decompose 调制必须过车钩力投影】基线 get_action_cyclic_braking
        # 已应用 _coupler_throttle_scale，但 RL 调制后的 final 此前直接返回，导致 RL 可在
        # 车钩力接近上限时把 ED 顶满（+ed_mod_coef）/触发 AB，突破 1000kN 底线（ep41-50
        # 实测 peakCoupler 1366-1417kN、viol 138-794 发散）。与 get_action_accel 的
        # ed_throttle *= scale 对齐：调制输出同样按比例钳制（车钩力>80%上限 → 制动缓和）。
        scale = self._coupler_throttle_scale(train_env)
        final[:, 0] *= scale
        final[:, 1] *= scale
        return final, baseline

    # ------------------------------------------------------------------ #
    # 主接口 2：目标加速度（fleet 非分层模式，与 TrainLowLevelController 同签名）
    # ------------------------------------------------------------------ #
    def get_action_accel(self, train_env, target_accel: float) -> np.ndarray:
        n = self.num_vehicles
        throttle = np.full(n, 0.0)
        ed_throttle = np.full(n, 0.0)
        ab_sources = []
        if target_accel < 0:
            # 需要制动
            ed = min(-target_accel / max(self.max_accel, 1e-6), 1.0)
            ed = max(ed, 0.0)
            # 每个机车独立 ED（错峰忽略：规则冒烟用统一 ED）
            for loco_idx in self.loco_indices:
                ed_throttle[loco_idx] = ed
            scale = self._coupler_throttle_scale(train_env)
            ed_throttle *= scale
        else:
            for loco_idx in self.loco_indices:
                throttle[loco_idx] = min(target_accel / max(self.max_accel, 1e-6), 1.0)
        return np.stack([ed_throttle[self.loco_indices], np.full(self.num_locomotives, 0.0)], axis=1)

    # ------------------------------------------------------------------ #
    # A1 列间协同偏置（ADR-013 编队目的落地，2026-09-09）
    # ------------------------------------------------------------------ #
    def coordination_adj(
        self,
        gap_err: float,
        rel_speed: float,
        kp_gap: float = 0.001,
        kd_rel: float = 0.003,
        traction_coef: float = 0.0005,
        max_traction: float = 0.3,
        max_adj: float = 2.0,
    ) -> tuple:
        """按前列间距误差 + 相对速度差，返回速度带偏移 (v_max_adj, v_min_adj, traction)。

        A1b 扩展：首版 A1（仅调带）无效——因为 `get_action_cyclic_braking` 是纯两态
        （带外制动/带内惰行），带内根本没有"主动追逐"的杠杆，调带也追不上。
        因此协同需要**真杠杆**：返回一个 `traction∈[0,max_traction]`，让 TMPF 跟随列在
        **带内非制动段**输出正牵引主动追上（耦合进 decompose 的负 ed 通道）。领航列
        (n=0) 无前列，gap_err/rel_speed 恒 0 → traction=0，单列特性零回归。

        - gap_err > 0（间距偏大）：正 traction 主动追，缩间距；
        - gap_err < 0（间距偏小）：负 traction（退 => 更慢的释放，避免压迫前列车钩力）；
        - rel_speed = v_self - v_lead > 0（本列更快）：抑制 traction，防追尾积聚。
        """
        gap_adj = kp_gap * float(gap_err)
        v_adj = np.clip(gap_adj + kd_rel * float(rel_speed), -max_adj, max_adj)
        v_min_adj = np.clip(gap_adj, -max_adj, max_adj)
        traction = np.clip(
            traction_coef * float(gap_err) - kd_rel * float(rel_speed),
            -max_traction, max_traction,
        )
        return float(v_adj), float(v_min_adj), float(traction)

    def reset(self):
        self._cyclic_braking = False