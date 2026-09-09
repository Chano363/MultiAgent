from __future__ import annotations

import math
from dataclasses import dataclass

from .models import LongitudinalSnapshot, ManualCommand, SimulationState, TrainConfig


MODEL_ID = "matlab_macro_longitudinal_rk4_v4_no_lateral"
GRAVITY_MPS2 = 9.81
CURVE_RESISTANCE_COEFFICIENT = 700.0
MAX_RK4_STEP_S = 0.02
STATIC_SPEED_THRESHOLD_MPS = 1.0e-3

COUPLER_GAP_M = 0.015
COUPLER_GAP_VARIATION_M = 0.003
COUPLER_HARDENING_STROKE_M = 0.08
COUPLER_TENSION_STIFFNESS_N_PER_M = 4.5e6
COUPLER_COMPRESSION_STIFFNESS_N_PER_M = 6.5e6
COUPLER_HARDENING_MULTIPLIER = 3.0
COUPLER_TENSION_DAMPING_N_S_PER_M = 9.0e5
COUPLER_COMPRESSION_DAMPING_N_S_PER_M = 1.15e6
COUPLER_DRY_FRICTION_TENSION_N = 50e3
COUPLER_DRY_FRICTION_COMPRESSION_N = 80e3
COUPLER_DRY_FRICTION_VELOCITY_EPS_MPS = 0.02
COUPLER_HYSTERESIS_STIFFNESS_N_PER_M = 9.0e6
COUPLER_HYSTERESIS_TENSION_LIMIT_N = 160e3
COUPLER_HYSTERESIS_COMPRESSION_LIMIT_N = 240e3
COUPLER_HYSTERESIS_RESET_TAU_S = 0.20
COUPLER_STIFFNESS_VARIATION = 0.08
COUPLER_DAMPING_VARIATION = 0.20
COUPLER_FRICTION_VARIATION = 0.20
COUPLER_HYSTERESIS_LIMIT_VARIATION = 0.20
MAX_COUPLER_FORCE_N = 1.0e6

AIR_BUILD_TIME_S = 20.0
AIR_RELEASE_TIME_S = 20.0
AIR_CHARGE_TIME_S = 180.0
AIR_WAVE_SPEED_MPS = 200.0
TRACTION_EFFORT_TAU_S = 8.0
TRACTION_EFFORT_MAX_RATE_N_PER_S = 35.0e3


@dataclass(frozen=True)
class ExpandedVehicle:
    role: str
    vehicle_id: str
    mass_kg: float
    length_m: float
    kh_kn: float
    res_a: float
    res_b: float
    res_c: float

    @property
    def is_loco(self) -> bool:
        return self.role == "locomotive"


@dataclass
class AirTransition:
    mode: str = "idle"
    target_dp_kpa: float = 0.0
    release_dp_kpa: float = 0.0
    start_s: float = 0.0
    release_start_factors: list[float] | None = None


@dataclass(frozen=True)
class CouplerParameters:
    gap_m: float
    hardening_stroke_m: float
    tension_stiffness_n_per_m: float
    compression_stiffness_n_per_m: float
    hardening_multiplier: float
    tension_damping_n_s_per_m: float
    compression_damping_n_s_per_m: float
    tension_friction_n: float
    compression_friction_n: float
    friction_velocity_eps_mps: float
    hysteresis_stiffness_n_per_m: float
    hysteresis_tension_limit_n: float
    hysteresis_compression_limit_n: float
    hysteresis_reset_tau_s: float


def expand_train_config(config: TrainConfig) -> list[ExpandedVehicle]:
    vehicles = []
    for item in config.consist:
        for _ in range(item.quantity):
            params = config.locomotive if item.role == "locomotive" else config.vehicles[item.vehicle_id]
            vehicles.append(
                ExpandedVehicle(
                    role=item.role,
                    vehicle_id=params.id,
                    mass_kg=params.mass_t * 1000.0,
                    length_m=params.length_m,
                    kh_kn=445.0 if item.role == "locomotive" else 160.0,
                    res_a=params.res_a_n_per_t,
                    res_b=params.res_b_n_per_t_kmh,
                    res_c=params.res_c_n_per_t_kmh2,
                )
            )
    if not vehicles or not any(vehicle.is_loco for vehicle in vehicles):
        raise ValueError("Train consist must contain at least one locomotive")
    return vehicles


