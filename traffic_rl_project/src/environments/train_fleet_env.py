"""
重载列车群组（多列编队）协同控制 Gym 环境。

【核心定位（2026-08-14 架构澄清）】
- 多智能体 = 多列万吨列车（每列 = 1 个智能体，编队/群组协同）
- 列内（1 机车 + 100 拖挂）= 单列控制（车钩力作为该列状态/奖励的约束指标），不是多智能体

【任务场景（已确认）】
- 3 列万吨列车在长大下坡 leader-follower 编队巡航
- 目标 = 速度一致（20 m/s）+ 保持 100m 安全间距 + 车钩力 ≤1000kN

【分层架构】
层级一（本文件）：多列编队 MARL 环境
    - 智能体 = 每列万吨列车
    - 每列状态 = 该列速度 / 间距误差 / 前方坡度 / 自身车钩力统计（均值/峰值/超限）
    - 每列动作 = 该列目标加速度（宏观决策，m/s²，对齐 Zhang2021 控加速度）
    - 每列奖励 = 速度同步 + 列间安全间距 + 自身车钩力约束 + 舒适性

层级二（列内底层控制器）：TrainLowLevelController
    - 接收层级一的目标加速度 → 转为列级 throttle（get_action_accel）+ 车钩力安全钳制
    - 输出该列实际车钩力反馈给层级一作状态/奖励
"""

import json
import logging
from copy import deepcopy
from pathlib import Path

import numpy as np
from gym import spaces

from src.environments.train_env import TrainFormationEnv, COUPLER_FORCE_LIMIT_N, CONSIST_PRESETS
from src.controllers.low_level_controller import TrainLowLevelController
from src.controllers.multi_loco_controller import MultiLocoController
from src.train_dynamics.grade_profile import PROFILES
from src.train_dynamics.braking import AirBrakeNotch
from src.train_dynamics.params import sample_coupler_params
from src.train_dynamics.etcs_braking import (
    EtcsBrakingCurve, EbdTarget, braking_build_up_from_train, G_RAIL,
)


# 【ADR-021 决策2 2026-10-01】奖励 schema 版本 + 车钩力"受控超限项"常量（文献 Tang2020 / Wang2025）。
# reward 峰值口径改为**断面力**（coupler_interface_forces）后，旧权重需重训；此常量供 metadata 标注。
# v4 = v3 + 间距危险项穿透有界化（ADR-028 2026-10-04）：穿透时 over 不再退化为"米²"（量级炸裂）。
# 【2026-10-14 ADR-036 门限档位化】车钩限值成为 env 可配（1.0e6/1.5e6 档），
# reward 超限项分母随运行配置变 ⇒ 按 ADR-026 同款纪律升 schema：v4 与 v5 结果
# 仅在 coupler_force_limit_n 相同（1.0e6）时可直接比较；不同限值档必须按档位分别归档。
# v6 = v5 + 按文献槽位收敛（ADR-043 2026-10-20）：13 项 → 6 槽位；领航带内改平顶；
# 车钩删均值项、改峰值比有界饱和形（Wang2026 式17 同型、修正其单调方向）；删 a²/追尾趋势/追尾硬罚。
# v5 与 v6 结果不可比，须重训。
# v7 = v6 + 领航列速度项改"跟踪规则基线参考速度"（2026-11-08）：删带内平顶/凸斜坡，
# 换单峰有界二次跟踪项 r = W·(1 − min(((v−v_ref)/band)², CAP))。提出动机：v6 的 flat
# 在 40–80 km/h 内**无速度梯度**（基线实测 88.5% 步直接拿满 +5，占奖励 41.5%），
# 属"恒定额白拿分"，既不区分快慢也无法引导"贴基线"。v6 与 v7 结果不可比。
# v8 = v7 + 超限项权重 6.0 → 15.0（2026-11-09，ADR-059）：梯度交换比修正，支撑 ADR-058
# "峰值优化移交 RL"的 1000 kN 目标。项集/形态与 v7 完全相同，仅常量变化；v7 与 v8 结果不可比。
REWARD_SCHEMA = 'v9-overlimit-w60'
# 【ADR-043】领航列速度项权重（对齐 Zhang2024 式22 Rd=+5；v7 下为跟踪峰值）。
SPEED_BAND_W = 5.0
# 【速度带改形 2026-11-08】'ramp' 形态的凸指数：收益随接近上限**边际递增**（1 = 线性，>1 = 越靠上限挣得越快）。
SPEED_BAND_RAMP_EXP = 1.5
# 【参考速度跟踪 2026-11-08】'ref' 形态三参数（缺省值即标定值，YAML 可不写）：
#   band  = 5 km/h（= 验收口径里"贴基线"的容差；1 个带宽内偏离按二次衰减）
#   cap   = 4（x² 饱和上界 ⇒ 项取值 ∈ [W·(1−CAP), W] = [−15, +5]；|偏离| ≥ 2 个带宽即封底）
#   w     = SPEED_BAND_W（跟踪满分与 v6 平顶同量级，便于与历史奖励总量对比）
SPEED_REF_BAND_KMH = 5.0
SPEED_REF_CAP = 4.0

_logger = logging.getLogger('FleetEnv')
# 【ADR-043】车钩力峰值比塑形权重：-w_f·(1-exp(-p̂))，p̂ = 本步断面力峰值/限值。
# 取 Wang2026 式17 的有界饱和形并修正其单调方向（原文 -exp(-f/F) 单调反常，见 ADR-043）。
# 【2026-11-08 标定实测】基线 BC 轨迹实测该项绝对占比 1.45%（W=0.3）；按"目标 ~10%"反推 W≈2.26，
# 取 2.5 ⇒ 但 2026-11-08 全 31 419 步复算发现：上一轮把 mean(p̂) 直接代入凹函数
# （1−e^{−p̂} 是凹的，Jensen 意义上 E[1−e^{−p̂}] < 1−e^{−E[p̂]}），实际每步均值只有 −0.629（占 5.55%）。
# 按"实际占比 10%"重新标定 ⇒ W = 2.5 × (10.5903/9) / 0.6288 ≈ 4.68，取 4.7。
# 复算口径（只读归档、零仿真）：见 DIAGNOSTICS_2026-11「小节-2026-11-08（十）」。
COUPLER_PEAK_W = 4.7
# 超限项权重。【ADR-059 2026-11-09】6.0 → 15.0：v7 权重下梯度交换比不利——压峰 1450→1000 kN
# 每峰值步仅挣 ~3.3 分，而头车偏离 v_ref 5 km/h 即损失 5~20 分/步；trial40（v7）前 30 集实证
# 峰值持平微升（1392→1458）。ADR-058 已把峰值优化移交 RL 并锁定 1000 kN，超限带梯度必须给足。
# 【ADR-063 2026-11-11】15.0 → 60.0：v9_l1_cloud 全剖面实测（41.1 万步/集）定量——正项工资
# ≈ +7.07/步（rel_anchor 3.62 + gap_eff 3.45），15.0 下超限步（p̂=1.43 → over=0.43）仅罚
# -6.5/步 < 工资 ⇒ **车钩超限在经济上中性（冲高步净 +0.5）**，RL 理性选择忍罚不治峰。
# 60.0 ⇒ 超限步 -25.8/步，净 -18.7/步（亏 2.6 秒工资），超限在经济上不可行。
# 线性有界形态不变，上界 -120 仍小于已回滚的 -80·ov²（二次、无界趋势、每步爆炸）量级
# （旧教训是平方+无界，此处线性+CAP 封顶且仅低频超限步出现），且 speed_over
# （10/km/h、不封顶）日常即可达 -100 量级，value 尺度有先例。
COUPLER_OVER_W = 60.0
# 限幅：peak_norm 超过 3× 上限（over>=2）后不再加深 ⇒ 该项上界 = -COUPLER_OVER_W*CAP = -120。
COUPLER_OVER_CAP = 2.0

# 【ADR-026 编队间距：ATP 对齐两段式】
# 目标：车钩力不破线的前提下，"贴近 ATP 制动安全底线"跑——间距尽量小（高效）但不触发 ATP。
#   d_safe(t) = ETCS 制动距离（后列须在追上前列尾前降到前列当前速度）——**与 ATP 判据同源**
#                （EtcsBrakingCurve.braking_distance，含制动建立期 + 坡度分量）。
#   效率目标 d_eff = GAP_EFF_MARGIN · d_safe（留 10% 裕量，防相位/延迟下擦线）。
# 文献对位：Guo2025 式5（安全距离随速度动态变化）；Zhang2021（设点 + 越界悬崖）；Hua2024 式2
#   （平滑跟踪项 + 独立防撞项）。参见 docs/REFERENCE_INDEX.md。
GAP_EFF_MARGIN = 1.1          # 效率目标 = 1.1 · d_safe（10% 裕量）
GAP_EFF_SCALE_M = 150.0       # 效率项衰减尺度（gap ≥ d_eff + 此值 → 效率奖励为 0）
GAP_EFF_W = 3.0               # 效率项权重（每对，与原速度带 +6.0/列 同量级但不喧宾夺主）
GAP_DANGER_W = 60.0           # 危险项权重（每对）；跌破 d_safe **不封顶**（替代旧 -200 饱和）
# 【修复 2026-10-04】穿透时 _atp_safe_gap 恒返 0.0 ⇒ d_safe 退化为 0，用本固定参考尺度（m）
# 替代其作危险项分母，避免 over 退化成"穿透米数"后 over² 爆炸（见 _calculate_reward_decomposed）。
GAP_DANGER_REF_M = 100.0


