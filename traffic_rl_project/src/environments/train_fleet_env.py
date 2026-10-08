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
REWARD_SCHEMA = 'v4-atp-aligned-gap'
# 超限项权重（与速度带带内最高收益 +6.0/列 同量级；刻意远小于已回滚的 -80·ov² 硬惩罚）。
COUPLER_OVER_W = 6.0
# 限幅：peak_norm 超过 3× 上限（over>=2）后不再加深 ⇒ 该项上界 = -COUPLER_OVER_W*CAP = -12。
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
            - target_gap: 列间目标安全间距（m）
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
        self.grade_profile = config.get('grade_profile', 'shuozhou_real_53km')  # 主训练默认=朔黄完整真实纵断面 53.2km
        # 限速区间（m/s）：对齐 Zhang2024（朔黄线 23.8km 长大下坡循环制动）[40,80] km/h。
        # 依据（V5.24 系统核对）：
        # - 上限 80 km/h = 朔黄线实际线路限速（Zhang2024: "speed limit on this line was 80 km/h"，
        #   行业/线路标准，与研究对象1万吨朔黄线一致）
        # - 下限 40 km/h = 2万吨列车最小缓解速度（行业规则"重载30km/h以下不应缓解制动"，
        #   Zhang2024取40保守值；为与其直接对标+物理可行）
        # 弃用 [45,65]：那是樊运新（3万吨）参数，与1万吨对象不一致，且物理上不可行
        # （1.2km万吨列车在窄区间制动频繁→车钩力爆炸+掉速）。
        self.v_max = config.get('v_max', 80.0 / 3.6)   # 上限（80 km/h，线路限速）
        self.v_min = config.get('v_min', 40.0 / 3.6)   # 下限（40 km/h，最小缓解速度）
        # 巡航参考速度 = 限速区间中值（作为 obs 速度误差参考，非硬目标）
        self.target_speed = config.get('target_speed', (self.v_min + self.v_max) / 2.0)
        self.target_gap = config.get('target_gap', 100.0)  # 列间参考间距（m，用于初始布置/时间间隔换算）
        # E4 时间间隔（VCTS 虚拟耦合范式）：动态目标间距 = headway_s × 本列速度。
        # 论文依据：VCTS 用时间间隔而非固定距离（速度快时拉大、慢时缩小，自适应），
        # Wang2021 动态安全间距 x_safe 随速度/制动力变化；固定 100m 在真实剖面多坡段
        # 无法与控速同时满足。默认 5s：20m/s 时 = 100m（与历史一致），速度自适应。
        self.headway_s = config.get('headway_s', 5.0)
        self.coupler_force_limit_n = config.get('coupler_force_limit_n', COUPLER_FORCE_LIMIT_N)
        self.max_steps = config.get('max_steps', 500)
        self.dt = config.get('dt', 0.1)
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
        # 注：方案A（start_offset_m/spacing_m 人为坡段错开）已于 2026-08-20 移除。
        # 它偏离正确场景（各列同坡段起步、随间距保持自然产生动态相位差），
        # 且导致前列/后列缓解持续不同步 → 车钩力持续超限 + M1 训练不收敛。
        # 正确场景 = 普通 reset 布局（各列同坡段起步，见 reset()），协同由场景天然驱动。
        # 【2026-10-06 路线覆盖修复】训练起点随机化（消除 L1 诊断的固定起点 OOD）：
        # 每 episode reset 沿剖面随机前移整个编队，使 ≤1200 步的短训练窗口在**分布**上
        # 覆盖全路（L1：固定起点仅覆盖 −1.5‰ 单坡段，评估 83.9% 的步落在训练未见坡度区间）。
        # 默认关（零回归）；仅训练态生效（eval_mode=True 恒定用基准起点，保证评估可复现）。
        self._start_rand = None
        _sr = config.get('start_randomization', None)
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
                'line_speed_limit_mps': self.v_max,
                'dt': self.dt,
                'max_steps': self.max_steps,
                'etcs_curve': self.etcs_curve,
                'decompose': self.decompose,   # decompose 模式下单列 step 走 _step_decomposed
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
                )
                for tr in self.trains
            ]
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
            self.obs_dim = 12
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
        # E21 追尾趋势：上一步各列间距误差（检测间距缩小→追尾风险，引导RL提前协同）
        self._prev_gap_err = None

    def _sample_start_offset(self) -> float:
        """训练起点随机化：均匀采样编队整体前移量（米）。

        max_m 缺省 = 剖面长 − 编队总长 − 3000（预留一个短窗口的前行余量），保证随机
        起点后编队仍能在剖面内跑完一个训练窗口。剖面为常量坡度（无 segments）时返回 0。
        """
        prof = getattr(self.trains[0].dynamics, '_grade_profile', None)
        if prof is None or not prof.segments:
            return 0.0
        route_len = max(seg.start_m for seg in prof.segments)
        train_len = abs(self._base_pos[0][0] - self._base_pos[0][-1])
        platoon_len = (train_len * len(self.trains)
                       + self._dynamic_gap() * (len(self.trains) - 1))
        span = max(0.0, route_len - platoon_len - 3000.0)
        lo = float(np.clip(self._start_rand['min_m'], 0.0, span))
        hi = (span if self._start_rand['max_m'] is None
              else float(np.clip(self._start_rand['max_m'], lo, span)))
        return float(self._start_rand['rng'].uniform(lo, hi))

    def reset(self, seed=None, options=None):
        self.steps = 0
        self._peak_coupler_n = 0.0
        self._coupler_limit_violations = 0
        self._safety_events = 0
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
        # 训练起点随机化：整列编队沿剖面随机前移（route_offset=0 时零回归）
        route_offset = 0.0
        if self._start_rand is not None and not self.eval_mode:
            route_offset = self._sample_start_offset()
        for i, (tr, ctrl) in enumerate(zip(self.trains, self.controllers)):
            tr.reset(options={'speed': init_speed})
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
                init_gap = self._dynamic_gap()
                offset = train_len + init_gap
                cumulative_offset += offset
                tr.dynamics.set_initial(
                    pos=base_pos - cumulative_offset + route_offset,
                    vel=tr.dynamics.vel,
                )
            self._train_heads[i] = float(tr.dynamics.pos[0])
        if self.decompose:
            return self._get_obs_decomposed(), {}
        return self._get_obs(), {}

    def _dynamic_gap(self) -> float:
        """动态目标间距（VCTS 时间间隔范式）：target_gap + headway_s × 参考速度。

        E4 修正：目标间距用**固定参考速度**（限速区间中值），而非本列速度。
        原实现用本列速度导致 RL 漏洞——速度越高目标间距越大，RL 通过超速"逃避"间距
        惩罚（E4 评估超速 83.4%、间距 1194m）。用固定参考速度则动态间距为常数，
        既保留 VCTS 时间间隔语义（headway×速度尺度），又不让 RL 操纵目标。
        对齐 Wang2021 动态安全间距、Chen2024 虚拟耦合重载列车编队。
        【代码清理 2026-08-20】原签名带 vel 参数但恒被忽略（死参数），现移除。
        """
        return float(self.target_gap + self.headway_s * max(self.target_speed, 0.0))

    def _atp_safe_gap(self, i: int):
        """第 i 列相对前列的 **ATP 制动安全距离 d_safe**（m）——与安全层 ATP 判据同源。

        d_safe = 后列从当前速度、当前位置，把速度降到**前列当前速度**所需距离
        （`EtcsBrakingCurve.braking_distance`：含制动建立期 + 真实坡度分量）。ATP 恰在
        `实际间距 < d_safe` 时介入（ETCS EBI）⇒ 本值即"贴线不越线"的那条线。

        返回 None 表示不可计算（无 ETCS 曲线 / 制动无效 / 非跟随列），调用方回退 `_dynamic_gap`。
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

            # 列间间距误差：前车（i-1）尾部 vs 本列队首 - 动态目标间距
            # E4：目标间距 = 时间间隔×本列速度（VCTS 动态安全间距），非固定 100m
            gap_err = 0.0
            if i > 0:
                prev_tail = self.trains[i - 1].dynamics.pos[-1]
                dyn_gap = self._dynamic_gap()
                gap_err = (prev_tail - self._train_heads[i]) - dyn_gap

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
                tr.set_etcs_targets([EbdTarget(
                    position_m=leading_tail, speed_mps=lead_speed, kind='gap',
                )])
            tr.step(col_actions)
            self._train_heads[i] = float(tr.dynamics.pos[0])
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

        obs = self._get_obs()
        reward = self._calculate_reward(obs, target_accels, accels, executed_throttles)

        self.steps += 1
        terminated = False
        truncated = self.steps >= self.max_steps

        info = {
            'reward': reward,
            'coupler_force_peak': float(self._peak_coupler_n),
            'coupler_force_limit': float(self.coupler_force_limit_n),
            'coupler_limit_violations': int(self._coupler_limit_violations),
            'safety_events': int(self._safety_events),
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
        a = 0
        for ti, (tr, ctrl) in enumerate(zip(self.trains, self.multi_loco_controllers)):
            dyn = tr.dynamics
            vel = float(dyn.vel[0])
            gap_err = 0.0
            if ti > 0:
                prev_tail = self.trains[ti - 1].dynamics.pos[-1]
                gap_err = (prev_tail - self._train_heads[ti]) - self._dynamic_gap()
            # 规则基线（ED 优先 + 错峰 + AB 兜底）——观测告诉 RL"规则本步想做什么"
            base = ctrl.get_action_cyclic_braking(tr, v_max=self.v_max, v_min=self.v_min)
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
                a += 1
        return obs

    def _gap_metrics(self):
        """本步列间间距指标：(间距误差均值 m, 最小实际列间距 m)。

        供训练日志监控（CSV/TB 的 gap_err_mean / gap_min_m 列）。单列编组无列间距，
        返回 (0.0, float('inf'))。
        """
        if self.num_trains <= 1:
            return 0.0, float('inf')
        dyn_gap = self._dynamic_gap()
        errs, gaps = [], []
        for i in range(1, self.num_trains):
            ge = (self.trains[i - 1].dynamics.pos[-1] - self._train_heads[i]) - dyn_gap
            errs.append(ge)
            gaps.append(dyn_gap + ge)
        return float(np.mean(errs)), float(np.min(gaps))

    def _step_decomposed_fleet(self, actions: np.ndarray):
        """decompose 模式 step：每机车 RL 调制 [ed_mod, ab_mod] → 规则基线+调制 → 单列 _step_decomposed。"""
        actions = np.asarray(actions, dtype=float)
        if actions.shape != (self.num_agents, 2):
            raise ValueError(
                f"decompose 动作形状应为 {(self.num_agents, 2)}, 实际 {actions.shape}"
            )
        self._safety_events = 0
        accels = np.zeros(self.num_trains)
        ab_count = 0       # 本步激活的 AB 源总数（奖励塑形：AB 贵）
        ed_sum = 0.0       # 本步 ED 深度合计（ED 便宜，鼓励 ED 优先）
        # 【ADR-021 决策3 / D】安全层对 AB 的"禁新增源"本步计数（跨列车累加）。
        # 逐列车子环境（train_env）已在 info 暴露，此处聚合到 fleet info，供诊断/留痕可观测。
        ab_safety_vetoed_count = 0
        self._step_coupler_peak_n = 0.0  # 本步全列最大车钩力（跨列车取 max；奖励车钩力用真实峰值，非机车局部值）
        a = 0
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
                gap_err = (lead_tail - self._train_heads[ti]) - self._dynamic_gap()
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
                v_bound_max = min(v_bound_max, lead_speed + self.LEAD_TAIL_OFFSET_MPS)
                # 【等速冻结消除 chase 2026-09-09】三列等速时 coordination_adj 追的偏置
                # 因 rel_speed≈0 / gap_err 恒定而无累积 → 间距在 ~1300m 冻结。补救：当
                # follower 仍明显落后（gap_err>死区）时，把缓解线(v_min)抬高到
                # "仅比 lead 快一个小量"的目标速度，使 follower 在带内常态获得正向加速度，
                # 持续缩距直到 gap_err 落入死区（进入死区后撤销 chase，防追过头压迫前列）。
                if gap_err > self.LEAN_CHASE_DEADBAND_M:
                    chase_v = float(np.clip(
                        lead_speed + self.LEAN_CHASE_DELTA_MPS, self.v_min, self.v_max))
                    v_bound_min = max(v_bound_min, chase_v - self.v_min)
            final_edab, _ = ctrl.get_action_decomposed(
                tr, rl, v_max=self.v_max, v_min=self.v_min,
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
            # ETCS 前列尾车监督（与旧模式同语义；decompose 下安全层经投影钳 ED）
            if ti > 0:
                leading_tail = float(self.trains[ti - 1].dynamics.pos[-1])
                lead_speed = float(self.trains[ti - 1].dynamics.vel[0])
                tr.set_etcs_targets([EbdTarget(
                    position_m=leading_tail, speed_mps=lead_speed, kind='gap',
                )])
            _pt_info = tr.step(final_edab)[-1]
            # 【ADR-021 决策3 / D】聚合本列的安全层 AB 权限计数（子环境 info 上抛）
            ab_safety_vetoed_count += int(bool(_pt_info.get('ab_safety_vetoed', False)))
            self._train_heads[ti] = float(tr.dynamics.pos[0])
            accels[ti] = (float(tr.dynamics.vel[0]) - v_before) / max(self.dt, 1e-6)
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
        reward = self._calculate_reward_decomposed(obs, accels, ab_count, ed_sum,
                                                   step_coupler_peak_n=self._step_coupler_peak_n)
        self.steps += 1
        terminated = False
        truncated = self.steps >= self.max_steps
        info = {
            'reward': reward,
            'coupler_force_peak': float(self._peak_coupler_n),
            'coupler_force_limit': float(self.coupler_force_limit_n),
            'coupler_limit_violations': int(self._coupler_limit_violations),
            'safety_events': int(self._safety_events),
            # 列间间距监控（2026-09-23 新增，训练日志 CSV/TB 用）
            **dict(zip(('gap_err_mean', 'gap_min_m'), self._gap_metrics())),
            'executed_actions': self._executed_actions.copy(),
            'actions_modified': False,
            'ab_source_count': ab_count,          # 本步 AB 源数（ED 优先/AB 兜底 分配诊断）
            'mean_ed_frac': ed_sum / max(self.num_agents, 1),
            'decomposed_actions': self._executed_actions.copy(),
            # 【ADR-021 决策3 / D】安全层对 AB 的权限计数（跨列车本步聚合；新增键，既有键不删）
            'ab_safety_vetoed': ab_safety_vetoed_count,
        }
        return obs, reward, terminated, truncated, info

    def _calculate_reward_decomposed(self, obs: np.ndarray, accels: np.ndarray,
                                     ab_count: int, ed_sum: float,
                                     step_coupler_peak_n: float = None) -> float:
        """decompose 模式奖励：限速区间 + 车钩力 + 舒适 + 电空分工塑形。

        与旧模式共享的语义（speed_band/车钩力/舒适/列间间距）沿用原权重；
        新增电空分工塑形（ADR-009.1 第2层"ED 优先 + AB 兜底"）：
        - AB 使用成本 -0.2/源/步：AB 是车钩力（纵向冲动）主源且难恢复（充风时间长），
          让 RL 学"ED 打满、AB 只在 ED 不足时兜底"——这是本架构给 RL 的真物理杠杆；
        - ED 轻成本 -0.02/深度：防无谓满 ED（如低速滑行），但远低于 AB 成本。
        """
        # 【相对列距锚定 2026-09-10】限速区间（循环制动核心）只由领航列承载绝对带责任，
        # 跟随列改为相对锚定前列（列距由 gap_reward 承担、相对速度在此镜像），
        # 避开 53km 多坡段"绝对同速物理不可达"（诊断-2026-09-10 发散短训 35ep 复现）。
        # 文献基准：Zhang2021 逐 agent 连续 APF / Guo2025 大负值硬奖惩（超速不可容忍）；
        # 旧"逐列独立绝对带 + 全局 std 同速"(V3.5.3b) 在 53km 仍是发散根因之一，此处废止为
        # "领航列绝对带 + 跟随列相对锚定"。
        speed_band_reward = 0.0
        rel_anchor_reward = 0.0
        v_center = 0.5 * (self.v_min + self.v_max)
        band_half = 0.5 * (self.v_max - self.v_min)
        force_penalty = 0.0  # 超速硬惩罚（跟随列由相对锚定 + 前置 ETCS 兜底）
        for ti, tr in enumerate(self.trains):
            v = float(tr.dynamics.vel[0])
            if ti == 0:
                # 领航列：锚绝对带（编队节奏负责人）
                norm_dev = abs(v - v_center) / max(band_half, 1e-6)
                if norm_dev <= 1.0:           # 带内：越近中心奖越大（+6 → 0）
                    speed_band_reward += 6.0 * (1.0 - 0.9 * norm_dev)
                else:                          # 越带：越深越罚
                    speed_band_reward -= 0.2 * (norm_dev - 1.0) * 100.0
                if v > self.v_max:             # 超线路限速 → 不可容忍硬罚
                    force_penalty -= 5.0 * (v - self.v_max)
            else:
                # 跟随列：镜像前列可行轨迹（相对速度匹配）——不再被绝对带拖累
                lead_v = float(self.trains[ti - 1].dynamics.vel[0])
                rel_spd_norm = (v - lead_v) / self.REL_ANCHOR_SPD_SCALE
                rel_anchor_reward += self.REL_ANCHOR_SPD_W * max(0.0, 1.0 - rel_spd_norm ** 2)
                # 跟随列绝对线速兜底（轻权重，主要靠 ETCS+车钩钳制；不强行与带中心一致）
                if v > self.v_max * 1.05:
                    force_penalty -= 3.0 * (v - self.v_max)
        # 编队级联稳定性：删除旧全局 rel_vel_penalty(std 全列速度)——逐列绝对同速在 53km
        # 多坡段不可达，已由逐对相对速度镜像(rel_anchor_reward) + 相对列距(gap_reward)替代。

        # 车钩力约束（创新点）。2026-09-10 回滚 SSOT：破线由底层硬安全层 enforce_coupler
        # 杜绝（车钩力定位 = 硬安全层≤1000kN + 观测上下文，不作 reward 强化最小化对象）。
        # 此处仅保留"用本步全列真实峰值"作观测塑形（旧用 obs[:,5] 机车局部值 → 低估；
        # 全列真实峰值更贴合物理约束），但不再施加 -80·ov² 二次硬惩罚——量纲(|-80| >> 带内
        # 收益 ~6)使 value 目标震荡、KL 频繁早停，是诊断-2026-09-10 训练不稳的直接诱因之一；
        # 且破线本就该由安全层兜底，非 reward 职责（SSOT：硬安全层 + 观测上下文）。
        coupler_means = obs[:, 5] if self.num_agents else np.zeros(1)
        if step_coupler_peak_n is not None and step_coupler_peak_n > 0:
            peak_n_norm = step_coupler_peak_n / max(self.coupler_force_limit_n, 1e-9)
        else:
            peak_n_norm = float(np.max(coupler_means)) if len(coupler_means) else 0.0
        coupler_term = -0.2 * float(np.mean(coupler_means)) - 0.2 * peak_n_norm

        # 【ADR-021 决策2 2026-10-01】车钩力"受控超限项"（文献 Tang2020 / Wang2025）：
        # 保留"不作均值最小化"原则（不动 mean(obs[:,5]) 权重），仅对**断线峰值超限**加深
        # 有界梯度。上界 -12 与带外速度惩罚（norm_dev=2 → -20）同档但更小；**刻意避免**
        # -80·ov² 量级（回滚原因：value 目标震荡 / KL 频繁早停，见上方 :757-760 注释）。
        # peak_n_norm < 1（未破线）时该式恒为 0（over=0）。
        over = max(0.0, peak_n_norm - 1.0)
        coupler_over_term = -COUPLER_OVER_W * min(over, COUPLER_OVER_CAP)

        # 舒适性（同旧模式）
        comfort_penalty = -0.3 * float(np.mean(accels ** 2)) if len(accels) else 0.0

        # 列间间距（多列 decompose 后叠阶段复用；单列时无项）
        # 【ADR-026 2026-10-04】改为"ATP 对齐两段式"：效率项（贴近 d_eff=1.1·d_safe 越好）
        # + 危险项（跌破 d_safe 陡罚、**不封顶**）。旧实现（+1.0·exp(-(ge/140)²) 小高斯丘 +
        # max(...,-200) 饱和势场 + 对固定 200m 双向惩罚）已废止：它既不给"贴紧"的奖励，
        # 也在危险区没有梯度（gap≤70m 后恒为 -200），实测最小列距掉到 19m。
        gap_eff_reward = 0.0
        gap_danger_penalty = 0.0
        collision_penalty = 0.0
        gap_trend_penalty = 0.0
        current_gap_err = []
        if self.num_trains > 1:
            for i in range(1, self.num_trains):
                lead_tail = float(self.trains[i - 1].dynamics.pos[-1])
                actual_gap = lead_tail - float(self._train_heads[i])
                d_safe = self._atp_safe_gap(i)
                if d_safe is None:
                    d_safe = self._dynamic_gap()   # 回退（无 ETCS 曲线等）
                current_gap_err.append(actual_gap - d_safe)
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
                    over = (d_safe - actual_gap) / denom
                    gap_danger_penalty -= GAP_DANGER_W * over * over
                if actual_gap < 5.0:
                    # 追尾硬惩罚（保留旧降软值，仅作最后兜底；主要靠上面的危险项）
                    collision_penalty -= 10.0
            if self._prev_gap_err is not None and len(current_gap_err) == len(self._prev_gap_err):
                for i, cur in enumerate(current_gap_err):
                    # 间距在缩小且已贴近安全线（gap-d_safe < 20m）→ 追尾趋势 → 提前惩罚
                    shrink = self._prev_gap_err[i] - cur
                    if shrink > 0.5 and cur < 20.0:
                        gap_trend_penalty -= 0.4 * shrink
            self._prev_gap_err = current_gap_err

        # 电空分工塑形（本架构核心）。诊断-2026-09-25：原 `ab_cost=0.0` 使 AB 在奖励上
        # 完全中性、且在触发舒适/车钩项时被隐式扣分 → seed0 退化成"纯 ED 蠕行"
        # （完整 53km 评估 ab_steps=0、pe41248kN 超限、band 6%、末速18km/h 失速）。
        # 文献张2024_DQN_CyclicBraking_Bownhill 式22："越限 Rc<0 罚 / AB engaged=0 /
        # 释放 Rd>0 奖"的需求驱动塑形。此处对齐但避免引入大系数致 value 震荡（KL 早停）：
        # 用"领航列带外/超速"作为制动需求信号，needy 时 AB 未参与 → 加惩罚，
        # 使"AB 是带内唯一守住速度带的手段"从 reward 里自然涌现。
        ab_cost = 0.0
        # 需求信号 = 领航列是否带外（norm_dev>1）或超线速（v>v_max）。这些量在带内 retable 为 0
        needs_brake = 0.0
        if self.num_trains:
            lv = float(self.trains[0].dynamics.vel[0])
            needs_brake = float(lv > self.v_max) or float(
                abs(lv - v_center) > band_half)
        if needs_brake > 0.0 and ab_count <= 0:
            # 领航列已带外/超速却无 AB 参与 → 弱惩罚，倒逼"需减速时必须靠 AB 兜底"
            ab_cost -= 0.5 * needs_brake
        ed_cost = -0.02 * float(ed_sum)

        return (
            + speed_band_reward
            + rel_anchor_reward
            + force_penalty
            + gap_eff_reward
            + gap_danger_penalty
            + gap_trend_penalty
            + collision_penalty
            + comfort_penalty
            + coupler_term
            + coupler_over_term
            + ab_cost
            + ed_cost
        )

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
            # E4 动态间距：实际间距 = 动态目标 + gap_err（obs[1] 基于动态目标）
            dyn_gap = self._dynamic_gap()
            actual_gap = dyn_gap + obs[i, 1]
            min_gap = dyn_gap * 0.4
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
            if self.v_min <= vel <= self.v_max:
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
