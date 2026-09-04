"""
重载列车群组协同控制 Gym 环境。

多车厢列车纵向编队任务：每节车厢独立控制（牵引/制动），
目标 = 速度同步 + 间距保持 + 纵向冲动（车钩力）最小化。

制动分两类（对应"电控连续 + 空气制动离散"）：
- 电制动（ED）：机车连续可调制动力，即时施加于机车
- 空气制动（AB）：离散档位（MIN/SERVICE/EMERGENCY），沿车列按制动波速向后传播

安全防护：规则式 ATP 安全层（SafetyLayer）在动作喂给动力学前修正危险动作，
约束包括限速、车钩力上限（1000 kN）、列车间距下限。

底层动力学基于 src/train_dynamics（NeTrainSim 公式 + 多体车钩模型）。
"""

import numpy as np
from gym import spaces

from src.train_dynamics.params import VehicleParams, LocomotiveParams, CouplerParams, TrainConsist
from src.train_dynamics.train import TrainDynamics
from src.train_dynamics.braking import AirBrakeNotch, notch_from_throttle
from src.safety_layer import SafetyLayer

# 车钩力最终硬指标上限（牛顿）= 1000 kN
COUPLER_FORCE_LIMIT_N = 1.0e6
# 电制动占制动指令的比例：-1 时电制动打满，空气制动进入 SERVICE
ED_THROTTLE_RATIO = 0.5


def notch_depth(notch: AirBrakeNotch) -> float:
    """空气制动离散档位对应的制动深度（0~1，用于车钩力安全钳制的等价投影）。"""
    return {
        AirBrakeNotch.RELEASE: 0.0,
        AirBrakeNotch.MIN: 0.2,
        AirBrakeNotch.SERVICE: 0.75,
        AirBrakeNotch.EMERGENCY: 1.0,
    }.get(notch, 0.0)


def default_consist(num_vehicles: int = 4, num_locomotives: int = 1):
    """默认重载列车编组：1 机车在前 + (num_vehicles-1) 节货车。"""
    loco = LocomotiveParams(
        mass_t=188.0, no_of_axles=6, frontal_area_m2=11.5, drag_coef=1.4,
        length_m=21.0, max_power_kw=9600.0, transmission_efficiency=0.85,
        max_speed_mps=30.0, n_notches=8,
    )
    car = VehicleParams(
        mass_t=100.0, no_of_axles=4, frontal_area_m2=10.0, drag_coef=1.0,
        length_m=20.0,
    )
    return TrainConsist([loco] + [car for _ in range(num_vehicles - num_locomotives)])


def consist_10kt_1plus0():
    """一万吨级 1+0 编组：1 台 HXD3B 机车 + 100 节 C80 货车（约 10188 t）。

    对应论文研究对象"一万吨级 1+0 重载列车群组"的单列单元。
    """
    loco = LocomotiveParams(
        mass_t=188.0, no_of_axles=6, frontal_area_m2=11.5, drag_coef=1.4,
        length_m=21.0, max_power_kw=9600.0, transmission_efficiency=0.85,
        max_speed_mps=30.0, n_notches=8,
    )
    # C80 货车：载重 80t + 自重 20t ≈ 100t，4 轴
    car = VehicleParams(
        mass_t=100.0, no_of_axles=4, frontal_area_m2=10.0, drag_coef=1.0,
        length_m=12.0,  # C80 长度约 12m
    )
    return TrainConsist([loco] + [car for _ in range(100)])


