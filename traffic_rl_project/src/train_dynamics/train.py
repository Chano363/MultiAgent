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
    air_brake_force_n, electric_brake_force_n, notch_from_throttle,
)
from .coupler import coupler_force
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
    ):
        self.consist = consist
        self.coupler = coupler or CouplerParams()
        self.dt = dt
        self.friction_coef = friction_coef

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
        self._air_brake_release_frac = np.ones(n)

        self._spacing()  # 按车钩自由长度初始化位置

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

    def set_initial_speed(self, speed_mps: float):
        """全体车辆初始速度一致。"""
        self.vel = np.full(self.num_vehicles, speed_mps)

    def _coupler_forces(self) -> np.ndarray:
        """计算每节车受到的车钩合力（正=向前）。

        向量化实现：相邻车钩力用 numpy 数组一次算完（替代 n-1 次标量循环）。
        """
        n = self.num_vehicles
        forces = np.zeros(n)
        if n < 2:
            return forces
        p = self.coupler

        # 相邻车钩伸长量 e = (x_back - x_front) + free_length
        e = (self.pos[1:] - self.pos[:-1]) + p.free_length_m
        # 车钩间隙死区
        if p.coupler_gap_m > 0.0:
            e_eff = np.where(
                e > p.coupler_gap_m, e - p.coupler_gap_m,
                np.where(e < -p.coupler_gap_m, e + p.coupler_gap_m, 0.0),
            )
        else:
            e_eff = e
        # 相邻车钩对前车的力：+stiffness*e_eff - damping*(v_front - v_back)
        dv = self.vel[:-1] - self.vel[1:]
        f_adj = p.stiffness * e_eff - p.damping * dv

        # 前车受力 +f，后车受力 -f（牛顿第三定律成对抵消）
        forces[:-1] += f_adj
        forces[1:] -= f_adj
        return forces

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
        """空气制动力（与速度方向相反），基于传播后生效的离散档位。"""
        n = self.num_vehicles
        forces = np.zeros(n)
        for i, v in enumerate(self.consist.vehicles):
            if not self._air_brake_active[i]:
                continue
            f = air_brake_force_n(
                v.mass_t, abs(self.vel[i]), self._air_brake_notch[i],
                v.braked_weight_ratio,
            )
            # E7：缓解制动力渐变衰减（真实缓解逐步排风，非瞬间释放），避免掉速
            f *= self._air_brake_release_frac[i]
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
        """按每节车独立控制推进一个时间步（半隐式 Euler）。

        Args:
            throttle: 每节车 throttle（0~1）
            brake_notch: 每节车制动档位（0~1，连续映射，兼容旧接口）
        """
        forces = (
            self._tractive_forces_per_vehicle(throttle)
            + self._braking_forces_per_vehicle(brake_notch)
            - self._resistance_forces()
            + self._grade_forces()
            + self._coupler_forces()
        )
        acc = forces / self.masses_kg
        self.vel = self.vel + acc * self.dt
        self.vel = np.maximum(self.vel, 0.0)
        self.pos = self.pos + self.vel * self.dt
        self.time += self.dt
        self._update_grade_from_profile()

    def step_vehicles_ed_ab(
        self,
        throttle: np.ndarray,
        ed_throttle: np.ndarray,
        ab_command: AirBrakeNotch,
        brake_origin: int = 0,
        ab_sources: list = None,
        release_sync: bool = False,
        eot: bool = False,
    ):
        """按 电制动（连续）+ 空气制动（离散+波速传播）推进一个时间步。

        Args:
            throttle: 每节车牵引 throttle（0~1，仅机车有效）
            ed_throttle: 每节车电制动指令（0~1，仅机车有效，连续）
            ab_command: 空气制动指令（离散档位，队首发出后向后传播）
            brake_origin: 空气制动指令源车辆索引（默认 0=机车/队首）
            ab_sources: 可选多源空气制动列表 [(index, AirBrakeNotch), ...]。
                用于验证"尾部动力/分布式制动"降低纵向冲动（樊运新规律）。
                提供时优先使用多源，忽略 ab_command/brake_origin 的单源逻辑。
        """
        if ab_sources:
            # 多源制动：多个位置同时发出空气制动指令（分布式动力）
            # 尾部/中部动力源需要双向传播以提升制动同步
            cmd = ab_sources[0][1]
            if cmd != AirBrakeNotch.RELEASE:
                for idx, notch in ab_sources:
                    if not self._air_brake_active[idx]:
                        self._apply_air_brake_command(notch, idx, bidirectional=True)
            else:
                if np.any(self._air_brake_active):
                    self._reset_air_brake_command(0, sync=release_sync, eot=eot)
        elif ab_command != AirBrakeNotch.RELEASE:
            # 单源制动（向后兼容）
            if not self._air_brake_active[brake_origin]:
                self._apply_air_brake_command(ab_command, brake_origin)
        else:
            # 缓解：仅在确实处于制动状态时释放
            # 【bug修复】缓解波传播中（车头 _air_brake_releasing[0] 已触发）不重复
            # _reset_air_brake_command，否则每次 step 都重置缓解波 delay → 缓解波
            # 永远传播不完 → 尾部持续制动 → 掉速 + active 反而增加（8/18 诊断：
            # 缓解后 active 4→14、delay 恒定6.0）。首次缓解才触发缓解波。
            if np.any(self._air_brake_active) and not self._air_brake_releasing[brake_origin]:
                self._reset_air_brake_command(brake_origin, sync=release_sync, eot=eot)

        # 推进空气制动波速传播
        self._advance_air_brake_propagation(self.dt)

        forces = (
            self._tractive_forces_per_vehicle(throttle)
            + self._electric_braking_forces(ed_throttle)
            + self._air_braking_forces()
            - self._resistance_forces()
            + self._grade_forces()
            + self._coupler_forces()
        )
        acc = forces / self.masses_kg
        self.vel = self.vel + acc * self.dt
        self.vel = np.maximum(self.vel, 0.0)
        self.pos = self.pos + self.vel * self.dt
        self.time += self.dt
        self._update_grade_from_profile()

        # 能耗追踪：牵引功率 = 牵引力 × 速度（仅对牵引为正的工况累计）
        # 牵引力 > 0 表示机车做功；能耗 kWh = Σ(F_tractive * v * dt) / (3600*1000)
        tractive = self._tractive_forces_per_vehicle(throttle)
        power_w = np.sum(np.maximum(tractive, 0.0) * self.vel)
        self._energy_delta_kwh = power_w * self.dt / 3.6e6
        self.energy_kwh += self._energy_delta_kwh

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
        """推进空气制动波速传播：按车列逐节延迟生效（支持双向传播）。

        空气制动指令从源车辆以有限波速（200~250 m/s）沿车列传播，
        传播延迟 = 到该车的累计距离 / 波速。源在前（队首）向后传播；
        尾部/中部动力源还可向前传播（双向）。这决定制动同步性 → 纵向冲动。
        """
        n = self.num_vehicles
        # 从前向后传播：前车已激活 → 倒计时激活后车
        for i in range(1, n):
            if self._air_brake_active[i - 1] and not self._air_brake_active[i]:
                self._air_brake_delay_remaining[i] -= dt
                if self._air_brake_delay_remaining[i] <= 0.0:
                    self._air_brake_active[i] = True
                    self._air_brake_notch[i] = self._air_brake_notch[i - 1]
        # 从后向前传播：后车已激活 → 倒计时激活前车（尾部动力/中部动力）
        # 【bug修复】缓解状态（车头 _air_brake_releasing[0]）时禁止反向制动传播：
        # 否则缓解波传播中尾部仍 active → 反向把已释放的前车重新激活 → active车反而增加
        # → 缓解不生效 → 持续制动 → 掉速（8/18 诊断：缓解后 active 6→21、制动力不归零）
        if not self._air_brake_releasing[0]:
            for i in range(n - 2, -1, -1):
                if self._air_brake_active[i + 1] and not self._air_brake_active[i]:
                    self._air_brake_delay_remaining[i] -= dt
                    if self._air_brake_delay_remaining[i] <= 0.0:
                        self._air_brake_active[i] = True
                        self._air_brake_notch[i] = self._air_brake_notch[i + 1]

        # 【缓解波传播修复 2026-08-22】连续波前并行释放（替代原"逐节串行等待"）。
        # 原实现依赖 releasing[i-1]（前一节已释放才倒计时本节的独立满 delay），导致
        # 第 k 节需 ~60k 步才释放（串行累积，缓解传播严重延迟 → 尾部残留满制动 → 拖停）。
        # 正确物理：缓解波以 ~200m/s 连续传播，各节 delay = distance/波速，并行独立倒计时，
        # 波前到达即释放（1200m 车长 6 秒传完），保留"缓解后车钩力最大"不同步物理现象。
        # 每节 i 在缓解开始时已被 `_reset_air_brake_command` 标记 releasing[i]=True 并设置
        # delay_remaining[i]=distance/波速；此处对"缓解波传播中且仍在制动"的节独立倒计时。
        for i in range(n):
            if self._air_brake_releasing[i] and self._air_brake_active[i]:
                self._air_brake_delay_remaining[i] -= dt
                # 制动力随缓解进度衰减：delay 剩余越多，制动力越大；delay→0 时制动力→0
                self._air_brake_release_frac[i] = max(
                    self._air_brake_delay_remaining[i] / max(self._air_brake_delay_total[i], 1e-6),
                    0.0,
                )
                if self._air_brake_delay_remaining[i] <= 0.0:
                    self._air_brake_active[i] = False
                    self._air_brake_notch[i] = AirBrakeNotch.RELEASE
                    self._air_brake_release_frac[i] = 0.0

        # 【EOT 缓解波】EOT 时 delay 已在 _reset_air_brake_command 设为 min(到头,到尾)/波速，
        # 正向传播循环按此 delay 递减即可实现"两端向中间缓解"，无需单独反向循环。

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

        if not self._air_brake_active[vehicle_idx]:
            self._air_brake_active[vehicle_idx] = True
            self._air_brake_notch[vehicle_idx] = cmd_notch
            # 若该节正在缓解波传播中，清除缓解状态（重新制动）
            if self._air_brake_releasing[vehicle_idx]:
                self._air_brake_releasing[vehicle_idx] = False
            # E7：重新制动时恢复满制动力（清除缓解衰减）
            self._air_brake_release_frac[vehicle_idx] = 1.0
            # 向后传播（source -> 后方）
            for j in range(vehicle_idx + 1, n):
                distance = cum_len[j] - cum_len[vehicle_idx]
                self._air_brake_delay_remaining[j] = max(distance / wave_speed, 0.0)
            # 向前传播（source -> 前方），用于尾部/中部动力（分布式制动）
            if bidirectional:
                for j in range(vehicle_idx - 1, -1, -1):
                    distance = cum_len[vehicle_idx] - cum_len[j]
                    self._air_brake_delay_remaining[j] = max(distance / wave_speed, 0.0)

    def _reset_air_brake_command(self, vehicle_idx: int = 0, sync: bool = False, eot: bool = False):
        """缓解空气制动。

        真实缓解（sync=False，默认）：缓解波按波速（~200m/s）从车头向后传播，
        车头先缓、车尾后缓，不同步导致"缓解后车钩力最大"（张二田等一致）。
        仅释放源头车辆，后方由 `_advance_air_brake_propagation` 逐节延迟释放。

        同步缓解（sync=True）：所有车厢立即同时释放（简化物理）。
        E7 分层：第1层（单列控速，train_cyclic_braking）用 sync=True 简化缓解，
        避免缓解波延迟导致 RL 训练掉速+车钩力爆炸学不会；第2层（多列协同）用
        缓解波（sync=False）保留"缓解后车钩力最大"物理机制。

        EOT（eot=True，论文解决方案）：缓解时**尾部同时触发缓解波**（双向缓解）。
        真实重载列车配 EOT（可控尾车），缓解时尾部同步排风加速缓解波传播，
        提升缓解同步性。论文依据：Zhang2025 大秦线 20kT EOT 使最大拉钩力
        780→489kN（-37%）；樊运新 3万吨 长大下坡循环制动最大拉钩力 952.6kN
        （尾部分布式动力提升同步）。EOT 让缓解波下"缓解后车钩力最大"的峰值
        显著降低，车钩力可守住 1000kN。
        """
        n = self.num_vehicles
        if sync:
            # 同步缓解：所有车厢立即释放
            self._air_brake_active[:] = False
            self._air_brake_notch[:] = AirBrakeNotch.RELEASE
            self._air_brake_releasing[:] = False
            self._air_brake_release_frac[:] = 1.0
            self._air_brake_delay_remaining[:] = 0.0
            return
        cum_len = self._vehicle_cum_lengths()
        wave_speed = AIR_BRAKE_PROPAGATION_SPEED_SERVICE
        # 源头车辆立即释放，并触发缓解波
        if vehicle_idx < n:
            self._air_brake_active[vehicle_idx] = False
            self._air_brake_notch[vehicle_idx] = AirBrakeNotch.RELEASE
            self._air_brake_releasing[vehicle_idx] = True
            self._air_brake_delay_remaining[vehicle_idx] = 0.0
            # 对后方仍在制动的车辆设置缓解波延迟（按距离/波速）
            for j in range(vehicle_idx + 1, n):
                if self._air_brake_active[j]:
                    distance = cum_len[j] - cum_len[vehicle_idx]
                    delay = max(distance / wave_speed, 0.0)
                    # EOT：尾部（倒数第1节）也作为缓解源，缓解波双向传播 →
                    # 中间车辆延迟 = min(到头距离, 到尾部距离)/波速，缓解同步性显著提升
                    if eot:
                        distance_to_tail = cum_len[n - 1] - cum_len[j]
                        delay = min(delay, max(distance_to_tail / wave_speed, 0.0))
                    self._air_brake_delay_remaining[j] = delay
                    # E7：记录缓解波初始延迟总量，供制动力渐变衰减
                    self._air_brake_delay_total[j] = delay
                    # 【缓解波修复 2026-08-22】标记该节"缓解波传播中"（releasing=True）。
                    # 原实现缓解波循环依赖 releasing[i-1]（逐节串行），导致第 k 节需
                    # ~60k 步才释放（串行累积），缓解传播严重延迟 → 尾部残留满制动 → 拖停。
                    # 改为各节并行按 distance/波速 独立倒计时（连续波前，6 秒传完）。
                    self._air_brake_releasing[j] = True
                    self._air_brake_release_frac[j] = 1.0
            if eot:
                # EOT：尾部也立即释放并作为缓解波源（双向）
                self._air_brake_active[n - 1] = False
                self._air_brake_notch[n - 1] = AirBrakeNotch.RELEASE
                self._air_brake_releasing[n - 1] = True
                self._air_brake_delay_remaining[n - 1] = 0.0

    def max_throttle_at_speed(self, speed_mps: float) -> float:
        """该速度下允许的最大 throttle（由机车档位曲线决定）。"""
        vals = []
        for v in self.consist.vehicles:
            if v.is_locomotive:
                vals.append(throttle_coefficient(speed_mps, v.max_speed_mps, v.n_notches))
        return max(vals) if vals else 1.0
