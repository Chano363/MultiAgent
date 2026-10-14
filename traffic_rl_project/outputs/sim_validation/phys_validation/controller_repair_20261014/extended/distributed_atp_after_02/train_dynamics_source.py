"""
列车纵向动力学（多体模型）。

每节车为独立质点，受到：
    F_i = F_tractive_i - F_brake_i - F_resist_i - F_grade_i + F_coupler_front_i + F_coupler_rear_i

其中：
- F_tractive：机车牵引力（仅机车有，throttle 驱动）
- F_brake：制动力（与运动方向相反）
- F_resist：Davis 阻力（恒与运动方向相反）
- F_grade：坡度阻力（下坡为正，上坡为负），m*g*sin(grade)
- F_coupler：相邻车钩力（弹簧-阻尼）

积分采用半隐式 Euler，时间步默认 0.1s。
"""

import numpy as np

from .resistance import G, resistance_force_n
from .tractive import tractive_force, throttle_coefficient
from .braking import (
    braking_force, BrakeShoeType, AirBrakeNotch,
    air_brake_force_n, air_brake_force_real, electric_brake_force_n,
    notch_from_throttle, cyclic_braking_degrade,
    tail_pressure_to_cyl_ratio, cylinder_pressure_gradient,
)
from .coupler import (
    RONG2025_X_M, RONG2025_FL_N, RONG2025_FU_N, STIFFNESS_BASE_N_PER_M,
)
from .params import TrainConsist, CouplerParams


# 空气制动波速（米/秒），沿车列从机车向后传播。
# 常用制动约 200 m/s，紧急制动约 250 m/s。
AIR_BRAKE_PROPAGATION_SPEED_SERVICE = 200.0
AIR_BRAKE_PROPAGATION_SPEED_EMERGENCY = 250.0


