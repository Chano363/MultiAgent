from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class LocomotiveParams:
    id: str
    name: str
    mass_t: float
    length_m: float
    max_traction_kn: float
    max_electric_brake_kn: float
    res_a_n_per_t: float
    res_b_n_per_t_kmh: float
    res_c_n_per_t_kmh2: float


@dataclass(frozen=True)
class VehicleParams:
    id: str
    name: str
    mass_t: float
    length_m: float
    res_a_n_per_t: float
    res_b_n_per_t_kmh: float
    res_c_n_per_t_kmh2: float


@dataclass(frozen=True)
class ConsistItem:
    sequence: int
    vehicle_id: str
    quantity: int
    role: str


@dataclass(frozen=True)
class Segment:
    start_m: float
    end_m: float
    value: float

    def contains(self, position_m: float) -> bool:
        return self.start_m <= position_m < self.end_m


@dataclass(frozen=True)
class TrainConfig:
    locomotive: LocomotiveParams
    vehicles: dict[str, VehicleParams]
    consist: list[ConsistItem]
    grades: list[Segment]
    curves: list[Segment]
    speed_limits: list[Segment]
    route_end_m: float
    weight_key: str
    direction: str
    origin_position_m: float

    @property
    def total_mass_t(self) -> float:
        total = 0.0
        for item in self.consist:
            params = self.locomotive if item.role == "locomotive" else self.vehicles[item.vehicle_id]
            total += params.mass_t * item.quantity
        return total

    @property
    def total_length_m(self) -> float:
        total = 0.0
        for item in self.consist:
            params = self.locomotive if item.role == "locomotive" else self.vehicles[item.vehicle_id]
            total += params.length_m * item.quantity
        return total

    @property
    def wagon_count(self) -> int:
        return sum(item.quantity for item in self.consist if item.role != "locomotive")

    @property
    def locomotive_count(self) -> int:
        return sum(item.quantity for item in self.consist if item.role == "locomotive")


@dataclass
class ManualCommand:
    traction_level: int = 0
    electric_brake_level: int = 0
    air_brake_reduction_kpa: int = 0
    is_relief: bool = True
    is_emergency: bool = False

    def normalized(self) -> "ManualCommand":
        traction = max(0, min(10, int(self.traction_level)))
        electric = max(0, min(10, int(self.electric_brake_level)))
        reduction = max(0, min(170, int(self.air_brake_reduction_kpa)))
        emergency = bool(self.is_emergency)
        relief = bool(self.is_relief) and not emergency and reduction == 0
        if traction > 0:
            electric = 0
            reduction = 0
            relief = True
            emergency = False
        return ManualCommand(traction, electric, reduction, relief, emergency)


@dataclass
class SimulationState:
    time_s: float = 0.0
    position_m: float = 0.0
    speed_kmh: float = 0.0
    acceleration_mps2: float = 0.0
    traction_force_kn: float = 0.0
    electric_brake_force_kn: float = 0.0
    air_brake_force_kn: float = 0.0
    rolling_resistance_kn: float = 0.0
    grade_resistance_kn: float = 0.0
    curve_resistance_kn: float = 0.0
    net_force_kn: float = 0.0
    coupler_force_kn: float = 0.0
    brake_pipe_pressure_kpa: float = 500.0
    brake_cylinder_pressure_kpa: float = 0.0
    grade_permille: float = 0.0
    curve_radius_m: float = 0.0
    speed_limit_kmh: float = 80.0
    emergency_active: bool = False
    air_brake_phase: str = "ready"
    air_brake_available: bool = True
    air_release_remaining_s: float = 0.0
    air_charge_remaining_s: float = 0.0
    head_speed_kmh: float = 0.0
    head_acceleration_mps2: float = 0.0
    tail_speed_kmh: float = 0.0
    speed_spread_kmh: float = 0.0


@dataclass(frozen=True)
class LongitudinalSnapshot:
    time_s: float
    vehicle_positions_m: list[float] = field(default_factory=list)
    vehicle_speeds_kmh: list[float] = field(default_factory=list)
    coupler_forces_kn: list[float] = field(default_factory=list)
