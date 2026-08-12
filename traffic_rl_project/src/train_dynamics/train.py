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
from .braking import braking_force, BrakeShoeType
from .coupler import coupler_force
from .params import TrainConsist, CouplerParams


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

    def _braking_forces(self, brake_notch: float) -> np.ndarray:
        """制动力（与速度方向相反）。"""
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
            brake_notch: 每节车制动档位（0~1）
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
        """每节车独立制动力。"""
        n = self.num_vehicles
        forces = np.zeros(n)
        for i, v in enumerate(self.consist.vehicles):
            f = braking_force(
                v.mass_t, abs(self.vel[i]), brake_notch[i], v.braked_weight_ratio,
            )
            forces[i] = -f * np.sign(self.vel[i]) if abs(self.vel[i]) > 1e-6 else -f
        return forces

    def max_throttle_at_speed(self, speed_mps: float) -> float:
        """该速度下允许的最大 throttle（由机车档位曲线决定）。"""
        vals = []
        for v in self.consist.vehicles:
            if v.is_locomotive:
                vals.append(throttle_coefficient(speed_mps, v.max_speed_mps, v.n_notches))
        return max(vals) if vals else 1.0