class TrainDynamics:
    """
    多体列车纵向动力学。

    Args:
        consist: 列车编组（TrainConsist）
        coupler: 车钩参数（CouplerParams）
        dt: 积分时间步（秒）
        friction_coef: 轮轨摩擦系数
    """

    def __init__(
        self,
        consist: TrainConsist,
        coupler: CouplerParams = None,
        dt: float = 0.1,
        friction_coef: float = 0.9,
        enable_cyclic_degrade: bool = None,   # 【2026-09-06 R0-D】None=默认启用（主场景基线物理）
        tail_pressure_kpa: float = None,      # 【2026-09-03 L1】列尾压强（kPa）（仅 DEBUG 工况）
        couplers: list = None,                # 【E4-H 异构】逐耦合 CouplerParams（len=n-1）或 None=齐次 self.coupler（MT-2，全列统一）
        simcase: str = 'official',            # 【治理】official 禁止调试物理；debug 才允许关闭 B3/L1
        release_exhaust_tau_s: float = 6.0,   # 【2026-09-06 R0-E】缓解排气时间常数（秒，
                                              # 按刘博阳 L1 拉钩力锚 742/1058/1337 kN 标定，文献无解析值）
    ):
        self.consist = consist
        self.coupler = coupler or CouplerParams()
        self.couplers = couplers
        self.simcase = simcase
        # 【R0-D 2026-09-06】循环制动性能衰减升级为主场景基线物理（赵紫宁表5-5
        # C_β 段间衰减，首段=1.0 不改变首段量级）。None → True；debug 工况可
        # 显式关闭做消融；official 下显式 False = 调试物理进正式流程 → 拒绝。
        if enable_cyclic_degrade is None:
            enable_cyclic_degrade = True
        # 【治理】枚举门禁：official 下调试物理开关直接抛异常（不做静默布尔关闭）
        if simcase == 'official':
            if tail_pressure_kpa is not None:
                raise RuntimeError(
                    "[case-guard] 调试物理(L1列尾压)不能进入 official TrainDynamics "
                    "simcase='official'")
            if not enable_cyclic_degrade:
                raise RuntimeError(
                    "[case-guard] 显式关闭 B3循环衰减属调试物理，不能进入 official "
                    "TrainDynamics simcase='official'（用 simcase='debug'）")
        self._cp = self._build_coupler_param_arrays()   # 逐耦合力参数字典（长度 n-1）
        self.dt = dt
        self.friction_coef = friction_coef
        # 【2026-09-03 B3 / 2026-09-06 R0-D 升级】赵紫宁表5-5 C_β 段间衰减
        # （0.705/0.676）。自 R0-D 起为主场景基线物理（默认启用，首段=1.0），
        # debug 工况可显式关闭做消融。
        self.enable_cyclic_degrade = enable_cyclic_degrade
        # 【2026-09-06 R0-E】缓解排气时间常数：缓解波到达后制动缸按
        # exp(-t/τ) 排风（真实排气非线性、非瞬时），替代"随缓解波进度线性渐变"。
        self.release_exhaust_tau_s = release_exhaust_tau_s
        self._brake_segment = 0   # 当前空气制动段序号（从 1 计，0=未制动过）
        self._brake_was_active = False  # 上一步是否处于制动状态（段切换检测）
        # 【2026-09-03 L1 列尾压强梯度】刘博阳 L6 平衡压梯度。
        # None=无梯度（默认，向后兼容）；给定列尾压强 → 后部制动力按比例弱化。
        self.tail_pressure_kpa = tail_pressure_kpa
        self._cyl_gradient = None  # 缓存的每车平衡压系数（首次需要时计算）

        n = consist.num_vehicles
        self.pos = np.zeros(n)      # 每节车参考点位置（米）
        self.vel = np.zeros(n)      # 每节车速度（米/秒）
        self.grade = np.zeros(n)    # 每节车所在坡度
        self.time = 0.0

        # 能耗追踪（kWh）：累计牵引能量（力×速度×dt 沿机车积分）
        self.energy_kwh = 0.0
        self._energy_delta_kwh = 0.0  # 单步能耗增量（供奖励用）

        # 空气制动传播状态：
        #   _air_brake_active[i] 是否已接收制动指令
        #   _air_brake_notch[i]   当前实际生效的离散档位
        #   _air_brake_delay_remaining[i] 剩余传播延迟（秒）
        self._air_brake_active = np.zeros(n, dtype=bool)
        self._air_brake_notch = np.array(
            [AirBrakeNotch.RELEASE] * n, dtype=object
        )
        self._air_brake_delay_remaining = np.zeros(n)
        # 制动波目标档位（并行倒数用）：delay 减到 0 时该车按 pending 档位激活
        self._air_brake_pending = np.full(n, None, dtype=object)
        self._air_brake_upgrade_pending = np.full(n, None, dtype=object)
        self._air_brake_upgrade_delay = np.zeros(n)
        # 缓解波状态：_air_brake_releasing[i]=True 表示该节"已接收缓解指令、等待传播解除制动"
        # 真实空气制动缓解是"缓解波"按波速从车头向后传播（车头先缓、车尾后缓），
        # 这种不同步正是"缓解后车钩力最大"（张二田/刘博阳/王宏宇/李蔚 一致）的物理根源。
        self._air_brake_releasing = np.zeros(n, dtype=bool)
        # 缓解波初始延迟总量（记录每节车缓解开始时到释放的时间，供制动力渐变衰减）
        self._air_brake_delay_total = np.zeros(n)
        # 缓解制动力衰减系数（0~1，1=满制动，0=完全释放）。
        # E7 物理改进：真实空气制动缓解是"制动力逐渐衰减"（逐步排风），
        # 而非"延迟期间保持满制动后突然释放"。原实现缓解波期间尾部保持 SERVICE
        # 满制动直到 6.1s 延迟结束才释放 → 掉速到0。改为随缓解波进度渐变衰减，
        # 既保留"缓解不同步→车钩力最大"的物理现象，又避免持续制动导致掉速。
        # 【2026-09-06 R0-E 重构】衰减曲线改为两段式：缓解波传播期（delay_remaining>0）
        # 保持满制动（管压波未到，制动缸不排风），波到达后按
        # exp(-t/τ) 排风衰减（τ=release_exhaust_tau_s）——替代原"线性随波渐变"
        # （线性渐变把"管压波传播"与"制动缸排气"混为一谈，且头车瞬时归零）。
        self._air_brake_release_frac = np.ones(n)
        # 缓解排气已进行时间（秒）：波到达（delay_remaining≤0）后开始累计
        self._air_brake_exhaust_t = np.zeros(n)

        self._spacing()  # 按车钩自由长度初始化位置

        # 【2026-08-30 标准 LTD 重构】Newmark-β 积分状态：上一步加速度（用于隐式步进）
        self._acc0 = np.zeros(n)
        # 【2026-08-30 缺失物理补全】制动缸升压过程：真实制动缸压力需 ~10s 上升至峰值
        # （周占松 2026："制动缸压力在约 10 秒内上升至峰值"；杨敏用静置试验升压曲线）。
        # 原实现阶跃施加满制动力（波到即满）→ 冲击远超真实（双基准 B 偏差 +1100%）。
        self._brake_pressure = np.zeros(n)   # 每节车制动缸压力系数 0~1
        # 【2026-09-02 P0-3】连续减压量覆盖（kPa）。None=按档位默认减压量
        # （BRAKE_NOTCH_REDUCTION_KPA），非 None 时对生效车辆施加该减压量当量。
        # 仅用于"减压量连续"工况（张二田 S5、赵紫宁循环制动、L1 列尾压强），
        # 训练/评估流程不传此参数（向后兼容）。
        self._brake_reduction_override_kpa = None
        self.brake_rise_time_s = 10.0        # 制动缸升压时间（秒，紧急制动 ~10s）
        # Newmark-β Picard 迭代参数（子步进后每控制步迭代 10×此值，是主要算力开销；
        # 设为可调属性，便于在精度/速度间权衡与实测调优）
        self.newmark_max_iter = 30
        self.newmark_tol = 1e-5
        # 【2026-08-30 基线对齐】分档位制动缸升压时间（李蔚2023：常用制动
        # "充气时间长，呈发散式"；周占松2026升压曲线：常用明显慢于紧急）。
        # 常用全制动升压慢 → 头尾制动力差积累更缓 → 前堵后涌峰值更低。
        self.brake_rise_time_by_notch = {
            AirBrakeNotch.MIN: 20.0,
            AirBrakeNotch.SERVICE: 18.0,
            AirBrakeNotch.EMERGENCY: 10.0,
            AirBrakeNotch.RELEASE: 18.0,
        }

    def _spacing(self):
        """按车钩自由长度均匀排列车辆。"""
        n = self.num_vehicles
        self.pos = np.zeros(n)
        # 前车在 0，后车依次在其后一个 free_length
        for i in range(1, n):
            self.pos[i] = self.pos[i - 1] - self.coupler.free_length_m

    @property
    def num_vehicles(self) -> int:
        return self.consist.num_vehicles

    @property
    def masses_kg(self) -> np.ndarray:
        return np.array([v.mass_t for v in self.consist.vehicles]) * 1000.0

    def set_grade(self, grade: float):
        """设置统一坡度（无量纲）。"""
        self.grade = np.full(self.num_vehicles, grade)

    def set_grade_profile(self, profile) -> None:
        """设置线路坡度剖面（GradeProfile），每步按车辆位置实时更新坡度。"""
        self._grade_profile = profile
        # 立即按当前位置更新一次
        self._update_grade_from_profile()

    def _update_grade_from_profile(self) -> None:
        """根据每节车当前位置从坡度剖面查询坡度（无量纲）。"""
        if getattr(self, '_grade_profile', None) is not None:
            self.grade = self._grade_profile.grades_for_positions(self.pos)

    def set_initial(self, pos: np.ndarray = None, vel: np.ndarray = None):
        """设置初始位置/速度（米, 米/秒）。"""
        if pos is not None:
            self.pos = np.asarray(pos, dtype=float)
        if vel is not None:
            self.vel = np.asarray(vel, dtype=float)
        # Newmark 上一步加速度清零（episode 间不残留）
        self._acc0 = np.zeros(self.num_vehicles)
        self._brake_pressure = np.zeros(self.num_vehicles)
        self._brake_reduction_override_kpa = None
        self._air_brake_pending = np.full(self.num_vehicles, None, dtype=object)
        self._air_brake_upgrade_pending = np.full(self.num_vehicles, None, dtype=object)
        self._air_brake_upgrade_delay = np.zeros(self.num_vehicles)
        # 【R0-D/E】episode 间不残留：衰减段号/缓解排气计时归零
        self._brake_segment = 0
        self._brake_was_active = False
        self._air_brake_exhaust_t = np.zeros(self.num_vehicles)

    def set_initial_speed(self, speed_mps: float):
        """全体车辆初始速度一致。"""
        self.vel = np.full(self.num_vehicles, speed_mps)
        # Newmark 上一步加速度清零（episode 间不残留）
        self._acc0 = np.zeros(self.num_vehicles)
        self._brake_pressure = np.zeros(self.num_vehicles)
        self._brake_reduction_override_kpa = None
        self._air_brake_pending = np.full(self.num_vehicles, None, dtype=object)
        self._air_brake_upgrade_pending = np.full(self.num_vehicles, None, dtype=object)
        self._air_brake_upgrade_delay = np.zeros(self.num_vehicles)
        # 【R0-D/E】episode 间不残留：衰减段号/缓解排气计时归零
        self._brake_segment = 0
        self._brake_was_active = False
        self._air_brake_exhaust_t = np.zeros(self.num_vehicles)

    def _coupler_interface_forces_vec(
        self, e: np.ndarray = None, dv: np.ndarray = None
    ) -> np.ndarray:
        """相邻车钩断面力（向量化核心，MT-2 迟滞模型：查表 + 速度法）。

        模型结构（容嘉欣2025 式(2) 速度法 + 图4(b) 货车 MT-2 fl/fu 曲线，
        2026-08-30「预压+线性刚度±Stribeck」解析式已废止，见 coupler.py 模块头）：

            f0(x) = [fl(x) + fu(x)]/2，half = [fl(x) − fu(x)]/2
            F_mag = contact·(f0 − tanh(s_e·dv/ε)·half) + rigid，|F_mag| ≤ F_max
            加载(s_e·dv<0)取 fl、卸载取 fu → 迟滞环耗能；dv→0 回中线 f0
            F_on_front = sgn(e)·F_mag

        实现要点（数值稳健性）：
        - 车钩间隙 gap：|e|≤gap 时无接触无力；接触渐入用 tanh 平滑（宽度
          ±4mm），避免接触瞬间力硬跳变注入数值能量。
        - 速度法方向因子用窄带 tanh(s_e·dv/ε)（ε=friction_v_eps，默认
          0.002 m/s）：摩擦幅值**不随速度大小衰减**（旧 Stribeck 幅值调制
          在准静态 0.01 m/s 下只剩 19.7%，是装载缓释曲线失真的根因），
          仅按 sign(Δv) 选支；dv→0 连续回到 f0，无硬切换。
        - 行程限位：x_el > stroke 后叠加刚性接触力（金属打满不可压缩），
          且在饱和封顶之外独立叠加（否则限位力被封顶削弱 → 位移漂移）。

        Args:
            e: 伸长量数组（可选，默认由当前 pos 算）
            dv: 相对速度数组 v_front−v_back（可选，默认由当前 vel 算）

        Returns:
            单钩断面力数组（长度 n−1，正=前车受向前力）
        """
        fl = self.coupler.free_length_m          # 布局用自由长度（齐次，保持编组尺度）
        cp = self._cp                            # 逐耦合力参数字典（长度 n-1）
        if e is None:
            e = (self.pos[1:] - self.pos[:-1]) + fl
        if dv is None:
            dv = self.vel[:-1] - self.vel[1:]
        gap = np.maximum(cp['coupler_gap_m'], 1e-9)

        # 平滑方向函数：间隙内≈0，接触后≈±1（避免 |e|≈0 处 sign 硬切换）
        s_e = np.tanh(e / gap)
        # 有符号间隙距离：>0 接触压缩/拉伸量，<0 在游隙内
        d = np.abs(e) - gap
        # 接触渐入系数（0→1，半宽 4mm）：阻抗随接触平滑建立
        contact = 0.5 * (1.0 + np.tanh(d / 0.004))
        # 有效弹性变形（游隙内为 0）
        x_el = np.maximum(d, 0.0)
        # 行程限位：缓冲器打满后金属接触，力剧增约束位移
        rigid = cp['rigid_stiffness_nm'] * np.maximum(x_el - cp['stroke_m'], 0.0)

        # 速度法方向因子：加载 ⟺ s_e·dv<0；sign(Δv) 窄带 tanh 平滑（无硬切换）
        dir_sm = np.tanh(s_e * dv / cp['friction_v_eps'])

        # 查容嘉欣图4(b) fl/fu 表（stiffness = 全局增益）→ 中线 f0、半宽 half
        gain = cp['stiffness'] / STIFFNESS_BASE_N_PER_M
        fl_x = np.interp(x_el, RONG2025_X_M, RONG2025_FL_N)
        fu_x = np.interp(x_el, RONG2025_X_M, RONG2025_FU_N)
        f0 = 0.5 * (fl_x + fu_x) * gain
        half = 0.5 * (fl_x - fu_x) * gain

        # 阻抗幅值（可饱和部分）：选支结果（接触渐入门控），
        # 封顶于缓冲器最大阻抗力（MT-2 2270 kN）
        f_imp = contact * (f0 - dir_sm * half)
        f_imp = np.clip(f_imp, 0.0, cp['max_impulse_n'])
        # 刚性限位力必须在饱和封顶之外独立叠加！
        # 若一起 clip，行程打满后限位力被封顶削弱 → 无法约束位移 →
        # 车钩相对位移漂移，全列力雪崩饱和。
        f_mag = f_imp + rigid
        return s_e * f_mag

    def set_couplers(self, couplers: list = None) -> None:
        """运行时替换逐耦合 CouplerParams 并重建力参数字典。

        【E4-H domain randomization】训练期每个 episode reset 时据此换一组新的
        逐车钩异构参数（None=回退齐次）。评估（held-out）用构造时的 fix 抽取不动。
        """
        self.couplers = couplers
        self._cp = self._build_coupler_param_arrays()

    def _build_coupler_param_arrays(self) -> dict:
        """把逐耦合 CouplerParams 编译为力参数字典（每项都是长度 n-1 的数组）。

        【2026-09-07 ADR】统一 MT-2（A 范式）：齐次默认（self.couplers 为 None）
        下所有耦合一律用 self.coupler（MT-2），含机车-货车连挂。原 R0-C 机车用
        QKX100 自动派发已彻底移除。显式 couplers 列表（E4-H 货车异构研究域）
        优先于齐次默认，逐耦合照用。
        """
        m = max(self.consist.num_vehicles - 1, 0)
        if self.couplers is not None and len(self.couplers) == m:
            ps = list(self.couplers)
        else:
            ps = [self.coupler] * m
        names = ('stiffness', 'preload_n', 'friction_n', 'friction_static_n',
                 'friction_v_er', 'friction_v_eps', 'unload_stiffness_ratio',
                 'coupler_gap_m', 'max_impulse_n', 'stroke_m', 'rigid_stiffness_nm')
        out = {name: np.array([float(getattr(p, name)) for p in ps]) for name in names}
        return out

    def _coupler_forces(self) -> np.ndarray:
        """计算每节车受到的车钩合力（正=向前）。

        向量化实现：相邻车钩力用 numpy 数组一次算完（替代 n-1 次标量循环）。
        """
        n = self.num_vehicles
        forces = np.zeros(n)
        if n < 2:
            return forces
        f_adj = self._coupler_interface_forces_vec()

        # 前车受力 +f，后车受力 -f（牛顿第三定律成对抵消）
        forces[:-1] += f_adj
        forces[1:] -= f_adj
        return forces

    def coupler_interface_forces(self) -> np.ndarray:
        """相邻车钩断面力（单钩力，正=前车受向前力），长度 n-1。

        与 _coupler_forces 共用同一力模型，但返回**单钩断面力**而非车厢净力。
        实测数据（张二田 929/1021 kN、刘博阳等）均为单钩断面力口径，
        所有对照验证必须用它，避免用车厢净力（中部车厢前后钩叠加）造成误判。
        """
        n = self.num_vehicles
        if n < 2:
            return np.zeros(0)
        return self._coupler_interface_forces_vec()

    def coupler_interface_forces_per_vehicle(self) -> np.ndarray:
        """每节车所受相邻钩断面力的**最大幅值**（长度 n，无量纲符号，恒 ≥ 0）。

        【2026-09-30 治本-口径统一】断面力口径（coupler_interface_forces，长度 n-1，
        单钩）作用于相邻两车：第 i 车同时承受前钩(i-1)与后钩(i)的断面力，其强度取
        两者幅值较大者。本函数把"单钩断面力"映射回"每车视图"，专供：
        - **安全层按车索引钳制动作**（actions[i] 对应第 i 车，需长度 n）；
        - 控制器按车取"当前列内耦合器力量级"。

        ⚠️ 评估/违规计数口径请用 coupler_interface_forces()（长度 n-1），
        **不要**用本函数做统计（本函数对每钩力重复计入相邻两车，会 2× 计数）。
        """
        n = self.num_vehicles
        if n < 2:
            return np.zeros(n)
        f = np.abs(self._coupler_interface_forces_vec())  # 长度 n-1
        padded = np.concatenate(([0.0], f, [0.0]))        # 长度 n+1
        return np.maximum(padded[:-1], padded[1:])        # 长度 n

    def _resistance_forces(self) -> np.ndarray:
        """Davis 阻力（恒与速度方向相反，含坡度项在 grade 中单独计算）。

        向量化实现：内联 Davis 公式（与 resistance_force_n 数值一致），
        提取每车参数为数组，替代逐车标量循环。
        """
        n = self.num_vehicles
        # 每车参数数组
        mass_t = np.array([v.mass_t for v in self.consist.vehicles])
        axles = np.array([v.no_of_axles for v in self.consist.vehicles])
        area_m2 = np.array([v.frontal_area_m2 for v in self.consist.vehicles])
        drag = np.array([v.drag_coef for v in self.consist.vehicles])

        speed = np.abs(self.vel)
        # Davis 单位换算（与 resistance.py 的 _short_tons/_mph/_sqft 一致）
        w = mass_t * 1.10231                    # 公吨 -> 短吨
        v_mph = speed * 2.23694                 # m/s -> mph
        area_sqft = area_m2 * 10.7639           # m² -> ft²
        axle_weight = w / np.maximum(axles, 1)

        unit_resistance = 1.5 + 18.0 / axle_weight + 0.03 * v_mph
        air_resistance = 0.0018 * area_sqft * drag * v_mph ** 2
        r_lb = unit_resistance * w + air_resistance
        forces = r_lb * 4.44822                 # lb -> N

        # 方向与速度相反；静止时无阻力
        forces = np.where(speed > 1e-6, forces * np.sign(self.vel), 0.0)
        return forces

    def _grade_forces(self) -> np.ndarray:
        """坡度阻力（重力沿轨道分量），m*g*grade。"""
        return -self.masses_kg * G * self.grade

    def _tractive_forces(self, throttle: float) -> np.ndarray:
        """机车牵引力。throttle 为全局手柄（0~1）。"""
        n = self.num_vehicles
        forces = np.zeros(n)
        for i, v in enumerate(self.consist.vehicles):
            if v.is_locomotive:
                forces[i] = tractive_force(
                    v.max_power_kw, v.transmission_efficiency, throttle,
                    abs(self.vel[i]), v.mass_t, self.friction_coef,
                )
        return forces

    def _air_braking_forces(self) -> np.ndarray:
        """空气制动力（与速度方向相反），基于传播后生效的离散档位。

        【2026-09-02 P0-3 重标定】改用牵规 β_c 法（braking.py）：
        常用制动 B_c = β_c(r)·φ_h(v)·K_h，C80 SERVICE(140kPa)≈31 kN/车、
        紧急≈42 kN/车（50 km/h）—— 与赵紫宁表3-5/实测一致（原李蔚法偏强 2~4 倍）。

        【2026-09-03 B3】enable_cyclic_degrade=True 时，制动力乘段间衰减因子
        cyclic_braking_degrade(self._brake_segment)（赵紫宁表5-5 C_β，段2→0.705、
        段3→0.676，相对首段归一）。默认关闭，不影响既有数值。

        【2026-09-03 L1】tail_pressure_kpa 给定列尾压强时，制动力乘沿列车平衡压
        梯度（前部满压 → 后部按刘博阳 L6 比例衰减）。默认 None=无梯度。
        """
        n = self.num_vehicles
        forces = np.zeros(n)
        override = self._brake_reduction_override_kpa
        # B3 段间衰减乘子（默认 1.0 = 不衰减，向后兼容）
        degrade = (cyclic_braking_degrade(self._brake_segment)
                   if self.enable_cyclic_degrade else 1.0)
        # L1 平衡压梯度（默认 None → 全 1.0，向后兼容）
        if self.tail_pressure_kpa is not None and self._cyl_gradient is None:
            ratio = tail_pressure_to_cyl_ratio(self.tail_pressure_kpa)
            self._cyl_gradient = cylinder_pressure_gradient(n, ratio)
        cyl_grad = (self._cyl_gradient if self._cyl_gradient is not None
                    else np.ones(n))
        for i, v in enumerate(self.consist.vehicles):
            if not self._air_brake_active[i]:
                continue
            f = air_brake_force_real(
                abs(self.vel[i]), self._air_brake_notch[i], v.is_locomotive,
                reduction_kpa=override,
            )
            # E7：缓解制动力渐变衰减（真实缓解逐步排风，非瞬间释放），避免掉速
            f *= self._air_brake_release_frac[i]
            # 【2026-08-30】制动缸升压渐入（~10s 上升至峰值，文献标准）
            f *= self._brake_pressure[i]
            # 【2026-09-03 B3】循环制动段间衰减
            f *= degrade
            # 【2026-09-03 L1】列尾压强平衡压梯度（后部制动力弱化）
            f *= cyl_grad[i]
            forces[i] = -f * np.sign(self.vel[i]) if abs(self.vel[i]) > 1e-6 else -f
        return forces

    def _electric_braking_forces(self, ed_throttle: np.ndarray) -> np.ndarray:
        """机车电制动力（连续，与速度方向相反）。ed_throttle 长度 = 车辆数。"""
        n = self.num_vehicles
        forces = np.zeros(n)
        for i, v in enumerate(self.consist.vehicles):
            if v.is_locomotive and ed_throttle[i] > 1e-6:
                f = electric_brake_force_n(
                    v.mass_t, abs(self.vel[i]), ed_throttle[i],
                    v.max_power_kw, v.transmission_efficiency,
                    self.friction_coef,
                )
                forces[i] = -f * np.sign(self.vel[i]) if abs(self.vel[i]) > 1e-6 else -f
        return forces

    def _braking_forces(self, brake_notch: float) -> np.ndarray:
        """制动力（与速度方向相反）。兼容旧接口，连续映射。"""
        n = self.num_vehicles
        forces = np.zeros(n)
        for i, v in enumerate(self.consist.vehicles):
            f = braking_force(
                v.mass_t, abs(self.vel[i]), brake_notch, v.braked_weight_ratio,
            )
            forces[i] = -f * np.sign(self.vel[i]) if abs(self.vel[i]) > 1e-6 else -f
        return forces

    def net_forces(self, throttle: float, brake_notch: float) -> np.ndarray:
        """计算每节车的净力（牛顿）。"""
        return (
            self._tractive_forces(throttle)
            + self._braking_forces(brake_notch)
            - self._resistance_forces()
            + self._grade_forces()
            + self._coupler_forces()
        )

    def accelerations(self, throttle: float, brake_notch: float) -> np.ndarray:
        """每节车加速度（米/秒^2）。"""
        return self.net_forces(throttle, brake_notch) / self.masses_kg

    def step(self, throttle: float, brake_notch: float):
        """推进一个时间步（半隐式 Euler）。统一 throttle/brake。"""
        self.step_vehicles(
            np.full(self.num_vehicles, throttle),
            np.full(self.num_vehicles, brake_notch),
        )

    def step_vehicles(self, throttle: np.ndarray, brake_notch: np.ndarray):
        """按每节车独立控制推进一个时间步。

        【2026-10-12 数值稳定修复】容嘉欣2025 查表迟滞模型在小行程段
        （0–10mm）局部斜率 ~43 kN/mm，旧半隐式 Euler（dt=0.1s）在车钩链
        上振荡指数放大 → 3 步内撞刚性限位爆炸（test_grade_updates_with_position
        实证）。改为与 step_vehicles_ed_ab 相同的 ≤0.01s 子步 + Newmark-β
        隐式积分路径：控制力（牵引/连续制动当量）在迭代外固定，状态力
        （阻力/坡度/车钩）由 Newmark 内部计算，保持与主路径物理同源。

        Args:
            throttle: 每节车 throttle（0~1）
            brake_notch: 每节车制动档位（0~1，连续映射，兼容旧接口）
        """
        n_sub = max(1, int(np.ceil(self.dt / 0.01)))
        h = self.dt / n_sub
        for _ in range(n_sub):
            # 控制力 = 牵引 + 连续制动当量（不依赖位置/速度，迭代外固定）
            control_forces = (
                self._tractive_forces_per_vehicle(throttle)
                + self._braking_forces_per_vehicle(brake_notch)
            )
            self._step_newmark(control_forces, h)
        self._update_grade_from_profile()

    def step_vehicles_ed_ab(
        self,
        throttle: np.ndarray,
        ed_throttle: np.ndarray,
        ab_command: AirBrakeNotch,
        brake_origin: int = 0,
        ab_sources: list = None,
        eot: bool = False,
        reduction_kpa: float = None,
    ):
        """按 电制动（连续）+ 空气制动（离散+波速传播）推进一个时间步。

        【2026-08-30 子步进】缓冲器冲击事件 ~50-100ms，外部步长 dt>0.01s
        时无法解析（1 m/s 相对速度每步位移 > 全行程 83mm，刚性限位下
        Newmark/Picard 发散 NaN）。内部自动拆分为 ≤0.01s 的物理子步，
        对外控制频率/观测频率不变（RL 透明）。代价：物理计算量 ×(dt/0.01)。

        Args:
            throttle: 每节车牵引 throttle（0~1，仅机车有效）
            ed_throttle: 每节车电制动指令（0~1，仅机车有效，连续）
            ab_command: 空气制动指令（离散档位，队首发出后向后传播）
            brake_origin: 空气制动指令源车辆索引（默认 0=机车/队首）
            ab_sources: 可选多源空气制动列表 [(index, AirBrakeNotch), ...]。
                用于验证"尾部动力/分布式制动"降低纵向冲动（樊运新规律）。
                提供时优先使用多源，忽略 ab_command/brake_origin 的单源逻辑。
            reduction_kpa: 【2026-09-02 P0-3】可选连续减压量（kPa），
                覆盖档位默认减压量，对所有生效车辆施加（验证专用，向后兼容）。
        """
        n_sub = max(1, int(np.ceil(self.dt / 0.01)))
        h = self.dt / n_sub
        for k in range(n_sub):
            # 指令施加只在第一个子步执行（每控制步一次）
            self._advance_control_once(
                throttle, ed_throttle, ab_command, brake_origin, ab_sources,
                eot, h, apply_command=(k == 0),
                reduction_kpa=reduction_kpa,
            )
        # 能耗追踪（控制步级）：牵引功率 = 牵引力 × 速度（仅牵引为正时累计）
        tractive = self._tractive_forces_per_vehicle(throttle)
        power_w = np.sum(np.maximum(tractive, 0.0) * self.vel)
        self._energy_delta_kwh = power_w * self.dt / 3.6e6
        self.energy_kwh += self._energy_delta_kwh

    def _advance_control_once(
        self,
        throttle: np.ndarray,
        ed_throttle: np.ndarray,
        ab_command: AirBrakeNotch,
        brake_origin: int,
        ab_sources: list,
        eot: bool,
        h: float,
        apply_command: bool,
        reduction_kpa: float = None,
    ):
        """推进一个物理子步（步长 h，≤0.01s）。"""
        if apply_command:
            # 【2026-09-02 P0-3】连续减压量覆盖：每控制步更新（验证专用，None=档位默认）
            self._brake_reduction_override_kpa = reduction_kpa
            # 【2026-09-03 B3】段切换检测：上一步无制动 → 这一步有制动指令 → 段号+1。
            # 段号仅在有新制动段发出时递增（持续制动中不递增，缓解后再制动才 +1）。
            cmd_now = (ab_sources[0][1] if ab_sources
                       else (None if ab_command is None else ab_command))
            is_braking_cmd = (cmd_now is not None
                              and cmd_now != AirBrakeNotch.RELEASE)
            if self.enable_cyclic_degrade and is_braking_cmd and not self._brake_was_active:
                self._brake_segment += 1
            self._brake_was_active = is_braking_cmd
            if ab_sources:
                # 多源制动：多个位置同时发出空气制动指令（分布式动力）
                # 尾部/中部动力源需要双向传播以提升制动同步
                cmd = ab_sources[0][1]
                if cmd != AirBrakeNotch.RELEASE:
                    for idx, notch in ab_sources:
                        self._apply_air_brake_command(
                            notch, idx, bidirectional=True)
                else:
                    if np.any(self._air_brake_active):
                        self._reset_air_brake_command(0, eot=eot)
            elif ab_command is None:
                # 【2026-09-02 bug修复】ab_command=None 表示"不使用空气制动"，
                # 不得触发任何制动/缓解逻辑。此前 None != RELEASE 为真 → 头车被
                # 错误 _apply_air_brake_command(None) → _air_brake_active[0]=True，
                # 导致平坡静止列车蠕动、惰行能量不守恒（第一锚物理硬约束测试发现）。
                pass
            elif ab_command != AirBrakeNotch.RELEASE:
                # 单源制动（向后兼容）
                self._apply_air_brake_command(ab_command, brake_origin)
            else:
                # 缓解：仅在确实处于制动状态时释放
                # 【bug修复】缓解波传播中（车头 _air_brake_releasing[0] 已触发）不重复
                # _reset_air_brake_command，否则每次 step 都重置缓解波 delay → 缓解波
                # 永远传播不完 → 尾部持续制动 → 掉速 + active 反而增加（8/18 诊断：
                # 缓解后 active 4→14、delay 恒定6.0）。首次缓解才触发缓解波。
                if (np.any(self._air_brake_active)
                        and not self._air_brake_releasing[brake_origin]):
                    self._reset_air_brake_command(brake_origin, eot=eot)

        # 推进空气制动波速传播
        self._advance_air_brake_propagation(h)

        # 【2026-08-30 缺失物理补全】制动缸升压：波到达后压力渐入
        # （真实制动缸充风升压，阶跃施加会产生远超真实的纵向冲击）。
        # 升压时间按档位区分（常用 ~18-20s 发散式，紧急 ~10s，李蔚2023）。
        rising = self._air_brake_active & (~self._air_brake_releasing)
        rise_times = np.array([
            self.brake_rise_time_by_notch.get(nh, self.brake_rise_time_s)
            for nh in self._air_brake_notch
        ])
        self._brake_pressure = np.where(
            rising,
            np.minimum(1.0, self._brake_pressure + h / rise_times),
            self._brake_pressure,
        )
        # 缓解完成（不再激活）后压力归零，再次制动时重新升压
        self._brake_pressure = np.where(self._air_brake_active,
                                        self._brake_pressure, 0.0)

        # 【2026-08-30 标准 LTD 重构】Newmark-β 隐式积分（替代半隐式 Euler）
        # 控制力 = 牵引 + 电制动 + 空气制动（不依赖位置/速度，迭代外固定）
        control_forces = (
            self._tractive_forces_per_vehicle(throttle)
            + self._electric_braking_forces(ed_throttle)
            + self._air_braking_forces()
        )
        self._step_newmark(control_forces, h)
        self._update_grade_from_profile()

    # ------------------------------------------------------------------
    # 【2026-08-30 标准 LTD 重构】Newmark-β 积分器（替代半隐式 Euler）
    #
    # 半隐式 Euler 对刚性弹簧-阻尼多体系统（重载列车 101 质点 + 车钩）
    # 在制动瞬态数值不稳定（实测车钩位移漂移到 1m+、力爆炸 17 万 kN）。
    # 文献标准（李蔚 2023 / He2025 / 常崇义）采用 Newmark-β 隐式积分，
    # 无条件稳定。本实现用 Picard 定点迭代求解隐式位移。
    # 参数 β=1/4, γ=1/2（常加速度法，无条件稳定）。
    # ------------------------------------------------------------------

    def _state_forces(self, x: np.ndarray, v: np.ndarray) -> np.ndarray:
        """状态相关力（Davis 阻力 + 坡度 + 车钩力），依赖位置/速度。

        Newmark 迭代中，用给定 (x, v) 临时计算状态力（控制力不依赖状态，
        由调用方固定传入）。
        """
        x_save, v_save = self.pos, self.vel
        self.pos, self.vel = x, v
        try:
            f = -self._resistance_forces() + self._grade_forces() + self._coupler_forces()
        finally:
            self.pos, self.vel = x_save, v_save
        return f

    def _step_newmark(
        self,
        control_forces: np.ndarray,
        dt: float,
        max_iter: int = None,
        tol: float = None,
    ) -> None:
        """Newmark-β（β=1/4, γ=1/2）推进一个时间步，Picard 迭代求解。

        Args:
            control_forces: 每车控制力（牵引/制动/电制动），本步固定
            dt: 时间步长（秒）
            max_iter: 定点迭代上限（None=用 self.newmark_max_iter）
            tol: 位移收敛容差（米，None=用 self.newmark_tol）
        """
        max_iter = self.newmark_max_iter if max_iter is None else max_iter
        tol = self.newmark_tol if tol is None else tol
        m = self.masses_kg
        beta, gamma = 0.25, 0.5
        x_n, v_n, a_n = self.pos.copy(), self.vel.copy(), self._acc0

        # 预估
        x_p = x_n + dt * v_n + dt * dt * (0.5 - beta) * a_n
        v_p = v_n + dt * (1.0 - gamma) * a_n

        # 欠松弛（α=0.5）稳定 Picard 迭代：刚性限位力剧增时防止发散
        # 【2026-09-02 bug修复】欠松弛只用于迭代过程，收敛后必须取**未松弛**
        # 候选解 (x_cand, v_cand)。此前松弛中间量 (x_new, v_new) 被直接当作
        # 最终状态，稳态下等效 v_{n+1} = v_n + α·(1-γ)·… → 全部动力学响应
        # 被系统性缩放至 75%（实测单车减速 0.0258 vs 公式 0.0344 m/s²，
        # 恰为 0.75 倍；惰行末速差 8.8%）。第一锚/第二锚验证测试发现。
        alpha = 0.5
        x_final, v_final = None, None
        for _ in range(max_iter):
            a_p = (control_forces + self._state_forces(x_p, v_p)) / m
            v_cand = v_n + dt * ((1.0 - gamma) * a_n + gamma * a_p)
            x_cand = x_n + dt * v_n + dt * dt * ((0.5 - beta) * a_n + beta * a_p)
            v_new = v_p + alpha * (v_cand - v_p)
            x_new = x_p + alpha * (x_cand - x_p)
            if np.max(np.abs(x_new - x_p)) < tol:
                x_final, v_final = x_cand, v_cand  # 收敛解 = 未松弛候选
                break
            x_p, v_p = x_new, v_new
        if x_final is None:  # 未收敛（刚性冲击等）：回退松弛值防爆炸
            x_final, v_final = x_new, v_new

        # 列车不倒车（真实列车无倒车控制）
        v_final = np.maximum(v_final, 0.0)
        self.pos, self.vel, self._acc0 = x_final, v_final, a_p
        self.time += dt

    def reset_energy(self):
        """重置能耗累计（用于评估/回合开始）。"""
        self.energy_kwh = 0.0
        self._energy_delta_kwh = 0.0

    def air_brake_state(self) -> np.ndarray:
        """返回每节车当前生效的空气制动档位（AirBrakeNotch 数组）。"""
        return self._air_brake_notch.copy()

    def _tractive_forces_per_vehicle(self, throttle: np.ndarray) -> np.ndarray:
        """每节车独立牵引力。throttle 数组长度 = 车辆数。"""
        n = self.num_vehicles
        forces = np.zeros(n)
        for i, v in enumerate(self.consist.vehicles):
            if v.is_locomotive:
                forces[i] = tractive_force(
                    v.max_power_kw, v.transmission_efficiency, throttle[i],
                    abs(self.vel[i]), v.mass_t, self.friction_coef,
                )
        return forces

    def _braking_forces_per_vehicle(self, brake_notch: np.ndarray) -> np.ndarray:
        """每节车独立制动力（连续映射，兼容旧接口）。"""
        n = self.num_vehicles
        forces = np.zeros(n)
        for i, v in enumerate(self.consist.vehicles):
            f = braking_force(
                v.mass_t, abs(self.vel[i]), brake_notch[i], v.braked_weight_ratio,
            )
            forces[i] = -f * np.sign(self.vel[i]) if abs(self.vel[i]) > 1e-6 else -f
        return forces

    def _vehicle_cum_lengths(self) -> np.ndarray:
        """每节车参考点到队首的累计长度（米），用于制动波速传播延迟。"""
        n = self.num_vehicles
        lengths = np.array([v.length_m for v in self.consist.vehicles])
        return np.concatenate([[0.0], np.cumsum(lengths[:-1])])

    def _advance_air_brake_propagation(self, dt: float):
        """推进空气制动波速传播：连续波前并行倒数生效（支持双向传播）。

        空气制动指令从源车辆以有限波速（200~250 m/s）沿车列传播，
        传播延迟 = 到该车的累计距离 / 波速，各节独立倒计时（连续波前）。
        源在前（队首）向后传播；尾部/中部动力源还可向前传播（双向）。
        这决定制动同步性 → 纵向冲动。

        【bug修复 2026-08-30】制动波传播 O(i²) 二次延迟：
        原实现"串行等待前节激活"（delay_remaining 每步只在邻节激活后递减 dt）
        与"delay = 累计距离/波速"（_apply_air_brake_command 初始化）组合，
        第 i 节实际激活时刻 = Σ(累计延迟) ≈ 0.03·i² 秒 → 第 43 节需 55s
        （物理正确值 6.1s）。尾部长时间无制动 → 下坡被重力加速前涌 →
        缓冲器行程压穿 → 车钩力虚高约 10 倍（B 基准 6549 vs 文献 634 kN）。
        修复：与缓解波（2026-08-22 修复）相同的并行倒数语义——各节 delay
        = 距源累计距离/波速，独立倒计时，波前到达即按 pending 档位激活。
        """
        n = self.num_vehicles
        # 制动波：pending 节并行倒计时，delay→0 激活
        pending_mask = np.array(
            [pn is not None for pn in self._air_brake_pending]
        )
        due = pending_mask & (self._air_brake_delay_remaining > 0.0)
        self._air_brake_delay_remaining[due] -= dt
        activated = pending_mask & (self._air_brake_delay_remaining <= 0.0)
        for i in np.where(activated)[0]:
            self._air_brake_active[i] = True
            if self._air_notch_rank(self._air_brake_pending[i]) > self._air_notch_rank(self._air_brake_notch[i]):
                self._air_brake_notch[i] = self._air_brake_pending[i]
            self._air_brake_pending[i] = None

        upgrade_mask = np.array([n is not None for n in self._air_brake_upgrade_pending])
        self._air_brake_upgrade_delay[upgrade_mask] -= dt
        for i in np.where(upgrade_mask & (self._air_brake_upgrade_delay <= 0))[0]:
            notch = self._air_brake_upgrade_pending[i]
            if (self._air_brake_releasing[i] or not self._air_brake_active[i]
                    or self._air_notch_rank(notch) > self._air_notch_rank(self._air_brake_notch[i])):
                if self._air_brake_releasing[i]:
                    self._brake_pressure[i] *= self._air_brake_release_frac[i]
                self._air_brake_notch[i] = notch
                self._air_brake_active[i] = True
                self._air_brake_releasing[i] = False
                self._air_brake_exhaust_t[i] = 0.0
                self._air_brake_release_frac[i] = 1.0
            self._air_brake_upgrade_pending[i] = None

        # 【缓解波传播修复 2026-08-22】连续波前并行释放（替代原"逐节串行等待"）。
        # 原实现依赖 releasing[i-1]（前一节已释放才倒计时本节的独立满 delay），导致
        # 第 k 节需 ~60k 步才释放（串行累积，缓解传播严重延迟 → 尾部残留满制动 → 拖停）。
        # 正确物理：缓解波以 ~200m/s 连续传播，各节 delay = distance/波速，并行独立倒计时，
        # 波前到达即释放（1200m 车长 6 秒传完），保留"缓解后车钩力最大"不同步物理现象。
        # 每节 i 在缓解开始时已被 `_reset_air_brake_command` 标记 releasing[i]=True 并设置
        # delay_remaining[i]=distance/波速。
        #
        # 【2026-09-06 R0-E 重构】缓解制动力衰减改为两段式物理：
        #   阶段1（delay_remaining>0）：缓解波（管压波）尚未到达 → 保持满制动；
        #   阶段2（波到达后）：制动缸排风，制动力按 exp(-t/τ) 衰减（τ=排气时间常数），
        #   frac≤0.02（≈4τ）后彻底缓解。
        # 替代原"frac 随波传播进度线性渐变"——线性渐变把"管压波传播"与"制动缸
        # 排气"混为一谈，且头车（delay=0）制动力瞬时归零，缓解冲击失真。
        tau = max(self.release_exhaust_tau_s, 1e-6)
        rel_mask = self._air_brake_releasing & self._air_brake_active
        if np.any(rel_mask):
            holding = rel_mask & (self._air_brake_delay_remaining > 0.0)
            self._air_brake_delay_remaining[holding] -= dt
            self._air_brake_release_frac[holding] = 1.0
            arrived = rel_mask & (self._air_brake_delay_remaining <= 0.0)
            self._air_brake_exhaust_t[arrived] += dt
            frac = np.exp(-self._air_brake_exhaust_t / tau)
            self._air_brake_release_frac = np.where(arrived, frac,
                                                    self._air_brake_release_frac)
            done = arrived & (frac <= 0.02)
            if np.any(done):
                self._air_brake_active[done] = False
                for i in np.where(done)[0]:
                    self._air_brake_notch[i] = AirBrakeNotch.RELEASE
                self._air_brake_release_frac[done] = 0.0
                self._air_brake_exhaust_t[done] = 0.0

        # 【EOT 缓解波】EOT 时 delay 已在 _reset_air_brake_command 设为 min(到头,到尾)/波速，
        # 正向传播循环按此 delay 递减即可实现"两端向中间缓解"，无需单独反向循环。

    @staticmethod
    def _air_notch_rank(notch):
        return {None: -1, AirBrakeNotch.RELEASE: 0, AirBrakeNotch.MIN: 1,
                AirBrakeNotch.SERVICE: 2, AirBrakeNotch.EMERGENCY: 3}[notch]

    def _apply_air_brake_command(
        self,
        cmd_notch: AirBrakeNotch,
        vehicle_idx: int,
        bidirectional: bool = False,
    ):
        """对 vehicle_idx 施加空气制动指令，并初始化波速传播。

        Args:
            cmd_notch: 空气制动离散档位
            vehicle_idx: 指令源车辆索引（0=队首，n-1=队尾）
            bidirectional: 是否双向传播（分布式动力，多源制动时用 True）。
                True：从源向前车与后车同时传播；False：仅向后传播（单源队首，向后兼容）。
        """
        n = self.num_vehicles
        is_emergency = cmd_notch == AirBrakeNotch.EMERGENCY
        wave_speed = (
            AIR_BRAKE_PROPAGATION_SPEED_EMERGENCY
            if is_emergency else AIR_BRAKE_PROPAGATION_SPEED_SERVICE
        )
        cum_len = self._vehicle_cum_lengths()

        if (not self._air_brake_active[vehicle_idx]
                or self._air_brake_releasing[vehicle_idx]
                or self._air_notch_rank(cmd_notch) > self._air_notch_rank(self._air_brake_notch[vehicle_idx])):
            self._air_brake_active[vehicle_idx] = True
            self._air_brake_notch[vehicle_idx] = cmd_notch
            # 若该节正在缓解波传播中，清除缓解状态（重新制动）
            if self._air_brake_releasing[vehicle_idx]:
                # Resume filling from effective cylinder pressure, not full pressure.
                self._brake_pressure[vehicle_idx] *= self._air_brake_release_frac[vehicle_idx]
                self._air_brake_releasing[vehicle_idx] = False
                self._air_brake_exhaust_t[vehicle_idx] = 0.0
            # Effective pressure has been preserved above; clear the release multiplier.
            self._air_brake_release_frac[vehicle_idx] = 1.0

            def _enqueue(j: int, distance: float):
                """将第 j 节挂入制动波（并行倒数，取更早到达的波）。"""
                delay = max(distance / wave_speed, 0.0)
                active = self._air_brake_active[j] and not self._air_brake_releasing[j]
                pending = self._air_brake_pending[j]
                if active or pending is not None:
                    existing = self._air_brake_notch[j] if active else pending
                    if self._air_notch_rank(cmd_notch) > self._air_notch_rank(existing):
                        # Preserve the earlier weaker wave; upgrade on its own
                        # finite-delay wave. Repeated requests never restart it.
                        queued = self._air_brake_upgrade_pending[j]
                        if (queued is None or self._air_notch_rank(cmd_notch) > self._air_notch_rank(queued)
                                or (cmd_notch == queued and delay < self._air_brake_upgrade_delay[j])):
                            self._air_brake_upgrade_pending[j] = cmd_notch
                            self._air_brake_upgrade_delay[j] = delay
                        return
                    if active or self._air_notch_rank(cmd_notch) < self._air_notch_rank(existing):
                        return
                if self._air_brake_releasing[j]:
                    # Keep exhausting until the new application wave arrives.
                    # Its timer must not overwrite the release-wave timer.
                    queued = self._air_brake_upgrade_pending[j]
                    if (queued is None or self._air_notch_rank(cmd_notch) > self._air_notch_rank(queued)
                            or (cmd_notch == queued and delay < self._air_brake_upgrade_delay[j])):
                        self._air_brake_upgrade_pending[j] = cmd_notch
                        self._air_brake_upgrade_delay[j] = delay
                    return
                delay = max(distance / wave_speed, 0.0)
                # 多源时保留更早到达的波（delay 更小者）
                if (self._air_brake_pending[j] is None
                        or delay < self._air_brake_delay_remaining[j]):
                    self._air_brake_pending[j] = cmd_notch
                    self._air_brake_delay_remaining[j] = delay

            # 向后传播（source -> 后方）：delay = 距源累计距离/波速，并行倒数
            for j in range(vehicle_idx + 1, n):
                _enqueue(j, cum_len[j] - cum_len[vehicle_idx])
            # 向前传播（source -> 前方），用于尾部/中部动力（分布式制动）
            if bidirectional:
                for j in range(vehicle_idx - 1, -1, -1):
                    _enqueue(j, cum_len[vehicle_idx] - cum_len[j])

    def _reset_air_brake_command(self, vehicle_idx: int = 0, eot: bool = False):
        """缓解空气制动。

        真实缓解：缓解波按波速（~200m/s）从车头向后传播，车头先缓、车尾后缓，
        不同步导致"缓解后车钩力最大"（张二田等一致）。仅释放源头车辆，
        由 `_advance_air_brake_propagation` 逐节延迟释放。

        EOT（eot=True，论文解决方案）：缓解时**尾部同时触发缓解波**（双向缓解）。
        真实重载列车配 EOT（可控尾车），缓解时尾部同步排风加速缓解波传播，
        提升缓解同步性。论文依据：Zhang2025 大秦线 20kT EOT 使最大拉钩力
        780→489kN（-37%）；樊运新 3万吨 长大下坡循环制动最大拉钩力 952.6kN
        （尾部分布式动力提升同步）。EOT 让缓解波下"缓解后车钩力最大"的峰值
        显著降低，车钩力可守住 1000kN。
        """
        n = self.num_vehicles
        # 【配套修复 2026-08-30】缓解时撤销所有未达的制动波 pending：
        # 否则缓解波传播中，尚在倒计时的制动波会继续激活车辆 → 缓解后
        # 残留车辆被延迟激活满制动 → 列车永远刹住不缓解。
        self._air_brake_pending[:] = None
        self._air_brake_upgrade_pending[:] = None
        self._air_brake_upgrade_delay[:] = 0.0
        cum_len = self._vehicle_cum_lengths()
        wave_speed = AIR_BRAKE_PROPAGATION_SPEED_SERVICE
        # 【R0-E 2026-09-06】源头车辆不再瞬时释放（旧实现 active=False 立即归零）：
        # 保持 active/notch 不变，进入"缓解排气"状态（delay=0 → 立即开始按
        # exp(-t/τ) 排风），由 _advance_air_brake_propagation 完成衰减与释放。
        if (vehicle_idx < n and self._air_brake_active[vehicle_idx]
                and not self._air_brake_releasing[vehicle_idx]):
            self._air_brake_releasing[vehicle_idx] = True
            self._air_brake_delay_remaining[vehicle_idx] = 0.0
            self._air_brake_delay_total[vehicle_idx] = 0.0
            self._air_brake_exhaust_t[vehicle_idx] = 0.0
            self._air_brake_release_frac[vehicle_idx] = 1.0
            # Only newly releasing vehicles need a wave. Existing exhaust must
            # continue without pressure restoration or a restarted timer.
            for j in range(vehicle_idx + 1, n):
                if self._air_brake_active[j] and not self._air_brake_releasing[j]:
                    distance = cum_len[j] - cum_len[vehicle_idx]
                    delay = max(distance / wave_speed, 0.0)
                    # EOT：尾部（倒数第1节）也作为缓解源，缓解波双向传播 →
                    # 中间车辆延迟 = min(到头距离, 到尾部距离)/波速，缓解同步性显著提升
                    if eot:
                        distance_to_tail = cum_len[n - 1] - cum_len[j]
                        delay = min(delay, max(distance_to_tail / wave_speed, 0.0))
                    self._air_brake_delay_remaining[j] = delay
                    # 记录缓解波延迟总量（传播期 = 满制动保持期，R0-E）
                    self._air_brake_delay_total[j] = delay
                    # 【缓解波修复 2026-08-22】标记该节"缓解波传播中"（releasing=True）。
                    # 并行按 distance/波速 独立倒计时（连续波前，6 秒传完）。
                    self._air_brake_releasing[j] = True
                    self._air_brake_release_frac[j] = 1.0
                    self._air_brake_exhaust_t[j] = 0.0
            if eot and self._air_brake_active[n - 1]:
                # EOT：尾部也作为缓解波源（双向，立即开始排气）
                self._air_brake_releasing[n - 1] = True
                self._air_brake_delay_remaining[n - 1] = 0.0
                self._air_brake_delay_total[n - 1] = 0.0
                self._air_brake_exhaust_t[n - 1] = 0.0
                self._air_brake_release_frac[n - 1] = 1.0

    def max_throttle_at_speed(self, speed_mps: float) -> float:
        """该速度下允许的最大 throttle（由机车档位曲线决定）。"""
        vals = []
        for v in self.consist.vehicles:
            if v.is_locomotive:
                vals.append(throttle_coefficient(speed_mps, v.max_speed_mps, v.n_notches))
        return max(vals) if vals else 1.0