def consist_20kt_1plus108_1plus108():
    """二万吨级组合列车：1 机车 + 108 货车 + 1 机车 + 108 货车（约 20176 t）。

    对齐 Zhang2024 / 张二田实测编组（1+108+1+108），用于编组规模效应验证：
    同一模型下 2 万吨循环制动车钩力应接近实测 929/1021 kN，
    以证明仿真器能代表 1 万吨 1+0 编组（527/597 kN 是编组差异的合理结果）。
    """
    loco = LocomotiveParams(
        mass_t=188.0, no_of_axles=6, frontal_area_m2=11.5, drag_coef=1.4,
        length_m=21.0, max_power_kw=9600.0, transmission_efficiency=0.85,
        max_speed_mps=30.0, n_notches=8,
    )
    car = VehicleParams(
        mass_t=100.0, no_of_axles=4, frontal_area_m2=10.0, drag_coef=1.0,
        length_m=12.0,
    )
    return TrainConsist([loco] + [car for _ in range(108)] +
                        [loco] + [car for _ in range(108)])


def consist_20kt_1plus1_validation():
    """赵紫宁 2022 验证编组：2×HXD1（200 t, 35.3 m）+ 216×C80（100 t, 12.1 m）。

    总重 22000 t、全长 2684.2 m —— 与 Zhao2022 §5.1 编组表、fig53 速度锚点
    CSV 完全一致（机车质量/长度、货车质量/长度）。**验证专用，勿作论文研究对象**
    （研究对象仍是 1 万吨 1+0）。用于 P0-2：赵紫宁 8 锚点速度曲线复现 + 张二田
    S1 统计对照（同 2 万吨 1+1 编组）。
    """
    loco = LocomotiveParams(
        mass_t=200.0, no_of_axles=8, frontal_area_m2=11.5, drag_coef=1.4,
        length_m=35.3, max_power_kw=9600.0, transmission_efficiency=0.85,
        max_speed_mps=33.3, n_notches=8,
    )
    car = VehicleParams(
        mass_t=100.0, no_of_axles=4, frontal_area_m2=10.0, drag_coef=1.0,
        length_m=12.1,
    )
    return TrainConsist([loco] + [car for _ in range(108)] +
                        [loco] + [car for _ in range(108)])


def consist_10kt_1plus1():
    """一万吨级 1+1 编组（多机车分布式动力）：1 机车 + 94 货车 + 1 机车（约 9976 t）。

    【2026-09-03 智能体分解重构（ADR-009）】多机车作"体"的研究级编组：
    - 队首 + 队尾各 1 台机车（vdp 分布式动力），index [0, 95]
    - 总重 ≈ 188 + 94×100 + 188 ≈ 9976 t（保持论文"一万吨级"口径）
    - 用于验证"每机车=子控制器，独立决策电制动/空气制动分工"（decompose='loco_ed_ab'）
    """
    loco = LocomotiveParams(
        mass_t=188.0, no_of_axles=6, frontal_area_m2=11.5, drag_coef=1.4,
        length_m=21.0, max_power_kw=9600.0, transmission_efficiency=0.85,
        max_speed_mps=30.0, n_notches=8,
    )
    car = VehicleParams(
        mass_t=100.0, no_of_axles=4, frontal_area_m2=10.0, drag_coef=1.0,
        length_m=12.0,
    )
    return TrainConsist([loco] + [car for _ in range(94)] + [loco])


CONSIST_PRESETS = {
    'default': default_consist,
    '10kt_1plus0': consist_10kt_1plus0,
    '10kt_1plus1': consist_10kt_1plus1,
    '20kt_1plus108_1plus108': consist_20kt_1plus108_1plus108,
    '20kt_1plus1_validation': consist_20kt_1plus1_validation,
}