def beta_from_air_reduction(dp_kpa: float) -> float:
    dp_table = [0.0, 50.0, 60.0, 70.0, 80.0, 90.0, 100.0, 110.0, 120.0, 130.0, 140.0, 150.0, 160.0, 170.0]
    beta_table = [0.0, 0.17, 0.28, 0.37, 0.46, 0.53, 0.60, 0.67, 0.73, 0.78, 0.83, 0.88, 0.93, 0.96]
    dp = max(dp_table[0], min(dp_table[-1], float(dp_kpa)))
    for index in range(len(dp_table) - 1):
        left, right = dp_table[index], dp_table[index + 1]
        if left <= dp <= right:
            ratio = (dp - left) / (right - left)
            return beta_table[index] + ratio * (beta_table[index + 1] - beta_table[index])
    return beta_table[-1]


def loco_force_limits_n(speed_kmh: float) -> tuple[float, float]:
    speed = max(0.0, float(speed_kmh))
    if speed <= 5.0:
        traction_kn = 760.0
    elif speed <= 65.0:
        traction_kn = 779.0 - 3.8 * speed
    else:
        traction_kn = 34560.0 / max(speed, 1.0e-6)
    if speed <= 3.0:
        electric_brake_kn = 153.3 * speed
    elif speed <= 75.0:
        electric_brake_kn = 461.0
    else:
        electric_brake_kn = 34560.0 / max(speed, 1.0e-6)
    return traction_kn * 1000.0, electric_brake_kn * 1000.0