class TrainFleetEnv:
    # 【A1-final 双向列距维持，2026-09-09】leader 最多比尾部列快这么多（m/s），
    # 留出追上裕量。大于此则 leader 迁就压速，编队以尾部能跟上的共同速度前进。
    LEAD_TAIL_OFFSET_MPS = 5.0

    # 【列距主动收缩 v2 2026-09-09】follower 级联追前列的强化增益。
    # A2 全局共同速度锁把 follower 上限一起压到"最慢列+5"，使"最慢列当 follower"时
    # 无追能力 → col1-col2 停在 ~2400m 缩不回；且原 coordination_adj 增益太小。
    # 放大追增益 + 上限改 min(协调抬带, lead_speed+offset)，让级联追前列真正生效。
    LEAN_KP_GAP = 0.004
    LEAN_TRACTION_COEF = 0.0015
    LEAN_MAX_TRACTION = 0.5
    LEAN_MAX_ADJ = 3.0

    # 【等速冻结消除 2026-09-09】三列等速时 coordination_adj 追的偏置无累积 → 间距冻结在
    # ~1300m。chase：follower 落后超前区时把缓解线抬到"仅比 lead 快一点"持续缩距。
    LEAN_CHASE_DELTA_MPS = 0.8
    LEAN_CHASE_DEADBAND_M = 25.0

    # 【相对列距锚定 2026-09-10，ADR-014 方向1】绝对速度带一致在 53km 多坡段物理不可达
    # （诊断-2026-09-10 发散短训 35ep 复现：位置差→坡度差→速度差→间距扩大，ep17 起崩坏）。
    # 编队学习目标从"所有列贴近绝对带中心 + 全局同速"改为相对锚定：
    #   - 领航列(ti==0)：锚绝对带（编队节奏负责人），带内奖 + 超上限硬罚。
    #   - 跟随列(ti>0)：锚"相对前列"(列距 gap_reward + 相对速度此处)，不再被绝对带/
    #     全局 std 惩罚拖累。跟随列镜像前列可行轨迹（同坡序相位差），物理可收敛。
    REL_ANCHOR_SPD_SCALE = 3.0       # 相对速度匹配对称尺度（m/s）：±3 内奖最强、越界衰减
    REL_ANCHOR_SPD_W = 2.0           # 相对速度镜像奖权重（替代旧 rel_vel_penalty 全局 std）

    """
    多列万吨列车编队协同控制环境。

    智能体 = 每列万吨列车。列内用底层控制器（TrainLowLevelController）跟踪目标速度。

    Args:
        config (Dict):
            - num_trains: 编队列车列数（默认 3）
            - consist_preset: 单列编组预设（默认 '10kt_1plus0'，1机车+100拖挂）
            - grade_profile: 坡度剖面（默认 'long_downhill'）
            - target_speed: 目标巡航速度（m/s）
            - coupler_force_limit_n: 车钩力上限（默认 1000kN）
            - max_steps: 每回合最大步数
            - dt: 积分步长
            - action_speed_range: 目标速度动作范围（m/s，相对 target_speed 的偏差范围）
        （ATP/ETCS 为永久启用的安全底线，无 enable_etcs 开关：每列安全层恒对
        "前列尾车"做 EBD/EBI 监督（防追尾由车载 ATP 保证），线速上限仍由反应式
        限速兜底（两者共存，见 safety_layer 规则0/规则1）。
    """

    def __init__(self, config: dict = None):
        config = config or {}
        self.num_trains = config.get('num_trains', 3)
        self.consist_preset = config.get('consist_preset', '10kt_1plus0')
        self.grade_profile = config.get('grade_profile', 'shuozhou_ningwuxi_beidaniu_49km')  # 主训练默认=朔黄宁武西→北大牛真实纵断面 49.6km
        # 限速区间（m/s）：对齐 Zhang2024（朔黄线 23.8km 长大下坡循环制动）[40,80] km/h。
        # 依据（V5.24 系统核对）：
        # - 上限 80 km/h = 朔黄线实际线路限速（Zhang2024: "speed limit on this line was 80 km/h"，
        #   行业/线路标准，与研究对象1万吨朔黄线一致）
        # - 下限 40 km/h = 2万吨列车最小缓解速度（行业规则"重载30km/h以下不应缓解制动"，
        #   Zhang2024取40保守值；为与其直接对标+物理可行）
        # 弃用 [45,65]：那是樊运新（3万吨）参数，与1万吨对象不一致，且物理上不可行
        # （1.2km万吨列车在窄区间制动频繁→车钩力爆炸+掉速）。
        self.v_max = config.get('v_max', 75.0 / 3.6)   # 全局上界（ADR-068：75 km/h；分段限速另由 _line_vmax_for 联动）
        self.v_min = config.get('v_min', 40.0 / 3.6)   # 下限（40 km/h，最小缓解速度）
        # 巡航参考速度 = 限速区间中值（作为 obs 速度误差参考，非硬目标）
        self.target_speed = config.get('target_speed', (self.v_min + self.v_max) / 2.0)
        # 【ADR-061 2026-11-09】删除 target_gap=100m / headway_s=5s 参考线：两者均无
        # 外部文献锚（100m 为早期默认值自证"拍脑袋"；5s 落在公路 CACC 0.5-1.5s 与铁路
        # VC 货运 ~40s 之间两头不锚）。列间距语义统一收敛到 d_safe 体系（ATP 同源）：
        # 奖励 gap_eff/gap_danger 与诊断参考线全部使用 d_eff = GAP_EFF_MARGIN × d_safe。
        # 文献锚：Shift2Rail TD2.8 VC = 制动距离内运行（Muniandi 2020, IET ITS，
        # DOI 10.1049/iet-its.2019.0694）；Wu 2024（ASME JDSMC 146(4):041008）确认
        # VC headway 主流设计族且重载场景 time headway 更优；包神 3.5 万吨重载群组
        # 实测追踪距离 943-1091 m @ 60 km/h（2025-12-08，科技日报/央视网）。
        self.coupler_force_limit_n = config.get('coupler_force_limit_n', COUPLER_FORCE_LIMIT_N)
        # 【I 组 2026-10-16】安全层车钩超限干预策略（规则 A）透传内层单列 env；
        # 默认 'release' = 旧行为（编队主线零回归），'min_brake' 供单列标定试验。
        self.coupler_override = config.get('coupler_override', 'release')
        # 【V 组 2026-10-16】安全层 AB 新增源 veto 三参数透传内层单列 env
        # （None = 安全层默认，零回归）
        self.veto_cfg = {k: config[k] for k in (
            'coupler_veto_ratio', 'coupler_veto_margin', 'coupler_veto_lag_s')
            if config.get(k, None) is not None}
        self.max_steps = config.get('max_steps', 500)
        # 【2026-11-08 截断口径｜虚构路况治理】头车到达剖面真实末端即截断，不再靠步数跑满。
        # 依据：`shuozhou_ningwuxi_beidaniu_49km` 源表总长 49 600 m（最后一段起点 48 561.4 m），
        # 越过末端后 `GradeProfile.grade_at` 静默沿用末段 −1.5‰ ⇒ **坡度外推 = 虚构路况**。
        # 基线归档实测 31 419 步已跑到 53 650.2 m（越界 4 050.2 m），故旧 36 000 步口径下
        # 约 20% 的步落在无真实坡度段上；训练/评估都要按真实剖面截断。
        # `route_end_m` 缺省 None = 不启用（单测/短剖面沙盒保持零回归）。
        _route_end = config.get('route_end_m')
        self.route_end_m = float(_route_end) if _route_end not in (None, 0, 0.0) else None
        self.dt = config.get('dt', 0.1)
        # 【奖励标定 2026-11-08，默认关 = 零回归】逐槽位奖励分量累计（只用于"占比"标定，
        # 不参与任何控制/学习路径）。开=true 时把每步各分量累加到 reward_term_sums，
        # 供诊断入口按真实轨迹统计"车钩峰值项占总奖励比例"。
        self.reward_term_log = bool(config.get('reward_term_log', False))
        self.reward_term_sums = {}
        self._reward_term_steps = 0
        self._last_reward_terms = None
        # 【速度带改形 2026-11-08，默认 'flat' = 零回归】领航列速度项形态：
        #   'flat' = v6 旧行为（带内平顶 +SPEED_BAND_W，无速度梯度）
        #   'ramp' = 带内随接近上限收益递增（凸梯度），越线速重罚
        #   'ref'  = v7 跟踪规则基线参考速度（单峰有界二次，见 _ref_speed_at / 奖励分支）
        # 动机：实测 `speed_band` 占奖励 41.5% 且带内恒 +5.000 ⇒ 无速度梯度，
        # "少制动/早缓解"在奖励上白赚速度（见 DIAGNOSTICS_2026-11 小节（九）8）。
        self.speed_band_shape = config.get('speed_band_shape', 'flat')
        if self.speed_band_shape not in ('flat', 'ramp', 'ref'):
            raise ValueError("speed_band_shape must be 'flat', 'ramp' or 'ref'")
        # 超线速罚权重。'flat' 旧行为硬编码 5.0（默认 5.0 = 零回归）；
        # 'ramp'/'ref' 默认 10.0：跟踪满分 +5 落在参考速度上，越线 1 km/h 必须罚到"不划算"
        # （旧值 5.0 时越线 1 km/h 仅 −1.39，不构成硬墙）。上限刻意不取 12 以上：
        # 长大下坡难免瞬时越线，罚太狠会诱导"宁可少制动"。
        over_w_default = 10.0 if self.speed_band_shape in ('ramp', 'ref') else 5.0
        self.speed_over_w = float(config.get('speed_over_w', over_w_default))
        # 【参考速度跟踪 2026-11-08】'ref' 形态参数（缺省 = 标定值；YAML 只写表路径即可）
        self.speed_ref_band_mps = float(
            config.get('speed_ref_band_kmh', SPEED_REF_BAND_KMH)) / 3.6
        self.speed_ref_cap = float(config.get('speed_ref_cap', SPEED_REF_CAP))
        self.speed_ref_w = float(config.get('speed_ref_w', SPEED_BAND_W))
        self._ref_s_m = None
        self._ref_v_mps = None
        self._ref_origin_m = 0.0
        if self.speed_band_shape == 'ref':
            self._load_speed_ref_table(config.get('speed_ref_table'))
        # 最大加速度（方案 B）：RL 输出 ∈ [-1,1]，映射到目标加速度 ∈ [-max_accel, max_accel]
        # 动作直接影响物理（列车加速度），有真实学习区分度（解决"学无可学"）
        self.max_accel = config.get('max_accel', 1.0)
        # 最小允许速度（长大下坡只能制动降速，速度下限）
        self.min_speed = config.get('min_speed', self.v_min)
        # 扰动（突发工况）配置：领航车在某时刻突发减速，测试跟随车协同制动
        self.enable_disturbance = config.get('enable_disturbance', False)
        self.disturbance_step = config.get('disturbance_step', 100)   # 扰动触发步
        # 扰动持续步数（默认大值=扰动触发后永久生效；评估设短暂窗口模拟"前方临时限速"）
        self.disturbance_duration = config.get('disturbance_duration', 1 << 30)
        # 扰动时领航车的目标加速度（负值 = 强制制动，模拟前方障碍/限速）
        self.disturbance_target_accel = config.get('disturbance_target_accel', -0.5)
        # 是否考虑车钩力约束（消融实验：use_coupler_constraint=False 模拟"忽略车钩力"，
        # 奖励去掉车钩力项 + 底层控制器不钳制，证明"车钩力建模必要性"）
        self.use_coupler_constraint = config.get('use_coupler_constraint', True)
        # E4 分层框架：层级二用第1层策略控速（hierarchical=True），层级一 RL 只学协同调整。
        # 依据：论文分层框架（层级一生成宏观决策 + 层级二执行）+ 物理诊断（第2层从零学
        # 控速+协同过重，第1层已验证能控速车钩力150kN/速度71km/h）。
        self.hierarchical = config.get('hierarchical', False)
        # 【方向A 2026-09-04】协同动作维度：1 = 单维 coor_adj（v_max/v_min 同向平移，兼容旧）；
        # 2 = v_max_adj/v_min_adj 独立偏移（可压缩/拉伸循环带宽）。见 HierarchicalController.get_action_2d。
        self.action_dim = config.get('action_dim', 1)
        # 【方向B 2026-09-04】group_obs：全局一致性观测（修根因3）。开启则 obs 追加
        # [群组速度一致度, 群组制动相位一致度] 两个全局特征（obs_dim 11→13），
        # 让每个智能体看到整个群组的一致性状态，而非只看到前列。默认 False 保持兼容。
        self.group_obs = config.get('group_obs', False)
        # 【ADR-009.1 2026-09-05 换架构】decompose='loco_ed_ab'：智能体 = 每台机车
        # （列内真多智能体），每机车独立决策 电制动(连续调制) / 空气制动(兜底触发)。
        # 层级二 = MultiLocoController 规则基线（ED优先+错峰+AB兜底），
        # RL 输出逐机车 [ed_mod, ab_mod] 调制（真物理杠杆，区别于阈值协同 ±0.5km/h）。
        # 默认 None 完全走旧路径（列=智能体），向后兼容。
        self.decompose = config.get('decompose', None)
        self.formation_relative_speed_obs = config.get('formation_relative_speed_obs', False)
        # 【ADR-065 / S1 参数化探针 2026-11-11】rule_param_probe=True 时，RL 的
        # [ed_mod, ab_mod] **不再当幅度调制使用**，而是重新解释为**循环制动相位门**：
        #   ed_mod → cyclic_brake_trigger_kmh（何时开始制动）
        #   ab_mod → cyclic_release_kmh     （何时缓解）
        # 底层 get_action_decomposed 收到的调制量恒为 0（纯规则幅度 + RL 定的相位）。
        # 目的：判定"峰值上限是 residual 的幅度 tube，还是规则层的相位排程"。
        # 动作维度/网络结构不变（仍 (num_agents,2)）⇒ v10 ckpt 可直接加载做对照。
        # 默认 False = 零回归。
        self.rule_param_probe = bool(config.get('rule_param_probe', False))
        # 【v2 动作尺度重标定 2026-11-12】实测（300 步 trace）：策略原始动作只有 ±0.13
        # （std≈0.044，BC 全零目标 + entropy_coef=0.005 所致），原映射（±7/±8 km/h）实际只
        # 覆盖 12%，S1 因此成了"微调探针"而非"相位探针"。
        # scale 把策略实际幅度放大到设计区间：trig = 62 + 7·scale·ed_r（clamp [55,69]）。
        # scale=1.0 为原语义（零回归）。
        self.rule_param_scale = float(config.get('rule_param_scale', 1.0))
        if not isinstance(self.formation_relative_speed_obs, bool):
            raise ValueError('formation_relative_speed_obs must be a boolean')
        if self.formation_relative_speed_obs and self.decompose != 'loco_ed_ab':
            raise ValueError('formation_relative_speed_obs requires decompose=loco_ed_ab')
        if self.decompose:
            self.hierarchical = False  # decompose 模式自带规则基线，不与阈值协同混用
        # 【杠杆隔离消融】mask_lever∈{'none','ed','ab'}：decompose 模式下禁用对应 RL 调制
        # （'ed'=仅 AB 杠杆生效；'ab'=仅 ED 杠杆生效）。须与训练/评估一致。
        self.mask_lever = config.get('mask_lever', 'none')
        # 【ADR-021 决策1 2026-10-01】AB 最小充风/保持时间（秒）：透传给 MultiLocoController，
        # 并存为属性（供 metadata 侧读取）。ab_min_refill_s 默认 222.0 有出处
        # （张二田 S6，见 VALIDATION_BASELINE:201）；ab_min_hold_s 无实测出处默认 0.0（不激活）。
        # ⚠️ 键须位于 env_cfg 下，否则 config.get 静默回退默认值（YAML .get 路径须严格匹配）。
        self.ab_min_refill_s = config.get('ab_min_refill_s', 222.0)
        self.ab_min_hold_s = config.get('ab_min_hold_s', 0.0)
        # 【ADR-053 C1 诊断】按列序递增的缓解延迟（秒/列）；0 = 关闭（零回归）。
        self.cyclic_release_stagger_per_train_s = float(
            config.get('cyclic_release_stagger_per_train_s', 0.0))
        # 【ADR-054 C6 诊断】生效列范围：immediate=仅紧邻前方一列；all=前方所有列。
        self.leader_brake_feedforward = bool(config.get('leader_brake_feedforward', False))
        self.leader_brake_ff_scope = str(config.get('leader_brake_ff_scope', 'immediate'))
        # 【2026-10-14 朔黄运营口径标定（表3）+ ADR-036 门限落地，全默认关/None=旧行为】
        self.cyclic_notch_50 = bool(config.get('cyclic_notch_50', False))
        self.cyclic_brake_trigger_kmh = config.get('cyclic_brake_trigger_kmh', None)
        self.cyclic_release_kmh = config.get('cyclic_release_kmh', None)
        # 【ADR-060 限速逐段联动 2026-11-09】分段限速联动循环制动触发裕量（km/h，
        # 默认 5.0）：触发上限 = min(既有触发门, 联动限速 − margin)。仅剖面带限速表
        # （shuozhou 49km）生效；恒坡等无表剖面联动自动关闭（零回归）。
        self.cyclic_trigger_margin_kmh = float(config.get('cyclic_trigger_margin_kmh', 5.0))
        # 【K 组 2026-10-16】CYCLIC 兜底预升级速度门（None=关=旧行为）：循环制动中
        # 最大车速 ≥ 该门时把 CYCLIC(50 kPa) 预升级 SERVICE，先于 ATP 规则 C 事后猛刹。
        self.cyclic_ab_upgrade_kmh = config.get('cyclic_ab_upgrade_kmh', None)
        self.cyclic_ab_upgrade_notch = config.get('cyclic_ab_upgrade_notch', 'service')
        self.ed_release_coordination = bool(config.get('ed_release_coordination', False))
        self.ed_release_hold_s = float(config.get('ed_release_hold_s', 50.0))
        self.ed_release_boost_kn = float(config.get('ed_release_boost_kn', 900.0))
        # 【2026-11-08】AB 全列到位后抬升循环期 ED 下限（默认关 = 零回归）。
        self.ed_floor_ab_ready = bool(config.get('ed_floor_ab_ready', False))
        self.ed_floor_ab_ready_ratio = float(config.get('ed_floor_ab_ready_ratio', 0.9))
        self.ed_floor_ab_ready_kn = float(config.get('ed_floor_ab_ready_kn', 400.0))
        # 【C 组 2026-11-08】列间速度收敛 + ED 撤除时序（两个独立开关，默认关 = 零回归）。
        # 二者只作用于 ED 份额（电制动力矩），不新增 AB 源、不改档位、不碰紧急制动。
        self.ed_release_timing_guard = bool(config.get('ed_release_timing_guard', False))
        self.ed_release_guard_trigger_frac = float(
            config.get('ed_release_guard_trigger_frac', 0.30))
        self.ed_release_guard_release_frac = float(
            config.get('ed_release_guard_release_frac', 0.05))
        self.ed_release_guard_neighbor_full_frac = float(
            config.get('ed_release_guard_neighbor_full_frac', 0.80))
        self.ed_release_guard_level_frac = float(
            config.get('ed_release_guard_level_frac', 0.50))
        self.ed_release_guard_hold_s = float(config.get('ed_release_guard_hold_s', 20.0))
        self.speed_convergence_share = bool(config.get('speed_convergence_share', False))
        self.conv_share_tol_kmh = float(config.get('conv_share_tol_kmh', 1.8))
        self.conv_share_gain = float(config.get('conv_share_gain', 0.20))
        self.conv_share_max = float(config.get('conv_share_max', 0.30))
        self.conv_share_lead_share = float(config.get('conv_share_lead_share', 0.50))
        # 【X 组 2026-10-16】ED-AB 波到达协同窗（默认 0.0/1.0 = 关，零回归）：
        # 升级边沿后窗内 ED × scale，尾波到齐前头中不猛减速（消 R 峰值的速度反转）
        self.ed_upgrade_ramp_s = float(config.get('ed_upgrade_ramp_s', 0.0))
        self.ed_upgrade_ramp_scale = float(config.get('ed_upgrade_ramp_scale', 1.0))
        # 【R 组 2026-10-16】EOT 可控尾车透传（单列 env 早已支持 eot=True 双向缓解波，
        # fleet 一直未透传 → 缓解波头→尾单向约 25-30 s，波尾车仍在全制动而头车已释放
        # = Q 峰值段速度反转压钩 -2406 kN 的根因；默认 False 零回归）。
        self.eot = bool(config.get('eot', False))
        # 【AD 组 2026-10-17】中置机车制动波源延时透传（0.0=同步多源零回归）
        self.mid_source_delay_s = float(config.get('mid_source_delay_s', 0.0))
        # 紧急顶显式传入（limit=1.5e6 时 2.25×limit=3375 kN 错误，须显式 2.25e6）；
        # None = 旧推导（2.25×limit，编队主线零回归）。
        self.coupler_force_limit_emergency_n = config.get('coupler_force_limit_emergency_n', None)
        # 【E4-H 车钩异构】hetero=True 时逐车钩/逐列独立物理参数（sample_coupler_params），
        # hetero_seed 固定保证可复现；held-out 评估用另一组 seed（训练未见）。
        self.hetero = config.get('hetero', False)
        self.hetero_seed = config.get('hetero_seed', 0)
        self._hetero_rng = np.random.default_rng(self.hetero_seed) if self.hetero else None
        self.layer1_checkpoint = config.get(
            'layer1_checkpoint',
            'outputs/checkpoints/cyclic_mappo_best_seed0_v40-80_init80.pt',  # [40,80]第1层策略（初始80循环制动）
        )
        self.adj_coef = config.get('adj_coef', 0.3)
        # 【bug修复 2026-08-20】eval_mode：评估时第1层策略用确定性采样（消除
        # M1/M3 结果随机性）；训练时 False 保持探索。评估脚本应设 eval_mode=True。
        self.eval_mode = config.get('eval_mode', False)
        initial = config.get('formation_start_randomization', {})
        if not isinstance(initial, dict) or not isinstance(initial.get('enabled', False), bool):
            raise ValueError('formation_start_randomization must be a mapping with boolean enabled')
        self._formation_start = dict(initial)
        self._formation_start_enabled = initial.get('enabled', False)
        self._formation_require_clear_sbi = initial.get('require_clear_sbi', False)
        self._formation_max_attempts = initial.get('max_attempts', 64)
        if not isinstance(self._formation_require_clear_sbi, bool):
            raise ValueError('require_clear_sbi must be a boolean')
        if (isinstance(self._formation_max_attempts, bool)
                or not isinstance(self._formation_max_attempts, int)
                or self._formation_max_attempts < 1):
            raise ValueError('formation max_attempts must be a positive integer')
        if self._formation_start_enabled and self.decompose != 'loco_ed_ab':
            raise ValueError('formation_start_randomization requires decompose=loco_ed_ab')
        self._formation_speed_bounds = self._initial_bounds(initial, 'speed_offset_kmh', [0, 0])
        self._formation_gap_bounds = self._initial_bounds(initial, 'gap_offset_m', [0, 0])
        initial_seed = initial.get('seed')
        self._formation_start_rng = np.random.default_rng(0 if initial_seed is None else initial_seed)
        # 注：方案A（start_offset_m/spacing_m 人为坡段错开）已于 2026-08-20 移除。
        # 它偏离正确场景（各列同坡段起步、随间距保持自然产生动态相位差），
        # 且导致前列/后列缓解持续不同步 → 车钩力持续超限 + M1 训练不收敛。
        # 正确场景 = 普通 reset 布局（各列同坡段起步，见 reset()），协同由场景天然驱动。
        # 【2026-10-06 路线覆盖修复】训练起点随机化（消除 L1 诊断的固定起点 OOD）：
        # 每 episode reset 沿剖面随机前移整个编队，使 ≤1200 步的短训练窗口在**分布**上
        # 覆盖全路（L1：固定起点仅覆盖 −1.5‰ 单坡段，评估 83.9% 的步落在训练未见坡度区间）。
        # 默认关（零回归）；仅训练态生效（eval_mode=True 恒定用基准起点，保证评估可复现）。
        self._start_rand = None
        self._cold_start_max_speed_mps = None
        _sr = config.get('start_randomization', None)
        if isinstance(_sr, dict) and _sr.get('cold_start_max_speed_kmh') is not None:
            cap = _sr['cold_start_max_speed_kmh']
            if (isinstance(cap, bool) or not isinstance(cap, (float, int))
                    or not np.isfinite(cap) or not 0 < cap <= self.v_max * 3.6):
                raise ValueError('cold_start_max_speed_kmh must be finite, positive and <= v_max')
            self._cold_start_max_speed_mps = float(cap) / 3.6
        if isinstance(_sr, dict) and _sr.get('enabled', False):
            self._start_rand = {
                'min_m': float(_sr.get('min_m', 0.0)),
                'max_m': (None if _sr.get('max_m', None) is None else float(_sr['max_m'])),
                'rng': np.random.default_rng(_sr.get('seed', None)),
            }

        # 【2026-09-02 ETCS 集成】多列"真 ATP"（永久启用，安全底线，无开关）：
        # 共享一条 ETCS 制动曲线。前列尾车位置作为后列的前方监督目标（防追尾），
        # 落地 safety_layer 的规则0。（曲线依赖 self.trains，故在本处创建后构建）
        self.etcs_curve = None

        # 每列内部用单列动力学环境（列车内车钩力由此计算）
        # line_speed_limit_mps：场景线路限速（80km/h），传给内层 ATP 安全层作
        # 限速保护 + 超速指标口径（bug修复：原内层用机车物理限速 108km/h）
        self.trains = []
        hetero_rng = np.random.default_rng(self.hetero_seed) if self.hetero else None
        for _ in range(self.num_trains):
            tr_cfg = {
                'consist_preset': self.consist_preset,
                'grade_profile': self.grade_profile,
                'target_speed': self.target_speed,
                'coupler_force_limit_n': self.coupler_force_limit_n,
                # 【2026-10-14 ADR-036 门限落地】紧急顶显式传入（防 limit=1.5e6 时
                # 2.25×limit=3375kN 错误推导）；None=旧行为，编队主线零回归。
                'coupler_force_limit_emergency_n': self.coupler_force_limit_emergency_n,
                # 【I 组】车钩超限干预策略透传（默认 'release' 零回归）
                'coupler_override': self.coupler_override,
                # 【V 组】安全层 AB 新增源 veto 三参数透传（空 = 安全层默认，零回归）
                **self.veto_cfg,
                # 【表3 运营口径】CYCLIC 50kPa 档开关透传内层 env（映射 notch 用）
                'cyclic_notch_50': self.cyclic_notch_50,
                # 【R 组】EOT 双向缓解波透传内层 env（默认 False 零回归）
                'eot': self.eot,
                # 【AD 组】中置机车波源延时透传内层 env（0.0 零回归）
                'mid_source_delay_s': self.mid_source_delay_s,
                'line_speed_limit_mps': self.v_max,
                'dt': self.dt,
                'max_steps': self.max_steps,
                'etcs_curve': self.etcs_curve,
                'decompose': self.decompose,   # decompose 模式下单列 step 走 _step_decomposed
                # 【C7 分级施加 2026-11-07】AB 整档 SERVICE 拆两级（默认关 = 零回归）
                'ab_staged_apply': bool(config.get('ab_staged_apply', False)),
                'ab_zone_apply': bool(config.get('ab_zone_apply', False)),
                'ab_zone_count': int(config.get('ab_zone_count', 2)),
                'ab_zone_rear_notch': str(config.get('ab_zone_rear_notch', 'min')),
                'ab_staged_gap_s': float(config.get('ab_staged_gap_s', 3.0)),
                # 【循环制动减压量 2026-11-08】非紧急循环制动档(SERVICE)减压量当量
                # （None = 140 kPa 零回归；70 = 长大下坡运营口径）
                'service_reduction_kpa': config.get('service_reduction_kpa', None),
            }
            if self.hetero:
                # 逐车钩异构：先用该列一致性预设得到车辆数，再按 (n-1) 个耦合逐钩抽样
                base_consist = CONSIST_PRESETS[self.consist_preset]()
                n_coupling = max(base_consist.num_vehicles - 1, 0)
                tr_cfg['couplers'] = [
                    sample_coupler_params(hetero_rng) for _ in range(n_coupling)
                ]
            self.trains.append(TrainFormationEnv(tr_cfg))
        # ETCS 共享曲线（**永久启用**，安全底线）：制动建立时间 = 车列总长/紧急制动波速 250m/s
        # （对齐 braking.py 波速传播，不用 free_length）；建立期内最不利 = 按剖面
        # 最陡下坡的沿坡加速度继续（最保守）；grade_at 绑定同一条剖面（坡度分量生效）。
        profile = PROFILES[self.grade_profile]()
        train_len = sum(v.length_m for v in self.trains[0].dynamics.consist.vehicles)
        build_up = braking_build_up_from_train(train_len, propagation_speed_mps=250.0)
        steepest_down = min(seg.grade_permille for seg in profile.segments)
        # 【2026-09-03 ATP 修复】原 nominal_emergency_decel=1.6 为旧李蔚法（制动力
        # 系统性偏强 2-4 倍）继承值，与牵规 β_c 法实际紧急制动减速度（1 万吨 1+0：
        # 40/60/80 km/h → 0.426/0.401/0.382 m/s²，tmp_etcs_decel_check.py 实测）
        # 严重不匹配 → EBD/EBI 安全距离仅为实际的 1/4 → ATP 兜不住追尾。
        # 改用实际减速度速度 profile（速度步进，见 EtcsBrakingCurve.nominal_decel）。
        self.etcs_curve = EtcsBrakingCurve(
            speed_profile=[(40.0 / 3.6, 0.426), (60.0 / 3.6, 0.401),
                           (80.0 / 3.6, 0.382)],
            k_dry=1.0,
            brake_build_up_s=build_up,
            assumed_accel_during_buildup=G_RAIL * abs(steepest_down) / 1000.0,
            grade_at=profile.grade_at,
        )
        for tr in self.trains:
            tr.etcs_curve = self.etcs_curve
        # 每列的底层控制器（列内：加速度执行 + 车钩力约束，可开关）
        self.controllers = [
            TrainLowLevelController(
                num_vehicles=tr.num_vehicles,
                dt=self.dt,
                coupler_force_limit_n=self.coupler_force_limit_n,
                enforce_coupler=self.use_coupler_constraint,
                # 【ADR-060】分段限速联动循环制动触发裕量（无表剖面自动失效）
                cyclic_trigger_margin_kmh=self.cyclic_trigger_margin_kmh,
            )
            for tr in self.trains
        ]
        # 分层控制器（2026-08-19 定位确认）：层级二用 RL 第1层策略控速
        # （warm start 自规则循环制动，缓解波下循环制动稳定，E16实测训练稳定avg+2.1万），
        # 层级一 RL 输出协同阈值偏移（v_max_adj/v_min_adj），层级二规则循环制动控速。
        # 【重构 2026-08-22→ADR-013】HierarchicalController 阈值协同（列=智能体的第2层）
        # 已废止：RL 落位收敛为机车级 ED/AB（decompose），不再实例化 HierarchicalController。
        # 保留 self.hierarchical 布尔仅为兼容旧 config 解析；执行统一走非分层/decompose 路径。
        self.hier_controllers = None
        # 【ADR-009.1 2026-09-05 换架构】decompose 模式：每列一个 MultiLocoController
        # 作规则基线（ED 优先 + 逐机车错峰 + AB 兜底），RL 逐机车调制分配。
        self.multi_loco_controllers = None
        if self.decompose:
            self.multi_loco_controllers = [
                MultiLocoController(
                    num_vehicles=tr.num_vehicles,
                    loco_indices=tr.loco_indices,
                    dt=self.dt,
                    max_accel=self.max_accel,
                    coupler_force_limit_n=self.coupler_force_limit_n,
                    enforce_coupler=self.use_coupler_constraint,
                    mask_lever=self.mask_lever,
                    ab_min_refill_s=self.ab_min_refill_s,
                    ab_min_hold_s=self.ab_min_hold_s,
                    ed_grade_feedforward=bool(config.get('ed_grade_feedforward', False)),
                    ed_prelimit=bool(config.get('ed_prelimit', False)),
                    # C4 (ADR-052 diagnostic; 1.0 = default, zero regression)
                    ed_veto_recovery_boost=float(config.get('ed_veto_recovery_boost', 1.0)),
                    # C1 / C3 / C5 (ADR-053 diagnostic switches; defaults are no-ops)
                    cyclic_release_stagger_s=float(config.get('cyclic_release_stagger_s', 0.0)),
                    gap_aware_refill=bool(config.get('gap_aware_refill', False)),
                    refill_gap_reference_m=float(config.get('refill_gap_reference_m', 800.0)),
                    refill_gap_relax_max_s=float(config.get('refill_gap_relax_max_s', 0.0)),
                    refill_gap_relax_span=float(config.get('refill_gap_relax_span', 1.0)),
                    follower_speed_conformance=bool(
                        config.get('follower_speed_conformance', False)),
                    speed_conformance_tol_kmh=float(
                        config.get('speed_conformance_tol_kmh', 1.8)),
                    speed_conformance_gain=float(config.get('speed_conformance_gain', 0.20)),
                    speed_conformance_max=float(config.get('speed_conformance_max', 0.30)),
                    # C6 (ADR-054 diagnostic; defaults off = no-op)
                    leader_brake_feedforward=bool(
                        config.get('leader_brake_feedforward', False)),
                    leader_brake_ff_hold_s=float(config.get('leader_brake_ff_hold_s', 2.0)),
                    leader_brake_ff_duration_s=float(
                        config.get('leader_brake_ff_duration_s', 10.0)),
                    leader_brake_ff_ed_low_frac=float(
                        config.get('leader_brake_ff_ed_low_frac', 0.20)),
                    leader_brake_ff_ed_floor_frac=float(
                        config.get('leader_brake_ff_ed_floor_frac', 0.25)),
                    # 【2026-10-14 朔黄表3 运营口径标定，全默认关=旧行为】
                    cyclic_notch_50=self.cyclic_notch_50,
                    cyclic_brake_trigger_kmh=self.cyclic_brake_trigger_kmh,
                    cyclic_release_kmh=self.cyclic_release_kmh,
                    # 【ADR-060】分段限速联动循环制动触发裕量（无表剖面自动失效）
                    cyclic_trigger_margin_kmh=self.cyclic_trigger_margin_kmh,
                    cyclic_ab_upgrade_kmh=self.cyclic_ab_upgrade_kmh,
                    cyclic_ab_upgrade_notch=self.cyclic_ab_upgrade_notch,
                    ed_release_coordination=self.ed_release_coordination,
                    ed_release_hold_s=self.ed_release_hold_s,
                    ed_release_boost_kn=self.ed_release_boost_kn,
                    # 【2026-11-08】AB 到位率联动 ED 下限（默认关 = 零回归）
                    ed_floor_ab_ready=self.ed_floor_ab_ready,
                    ed_floor_ab_ready_ratio=self.ed_floor_ab_ready_ratio,
                    ed_floor_ab_ready_kn=self.ed_floor_ab_ready_kn,
                    # 【C 组 2026-11-08】ED 撤除时序 + 速度差协同收敛（默认关 = 零回归）
                    ed_release_timing_guard=self.ed_release_timing_guard,
                    ed_release_guard_trigger_frac=self.ed_release_guard_trigger_frac,
                    ed_release_guard_release_frac=self.ed_release_guard_release_frac,
                    ed_release_guard_neighbor_full_frac=(
                        self.ed_release_guard_neighbor_full_frac),
                    ed_release_guard_level_frac=self.ed_release_guard_level_frac,
                    ed_release_guard_hold_s=self.ed_release_guard_hold_s,
                    speed_convergence_share=self.speed_convergence_share,
                    conv_share_tol_kmh=self.conv_share_tol_kmh,
                    conv_share_gain=self.conv_share_gain,
                    conv_share_max=self.conv_share_max,
                    conv_share_lead_share=self.conv_share_lead_share,
                    ed_native_force_conversion=bool(config.get(
                        'ed_native_force_conversion', False)),
                    # 【X 组】ED-AB 波到达协同窗透传（默认 0/1 = 关）
                    ed_upgrade_ramp_s=self.ed_upgrade_ramp_s,
                    ed_upgrade_ramp_scale=self.ed_upgrade_ramp_scale,
                )
                for tr in self.trains
            ]
            # 【S2-v2 2026-11-12】绝对档位模式（loco_notch）的两个可调参数，属性级覆盖，
            # 不改 MultiLocoController 构造签名（旧路径零回归）：
            #   ed_zero_point  : ED 零点，默认 0.77 = 规则层 meanED(0.769)，避免开局欠电制动
            #   ab_notch_hold_s: 档位最短保持秒数，默认 90 = AB 波传播时延（张二田实测）
            if self.decompose == 'loco_notch':
                _zp = float(config.get('ed_zero_point', 0.77))
                _hs = float(config.get('ab_notch_hold_s', 90.0))
                # 【V17】低速强制缓解兜底（默认 off = 零回归）；margin 用 km/h 配置，内部转 m/s
                _lsr = bool(config.get('ab_low_speed_release', False))
                _lsm = float(config.get('ab_low_speed_margin_kmh', 2.0)) / 3.6
                _eia = bool(config.get('ed_idle_action', False))
                for _c in self.multi_loco_controllers:
                    _c.ed_zero_point = _zp
                    _c.ab_notch_hold_s = _hs
                    _c.ab_low_speed_release = _lsr
                    _c.ab_low_speed_margin_mps = _lsm
                    _c.ed_idle_action = _eia
            self.num_agents = sum(len(tr.loco_indices) for tr in self.trains)
        else:
            self.num_agents = self.num_trains
        # 记录每列参考点位置（队首位置，用于列间间距）
        self._train_heads = np.zeros(self.num_trains)
        # 每列初始基准位置（reset 时据此重建，避免跨 reset 累积平移）
        self._base_pos = [np.array(tr.dynamics.pos, dtype=float) for tr in self.trains]

        # 列级观测（E3+E4 增强，借鉴第1层成功设计：位置推断坡度 + 协同预判信息）：
        # [0]=速度误差 [1]=间距误差 [2]=前方坡度(队首) [3]=车钩力均值 [4]=车钩力峰值 [5]=超限数
        # [6]=本列队首位置(归一化,推断坡度剖面) [7]=本列队尾坡度(前方坡度变化)
        # [8]=前列队首速度 [9]=前列是否制动 [10]=前列减速度强度（协同制动预判，E4 新增）
        # [11] [12]=方向B group_obs 追加的全局一致性特征（仅 group_obs=True 时存在）
        self._last_target_accels = np.zeros(self.num_trains)
        if self.decompose:
            # 逐机车观测（ADR-009.1 第3层：AB 状态作观测）——见 _get_obs_decomposed：
            # [0]速度误差 [1]超上限裕量 [2]低下限裕量 [3]规则基线ED [4]规则基线AB
            # [5]本机车局部车钩力 [6]AB激活比例 [7]AB缓解剩余比例 [8]制动段序号
            # [9]本机车位置(归一化) [10]本列列间间距误差（单列=0）
            # [11]【ADR-030】AB 充风就绪度 = 距上次 AB 释放的充风时长 / ab_min_refill_s ∈[0,1]
            #    ——把 222 s 长充风滞后"编码进观测"（文献 Wang2026 的累计缓解时间 t_r 口径），
            #    使策略不必靠"拉长 rollout 窗口"即可感知该长时约束。
            self.obs_dim = 14 if self.formation_relative_speed_obs else 12
            self.observation_schema = {
                'name': ('loco_ed_ab_relative_speed_v1' if self.formation_relative_speed_obs
                         else 'loco_ed_ab_base12'),
                'dimension': self.obs_dim,
                'appended_fields': (['head_relative_speed_mps', 'tail_closing_speed_mps']
                                    if self.formation_relative_speed_obs else []),
                'relative_speed_sign': 'positive means follower is faster',
                'leader_appended_values': [0.0, 0.0] if self.formation_relative_speed_obs else [],
            }
            self.act_dim = 2
            self.observation_space = spaces.Box(
                low=-np.inf, high=np.inf,
                shape=(self.num_agents, self.obs_dim), dtype=np.float32,
            )
            self.action_space = spaces.Box(
                low=-1.0, high=1.0, shape=(self.num_agents, 2), dtype=np.float32,
            )
        else:
            self.obs_dim = 11 + (2 if self.group_obs else 0)
            self.act_dim = self.action_dim
            # 列级动作：每列目标速度偏差 ∈ [-1,1]（RL 输出），映射到实际目标速度
            self.observation_space = spaces.Box(
                low=-np.inf, high=np.inf,
                shape=(self.num_trains, self.obs_dim), dtype=np.float32,
            )
            # 列级动作：每列目标速度偏差 ∈ [-1,1]（RL 输出），映射到实际目标速度
            self.action_space = spaces.Box(
                low=-1.0, high=1.0, shape=(self.num_trains,), dtype=np.float32,
            )

        self.steps = 0
        self._peak_coupler_n = 0.0
        self._coupler_limit_violations = 0
        self._safety_events = 0
        # 【2026-11-08 取舍判据】逐集累计：超速车·步（任一车 >v_max）+ 领航列均速
        self._ep_overspeed_car_steps = 0
        self._ep_head_speed_sum_kmh = 0.0
        self._ep_head_steps = 0
        # E21 追尾趋势：上一步各列间距误差（检测间距缩小→追尾风险，引导RL提前协同）
        self._prev_gap_err = None

    def _load_speed_ref_table(self, path):
        """加载"里程 → 参考速度"表（v7 跟踪项用）。

        表来源 = 规则基线全程归档（`scripts/gen_ref_speed_table.py` 从
        `trajectory.npz` 的 (领航列头位, 领航列头速) 派生）。约定：npz 含 `s_m`/`v_mps`，
        里程单位 m、速度单位 m/s；其余键忽略。

        两条硬约束（缺一即无意义）：
        1. 里程必须单调递增（否则 `np.interp` 结果不确定）⇒ 排序 + 同里程去重。
        2. 参考速度必须 clamp 到 **≤ v_max**——基线自身存在 >80 km/h 的瞬时（实测单车
           最高 80.506 km/h），若把越线速度当奖励目标，等于用奖励诱导超速，与限速验收冲突。
           **下界不 clamp**：基线本就有 11.5% 的步低于 40 km/h（实测 3 618 点），
           把下界抬到 40 会造成"参考目标物理不可达"，让策略与坡道硬顶牛。
        """
        if not path:
            raise ValueError(
                "speed_band_shape='ref' 必须提供 env_cfg.speed_ref_table"
                "（参考速度表 .npz 路径；由 scripts/gen_ref_speed_table.py 生成）")
        p = Path(path)
        if not p.is_file():
            raise FileNotFoundError(f"speed_ref_table 不存在：{p}")
        with np.load(p) as z:
            s = np.asarray(z['s_m'], dtype=np.float64).ravel()
            v = np.asarray(z['v_mps'], dtype=np.float64).ravel()
        if s.size < 2 or s.size != v.size:
            raise ValueError(
                f"speed_ref_table 内容非法：s_m/v_mps 长度 {(s.size, v.size)}，至少 2 点且等长")
        order = np.argsort(s, kind='stable')
        s, v = s[order], v[order]
        keep = np.concatenate([[True], np.diff(s) > 1e-6])
        s, v = s[keep], v[keep]
        if s.size < 2:
            raise ValueError('speed_ref_table 去重后不足 2 点')
        # 【2026-11-13 ADR-068 防白跑】表必须带口径元数据，且与当前 v_max 一致。
        # 旧行为：v > self.v_max 的点被静默 clamp ⇒ 用 80 口径的表配 75 口径的配置，
        # 训练目标仍指向旧口径速度曲线、全程无报错、结果不可比（与 V15 同类的静默失真）。
        meta_path = p.with_name('ref_speed_meta.json')
        if not meta_path.is_file():
            raise FileNotFoundError(
                f"参考速度表缺口径元数据 {meta_path.name}（应随表由 "
                "scripts/gen_ref_speed_table.py 一并产出）；无元数据无法校验表与 v_max 同源")
        with open(meta_path, encoding='utf-8') as f:
            meta = json.load(f)
        src_vmax = meta.get('clamp_upper_mps')
        if src_vmax is None:
            raise ValueError(
                f"{meta_path.name} 缺 clamp_upper_mps 字段，无法校验口径；请重生成该表")
        if abs(float(src_vmax) - float(self.v_max)) > 1e-9:
            raise ValueError(
                f"参考速度表口径不一致：{p.name} 由 v_max={float(src_vmax) * 3.6:.1f} km/h 生成，"
                f"当前配置 v_max={self.v_max * 3.6:.1f} km/h。按 ADR-068「六量同批」纪律不得混用 —— "
                "先用新口径基线跑产出 trajectory.npz，再跑 scripts/gen_ref_speed_table.py 重生成")
        self._ref_v_clamped = int(np.count_nonzero(v > self.v_max))
        v = np.minimum(v, self.v_max)
        self._ref_s_m = s
        self._ref_v_mps = v
        _logger.info(
            "[ref-speed] 加载参考速度表 %s：%d 点，里程 %.1f–%.1f m，"
            "参考速度 %.2f–%.2f km/h（越线被 clamp 的点 %d 个）",
            p, s.size, s[0], s[-1], v.min() * 3.6, v.max() * 3.6, self._ref_v_clamped)

    def _ref_speed_at(self, pos_m: float) -> float:
        """按里程线性插值取参考速度（越界自动 clamp 到首/末点）。"""
        if self._ref_s_m is None:
            raise RuntimeError('参考速度表未加载（speed_band_shape 非 ref 时不应调用）')
        return float(np.interp(float(pos_m), self._ref_s_m, self._ref_v_mps))

    def _ref_lookup(self) -> float:
        """按**线路绝对里程**（领航列车头位置）查参考速度。

        表内 `s_m` 为绝对里程（`s_basis='absolute_profile_m'`），故直接按头位插值，
        与编队起点如何摆放无关（越界由 `np.interp` clamp 到首/末点）。
        修订前为"按自本集起点已行驶里程"查归零表，起点一改就须重建表（见
        scripts/gen_ref_speed_table.py 的修订说明）。
        """
        return self._ref_speed_at(float(self._train_heads[0]))

    def _line_vmax_for(self, ti: int) -> float:
        """【ADR-060 限速逐段联动】该列的联动线路限速（m/s）。

        = min(常数 v_max, 分段限速表在该列头车位置的值)。内层 env 无限速表
        （恒坡/沙盒剖面）或查表 None → 恒 self.v_max（零回归）。
        供超速计数 / 奖励 speed_band·speed_over 越线判定 / 循环制动触发联动。
        """
        tr = self.trains[ti]
        lookup = getattr(tr, 'line_limit_lookup_kmh', None)
        if lookup is not None:
            lv = lookup(float(tr.dynamics.pos[0]))
            if lv is not None:
                return min(self.v_max, lv / 3.6)
        return self.v_max

    @staticmethod
    def _initial_bounds(config, name, default):
        values = np.asarray(config.get(name, default), dtype=float)
        if values.shape != (2,) or not np.all(np.isfinite(values)) or values[0] > values[1]:
            raise ValueError(f'formation_start_randomization.{name} needs finite [min, max]')
        return values

    def _sample_formation_start(self, speed_mps, seed):
        speeds = np.full(self.num_trains, float(speed_mps))
        gaps = np.full(max(0, self.num_trains - 1), self._formation_ref_gap())
        sampled = self._formation_start_enabled and not self.eval_mode
        if sampled:
            low, high = self._formation_speed_bounds / 3.6 + speed_mps
            if low < 0 or high > self.v_max:
                raise ValueError('formation speed offset range exceeds [0, v_max]; no clipping')
            if self._formation_ref_gap() + self._formation_gap_bounds[0] <= 0:
                raise ValueError('formation gap offset range permits overlapping trains')
            if seed is not None:
                self._formation_start_rng = np.random.default_rng(seed)
            speeds += self._formation_start_rng.uniform(*self._formation_speed_bounds,
                                                       size=self.num_trains) / 3.6
            gaps += self._formation_start_rng.uniform(*self._formation_gap_bounds,
                                                     size=max(0, self.num_trains - 1))
        return speeds, gaps, sampled

    def _initial_formation_info(self, sampled):
        context = self.get_formation_context()
        supervision = []
        for i in range(1, self.num_trains):
            tr = self.trains[i]
            previous = self.trains[i - 1].dynamics
            ebi, sbi = tr.safety._etcs_check(
                float(tr.dynamics.pos[0]), float(tr.dynamics.vel[0]), self.etcs_curve,
                [EbdTarget(position_m=float(previous.pos[-1]),
                           speed_mps=float(previous.vel[0]), kind='gap')])
            speed = float(tr.dynamics.vel[0])
            supervision.append({'train_index': i,
                                'above_sbi': sbi is not None and speed > sbi + 1e-6,
                                'above_ebi': ebi is not None and speed > ebi + 1e-6})
        return {'formation_initialization': {'sampled': sampled, 'context': context,
                                             'supervision': supervision}}

    def _sample_start_offset(self) -> float:
        """训练起点随机化：均匀采样编队整体前移量（米）。

        【2026-10-21 边界修复】旧实现 `span = route_len - platoon_len - 3000` 只留 3000 m
        固定余量，与本集实际行程无关，导致两类静默失真（`grade_at` 对越界位置不报错，
        直接沿用首/末段坡度 → 训练分布混入真实线路上不存在的路况）：

          1) 下界为 0：队尾落在 ``−platoon_len``（线路起点之前，≈ −8 km）；
          2) 上界过高：长窗口（如 1200 s ≈ 22 km 行程）时队首跑出线路末端最多 ≈ 11.7 km，
             实测约 40% 的 episode 含虚构路段。

        新实现按**本集实际行程**收边界，保证「队尾 ≥ 0」且「队首 + 行程 ≤ 线路末端」：
            lo = platoon_len + margin
            hi = route_len − horizon·dt·v_max − margin
        行程按 ``v_max`` 取上界，故任何速度下都不会越界。

        退化情形（窗口行程 ≥ 线路可用长度，如全剖面 36000 步）下无法在保证不越界的前提下
        随机化，退化为固定起点 ``lo`` 并置 ``_start_rand_degenerate=True``（调用方可据此记日志）。
        剖面为常量坡度（无 segments）时返回 0。
        """
        prof = getattr(self.trains[0].dynamics, '_grade_profile', None)
        if prof is None or not prof.segments:
            return 0.0
        route_len = max(seg.start_m for seg in prof.segments)
        train_len = abs(self._base_pos[0][0] - self._base_pos[0][-1])
        platoon_len = (train_len * len(self.trains)
                       + self._formation_ref_gap() * (len(self.trains) - 1))
        # 本集行程上界（米）：用 v_max 保守估计，保证任何速度下队首都不越过线路末端
        horizon = int(getattr(self, 'max_steps', 0) or 0)
        dt = float(getattr(self, 'dt', 0.1) or 0.1)
        v_upper = max(float(getattr(self, 'v_max', 0.0) or 0.0), 1e-6)
        window_m = max(0.0, float(horizon) * dt * v_upper)
        margin = 500.0

        safe_lo = platoon_len + margin
        safe_hi = route_len - window_m - margin
        explicit_max = self._start_rand['max_m']

        if explicit_max is not None:
            # 显式 [min_m, max_m] = 调用方的研究意图（如固定落在某一坡段起点），
            # 保留原语义；只裁剪到物理合法范围 [0, route_len]，越出安全窗口记标志。
            lo = float(np.clip(self._start_rand['min_m'], 0.0, route_len))
            hi = float(np.clip(float(explicit_max), lo, route_len))
            self._start_rand_degenerate = not (lo >= safe_lo and hi <= safe_hi)
            return float(self._start_rand['rng'].uniform(lo, hi))

        # 默认（未显式指定）：按本集实际行程收边界，保证整列与整段行程都在线路内
        lo = max(safe_lo, float(self._start_rand['min_m']))
        hi = safe_hi
        if hi <= lo:
            # 本集窗口 ≥ 线路可用长度（如全剖面 36000 步，或 max_steps 仍是评估上限
            # 35000 的裸构造场景）：无法在保证不越界的前提下随机化。
            # 退回旧口径 [0, route_len − platoon_len − 3000] 以保留随机性，
            # 同时置 degenerate 标志（调用方/日志可据此判断本集可能含虚构延伸路段）。
            self._start_rand_degenerate = True
            span = max(0.0, route_len - platoon_len - 3000.0)
            lo = float(np.clip(self._start_rand['min_m'], 0.0, span))
            hi = span
            if hi <= lo:
                return float(lo)
            return float(self._start_rand['rng'].uniform(lo, hi))
        self._start_rand_degenerate = False
        return float(self._start_rand['rng'].uniform(lo, hi))

    def reset(self, seed=None, options=None):
        """Optionally reject supervised initial states, with a bounded audit trail."""
        if seed is not None and self._start_rand is not None:
            # Explicit reset seeds must replay the route offset too, not only
            # the formation-speed RNG. Rejection retries advance this RNG.
            self._start_rand['rng'] = np.random.default_rng(seed)
        filter_initial = (self._formation_start_enabled and not self.eval_mode
                          and self._formation_require_clear_sbi)
        attempts = self._formation_max_attempts if filter_initial else 1
        rejected_sbi = rejected_ebi = 0
        for attempt in range(attempts):
            obs, info = self._reset_once(seed=seed if attempt == 0 else None, options=options)
            initial = info.get('formation_initialization')
            if filter_initial:
                statuses = initial['supervision']
                above_sbi = any(s['above_sbi'] for s in statuses)
                above_ebi = any(s['above_ebi'] for s in statuses)
                rejected_sbi += int(above_sbi)
                rejected_ebi += int(above_ebi)
                accepted = not above_sbi and not above_ebi
            else:
                accepted = True
            if accepted:
                if initial is not None:
                    initial.update(attempts=attempt + 1,
                                   rejected_sbi_candidates=rejected_sbi,
                                   rejected_ebi_candidates=rejected_ebi,
                                   require_clear_sbi=bool(filter_initial))
                return obs, info
        raise ValueError(f'No clear-SBI formation initial state after {attempts} attempts; '
                         'revise the configured distribution, not safety thresholds')

    def _reset_once(self, seed=None, options=None):
        self.steps = 0
        self._peak_coupler_n = 0.0
        self._coupler_limit_violations = 0
        self._safety_events = 0
        self._ep_overspeed_car_steps = 0
        self._ep_head_speed_sum_kmh = 0.0
        self._ep_head_steps = 0
        self._last_target_accels = np.zeros(self.num_trains)
        self._prev_gap_err = None
        # 【E4-H domain randomization】训练态（非 eval_mode）每 episode reset 重新抽取
        # 逐车钩异构参数，让策略在分布上训练；评估（held-out）用构造时 fix 抽取保持不变。
        if self.hetero and not self.eval_mode and self._hetero_rng is not None:
            base_consist = CONSIST_PRESETS[self.consist_preset]()
            n_coupling = max(base_consist.num_vehicles - 1, 0)
            for tr in self.trains:
                tr.dynamics.set_couplers(
                    [sample_coupler_params(self._hetero_rng) for _ in range(n_coupling)]
                )
        # decompose 模式：每机车 (ED,AB) 2 维；旧模式：每列 1 维 throttle
        self._executed_actions = (
            np.zeros((self.num_agents, 2)) if self.decompose
            else np.zeros(self.num_agents)
        )

        # 记录每列参考点位置（队首位置，用于列间间距）
        cumulative_offset = 0.0
        # 初始速度：对齐 Zhang2024 长大下坡循环制动初始速度 65 km/h（18.06 m/s）
        init_speed = (options or {}).get('speed', 65.0 / 3.6)
        initial_speeds, initial_gaps, sampled_formation = self._sample_formation_start(init_speed, seed)
        requested_speeds = initial_speeds.copy()
        cold_start_policy = (self._start_rand is not None and not self.eval_mode
                             and self._cold_start_max_speed_mps is not None)
        if cold_start_policy:
            # Explicit training-distribution change, not an actuator clamp or
            # safety guarantee. A common shift preserves relative train speeds.
            shift = max(0.0, float(initial_speeds.max()) - self._cold_start_max_speed_mps)
            initial_speeds -= shift
            if np.any(initial_speeds < 0):
                raise ValueError('cold-start speed shift would create a negative train speed')
        # 训练起点随机化：整列编队沿剖面随机前移（route_offset=0 时零回归）
        # 【2026-11-08 队尾负里程修复】评估态不再恒用 0，而是取配置的**最小起点**
        # （`min_m=max_m` 时即固定起点）：否则评估从 0 起步、队尾落在 −platoon_len
        # （≈ −4.25 km），`grade_at` 对越界位置静默沿用首段坡度 ⇒ 后两列跑虚构路况，
        # 训练/评估不同源。`min_m=0`（旧配置）时与历史零回归。
        route_offset = 0.0
        if self._start_rand is not None:
            if self.eval_mode:
                route_offset = float(self._start_rand['min_m'])
            else:
                route_offset = self._sample_start_offset()
        for i, (tr, ctrl) in enumerate(zip(self.trains, self.controllers)):
            tr.reset(options={'speed': initial_speeds[i]})
            ctrl.reset()
            if self.multi_loco_controllers is not None:
                self.multi_loco_controllers[i].reset()
            tr.dynamics.reset_energy()  # 重置能耗累计（避免跨回合累积）
            # 从基准初始位置重建（避免跨 reset 的累积平移）
            base_pos = self._base_pos[i].copy()
            if i == 0:
                # 领航列在原点（各列同坡段起步，普通场景）；
                # route_offset>0 = 训练起点随机化整体前移（见 _sample_start_offset）
                tr.dynamics.set_initial(pos=base_pos + route_offset, vel=tr.dynamics.vel)
            else:
                # 跟随列：整列向后平移（列内长度 + 动态目标间距，E4 时间间隔）。
                # 各列同坡段起步，随编队推进自然产生动态相位差（真实编队总长~4km，
                # 前列后列进入同一坡段的时机天然不同）——协同由场景驱动，非人为错开。
                train_len = abs(base_pos[0] - base_pos[-1])
                init_gap = initial_gaps[i - 1]
                offset = train_len + init_gap
                cumulative_offset += offset
                tr.dynamics.set_initial(
                    pos=base_pos - cumulative_offset + route_offset,
                    vel=tr.dynamics.vel,
                )
            self._train_heads[i] = float(tr.dynamics.pos[0])
        # 【参考速度基准 2026-11-08 修订】参考表用**线路绝对里程**索引（见 _ref_lookup），
        # 故这里不再记"本集起点原点"；编队起点由 start_randomization 的固定段决定。
        if self._ref_s_m is not None:
            # 口径校验：旧表是归零口径（表首 ≈ 0），配前移起点会整段 clamp 到首点
            # （跟踪项恒指向同一速度、静默失真）⇒ 正向偏差直接报错，不猜。
            # 反向（起点在表首之前）只告警：np.interp clamp 到首点，前几公里降级但可跑。
            gap_m = float(self._train_heads[0]) - float(self._ref_s_m[0])
            if gap_m > 2000.0:
                raise ValueError(
                    f'参考速度表与编队起点里程不匹配：表首 {self._ref_s_m[0]:.1f} m、'
                    f'领航列头位 {self._train_heads[0]:.1f} m（差 {gap_m:+.1f} m）。'
                    '表必须是线路绝对里程口径（scripts/gen_ref_speed_table.py 生成），'
                    '且编队起点须落在表的覆盖区间内。')
            if gap_m < -500.0:
                # 【2026-11-08】起点在表首之前**不报错**，只告警：训练/评估主配置的
                # 起点由 start_randomization 固定段保证落在表内（4300 ≥ 表首 4291.9）；
                # 越界只出现在单测或历史复现里把起点显式置 0 的场景，此时前几公里
                # np.interp 会 clamp 到首点速度，属已知降级行为，不应让整条链路崩掉。
                _logger.warning(
                    '参考速度表早于编队起点 %.1f m（表首 %.1f m），起点之前按首点速度 clamp；'
                    '若为正式训练请把 start_randomization 起点设到 ≥ %.0f m（真实剖面内）。',
                    -gap_m, self._ref_s_m[0], self._ref_s_m[0])
        if self.decompose:
            initial_info = (self._initial_formation_info(sampled_formation)
                            if self._formation_start_enabled else {})
            if cold_start_policy:
                initial_info['cold_start_initialization'] = {
                    'mode': 'cold_zero_air',
                    'max_speed_kmh': self._cold_start_max_speed_mps * 3.6,
                    'requested_speeds_kmh': (requested_speeds * 3.6).tolist(),
                    'actual_speeds_kmh': (initial_speeds * 3.6).tolist(),
                    'common_speed_shift_kmh': shift * 3.6,
                    'route_offset_m': route_offset,
                    'feasibility_guaranteed': False,
                }
            return self._get_obs_decomposed(), initial_info
        return self._get_obs(), {}

    def _atp_safe_gap(self, i: int):
        """第 i 列相对前列的 **ATP 制动安全距离 d_safe**（m）——与安全层 ATP 判据同源。

        d_safe = 后列从当前速度、当前位置，把速度降到**前列当前速度**所需距离
        （`EtcsBrakingCurve.braking_distance`：含制动建立期 + 真实坡度分量）。ATP 恰在
        `实际间距 < d_safe` 时介入（ETCS EBI）⇒ 本值即"贴线不越线"的那条线。

        返回 None 表示不可计算（无 ETCS 曲线 / 制动无效 / 非跟随列），调用方回退
        `_fallback_d_safe` / `_formation_ref_gap`。
        """
        curve = getattr(self, 'etcs_curve', None)
        if curve is None or i <= 0 or i >= self.num_trains:
            return None
        lead_tail = float(self.trains[i - 1].dynamics.pos[-1])
        lead_v = float(self.trains[i - 1].dynamics.vel[0])
        head = float(self._train_heads[i])
        if lead_tail <= head:
            return 0.0
        try:
            d = curve.braking_distance(
                float(self.trains[i].dynamics.vel[0]), head,
                EbdTarget(position_m=lead_tail, speed_mps=lead_v, kind='gap'))
        except Exception:
            return None
        return float(d) if np.isfinite(d) else None

    def _fallback_d_safe(self) -> float:
        """无 ETCS 曲线时的简化制动安全距离 fallback（m）。

        物理同源：d = v²/(2·a_ref) + v·t_react（a_ref=1.5 m/s² 取 ATP 紧急减速度
        量级，t_react=2 s 制动建立与反应余量）。替代已删除的无锚 100m/5s 常数
        （ADR-061：100m 为早期默认值自证"拍脑袋"，5s 落在公路 CACC 0.5-1.5s 与
        铁路 VC 货运 ~40s 之间两头不锚）。
        """
        v = max(float(self.target_speed), 1.0)
        return v * v / (2.0 * 1.5) + v * 2.0

    def _formation_ref_gap(self, i: int = None) -> float:
        """编队参考间距 d_eff = GAP_EFF_MARGIN × d_safe（ATP 同源，ADR-061）。

        全部间距语义（初始布置默认 / obs[1] / decomposed obs[10] / 规则协调
        gap_err / 势场惩罚 / 诊断参考线）统一使用本函数；奖励 gap_eff/gap_danger
        本就以 d_eff/d_safe 为目标。第 i 列 d_safe 不可算时退化为简化制动模型的
        d_eff（_fallback_d_safe）。旧 `_dynamic_gap`（100m + 5s×v = 恒 200m）已删。
        """
        d = self._atp_safe_gap(i) if i is not None else None
        if d is None:
            d = self._fallback_d_safe()
        return GAP_EFF_MARGIN * d

    def _get_obs(self) -> np.ndarray:
        """构造每列观测（E3 增强）。

        [0]=速度误差 [1]=间距误差 [2]=前方坡度(队首) [3]=车钩力均值 [4]=车钩力峰值 [5]=超限数
        [6]=本列队首位置(归一化,推断坡度剖面位置) [7]=本列队尾坡度(前方坡度变化预判)
        [8]=前列队首速度 [9]=前列是否制动 [10]=前列减速度强度（协同制动预判，跟随车用；领航列=自身）
        """
        obs = np.zeros((self.num_trains, self.obs_dim), dtype=np.float32)
        # 先算各列队首速度（协同预判用）
        head_speeds = np.array([tr.dynamics.vel[0] for tr in self.trains])
        for i, tr in enumerate(self.trains):
            # 每列内部车钩力
            coupler = np.abs(tr.dynamics._coupler_forces())
            coupler_mean = np.mean(coupler) if len(coupler) else 0.0
            coupler_peak = np.max(coupler) if len(coupler) else 0.0
            viol = int(np.sum(coupler > self.coupler_force_limit_n))

            # 列间间距误差：前车（i-1）尾部 vs 本列队首 - 编队参考间距 d_eff（ATP 同源）
            # 【ADR-061】参考 = _formation_ref_gap(i)（1.1×d_safe，与奖励 gap_eff 同口径）
            gap_err = 0.0
            if i > 0:
                prev_tail = self.trains[i - 1].dynamics.pos[-1]
                d_eff = self._formation_ref_gap(i)
                gap_err = (prev_tail - self._train_heads[i]) - d_eff

            # 坡度：队首（当前）与队尾（前方将遇到）所在坡度
            grade_head = float(tr.dynamics.grade[0]) if hasattr(tr.dynamics, 'grade') else 0.0
            grade_tail = float(tr.dynamics.grade[-1]) if hasattr(tr.dynamics, 'grade') else grade_head

            # 本列队首位置归一化（用于推断坡度剖面位置，借鉴第1层 pos*0.0001）
            pos_norm = float(tr.dynamics.pos[0]) * 0.0001
            # 前列状态（跟随车预判协同制动；领航列用自身）
            prev_speed = head_speeds[i - 1] if i > 0 else head_speeds[i]
            prev_accel = self._last_target_accels[i - 1] if i > 0 else self._last_target_accels[i]
            prev_braking = float(prev_accel < -0.05)   # 前列是否正在制动（目标加速度<0）
            prev_decel = float(min(prev_accel, 0.0)) / max(self.max_accel, 1e-6)  # 前列减速度强度 ∈[-1,0]

            obs[i, 0] = tr.dynamics.vel[0] - self.target_speed   # 速度误差
            obs[i, 1] = gap_err                                   # 列间间距误差
            obs[i, 2] = grade_head                                # 前方坡度(队首)
            obs[i, 3] = coupler_mean / self.coupler_force_limit_n  # 车钩力均值（归一化）
            obs[i, 4] = coupler_peak / self.coupler_force_limit_n  # 车钩力峰值（归一化）
            obs[i, 5] = float(viol)                                # 车钩力超限次数
            obs[i, 6] = pos_norm                                   # 本列队首位置（推断坡度）
            obs[i, 7] = grade_tail                                 # 本列队尾坡度（前方坡度变化）
            obs[i, 8] = prev_speed / self.v_max                    # 前列速度（协同预判，归一化）
            obs[i, 9] = prev_braking                               # 前列是否制动（E4 协同预判）
            obs[i, 10] = prev_decel                                # 前列减速度强度（E4 协同预判）

        # 【方向B 2026-09-04】全局一致性观测（修根因3）：群组速度一致度 + 制动相位一致度。
        # 让每个智能体都能感知整个群组是否"拧成一股绳"（速度齐、制不制动同步），
        # 而非只盯前列——帮助 RL 学习一致协同而非各自为政。
        if self.group_obs:
            head_speed_std = float(np.std(head_speeds)) / max(self.v_max, 1e-6)
            braking = (np.abs(self._last_target_accels) > 0.05).astype(float)
            frac_braking = float(np.mean(braking)) if len(braking) else 0.0
            obs[:, 11] = head_speed_std
            obs[:, 12] = frac_braking
        return obs

    def step(self, actions: np.ndarray):
        """推进所有列车一步。

        Args:
            actions: decompose 模式 = 每机车 [ed_mod, ab_mod] ∈ [-1,1]²（(num_agents,2)）；
                否则为每列目标速度偏差 ∈ [-1,1]，长度 = num_trains。
        """
        if self.decompose:
            return self._step_decomposed_fleet(actions)
        actions = np.asarray(actions, dtype=float).reshape(self.num_trains, self.action_dim)
        if actions.size != self.num_trains * self.action_dim:
            raise ValueError(
                f"动作元素数应为 {self.num_trains * self.action_dim}, 实际 {actions.size}"
            )

        reward = 0.0
        self._safety_events = 0
        target_accels = np.zeros(self.num_trains)  # 记录每列实际目标加速度（奖励判断用）
        accels = np.zeros(self.num_trains)         # 记录每列实际加速度（舒适性奖励项）
        executed_throttles = np.zeros(self.num_trains)  # 每列实际执行 throttle（安全层修正后）
        for i, (tr, ctrl) in enumerate(zip(self.trains, self.controllers)):
            # 记录步前速度（算实际加速度用）
            v_before = float(tr.dynamics.vel[0])

            if self.hierarchical:
                # 【ADR-013 已废止】HierarchicalController 阈值协同（列=智能体的第2层）
                # 不再使用。hierarchical=True 旧 config 退化为"目标加速度直控"（与第1层
                # 底层控制器 get_action_accel 一致），避免旧配置崩溃、主路径不残留废止代码。
                target_accel = float(actions[i, 0]) * self.max_accel
                if self.enable_disturbance and i == 0 and self.disturbance_step <= self.steps < self.disturbance_step + self.disturbance_duration:
                    target_accel = self.disturbance_target_accel
                target_accels[i] = target_accel
                col_actions = ctrl.get_action_accel(tr, target_accel)
            else:
                # 非分层模式：层级一动作 → 该列目标加速度（动作直接影响物理）
                target_accel = float(actions[i, 0]) * self.max_accel
                # 领航车（第0列）扰动：突发强制制动（模拟前方障碍/限速），
                if self.enable_disturbance and i == 0 and self.disturbance_step <= self.steps < self.disturbance_step + self.disturbance_duration:
                    target_accel = self.disturbance_target_accel
                target_accels[i] = target_accel
                # 层级二底层控制器：目标加速度 → 列级 throttle（执行 + 车钩力约束）
                col_actions = ctrl.get_action_accel(tr, target_accel)

            # 记录实际执行 throttle（分层/映射模式取第0节，即整列统一动作）
            executed_throttles[i] = float(col_actions[0])
            # 关键：RL 输出的列级动作（δ 协同调整 / 目标加速度）经底层控制器
            # 确定性映射为 throttle 后才执行。策略分布定义在"RL 输出动作"空间，
            # log_prob 应基于原始 RL 动作计算，无需用 throttle 重算（V5.1 教训
            # 仅适用于"同一动作空间内的安全层修正"，如 train_cyclic_braking）。
            # 此处仅记录实际执行 throttle 供 info 诊断，不覆盖 RL 动作。
            self._executed_actions[i] = executed_throttles[i]
            # 【2026-09-02 ETCS 集成】后列的前方监督目标 = 前列尾车当前位置（实时），
            # 目标速度 = 编队巡航参考速度（后列须在到达前列尾前降到该速度 → 防追尾）。
            # 领航列（i=0）无前列，不设目标；其线速上限由反应式限速兜底。
            # 【2026-09-02 修复】目标速度用**前列当前实时速度**而非固定 target_speed：
            # 前列循环制动降速（≤40km/h）时若后列仍被允许按 16.7m/s 逼近前列尾，
            # EBD 预留距离不足以应对"前列更慢" → 后列穿透前列（35km 长坡实测
            # 28581/35000 步 gap<5m、min=-5401m）。正确语义：后列须在到达前列尾前
            # 降到前列当前速度，才真正防追尾。
            if i > 0:
                leading_tail = float(self.trains[i - 1].dynamics.pos[-1])
                lead_speed = float(self.trains[i - 1].dynamics.vel[0])
                # 【ADR-053 C3/C5 诊断】把编队净空与领航速度暴露给该列控制器；
                # 开关关闭时控制器不读取（getattr 默认 None），零回归。
                tr.formation_clear_gap_m = leading_tail - float(tr.dynamics.pos[0])
                tr.formation_leader_speed_kmh = lead_speed * 3.6
                tr.formation_release_delay_s = self.cyclic_release_stagger_per_train_s * i
                tr.set_etcs_targets([EbdTarget(
                    position_m=leading_tail, speed_mps=lead_speed, kind='gap',
                )])
            if (self.leader_brake_feedforward and self.multi_loco_controllers is not None
                    and i + 1 < len(self.trains)):
                js = (range(i + 1, len(self.trains)) if self.leader_brake_ff_scope == 'all'
                      else (i + 1,))
                rear_braking = False
                rear_ed_frac = 1.0
                for j in js:
                    c = self.multi_loco_controllers[j]
                    ab_on = getattr(c, '_ab_on', None)
                    if ab_on is not None and np.any(np.asarray(ab_on)):
                        rear_braking = True
                    prev = getattr(c, '_previous_ed', None)
                    if prev is not None:
                        rear_ed_frac = min(
                            rear_ed_frac, float(np.mean(np.abs(np.asarray(prev)))))
                # 【ADR-054 C6 诊断】后部列制动/ED 近零 → 前部列需建立最小 ED；
                # 开关关闭时不下发，控制器不读取（零回归）。
                tr.formation_rear_braking = rear_braking
                tr.formation_rear_ed_frac = rear_ed_frac
            tr.step(col_actions)
            self._train_heads[i] = float(tr.dynamics.pos[0])
            # 【2026-11-08 超速口径】车·步计数（任一车 >v_max 即计 1）：逐集累计，
            # 供"峰值下降是否以超速上升为代价"的取舍判据（见 DIAGNOSTICS 小节（十八））。
            # 【ADR-060 限速逐段联动】越线门 = 该列联动限速（无表剖面 = self.v_max 零回归）
            self._ep_overspeed_car_steps += int(
                np.count_nonzero(tr.dynamics.vel > self._line_vmax_for(i)))
            # 实际加速度 = (新速度 - 旧速度) / dt（舒适性奖励项，对齐 Hua2024 w3·u²）
            accels[i] = (float(tr.dynamics.vel[0]) - v_before) / max(self.dt, 1e-6)

            # 该列车钩力指标（**断面力口径** coupler_interface_forces，长度 n-1；列内累计）
            # 【2026-09-30 治本】原用每车净力 _coupler_forces → 拉压交界处矢量和误报/漏报
            interface = np.abs(tr.dynamics.coupler_interface_forces())
            if interface.size:
                self._peak_coupler_n = max(self._peak_coupler_n, float(np.max(interface)))
                self._coupler_limit_violations += int(
                    np.sum(interface > self.coupler_force_limit_n))
            self._safety_events += tr._safety_events

        # 记录本步各列目标加速度（供 obs 的"前列制动状态"，E4 协同预判用）
        self._last_target_accels = target_accels.copy()
        self._ep_head_speed_sum_kmh += float(self.trains[0].dynamics.vel[0]) * 3.6
        self._ep_head_steps += 1

        obs = self._get_obs()
        reward = self._calculate_reward(obs, target_accels, accels, executed_throttles)

        self.steps += 1
        terminated = False
        # 【2026-11-08】头车到剖面末端即截断（越界段无真实坡度）；max_steps 仅作时间上限
        route_end = (self.route_end_m is not None
                     and float(self._train_heads[0]) >= self.route_end_m)
        truncated = bool(route_end or self.steps >= self.max_steps)

        info = {
            'reward': reward,
            'coupler_force_peak': float(self._peak_coupler_n),
            'coupler_force_limit': float(self.coupler_force_limit_n),
            'coupler_limit_violations': int(self._coupler_limit_violations),
            'safety_events': int(self._safety_events),
            # 【2026-11-08 截断口径】本步是否因"头车到达剖面末端"而结束（区分步数上限）
            'route_end_reached': bool(route_end),
            'head_position_m': float(self._train_heads[0]),
            # 【2026-11-08 取舍判据】逐集累计超速车·步 + 领航列均速（km/h）
            'overspeed_car_steps': int(getattr(self, '_ep_overspeed_car_steps', 0)),
            'head_speed_mean_kmh': (
                float(self._ep_head_speed_sum_kmh) / max(int(self._ep_head_steps), 1)),
            # 列间间距监控（2026-09-23 新增，训练日志 CSV/TB 用）
            **dict(zip(('gap_err_mean', 'gap_min_m'), self._gap_metrics())),
            # 实际执行 throttle（列级，供诊断/评估）
            'executed_actions': self._executed_actions.copy(),
            # 恒 False：RL 输出动作（δ 协同 / 目标加速度）经确定性映射才执行，
            # 策略分布定义在 RL 动作空间，log_prob 应基于原始动作，无需重算。
            # （V5.1 教训仅针对"同一动作空间内安全层修正"，见 train_cyclic_braking）
            'actions_modified': False,
        }
        return obs, reward, terminated, truncated, info

    # ------------------------------------------------------------------ #
    # 【ADR-009.1 2026-09-05 换架构】decompose='loco_ed_ab'：逐机车 RL 智能体
    # ------------------------------------------------------------------ #
    def _get_obs_decomposed(self) -> np.ndarray:
        """逐机车观测（含 AB 状态，ADR-009.1 第3层：让策略"感知"AB 动态而非预测）。

        每台机车（智能体）12 维：
        [0]速度误差 [1]超上限裕量(vel-v_max) [2]低下限裕量(vel-v_min)
        [3]规则基线ED [4]规则基线AB(0/1) [5]本机车局部车钩力(归一化)
        [6]AB激活比例 [7]AB缓解剩余比例 [8]制动段序号(缩放)
        [9]本机车位置(归一化) [10]本列列间间距误差（单列=0）
        [11]AB 充风就绪度(ADR-030)：距上次 AB 释放的充风时长 / ab_min_refill_s ∈[0,1]
        """
        obs = np.zeros((self.num_agents, self.obs_dim), dtype=np.float32)
        context = self.get_formation_context() if self.formation_relative_speed_obs else None
        a = 0
        for ti, (tr, ctrl) in enumerate(zip(self.trains, self.multi_loco_controllers)):
            dyn = tr.dynamics
            vel = float(dyn.vel[0])
            gap_err = 0.0
            if ti > 0:
                prev_tail = self.trains[ti - 1].dynamics.pos[-1]
                gap_err = (prev_tail - self._train_heads[ti]) - self._formation_ref_gap(ti)
            # 规则基线（ED 优先 + 错峰 + AB 兜底）——观测告诉 RL"规则本步想做什么"
            # Observations must not advance any controller clock, latch or
            # future mutable state. Preview on an isolated controller copy.
            base = deepcopy(ctrl).get_action_cyclic_braking(
                tr, v_max=self.v_max, v_min=self.v_min)
            coupler = np.abs(dyn._coupler_forces())
            ab_state = dyn.air_brake_state()
            ab_active_frac = float(np.mean([x != AirBrakeNotch.RELEASE for x in ab_state]))
            ab_release_frac = float(np.mean(np.asarray(dyn._air_brake_release_frac, dtype=float)))
            for k, loco_idx in enumerate(tr.loco_indices):
                obs[a, 0] = vel - self.target_speed
                obs[a, 1] = vel - self.v_max
                obs[a, 2] = vel - self.v_min
                obs[a, 3] = float(base[k, 0])
                obs[a, 4] = 1.0 if base[k, 1] < 0 else 0.0
                obs[a, 5] = float(coupler[loco_idx]) / self.coupler_force_limit_n
                obs[a, 6] = ab_active_frac
                obs[a, 7] = ab_release_frac
                obs[a, 8] = float(dyn._brake_segment) / 10.0
                obs[a, 9] = float(dyn.pos[loco_idx]) * 0.0001
                obs[a, 10] = gap_err
                # [11] AB 充风就绪度（ADR-030）：距上次 AB 释放的充风时长 / ab_min_refill_s ∈[0,1]。
                # 口径 = 文献 Wang2026 的"累计缓解时间 t_r"归一化：把 222 s 长充风滞后做成可观测量，
                # 让策略无需靠拉长 rollout 窗口即可感知该长时约束。初值 -1e9 → 首次恒为 1.0（允许）。
                _refill_s = max((ctrl._ab_step - ctrl._ab_last_release_step[k]) * ctrl.dt, 0.0)
                obs[a, 11] = float(min(_refill_s / max(self.ab_min_refill_s, 1.0), 1.0))
                if context is not None and ti > 0:
                    obs[a, 12] = context[ti]['head_relative_speed_mps']
                    obs[a, 13] = context[ti]['tail_closing_speed_mps']
                a += 1
        return obs

    def get_formation_context(self) -> list:
        """Return a read-only, same-time diagnostic snapshot in SI units.

        Positive relative/closing speed means the follower is faster. Head
        relative speed matches coordination; tail closing speed describes
        the actual tail-to-head gap. This does not extend policy observations.

        【ADR-061】间距参考线 = d_eff = GAP_EFF_MARGIN × d_safe（ATP 同源，与奖励
        gap_eff/gap_danger 同口径）；d_safe 不可算（含陡坡 EBD 发散）时统一退
        fallback（_formation_ref_gap），不再记 None。
        """
        context = []
        for ti, tr in enumerate(self.trains):
            dyn = tr.dynamics
            # 【ADR-061】d_eff 走 _formation_ref_gap（含 fallback）：朔黄陡坡下重载 EBD
            # 会数学发散（净减速≤坡度加速 → braking_distance=inf → _atp_safe_gap=None），
            # 此时统一退到简化制动模型 fallback，与奖励/obs 同口径
            d_eff = self._formation_ref_gap(ti) if ti else None
            item = {
                'train_index': ti,
                'preceding_train_index': ti - 1 if ti else None,
                'head_position_m': float(dyn.pos[0]),
                'tail_position_m': float(dyn.pos[-1]),
                'head_speed_mps': float(dyn.vel[0]),
                'tail_speed_mps': float(dyn.vel[-1]),
                'target_gap_m': d_eff,
                'gap_m': None, 'gap_error_m': None,
                'preceding_head_speed_mps': None,
                'preceding_tail_speed_mps': None,
                'head_relative_speed_mps': None,
                'tail_closing_speed_mps': None,
            }
            if ti:
                preceding = self.trains[ti - 1].dynamics
                gap = float(preceding.pos[-1] - dyn.pos[0])
                item.update(
                    gap_m=gap,
                    gap_error_m=(gap - d_eff) if d_eff is not None else None,
                    preceding_head_speed_mps=float(preceding.vel[0]),
                    preceding_tail_speed_mps=float(preceding.vel[-1]),
                    head_relative_speed_mps=float(dyn.vel[0] - preceding.vel[0]),
                    tail_closing_speed_mps=float(dyn.vel[0] - preceding.vel[-1]),
                )
            context.append(item)
        return context

    def _gap_metrics(self):
        """本步列间间距指标：(间距误差均值 m, 最小实际列间距 m)。

        供训练日志监控（CSV/TB 的 gap_err_mean / gap_min_m 列）。
        【ADR-061】误差参考线 = d_eff = GAP_EFF_MARGIN × d_safe（ATP 同源，与奖励
        gap_eff/gap_danger 同口径）；d_safe 不可算的列跳过误差统计，min gap 始终取
        真实列间距。单列编组无列间距，返回 (0.0, float('inf'))。
        """
        if self.num_trains <= 1:
            return 0.0, float('inf')
        errs, gaps = [], []
        for i in range(1, self.num_trains):
            gap = (self.trains[i - 1].dynamics.pos[-1] - self._train_heads[i])
            gaps.append(gap)
            d_safe = self._atp_safe_gap(i)
            if d_safe is not None:
                errs.append(gap - GAP_EFF_MARGIN * d_safe)
        return (float(np.mean(errs)) if errs else 0.0), float(np.min(gaps))

    def _step_decomposed_fleet(self, actions: np.ndarray):
        """decompose 模式 step：每机车 RL 调制 [ed_mod, ab_mod] → 规则基线+调制 → 单列 _step_decomposed。"""
        actions = np.asarray(actions, dtype=float)
        if actions.shape != (self.num_agents, 2):
            raise ValueError(
                f"decompose 动作形状应为 {(self.num_agents, 2)}, 实际 {actions.shape}"
            )
        self._safety_events = 0
        ab_count = 0       # 本步激活的 AB 源总数（奖励塑形：AB 贵）
        ed_sum = 0.0       # 本步 ED 深度合计（ED 便宜，鼓励 ED 优先）
        # 【ADR-021 决策3 / D】安全层对 AB 的"禁新增源"本步计数（跨列车累加）。
        # 逐列车子环境（train_env）已在 info 暴露，此处聚合到 fleet info，供诊断/留痕可观测。
        ab_safety_vetoed_count = 0
        self._step_coupler_peak_n = 0.0  # 本步全列最大车钩力（跨列车取 max；奖励车钩力用真实峰值，非机车局部值）
        a = 0
        # 【C 组 2026-11-08】编队级 ED/速度快照：本步决策前**一次采样**，供
        # ed_release_timing_guard 与 speed_convergence_share 共用。
        # 只用各列控制器上一步已提交的 ED 请求（_previous_ed）与本步起始队首速度，
        # 不预支本步尚未计算的决策 → 无未来信息、无循环内先后顺序偏差（三列同时看到同一份快照）。
        # 两个开关都关闭时不下发，控制器 getattr 默认 None（零回归）。
        if self.speed_convergence_share or self.ed_release_timing_guard:
            ed_last = []
            for c in self.multi_loco_controllers:
                prev = getattr(c, '_previous_ed', None)
                ed_last.append(
                    float(np.mean(np.abs(np.asarray(prev)))) if prev is not None else 0.0
                )
            speeds_kmh = [float(tr.dynamics.vel[0]) * 3.6 for tr in self.trains]
            for ti, tr in enumerate(self.trains):
                neighbors = []
                if ti > 0:
                    neighbors.append(ed_last[ti - 1])
                if ti + 1 < len(self.trains):
                    neighbors.append(ed_last[ti + 1])
                tr.formation_neighbor_ed_frac = max(neighbors) if neighbors else None
                tr.formation_rear_speed_kmh = (speeds_kmh[ti + 1]
                                               if ti + 1 < len(self.trains) else None)
                tr.formation_self_speed_kmh = speeds_kmh[ti]
        # 【列距收缩 v2 2026-09-09】放弃 A2"全场共同速度锁"（它会连 follower 一起压死，
        # 使"最慢列当 follower"时无追能力 → col1-col2 停在 ~2400m 缩不回）。
        # 现为：leader(ti==0) 沿用 A1-final 迁就尾列；follower(ti>0) 级联追自己前列，
        # 上限 = min(协调抬带, lead_speed+offset)，见下方 follower 分支。
        for ti, (tr, ctrl) in enumerate(zip(self.trains, self.multi_loco_controllers)):
            v_before = float(tr.dynamics.vel[0])
            n_loco = len(tr.loco_indices)
            rl = actions[a:a + n_loco]
            # 【A1-final 双向列距维持，2026-09-09。C3 铁证：长大下坡"位置→坡度→速度"
            # 正反馈——leader 先进深坡加速到 |v_max|，follower 在缓坡平衡低速，物理上
            # 追不上（A1b"follower 追"无效）。唯一物理可收敛路径 = leader 迁就降速：
            # leader 目标速度带上限受"尾部列速度"约束，编队以尾部能跟上的共同速度前进。
            # 领航列(ti==0)迁就；跟随列(ti>0)保留带内追上杠杆作辅助。
            if ti == 0:
                # 【leader 迁就】限制 leader 速度带不高于 "尾部列速度 + 裕量"。
                tail_speed = float(self.trains[-1].dynamics.vel[0])
                lead_cap = float(np.clip(self.v_max, 0.0,
                                         tail_speed + self.LEAD_TAIL_OFFSET_MPS))
                v_bound_max = lead_cap - self.v_max  # ≤0：压低 leader 的超速触发线
                v_bound_min = 0.0
                coordination_traction = 0.0
            else:
                lead_tail = float(self.trains[ti - 1].dynamics.pos[-1])
                gap_err = (lead_tail - self._train_heads[ti]) - self._formation_ref_gap(ti)
                lead_speed = float(self.trains[ti - 1].dynamics.vel[0])
                self_vel = v_before
                v_bound_max, v_bound_min, coordination_traction = ctrl.coordination_adj(
                    gap_err=gap_err,
                    rel_speed=self_vel - lead_speed,
                    kp_gap=self.LEAN_KP_GAP,
                    traction_coef=self.LEAN_TRACTION_COEF,
                    max_traction=self.LEAN_MAX_TRACTION,
                    max_adj=self.LEAN_MAX_ADJ,
                )
                # 【列距主动收缩 v2 2026-09-09】A2 全场共同速度锁（v_cap_max）把 follower
                # 速度带上限压到"最慢列+5"。当 follower 恰为全场最慢列时被自己拖死，col1-col2
                # 停在 ~2400m 缩不回。修复：共同速度锁只约束 leader；follower 上限改用
                # "lead 速度 + 允许offset"，让级联追前列真正生效，间距靠 coordination_adj
                # 的 gap 抬带/牵引收缩，防追尾由 rel_speed 抑制 + 前置 ETCS(gap) 监督兜底。
                # The controller expects an offset relative to self.v_max,
                # whereas preceding speed + margin is an absolute speed cap.
                follower_cap_adj = lead_speed + self.LEAD_TAIL_OFFSET_MPS - self.v_max
                v_bound_max = min(v_bound_max, follower_cap_adj)
                # 【等速冻结消除 chase 2026-09-09】三列等速时 coordination_adj 追的偏置
                # 因 rel_speed≈0 / gap_err 恒定而无累积 → 间距在 ~1300m 冻结。补救：当
                # follower 仍明显落后（gap_err>死区）时，把缓解线(v_min)抬高到
                # "仅比 lead 快一个小量"的目标速度，使 follower 在带内常态获得正向加速度，
                # 持续缩距直到 gap_err 落入死区（进入死区后撤销 chase，防追过头压迫前列）。
                if gap_err > self.LEAN_CHASE_DEADBAND_M:
                    chase_v = float(np.clip(
                        lead_speed + self.LEAN_CHASE_DELTA_MPS, self.v_min, self.v_max))
                    v_bound_min = max(v_bound_min, chase_v - self.v_min)
            # Refresh the same target used by the safety layer before the
            # rule controller decides; never anticipate from last-step data.
            if ti > 0:
                leading_tail = float(self.trains[ti - 1].dynamics.pos[-1])
                lead_speed = float(self.trains[ti - 1].dynamics.vel[0])
                tr.set_etcs_targets([EbdTarget(
                    position_m=leading_tail, speed_mps=lead_speed, kind='gap',
                )])
                # 【2026-11-05 修复】decompose 路径此前缺少 C1/C3/C5/C6 所需的编队外溢信息，
                # 使这些开关在该路径下静默失效（C6 首轮实测轨迹与基线 md5 完全相同）。
                # 三个开关关闭时控制器不读取（getattr 默认 None），零回归。
                tr.formation_clear_gap_m = leading_tail - float(tr.dynamics.pos[0])
                tr.formation_leader_speed_kmh = lead_speed * 3.6
                tr.formation_release_delay_s = self.cyclic_release_stagger_per_train_s * ti
            if (self.leader_brake_feedforward and self.multi_loco_controllers is not None
                    and ti + 1 < len(self.trains)):
                js = (range(ti + 1, len(self.trains)) if self.leader_brake_ff_scope == 'all'
                      else (ti + 1,))
                rear_braking = False
                rear_ed_frac = 1.0
                for j in js:
                    c = self.multi_loco_controllers[j]
                    ab_on = getattr(c, '_ab_on', None)
                    if ab_on is not None and np.any(np.asarray(ab_on)):
                        rear_braking = True
                    prev = getattr(c, '_previous_ed', None)
                    if prev is not None:
                        rear_ed_frac = min(
                            rear_ed_frac, float(np.mean(np.abs(np.asarray(prev)))))
                tr.formation_rear_braking = rear_braking
                tr.formation_rear_ed_frac = rear_ed_frac
            if self.decompose == 'loco_notch':
                # 【S2 / ADR-065 绝对档位】RL 直接决定 ED 深度与 AB 减压档
                # （0=缓解 / 50 kPa / 70 kPa / 140 kPa），**不经规则循环制动状态机**。
                # 安全边界（充风 222 s 门控、超速强制 SERVICE）在 controller 内保留，
                # 车钩力源头 veto 仍由子环境 safety 层执行。
                final_edab = ctrl.get_action_notch(
                    tr, rl, v_max=self.v_max, v_min=self.v_min,
                    v_max_adj=v_bound_max, v_min_adj=v_bound_min,
                )
            else:
                # 【ADR-065 / S1 参数化探针】2 维动作在此被**重新解释为循环制动相位门**：
                #   ed_mod → cyclic_brake_trigger_kmh（何时开始制动，[55,69] km/h，基线 65.95）
                #   ab_mod → cyclic_release_kmh     （何时缓解，    [48,64] km/h，基线 54.96）
                # 幅度调制恒 0 ⇒ 传给控制器的是零向量（纯规则执行 + RL 定的相位）。
                # 约束 trig − rel ≥ 4 km/h 防抖（基线差 10.99，范围内不会撞界）。
                rl_eff = rl
                if self.rule_param_probe:
                    ed_r = float(np.clip(rl[0, 0], -1.0, 1.0))
                    ab_r = float(np.clip(rl[0, 1], -1.0, 1.0))
                    sc = float(self.rule_param_scale)
                    trig = float(np.clip(62.0 + 7.0 * sc * ed_r, 55.0, 69.0))
                    rel = float(np.clip(56.0 + 8.0 * sc * ab_r, 48.0, 64.0))
                    if trig - rel < 4.0:
                        trig = min(69.0, rel + 4.0)
                    ctrl.cyclic_brake_trigger_kmh = float(trig)
                    ctrl.cyclic_release_kmh = float(rel)
                    rl_eff = np.zeros_like(rl)
                final_edab, _ = ctrl.get_action_decomposed(
                    tr, rl_eff, v_max=self.v_max, v_min=self.v_min,
                    v_max_adj=v_bound_max, v_min_adj=v_bound_min,
                )
            # 【A1b 带内追逐】协调偏置的正 traction 注入 decompose 的 ed 通道（负 ed=牵引）：
            # 仅当本步规则在"带内非制动段"（_cyclic_braking==False）且不在电梯制动中
            # 才注入——制动/ED 段仍以安全为准，避免"边追边制"冲突。
            if ti > 0 and coordination_traction > 0 and not ctrl._cyclic_braking:
                for k in range(final_edab.shape[0]):
                    if final_edab[k, 0] <= 1e-9:  # 本机车未在 ED 制动
                        final_edab[k, 0] = -float(coordination_traction)
            self._executed_actions[a:a + n_loco] = final_edab
            a += n_loco
            ab_count += int(np.sum(final_edab[:, 1] < 0))
            ed_sum += float(np.sum(final_edab[:, 0]))
            _pt_info = tr.step(final_edab)[-1]
            feedback = getattr(ctrl, 'record_executed_ed', None)
            if feedback is not None and 'actual_loco_ed' in _pt_info:
                feedback(_pt_info['actual_loco_ed'])
            # 【ADR-021 决策3 / D】聚合本列的安全层 AB 权限计数（子环境 info 上抛）
            ab_safety_vetoed_count += int(bool(_pt_info.get('ab_safety_vetoed', False)))
            self._train_heads[ti] = float(tr.dynamics.pos[0])
            # 【2026-11-08 超速口径】同 `_step`：逐集累计车·步超速计数
            # 【ADR-060 限速逐段联动】越线门 = 该列联动限速（无表剖面 = self.v_max 零回归）
            self._ep_overspeed_car_steps += int(
                np.count_nonzero(tr.dynamics.vel > self._line_vmax_for(ti)))
            # 【ADR-021 决策2 2026-10-01】reward 峰值口径改**断面力**（coupler_interface_forces，
            # 长度 n-1）：原用每车净力 _coupler_forces() 少报约 7.8×，使"破线/不破线"在 reward
            # 里几乎不可区分。此为**有意**口径变更（ADR-018 指标 SSOT = 断面力）→ 会改变 reward
            # ⇒ 旧权重需重训。断面力违规计数（下方）保持不变。
            iface = np.abs(tr.dynamics.coupler_interface_forces())
            iface_max = float(np.max(iface)) if iface.size else 0.0
            self._step_coupler_peak_n = max(self._step_coupler_peak_n, iface_max)
            interface = iface
            if interface.size:
                self._peak_coupler_n = max(self._peak_coupler_n, float(np.max(interface)))
                self._coupler_limit_violations += int(
                    np.sum(interface > self.coupler_force_limit_n))
            self._safety_events += tr._safety_events

        obs = self._get_obs_decomposed()
        self._ep_head_speed_sum_kmh += float(self.trains[0].dynamics.vel[0]) * 3.6
        self._ep_head_steps += 1
        reward = self._calculate_reward_decomposed(
            ab_count, ed_sum, step_coupler_peak_n=self._step_coupler_peak_n)
        self.steps += 1
        terminated = False
        # 【2026-11-08】头车到剖面末端即截断（越界段无真实坡度）；max_steps 仅作时间上限
        route_end = (self.route_end_m is not None
                     and float(self._train_heads[0]) >= self.route_end_m)
        truncated = bool(route_end or self.steps >= self.max_steps)
        info = {
            'reward': reward,
            'coupler_force_peak': float(self._peak_coupler_n),
            'coupler_force_limit': float(self.coupler_force_limit_n),
            'coupler_limit_violations': int(self._coupler_limit_violations),
            'safety_events': int(self._safety_events),
            # 【2026-11-08 截断口径】本步是否因"头车到达剖面末端"而结束（区分步数上限）
            'route_end_reached': bool(route_end),
            'head_position_m': float(self._train_heads[0]),
            # 【2026-11-08 取舍判据】逐集累计超速车·步 + 领航列均速（km/h）
            'overspeed_car_steps': int(getattr(self, '_ep_overspeed_car_steps', 0)),
            'head_speed_mean_kmh': (
                float(self._ep_head_speed_sum_kmh) / max(int(self._ep_head_steps), 1)),
            # 列间间距监控（2026-09-23 新增，训练日志 CSV/TB 用）
            **dict(zip(('gap_err_mean', 'gap_min_m'), self._gap_metrics())),
            'executed_actions': self._executed_actions.copy(),
            'actions_modified': False,
            'ab_source_count': ab_count,          # 本步 AB 源数（ED 优先/AB 兜底 分配诊断）
            'mean_ed_frac': ed_sum / max(self.num_agents, 1),
            'decomposed_actions': self._executed_actions.copy(),
            # 【ADR-021 决策3 / D】安全层对 AB 的权限计数（跨列车本步聚合；新增键，既有键不删）
            'ab_safety_vetoed': ab_safety_vetoed_count,
            'formation_context': self.get_formation_context(),
        }
        return obs, reward, terminated, truncated, info

    def _calculate_reward_decomposed(self, ab_count: int, ed_sum: float,
                                     step_coupler_peak_n: float = None) -> float:
        """decompose 模式奖励（v6-literature-slots，ADR-043）：13 项收敛为 6 个文献槽位。

        - 领航列速度项：'flat' 带内平顶 +5 / 'ramp' 带内凸斜坡 / 'ref' 跟踪规则基线参考速度
          （v7 默认用 'ref'：单峰有界二次，见奖励分支注释；带外比例罚仅在 flat/ramp 生效）
        - 跟随列速度：相对前列镜像 + 超线速硬罚与领航同通道（Guo2025 leader/follower 异构）
        - 间距效率 / 间距危险：ATP 对齐两段式（ADR-026；Song2026 势场 / Hua2024 近距罚同型）
        - 车钩力：峰值比有界饱和塑形 + 受控超限项（Wang2026 式17 同型 + ADR-021）
        - 电空分工：AB 需求塑形 + ED 微成本（Zhang2024 式22 / Wang2026 式16 Rb 充风约束）

        v6 删除项（ADR-043）：a²（原误标"舒适"；文献一致用 jerk²，且 Song2026 明写 jerk 是
        车钩力变化率代理——本项目直接量测断面力车钩力，无须代理）；追尾趋势罚与追尾硬罚
        （危险项 -60·õ² 已不封顶，文献对碰撞 = 大罚 + 终止）；车钩均值项 -0.2·mean(obs[:,5])
        （口径为每车净力 ≠ 断面力 SSOT，且无文献锚）。
        """
        # 【相对列距锚定 2026-09-10】限速区间（循环制动核心）只由领航列承载绝对带责任，
        # 跟随列改为相对锚定前列（列距由 gap 承担、相对速度在此镜像），
        # 避开 53km 多坡段"绝对同速物理不可达"（诊断-2026-09-10 发散短训 35ep 复现）。
        speed_band_reward = 0.0
        rel_anchor_reward = 0.0
        # 【ADR-060 限速逐段联动】速度带/越线判定用领航列联动限速（无表 = self.v_max 零回归）。
        v_line0 = self._line_vmax_for(0)
        v_center = 0.5 * (self.v_min + v_line0)
        band_half = 0.5 * (v_line0 - self.v_min)
        force_penalty = 0.0  # 超速硬惩罚（三列同一通道，见循环末尾）
        for ti, tr in enumerate(self.trains):
            v = float(tr.dynamics.vel[0])
            if ti == 0 and self.speed_band_shape == 'ref':
                # 【v7 参考速度跟踪】单峰有界二次项：r = W·(1 − min(x², CAP))，x=(v−v_ref)/band。
                # 与 v6 平顶的根本区别：**全程有梯度**（贴基线才拿满分；偏离按二次衰减，
                # |偏离| ≥ 2 个带宽封底 −15）。三条设计取舍：
                #  ① 不用"带宽内满分 + 带外线性扣"：那会在带宽边界制造不连续点，策略会贴边抖动。
                #  ② 参考速度已 clamp ≤ v_max ⇒ 朝参考"跑快"不可能越过限速（无诱导超速）。
                #  ③ 越线速另有 speed_over_w=10 的硬通道兜底 ⇒ 参考点附近不会被"跑快"抵消。
                ref_v = self._ref_lookup()
                x = (v - ref_v) / max(self.speed_ref_band_mps, 1e-6)
                speed_band_reward += self.speed_ref_w * (
                    1.0 - min(x * x, self.speed_ref_cap))
            elif ti == 0:
                # 领航列：锚绝对带（编队节奏负责人）
                norm_dev = abs(v - v_center) / max(band_half, 1e-6)
                if self.speed_band_shape == 'flat':
                    if norm_dev <= 1.0:
                        # 【ADR-043】带内平顶（对齐 Zhang2024 式22 Rd=+5）——带内无中心梯度
                        speed_band_reward += SPEED_BAND_W
                    else:                      # 越带：越深越罚
                        speed_band_reward -= 0.2 * (norm_dev - 1.0) * 100.0
                else:
                    # 【速度带改形 2026-11-08】'ramp'：带内收益随接近上限**边际递增**（凸梯度），
                    # 带内不再平顶 ⇒ "贴限速不再零边际收益"，越线速另有重罚兜底（见下方 force_penalty）。
                    # 【ADR-060】上限用联动限速 v_line0（无表 = self.v_max 零回归）。
                    frac = min(max((v - self.v_min) / max(v_line0 - self.v_min, 1e-6), 0.0), 1.0)
                    speed_band_reward += SPEED_BAND_W * frac ** SPEED_BAND_RAMP_EXP
                    if norm_dev > 1.0:         # 越带：越深越罚（带宽外仍保留旧比例罚）
                        speed_band_reward -= 0.2 * (norm_dev - 1.0) * 100.0
            else:
                # 跟随列：镜像前列可行轨迹（相对速度匹配）——不再被绝对带拖累
                lead_v = float(self.trains[ti - 1].dynamics.vel[0])
                rel_spd_norm = (v - lead_v) / self.REL_ANCHOR_SPD_SCALE
                rel_anchor_reward += self.REL_ANCHOR_SPD_W * max(0.0, 1.0 - rel_spd_norm ** 2)
            # 【超线速通道补齐 2026-11-08】领航与跟随列统一：v > v_max 一律按 speed_over_w 计罚。
            # 原先只有领航列进这条通道，跟随列挂的是 v_max*1.05 之上的轻权重软兜底
            # （3.0·Δ），结果第 2/3 列车越 80 只靠 ATP 兜底、奖励侧没有梯度。约束口径改为
            # "单车最高 ≤81.5 km/h"后，越限仍必须"越线不划算"，故三列同权重同阈值。
            # 纯奖励侧改动：不动物理、不动规则层 ⇒ BC 标签轨迹逐位不变。
            # 【ADR-060 限速逐段联动】越线门 = 该列联动限速（无表 = self.v_max 零回归）。
            v_line_ti = self._line_vmax_for(ti)
            if v > v_line_ti:
                force_penalty -= self.speed_over_w * (v - v_line_ti)

        # 车钩力约束（创新点）。破线由底层硬安全层 enforce_coupler 杜绝
        # （车钩力定位 = 硬安全层 + 观测上下文，不作 reward 强化最小化对象）。
        # 【ADR-043】删旧均值项 -0.2·mean(obs[:,5])（口径为每车净力 ≠ 断面力 SSOT，且无文献锚）；
        # 峰值比塑形取 Wang2026 式17 同型有界饱和形 -(1-exp(-p̂)) 并修正其单调方向
        # （原文 -exp(-f/F) 单调反常 ⇒ 不可照抄，见 ADR-043）。
        if step_coupler_peak_n is not None and step_coupler_peak_n > 0:
            peak_n_norm = step_coupler_peak_n / max(self.coupler_force_limit_n, 1e-9)
        else:
            peak_n_norm = 0.0
        coupler_peak_term = -COUPLER_PEAK_W * (1.0 - float(np.exp(-peak_n_norm)))

        # 【ADR-021 决策2 / ADR-043 修订】车钩力"受控超限项"（文献 Tang2020 / Wang2025）：
        # 仅对**断线峰值超限**加深有界梯度；上界 -12 与带外速度惩罚同档但更小，**刻意避免**
        # -80·ov² 量级（回滚原因：value 目标震荡 / KL 频繁早停）。
        # peak_n_norm < 1（未破线）时该式恒为 0（over=0）。ADR-043 起均值项已删，只保留峰值口径。
        over = max(0.0, peak_n_norm - 1.0)
        coupler_over_term = -COUPLER_OVER_W * min(over, COUPLER_OVER_CAP)

        # 【ADR-043 删】原 a² 舒适项已删除：文献一致用 jerk²（Song2026/Hu2026/Guo2025），
        # 且 Song2026 明写 jerk 是车钩力变化率代理——本项目直接量测断面力车钩力，无须代理。

        # 列间间距（多列 decompose 后叠阶段复用；单列时无项）
        # 【ADR-026 2026-10-04】改为"ATP 对齐两段式"：效率项（贴近 d_eff=1.1·d_safe 越好）
        # + 危险项（跌破 d_safe 陡罚、**不封顶**）。旧实现（+1.0·exp(-(ge/140)²) 小高斯丘 +
        # max(...,-200) 饱和势场 + 对固定 200m 双向惩罚）已废止：它既不给"贴紧"的奖励，
        # 也在危险区没有梯度（gap≤70m 后恒为 -200），实测最小列距掉到 19m。
        gap_eff_reward = 0.0
        gap_danger_penalty = 0.0
        if self.num_trains > 1:
            for i in range(1, self.num_trains):
                lead_tail = float(self.trains[i - 1].dynamics.pos[-1])
                actual_gap = lead_tail - float(self._train_heads[i])
                d_safe = self._atp_safe_gap(i)
                if d_safe is None:
                    d_safe = self._fallback_d_safe()   # 回退（无 ETCS 曲线等，物理同源简化模型）
                d_eff = GAP_EFF_MARGIN * d_safe
                # 效率项：gap ≥ d_eff 时，越接近 d_eff（间距越小）奖励越高；再大则衰减到 0。
                if actual_gap >= d_eff:
                    gap_eff_reward += GAP_EFF_W * max(
                        0.0, 1.0 - (actual_gap - d_eff) / GAP_EFF_SCALE_M)
                # 危险项：跌破 ATP 安全线 d_safe → 陡罚，不封顶（越线绝不被速度带收益抵消）。
                # 【修复 2026-10-04】穿透时 _atp_safe_gap 恒返 0.0（lead_tail<=head），原
                # max(d_safe,1.0)=1.0 使 over 退化成"穿透米数"（-53m→over=53）⇒ over² 爆炸
                # （-60·53²≈-1.7e5/步）⇒ 单集回报 R≈-9.18e6 ⇒ ValueNorm vstd 永久抬高（17k）
                # 致后续数十集 advantage 被压缩、训练停滞。改用固定参考尺度归一（over 保持
                # 无量纲、量级有界）；非穿透路径（d_safe>1）行为不变。
                if actual_gap < d_safe:
                    denom = d_safe if d_safe > 1.0 else GAP_DANGER_REF_M
                    over_gap = (d_safe - actual_gap) / denom
                    gap_danger_penalty -= GAP_DANGER_W * over_gap * over_gap
                # 【ADR-043 删】追尾硬罚（-10, gap<5m）与趋势罚（-0.4·shrink）已删除：
                # 危险项 -60·õ² 已不封顶、量级远大于二者；文献对碰撞的普遍处理 = 大罚 + 终止。

        # 电空分工塑形（本架构核心）。诊断-2026-09-25：原 `ab_cost=0.0` 使 AB 在奖励上
        # 完全中性、且在触发舒适/车钩项时被隐式扣分 → seed0 退化成"纯 ED 蠕行"
        # （完整 53km 评估 ab_steps=0、pe41248kN 超限、band 6%、末速18km/h 失速）。
        # 文献：Zhang2024 式22（带外/超速 = 制动需求信号，AB 未参与则罚）；Wang2026 式16 Rb
        # 充风约束（与本项目 obs[11] 充风就绪度 ADR-030 同源）。用"领航列带外/超速"作需求信号，
        # needy 时 AB 未参与 → 加惩罚，使"AB 是带内唯一守住速度带的手段"从 reward 里自然涌现。
        ab_cost = 0.0
        # 需求信号 = 领航列是否带外（norm_dev>1）或超线速（v>v_max）。这些量在带内 retable 为 0
        needs_brake = 0.0
        if self.num_trains:
            lv = float(self.trains[0].dynamics.vel[0])
            if self.speed_band_shape == 'ref':
                # v7：需求信号 = 领航列"高于参考速度一个带宽"或"超线速"。
                # 低于参考要的是牵引（不是制动），故不触发 AB 兜底惩罚。
                ref_v = self._ref_lookup()
                needs_brake = float(lv > self.v_max) or float(
                    lv - ref_v > self.speed_ref_band_mps)
            else:
                needs_brake = float(lv > self.v_max) or float(
                    abs(lv - v_center) > band_half)
        if needs_brake > 0.0 and ab_count <= 0:
            # 领航列已带外/超速却无 AB 参与 → 弱惩罚，倒逼"需减速时必须靠 AB 兜底"
            ab_cost -= 0.5 * needs_brake
        ed_cost = -0.02 * float(ed_sum)

        reward = (
            + speed_band_reward
            + rel_anchor_reward
            + force_penalty            # speed_over（超线速硬罚，只出现在 force_penalty 里）
            + gap_eff_reward
            + gap_danger_penalty
            + coupler_peak_term
            + coupler_over_term
            + ab_cost
            + ed_cost
        )
        if self.reward_term_log:
            terms = {
                'speed_band': speed_band_reward,
                'rel_anchor': rel_anchor_reward,
                'speed_over': force_penalty,
                'gap_eff': gap_eff_reward,
                'gap_danger': gap_danger_penalty,
                'coupler_peak': coupler_peak_term,
                'coupler_over': coupler_over_term,
                'ab_cost': ab_cost,
                'ed_cost': ed_cost,
                'total': reward,
            }
            self._last_reward_terms = terms
            self._reward_term_steps = int(getattr(self, '_reward_term_steps', 0)) + 1
            for key, value in terms.items():
                self.reward_term_sums[key] = self.reward_term_sums.get(key, 0.0) + float(value)
        return reward

    def _calculate_reward(self, obs: np.ndarray, target_accels: np.ndarray = None,
                          accels: np.ndarray = None,
                          executed_throttles: np.ndarray = None) -> float:
        """列间奖励（聚焦协同制动策略 + 舒适性）：避免追尾 + 平稳驾驶 + 车钩力 + 间距。

        领域认知（2026-08-14）：长大下坡本质是制动控制问题——列车无法牵引超速，
        只能制动降速。因此列间 RL 的价值是"协同制动策略"（多列如何协同制动避免追尾、
        保持安全间距、车钩力不超限）。

        对齐业界（Hua2024 w3·u² 舒适性 / Zhang2021 APF 势场）：
        - 舒适性（加速度惩罚）：惩罚剧烈加减速 → RL 学"平稳驾驶"（底层 PID 不会优化
          舒适性，这是 RL 的增量价值，解决"学无可学"）
        - 避免追尾（势场）：间距低于安全阈值 → 强惩罚（协同制动核心目标）
        - 速度不超限：速度超目标 → 惩罚（长大下坡制动控速）
        - 车钩力约束：超限 → 成比例惩罚（本项目创新点）
        - 间距保持 + 速度一致性：跟随车协同保持间距

        奖励项：
        - 舒适性（accels）：各列加速度平方和 → 惩罚
        - 避免追尾（势场）：间距低于安全阈值 → 强惩罚（协同制动核心目标）
        - 速度不超限：速度超目标 → 惩罚（长大下坡制动控速）
        - 车钩力约束：超限 → 成比例惩罚（本项目创新点）
        - 间距保持：间距误差 → 惩罚（跟随车协同保持间距）
        - 速度一致性：各列速度差 → 惩罚（协同制动一致）
        """
        # 【E3 奖励重构，借鉴第1层 train_cyclic_braking 已验证有效的"稀疏清晰"哲学】
        # 第1层成功关键：速度在限速区间内给清晰正向(+5/步)，超出硬惩罚(-20/步)，制动有成本(-0.5)。
        # 第2层原奖励全是连续负惩罚，RL 无法判断"该制动还是缓解"，导致 v1 贴上限超速(97%)、
        # v2 二次惩罚探索期崩溃。重构为与第1层一致的清晰区间引导 + 多列协同项。
        # 【reward 版本 R2（2026-09-08，编队层长程 curriculum 修复）】seed1 长程(9000+步)灾难根因=
        # 追尾惩罚每步 -50 长程累积爆炸（-172万）。R2 改动：追尾硬惩罚 -50→-12/步；速度带内
        # +5→+10/列/步（强化长程"维持带内循环"持续正反馈）。避免追尾仍由 gap_trend(超前预防)
        # + 势场(clip)分担。其余 shaping 不变。训练/评估共用本 env，reward 口径一致。
        #
        # 速度一致性（各列速度相互差，越小越好）——协同制动时各列应协调减速
        speeds = np.array([tr.dynamics.vel[0] for tr in self.trains])
        speed_consistency = float(np.std(speeds))

        # 避免追尾（势场硬惩罚）：间距低于安全阈值 → 强惩罚（协同制动核心）
        # V5.x 修正：势场二次惩罚在追尾穿透时二次爆炸（单步可到 -4万）导致 GAE 尺度爆炸、
        # 训练发散（E3 实测 Ep70 崩盘到 -2000万）。加 clip 上限保证数值稳定，
        # 同时保留足够强的惩罚引导（协同制动核心目标）。
        potential_field = 0.0
        collision_penalty = 0.0
        # E21 追尾趋势惩罚：间距在缩小（后列逼近前列）→ 早期惩罚，引导 RL 提前协同
        # 减速避免追尾（seed1 灾难根因：追尾698步累积-172万，需提前预防而非等追尾势场爆炸）
        gap_trend_penalty = 0.0
        current_gap_err = obs[1:, 1].copy() if self.num_trains > 1 else np.array([])
        if self._prev_gap_err is not None and len(current_gap_err) == len(self._prev_gap_err):
            for i, cur in enumerate(current_gap_err):
                prev = self._prev_gap_err[i]
                # 间距误差在变小（实际间距缩短，逼近前列）→ 追尾趋势 → 惩罚
                shrink = prev - cur
                if shrink > 1.0 and cur < 30.0:  # 间距缩短且已较近 → 追尾风险
                    gap_trend_penalty -= 0.5 * shrink
        self._prev_gap_err = current_gap_err

        for i in range(1, self.num_trains):
            # 【ADR-061】直接用真实列间距（原从 obs[1] 反推 actual_gap = 动态目标 + err，
            # 参考线删除后反推链断裂）；危险区参考 = 0.4 × d_eff（ATP 同源，随 d_safe 缩放）
            actual_gap = float(self.trains[i - 1].dynamics.pos[-1] - self._train_heads[i])
            min_gap = 0.4 * self._formation_ref_gap(i)
            if actual_gap < min_gap:
                # 势场惩罚：间距越近惩罚越重（二次），clip 防爆炸
                potential_field += -2.0 * (min_gap - actual_gap) ** 2
            # 追尾硬惩罚（间距接近 0）
            if actual_gap < 5.0:
                collision_penalty -= 12.0  # R2：-50→-12，防长程追尾累积爆炸（seed1 -172万根因）
        potential_field = max(potential_field, -200.0)  # E22：数值稳定+降灾难量级（原-2000长距离累积爆炸）

        # 限速区间约束 [v_min, v_max]（循环制动核心目标，对齐 Zhang2024 朔黄线[40,80]，V5.24）：
        # 借鉴第1层 train_cyclic_braking 哲学（对齐 Zhang2024 Eq.22 的 Rc/Rd）：
        # - 速度在区间内 → 每列 +5 清晰正向（鼓励保持有效运行速度，非"免罚"）
        # - 超 v_max / 低于 v_min → 每列 -20 硬惩罚（长大下坡必须制动降速）
        # 这样 RL 有明确动机在 [v_min,v_max] 循环，而非贴上限超速（v1）或探索期崩溃（v2）。
        speed_band_reward = 0.0
        for i, tr in enumerate(self.trains):
            vel = tr.dynamics.vel[0]
            # 【ADR-060 限速逐段联动】越线门 = 该列联动限速（无表 = self.v_max 零回归）
            v_lim_i = self._line_vmax_for(i)
            if self.v_min <= vel <= v_lim_i:
                speed_band_reward += 10.0
            else:
                speed_band_reward -= 20.0

        # 制动成本：鼓励"只在必要时制动"（循环制动关键——学到"到上限制动，区间内缓解滑行"）
        # 借鉴第1层 brake_engaged → -0.5（Zhang2024 制动距离维护成本）
        brake_cost = 0.0
        if target_accels is not None:
            # target_accels<0 = 请求制动（加速度为负）
            brake_cost = -0.5 * float(np.sum(np.asarray(target_accels) < -0.05))

        # 间距保持（跟随车）——E4 重构为"安全跟车"语义（对齐虚拟耦合 VCTS 安全间隔）。
        # E4 诊断：真实剖面多坡段 → 3列速度天然不同步（列间实距~1300m），精确保持固定
        # 间距物理上不可行。且 speed_band_reward(超速-20) 与"追车需速度差"冲突，RL 学不会
        # 追车（v4 间距拉到1106m）。改为"安全跟车"：间距误差在安全区间内无惩罚（跟住了），
        # 拉开过大（跟丢，协同失败）→ 硬惩罚。过近由势场处理（避免追尾）。
        # 依据：VCTS 用安全间隔而非精确间距；Chen2024 虚拟耦合重载列车 = 安全间隔约束。
        # 【方向A 2026-09-04】gap_reward 连续化（修根因2）：原分桶（±1 区间 / >200m 惩罚）
        # 使微小协同偏移产生不了平滑梯度，RL 学不到"微调协同步伐→间距渐变"的映射。
        # 改为以 ge=0 为中心的高斯峰（任意 ge 有连续梯度）+ 拉开超 150m 的线性跟丢惩罚。
        gap_reward = 0.0
        if self.num_trains > 1:
            for i in range(1, self.num_trains):
                ge = obs[i, 1]  # 该跟随列间距误差（带符号：正=拉大，负=逼近）
                # 高斯峰奖励（ge=0 处 +1/列，σ=140，渐消失）：连续、平滑、处处有梯度
                gap_reward += 1.0 * float(np.exp(-(ge / 140.0) ** 2))
                # 线性跟丢惩罚：拉开超过 150m 后梯度增强，引导"别跟丢"
                if ge > 150.0:
                    gap_reward -= 0.02 * (ge - 150.0)

        # 舒适性（加速度惩罚，对齐 Hua2024 w3·u²）：惩罚剧烈加减速 → RL 学平稳驾驶。
        # 这是底层 PID 不优化的目标，是列间 RL 的增量价值（解决"学无可学"）。
        comfort_penalty = 0.0
        if accels is not None and len(accels) > 0:
            comfort_penalty = -0.3 * float(np.mean(accels ** 2))

        # 车钩力约束（创新点：考虑车钩力）——消融实验可关闭（use_coupler_constraint=False）
        if self.use_coupler_constraint:
            coupler_mean = np.mean(obs[:, 3])
            coupler_peak = np.max(obs[:, 4]) if self.num_trains else 0.0
            violation_penalty = 0.0
            if coupler_peak > 1.0:
                violation_penalty = -5.0 * (coupler_peak - 1.0)
            coupler_term = -0.2 * coupler_mean - 0.2 * coupler_peak + violation_penalty
        else:
            coupler_term = 0.0  # 忽略车钩力（奖励不含车钩力项）

        # 【方向B 2026-09-04】显式一致性奖励（修根因3）：各列制动相位越"同相"
        # （全都在制动 / 全都在缓解）越给正奖励，相位分裂（一半制动一半缓解）给 0。
        # 引导 RL 找三列一致的阈值组合，缓解"多智能体一致性难收敛 → 间距拉开跟丢"。
        # 用实际执行 throttle 判制动相位（鲁棒），量级轻（+0.2）不干扰主奖励尺度。
        consistency_reward = 0.0
        if executed_throttles is not None and len(executed_throttles) > 0:
            braking = (np.asarray(executed_throttles) < -0.01).astype(float)
            frac = float(np.mean(braking))
            consistency_reward = 0.2 * abs(frac - 0.5) * 2.0  # frac=0或1→+0.2，frac=0.5→0

        reward = (
            + speed_band_reward        # 限速区间内+5/超限-20（E3 重构，第1层哲学）
            - 0.1 * speed_consistency  # 速度一致性（E4 降低权重：真实剖面多坡段各列速度天然不同，且追车需速度差）
            + gap_reward               # 间距保持（E4：安全跟车，拉开过大硬惩罚）
            + potential_field          # 避免追尾势场（clip 防爆炸）
            + collision_penalty        # 追尾硬惩罚
            + gap_trend_penalty        # E21 追尾趋势早期惩罚（间距缩小→提前协同避免追尾）
            + brake_cost               # 制动成本（E3 新增，鼓励循环制动）
            + comfort_penalty          # 舒适性
            + coupler_term             # 车钩力约束（可关闭）
            + consistency_reward       # 方向B：制动相位一致性奖励（微弱正塑形）
        )
        return reward

    def close(self):
        for tr in self.trains:
            tr.close()
