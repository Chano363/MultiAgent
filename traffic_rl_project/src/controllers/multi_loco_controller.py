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
        # 【ADR-060 限速逐段联动】循环制动触发裕量（km/h）：触发上限 =
        # min(既有触发门, 分段限速 − margin)。仅 env 暴露 line_limit_lookup_kmh
        # （剖面带限速表）时生效；恒坡等无表剖面自动回退旧行为（零回归）。
        cyclic_trigger_margin_kmh: float = 5.0,
        cyclic_ab_upgrade_kmh: float = None,
        cyclic_ab_upgrade_notch: str = 'service',
        ed_release_coordination: bool = False,
        ed_release_hold_s: float = 50.0,
        ed_release_boost_kn: float = 900.0,
        # 【2026-11-08 ED-AB 到位联动】循环制动期，当全列 AB 实际到位率
        # ≥ ed_floor_ab_ready_ratio 时把 ED 恒持下限由 CYCLIC_ED_FLOOR_KN
        # 抬到 ed_floor_ab_ready_kn；其余时段保持 CYCLIC_ED_FLOOR_KN。
        # 默认关 = 零回归。ED 是电制动力矩，不新增 AB 源、不触碰充风门；
        # 抬高后的请求仍受 downstream 车钩力安全层与动力学粘着/功率饱和约束。
        ed_floor_ab_ready: bool = False,
        ed_floor_ab_ready_ratio: float = 0.9,
        ed_floor_ab_ready_kn: float = 400.0,
        ed_native_force_conversion: bool = False,
        ed_upgrade_ramp_s: float = 0.0,
        ed_upgrade_ramp_scale: float = 1.0,
        # C4 (ADR-052 diagnostic): multiply the ED recovery-rate ceiling while the
        # safety layer vetoes new AB sources. 1.0 = original behaviour.
        ed_veto_recovery_boost: float = 1.0,
        # C1 (ADR-053 diagnostic): delay the cyclic release transition by this many
        # seconds. 0.0 = original behaviour. Fleet may add a per-train stagger.
        cyclic_release_stagger_s: float = 0.0,
        # C3 (ADR-053 diagnostic): let the refill gate shorten with the clear gap.
        gap_aware_refill: bool = False,
        refill_gap_reference_m: float = 800.0,
        refill_gap_relax_max_s: float = 0.0,
        refill_gap_relax_span: float = 1.0,
        # C5 (ADR-053 diagnostic): follower speed must stay within tollerance of
        # the formation leader; excess is met by cutting traction then adding ED.
        follower_speed_conformance: bool = False,
        speed_conformance_tol_kmh: float = 1.8,
        speed_conformance_gain: float = 0.20,
        speed_conformance_max: float = 0.30,
        # C6 (ADR-054 diagnostic): when trains behind are braking (AB applied or
        # ED near zero) hold a minimum ED floor on this (leading) train for a
        # bounded window. Default off = no-op.
        leader_brake_feedforward: bool = False,
        leader_brake_ff_hold_s: float = 2.0,
        leader_brake_ff_duration_s: float = 10.0,
        leader_brake_ff_ed_low_frac: float = 0.20,
        leader_brake_ff_ed_floor_frac: float = 0.25,
        # ===== C 组 2026-11-08（列间速度收敛 + ED 撤除时序；默认关 = 零回归）=====
        # (a) ed_release_timing_guard：ED 撤除时序**状态约束**（同 ab_gate 的否决标志做法）。
        ed_release_timing_guard: bool = False,
        ed_release_guard_trigger_frac: float = 0.30,
        ed_release_guard_release_frac: float = 0.05,
        ed_release_guard_neighbor_full_frac: float = 0.80,
        ed_release_guard_level_frac: float = 0.50,
        ed_release_guard_hold_s: float = 20.0,
        # (b) speed_convergence_share：速度差协同收敛（前车减 ED + 后车加制动共同承担）。
        speed_convergence_share: bool = False,
        conv_share_tol_kmh: float = 1.8,
        conv_share_gain: float = 0.20,
        conv_share_max: float = 0.30,
        conv_share_lead_share: float = 0.50,
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
        self.ed_veto_recovery_boost = float(ed_veto_recovery_boost)
        if not np.isfinite(self.ed_veto_recovery_boost) or self.ed_veto_recovery_boost < 1.0:
            raise ValueError('ed_veto_recovery_boost must be finite and >= 1.0')
        # C1 / C3 / C5 (ADR-053 diagnostic switches; default values are no-ops).
        self.cyclic_release_stagger_s = float(cyclic_release_stagger_s)
        if not np.isfinite(self.cyclic_release_stagger_s) or self.cyclic_release_stagger_s < 0:
            raise ValueError('cyclic_release_stagger_s must be finite and nonnegative')
        self.gap_aware_refill = bool(gap_aware_refill)
        self.refill_gap_reference_m = float(refill_gap_reference_m)
        self.refill_gap_relax_max_s = float(refill_gap_relax_max_s)
        self.refill_gap_relax_span = float(refill_gap_relax_span)
        if self.refill_gap_reference_m <= 0 or self.refill_gap_relax_max_s < 0:
            raise ValueError('refill gap reference must be positive and relax must be nonnegative')
        self.follower_speed_conformance = bool(follower_speed_conformance)
        self.speed_conformance_tol_kmh = float(speed_conformance_tol_kmh)
        self.speed_conformance_gain = float(speed_conformance_gain)
        self.speed_conformance_max = float(speed_conformance_max)
        if (self.speed_conformance_tol_kmh < 0 or self.speed_conformance_gain < 0
                or self.speed_conformance_max < 0):
            raise ValueError('speed conformance parameters must be nonnegative')
        self._release_hold_steps = 0
        self._last_clear_gap_m = None
        self._last_leader_speed_kmh = None
        # C6 (ADR-054 diagnostic): bounded leading-train ED floor.
        self.leader_brake_feedforward = bool(leader_brake_feedforward)
        self.leader_brake_ff_hold_s = float(leader_brake_ff_hold_s)
        self.leader_brake_ff_duration_s = float(leader_brake_ff_duration_s)
        self.leader_brake_ff_ed_low_frac = float(leader_brake_ff_ed_low_frac)
        self.leader_brake_ff_ed_floor_frac = float(leader_brake_ff_ed_floor_frac)
        if (self.leader_brake_ff_hold_s < 0 or self.leader_brake_ff_duration_s < 0
                or not 0 <= self.leader_brake_ff_ed_floor_frac <= 1.0):
            raise ValueError('leader-brake feedforward parameters out of range')
        self._ff_hold_steps = 0
        self._ff_active_steps = 0
        self._previous_ed = None
        # ===== C 组 2026-11-08 (a) ED 撤除时序状态约束 =====
        # 实测坏局面（k3-MIN 全程 t≈1344–1443 s）：中列 ED=1.00、尾列 ED=0.00 且 AB=RELEASE
        # 持续 ~30 s，列间速度差 4–6 km/h 不收敛、净空按 1.2 m/s 单调收缩 → EBI 触发、
        # 上限放宽到 2250 kN，峰值被锁定。本开关做成**状态约束**（同 ab_gate 否决标志）：
        # 本列发生"撤 ED"事件（上一步 ED 均值 ≥ trigger、本步 ≤ release）且相邻列 ED
        # 仍 ≥ neighbor_full 时，否决这次全撤，按 level_frac 保住一档 ED，直到相邻列退出
        # 满 ED 或持有窗（hold_s）到期（有界，不锁死；到期后须真正退出制动才重新解锁）。
        # 只改本列 ED（电制动力矩，即时无延迟、不产生纵向冲动）：不新增 AB 源、
        # 不触碰充风门 / new_source_veto / 车钩力安全层（它们仍保有最终权限）。
        self.ed_release_timing_guard = bool(ed_release_timing_guard)
        self.ed_release_guard_trigger_frac = float(ed_release_guard_trigger_frac)
        self.ed_release_guard_release_frac = float(ed_release_guard_release_frac)
        self.ed_release_guard_neighbor_full_frac = float(ed_release_guard_neighbor_full_frac)
        self.ed_release_guard_level_frac = float(ed_release_guard_level_frac)
        self.ed_release_guard_hold_s = float(ed_release_guard_hold_s)
        if not 0.0 <= self.ed_release_guard_release_frac < self.ed_release_guard_trigger_frac <= 1.0:
            raise ValueError('ED release guard needs 0 <= release_frac < trigger_frac <= 1')
        if not 0.0 <= self.ed_release_guard_neighbor_full_frac <= 1.0:
            raise ValueError('ed_release_guard_neighbor_full_frac must be in [0,1]')
        if not 0.0 <= self.ed_release_guard_level_frac <= 1.0:
            raise ValueError('ed_release_guard_level_frac must be in [0,1]')
        if not np.isfinite(self.ed_release_guard_hold_s) or self.ed_release_guard_hold_s < 0:
            raise ValueError('ed_release_guard_hold_s must be finite and nonnegative')
        self._ed_guard_steps_left = 0
        self._ed_guard_ref = None
        self._ed_guard_armed = True
        self.ed_release_guard_veto_count = 0
        self.ed_release_guard_hold_steps = 0
        # ===== C 组 2026-11-08 (b) 速度差协同收敛 =====
        # C5 失败模式对照（ADR-053 C5）：C5 只动后车（先收牵引、再把 ED 拉成负值=牵引），
        # 实测结果是"只压后车、编队越跑越松"。本开关禁止单侧加刹：速度差超出 tol 时，
        # 校正量 u = min(gain·Δv, max) 按 conv_share_lead_share 显式分配——
        #   前车侧承担 lead_share·u（**只减 ED**，绝不新增 AB、绝不转成牵引）；
        #   后车侧承担 (1−lead_share)·u（加 ED 制动）。
        # 分配比例依据：ED 无延迟、不产生纵向冲动（电制动），AB 沿列以 ~250 m/s 传播
        # （1297 m 列约 5.2 s 才到尾部），故两端都只用 ED；等额 0.5 是最不任意的初值
        # （每侧扰动幅度减半，任一侧都不单独承担全部制动需求），参数留给 0.3–0.7 扫描。
        # 前车侧可减量受其当前 ED 限制，不足部分不转嫁给后车（防 C5 式过刹），只计数。
        self.speed_convergence_share = bool(speed_convergence_share)
        self.conv_share_tol_kmh = float(conv_share_tol_kmh)
        self.conv_share_gain = float(conv_share_gain)
        self.conv_share_max = float(conv_share_max)
        self.conv_share_lead_share = float(conv_share_lead_share)
        if (not np.isfinite(self.conv_share_tol_kmh) or self.conv_share_tol_kmh < 0
                or not np.isfinite(self.conv_share_gain) or self.conv_share_gain < 0
                or not np.isfinite(self.conv_share_max) or self.conv_share_max < 0
                or not 0.0 <= self.conv_share_lead_share <= 1.0):
            raise ValueError('speed convergence share parameters out of range')
        self.ed_conv_unmet_count = 0
        self.ed_conv_active_steps = 0
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
        # 【S2-v2 2026-11-12】绝对档位模式（get_action_notch）的两个新参数。
        # 属性默认值 = 旧行为/无害，env 侧按需覆盖；**不影响 get_action_decomposed 路径**。
        #   ed_zero_point：ED 映射 ed = clip(zero + 0.5·a, 0, 1) 的零点。0.5=中立；
        #                  0.77 = 对齐规则层 meanED(0.769)，避免起点欠电制动导致一开局飙车。
        #   ab_notch_hold_s：档位最短保持时间（秒）。AB 波传播 ≈90 s（张二田实测），
        #                  若允许每 1 s 改档，波未传完即变档 → 压缩/拉伸波反复叠加 →
        #                  峰值反升（S2 第 1 轮实测 1394 kN 的主因）。文献依据：
        #                  Tang2020（DSQ）明确约束 "locomotive notches and their change rates"。
        self.ed_zero_point = 0.5
        self.ab_notch_hold_s = 0.0
        self._ab_notch_state = [0.0] * self.num_locomotives
        self._ab_notch_step = [-10 ** 9] * self.num_locomotives
        # 【ADR-080】AB 释放迟滞带的状态：每台机车记录「物理不足判据最近成立时刻」
        #（原始步；-10**9 = 从未成立）。
        self._ab_phys_insuff_step = [-10 ** 9] * self.num_locomotives
        # 【V17 / 2026-11-13 探针】低速强制缓解兜底（默认关 = 零回归）。
        # 与"超速强制 SERVICE"对称的安全底线：速度逼近下限时不允许新增/保持 AB，
        # 否则 AB 可被一次施加到停车，而 loco_notch 无牵引通道 ⇒ 停车是吸收态
        # （V16 实测：列 1 单次施加 3133 s → 0 km/h → 列 0 追尾 2382 kN）。
        # 依据：杨辉2020「空气制动需要有充足的缓解时间与较大的缓解速度」、
        #       张二田2021「提高列车缓解速度…可降低纵向车钩力」⇒ 缓解由速度触发，不由时长触发。
        self.ab_low_speed_release = False
        self.ab_low_speed_margin_mps = 2.0 / 3.6
        # 【V18】ED 惰行通道开关（默认关；开则 rl=−1 → ED=0，见 get_action_notch 注释）
        self.ed_idle_action = False
        # 【W4-v3 / 2026-11-15】ED 零可达阈值（默认 None = 沿用 V18 旧映射）。
        # 语义：`ed_idle_action=True` 且该值为 (-1,0) 时，r ≤ 阈值 ⇒ ED=0；
        #       阈值 < r < 0 线性映射到 [0, zero]；r ≥ 0 不变。
        # 依据：W4-v2 12k 探针 `raw_ed` 最小 −0.814 ⇒ 旧映射结构性下限 0.143。
        # 阈值必须由配置给出（如 −0.8），不得在代码里拍脑袋；默认关 = 零回归。
        self.ed_idle_zero_action = None
        # 【W4-v21 / ADR-072】ED 级位增量限幅（默认 0 = 关，零回归）。
        # 语义：>0 时 RL 的 ED 输出先按既有映射得到"目标深度"，再限制每决策步
        #       实际 ED 深度变化 ≤ notches/20（20 级制动机，对标 Wang2023 的
        #       "级位增量 ±3 限幅"——增量动作使级位轨迹平滑，是其实车 −8.93%
        #       拉钩改善的间接通道；车钩力本身不进奖励）。
        self.ed_rate_limit_notches = 0.0
        self._ed_notch_state = None
        # 【ADR-074 / 2026-11-18 级位派生化】decompose='loco_notch_incr' 专用
        # （默认 0/关 = 旧路径零回归）。Wang2023 ②对标：动作 = 级位增量（单决策步
        # |Δn| ≤ notches/20，量级对标文献"级位限 ±12、单步变化限 3"），
        # **ED = 级位（派生）**，**AB 由级位越限派生（不再进动作空间）**——
        # ED→AB 交接由"两个独立指令的时序"退化为"级位越限的派生事件"，
        # 直接作用于诊断 §7 的"缓解—再施加—ED 交接相位差"瓶颈。
        # 文献锚：Wang2023 实车拉钩 −8.93%（间接平滑通道替代直接车钩罚）。
        self.notch_incr_rate_notches = 0.0        # >0 = 本模式启用（语义同 ed_rate_limit_notches）
        self.ab_derive_threshold = 0.5            # n ≥ 阈值 → 请求 AB on
        self.ab_derive_release_margin = 0.05      # n < 阈值 − margin → 释放（滞回防抖）
        self.ab_derive_notch_idx = 2              # 派生档位 = AB_NOTCH_LEVELS[2] = MIN(70 kPa)
        # 【ADR-076 待验证 2026-11-20：逐列 AB 派生阈值偏置，默认关 = 零回归】
        # 诊断 §19.13.3 的根因：规则基线与我们的策略跑在同一套 env 协调律上
        # （同一 LEAD_TAIL_OFFSET_MPS=+5、同一 _formation_ref_gap / leader 迁就 /
        # follower 追距），但规则基线拿到 gap_err 24.5 m + band 100%，
        # 而 nincr 拿 495 m ⇒ **H1 可解，不是物理不可行**。
        # 差异载体 = **AB 的逐列分配方向相反**：
        #   规则基线 ab_agent_steps = [10693, 1527, 1171]（领航 39% / 中尾 4~6%）
        #   我们 baseline           = [0.092, 0.138, 0.138]      （领航 9% / 中尾 14%）
        # 逐拍分解：领航 AB 在场时 pair0 几何速率 −0.437 m/s（收拢），
        # 而中/尾列 AB 在场时 pair1 速率 +1.17/+0.42 m/s（撑开）⇒
        # **让速义务必须落在领航列**（领航减速 ⇒ 后列追得上），
        # 落在后列上则后列自己慢下来 ⇒ 净空被撑开。
        # nincr 路径的 AB 由级位越限派生（ADR-074），逐列阈值相同 ⇒ 分配结构
        # 完全由 RL 的级位动作决定，无法表达"领航多带闸、后列少带闸"。
        # 本偏置把**派生阈值**逐列区分：领航列阈值下调（更早、更久请求 AB），
        # 后列列阈值上调（更少带 AB）⇒ 复刻规则基线的分配结构。
        # 只改 AB **请求**门限，不改 ED/AB 物理、不改动作面（仍 1 维级位增量）、
        # 不改奖励面、不改安全层 ⇒ 两侧物理同源；222 s 充风门与低速兜底全保留。
        self.ab_derive_threshold_lead = None      # 领航列 AB 派生阈值覆写（None=用默认）
        self.ab_derive_threshold_follower = None  # 后列列 AB 派生阈值覆写（None=用默认）
        # 【ADR-076 待验证 2026-11-20：ED 前馈浅化上限，默认 0 = 不启用 = 零回归】
        # 诊断 §19.17.3（路线级发现）：decompose 路线（规则在环）的 RL 投历史读数
        #   gap_err 41.78 m / band 100% / mean_ed 0.7693
        # 而 nincr 路线（现行第 6 投）gap_err 495.08 m / band 86% / mean_ed 0.9013
        #   —— 几何差 11.9 倍。机制定位（源码级）：
        #   `ed_grade_feedforward` 的 ED 前馈浅化**只在 decompose 路径被调用**
        #   （get_action_cyclic_braking L857 / get_action_decomposed L1067），
        #   `get_action_notch_incr`（nincr）**从不调用** ⇒ nincr 的 ED 只能由 RL
        #   单调积分推深 ⇒ 贴顶（0.9013）⇒ 缓解-再施加相位差大 ⇒ 既丢几何
        #   （ED 贴顶 ⇒ 后列被迫自己减速）又丢峰（冲击集中）。
        # 本开关把同一前馈反解（`_grade_feedforward_actions`：二分求维持速度
        # 所需的最小 ED 级位）作为 **RL 级位的上限**，使 ED 保持"浅"：
        #   · RL 仍可自由下探（缓解空间保留 ⇒ 相位差小）；
        #   · RL 不能把 ED 推过头贴顶（多余的制动力只会加剧纵向冲击）。
        # 不改动作面（仍 1 维级位增量）、不改物理、不改奖励面、不改安全层
        # ⇒ 两侧物理同源；属控制面改动 ⇒ 改轨迹 ⇒ 可零机时探针判。
        self.ed_feedforward_cap = 0.0            # >0：级位上限 = 前馈反解 ED × 该系数
        self.ed_feedforward_margin = 0.0         # 额外裕量（级位单位）
        # 【ADR-076 待验证 2026-11-20：ED 深度常数上限，默认 1.0 = 不启用】
        # 诊断 §19.17.4（路线级对照）：decompose 路线（规则在环）历史读数
        #   gap_err 41.78 m / band 100% / **mean_ed 0.7693**
        # 而 nincr 路线 gap_err 495.08 m / band 86% / **mean_ed 0.9013**（ED 贴顶）。
        # `ed_feedforward_cap` 在陡坡实测前馈反解 = 1.0（饱和）⇒ 封顶无效
        # （600 步冒烟：cap1.0 与 cap2.0 结果几乎相同）⇒ 需要一个**常数**上限
        # 才能把 ED 压到与 decompose 同等深度。这是把"ED 浅 ⇒ 缓解-再施加相位差
        # 小 ⇒ 几何与峰同时可控"从相关升级为干预实验的最小旋钮。
        # 纯参数 ⇒ 两侧物理同源；改轨迹 ⇒ 可零机时探针判。
        self.ed_notch_cap = 1.0                  # ED 级位上限（1.0 = 不限制）
        # 【ADR-076 待验证 2026-11-20：ED 上限的速度释放阀，默认 0 = 不启用】
        # 诊断 §19.19（整程读数）：ED 上限 0.85 ⇒ 几何发散速率 +0.255/+0.225 m/s
        #   → +0.046/+0.065 m/s（**5.6×/3.5× 改善，几何由发散转收敛**），
        #   但 peak 1093.9→1252.5、超限 167→4934 步、末段尾列速度上飘到 74.9 km/h
        #   （贴速度带上限 75）⇒ **代价机制 = ED 制动被限 ⇒ 减速不足 ⇒ 速度上飘
        #   ⇒ 贴带上限 ⇒ 车钩力/超限恶化**（超限集中在 t≥2000 s）。
        # 本阀：当速度 ≥ 释放阀值时**放开 ED 上限**（回到 1.0）⇒ 允许策略正常减速
        # ⇒ 抑制速度上飘；其余区段仍受上限约束（几何收敛收益保留）。
        self.ed_notch_cap_release_kmh = 0.0     # >0：速度 ≥ 该值(km/h)时放开上限
        # 【ADR-076 待验证 2026-11-20：ED 上限的渐进式斜坡，默认 0 = 不启用】
        # 诊断 §19.19.6（整程实测）：**阶跃式释放阀（速度≥72 放开上限）有害**——
        #   cap0.75+valve72：peak 961.9→**1237.7**、超限 [0,0,0]→[0,871,983]、
        #   band 0.8318→0.8266 ⇒ 领航从浅 ED **突跳**到深 ED ⇒ 相位差冲击大 ⇒ 峰涨。
        #   ⇒ "放开 ED 来减速"在控制面上是死的（同一动作的三面，§19.7 三轴耦合
        #   在 ED 维度上的再现：加深 ED 能减速 ⇒ 但峰涨 ⇒ band 与峰互斥）。
        # 本斜坡改为**连续放宽**：上限(v) = min(1, cap + slope·max(0, v − v_from))，
        # 速度越高允许越深 ED，但**变化率受限** ⇒ 无阶跃冲击 ⇒ 抑制超速跑分的
        # 同时不引入新的相位差冲击。纯参数 ⇒ 零机时可判。
        self.ed_notch_cap_slope = 0.0           # 每 km/h 放宽的级位量（0 = 不启用）
        self.ed_notch_cap_slope_from_kmh = 70.0 # 斜坡起点速度
        # 【ADR-076 待验证 2026-11-20：物理触发式 AB 兜底，默认关 = 零回归】
        # 诊断 §19.14.2 的核心发现：规则基线与我们的策略**同物理、同协调律**，
        # 但规则基线 gap_err 24.5 m / band 100%，我们 654 m ⇒ H1 可解。
        # 唯一的系统性差异 = **AB 的触发源**：
        #   规则基线（decompose）：`_ed_ab_price(train_env) < 0.99` ⇒ 引 AB 兜底
        #        （物理触发；逐列 ed_avail 不同 ⇒ 领航在陡坡高速段 AB 率天然最高
        #          ⇒ 减速责任落在领航 ⇒ 几何收敛；实测领航 39% / 中尾 4~6%）
        #   我们 nincr（ADR-074）：级位越限派生（策略派生；分配结构由 RL 决定，
        #        无任何机制保证让速义务落在领航 ⇒ 实测领航 9% / 中尾 14%，方向相反）
        # 本开关把**物理触发**接入 nincr：当本列 ED 物理上不足以维持速度时，
        # 即便级位未越限也请求 AB（**只做加法**：多一个请求理由，绝不绕开
        # 222 s 充风门 / 低速强制缓解 / 车钩力源头 veto 等任何既有安全门）。
        # ED 仍由级位派生（动作面 1 维不变，Wang2023 对标保持），
        # AB 变为「级位越限 **或** 物理不足」双通道。
        self.ab_physical_trigger = False           # > 开启：ed_avail 不足时也请求 AB
        self.ab_physical_avail_threshold = 0.99    # 触发阈值（同规则基线口径）
        # 【ADR-076 待验证 2026-11-20：AB 保持/释放改用「当前实际坡度」的物理判据】
        # 诊断 §19.21 的判别结论 + 今早物理触发失败的死因：
        #   · `ed_avail = F_ed / F_req` 中 **F_req 取「全剖面最陡下坡」**
        #     （`_ed_ab_price`：`steepest_down = max(0, -min(grades))`）⇒ **位置无关**，
        #     且 F_ed = P/v 随速度降低而增大 ⇒ **低速时 ed_avail 反而 ≥ 1 ⇒ 误判
        #     「ED 已够用」⇒ 释放 AB ⇒ 222 s 充风门锁死 ⇒ 陡坡拖停**
        #     （该机制整程 peak 1842.4 / 尾列末速 0.0 的死因，§19.14–§19.15）。
        #   · 而陡坡上**纯 ED 物理上无法平衡**：沿坡分力 ≈1163 kN > 单台机车
        #     粘着上限 ≈645 kN（§19.21.3 核算）⇒ AB 是物理刚需，释放代价极高。
        # 本开关把「物理不足」判据换成**位置相关**的 `_ed_cannot_hold_speed`
        # （按各车实际坡度算 grade_force − resistance vs electric_capacity）：
        #   · 陡坡（含低速）⇒ 仍判「ED 不够」⇒ **保持 AB ⇒ 不拖停**；
        #   · 进缓坡 ⇒ 判「ED 够用」⇒ **允许释放** ⇒ 释放次数少 ⇒ 222 s 锁死空窗少
        #     ⇒ 超速跑分减少 ⇒ band 回升。
        # 纯控制面改动（不改动作面/物理/奖励面/安全层）⇒ 两侧物理同源、零机时可判。
        self.ab_release_by_local_grade = False
        # 【ADR-081 待验证 2026-11-20：ED 深度上限随「追及需求」放宽】
        # 依据（诊断 §19.29.2 / §19.30.3–§19.30.4）：中列超限是「急追 + 无减速」型
        # （超限时 v_rel = +12.50 km/h、dgap = −3.40 m/s、中列 AB 在场 0.000）
        # ⇒ 结构性矛盾 = 「ED 深度上限 0.75（压峰）」× 「中列追及减速需求」
        # ⇒ 机制：追及压力大（v_rel ≥ 阈值）时把 ED 上限放宽到 `ed_cap_relaxed`，
        #    不追及时维持原上限 ⇒ 常态的峰保护不变，追及时有减速能力。
        # ⚠️ 只改 ED 级位上限的生效值；不改施加来源/不改 AB 派生/不改安全链。
        # 默认 0.0 = 不启用 = 逐位零回归。
        self.ed_cap_rel_speed_kmh = 0.0
        # 【ADR-081】env 侧每步写入的「本列相对前列速度差」(km/h)；
        # 领航列写 -inf（无前列 ⇒ 永不触发放宽）。
        self._ed_cap_rel_speed_now = float('-inf')
        self.ed_cap_relaxed = 1.0
        self._ed_cap_col_index = -1
        # 【ADR-080 待验证 2026-11-20：AB 释放迟滞带】
        # 依据（诊断 §19.29.2–§19.29.3）：中列超限是「制动力不足」型
        # （超限时 v01 = −12.50 km/h、中列 AB 在场率 0.000 vs 全程 0.265）
        # ⇒「该用 AB 时 AB 缺席」与「AB 用太久 ⇒ 相位差累积」是同一根轴两端。
        # 语义：已施加态下，若物理不足判据在最近 N 秒内曾成立，则继续保持 AB
        # （需求消失后仍维持一小段）⇒ 避免「需求一消失即释放」造成反复施加-释放。
        # ⚠️ 只改「释放时机」，不改施加来源、不改档位保持、不改 222 s 充风门、
        #    不改低速强制缓解、不改车钩 veto ⇒ 安全链不放松。
        # 默认 0.0 = 不启用 = 逐位零回归。
        self.ab_release_hysteresis_s = 0.0
        # 【P1 候选 / ADR-074 附段三「坡度门解耦」，2026-11-19；默认关 = 零回归】
        # 语义：把「缓解 AB」的触发条件从"级位下探穿释放阈值"解耦为"坡度进入缓坡段"。
        # 已施加态即便级位下探，只要本列队首坡度仍陡（≤ 门限），就不许释放 AB——
        # 与规程一致（赵紫宁2022「尽量在缓坡段缓解」+ 张二田2021「带闸到缓坡处缓解」）。
        # 门限锚：张二田2021「列车全部处于 −7 ‰以下缓坡」(fulltext:353) ⇒ 默认 −7.0 ‰。
        # 只加一道释放否决（RL 无法关闭，与低速强制缓解同层），不改奖励面、不改物理、
        # 不动 222 s 充风门数值。坡度缺失（mock/恒坡无 grade 属性）时门自动失效 = 零回归。
        self.ab_grade_release_gate = False
        self.ab_grade_release_permille = -7.0
        # 【A-4 / 诊断 §8，2026-11-19；默认关 = 零回归】P1 第二版两个候选开关。
        # A-4a 变坡点门：把级位释放的坡度门从"绝对坡度 ≤ 门限"改为"坡度较上一步回升
        #   ≥ ab_grade_rebound_permille（变缓事件）"——49.6 km 真实剖面变缓点锚
        #   （K25013 −8.9→−1.5 回升 7.4‰；grade_profile.py:418）。开启时覆盖
        #   ab_grade_release_gate 的绝对判断（二者互斥，A-4a 优先）。
        # A-4b 低速兜底坡度门控：低速强制缓解触发从"v≤v_min+2"改为
        #   "v≤v_min+2 且（坡度已变缓 或 v≤ab_low_speed_stop_kmh）"——
        #   陡坡低速继续带闸，直到变缓点或逼近停车红线。须配 v_stop 防 V18-b 拖停。
        #   具体数值 Δ=3‰ / v_stop=35 km/h 是待探针检验的候选值，非文献锚。
        self.ab_grade_rebound_gate = False
        self.ab_grade_rebound_permille = 3.0
        self.ab_low_speed_grade_gate = False
        self.ab_low_speed_stop_kmh = 35.0
        self._prev_grade_permille = None
        # 【AB 物理释放判据（诊断 §14，2026-11-19）；默认关 = 零回归】
        # 语义：已施加态的**释放**判据不再由「级位下探」触发，而由「物理上 ED 已足够」
        # 触发 —— ed_avail = F_ed/F_req（_ed_ab_price，物理化口径）≥ 门限才允许释放；
        # 物理仍不足时保持 AB on。判据与规则基线同源（decompose 基线 L701 用
        # `ed_avail >= 0.99` 才不引 AB），但**释放权仍属安全层**（低速强制缓解 v≤42
        # 仍可强制释放，222 s 充风门不动）。
        # 动机（一手量化，诊断 §14）：nincr 轨迹上 ed_avail 恒 ≈0.51 < 1（ED 物理不足、
        #   AB 是刚需），但 AB on:off ≈ 1:9.6、86% 时间被 222 s 充风门锁死 ⇒ ED 单源空窗
        #   ⇒ ED 贴顶（meanED 0.900）⇒ band 崩（84.97%）。
        # 风险（须整程探针判）：AB 长时间不释放 ⇒ 拖停（V17/V18-b 铁证）。
        self.ab_release_by_physical = False
        self.ab_release_avail_threshold = 0.99
        # 【AB 释放速度门（诊断 §14，2026-11-19）；默认关 = 零回归】
        # 语义：已施加态的释放判据由「级位下探」改为「速度门」——v ≤ 门限才允许释放。
        # 门限默认 50 km/h = 主配置 `cyclic_release_kmh`（**未调参值**；诊断 L2386 明确
        # GA 那批 54.96/56/52 已作废，规则基线唯一身份以未调参 50 为准）。
        # 机理（一手量化，诊断 §14）：nincr 现状 AB on:off ≈ 1:9.6、86% 时间被 222 s
        # 充风门锁死（每次 on 仅 23–31 s）⇒ ED 单源空窗 ⇒ ED 贴顶 ⇒ band 崩。
        # 速度门让 AB on 段与 ED 级位轨迹**解耦**（ED 可自由上下探而不动 AB 状态），
        # 与 A-4a/b 的「加否决」方向相反（那两条否决了正确的级位释放路径、留下最坏的
        # 低速兜底路径 ⇒ 拖停/暴峰）。
        # 风险：AB 持续到 v≤50 ⇒ 须整程探针判末速/是否跑完全程（V17/V18-b 拖停铁证）。
        # 低速强制缓解（v ≤ v_min+2）仍可强制释放（安全底线，不受本门影响）。
        self.ab_release_speed_gate = False
        self.ab_release_speed_kmh = 50.0
        # 【AB 施加门控（诊断 §16，2026-11-19）；默认 0 = 不启用 = 零回归】
        # 语义：**低速段不新增 AB 源**——速度低于 `ab_apply_speed_min_kmh` 时，即使
        # 级位越限请求 AB（want_on=True）也不落地（ab=0，请求被搁置但不改变 AB 状态）。
        # 动机（一手，诊断 §16）：释放速度门整程三变体中，**全程峰 1,199.4 kN 全部来自
        # 起步段 t=26.2 s、尾列**——起步时速度已 60 km/h > 释放门限 50/56 ⇒ AB 立即施加
        # ⇒ 起步瞬态冲高；而 gate56 在真实主峰窗（1,100–1,300 s）尾列峰 838.9 kN
        # **低于 baseline 928.1**（−89.2）⇒ 机制本身有效、收益被起步瞬态吃掉。
        # 物理依据：`ed_avail` 在低速段更高（ED 功率富余 ⇒ 物理上更不需要 AB）。
        # 与释放门控**方向相反**（释放门控管"何时放"，本门控管"何时加"），互不替代。
        # 风险：低速段不施加 AB ⇒ 若该段物理确需 AB 会更差 ⇒ 须整程探针判
        #（判据：起步峰回落 ≤ baseline 853、主峰窗保持 838.9 量级改善、band ≥90%、
        #  超限步回落至 ≲baseline 量级、零穿透、跑完全程）。
        self.ab_apply_speed_min_kmh = 0.0
        # 【W4-v4 / 2026-11-15】近上限 AB 充风门旁路（默认关 = 零回归）。
        # 语义：速度贴近有效上限且 RL 想施加 AB 时，绕过 222 s 充风门控。
        # 依据：W4-v3 12k 归因显示 ATP 过触发主体是规则 C 逐车超速；若门控
        #       在近上限拒绝新增 AB，会让 RL 事后无制动可用。
        self.ab_high_speed_bypass_gate = False
        # 【W4-v5 / 2026-11-15】近上限分级制动（默认关 = 零回归）。
        # 语义：仅当 `ab_high_speed_bypass_gate=True` 且速度贴近但未越过有效上限时，
        #       把兜底档从 SERVICE 降到 MIN；已越过有效上限仍强制 SERVICE。
        # 依据：W4-v4 12k 归因显示列 1/2 的近上限 SERVICE 与惰行叠加是车钩超限主因。
        self.ab_near_limit_min_brake = False
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
        # 【ADR-060】分段限速联动触发裕量：km/h 原名属性必须保留——
        # diagnose_low_level_control 的 frozen-controller 复原按
        # inspect.signature 参数名逐个 getattr(controller, name) 回注，
        # 缺原名会让归档复现直接 AttributeError。
        self.cyclic_trigger_margin_kmh = float(cyclic_trigger_margin_kmh)
        self.cyclic_trigger_margin_mps = float(cyclic_trigger_margin_kmh) / 3.6
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
        # 【2026-11-08】AB 到位后抬升 ED 下限（诊断开关；默认关 = 零回归）。
        self.ed_floor_ab_ready = bool(ed_floor_ab_ready)
        self.ed_floor_ab_ready_ratio = float(ed_floor_ab_ready_ratio)
        self.ed_floor_ab_ready_kn = float(ed_floor_ab_ready_kn)
        if not (0.0 <= self.ed_floor_ab_ready_ratio <= 1.0):
            raise ValueError('ed_floor_ab_ready_ratio must be in [0,1]')
        if self.ed_floor_ab_ready_kn <= 0.0:
            raise ValueError('ed_floor_ab_ready_kn must be positive')
        # 本步实际使用的循环期 ED 下限（kN），供诊断归档核对分支是否真进入。
        self._active_ed_floor_kn = self.CYCLIC_ED_FLOOR_KN
        self._ed_hold_steps = 0
        self._ab_step = 0
        self._ab_on = [False] * self.num_locomotives
        # 初值 -1e9 保证首次允许（充风/保持门不会拦第一个源/第一次释放）
        self._ab_last_release_step = [-10 ** 9] * self.num_locomotives
        self._ab_last_apply_step = [-10 ** 9] * self.num_locomotives
        # 门控拒绝计数（诊断用）
        self.ab_refill_veto_count = 0
        self.ab_hold_veto_count = 0
        # 【ADR-074 级位派生化】每机车级位状态 [0,1]，0=惰行；仅 loco_notch_incr 模式使用
        self._notch_level = None
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

    def _refill_gate_s(self) -> float:
        """C3 (ADR-053 diagnostic): refill gate that shortens with the clear gap.

        The 222 s anchor (ab_min_refill_s) is **never** raised or removed; when the
        switch is on and the fleet supplies ``formation_clear_gap_m``, the gate may
        shorten by at most ``refill_gap_relax_max_s`` proportional to the gap excess
        over ``refill_gap_reference_m`` (capped by ``refill_gap_relax_span``).
        Defaults (switch off / relax 0 / gap unknown) return the anchor unchanged.
        """
        if not self.gap_aware_refill or self.refill_gap_relax_max_s <= 0:
            return self.ab_min_refill_s
        gap = self._last_clear_gap_m
        if gap is None or not np.isfinite(gap):
            return self.ab_min_refill_s
        ratio = max(0.0, (gap - self.refill_gap_reference_m) / self.refill_gap_reference_m)
        ratio = min(ratio, self.refill_gap_relax_span)
        return max(0.0, self.ab_min_refill_s - self.refill_gap_relax_max_s * ratio)

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
            if (self._ab_step - self._ab_last_release_step[i]) * self.dt >= self._refill_gate_s():
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
        # 【ADR-060 限速逐段联动】有分段限速表（env 暴露 line_limit_lookup_kmh）→
        # 循环制动触发上限随头车位置联动（限速 − cyclic_trigger_margin_kmh）；
        # 无表/查表 None → 不联动（恒坡等零回归）。
        _lookup = getattr(train_env, 'line_limit_lookup_kmh', None)
        if _lookup is not None:
            _lv = _lookup(float(train_env.dynamics.pos[0]))
            if _lv is not None:
                ceiling = min(ceiling,
                              max(0.0, _lv / 3.6 - self.cyclic_trigger_margin_mps))
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
        # C1 (ADR-053 diagnostic, default 0 s = no-op): hold the release transition
        # for the staggered delay so followers keep braking while the leader's
        # release wave is still travelling backwards.
        release_delay_s = self.cyclic_release_stagger_s + float(
            getattr(train_env, 'formation_release_delay_s', 0.0) or 0.0)
        release_delay_steps = (int(round(release_delay_s / self.dt))
                               if release_delay_s > 0 else 0)
        if vel >= trigger_mps or max_vel >= formation_ceiling:
            self._cyclic_braking = True
            self._release_hold_steps = 0
        elif vel <= release_mps and max_vel <= release_ceiling:
            if release_delay_steps:
                self._release_hold_steps += 1
                if self._release_hold_steps >= release_delay_steps:
                    self._cyclic_braking = False
            else:
                self._cyclic_braking = False
        else:
            self._release_hold_steps = 0
        # 【ADR-053 C1】延迟期内保持原制动指令（cyclic 仍为 True），不额外放宽任何门限。
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
            # 【2026-11-08】AB 全列到位（≥ 阈值）时可抬到 ed_floor_ab_ready_kn。
            ed_floor = (self._ed_frac_for_total_kn(train_env, self._cyclic_ed_floor_kn(train_env))
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

    def _ab_arrival_ratio(self, train_env) -> float:
        """全列空气制动实际到位率：生效档位非 RELEASE 的车数 / 总车数。

        只读动力学当前生效档位（波前已到达并激活的车辆才算到位），
        不改任何 AB 状态、不推进波速传播。
        """
        state = train_env.dynamics.air_brake_state()
        if state is None or len(state) == 0:
            return 0.0
        applied = sum(1 for notch in state if notch != AirBrakeNotch.RELEASE)
        return float(applied) / float(len(state))

    def _cyclic_ed_floor_kn(self, train_env) -> float:
        """循环制动期的 ED 恒持下限（kN）。

        默认返回 CYCLIC_ED_FLOOR_KN（300 kN）。仅当 ed_floor_ab_ready 开启
        且 AB 到位率 ≥ 阈值时抬到 ed_floor_ab_ready_kn；本步实际取值写入
        _active_ed_floor_kn 供诊断归档核对分支是否真进入。
        """
        floor_kn = self.CYCLIC_ED_FLOOR_KN
        if self.ed_floor_ab_ready and self.ed_release_coordination:
            if self._ab_arrival_ratio(train_env) >= self.ed_floor_ab_ready_ratio:
                floor_kn = self.ed_floor_ab_ready_kn
        self._active_ed_floor_kn = floor_kn
        return floor_kn

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
            floor = self._ed_frac_for_total_kn(train_env, self._cyclic_ed_floor_kn(train_env))
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
        # C4 (ADR-052 diagnostic, default 1.0 = bit-identical): while the safety
        # layer vetoes new AB sources, let ED rise toward its own ceiling (capped
        # at 1.0). AB admission, refill gate and the coupler safety layer are
        # untouched; ED is not an AB source, so no AB constraint is bypassed.
        if self.ed_veto_recovery_boost > 1.0 and ab_add_vetoed:
            final[:, 0] = np.minimum(final[:, 0] * self.ed_veto_recovery_boost, 1.0)
        # C5 (ADR-053 diagnostic, default off): keep the follower within
        # |v_self − v_leader| <= tol. Excess closes traction first, then adds ED,
        # capped at the existing ED authority; AB admission / refill gate / coupler
        # safety layer keep final authority (no bypass).
        if self.follower_speed_conformance:
            leader_kmh = getattr(train_env, 'formation_leader_speed_kmh', None)
            if leader_kmh is not None and np.isfinite(leader_kmh):
                excess_kmh = (float(train_env.dynamics.vel[0]) * 3.6
                              - (float(leader_kmh) + self.speed_conformance_tol_kmh))
                if excess_kmh > 0:
                    final[:, 0] = np.minimum(final[:, 0], 0.0)   # 先收回牵引
                    delta = min(self.speed_conformance_gain * excess_kmh,
                                self.speed_conformance_max)
                    final[:, 0] = np.maximum(final[:, 0] - delta, -1.0)
        # C6 (ADR-054 diagnostic, default off): while trains behind are braking
        # (AB applied) or coasting with near-zero ED, hold a bounded minimum ED
        # floor on this leading train so it does not free-wheel ahead of a
        # braking rear formation. ED only; AB admission / refill gate / coupler
        # safety layer keep final authority.
        if self.leader_brake_feedforward:
            rear_braking = bool(getattr(train_env, 'formation_rear_braking', False))
            rear_ed = getattr(train_env, 'formation_rear_ed_frac', None)
            trigger = rear_braking or (
                rear_ed is not None and float(rear_ed) < self.leader_brake_ff_ed_low_frac)
            self._ff_hold_steps = self._ff_hold_steps + 1 if trigger else 0
            hold_steps = int(round(self.leader_brake_ff_hold_s / self.dt))
            if hold_steps == 0 or self._ff_hold_steps >= hold_steps:
                self._ff_active_steps = int(round(
                    self.leader_brake_ff_duration_s / self.dt))
            if self._ff_active_steps > 0:
                final[:, 0] = np.maximum(
                    np.minimum(final[:, 0], -self.leader_brake_ff_ed_floor_frac), -1.0)
                self._ff_active_steps -= 1
        # ===== C 组 2026-11-08 (a) ED 撤除时序状态约束（默认关 = 零回归）=====
        # 只在本步"正在撤 ED"（上一步 ED 高、本步跌到近零）且相邻列仍满 ED 时否决，
        # 保住 level_frac 档 ED；相邻列退出满 ED 或持有窗到期即解除。AB 侧一律不动。
        if self.ed_release_timing_guard and self.num_locomotives:
            prev_mean = (float(np.mean(self._previous_ed))
                         if self._previous_ed is not None else 0.0)
            cur_mean = float(np.mean(final[:, 0]))
            # 真正退出制动（ED 已落在近零带）→ 解锁下一次撤除事件（防到期后原地重触发）
            if prev_mean < self.ed_release_guard_trigger_frac:
                self._ed_guard_armed = True
            neighbor = getattr(train_env, 'formation_neighbor_ed_frac', None)
            neighbor_full = (neighbor is not None and np.isfinite(neighbor)
                             and float(neighbor) >= self.ed_release_guard_neighbor_full_frac)
            if self._ed_guard_steps_left > 0:
                if not neighbor_full:
                    self._ed_guard_steps_left = 0      # 相邻列已退出满 ED → 立即放行
                else:
                    self._ed_guard_steps_left -= 1
                    final[:, 0] = np.maximum(
                        final[:, 0],
                        self._ed_guard_ref * self.ed_release_guard_level_frac)
                    self.ed_release_guard_hold_steps += 1
            elif (self._ed_guard_armed and neighbor_full
                    and prev_mean >= self.ed_release_guard_trigger_frac
                    and cur_mean <= self.ed_release_guard_release_frac):
                self._ed_guard_ref = np.asarray(self._previous_ed, dtype=float).copy()
                self.ed_release_guard_veto_count += 1
                self._ed_guard_steps_left = int(round(self.ed_release_guard_hold_s / self.dt))
                if self._ed_guard_steps_left > 0:
                    self._ed_guard_steps_left -= 1
                    final[:, 0] = np.maximum(
                        final[:, 0],
                        self._ed_guard_ref * self.ed_release_guard_level_frac)
                    self.ed_release_guard_hold_steps += 1
                else:
                    self._ed_guard_armed = False       # hold_s=0：只记录否决，不保持
        # ===== C 组 2026-11-08 (b) 速度差协同收敛（默认关 = 零回归）=====
        # 同一列可能同时扮演两个角色（夹在两列之间）：对后车它是前车（减 ED），
        # 对前车它是后车（加 ED）。两端同时动作，杜绝 C4 式"只压一侧"。
        # 只动 ED：不新增 AB 源、不改档位、不碰紧急（紧急是 EBI 的结果，不是控制手段）。
        if self.speed_convergence_share and self.num_locomotives:
            self_kmh = float(train_env.dynamics.vel[0]) * 3.6
            front_kmh = getattr(train_env, 'formation_leader_speed_kmh', None)
            rear_kmh = getattr(train_env, 'formation_rear_speed_kmh', None)
            active = False
            if front_kmh is not None and np.isfinite(front_kmh):
                excess = self_kmh - float(front_kmh) - self.conv_share_tol_kmh
                if excess > 0.0:
                    add = ((1.0 - self.conv_share_lead_share)
                           * min(self.conv_share_gain * excess, self.conv_share_max))
                    room = float(np.mean(np.clip(1.0 - np.maximum(final[:, 0], 0.0), 0.0, 1.0)))
                    if add > room:
                        self.ed_conv_unmet_count += 1
                    final[:, 0] = np.minimum(np.maximum(final[:, 0], 0.0) + add, 1.0)
                    active = True
            if rear_kmh is not None and np.isfinite(rear_kmh):
                excess = float(rear_kmh) - self_kmh - self.conv_share_tol_kmh
                if excess > 0.0:
                    cut = (self.conv_share_lead_share
                           * min(self.conv_share_gain * excess, self.conv_share_max))
                    # 只减 ED，绝不把 ED 转成牵引（C5 的失败点之一）；减到 0 为止。
                    if cut > float(np.mean(np.maximum(final[:, 0], 0.0))):
                        self.ed_conv_unmet_count += 1
                    final[:, 0] = np.maximum(np.maximum(final[:, 0], 0.0) - cut, 0.0)
                    active = True
            if active:
                self.ed_conv_active_steps += 1
        self._last_clear_gap_m = getattr(train_env, 'formation_clear_gap_m', None)
        self._last_leader_speed_kmh = getattr(train_env, 'formation_leader_speed_kmh', None)
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
    # 主接口 4【S2 / ADR-065 绝对档位】RL 直接给 ED 深度 + AB 减压档位
    # ------------------------------------------------------------------ #
    # 4 档编码（沿用 AirBrakeNotch 现有物理，不改 physics）：
    #   0.0  → RELEASE   （缓解，0 kPa）
    #   -0.05 → CYCLIC   （50 kPa，朔黄表3 循环档）
    #   -0.20 → MIN      （70 kPa，最小常用）
    #   -0.40 → SERVICE  （140 kPa，常用全制动）
    # 与 get_action_decomposed 的本质区别：**不调用 get_action_cyclic_braking**，
    # 即 RL 自己决定「何时施加 / 何时缓解 / 用哪一档」，规则层不再排程。
    # 保留的安全边界（不可被 RL 关闭）：
    #   ① _ab_gate 充风/保持门控（222 s 纪律）；② 超速兜底强制 SERVICE；
    #   ③ 车钩力源头 veto 由子环境 train_env.safety 执行（本方法不绕过）。
    AB_NOTCH_LEVELS = (0.0, -0.05, -0.20, -0.40)

    def get_action_notch(
        self, train_env, rl_actions, v_max: float = 80.0 / 3.6,
        v_min: float = 40.0 / 3.6, v_max_adj: float = 0.0, v_min_adj: float = 0.0,
    ) -> np.ndarray:
        """S2：RL 绝对档位控制 → (num_loco, 2) 的 [ed_cmd, ab_frac]。

        Args:
            rl_actions: (num_loco, 2) ∈[-1,1]²。
                [:,0] ed_cmd  = 电制动深度（正=电制动，负=牵引），直接作为 ED 指令；
                [:,1] ab_frac = 空气制动"施加程度"（0=缓解，-1=满制动），量化到 4 档。
        Returns:
            final (num_loco, 2)：第 0 列 ED、第 1 列 AB（负=施加，语义与现有通道一致）。
        """
        self._ab_step += 1
        rl = np.asarray(rl_actions, dtype=float).reshape(self.num_locomotives, 2)
        n = self.num_locomotives
        final = np.zeros((n, 2), dtype=float)
        vel = float(train_env.dynamics.vel[0])
        vmax_eff = float(v_max) + float(v_max_adj)

        for k in range(n):
            # ED：绝对深度，映射 ed = clip(zero + 0.5·rl, 0, 1)，default zero=0.5。
            # zero 可被 env 覆盖（v2 用 0.77 对齐规则层 meanED，避免起点欠电制动）。
            # 长大下坡无需牵引，故 ED 只取非负（不保留负=牵引语义）。
            # 【V18 / 2026-11-13】ED 惰行通道（默认关 = 零回归）。
            # 关：ed = zero + 0.5·rl ⇒ rl=−1 仍剩 0.27 电制动，**无惰行能力**。
            #      V17 实测：崩溃时刻三列 AB 全关、速度 6.7/9.5 km/h，ED 仍 0.76
            #      ⇒ 停车是电制动在低速段拖停的，不是 AB。
            # 开：非对称映射 rl=−1→0（惰行）/ rl=0→zero（中性点不变）/ rl=+1→1.0，
            #     使速度下限可恢复。依据：杨辉2020 循环制动 = 50 kPa 初制动 + 惰行；
            #     Zhang2024 的 RL 动作同为"电制动档 + AB 档"，无牵引维度。
            # 【W4-v3 / 2026-11-15】`ed_idle_zero_action` 修"名义惰行"缺口：
            #     V18 的 `zero·(1+r)` 只有 r=−1 才到 0，而 tanh 有限动作到不了 −1；
            #     W4-v2 实测 ED 下限 0.143。此阈值让 r ≤ 阈值时真正给 ED=0。
            _r = float(rl[k, 0])
            if self.ed_idle_action:
                if self.ed_idle_zero_action is not None:
                    _zr = float(self.ed_idle_zero_action)
                    if not (-1.0 < _zr < 0.0):
                        raise ValueError(
                            "ed_idle_zero_action must lie in (-1, 0); "
                            f"got {_zr}")
                    if _r <= _zr:
                        _ed = 0.0
                    elif _r < 0.0:
                        _ed = self.ed_zero_point * (_r / _zr)
                    else:
                        _ed = (self.ed_zero_point
                               + (1.0 - self.ed_zero_point) * _r)
                else:
                    _ed = (self.ed_zero_point * (1.0 + _r) if _r < 0
                           else self.ed_zero_point + (1.0 - self.ed_zero_point) * _r)
            else:
                _ed = self.ed_zero_point + 0.5 * _r
            # 【W4-v21 / ADR-072】ED 级位增量限幅（默认关 = 零回归）。
            # 对既有映射的"目标深度"先 clip 到 [0,1]，再限制每决策步变化
            # |Δed| ≤ notches/20，内部积分（状态即上一步实际 ED）；首步从
            # 起点级位 0 出发限幅（对齐 Wang2023 增量动作语义：从当前级位
            # 出发逐步逼近目标，禁止一步跳到满制动）。
            if self.ed_rate_limit_notches > 0:
                _tgt = float(np.clip(_ed, 0.0, 1.0))
                _max_d = float(self.ed_rate_limit_notches) / 20.0
                if self._ed_notch_state is None:
                    self._ed_notch_state = [None] * n
                _prev = self._ed_notch_state[k]
                _prev = 0.0 if _prev is None else float(_prev)  # 首步从起点级位 0 出发
                _ed = float(np.clip(
                    _prev + np.clip(_tgt - _prev, -_max_d, _max_d), 0.0, 1.0))
                self._ed_notch_state[k] = _ed
            final[k, 0] = float(np.clip(_ed, 0.0, 1.0))
            # AB：连续 → 4 档量化（x = 施加程度 0~1）
            x = float(np.clip(-rl[k, 1], 0.0, 1.0))
            if x < 0.025:
                ab = self.AB_NOTCH_LEVELS[0]
            elif x < 0.125:
                ab = self.AB_NOTCH_LEVELS[1]
            elif x < 0.30:
                ab = self.AB_NOTCH_LEVELS[2]
            else:
                ab = self.AB_NOTCH_LEVELS[3]
            # 超速兜底：已越线强制 SERVICE（RL 无权关闭安全底线）。
            # 【W4-v5】贴近但未越线时可用 MIN，缓解近上限 SERVICE 与惰行叠加的车钩冲击；
            #          开关关闭时保持旧行为（近上限一律 SERVICE）。
            if vel >= vmax_eff:
                if ab > self.AB_NOTCH_LEVELS[3]:
                    ab = self.AB_NOTCH_LEVELS[3]
            elif vel >= vmax_eff - self.AB_SUPPRESS_MARGIN_MPS:
                _soft_limit = (self.AB_NOTCH_LEVELS[2]
                               if self.ab_near_limit_min_brake
                               else self.AB_NOTCH_LEVELS[3])
                if ab > _soft_limit:
                    ab = _soft_limit
            # 【v3 档位最短保持·修正语义】AB 波传播 ≈90 s，施加态下若每 1 s 改档，
            # 波未传完即变档 → 压缩/拉伸波反复叠加 → 峰值反升。
            # ⚠️ 只约束「施加态 → 施加态」的档位变化；「施加 → 缓解」不受保持约束
            #    （缓解由 222 s 充风门控管，若也纳入保持会退化为"单次长制动"，
            #     即 S2-v2 ep42 崩溃到 2351 kN / speed 23 km/h 的直接原因）。
            if self.ab_notch_hold_s > 0 and ab < 0 and self._ab_notch_state[k] < 0:
                elapsed = (self._ab_step - self._ab_notch_step[k]) * self.dt
                if ab != self._ab_notch_state[k] and elapsed < self.ab_notch_hold_s:
                    ab = self._ab_notch_state[k]
            # 充风/保持门控：新增源被拒 → 本步不发（已建立的源沿用，不撤销）
            # 【W4-v4】近上限旁路：贴近 vmax_eff 时不再让 222 s 充风门拦掉新 AB 源。
            _near_upper_limit = (
                self.ab_high_speed_bypass_gate
                and vel >= vmax_eff - self.AB_SUPPRESS_MARGIN_MPS)
            if ab < 0 and not _near_upper_limit and not self._ab_gate(k, True):
                ab = 0.0
            # 【V17】低速强制缓解兜底：速度 ≤ v_min + margin 时强制缓解（RL 无权关闭）。
            # 放在门控之后 —— 门控只拦"新增"，这里连"已建立的源"一起释放，
            # 否则 AB 可以被一次施加拖到停车（V16 主因 ②③）。
            if self.ab_low_speed_release and vel <= float(v_min) + self.ab_low_speed_margin_mps:
                ab = 0.0
            final[k, 1] = ab

        # 提交 AB 状态（与 get_action_decomposed 同口径：记录施加/释放时刻）
        for i in range(n):
            new_on = bool(final[i, 1] < 0)
            if new_on and not self._ab_on[i]:
                self._ab_last_apply_step[i] = self._ab_step
            elif (not new_on) and self._ab_on[i]:
                self._ab_last_release_step[i] = self._ab_step
            self._ab_on[i] = new_on
            # v2：档位变化记账（用于最短保持约束）
            if float(final[i, 1]) != float(self._ab_notch_state[i]):
                self._ab_notch_state[i] = float(final[i, 1])
                self._ab_notch_step[i] = self._ab_step
        return final

    # ------------------------------------------------------------------ #
    # 主接口 5【ADR-074 / 2026-11-18 级位派生化】动作 = 级位增量，ED/AB 均派生
    # ------------------------------------------------------------------ #
    # Wang2023 ②对标（实车验证拉钩 −8.93%）：空气制动 on/off 不进动作空间，
    # 由级位越限 + 最小充风时间派生。本实现：
    #   - RL 动作 = 每机车 1 维 ∈ [-1,1] = 级位增量请求；
    #   - 级位状态 n ∈ [0,1]（0=惰行，1=满制动；长大下坡无牵引语义与 S2 一致），
    #     单决策步 |Δn| ≤ notch_incr_rate_notches/20（复用 ADR-072 口径，默认 3
    #     ⇒ 0.15/决策步，量级对标文献 ±3/±12）；
    #   - ED = n（派生；n=0 = 真惰行，天然实现 Wang2023 "初制动 + 惰行" 循环）；
    #   - AB 派生（级位越限 + 滞回）：n ≥ θ → 请求 on；n < θ − margin → 释放。
    #     派生档位默认 MIN（70 kPa）——诊断 §7：140 kPa 时序完美也 ≈1004 > 1000，
    #     70 kPa 级循环制动是单源进线的前提而非选项。
    # 安全链与 get_action_notch 同口径、同顺序（RL 无权关闭）：
    #   ① 超速兜底强制 SERVICE；② 近上限分级（W4-v5）；③ 档位最短保持（仅施加态）
    #   ④ 222 s 充风门（近上限旁路 W4-v4）；⑤ 低速强制缓解（V17）。
    def get_action_notch_incr(
        self, train_env, rl_actions, v_max: float = 80.0 / 3.6,
        v_min: float = 40.0 / 3.6, v_max_adj: float = 0.0, v_min_adj: float = 0.0,
    ) -> np.ndarray:
        """级位派生化：rl_actions (num_loco, 1) ∈[-1,1] = 级位增量请求。

        Returns:
            final (num_loco, 2)：[ED=n, AB（负=施加）]，语义与现有通道一致。
        """
        if not (self.notch_incr_rate_notches > 0):
            raise ValueError(
                'notch_incr mode requires notch_incr_rate_notches > 0 '
                '(fail-fast: 无速率限制的级位积分不满足 Wang2023 对标语义)')
        self._ab_step += 1
        rl = np.asarray(rl_actions, dtype=float).reshape(self.num_locomotives, -1)
        if rl.shape[1] != 1:
            raise ValueError(
                f'notch_incr expects (num_loco, 1) actions, got shape {rl.shape}')
        n_loco = self.num_locomotives
        if self._notch_level is None:
            self._notch_level = [0.0] * n_loco   # 起点级位 0 = 惰行
        final = np.zeros((n_loco, 2), dtype=float)
        vel = float(train_env.dynamics.vel[0])
        vmax_eff = float(v_max) + float(v_max_adj)
        max_d = float(self.notch_incr_rate_notches) / 20.0
        # 【A-4】每决策步读一次队首坡度（‰）；坡度缺失（mock/恒坡无 grade）⇒ None，
        # 所有 A-4 门自动失效 = 零回归。变缓量 = 当前 − 上一步（正=坡度回升/变缓）。
        _grade_arr = getattr(train_env.dynamics, 'grade', None)
        grade_permille = (float(np.asarray(_grade_arr).ravel()[0]) * 1000.0
                          if _grade_arr is not None else None)
        grade_rebound = (grade_permille - self._prev_grade_permille
                         if (grade_permille is not None
                             and self._prev_grade_permille is not None) else None)
        for k in range(n_loco):
            # 1) 级位积分：增量限幅
            a_k = float(np.clip(rl[k, 0], -1.0, 1.0))
            n_k = float(np.clip(self._notch_level[k] + a_k * max_d, 0.0, 1.0))
            # 【ADR-076 待验证：ED 前馈浅化上限（默认关 = 零回归）】
            # 诊断 §19.17.3：decompose 路线（规则在环）历史读数 gap_err 41.78 m /
            # band 100% / mean_ed 0.7693；nincr 路线 495.08 m / 86% / 0.9013
            # —— 几何差 11.9 倍。机制定位（源码级）：`ed_grade_feedforward` 的
            # ED 前馈浅化**只在 decompose 路径调用**（get_action_cyclic_braking /
            # get_action_decomposed），**nincr 从不调用** ⇒ nincr 的 ED 只能由
            # RL 单调积分推深 ⇒ 贴顶 ⇒ 缓解-再施加相位差大 ⇒ 既丢几何又丢峰。
            # 本段把同一前馈反解（维持速度所需的最小 ED 级位）作为 **RL 级位的
            # 上限**：RL 仍可自由下探（缓解空间保留 ⇒ 相位差小），但不能把 ED
            # 推过头贴顶（多余制动力只加剧纵向冲击）；额外减速需求交给 AB。
            # 不改动作面（仍 1 维级位增量）/不改物理/不改奖励面/不改安全层。
            if self.ed_feedforward_cap > 0.0:
                try:
                    _ff = self._grade_feedforward_actions(train_env)
                    # 前馈给的是"维持速度所需"的最小 ED ⇒ 乘系数后可作上限；
                    # 系数 >1 留出策略余量（探针扫描用）。
                    _cap = float(_ff[k, 0]) * float(self.ed_feedforward_cap) \
                        + float(self.ed_feedforward_margin)
                    if _cap > 0.0 and n_k > _cap:
                        n_k = _cap
                except Exception:
                    pass
            # 【ADR-076 待验证：ED 深度常数上限（默认 1.0 = 不限制 = 零回归）】
            # 诊断 §19.17.4：decompose 路线 mean_ed 0.7693（浅）/ gap 41.78 m；
            # nincr mean_ed 0.9013（贴顶）/ gap 495.08 m ⇒ 差 11.9 倍。
            # 本项把 ED 级位封顶到常数（探针扫描 0.6~0.9），直接干预 ED 深度，
            # 检验"ED 浅 ⇒ 缓解-再施加相位差小 ⇒ 几何与峰同时可控"的因果性。
            # ⚠️ 只压 ED 深度上限，不改 AB 派生/充风门/低速兜底/车钩 veto。
            # 【ADR-081】追及需求 ⇒ ED 深度上限放宽（仅在本列追及压力大时）
            _cap_eff_base = float(self.ed_notch_cap)
            if (self.ed_cap_rel_speed_kmh > 0.0
                    and _cap_eff_base < float(self.ed_cap_relaxed)):
                # 【ADR-081】相对速度优先取 env 侧传入的标量
                # （env 侧算好，因 controller 收到的是单列子环境、
                #  取不到整编队的前列速度；见 ADR-081 修正说明）。
                _v_rel_now = float(self._ed_cap_rel_speed_now)
                if _v_rel_now >= float(self.ed_cap_rel_speed_kmh):
                    _cap_eff_base = float(self.ed_cap_relaxed)
                else:
                    # 双保险：若 train_env 恰为 fleet env，则在此自算
                    try:
                        _trains = getattr(train_env, 'trains', None)
                        _ci = int(self._ed_cap_col_index)
                        if (_trains is not None and 0 <= _ci < len(_trains)
                                and _ci > 0):
                            _v_self = float(_trains[_ci].dynamics.vel[0])
                            _v_lead = float(
                                _trains[_ci - 1].dynamics.vel[0])
                            _v_rel = (_v_self - _v_lead) * 3.6   # km/h
                            if _v_rel >= float(
                                    self.ed_cap_rel_speed_kmh):
                                _cap_eff_base = float(self.ed_cap_relaxed)
                    except Exception:
                        pass
            if _cap_eff_base < 1.0 and n_k > _cap_eff_base:
                # 【ADR-076】ED 上限的两种放宽方式（互斥，斜坡优先）：
                # ① 阶跃释放阀：速度 ≥ 阈值 ⇒ 完全放开（实测有害，见参数注释）
                # ② 渐进斜坡：上限随速度线性放宽（变化率受限 ⇒ 无阶跃冲击）
                # 【ADR-081】起点用 `_cap_eff_base`（追及放宽后的上限）；
                # 未开启 ADR-081 时它 == ed_notch_cap ⇒ 逐位等价。
                _cap_eff = float(_cap_eff_base)
                _rel_v = float(self.ed_notch_cap_release_kmh)
                if _rel_v > 0.0 and vel * 3.6 >= _rel_v:
                    _cap_eff = 1.0
                _slope = float(self.ed_notch_cap_slope)
                if _slope > 0.0:
                    _dv = vel * 3.6 - float(self.ed_notch_cap_slope_from_kmh)
                    if _dv > 0.0:
                        _cap_eff = min(1.0, _cap_eff + _slope * _dv)
                if n_k > _cap_eff:
                    n_k = _cap_eff
            self._notch_level[k] = n_k
            # 2) ED = 级位（派生）
            final[k, 0] = n_k
            # 3) AB 派生（级位越限；滞回防抖：释放阈值低于触发阈值）。
            #    比较带 epsilon：级位是浮点积分，0.60−0.15=0.4499…96 会击穿
            #    恰好落在阈值上的滞回边界（单测实证），必须容差比较。
            # 【ADR-076 待验证：逐列 AB 派生阈值，默认 None = 用默认 0.5 = 零回归】
            # 诊断 §19.13.3：AB 的**逐列分配方向**是几何收敛的载体——领航多带闸
            # （规则基线 39%）⇒ 领航减速 ⇒ 后列追得上（pair0 速率 −0.437 m/s）；
            # 后列多带闸 ⇒ 后列自己慢下来 ⇒ 净空被撑开（pair1 速率 +1.17 m/s）。
            # nincr 的 AB 由级位越限派生且逐列同阈 ⇒ 分配结构完全由 RL 的级位
            # 动作决定，无法表达该结构。此处按列角色选**请求门限**：
            # 领航列阈值下调（更早/更久请求 AB）、后列列阈值上调（更少带 AB）。
            # 只改 AB 请求门限，不改 ED/AB 物理、不改动作面（仍 1 维级位增量）、
            # 不改奖励面、不改安全层 ⇒ 两侧物理同源；222 s 充风门与低速兜底保留。
            _thr = self.ab_derive_threshold
            if self.ab_derive_threshold_lead is not None:
                _thr = float(self.ab_derive_threshold_lead)
            elif self.ab_derive_threshold_follower is not None:
                _thr = float(self.ab_derive_threshold_follower)
            _eps = 1e-9
            # 【ADR-076 待验证：物理触发式 AB 兜底，默认关 = 零回归】
            # 诊断 §19.14.2：规则基线的 AB 是**物理触发**（ed_avail < 0.99 ⇒ 引 AB），
            # 我们的 nincr 是级位派生 ⇒ 逐列分配结构由 RL 决定，实测方向与规则基线
            # 相反（领航 9% vs 39%）⇒ 减速责任落在后列 ⇒ 净空被撑开、几何发散。
            #
            # 语义设计（与规则基线的循环制动状态机同构，但严格「只加不减」）：
            #   · 物理不足（ed_avail < 阈值）⇒ **持续**请求 AB（规则基线同源判据：
            #     循环制动态下 ed_avail < 0.99 即引 AB 兜底，并持续到退出循环制动）。
            #   · 释放权仍归既有链：释放速度门（§16）、低速强制缓解（V17）、
            #     档位最短保持、222 s 充风门 —— 全部保留且不受本机制否决。
            #   · **级位滞回在物理触发下不单独触发释放**：否则"级位滞回 ⇒ 释放"与
            #     "物理不足 ⇒ 请求"每步互相打架，产生 1 步抖动（实测）。
            #     物理触发下的释放改由 ed_avail 恢复（≥ 阈值 ⇒ ED 足够 ⇒ 缓解），
            #     即**物理判据自洽地同时管请求与释放**，与规则基线同构。
            #     ⚠️ 因此"只加不减"指的是**不放松任何既有安全门**（充风门/低速兜底/
            #     档位保持/车钩 veto 全在），而不是"物理判据永不释放"——
            #     后者会把 AB 永久按住不放（拖停风险），规则基线也不是那样。
            _phys_insufficient = False
            if self.ab_release_by_local_grade:
                # 【ADR-076 待验证：位置相关的物理判据（§19.21）】
                # 用**当前实际坡度**判定「ED 是否已不足以维持速度」
                # （`_ed_cannot_hold_speed`：grade_force − resistance vs
                #  electric_capacity，按各车实际坡度算，位置相关）。
                # 与 ed_avail 口径的关键差异：
                #   · ed_avail 的需求项取**全程最陡坡**（位置无关）且随速度变化
                #     ⇒ 低速误判「ED 已够用」⇒ 释放 ⇒ 222 s 锁死 ⇒ 拖停；
                #   · 本判据在陡坡（含低速）恒判「不够」⇒ 保持 AB；进缓坡才释放。
                try:
                    _phys_insufficient = bool(self._ed_cannot_hold_speed(train_env))
                except Exception:
                    _phys_insufficient = False
            elif self.ab_physical_trigger:
                try:
                    _avail = self._ed_ab_price(train_env)
                except Exception:
                    _avail = None
                if _avail is not None and _avail < float(self.ab_physical_avail_threshold):
                    _phys_insufficient = True
            if self._ab_on[k]:
                want_on = n_k >= (_thr
                                  - self.ab_derive_release_margin - _eps)
                if _phys_insufficient:
                    want_on = True      # 物理不足 ⇒ 保持（释放交由物理判据恢复）
                elif self.ab_release_hysteresis_s > 0.0:
                    # 【ADR-080】释放迟滞带：物理不足在最近 N 秒内曾成立
                    # ⇒ 继续保持 AB（避免「需求一消失即释放」的反复相位差）。
                    # 注意：仅在「因物理理由释放」这条路径上加迟滞；
                    # 其它释放路径（级位释放判据/低速强制缓解/充风门）不受影响。
                    _last_insuff = self._ab_phys_insuff_step[k]
                    _since_insuff = (self._ab_step - _last_insuff) * self.dt
                    if (0.0 <= _since_insuff
                            <= float(self.ab_release_hysteresis_s)):
                        want_on = True
            else:
                want_on = n_k >= _thr - _eps
                if _phys_insufficient:
                    want_on = True      # 级位未越限但物理不足 ⇒ 仍请求（加法）
            if _phys_insufficient:
                # 【ADR-080】记录「物理不足最近成立时刻」（释放迟滞带用）
                self._ab_phys_insuff_step[k] = self._ab_step
            # 【AB 释放速度门（诊断 §14，默认关 = 零回归）】：已施加态若开启本门，
            # 释放判据由「级位下探」改为「速度门」——速度高于门限 ⇒ 保持 AB on，
            # 使 AB on 段与 ED 级位轨迹解耦（消除 25 s on → 222 s 锁死空窗的自锁死）。
            # 低速强制缓解在安全链末尾仍可强制释放（v ≤ v_min+2）⇒ 防拖叠底线在位。
            # 【ADR-076】物理触发开启时，物理不足已把 want_on 置 True（保持），
            # 此时**不再用速度门覆盖**（否则会抹掉物理保持语义）；速度门只在
            # 物理不不足（即 want_on 由级位判据给出）时接管释放判据。
            if (self._ab_on[k] and self.ab_release_speed_gate
                    and not _phys_insufficient):
                want_on = vel * 3.6 > float(self.ab_release_speed_kmh)
            # 【A-4 坡度门（默认全关 = 零回归）】：已施加态若因级位下探而想释放，
            # 但没进入"变缓点"，则否决释放、保持 AB on。释放时机由级位下探解耦到坡度。
            # A-4a（相对变坡点）：仅当坡度回升 ≥ Δ 才允许释放（覆盖绝对门）。
            # P1-v1（绝对坡度门）：坡度 ≤ 门限才否决（保留供对照）。
            if (not want_on) and self._ab_on[k] and grade_permille is not None:
                if (self.ab_grade_rebound_gate and grade_rebound is not None):
                    if grade_rebound < float(self.ab_grade_rebound_permille):
                        want_on = True   # 没到变缓点 → 否决释放
                elif self.ab_grade_release_gate:
                    if grade_permille <= float(self.ab_grade_release_permille):
                        want_on = True   # 坡度仍陡 → 否决释放（P1-v1 对照）
            ab = (self.AB_NOTCH_LEVELS[self.ab_derive_notch_idx]
                  if want_on else self.AB_NOTCH_LEVELS[0])
            # 【AB 施加门控（诊断 §16，默认 0 = 不启用 = 零回归）】：低速段不**新增** AB 源
            # ——速度低于 `ab_apply_speed_min_kmh` 且当前未施加时，即使 want_on=True
            # 也不落地（ab=0）。只挡新增、不挡已施加态的维持（与释放门控互不替代）。
            # 动机：释放速度门整程实测的全程峰 1,199.4 kN 全部来自起步段 t=26.2 s
            # （起步速度已 60 > 释放门限 ⇒ 立即施加 ⇒ 起步瞬态冲高），而 gate56 在
            # 真实主峰窗尾列峰 838.9 < baseline 928.1 ⇒ 收益被起步瞬态吃掉。
            if (self.ab_apply_speed_min_kmh > 0 and not self._ab_on[k]
                    and vel * 3.6 < float(self.ab_apply_speed_min_kmh)):
                ab = self.AB_NOTCH_LEVELS[0]
            # 4) 安全链（与 get_action_notch 同顺序）
            if vel >= vmax_eff:
                # 超速兜底：强制 SERVICE（RL 无权关闭安全底线）
                if ab > self.AB_NOTCH_LEVELS[3]:
                    ab = self.AB_NOTCH_LEVELS[3]
            elif vel >= vmax_eff - self.AB_SUPPRESS_MARGIN_MPS:
                _soft_limit = (self.AB_NOTCH_LEVELS[2]
                               if self.ab_near_limit_min_brake
                               else self.AB_NOTCH_LEVELS[3])
                if ab > _soft_limit:
                    ab = _soft_limit
            # 档位最短保持（只约束施加态 → 施加态；缓解不受限，防 S2-v2 式拖停）
            if self.ab_notch_hold_s > 0 and ab < 0 and self._ab_notch_state[k] < 0:
                elapsed = (self._ab_step - self._ab_notch_step[k]) * self.dt
                if ab != self._ab_notch_state[k] and elapsed < self.ab_notch_hold_s:
                    ab = self._ab_notch_state[k]
            # 充风/保持门控（新增源被拒 → 本步不发；近上限旁路 W4-v4）
            _near_upper_limit = (
                self.ab_high_speed_bypass_gate
                and vel >= vmax_eff - self.AB_SUPPRESS_MARGIN_MPS)
            if ab < 0 and not _near_upper_limit and not self._ab_gate(k, True):
                ab = 0.0
            # 低速强制缓解兜底（V17：防 AB 拖到停车）
            if self.ab_low_speed_release and vel <= float(v_min) + self.ab_low_speed_margin_mps:
                # 【A-4b】陡坡低速时继续带闸（推迟缓解到变缓点），但逼近停车红线
                # v_stop 仍强制缓解——保住 V17/V18-b 拖停底线。默认关 = 零回归。
                _allow_low_release = True
                if (self.ab_low_speed_grade_gate and ab < 0
                        and grade_permille is not None):
                    _at_rebound = (grade_rebound is not None and
                                   grade_rebound >= float(self.ab_grade_rebound_permille))
                    _near_stop = vel * 3.6 <= float(self.ab_low_speed_stop_kmh)
                    if (not _at_rebound) and (not _near_stop):
                        _allow_low_release = False
                if _allow_low_release:
                    ab = 0.0
            final[k, 1] = ab
        # 提交 AB 状态（与 get_action_notch 同口径：施加/释放时刻 + 档位保持记账）
        for i in range(n_loco):
            new_on = bool(final[i, 1] < 0)
            if new_on and not self._ab_on[i]:
                self._ab_last_apply_step[i] = self._ab_step
            elif (not new_on) and self._ab_on[i]:
                self._ab_last_release_step[i] = self._ab_step
            self._ab_on[i] = new_on
            if float(final[i, 1]) != float(self._ab_notch_state[i]):
                self._ab_notch_state[i] = float(final[i, 1])
                self._ab_notch_step[i] = self._ab_step
        # 【A-4】记录本步坡度供下一步算"变缓量"；坡度缺失时清空（零回归）。
        self._prev_grade_permille = grade_permille
        return final

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
        self._ed_notch_state = None
        self._notch_level = None
        self._ed_recovery_pending[:] = False
        self._ed_hold_steps = 0
        self._ed_guard_steps_left = 0
        self._ed_guard_ref = None
        self._ed_guard_armed = True
        self.ed_release_guard_veto_count = 0
        self.ed_release_guard_hold_steps = 0
        self.ed_conv_unmet_count = 0
        self.ed_conv_active_steps = 0
        self._ab_step = 0
        self._ab_on = [False] * self.num_locomotives
        self._prev_grade_permille = None   # 【A-4】变坡点门的坡度历史，reset 清零
        self._ab_last_release_step = [-10 ** 9] * self.num_locomotives
        self._ab_last_apply_step = [-10 ** 9] * self.num_locomotives
        self.ab_refill_veto_count = 0
        self.ab_hold_veto_count = 0
