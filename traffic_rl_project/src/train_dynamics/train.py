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

        # 空气制动传播状态：
        #   _air_brake_active[i] 是否已接收制动指令
        #   _air_brake_notch[i]   当前实际生效的离散档位
        #   _air_brake_delay_remaining[i] 剩余传播延迟（秒）
        self._air_brake_active = np.zeros(n, dtype=bool)
        self._air_brake_notch = np.array(
            [AirBrakeNotch.RELEASE] * n, dtype=object
        )
        self._air_brake_delay_remaining = np.zeros(n)

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
        """计算每节车受到的车钩合力（正=向前）。"""
        n = self.num_vehicles
        forces = np.zeros(n)
        if n < 2:
            return forces
        p = self.coupler
        for i in range(n - 1):
            f = coupler_force(
                self.pos[i], self.vel[i],
                self.pos[i + 1], self.vel[i + 1],
                p.stiffness, p.damping, p.free_length_m,
            )
            forces[i] += f       # 前车受后车拉力
            forces[i + 1] -= f   # 后车受前车反力
        return forces

    def _resistance_forces(self) -> np.ndarray:
        """Davis 阻力（恒与速度方向相反，含坡度项在 grade 中单独计算）。"""
        n = self.num_vehicles
        forces = np.zeros(n)
        for i, v in enumerate(self.consist.vehicles):
            forces[i] = resistance_force_n(
                v.mass_t, v.no_of_axles, v.frontal_area_m2, v.drag_coef,
                abs(self.vel[i]), 0.0, 0.0,
            ) * np.sign(self.vel[i]) if abs(self.vel[i]) > 1e-6 else 0.0
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

    def step_vehicles_ed_ab(
        self,
        throttle: np.ndarray,
        ed_throttle: np.ndarray,
        ab_command: AirBrakeNotch,
        brake_origin: int = 0,
    ):
        """按 电制动（连续）+ 空气制动（离散+波速传播）推进一个时间步。

        Args:
            throttle: 每节车牵引 throttle（0~1，仅机车有效）
            ed_throttle: 每节车电制动指令（0~1，仅机车有效，连续）
            ab_command: 空气制动指令（离散档位，队首发出后向后传播）
            brake_origin: 空气制动指令源车辆索引（默认 0=机车/队首）
        """
        # 空气制动指令：发出后由 _apply_air_brake_command 建立向后传播
        if ab_command != AirBrakeNotch.RELEASE:
            if not self._air_brake_active[brake_origin]:
                self._apply_air_brake_command(ab_command, brake_origin)
        else:
            # 缓解：仅在确实处于制动状态时释放
            if np.any(self._air_brake_active):
                self._reset_air_brake_command(brake_origin)

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
        """推进空气制动波速传播：按车列从前向后逐节延迟生效。

        空气制动指令在队首（机车）发出，以有限波速沿车辆累计长度向后传播。
        传播延迟 = 到该车的累计距离 / 波速（真实重载列车制动波速为 200~250 m/s）。
        """
        n = self.num_vehicles
        for i in range(1, n):
            # 前车已激活时，若当前车尚未激活，则倒计时传播延迟
            if self._air_brake_active[i - 1] and not self._air_brake_active[i]:
                self._air_brake_delay_remaining[i] -= dt
                if self._air_brake_delay_remaining[i] <= 0.0:
                    self._air_brake_active[i] = True
                    self._air_brake_notch[i] = self._air_brake_notch[i - 1]

    def _apply_air_brake_command(self, cmd_notch: AirBrakeNotch, vehicle_idx: int):
        """对 vehicle_idx 施加空气制动指令，并初始化向后传播。

        vehicle_idx 为 0（机车）时为指令源；传播延迟按车辆累计长度与波速计算，
        越靠后的车辆延迟越大（这正是纵向冲动的主要来源）。
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
            # 为后续车辆设置传播延迟（相对指令源的距离差 / 波速）
            for j in range(vehicle_idx + 1, n):
                distance = cum_len[j] - cum_len[vehicle_idx]
                self._air_brake_delay_remaining[j] = max(distance / wave_speed, 0.0)

    def _reset_air_brake_command(self, vehicle_idx: int = 0):
        """缓解空气制动（全部车辆释放）。"""
        n = self.num_vehicles
        for i in range(vehicle_idx, n):
            self._air_brake_active[i] = False
            self._air_brake_notch[i] = AirBrakeNotch.RELEASE
            self._air_brake_delay_remaining[i] = 0.0

    def max_throttle_at_speed(self, speed_mps: float) -> float:
        """该速度下允许的最大 throttle（由机车档位曲线决定）。"""
        vals = []
        for v in self.consist.vehicles:
            if v.is_locomotive:
                vals.append(throttle_coefficient(speed_mps, v.max_speed_mps, v.n_notches))
        return max(vals) if vals else 1.0
