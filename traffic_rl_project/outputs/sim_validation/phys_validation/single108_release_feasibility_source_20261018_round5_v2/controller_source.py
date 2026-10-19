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

from src.safety_layer import DEFAULT_COUPLER_FORCE_LIMIT_N as COUPLER_FORCE_LIMIT_N
from src.train_dynamics.braking import AirBrakeNotch, notch_from_throttle
from src.train_dynamics.etcs_braking import G_RAIL
from src.train_dynamics.resistance import G as DYNAMICS_GRAVITY


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
        ab_min_refill_s: float = 222.0,
        ab_min_hold_s: float = 0.0,
        ed_recovery_rate_per_s: float = 0.0,
        ed_baseline_projection: str = 'legacy',
        anticipate_etcs: bool = False,
        ed_recovery_scope: str = 'all',
        ed_grade_feedforward: bool = False,
        ed_physics_availability: bool = False,
        ed_prelimit: bool = False,
        cyclic_notch_50: bool = False,
        cyclic_brake_trigger_kmh: float = None,
        cyclic_release_kmh: float = None,
        cyclic_ab_upgrade_kmh: float = None,
        cyclic_ab_upgrade_notch: str = 'service',
        ed_release_coordination: bool = False,
        ed_release_hold_s: float = 50.0,
        ed_release_boost_kn: float = 900.0,
        ed_native_force_conversion: bool = False,
        ed_upgrade_ramp_s: float = 0.0,
        ed_upgrade_ramp_scale: float = 1.0,
    ):
        self.num_vehicles = num_vehicles
        self.ed_native_force_conversion = bool(ed_native_force_conversion)
        self.loco_indices = list(loco_indices)
        self.num_locomotives = len(self.loco_indices)
        self.dt = dt
        self.max_accel = max_accel
        self.coupler_force_limit_n = coupler_force_limit_n
        self.enforce_coupler = enforce_coupler
        self.ed_priority = ed_priority  # 电空分工：ED 优先打满，ED 不足才引 AB
        # Controller tuning, not a vehicle constant or a literature constraint.
        # Disabled by default: the 1/s trial increased full-route overspeed
        # and violation counts. Positive values are experimental opt-ins.
        self.ed_recovery_rate_per_s = float(ed_recovery_rate_per_s)
        if not np.isfinite(self.ed_recovery_rate_per_s) or self.ed_recovery_rate_per_s < 0:
            raise ValueError('ed_recovery_rate_per_s must be finite and nonnegative')
        self._previous_ed = None
        if ed_recovery_scope not in ('all', 'coupler'):
            raise ValueError('ed_recovery_scope must be all or coupler')
        self.ed_recovery_scope = ed_recovery_scope
        self.ed_grade_feedforward = bool(ed_grade_feedforward)
        self.ed_physics_availability = bool(ed_physics_availability)
        # Diagnostic-only: 120 s and second-route trials increased overspeed.
        # Short-window smoothing is insufficient evidence for default use.
        self.ed_prelimit = bool(ed_prelimit)
        self._ed_recovery_pending = np.zeros(self.num_locomotives, dtype=bool)
        # Preserve the established baseline protection by default. Removing it
        # increased first-window interface violations from 170 to 1008.
        # Single projection remains an explicit diagnostic option.
        if ed_baseline_projection not in ('single', 'legacy'):
            raise ValueError('ed_baseline_projection must be single or legacy')
        self.ed_baseline_projection = ed_baseline_projection
        # Experimental: use the existing service supervision ceiling earlier
        # in normal control. No ETCS/vehicle constants are changed.
        self.anticipate_etcs = bool(anticipate_etcs)
        # 【2026-09-05 杠杆隔离消融】mask_lever∈{'none','ed','ab'}：
        #   - 'none'：两根杠杆（ed_mod/ab_mod）都生效（默认，一致性不变）
        #   - 'ed'  ：禁用 ed_mod（仅 ab_mod 生效）→ 验证"AB 错峰杠杆"的独立贡献
        #   - 'ab'  ：禁用 ab_mod（仅 ed_mod 生效）→ 验证"ED 深度杠杆"的独立贡献
        # 训练与评估须用同一 mask（train_fleet --mask_lever / evaluate_decompose
        # --mask_lever），否则策略与掩码失配。
        self.mask_lever = mask_lever
        # 【ADR-021 决策1 2026-10-01】AB「最小充风时间 / 最小保持时间」进动作空间（文献 Zhang2024）。
        # - ab_min_refill_s：AB 源释放后到下一次允许**新增/保持**该源的"最短充风时间"（秒）。
        #   出处：docs/VALIDATION_BASELINE.md:201（张二田 S6：困难区段 5 次循环制动，最短充风
        #   222 s）；实测范围 175~512 s 见同文件 :169（赵紫宁2022）。**有出处，勿改数值。**
        # - ab_min_hold_s：AB 源施加后到下一次允许**释放**的最短保持时间（秒）。
        #   **2026-10-01 结案：无出处 ⇒ 默认 0.0（该半边不激活）**，不得编造数值。
        #   检索范围：① Zhang2024 全文 §2.2 仅三条运行约束（充风式(9)/速度式(10)/电制力式(11)），
        #   无"最短制动保持时长"；②《铁路机车操作规则》（TG/JW104-2012）最接近的两条均不适用
        #   ——"列检作业场…减压100kPa并保压3min"是**站内保压试验**非运行约束；"重载列车
        #   v<30km/h 不应缓解"是**速度门限**，且本场景 v_min=40km/h ⇒ 恒不触发（空约束）；
        #   ③ 赵紫宁2022 表5-3 的制动时长 212~1358s 是**实测观测值**非下界。
        #   若日后要建模"低速段禁止缓解"，须作**独立机制**并入更低 v_min 剖面，勿复用本参数。
        #   留痕：docs/REFERENCE_INDEX.md 落地映射 + DIAGNOSTICS_2026-10.md「检索-2026-10-01」。
        # ⚠️ 计时前提（防后人误改单位）：get_action_decomposed **每个原始 dt 步都会被调用一次**
        #   （"动作保持"/decision_interval 由外层循环反复调 env.step 实现，env 内部仍每步重算
        #   规则基线与 RL 调制）。因此 _ab_step 等价原始步数，
        #   elapsed_s = (self._ab_step - last_step) * self.dt 即正确仿真秒数；
        #   **不要**乘 decision_interval，也不要新增 decision_interval 参数（会引入 10× 偏差）。
        self.ab_min_refill_s = float(ab_min_refill_s)
        self.ab_min_hold_s = float(ab_min_hold_s)
        # AB 充风/保持门控状态（**仅在 get_action_decomposed 内维护**；
        # get_action_cyclic_braking 保持无状态）。
        # 【2026-10-14 朔黄运营口径标定（表3「制动缓解位置」，全默认关=旧行为，编队主线零回归）】
        # - cyclic_notch_50：规则循环制动用 CYCLIC（减压 50 kPa）档替代 SERVICE（140 kPa）。
        #   依据：表3 全部 14 个制动循环减压一律 50 kPa
        #   （reference/simulation/data_line/朔黄铁路_完整线路信息表_表3表4补充版.xlsx）。
        # - cyclic_brake_trigger_kmh / cyclic_release_kmh：独立制动触发/缓解速度门
        #   （表3：制动触发 58–65 km/h、缓解 50–60 km/h），与奖励速度带 40/80 解耦，
        #   **不改 v_min/v_max、观测/reward 语义不动**。
        # - ed_release_coordination + ed_release_hold_s：循环期 ED 下限 300 kN；
        #   缓解时刻抬再生力 ≈900 kN 并保持 50 s 再撤
        #   （表3「缓解前抬再生力、缓解后保持 50s 不变」；本实现在缓解转换时刻抬至 900 kN
        #   并持 50 s，覆盖缓解波不同步窗口，为"缓解前抬"的因果可实现近似）。
        self.cyclic_notch_50 = bool(cyclic_notch_50)
        self.cyclic_brake_trigger_kmh = (None if cyclic_brake_trigger_kmh is None
                                         else float(cyclic_brake_trigger_kmh))
        self.cyclic_release_kmh = (None if cyclic_release_kmh is None
                                   else float(cyclic_release_kmh))
        # 【K 组 2026-10-16 规则层 AB 预升级（默认 None = 旧行为，零回归）】
        # J 负结果根因链（归档 J_floor_decomp 时间线）：50 kPa 循环档在最陡段制动力不足
        # → 车速缓爬到 80 → ATP 规则 C **事后**把全列动作改 SERVICE（ab_command 单源猛刹、
        # ab_sources 被清空）→ 头部 SERVICE 波向中部传播（argmax 断面力 11→19→48→126）
        # → 头波撞中后部成主团簇。本旋钮把升级**提前到触发门之前**：队首速度一旦
        # ≥ (制动触发门 − 升级裕量)，规则层循环兜底档即由 CYCLIC(50 kPa) 预升级到
        # SERVICE(140 kPa)——仍是规则层自己发起的错峰 AB 源（受充风/并发/veto 门约束），
        # 而非 ATP 事后整列单源猛刹；裕量耗尽（达触发门）即自然进入正常循环制动。
        # 语义：预升级只在启用 CYCLIC 档（cyclic_notch_50）时有意义；升级条件为
        # "触发门非 None 且 cyclic 开"，否则维持旧 CYCLIC/SERVICE 选择。
        self.cyclic_ab_upgrade_kmh = (None if cyclic_ab_upgrade_kmh is None
                                      else float(cyclic_ab_upgrade_kmh))
        # 【M 组 2026-10-16 升级档强度（默认 'service' = K/L 行为零回归）】
        # L 负结果证据：预升级覆盖越多（方向①成立），SERVICE(140 kPa, β 0.75) 过刹
        # 与振荡越强（|F|>1350 步 548→1769、overspeed 483→1234）——方向①须与
        # 方向②（降强度）联合。'min' = MIN(70 kPa, β 0.20) 中间档：升压仍先于
        # ATP 事后猛刹（介于 CYCLIC 0.17 与 SERVICE 0.75 之间），过刹幅度大减。
        if cyclic_ab_upgrade_notch not in ('service', 'min'):
            raise ValueError("cyclic_ab_upgrade_notch must be 'service' or 'min'")
        self.cyclic_ab_upgrade_notch = cyclic_ab_upgrade_notch
        # 【X 组 2026-10-16 ED-AB 波到达协同（默认 0.0/1.0 = 关，零回归）】
        # R 峰值微观实证（R_eot t=21661-21811）：头/中先 service，尾车 AB 波延迟 7.5 s
        # 才到达 → 尾 free-run 冲 81.7，ruleA 又把头机 ED 钳 366→150 而尾机全开
        # （-274+service）→ 中尾速度反转，断面 133 拉爆 1823 kN。本旋钮：升级**边沿**
        # 触发后窗内（ed_upgrade_ramp_s）头/中机车 ED × scale 降权（不提前猛减速），
        # 窗到期（尾波已到）恢复满值 → 全列 ED+AB 同步减速，缩小波延迟期速度反转。
        if ed_upgrade_ramp_s < 0:
            raise ValueError('ed_upgrade_ramp_s must be nonnegative')
        if not (0.0 <= ed_upgrade_ramp_scale <= 1.0):
            raise ValueError('ed_upgrade_ramp_scale must be in [0,1]')
        self.ed_upgrade_ramp_s = float(ed_upgrade_ramp_s)
        self.ed_upgrade_ramp_scale = float(ed_upgrade_ramp_scale)
        # ramp 状态（仅 get_action_cyclic_braking 内维护）
        self._ed_ramp_steps_left = 0
        self._ed_ramp_armed = True   # 升级条件下降沿后允许再触发
        self.ed_release_coordination = bool(ed_release_coordination)
        self.ed_release_hold_s = float(ed_release_hold_s)
        # 缓解窗口再生力目标（kN）：默认 900 = 表3「缓解前抬再生力」；
        # 文献锚定可调低（Oxford TSE 运营标准缓解期 50%≈230 kN，
        # 部标《铁路机车操作规则》缓解后逐步退动力制动 → F 组试 300 kN）。
        self.ed_release_boost_kn = float(ed_release_boost_kn)
        self._ed_hold_steps = 0
        self._ab_step = 0
        self._ab_on = [False] * self.num_locomotives
        # 初值 -1e9 保证首次允许（充风/保持门不会拦第一个源/第一次释放）
        self._ab_last_release_step = [-10 ** 9] * self.num_locomotives
        self._ab_last_apply_step = [-10 ** 9] * self.num_locomotives
        # 门控拒绝计数（诊断用）
        self.ab_refill_veto_count = 0
        self.ab_hold_veto_count = 0
        # 【2026-09-30 死代码消除】原内部 SafetyLayer 从未被调用（真安全层 = 环境的
        # train_env.safety，在动作喂给动力学前统一钳制）。此处删除，避免"两套安全层"混淆；
        # 车钩力源头门控改为直接咨询 train_env.safety（见 get_action_decomposed）。
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
                notch = notch_from_throttle(ab, allow_cyclic=self.cyclic_notch_50)
                ab_depth = self._notch_depth(notch)
            depth = max(ed, ab_depth)
            th[loco_idx] = -depth
        return th

    @staticmethod
    def _notch_depth(notch: AirBrakeNotch) -> float:
        return {AirBrakeNotch.RELEASE: 0.0, AirBrakeNotch.CYCLIC: 0.17,
                AirBrakeNotch.MIN: 0.2,
                AirBrakeNotch.SERVICE: 0.75, AirBrakeNotch.EMERGENCY: 1.0}.get(notch, 0.0)

    def _coupler_throttle_scale(self, train_env) -> float:
        """车钩力接近上限时按比例缓和（0.8→1.0 时 scale 1→0）。"""
        if not self.enforce_coupler:
            return 1.0
        # 【2026-09-30 口径统一】用**断面力**每车视图（原每车净力在拉压交界处误判）
        peak = (float(np.max(train_env.dynamics.coupler_interface_forces_per_vehicle()))
                if self.num_vehicles else 0.0)
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
        m_total_kg = sum(float(vp.mass_t) for vp in dyn.consist.vehicles) * 1000.0
        grades = np.asarray(dyn.grade, dtype=float)
        prof = getattr(dyn, '_grade_profile', None)
        if prof is not None:
            # 坡度从剖面按当前位置实时取（reset 后 dyn.grade 可能尚未刷新）
            grades = prof.grades_for_positions(dyn.pos)
        steepest_down = max(0.0, -float(np.min(grades))) if grades.size else 0.0
        # Query the same efficiency, adhesion and per-locomotive speeds as
        # the actuator, including the existing distributed ED allocation.
        nominal = np.zeros(self.num_vehicles)
        nominal[self.loco_indices] = [
            1.0 - self._ed_stagger(i) for i in range(self.num_locomotives)]
        if self.ed_physics_availability:
            f_ed = max(0.0, -float(np.sum(dyn._electric_braking_forces(nominal))))
        else:
            # Keep the established gate until paired dynamics accept the new
            # estimate: grade-4 trials increased air-brake coupler violations.
            v = max(float(dyn.vel[0]), 1.0)
            locos = [vp for vp in dyn.consist.vehicles if vp.is_locomotive]
            f_ed = min(sum(vp.max_power_kw for vp in locos) * 1000.0 / v,
                       sum(vp.mass_t for vp in locos) * 1000.0 * G_RAIL * 0.35)
        f_req = m_total_kg * G_RAIL * steepest_down
        if f_req <= 1e-6:
            return 1.5  # 无下坡需求 → ED 富余
        return float(np.clip(f_ed / f_req, 0.0, 1.5))

    def _ed_cannot_hold_speed(self, train_env) -> bool:
        """Experimental static screen; safety and air-wave supervision stay active."""
        dyn = train_env.dynamics
        profile = getattr(dyn, '_grade_profile', None)
        grades = (profile.grades_for_positions(dyn.pos) if profile is not None
                  else np.asarray(dyn.grade, dtype=float))
        grade_force = float(np.sum(-dyn.masses_kg * DYNAMICS_GRAVITY * grades))
        resistance = float(np.sum(dyn._resistance_forces()))
        nominal = np.zeros(self.num_vehicles)
        nominal[self.loco_indices] = [
            1.0 - self._ed_stagger(i) for i in range(self.num_locomotives)]
        electric_capacity = max(0.0, -float(np.sum(
            dyn._electric_braking_forces(nominal))))
        return grade_force - resistance > electric_capacity + 1e-6

    def _ab_gate(self, i: int, want_on: bool) -> bool:
        """【ADR-021 决策1】AB 充风/保持门控：返回「是否允许这次 AB 状态变更」。

        - want_on=True 且当前 off：仅在充风时长 ≥ ab_min_refill_s 后才允许新增/保持该源，
          否则 ab_refill_veto_count += 1 并拒绝（本步不发这个新源）；
        - want_on=False 且当前 on：仅在施加后保持时长 ≥ ab_min_hold_s 后才允许释放该源，
          否则 ab_hold_veto_count += 1 并拒绝（本步不释放）；
        - 其余（状态不变）直接允许。

        计时口径：_ab_step 每原始 dt 步 +1（见 __init__ 说明），故
        elapsed_s = (self._ab_step - last_step) * self.dt。ab_min_refill_s=0 时
        (Δstep*dt >= 0) 恒真 ⇒ 零回归（行为与改造前一致）。
        """
        if want_on and not self._ab_on[i]:
            if (self._ab_step - self._ab_last_release_step[i]) * self.dt >= self.ab_min_refill_s:
                return True
            self.ab_refill_veto_count += 1
            return False
        if (not want_on) and self._ab_on[i]:
            if (self._ab_step - self._ab_last_apply_step[i]) * self.dt >= self.ab_min_hold_s:
                return True
            self.ab_hold_veto_count += 1
            return False
        return True

    # ------------------------------------------------------------------ #
    # 主接口 1：循环制动
    # ------------------------------------------------------------------ #
    def _operating_ceiling(self, train_env, v_max, v_max_adj):
        ceiling = min(v_max, v_max + v_max_adj)
        if self.anticipate_etcs:
            curve = getattr(train_env, 'etcs_curve', None)
            targets = getattr(train_env, 'etcs_targets', ())
            if curve is not None and targets:
                _, service_ceiling = train_env.safety._etcs_check(
                    float(train_env.dynamics.pos[0]), float(train_env.dynamics.vel[0]),
                    curve, targets)
                if service_ceiling is not None and np.isfinite(service_ceiling):
                    ceiling = min(ceiling, max(0.0, service_ceiling))
        return ceiling

    def _grade_feedforward_actions(self, train_env):
        """Invert existing ED physics to offset net downhill force, read-only."""
        dyn = train_env.dynamics
        act = np.zeros((self.num_locomotives, 2))
        if not self.num_locomotives:
            return act
        profile = getattr(dyn, '_grade_profile', None)
        grades = profile.grades_for_positions(dyn.pos) if profile is not None else dyn.grade
        required = max(0.0, float(np.sum(
            -dyn.masses_kg * DYNAMICS_GRAVITY * grades
            - dyn._resistance_forces() + dyn._air_braking_forces())))
        if required <= 0.0:
            return act
        weights = np.array([1.0 - self._ed_stagger(i) for i in range(self.num_locomotives)])
        command = np.zeros(self.num_vehicles)

        def capacity(level):
            command[self.loco_indices] = level * weights
            return -float(np.sum(dyn._electric_braking_forces(command)))

        if capacity(1.0) <= required:
            level = 1.0  # Insufficient ED: saturate, keep the existing AB fallback.
        else:
            lo, hi = 0.0, 1.0
            for _ in range(24):  # Numerical inverse precision, not a vehicle constant.
                mid = (lo + hi) / 2.0
                if capacity(mid) >= required:
                    hi = mid
                else:
                    lo = mid
            level = hi
        act[:, 0] = level * weights
        return act

    def get_action_cyclic_braking(
        self, train_env, v_max: float = 80.0 / 3.6, v_min: float = 40.0 / 3.6,
        brake_notch: float = -0.75, release_throttle: float = 0.0,
        v_max_adj: float = 0.0, v_min_adj: float = 0.0,
        _scale_ed: bool = True,
    ) -> np.ndarray:
        """规则循环制动（超速→制动 / 低速→缓解 / 中段维持），输出 (num_loco,2)。

        制动时电空分工：ED 优先打满；ED 可用度不足或坡度极大时才引入 AB 源，
        且每机车错峰（公司主体 = 分布式动力）。
        """
        # Formation offsets may lower the braking ceiling, never raise the
        # absolute line limit. Match the environment's all-vehicle metric.
        eff_v_max = self._operating_ceiling(train_env, v_max, v_max_adj)
        # Chase must not collapse the apply/release band. Reuse the existing
        # control speed margin (not a new vehicle/air-brake time constant).
        release_ceiling = max(0.0, eff_v_max - self.AB_SUPPRESS_MARGIN_MPS)
        eff_v_min = min(v_min + v_min_adj, release_ceiling)
        vel = float(train_env.dynamics.vel[0])  # 队首速度
        max_vel = float(np.max(train_env.dynamics.vel))

        # 【表3 运营口径覆盖】独立制动触发/缓解速度门（默认 None = 旧行为，零回归）。
        # 触发门只许提前（≤ eff_v_max，不得放宽超速防线）；
        # 缓解门夹在 [eff_v_min, release_ceiling]（不得早于 v_min、不得在超速带内缓解）。
        trigger_mps = eff_v_max
        if self.cyclic_brake_trigger_kmh is not None:
            trigger_mps = min(eff_v_max, self.cyclic_brake_trigger_kmh / 3.6)
        release_mps = eff_v_min
        if self.cyclic_release_kmh is not None:
            release_mps = min(max(eff_v_min, self.cyclic_release_kmh / 3.6), release_ceiling)

        formation_ceiling = min(v_max, v_max + v_max_adj)
        was_braking = self._cyclic_braking
        if vel >= trigger_mps or max_vel >= formation_ceiling:
            self._cyclic_braking = True
        elif vel <= release_mps and max_vel <= release_ceiling:
            self._cyclic_braking = False
        # 【表3】制动→缓解转换时刻进入"抬 ED 保持"窗口（ed_release_coordination 开启才生效）
        if self.ed_release_coordination and was_braking and not self._cyclic_braking:
            self._ed_hold_steps = int(round(self.ed_release_hold_s / self.dt))

        if self._cyclic_braking:
            if self.ed_release_coordination:
                self._ed_hold_steps = 0
            # 制动：ED 优先打满，但**逐机车错峰**（体现"每机车=独立体"分布式动力）：
            # 队首机车先建立电制动，后部机车延迟错峰加入，避免整列同时制动前涌。
            ed_avail = self._ed_ab_price(train_env)
            # 是否需要 AB：ED 可用度不足时才引入空气制动兜底（长大下坡 ED 功率受限）
            # 【表3】cyclic_notch_50 开启时兜底档 = CYCLIC（50 kPa）替代 SERVICE（140 kPa）
            ab_nominal = 0.0 if ed_avail >= 0.99 else (
                self.CYCLIC_AB_SENTINEL if self.cyclic_notch_50 else float(brake_notch))
            # 高速预升级仍覆盖 CYCLIC 和 ED-only 两种状态；先按整列各车
            # 坡度、Davis 阻力及真实 ED 能力筛选，避免把一辆车进入陡坡
            # 当成整列都需要强空气制动。原 AB 兜底、源准入和 ATP 不变。
            _upgrading = (self.cyclic_ab_upgrade_kmh is not None
                          and self._ed_cannot_hold_speed(train_env)
                          and ab_nominal in (0.0, self.CYCLIC_AB_SENTINEL)
                          and max_vel >= self.cyclic_ab_upgrade_kmh / 3.6)
            if _upgrading:
                # 【X 组】升级**边沿**启动 ED ramp 窗（尾车收波前窗 ≈ 列长/波速 ≈ 7.5 s）：
                # 窗内 ED × scale，避免头中在尾波到达前猛减速制造速度反转。
                if self._ed_ramp_armed and self.ed_upgrade_ramp_s > 0.0:
                    self._ed_ramp_steps_left = max(
                        int(round(self.ed_upgrade_ramp_s / self.dt)), 1)
                self._ed_ramp_armed = False
            else:
                self._ed_ramp_armed = True   # 升级条件退出后允许下次边沿再触发
            if _upgrading:
                # 【M 组】升级档强度：'service'=K/L（brake_notch -0.75，140 kPa）；
                # 'min'=-0.15 → notch_from_throttle → MIN(70 kPa, β 0.20) 中间档。
                ab_nominal = (float(brake_notch)
                              if self.cyclic_ab_upgrade_notch == 'service' else -0.15)
            _ramp_active = self._ed_ramp_steps_left > 0
            if _ramp_active:
                self._ed_ramp_steps_left -= 1
            scale = self._coupler_throttle_scale(train_env) if _scale_ed else 1.0
            # 【表3】循环期 ED 恒持 300–400 kN（取 300 kN 下限；仅协调开启时生效）
            ed_floor = (self._ed_frac_for_total_kn(train_env, self.CYCLIC_ED_FLOOR_KN)
                        if self.ed_release_coordination else 0.0)
            act = np.zeros((self.num_locomotives, 2), dtype=float)
            for i in range(self.num_locomotives):
                # 错峰：越靠后的机车电制动深度略低（由机车 index 偏移量决定），
                # 形成"首机 ED 强、后机 ED 渐弱"的纵向错峰分配，抑制列内同步前涌。
                stagger = self._ed_stagger(i)
                ed = float(np.clip(1.0 - stagger, 0.0, 1.0)) * scale
                if self.ed_release_coordination:
                    # 【H 组 2026-10-15】floor 不再乘 scale：表3「循环期 ED 恒持 300–400 kN」
                    # 是运营口径的恒持下限，被 scale（ratio>0.8 后线性归零）侵蚀即名存实亡
                    # ——G 组 t≈678s 峰值探针实证 phys_ed 被砍到 [0,0] 后 8 s 内
                    # 1200→2203 kN（前部无 ED 只剩 AB、后部全制动的压缩正反馈）。
                    # 力比例缓和只作用于超出 floor 的部分。
                    ed = max(ed, ed_floor)
                if _ramp_active:
                    # 【X 组】ramp 窗内 ED 降权（尾波未达期头中不猛减速）；floor 之下
                    # 不再压（与 scale 同口径：只缓和超出运营下限的部分）
                    ed *= self.ed_upgrade_ramp_scale
                act[i, 0] = ed
                # AB is a discrete notch, not a continuously scalable force.
                # Source admission is handled by the decompose gates and environment.
                act[i, 1] = float(ab_nominal)
            return act
        else:
            # 【表3】缓解后把再生力抬至 ≈900 kN 并保持 50 s 再撤（空气已缓解、ED 顶住增速）。
            # 置于 ed_prelimit/feedforward 之前：协调窗口内输出优先于其他 ED 实验分支。
            # 【E 组 2026-10-15 实测撤销】曾豁免 `_coupler_throttle_scale`（防 scale→0 砍 boost），
            # 实测峰值反而 2448→2660 kN：压缩期满档 ED 继续拖慢前部 → 后部撞得更狠。
            # 文献佐证（Oxford TSE 平稳操纵系统：从控电制力与车钩力变化量**成正比**、
            # 运营标准缓解期只用 50%；部标《铁路机车操作规则》缓解后**逐步**退动力制动）
            # ⇒ 保留 scale 的力比例自适应，不豁免。
            if self.ed_release_coordination and self._ed_hold_steps > 0:
                self._ed_hold_steps -= 1
                boost = self._ed_frac_for_total_kn(train_env, self.ed_release_boost_kn)
                act = np.zeros((self.num_locomotives, 2))
                act[:, 0] = boost * (
                    self._coupler_throttle_scale(train_env) if _scale_ed else 1.0)
                return act
            if self.ed_prelimit:
                # Ordinary ED only: do not advance cyclic/air thresholds.
                head_start = max(eff_v_min, eff_v_max - self.AB_SUPPRESS_MARGIN_MPS)
                all_start = max(eff_v_min, formation_ceiling - self.AB_SUPPRESS_MARGIN_MPS)
                ramp = np.clip(max(
                    (vel - head_start) / max(eff_v_max - head_start, 1e-6),
                    (max_vel - all_start) / max(formation_ceiling - all_start, 1e-6)), 0.0, 1.0)
                if ramp > 0.0:
                    act = np.zeros((self.num_locomotives, 2))
                    act[:, 0] = [ramp * (1.0 - self._ed_stagger(i))
                                 for i in range(self.num_locomotives)]
                    if _scale_ed:
                        act[:, 0] *= self._coupler_throttle_scale(train_env)
                    return act
            if self.ed_grade_feedforward and vel >= eff_v_min:
                act = self._grade_feedforward_actions(train_env)
                # Blend from coasting at the floor to force balance within the
                # existing control speed margin; avoid a 0/full switch there.
                blend = np.clip((vel - eff_v_min) / self.AB_SUPPRESS_MARGIN_MPS, 0.0, 1.0)
                act[:, 0] *= blend
                if _scale_ed:
                    act[:, 0] *= self._coupler_throttle_scale(train_env)
                return act
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

    def _ed_frac_for_total_kn(self, train_env, target_kn: float) -> float:
        """Invert native ED physics for a total-force request; saturate if infeasible.

        Opt-in single-locomotive candidate uses native speeds and adhesion.
        Default and multi-locomotive paths preserve the legacy conversion.
        A saturated request is not achieved force.
        """
        # Preserve the validated legacy multi-locomotive path. This repair is
        # scoped to the newly adopted single-locomotive research consist.
        if self.num_locomotives > 1 or not self.ed_native_force_conversion:
            v = max(float(train_env.dynamics.vel[0]), 1.0)
            cap = min(0.85 * 9600.0 * 1000.0 / v,
                      0.35 * 188.0 * 1000.0 * G_RAIL * 0.85)
            return float(np.clip(target_kn * 1000.0 /
                                 max(self.num_locomotives * cap, 1e-6), 0.0, 1.0))
        dyn = train_env.dynamics
        target_n = max(0.0, float(target_kn) * 1000.0)
        if target_n == 0.0 or not self.num_locomotives:
            return 0.0
        command = np.zeros(self.num_vehicles)

        def capacity(level):
            command[self.loco_indices] = level
            return max(0.0, -float(np.sum(dyn._electric_braking_forces(command))))

        # Native power and adhesion saturation are not linear in throttle.
        # Query the real actuator instead of hard-coded vehicle/adhesion values.
        if capacity(1.0) <= target_n:
            return 1.0
        lo, hi = 0.0, 1.0
        for _ in range(24):
            mid = (lo + hi) / 2.0
            if capacity(mid) >= target_n:
                hi = mid
            else:
                lo = mid
        return hi

    # ------------------------------------------------------------------ #
    # 主接口 3：decompose RL 调制（ADR-009.1 空电分工，逐机车 RL 智能体）
    # ------------------------------------------------------------------ #
    # RL 提前触发的 AB 兜底档位（SERVICE；-0.4 经现有映射为 SERVICE）
    AB_FALLBACK_NOTCH = -0.4
    # 【2026-10-14 表3 运营口径】循环档哨兵：ab_frac 落 CYCLIC(50 kPa) 带
    # （notch_from_throttle allow_cyclic=True 时 x∈(1e-6,0.1) → CYCLIC）
    CYCLIC_AB_SENTINEL = -0.05
    # 表3：循环期 ED 恒持 300–400 kN（下限 300）/ 缓解抬再生力 ≈900 kN（全列合计）
    CYCLIC_ED_FLOOR_KN = 300.0
    CYCLIC_ED_BOOST_KN = 900.0
    # 距 v_max 不足该裕量（m/s）时禁止抑制 AB（AB 兜底不被轻率关闭 → 防 EB 兜不住超速）
    AB_SUPPRESS_MARGIN_MPS = 0.5
    # 【2026-09-10 安全层源头门控】当前列内耦合器力 ≥ 该比例上限时禁止 RL 新增 AB 源
    # （防"高力下叠加新 AB"的暴力吸态；车钩力=安全层兜底，SSOT，不靠 reward 惩罚）
    # 【2026-09-26 治本-滞后峰值防护】0.85→0.6 + 限制单步并发新增源：
    # 感知式安全层按"上一时刻力"钳制，拦不住 RL 新增 AB 波源沿列传播 ~5s 后才到的滞后峰值
    # （诊断-2026-09-25 AB 塑形短训：AB 激活后 viol 332 / pk1549、pk~1162 均值破线）。故：
    # ① 下调阈值：力比 ≥ 0.6 即禁止新增源（更早封"高力叠加"）；
    # ② 单步并发数 ≤1：杜绝多机车同时触发 AB 的压缩波叠加。仅保留基线 ED 调制。
    AB_ADD_SOURCE_MAX_RATIO = 0.6
    # 单次决策内允许新增的 AB 源最大并发数（>1 会多源同步压缩波叠加 → 滞后峰值叠加）
    AB_MAX_CONCURRENT_ADD = 1

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
            【ADR-024，2026-10-02】ed_mod_coef 回退为 **0.5（半幅调制）**：
            ADR-023 曾放宽到 1.0 以消除 MPC 桥接的"越权请求"截断（455→0），但完整
            剖面 A/B 实测显示——① 放宽对 MPC 无可用收益（53km 依旧远弱于规则基线）；
            ② 对 RL 有害：可整幅撤销规则层 ED（Δ=−1.0）⇒ 持续破 1000 kN（ep51–55
            旧 0.5 口径 viol=0 vs 新 1.0 口径 viol 327–694）。故回退 0.5；越权请求
            计数保留为观测指标（MPC baseline 细节不承担立论）。带宽仍由本默认值
            **唯一定义**（evaluate_decompose / metadata 派生读取，勿手抄常量）。
          * ab_mod > +0.5：抑制本机车 AB 源（仅当 vel < v_max - AB_SUPPRESS_MARGIN_MPS
            才生效——远离超速才允许关兜底，"ED 优先"可学且安全）；
          * ab_mod < -0.5：提前触发本机车 SERVICE 档 AB 兜底（错峰/预判性引入）。
        """
        baseline = self.get_action_cyclic_braking(
            train_env, v_max=v_max, v_min=v_min,
            v_max_adj=v_max_adj, v_min_adj=v_min_adj,
            _scale_ed=self.ed_baseline_projection == 'legacy',
        )
        # 【ADR-021 决策1】AB 计时：本方法每个原始 dt 步调用一次（见 __init__ 前提说明）。
        self._ab_step += 1
        final = baseline.copy()
        vel = float(train_env.dynamics.vel[0])
        max_vel = float(np.max(train_env.dynamics.vel))
        rl = np.asarray(rl_actions, dtype=float).reshape(self.num_locomotives, 2)
        operating_ceiling = self._operating_ceiling(train_env, v_max, v_max_adj)
        formation_ceiling = min(v_max, v_max + v_max_adj)
        ab_suppress_ceiling = operating_ceiling if self.anticipate_etcs else formation_ceiling
        # 【2026-09-10】当前列内耦合器力/上限比（安全层源头门控用；本次决策内统一评估一次）
        cur_coupler_ratio = 0.0
        if self.enforce_coupler and self.num_vehicles:
            # 【2026-09-30 口径统一】改用**断面力**每车视图（原每车净力会漏报/误报）
            cf = np.asarray(
                train_env.dynamics.coupler_interface_forces_per_vehicle(), dtype=float)
            if cf.size:
                cur_coupler_ratio = float(np.max(cf)) / max(self.coupler_force_limit_n, 1e-6)
        # 【2026-09-30 安全层 AB 减权限】咨询环境安全层的"一步新增 AB 源硬闸门"
        # （断面力口径 + 位置/波速预测式峰值防护）：命中则本步禁止 RL 新增 AB 源，
        # 仅保留规则基线。感知式钳制看的是"当前力"，拦不住 AB 波传播 ~5s 后的滞后峰值，
        # 故由安全层按列长/波速外推峰值提前封源（诊断-2026-09-30 根因②）。
        ab_add_vetoed = False
        if self.enforce_coupler:
            ab_add_vetoed = bool(
                train_env.safety.ab_new_source_veto(train_env._state_snapshot()))
        # 【2026-09-26 治本-滞后峰值防护】单步新增 AB 源并发计数（>1 禁止 → 防多车钩压缩波同步叠加）
        added_ab_sources = 0
        for i in range(self.num_locomotives):
            ed_mod = float(np.clip(rl[i, 0], -1.0, 1.0))
            ab_mod = float(np.clip(rl[i, 1], -1.0, 1.0))
            # 【杠杆隔离消融】按 mask 禁用对应调制（值为 0 → 该维度不可改变基线）：
            if self.mask_lever == 'ed':
                ed_mod = 0.0   # 仅 AB 杠杆生效（ab_mod-only）
            elif self.mask_lever == 'ab':
                ab_mod = 0.0   # 仅 ED 杠杆生效（ed_mod-only）
            final[i, 0] = float(np.clip(baseline[i, 0] + ed_mod_coef * ed_mod, 0.0, 1.0))
            if baseline[i, 1] < 0 and ab_mod > 0.15:
                # 抑制本机车 AB 源：仅当远离超速裕量才生效（保住"AB 兜底"安全性）
                if max_vel < ab_suppress_ceiling - self.AB_SUPPRESS_MARGIN_MPS:
                    # 【ADR-021 决策1】释放该源需过"最小保持时间"门
                    # （ab_min_hold_s>0 时才可能拒绝；默认 0.0 恒允许=零回归）。
                    if self._ab_gate(i, False):
                        final[i, 1] = 0.0
            elif baseline[i, 1] >= 0 and ab_mod < -0.15:
                # 提前触发 SERVICE 档兜底（RL 学"何时/哪台机车引入 AB"）
                # 【2026-09-10 安全层源头门控：防暴力 AB 吸态】车钩力由安全层兜底（SSOT），
                # 不靠 reward 惩罚。但感知式 _coupler_throttle_scale 按"当前时刻"力钳制，
                # 拦不住 RL 新增 AB 源沿列传播的**滞后峰值**（1km 列车 @200m/s 波速 ~5s，
                # 触发时力未升 → scale=1 不钳，峰值随后爆发）。故从**源头**封：当前列内
                # 耦合器力已 ≥ 安全线时，禁止 RL 新增 AB 源（仅保留基线 ED 调制）。
                # 依据：诊断-2026-09-10 三轮短训（相对锚定/车钩力惩罚/回滚）逐 ep 崩点一致的
                # 长时程坍塌，主因正是探索踩进"高耦合器力下叠加新 AB 源"的暴力吸态。
                # 【2026-09-26 治本】阈值 0.6 + 单步并发 ≤1：感知式安全层兜不住 5s 滞后峰值，
                # 故更早封新增源 + 限并发，避免多机车同步 AB 压缩波叠加。
                if (cur_coupler_ratio < self.AB_ADD_SOURCE_MAX_RATIO
                        and added_ab_sources < self.AB_MAX_CONCURRENT_ADD
                        and not ab_add_vetoed
                        and self._ab_gate(i, True)):
                    final[i, 1] = self.AB_FALLBACK_NOTCH
                    added_ab_sources += 1
                # 否则高力下/已限并发时禁止新增源（final[i,1] 保持 baseline 的 0 → 不引入新 AB）
        # Single mode uses a nominal baseline and one final ED projection.
        # Legacy mode retains the original baseline protection as well, for
        # isolated replay of its effect on coupler forces.
        # AB uses discrete source admission, not continuous depth scaling.
        scale = self._coupler_throttle_scale(train_env)
        if self.ed_recovery_scope == 'coupler':
            # Track a recovery episode only while braking remains requested.
            # A normal release ends it; the next cyclic application stays fast.
            self._ed_recovery_pending &= final[:, 0] > 0
            if scale < 1.0:
                self._ed_recovery_pending |= self._cyclic_braking | (final[:, 0] > 0)
                if scale == 0.0 and self.ed_grade_feedforward:
                    # A fully protected feedforward request is not coasting.
                    # Recover its intent only here; avoid adding observer state.
                    floor = min(v_min + v_min_adj, max(
                        0.0, operating_ceiling - self.AB_SUPPRESS_MARGIN_MPS))
                    if vel > floor:
                        self._ed_recovery_pending |= (
                            self._grade_feedforward_actions(train_env)[:, 0] > 0)
        final[:, 0] *= scale
        # 【J 组 2026-10-16 修复】H 组已在 baseline 制动分支把 300 kN 循环期 ED floor
        # 改为不乘 scale，但本方法随后这行 `final[:,0] *= scale` 会把保住的 floor
        # **二次清零**（I 组实测与 H 逐位相同、主团簇 2247 kN 不降的根因：ratio≥1 时
        # scale=0 → 前部无 ED 只剩 AB → 压缩正反馈）。表3「循环期 ED 恒持 300–400 kN」
        # 是运营口径恒持下限，此处按同一口径兜底复原；仅 ed_release_coordination 开
        # 且处于循环制动分支时生效（默认关 = 旧行为零回归，编队线 YAML 不受影响）。
        if self.ed_release_coordination and self._cyclic_braking:
            floor = self._ed_frac_for_total_kn(train_env, self.CYCLIC_ED_FLOOR_KN)
            final[:, 0] = np.maximum(final[:, 0], floor)
        # Fast safety reductions, slow recovery: never exceed the currently
        # projected request, and never delay ED at the speed ceiling. ATP is
        # applied separately by the environment and retains final authority.
        if (self._previous_ed is not None and self.ed_recovery_rate_per_s > 0
                and vel < operating_ceiling and max_vel < formation_ceiling):
            limited = np.minimum(
                final[:, 0], self._previous_ed + self.ed_recovery_rate_per_s * self.dt)
            if self.ed_recovery_scope == 'coupler':
                if scale >= 1.0:
                    self._ed_recovery_pending &= limited < final[:, 0]
                final[:, 0] = np.where(self._ed_recovery_pending, limited, final[:, 0])
            else:
                final[:, 0] = limited
        self._previous_ed = final[:, 0].copy()
        # Do not move an established AB source across notch boundaries in
        # response to instantaneous coupler force. Keep the discrete request;
        # new-source veto, refill and ATP retain their existing authority.
        # 【ADR-021 决策1】规则层自身新增的 AB 源同受充风门约束（gate 判定须在"提交状态"之前）：
        # baseline[i,1]<0 = 规则层要求该机车发 AB；若 final 仍 <0 且本步由 off→on 而充风门拒绝
        # ⇒ 本步不发这个新源（final[i,1]=0）。已 on 的源不受影响（不撤销已建立源）。
        for i in range(self.num_locomotives):
            if (baseline[i, 1] < 0 and final[i, 1] < 0
                    and not self._ab_on[i]):
                # [Step 0.5 quick-check 2026-10-08] (see DIAGNOSTICS 2026-10-08 safety-layer note)
                emergency = max_vel >= v_max
                allowed = (
                    emergency
                    or (cur_coupler_ratio < self.AB_ADD_SOURCE_MAX_RATIO
                        and added_ab_sources < self.AB_MAX_CONCURRENT_ADD
                        and not ab_add_vetoed)
                )
                if allowed and self._ab_gate(i, True):
                    added_ab_sources += 1
                else:
                    final[i, 1] = 0.0
        # 【ADR-021 决策1】提交本步 AB 状态（基于 final）：记录 0→1 的施加时刻 / 1→0 的释放时刻。
        for i in range(self.num_locomotives):
            new_on = bool(final[i, 1] < 0)
            if new_on and not self._ab_on[i]:
                self._ab_last_apply_step[i] = self._ab_step
            elif (not new_on) and self._ab_on[i]:
                self._ab_last_release_step[i] = self._ab_step
            self._ab_on[i] = new_on
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

    def record_executed_ed(self, ed):
        """Anchor opt-in recovery to the last post-safety actuator command."""
        value = np.asarray(ed, dtype=float)
        if (value.shape != (self.num_locomotives,) or not np.all(np.isfinite(value))
                or np.any(value < 0.0) or np.any(value > 1.0)):
            raise ValueError('Executed ED must be one finite fraction per locomotive')
        if self.ed_recovery_rate_per_s > 0:
            self._previous_ed = value.copy()

    def reset(self):
        self._cyclic_braking = False
        self._ed_ramp_steps_left = 0
        self._ed_ramp_armed = True
        self._previous_ed = None
        self._ed_recovery_pending[:] = False
        self._ed_hold_steps = 0
        self._ab_step = 0
        self._ab_on = [False] * self.num_locomotives
        self._ab_last_release_step = [-10 ** 9] * self.num_locomotives
        self._ab_last_apply_step = [-10 ** 9] * self.num_locomotives
        self.ab_refill_veto_count = 0
        self.ab_hold_veto_count = 0

# Frozen zero-RL, single-locomotive diagnostic; no production promotion.
_release_force_base_action = MultiLocoController.get_action_decomposed
_release_force_base_cyclic = MultiLocoController.get_action_cyclic_braking

def _release_force_cyclic(self, train_env, *args, **kwargs):
    was_braking = self._cyclic_braking
    was_holding = self._ed_hold_steps > 0
    previous = None if self._previous_ed is None else self._previous_ed.copy()
    action = _release_force_base_cyclic(self, train_env, *args, **kwargs)
    enabled = (getattr(self, '_release_force_enabled', False)
               and self.num_locomotives == 1 and self.ed_release_coordination)
    if enabled and was_braking and not self._cyclic_braking and previous is not None:
        physical = np.zeros(train_env.dynamics.num_vehicles)
        physical[self.loco_indices] = previous
        self._release_force_hold_kn = 0.25 * max(
            0.0, -float(train_env.dynamics._electric_braking_forces(physical).sum()) / 1000.0)
    target = getattr(self, '_release_force_hold_kn', None)
    if (enabled and not self._cyclic_braking and target is not None
            and (was_holding or was_braking)):
        command = self._ed_frac_for_total_kn(train_env, target)
        scale = self._coupler_throttle_scale(train_env) if kwargs.get('_scale_ed', True) else 1.0
        action[:, 0] = command * scale
    return action

def _release_force_action(self, train_env, rl_actions, *args, **kwargs):
    if not hasattr(self, '_release_original_recovery'):
        self._release_original_recovery = (self.ed_recovery_rate_per_s, self.ed_recovery_scope)
    self._release_force_enabled = bool(np.all(np.asarray(rl_actions) == 0.0))
    if self._ab_step == 0:
        self._release_force_hold_kn = None
    if self._release_force_enabled:
        self.ed_recovery_rate_per_s = 0.5
        self.ed_recovery_scope = 'coupler'
        if self._release_force_hold_kn is not None and not self._cyclic_braking:
            self.ed_recovery_rate_per_s = 0.05
            self.ed_recovery_scope = 'all'
    else:
        self.ed_recovery_rate_per_s, self.ed_recovery_scope = self._release_original_recovery
    return _release_force_base_action(self, train_env, rl_actions, *args, **kwargs)

MultiLocoController.get_action_cyclic_braking = _release_force_cyclic
MultiLocoController.get_action_decomposed = _release_force_action


# Experimental request shaping only: all native source gates and ATP remain.
_readmission_base_action = MultiLocoController.get_action_decomposed

def _readmission_prepare_action(self, train_env, rl_actions, *args, **kwargs):
    final, baseline = _readmission_base_action(self, train_env, rl_actions, *args, **kwargs)
    elapsed = (self._ab_step - self._ab_last_release_step[0]) * self.dt
    ceiling = kwargs.get('v_max', 80.0 / 3.6)
    preparing = (self.num_locomotives == 1
                 and bool(np.all(np.asarray(rl_actions) == 0.0))
                 and self._release_force_hold_kn is not None
                 and not any(self._ab_on)
                 and elapsed >= max(0.0, self.ab_min_refill_s - 20.0)
                 and float(train_env.dynamics.vel.max()) < ceiling - self.AB_SUPPRESS_MARGIN_MPS)
    if preparing:
        # Temporarily relax the legacy cyclic ED operating floor, never a safety gate.
        final[:, 0] = np.minimum(final[:, 0], 0.25)
    was_preparing = getattr(self, '_readmission_preparing', False)
    if preparing != was_preparing:
        if not hasattr(self, '_ed_guard_events'):
            self._ed_guard_events = []
        self._ed_guard_events.append({'step': int(self._ab_step),
                                     'preparing': bool(preparing),
                                     'elapsed_since_release_s': float(elapsed)})
    self._readmission_preparing = preparing
    return final, baseline

MultiLocoController.get_action_decomposed = _readmission_prepare_action


# Diagnostic phase cap: source admission is left to both original gates.
_service_phase_base_action = MultiLocoController.get_action_decomposed

def _service_phase_cap_action(self, train_env, rl_actions, *args, **kwargs):
    final, baseline = _service_phase_base_action(self, train_env, rl_actions, *args, **kwargs)
    enabled = (self.num_locomotives == 1
               and bool(np.all(np.asarray(rl_actions) == 0.0))
               and self._release_force_hold_kn is not None
               and any(self._ab_on))
    if enabled:
        # Experimental ED operating floor relaxation; native ATP remains downstream.
        final[:, 0] = np.minimum(final[:, 0], 0.25)
    return final, baseline

MultiLocoController.get_action_decomposed = _service_phase_cap_action

"""Native diagnostic lookahead; no training-time or production safety guarantee."""
import copy

import numpy as np


def clone_native_prediction_env(train_env):
    """Copy all native history, discarding only the diagnostic actuator observer.

    Python function closures are not deep-copied: leaving record_inputs attached
    would call the ORIGINAL dynamics from a copied environment.
    """
    branch = copy.deepcopy(train_env)
    hook = branch.dynamics.__dict__.get('step_vehicles_ed_ab')
    if hook is not None:
        if getattr(hook, '__name__', '') != 'record_inputs':
            raise ValueError('Unknown instance dynamics override in prediction state')
        del branch.dynamics.__dict__['step_vehicles_ed_ab']
    return branch


def evaluate_native_release(train_env, controller, control_kwargs, horizon_s):
    """Run a copied zero-RL controller and native physics through a refill window.

    Caller must set its wrapper to skip recursive guards when probe_active is
    true. Both native source admission and ATP remain enabled in the copy.
    """
    if not np.isfinite(horizon_s) or horizon_s <= 0:
        raise ValueError('Positive finite prediction horizon required')
    branch = clone_native_prediction_env(train_env)
    ctrl = copy.deepcopy(controller)
    ctrl._release_probe_active = True
    ceiling = float(control_kwargs.get('v_max', 80.0 / 3.6))
    floor = float(control_kwargs.get('v_min', 40.0 / 3.6))
    limit = float(ctrl.coupler_force_limit_n)
    count = int(np.ceil(horizon_s / ctrl.dt))
    # A forecast is not a training rollout. Its time budget must not expire at
    # the live episode's cutoff; only extend the copied administrative limit.
    original_max_steps = branch.max_steps
    branch.max_steps = max(branch.max_steps, branch.steps + count + 1)
    rows = []
    reason = 'horizon_completed'
    try:
        for step in range(count):
            if step % 500 == 0:
                print(f'release_lookahead step={step}/{count}', flush=True)
            action, _ = ctrl.get_action_decomposed(
                branch, np.zeros((ctrl.num_locomotives, 2)), **control_kwargs)
            _, _, terminated, truncated, info = branch.step(action)
            ctrl.record_executed_ed(info['actual_loco_ed'])
            peak = float(np.abs(branch.dynamics.coupler_interface_forces()).max())
            speed = float(branch.dynamics.vel.max())
            rows.append([(step + 1) * ctrl.dt, peak, speed,
                         float(branch.dynamics.vel.mean()), float(action[0, 1])])
            if not np.all(np.isfinite(rows[-1])):
                reason = 'nonfinite'
                break
            if peak > limit:
                reason = 'coupler_limit'
                break
            if speed >= ceiling - 1e-6:
                reason = 'speed_ceiling'
                break
            if float(branch.dynamics.vel.mean()) < floor - 1e-6:
                reason = 'speed_floor'
                break
            if terminated or truncated:
                reason = 'environment_ended'
                break
        rows = np.asarray(rows)
        return {
            'feasible': reason == 'horizon_completed',
            'reason': reason,
            'horizon_s': float(horizon_s),
            'simulated_s': float(rows[-1, 0]),
            'peak_kn': float(rows[:, 1].max() / 1000),
            'max_vehicle_kmh': float(rows[:, 2].max() * 3.6),
            'live_max_steps': int(original_max_steps),
            'prediction_max_steps': int(branch.max_steps),
            'trajectory': rows,
        }
    finally:
        branch.close()

from pathlib import Path as _PredictionPath
from src.train_dynamics.train import AIR_BRAKE_PROPAGATION_SPEED_SERVICE
_guard_base_action = MultiLocoController.get_action_decomposed

def _guarded_release_action(self, train_env, rl_actions, *args, **kwargs):
    if getattr(self, '_release_probe_active', False):
        return _guard_base_action(self, train_env, rl_actions, *args, **kwargs)
    controls = dict(zip(('v_max', 'v_min', 'ed_mod_coef', 'v_max_adj', 'v_min_adj'), args))
    controls.update(kwargs)
    floor = float(controls.get('v_min', 40.0 / 3.6)) + float(controls.get('v_min_adj', 0.0))
    ceiling = self._operating_ceiling(train_env, controls.get('v_max', 80.0 / 3.6), controls.get('v_max_adj', 0.0))
    original_release = self.cyclic_release_kmh
    release = min(max(floor, (original_release if original_release is not None else floor * 3.6) / 3.6), ceiling - self.AB_SUPPRESS_MARGIN_MPS)
    head = float(train_env.dynamics.vel[0])
    eligible = (self.num_locomotives == 1 and np.all(np.asarray(rl_actions) == 0.0)
                and getattr(self, '_release_force_hold_kn', None) is not None
                and self._cyclic_braking and any(self._ab_on)
                and head <= release and float(train_env.dynamics.vel.max()) <= ceiling - self.AB_SUPPRESS_MARGIN_MPS)
    delayed_gate = None
    if eligible:
        retry = getattr(self, '_release_guard_retry_kmh', None)
        if retry is not None and head * 3.6 > retry + 1e-8:
            delayed_gate = retry
        else:
            length = abs(float(train_env.dynamics.pos[0] - train_env.dynamics.pos[-1]))
            build = max(train_env.dynamics.brake_rise_time_by_notch.values()) + length / AIR_BRAKE_PROPAGATION_SPEED_SERVICE
            horizon = self.ab_min_refill_s + build
            print(f'release_probe begin step={self._ab_step+1} speed={head*3.6:.3f} horizon={horizon:.2f}', flush=True)
            result = evaluate_native_release(train_env, self, controls, horizon)
            trace = result.pop('trajectory')
            directory = _PredictionPath('outputs/sim_validation/phys_validation/single108_release_feasibility_trial_20261018_round5_v2/release_predictions')
            directory.mkdir(parents=True, exist_ok=True)
            trace_path = directory / f'step{self._ab_step+1}.npz'
            if trace_path.exists():
                raise RuntimeError('Prediction archive already exists; use a fresh run directory')
            np.savez_compressed(trace_path, rows=trace)
            at_floor = head <= floor + 1e-6
            if not hasattr(self, '_ed_guard_events'):
                self._ed_guard_events = []
            self._ed_guard_events.append({'event': 'release_feasibility',
                'step': int(self._ab_step+1), 'initial_speed_kmh': head*3.6,
                'at_floor': bool(at_floor), 'trace_path': str(trace_path), **result})
            print(f'release_probe end feasible={result["feasible"]} reason={result["reason"]}', flush=True)
            if not result['feasible'] and not at_floor:
                delayed_gate = max(floor*3.6, head*3.6-self.AB_SUPPRESS_MARGIN_MPS*3.6)
                self._release_guard_retry_kmh = delayed_gate
            else:
                # Failed at the existing floor is an explicit infeasible candidate,
                # never permission to lower that floor or retain AB indefinitely.
                self._release_guard_retry_kmh = None
    try:
        if delayed_gate is not None:
            self.cyclic_release_kmh = delayed_gate
        return _guard_base_action(self, train_env, rl_actions, *args, **kwargs)
    finally:
        self.cyclic_release_kmh = original_release

MultiLocoController.get_action_decomposed = _guarded_release_action