class MatlabMacroLongitudinalEngine:
    """Realtime multi-vehicle longitudinal model without lateral dynamics."""

    def __init__(self, config: TrainConfig):
        self.config = config
        self.vehicles = expand_train_config(config)
        self.total_mass_kg = sum(vehicle.mass_kg for vehicle in self.vehicles)
        self.sum_kh_kn = sum(vehicle.kh_kn for vehicle in self.vehicles)
        self._initial_positions = self._initial_positions_for(self.vehicles)
        self._positions = list(self._initial_positions)
        self._speeds = [0.0 for _ in self.vehicles]
        count = max(len(self.vehicles) - 1, 0)
        self._coupler_parameters = [self._coupler_parameters_for_index(i) for i in range(count)]
        self._coupler_hysteresis_forces = [0.0 for _ in range(count)]
        self._actual_efforts_n = [0.0 for _ in self.vehicles]
        self._traction_target = 0.0
        self._ebrake_target = 0.0
        self._air_transition = AirTransition()
        self._last_command_targets = (0.0, 0.0, 0.0)
        self._air_distances_m = self._air_distances()
        self.state = SimulationState(speed_limit_kmh=self._lookup(config.speed_limits, 0.0, 80.0))
        self._last_snapshot = LongitudinalSnapshot(0.0)

    @staticmethod
    def _initial_positions_for(vehicles: list[ExpandedVehicle]) -> list[float]:
        positions = [0.0]
        for index in range(1, len(vehicles)):
            previous = vehicles[index - 1]
            current = vehicles[index]
            positions.append(positions[-1] - previous.length_m / 2.0 - current.length_m / 2.0)
        return positions

    def _air_distances(self) -> list[float]:
        loco_positions = [
            self._initial_positions[index]
            for index, vehicle in enumerate(self.vehicles)
            if vehicle.is_loco
        ]
        return [
            min(abs(position - loco_position) for loco_position in loco_positions)
            for position in self._initial_positions
        ]

    @staticmethod
    def _deterministic_unit(index: int, salt: int) -> float:
        seed = ((index + 1) * 1103515245 + salt * 12345) & 0x7FFFFFFF
        return 2.0 * (seed / 0x7FFFFFFF) - 1.0

    @classmethod
    def _coupler_parameters_for_index(cls, index: int) -> CouplerParameters:
        stiffness = 1.0 + COUPLER_STIFFNESS_VARIATION * cls._deterministic_unit(index, 1)
        damping = 1.0 + COUPLER_DAMPING_VARIATION * cls._deterministic_unit(index, 2)
        friction = 1.0 + COUPLER_FRICTION_VARIATION * cls._deterministic_unit(index, 3)
        hysteresis = 1.0 + COUPLER_HYSTERESIS_LIMIT_VARIATION * cls._deterministic_unit(index, 4)
        gap = max(0.005, COUPLER_GAP_M + COUPLER_GAP_VARIATION_M * cls._deterministic_unit(index, 5))
        return CouplerParameters(
            gap_m=gap,
            hardening_stroke_m=COUPLER_HARDENING_STROKE_M,
            tension_stiffness_n_per_m=COUPLER_TENSION_STIFFNESS_N_PER_M * stiffness,
            compression_stiffness_n_per_m=COUPLER_COMPRESSION_STIFFNESS_N_PER_M * stiffness,
            hardening_multiplier=COUPLER_HARDENING_MULTIPLIER,
            tension_damping_n_s_per_m=COUPLER_TENSION_DAMPING_N_S_PER_M * damping,
            compression_damping_n_s_per_m=COUPLER_COMPRESSION_DAMPING_N_S_PER_M * damping,
            tension_friction_n=COUPLER_DRY_FRICTION_TENSION_N * friction,
            compression_friction_n=COUPLER_DRY_FRICTION_COMPRESSION_N * friction,
            friction_velocity_eps_mps=COUPLER_DRY_FRICTION_VELOCITY_EPS_MPS,
            hysteresis_stiffness_n_per_m=COUPLER_HYSTERESIS_STIFFNESS_N_PER_M,
            hysteresis_tension_limit_n=COUPLER_HYSTERESIS_TENSION_LIMIT_N * hysteresis,
            hysteresis_compression_limit_n=COUPLER_HYSTERESIS_COMPRESSION_LIMIT_N * hysteresis,
            hysteresis_reset_tau_s=COUPLER_HYSTERESIS_RESET_TAU_S,
        )

    def detail_snapshot(self) -> LongitudinalSnapshot:
        return self._last_snapshot

    def clamp_head_position(self, progress_m: float) -> SimulationState:
        target = max(0.0, min(float(progress_m), self.config.route_end_m))
        current = self._positions[0] - self._initial_positions[0]
        shift = target - current
        self._positions = [position + shift for position in self._positions]
        self._speeds = [0.0 for _ in self._speeds]
        self._actual_efforts_n = [0.0 for _ in self._actual_efforts_n]
        return self._publish_state()

    def step(self, command: ManualCommand, dt: float) -> SimulationState:
        command = command.normalized()
        dt = max(0.0, float(dt))
        if dt == 0.0:
            return self.state
        self._sync_command(command)
        remaining = dt
        while remaining > 1.0e-12:
            step = min(MAX_RK4_STEP_S, remaining)
            self._rk4_step(step)
            remaining -= step
        if self._positions[0] - self._initial_positions[0] > self.config.route_end_m:
            return self.clamp_head_position(self.config.route_end_m)
        return self._publish_state()

    def _sync_command(self, command: ManualCommand) -> None:
        self._refresh_air_transition(self.state.time_s)
        self._traction_target = command.traction_level / 10.0
        self._ebrake_target = command.electric_brake_level / 10.0
        target_air_dp = 170.0 if command.is_emergency else float(command.air_brake_reduction_kpa)
        if not self._air_command_available() and target_air_dp > 0.0:
            target_air_dp = 0.0
        targets = (self._traction_target, self._ebrake_target, target_air_dp)
        if targets == self._last_command_targets:
            return
        now = self.state.time_s
        previous_air_dp = self._last_command_targets[2]
        if target_air_dp != previous_air_dp:
            if target_air_dp > 0.0:
                self._air_transition = AirTransition(mode="apply", target_dp_kpa=target_air_dp, start_s=now)
            elif previous_air_dp > 0.0 or self._air_transition.mode == "apply":
                factors = [self._air_factor_for_vehicle(i, now) for i in range(len(self.vehicles))]
                self._air_transition = AirTransition(
                    mode="release",
                    release_dp_kpa=previous_air_dp,
                    start_s=now,
                    release_start_factors=factors,
                )
        self._last_command_targets = targets

    def _rk4_step(self, dt: float) -> None:
        time_s = self.state.time_s
        p0, v0 = self._positions, self._speeds
        h0, e0 = self._coupler_hysteresis_forces, self._actual_efforts_n
        k1 = self._evaluate(time_s, p0, v0, h0, e0)
        p2 = [p + dt * dp / 2.0 for p, dp in zip(p0, k1[0])]
        v2 = [max(0.0, v + dt * dv / 2.0) for v, dv in zip(v0, k1[1])]
        h2 = [self._clamp_hysteresis(h + dt * dh / 2.0, self._coupler_parameters[i]) for i, (h, dh) in enumerate(zip(h0, k1[2]))]
        e2 = [e + dt * de / 2.0 for e, de in zip(e0, k1[3])]
        k2 = self._evaluate(time_s + dt / 2.0, p2, v2, h2, e2)
        p3 = [p + dt * dp / 2.0 for p, dp in zip(p0, k2[0])]
        v3 = [max(0.0, v + dt * dv / 2.0) for v, dv in zip(v0, k2[1])]
        h3 = [self._clamp_hysteresis(h + dt * dh / 2.0, self._coupler_parameters[i]) for i, (h, dh) in enumerate(zip(h0, k2[2]))]
        e3 = [e + dt * de / 2.0 for e, de in zip(e0, k2[3])]
        k3 = self._evaluate(time_s + dt / 2.0, p3, v3, h3, e3)
        p4 = [p + dt * dp for p, dp in zip(p0, k3[0])]
        v4 = [max(0.0, v + dt * dv) for v, dv in zip(v0, k3[1])]
        h4 = [self._clamp_hysteresis(h + dt * dh, self._coupler_parameters[i]) for i, (h, dh) in enumerate(zip(h0, k3[2]))]
        e4 = [e + dt * de for e, de in zip(e0, k3[3])]
        k4 = self._evaluate(time_s + dt, p4, v4, h4, e4)
        self._positions = [
            value + dt * (a + 2.0 * b + 2.0 * c + d) / 6.0
            for value, a, b, c, d in zip(p0, k1[0], k2[0], k3[0], k4[0])
        ]
        self._speeds = [
            max(0.0, value + dt * (a + 2.0 * b + 2.0 * c + d) / 6.0)
            for value, a, b, c, d in zip(v0, k1[1], k2[1], k3[1], k4[1])
        ]
        self._coupler_hysteresis_forces = [
            self._clamp_hysteresis(
                value + dt * (a + 2.0 * b + 2.0 * c + d) / 6.0,
                self._coupler_parameters[index],
            )
            for index, (value, a, b, c, d) in enumerate(zip(h0, k1[2], k2[2], k3[2], k4[2]))
        ]
        self._actual_efforts_n = [
            value + dt * (a + 2.0 * b + 2.0 * c + d) / 6.0
            for value, a, b, c, d in zip(e0, k1[3], k2[3], k3[3], k4[3])
        ]
        self.state.time_s = time_s + dt
        self._refresh_air_transition(self.state.time_s)

    def _evaluate(self, time_s, positions, speeds, hysteresis_forces, actual_efforts):
        couplers, hysteresis_rates = self._coupler_response(positions, speeds, hysteresis_forces)
        head_speed_kmh = abs(speeds[0]) * 3.6
        dpos, dvel, defforts = [], [], []
        detail = {name: [] for name in ("couplers", "traction", "ebrake", "air", "rolling", "grade", "curve")}
        detail["couplers"] = couplers
        for index, vehicle in enumerate(self.vehicles):
            speed = speeds[index]
            route_position = positions[index] - self._initial_positions[0]
            rolling = self._rolling_resistance_n(vehicle, speed)
            grade = vehicle.mass_kg * 9.80665 * self._lookup(self.config.grades, route_position, 0.0) / 1000.0
            curve = self._curve_resistance_n(vehicle, self._lookup(self.config.curves, route_position, math.inf), speed)
            traction = ebrake = effort_rate = 0.0
            if vehicle.is_loco:
                traction_max, brake_max = loco_force_limits_n(head_speed_kmh)
                target_effort = self._traction_target * traction_max - self._ebrake_target * brake_max
                effort_rate = max(
                    -TRACTION_EFFORT_MAX_RATE_N_PER_S,
                    min(TRACTION_EFFORT_MAX_RATE_N_PER_S, (target_effort - actual_efforts[index]) / TRACTION_EFFORT_TAU_S),
                )
                if actual_efforts[index] >= 0.0:
                    traction = actual_efforts[index]
                else:
                    ebrake = -actual_efforts[index]
            air = self._air_force_n(index, vehicle, time_s, head_speed_kmh)
            front = couplers[index - 1] if index > 0 else 0.0
            rear = couplers[index] if index < len(couplers) else 0.0
            external = traction - ebrake - air - grade - curve + front - rear
            if abs(speed) < STATIC_SPEED_THRESHOLD_MPS:
                threshold = vehicle.res_a * vehicle.mass_kg / 1000.0 * GRAVITY_MPS2
                if abs(external) < threshold:
                    dpos.append(0.0)
                    dvel.append(0.0)
                else:
                    dpos.append(speed)
                    dvel.append((external - math.copysign(threshold, external)) / vehicle.mass_kg)
            else:
                dpos.append(speed)
                dvel.append((external - rolling) / vehicle.mass_kg)
            defforts.append(effort_rate)
            for name, value in (
                ("traction", traction), ("ebrake", ebrake), ("air", air),
                ("rolling", rolling), ("grade", grade), ("curve", curve),
            ):
                detail[name].append(value)
        return dpos, dvel, hysteresis_rates, defforts, detail

    @staticmethod
    def _clamp_hysteresis(value: float, params: CouplerParameters) -> float:
        return min(max(value, -params.hysteresis_compression_limit_n), params.hysteresis_tension_limit_n)

    def _coupler_response(self, positions, speeds, hysteresis_forces):
        forces, rates = [], []
        for index in range(len(self.vehicles) - 1):
            front, rear = self.vehicles[index], self.vehicles[index + 1]
            params = self._coupler_parameters[index]
            gap = (positions[index] - front.length_m / 2.0) - (positions[index + 1] + rear.length_m / 2.0)
            relative_speed = speeds[index] - speeds[index + 1]
            hysteresis = self._clamp_hysteresis(hysteresis_forces[index], params)
            rates.append(self._coupler_hysteresis_rate(gap, relative_speed, hysteresis, params))
            force = self._coupler_force(gap, relative_speed, hysteresis, params)
            forces.append(max(-MAX_COUPLER_FORCE_N, min(MAX_COUPLER_FORCE_N, force)))
        return forces, rates

    @staticmethod
    def _coupler_force(gap, relative_speed, hysteresis, params):
        if gap > params.gap_m:
            deflection = gap - params.gap_m
            linear = min(deflection, params.hardening_stroke_m)
            hard = max(deflection - params.hardening_stroke_m, 0.0)
            spring = params.tension_stiffness_n_per_m * linear + params.hardening_multiplier * params.tension_stiffness_n_per_m * hard
            damping = params.tension_damping_n_s_per_m * relative_speed
            friction = params.tension_friction_n * math.tanh(relative_speed / params.friction_velocity_eps_mps)
            return max(spring + damping + friction + hysteresis, 0.0)
        if gap < -params.gap_m:
            deflection = -gap - params.gap_m
            linear = min(deflection, params.hardening_stroke_m)
            hard = max(deflection - params.hardening_stroke_m, 0.0)
            spring = -(params.compression_stiffness_n_per_m * linear + params.hardening_multiplier * params.compression_stiffness_n_per_m * hard)
            damping = params.compression_damping_n_s_per_m * relative_speed
            friction = params.compression_friction_n * math.tanh(relative_speed / params.friction_velocity_eps_mps)
            return min(spring + damping + friction + hysteresis, 0.0)
        return 0.0

    @staticmethod
    def _coupler_hysteresis_rate(gap, relative_speed, hysteresis, params):
        active = abs(gap) > params.gap_m
        direction = 1.0 if relative_speed > 0.0 else -1.0 if relative_speed < 0.0 else 0.0
        limit = params.hysteresis_compression_limit_n if gap < -params.gap_m else params.hysteresis_tension_limit_n
        if active and direction:
            approach = max(1.0 - direction * hysteresis / max(limit, 1.0e-9), 0.0)
            return params.hysteresis_stiffness_n_per_m * relative_speed * approach
        if not active:
            return -hysteresis / params.hysteresis_reset_tau_s
        return 0.0

    @staticmethod
    def _rolling_resistance_n(vehicle: ExpandedVehicle, speed_mps: float) -> float:
        speed_kmh = abs(speed_mps) * 3.6
        resistance = vehicle.res_a + vehicle.res_b * speed_kmh + vehicle.res_c * speed_kmh**2
        weight_kn = vehicle.mass_kg / 1000.0 * GRAVITY_MPS2
        return resistance * weight_kn * math.tanh(speed_mps / 0.1)

    @staticmethod
    def _curve_resistance_n(vehicle: ExpandedVehicle, radius_m: float, speed_mps: float) -> float:
        if radius_m <= 0.0 or math.isinf(radius_m):
            return 0.0
        weight_kn = vehicle.mass_kg / 1000.0 * GRAVITY_MPS2
        return CURVE_RESISTANCE_COEFFICIENT / max(radius_m, 1.0) * weight_kn * math.tanh(speed_mps / 0.1)

    def _air_factor_for_vehicle(self, index: int, time_s: float) -> float:
        delay = self._air_distances_m[index] / AIR_WAVE_SPEED_MPS
        elapsed = time_s - self._air_transition.start_s
        if self._air_transition.mode == "apply":
            if elapsed <= delay:
                return 0.0
            return max(0.0, min(1.0, (elapsed - delay) / AIR_BUILD_TIME_S))
        if self._air_transition.mode == "release":
            factors = self._air_transition.release_start_factors or [0.0 for _ in self.vehicles]
            return factors[index] * max(0.0, 1.0 - max(0.0, elapsed) / AIR_RELEASE_TIME_S)
        return 0.0

    def _air_force_n(self, index, vehicle, time_s, head_speed_kmh):
        if self._air_transition.mode == "apply":
            reduction = self._air_transition.target_dp_kpa
        elif self._air_transition.mode == "release":
            reduction = self._air_transition.release_dp_kpa
        else:
            return 0.0
        ratio = (2.0 * head_speed_kmh + 150.0) / (3.0 * head_speed_kmh + 150.0)
        target = beta_from_air_reduction(reduction) * (vehicle.mass_kg / self.total_mass_kg) * 0.378 * ratio * self.sum_kh_kn * 1000.0
        return target * self._air_factor_for_vehicle(index, time_s)

    def _air_command_available(self) -> bool:
        return self._air_transition.mode not in {"release", "charge"}

    def _refresh_air_transition(self, time_s: float) -> None:
        if self._air_transition.mode == "release" and time_s - self._air_transition.start_s >= AIR_RELEASE_TIME_S:
            self._air_transition = AirTransition(mode="charge", start_s=self._air_transition.start_s + AIR_RELEASE_TIME_S)
        if self._air_transition.mode == "charge" and time_s - self._air_transition.start_s >= AIR_CHARGE_TIME_S:
            self._air_transition = AirTransition()

    def _air_status(self):
        mode = self._air_transition.mode
        if mode == "release":
            remaining = max(0.0, AIR_RELEASE_TIME_S - (self.state.time_s - self._air_transition.start_s))
            return "releasing", False, remaining, 0.0
        if mode == "charge":
            remaining = max(0.0, AIR_CHARGE_TIME_S - (self.state.time_s - self._air_transition.start_s))
            return "charging", False, 0.0, remaining
        if mode == "apply":
            factors = [self._air_factor_for_vehicle(i, self.state.time_s) for i in range(len(self.vehicles))]
            return ("holding" if factors and min(factors) >= 1.0 else "applying"), True, 0.0, 0.0
        return "ready", True, 0.0, 0.0

    def _publish_state(self) -> SimulationState:
        _, accelerations, _, _, detail = self._evaluate(
            self.state.time_s,
            self._positions,
            self._speeds,
            self._coupler_hysteresis_forces,
            self._actual_efforts_n,
        )
        progress_m = max(0.0, self._positions[0] - self._initial_positions[0])
        speeds_kmh = [speed * 3.6 for speed in self._speeds]
        train_speed = sum(vehicle.mass_kg * speed for vehicle, speed in zip(self.vehicles, speeds_kmh)) / self.total_mass_kg
        sums_kn = {name: sum(detail[name]) / 1000.0 for name in ("traction", "ebrake", "air", "rolling", "grade", "curve")}
        net_kn = sums_kn["traction"] - sums_kn["ebrake"] - sums_kn["air"] - sums_kn["rolling"] - sums_kn["grade"] - sums_kn["curve"]
        couplers_kn = [force / 1000.0 for force in detail["couplers"]]
        max_coupler = max(couplers_kn, key=abs) if couplers_kn else 0.0
        phase, available, release_remaining, charge_remaining = self._air_status()
        if self._air_transition.mode == "apply":
            display_reduction = self._air_transition.target_dp_kpa
        elif self._air_transition.mode == "release":
            average = sum(self._air_factor_for_vehicle(i, self.state.time_s) for i in range(len(self.vehicles))) / len(self.vehicles)
            display_reduction = self._air_transition.release_dp_kpa * average
        else:
            display_reduction = 0.0
        brake_pipe = 0.0 if display_reduction >= 170.0 else max(0.0, 500.0 - display_reduction)
        brake_cylinder = 450.0 if display_reduction >= 170.0 else min(400.0, display_reduction * 2.4)
        self.state = SimulationState(
            time_s=self.state.time_s,
            position_m=progress_m,
            speed_kmh=train_speed,
            acceleration_mps2=net_kn * 1000.0 / self.total_mass_kg,
            traction_force_kn=sums_kn["traction"],
            electric_brake_force_kn=sums_kn["ebrake"],
            air_brake_force_kn=sums_kn["air"],
            rolling_resistance_kn=sums_kn["rolling"],
            grade_resistance_kn=sums_kn["grade"],
            curve_resistance_kn=sums_kn["curve"],
            net_force_kn=net_kn,
            coupler_force_kn=max_coupler,
            brake_pipe_pressure_kpa=brake_pipe,
            brake_cylinder_pressure_kpa=brake_cylinder,
            grade_permille=self._lookup(self.config.grades, progress_m, 0.0),
            curve_radius_m=self._lookup(self.config.curves, progress_m, math.inf),
            speed_limit_kmh=self._lookup(self.config.speed_limits, progress_m, 80.0),
            emergency_active=self._air_transition.mode == "apply" and self._air_transition.target_dp_kpa >= 170.0,
            air_brake_phase=phase,
            air_brake_available=available,
            air_release_remaining_s=release_remaining,
            air_charge_remaining_s=charge_remaining,
            head_speed_kmh=speeds_kmh[0],
            head_acceleration_mps2=accelerations[0],
            tail_speed_kmh=speeds_kmh[-1],
            speed_spread_kmh=max(speeds_kmh) - min(speeds_kmh),
        )
        self._last_snapshot = LongitudinalSnapshot(
            time_s=self.state.time_s,
            vehicle_positions_m=[position - self._initial_positions[0] for position in self._positions],
            vehicle_speeds_kmh=speeds_kmh,
            coupler_forces_kn=couplers_kn,
        )
        return self.state

    @staticmethod
    def _lookup(segments, position_m: float, default: float) -> float:
        if position_m < 0.0 and segments and segments[0].start_m >= 0.0:
            position_m = 0.0
        for segment in segments:
            if segment.contains(position_m):
                return segment.value
        return default