class TrainFormationEnv:
    """
    重载列车编队控制环境（多智能体）。

    Args:
        config (Dict): 配置
            - num_vehicles: 车辆数（默认 4）
            - num_locomotives: 机车数（默认 1，位于队首）
            - dt: 积分步长（秒）
            - target_speed: 目标巡航速度（m/s）
            - target_gap: 目标车钩间距（m）
            - max_steps: 每回合最大步数
            - grade: 坡度（默认 0）
            - enable_safety: 是否启用规则式 ATP 安全层（默认 True）
            - coupler_force_limit_n: 车钩力上限（默认 1000 kN）
    """

    def __init__(self, config: dict = None):
        config = config or {}
        self.num_vehicles = config.get('num_vehicles', 4)
        self.num_locomotives = config.get('num_locomotives', 1)
        self.dt = config.get('dt', 0.1)
        self.target_speed = config.get('target_speed', 20.0)
        self.target_gap = config.get('target_gap', 1.0)
        self.max_steps = config.get('max_steps', 500)
        self.grade = config.get('grade', 0.0)
        self.grade_profile_name = config.get('grade_profile', None)  # 'long_downhill'/'gradual_to_steep'/'v_shape'
        self.enable_safety = config.get('enable_safety', True)
        self.coupler_force_limit_n = config.get('coupler_force_limit_n', COUPLER_FORCE_LIMIT_N)
        # E7：缓解空气制动用同步（True，第1层简化物理，RL能学循环制动不掉速）
        # 还是缓解波传播（False，第2层物理真实，保留"缓解后车钩力最大"机制）
        self.release_sync = config.get('release_sync', False)
        # E8：可控尾车 EOT（缓解时尾部同步排风，双向缓解波，提升缓解同步性）。
        # 论文依据：Zhang2025 大秦线 20kT EOT 使最大拉钩力 780→489kN（-37%）。
        # 用于缓解波下把"缓解后车钩力"峰值降到 1000kN 以内。
        self.eot = config.get('eot', False)
        # 【2026-08-30 基线对齐】多机同步制动（LTE-R 同步操控，张二田2021）：
        # 制动指令时所有机车（含中置从控）作为波源双向传播，初制动时差 ~3s。
        self.sync_loco_brake = config.get('sync_loco_brake', True)

        # 编组预设：优先用预设（如万吨级 1+0），否则按 num_vehicles 构造默认
        consist_preset = config.get('consist_preset', None)
        if consist_preset:
            if consist_preset not in CONSIST_PRESETS:
                raise ValueError(f"未知编组预设: {consist_preset}，可选: {list(CONSIST_PRESETS.keys())}")
            consist = CONSIST_PRESETS[consist_preset]()
            self.num_vehicles = consist.num_vehicles
        else:
            consist = default_consist(self.num_vehicles, self.num_locomotives)
        self.dynamics = TrainDynamics(consist, dt=self.dt)
        # 优先使用坡度剖面（长大下坡场景），否则用恒定坡度
        if self.grade_profile_name:
            from src.train_dynamics.grade_profile import PROFILES
            if self.grade_profile_name in PROFILES:
                self.dynamics.set_grade_profile(PROFILES[self.grade_profile_name]())
            else:
                raise ValueError(f"未知坡度剖面: {self.grade_profile_name}，可选: {list(PROFILES.keys())}")
        elif self.grade:
            self.dynamics.set_grade(self.grade)

        # 车钩力范围估计（约束观察/奖励缩放）
        self._max_coupler_n = self.coupler_force_limit_n

        # 【bug修复 2026-08-20】线路限速（ATP 限速保护/超速指标口径）。
        # 原实现用机车物理限速 max_speed_mps（30m/s=108km/h）作安全层限速保护，
        # 与场景限速区间 [40,80]km/h 不符（80km/h 线路限速完全不在安全层保护内）。
        # 现默认取机车限速，但可由外部传入 line_speed_limit_mps（如 fleet 传 80/3.6）。
        # 安全层用 line_speed_limit_mps 作限速防护，物理限速 max_speed_mps 保留为兜底。
        self.line_speed_limit_mps = config.get(
            'line_speed_limit_mps', consist.vehicles[0].max_speed_mps
        )
        # ETCS 前瞻式超速防护（"真 ATP"）：enable_etcs=True 时由安全层对给定前方目标
        #   （由外部 set_etcs_targets 注入，多列群组中=前列尾车）计算 EBD/EBI 监督限位，
        #   超限强制制动。etcs_curve 为共享曲线（多列同编组可复用）；缺省 None 不启用。
        #   max_speed_mps 仍传给安全层作线速兜底（与 ETCS 共存，见 safety_layer 规则1）。
        self.enable_etcs = config.get('enable_etcs', False)
        self.etcs_curve = config.get('etcs_curve', None)
        # 当前前方 ETCS 目标点（由 fleet 每步 set_etcs_targets 更新；单列场景可置空）
        self.etcs_targets = []
        self.safety = SafetyLayer(
            num_vehicles=self.num_vehicles,
            max_speed_mps=self.line_speed_limit_mps,
            coupler_force_limit_n=self.coupler_force_limit_n,
            min_gap_m=self.target_gap * 0.1,
            enable_etcs=self.enable_etcs,
        )

        # 【2026-09-03 智能体分解重构（ADR-009）】decompose='loco_ed_ab' 模式：
        # 把"整列统一 throttle"改为"每机车独立 (电制动, 空气制动)"，列内多智能体分工。
        # 默认 None 完全不动原逻辑（向后兼容）。
        self.decompose = config.get('decompose', None)
        self.loco_indices = list(self.dynamics.consist.locomotive_indices)
        self.num_locomotives = len(self.loco_indices)

        # 每节车的观察：速度误差、位置误差（相对前车）、车钩力、位置
        self.obs_dim = 4
        self.observation_space = spaces.Box(
            low=-np.inf, high=np.inf,
            shape=(self.num_vehicles, self.obs_dim), dtype=np.float32,
        )
        if self.decompose:
            # decompose：动作 = 每机车 [电制动, 空气制动]（(num_locos, 2)）
            self.action_space = spaces.Box(
                low=-1.0, high=1.0,
                shape=(self.num_locomotives, 2), dtype=np.float32,
            )
        else:
            # 默认：动作 = 每节车 throttle ∈ [-1,1]，>0 牵引，<0 制动
            self.action_space = spaces.Box(
                low=-1.0, high=1.0, shape=(self.num_vehicles,), dtype=np.float32,
            )

        self.steps = 0

        # 最终指标统计（车钩力 1000 kN）
        self._peak_coupler_n = 0.0
        self._coupler_limit_violations = 0
        self._overspeed_violations = 0
        self._safety_events = 0

    def reset(self, seed=None, options=None):
        self.steps = 0
        self.safety.reset()
        self.dynamics.set_initial_speed(0.0)
        if options and 'speed' in options:
            self.dynamics.set_initial_speed(options['speed'])
        # 重置最终指标
        self._peak_coupler_n = 0.0
        self._coupler_limit_violations = 0
        self._overspeed_violations = 0
        self._safety_events = 0
        return self._get_obs(), {}

    def _get_obs(self) -> np.ndarray:
        """构造观察：每节车 [速度误差, 与前车间距误差, 车钩力, 位置]。"""
        pos = self.dynamics.pos
        vel = self.dynamics.vel
        coupler = np.abs(self.dynamics._coupler_forces())
        obs = np.zeros((self.num_vehicles, self.obs_dim), dtype=np.float32)
        for i in range(self.num_vehicles):
            speed_err = vel[i] - self.target_speed
            gap_err = 0.0
            if i > 0:
                gap_err = (pos[i - 1] - pos[i]) - self.target_gap
            obs[i, 0] = speed_err
            obs[i, 1] = gap_err
            obs[i, 2] = coupler[i] / self._max_coupler_n
            obs[i, 3] = pos[i] * 0.01  # 位置缩放
        return obs

    def _calculate_reward(self, obs: np.ndarray, coupler: np.ndarray) -> float:
        """奖励：速度同步 + 间距保持 + 冲动最小化（含峰值惩罚与超限惩罚）。"""
        speed_err = np.mean(np.abs(obs[:, 0]))
        gap_err = np.mean(np.abs(obs[:, 1]))
        # 平均冲动 + 峰值冲动（峰值更能反映纵向冲动风险）
        mean_impulse = np.mean(np.abs(coupler)) / self._max_coupler_n
        peak_impulse = np.max(np.abs(coupler)) / self._max_coupler_n if len(coupler) else 0.0
        # 车钩力超限惩罚：按超限幅度成比例（超得越多罚得越重），
        # 替代原常数 -2.0（V5.4 教训：常数惩罚无梯度信息，策略学不会"平稳制动"）。
        # 超限幅度 = (峰值 - 上限) / 上限，无量纲；乘以惩罚系数给策略强梯度信号。
        abs_c = np.abs(coupler)
        peak = np.max(abs_c) if len(abs_c) else 0.0
        violation_penalty = 0.0
        if peak > self.coupler_force_limit_n:
            over_ratio = (peak - self.coupler_force_limit_n) / self.coupler_force_limit_n
            violation_penalty = -5.0 * over_ratio  # 超限 1 倍 → -5.0，2.5 倍 → -12.5
        reward = (
            -0.5 * speed_err
            - 0.3 * gap_err
            - 0.2 * mean_impulse
            - 0.2 * peak_impulse
            + violation_penalty
        )
        return reward

    def set_etcs_targets(self, targets: list):
        """设置本列前方 ETCS 监督目标点（多列群组中=前列尾车的动态位置）。"""
        self.etcs_targets = list(targets)

    def _state_snapshot(self) -> dict:
        """当前动力学状态快照（供安全层使用）。"""
        n = self.num_vehicles
        pos = self.dynamics.pos
        gaps = np.full(n, self.safety.min_gap_m)
        for i in range(1, n):
            gaps[i] = pos[i - 1] - pos[i]
        # 是否紧急制动工况（Fu2019：紧急制动时车钩力上限放宽到 2250kN）
        ab_state = self.dynamics.air_brake_state()
        is_emergency = any(x == AirBrakeNotch.EMERGENCY for x in ab_state)
        snap = {
            'vel': self.dynamics.vel.copy(),
            'coupler_forces': np.abs(self.dynamics._coupler_forces()),
            'gaps': gaps,
            'emergency': is_emergency,
        }
        # 启用 ETCS 时注入前瞻式监督所需数据（车头里程 + 前方目标 + 共享曲线）
        if self.enable_etcs and self.etcs_curve is not None:
            snap['head_position_m'] = float(pos[0])
            snap['etcs_curve'] = self.etcs_curve
            snap['etcs_targets'] = list(self.etcs_targets)
        return snap

    def _update_metrics(self, coupler: np.ndarray):
        """更新最终指标统计。"""
        abs_c = np.abs(coupler)
        if len(abs_c):
            self._peak_coupler_n = max(self._peak_coupler_n, float(np.max(abs_c)))
            self._coupler_limit_violations += int(np.sum(abs_c > self.coupler_force_limit_n))
        # 【bug修复 2026-08-20】超速指标按线路限速 line_speed_limit_mps 统计
        # （原实现按机车物理限速 max_speed_mps=108km/h，与论文"超80率"指标口径不符）
        if np.max(self.dynamics.vel) > self.line_speed_limit_mps:
            self._overspeed_violations += 1

    def step(self, actions: np.ndarray):
        if self.decompose:
            return self._step_decomposed(actions)
        actions = np.asarray(actions, dtype=float).flatten()
        if actions.shape[0] != self.num_vehicles:
            raise ValueError(f"动作维度应为 {self.num_vehicles}, 实际 {actions.shape[0]}")

        # 规则式 ATP 安全层：修正危险动作
        # 注意：修正后动作才是"实际执行动作"，训练时必须用它重算 log_prob，
        # 否则 log_prob 对应的是修正前动作 → 实际执行策略≠学习策略 → 重要性采样失效 → 策略发散
        actions_modified = False
        if self.enable_safety:
            original_actions = actions.copy()
            actions = self.safety.protect(actions, self._state_snapshot())
            actions_modified = not np.allclose(actions, original_actions, atol=1e-9)
            self._safety_events += len(self.safety.last_events)

        # 拆分动作为：牵引 / 电制动 / 空气制动
        throttle = np.zeros(self.num_vehicles)
        ed_throttle = np.zeros(self.num_vehicles)
        ab_command = AirBrakeNotch.RELEASE
        for i, a in enumerate(actions):
            vehicle = self.dynamics.consist.vehicles[i]
            if a > 0 and vehicle.is_locomotive:
                throttle[i] = float(a)
            elif a < 0:
                # 负动作：电制动（连续，仅机车）+ 空气制动（离散，队首传播）
                b = float(-a)
                if vehicle.is_locomotive:
                    ed_throttle[i] = min(b * ED_THROTTLE_RATIO, 1.0)
                # 空气制动档位由队首（第一个负动作）决定，向后传播
                # notch_from_throttle 接收负值（-1~0），a 即为此负值
                notch = notch_from_throttle(a)
                if self._air_brake_priority(notch, ab_command):
                    ab_command = notch

        # 【2026-08-30 基线对齐】多机同步制动（LTE-R 机车同步操控）：
        # "1+1"编组的中置从控机车同步响应制动指令，空气制动波从所有机车
        # 双向传播（张二田2021：2万吨初制动时差仅~3s，缓解时差~10s）。
        # 原单源队首发波 → 后半列延迟9-12s前涌 → 中置机车旁车钩力虚高
        # （A基准 2843 kN vs 实测 650-1430 kN）。
        ab_sources = None
        if ab_command != AirBrakeNotch.RELEASE and self.sync_loco_brake:
            ab_sources = [
                (i, ab_command) for i, v in enumerate(self.dynamics.consist.vehicles)
                if v.is_locomotive
            ]
        self.dynamics.step_vehicles_ed_ab(
            throttle, ed_throttle, ab_command, release_sync=self.release_sync,
            eot=self.eot, ab_sources=ab_sources,
        )

        obs = self._get_obs()
        coupler = np.abs(self.dynamics._coupler_forces())
        reward = self._calculate_reward(obs, coupler)
        self._update_metrics(coupler)

        self.steps += 1
        terminated = False
        truncated = self.steps >= self.max_steps

        # 安全终止：车速溢出（兜底）
        if np.max(np.abs(self.dynamics.vel)) > 200.0:
            terminated = True
            reward -= 10.0

        info = {
            'speed': float(np.mean(self.dynamics.vel)),
            'formation_gap_err': float(np.mean(np.abs(obs[:, 1]))),
            'coupler_force': float(np.mean(np.abs(coupler))),
            'coupler_force_peak': float(np.max(coupler)),
            'coupler_force_limit': float(self.coupler_force_limit_n),
            'coupler_limit_violations': int(self._coupler_limit_violations),
            'overspeed_violations': int(self._overspeed_violations),
            'safety_events': int(self._safety_events),
            'reward': reward,
            # 安全层修正后的实际执行动作（训练须用它重算 log_prob，保证一致性）
            'executed_actions': np.array(actions, dtype=float),
            # 本步安全层是否修正了动作（False 时训练可复用 select_actions 的 log_prob，省一次前向）
            'actions_modified': bool(actions_modified),
        }
        return obs, reward, terminated, truncated, info

    def _step_decomposed(self, actions: np.ndarray):
        """【ADR-009】decompose 模式的 step：每机车独立 (电制动 ED, 空气制动 AB)。

        actions 形状 (num_locomotives, 2)，每行 [ed_frac, ab_frac]:
          - ed_frac ∈ [0,1]：该机车电制动（连续，即时，无波速传播）
          - ab_frac ∈ [-1,0)：该机车作为独立空气制动波源（notch_from_throttle 取档位）
          - ab_frac >= 0    ：该机车不作空气制动源（缓解）

        车钩力安全：投影为逐车 throttle 走 SafetyLayer 钳制（超限缓和），再映射回 (ED,AB)。
        组装 ab_sources 时剔除 RELEASE 源（避免"缓机放在首位触发整列缓解"坑，train.py:508）。
        """
        act = np.asarray(actions, dtype=float)
        if act.ndim == 1:
            act = act.reshape(self.num_locomotives, 2)
        if act.shape != (self.num_locomotives, 2):
            raise ValueError(
                f"decompose 动作形状应为 {(self.num_locomotives, 2)}, 实际 {act.shape}"
            )

        throttle = np.zeros(self.num_vehicles)
        ed_throttle = np.zeros(self.num_vehicles)

        # 组装 ab_sources：只含非缓解档位的机车源（RELEASE 剔除，避免整列缓解坑）
        ab_sources = []
        any_ab = False
        for k, loco_idx in enumerate(self.loco_indices):
            ed_frac = float(np.clip(act[k, 0], 0.0, 1.0))
            ab_frac = float(act[k, 1])
            ed_throttle[loco_idx] = ed_frac
            if ab_frac < 0:
                notch = notch_from_throttle(ab_frac)
                if notch != AirBrakeNotch.RELEASE:
                    ab_sources.append((loco_idx, notch))
                    any_ab = True
        # 全缓时用 ab_command=None（=不使用空气制动，train.py pass 分支），较全 RELEASE 更安全
        ab_command = AirBrakeNotch.RELEASE if any_ab else None

        # 车钩力安全钳制：投影为整列逐车 throttle 近似走 SafetyLayer（制动方向保守安全）
        proj_throttle = np.zeros(self.num_vehicles)
        for k, loco_idx in enumerate(self.loco_indices):
            depth = max(float(act[k, 0]), 0.0)
            if act[k, 1] < 0:
                depth = max(depth, notch_depth(notch_from_throttle(float(act[k, 1]))))
            proj_throttle[loco_idx] = -depth
        actions_modified = False
        if self.enable_safety:
            original = proj_throttle.copy()
            proj_throttle = self.safety.protect(proj_throttle, self._state_snapshot())
            actions_modified = not np.allclose(proj_throttle, original, atol=1e-9)
            self._safety_events += len(self.safety.last_events)
        # 依据安全层修正，更新每机车 ED（安全层钳降则同步降 ED）
        for k, loco_idx in enumerate(self.loco_indices):
            ed_throttle[loco_idx] = min(ed_throttle[loco_idx],
                                        max(-proj_throttle[loco_idx], 0.0))

        self.dynamics.step_vehicles_ed_ab(
            throttle, ed_throttle, ab_command, release_sync=self.release_sync,
            eot=self.eot, ab_sources=ab_sources if ab_sources else None,
        )

        obs = self._get_obs()
        coupler = np.abs(self.dynamics._coupler_forces())
        reward = self._calculate_reward(obs, coupler)
        self._update_metrics(coupler)

        self.steps += 1
        terminated = False
        truncated = self.steps >= self.max_steps
        if np.max(np.abs(self.dynamics.vel)) > 200.0:
            terminated = True
            reward -= 10.0

        info = {
            'speed': float(np.mean(self.dynamics.vel)),
            'formation_gap_err': float(np.mean(np.abs(obs[:, 1]))),
            'coupler_force': float(np.mean(np.abs(coupler))),
            'coupler_force_peak': float(np.max(coupler)),
            'coupler_force_limit': float(self.coupler_force_limit_n),
            'coupler_limit_violations': int(self._coupler_limit_violations),
            'overspeed_violations': int(self._overspeed_violations),
            'safety_events': int(self._safety_events),
            'reward': reward,
            'executed_actions': np.array(act, dtype=float),
            'actions_modified': bool(actions_modified),
            'decomposed_actions': act.copy(),
        }
        return obs, reward, terminated, truncated, info

    @staticmethod
    def _air_brake_priority(candidate: AirBrakeNotch, current: AirBrakeNotch) -> bool:
        """空气制动档位取更紧急者（EB > SERVICE > MIN > RELEASE）。"""
        order = {
            AirBrakeNotch.RELEASE: 0,
            AirBrakeNotch.MIN: 1,
            AirBrakeNotch.SERVICE: 2,
            AirBrakeNotch.EMERGENCY: 3,
        }
        return order[candidate] > order[current]

    def close(self):
        pass
