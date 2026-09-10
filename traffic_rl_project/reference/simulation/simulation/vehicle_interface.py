from dataclasses import asdict, dataclass, field

from PySide6.QtCore import QObject, Signal

from .dynamics import ManualCommand, MatlabMacroLongitudinalEngine, TrainConfig


@dataclass(init=False)
class TrainDynamicState:
    position_km: float = 0.0
    speed_kmh: float = 0.0
    main_res_pressure_kpa: float = 800.0
    brake_pipe_pressure_kpa: float = 500.0
    allowed_speed_kmh: float = 80.0
    static_speed_limit_kmh: float = 80.0
    temp_speed_limit_kmh: float | None = None
    ma_end_km: float = 0.0
    air_brake_phase: str = "ready"
    air_brake_available: bool = True
    air_release_remaining_s: float = 0.0
    air_charge_remaining_s: float = 0.0
    emergency_brake: bool = False
    overspeed: bool = False
    emergency_brake_source: str = ""
    tracking_guard_active: bool = False
    clamped_position_km: float | None = None
    protection_curve_points: list[tuple[float, float]] = field(default_factory=list)
    base_curve_points: list[tuple[float, float]] = field(default_factory=list)
    target_braking_curve_points: list[tuple[float, float]] = field(default_factory=list)
    atp_controlling_source: str = "base_speed_limit"
    atp_target_name: str = ""
    atp_target_position_km: float | None = None
    atp_target_speed_kmh: float | None = None
    atp_brake_model_version: str = "atp_v1_segmented"
    atp_safety_margin_m: float = 50.0
    atp_reaction_time_s: float = 1.5

    def __init__(
        self,
        *,
        position_km: float = 0.0,
        speed_kmh: float = 0.0,
        main_res_pressure_kpa: float = 800.0,
        brake_pipe_pressure_kpa: float = 500.0,
        allowed_speed_kmh: float = 80.0,
        static_speed_limit_kmh: float = 80.0,
        temp_speed_limit_kmh: float | None = None,
        ma_end_km: float = 0.0,
        air_brake_phase: str = "ready",
        air_brake_available: bool = True,
        air_release_remaining_s: float = 0.0,
        air_charge_remaining_s: float = 0.0,
        emergency_brake: bool = False,
        overspeed: bool = False,
        emergency_brake_source: str = "",
        tracking_guard_active: bool = False,
        clamped_position_km: float | None = None,
        protection_curve_points: list[tuple[float, float]] | None = None,
        base_curve_points: list[tuple[float, float]] | None = None,
        target_braking_curve_points: list[tuple[float, float]] | None = None,
        atp_controlling_source: str = "base_speed_limit",
        atp_target_name: str = "",
        atp_target_position_km: float | None = None,
        atp_target_speed_kmh: float | None = None,
        atp_brake_model_version: str = "atp_v1_segmented",
        atp_safety_margin_m: float = 50.0,
        atp_reaction_time_s: float = 1.5,
        velocity: float | None = None,
        position: float | None = None,
        main_res_pressure: float | None = None,
        brake_pipe_pressure: float | None = None,
        clamped_position: float | None = None,
    ):
        self.position_km = float(position if position is not None else position_km)
        self.speed_kmh = float(velocity if velocity is not None else speed_kmh)
        self.main_res_pressure_kpa = float(
            main_res_pressure if main_res_pressure is not None else main_res_pressure_kpa
        )
        self.brake_pipe_pressure_kpa = float(
            brake_pipe_pressure if brake_pipe_pressure is not None else brake_pipe_pressure_kpa
        )
        self.allowed_speed_kmh = float(allowed_speed_kmh)
        self.static_speed_limit_kmh = float(static_speed_limit_kmh)
        self.temp_speed_limit_kmh = (
            None if temp_speed_limit_kmh is None else float(temp_speed_limit_kmh)
        )
        self.ma_end_km = float(ma_end_km)
        self.air_brake_phase = str(air_brake_phase)
        self.air_brake_available = bool(air_brake_available)
        self.air_release_remaining_s = float(air_release_remaining_s)
        self.air_charge_remaining_s = float(air_charge_remaining_s)
        self.emergency_brake = bool(emergency_brake)
        self.overspeed = bool(overspeed)
        self.emergency_brake_source = str(emergency_brake_source)
        self.tracking_guard_active = bool(tracking_guard_active)
        clamp_value = clamped_position if clamped_position is not None else clamped_position_km
        self.clamped_position_km = None if clamp_value is None else float(clamp_value)
        self.protection_curve_points = list(protection_curve_points or [])
        self.base_curve_points = list(base_curve_points or [])
        self.target_braking_curve_points = list(target_braking_curve_points or [])
        self.atp_controlling_source = str(atp_controlling_source)
        self.atp_target_name = str(atp_target_name)
        self.atp_target_position_km = (
            None if atp_target_position_km is None else float(atp_target_position_km)
        )
        self.atp_target_speed_kmh = (
            None if atp_target_speed_kmh is None else float(atp_target_speed_kmh)
        )
        self.atp_brake_model_version = str(atp_brake_model_version)
        self.atp_safety_margin_m = float(atp_safety_margin_m)
        self.atp_reaction_time_s = float(atp_reaction_time_s)

    def effective_position(self) -> float:
        return self.clamped_position_km if self.clamped_position_km is not None else self.position_km

    @property
    def velocity(self) -> float:
        return self.speed_kmh

    @velocity.setter
    def velocity(self, value: float) -> None:
        self.speed_kmh = float(value)

    @property
    def position(self) -> float:
        return self.position_km

    @position.setter
    def position(self, value: float) -> None:
        self.position_km = float(value)

    @property
    def main_res_pressure(self) -> float:
        return self.main_res_pressure_kpa

    @main_res_pressure.setter
    def main_res_pressure(self, value: float) -> None:
        self.main_res_pressure_kpa = float(value)

    @property
    def brake_pipe_pressure(self) -> float:
        return self.brake_pipe_pressure_kpa

    @brake_pipe_pressure.setter
    def brake_pipe_pressure(self, value: float) -> None:
        self.brake_pipe_pressure_kpa = float(value)

    @property
    def clamped_position(self) -> float | None:
        return self.clamped_position_km

    @clamped_position.setter
    def clamped_position(self, value: float | None) -> None:
        self.clamped_position_km = None if value is None else float(value)


class VehicleSimInterface(QObject):
    """Stable platform adapter around the multi-vehicle longitudinal engine."""

    state_updated = Signal(TrainDynamicState)

    def __init__(self, static_params: dict, dynamics_config: TrainConfig, parent=None):
        super().__init__(parent)
        self.static_params = static_params
        self.dynamics_config = dynamics_config
        self.engine = MatlabMacroLongitudinalEngine(dynamics_config)
        self.direction = dynamics_config.direction
        self._origin_position_km = dynamics_config.origin_position_m / 1000.0
        self._state = TrainDynamicState(position_km=self._origin_position_km)

        self.cmd_ele_level: float = 0.0
        self.cmd_air_brake_level: float = 0.0
        self.cmd_keep_flag: bool = False
        self.cmd_air_brake_relief: bool = False
        self.mode: str = "manual"
        self.running: bool = False
        self._motion_authorized: bool = False
        self.current_speed_limit: float = 80.0
        self._atp_allowed_speed_kmh: float = 80.0
        self._emergency_brake_reasons: set[str] = set()
        self._guard_position_limit_km: float | None = None

    def set_traction_level(self, value: float):
        self.cmd_ele_level = max(-10.0, min(10.0, float(value)))

    def set_ele_level(self, value: float):
        self.set_traction_level(value)

    def set_air_brake_reduction_kpa(self, value: float):
        value = float(value)
        if value != -1.0:
            value = max(0.0, min(170.0, value))
        self.cmd_air_brake_level = value

    def set_air_brake_level(self, value: float):
        self.set_air_brake_reduction_kpa(value)

    def set_keep_flag(self, value: bool):
        self.cmd_keep_flag = bool(value)

    def set_air_brake_relief(self, value: bool):
        self.cmd_air_brake_relief = bool(value)

    def set_driver_mode(self, mode: str):
        self.mode = mode

    def set_mode(self, mode: str):
        self.set_driver_mode(mode)

    def set_speed_limit(self, limit: float):
        self.current_speed_limit = float(limit)

    def set_external_speed_limit(self, limit: float):
        self._atp_allowed_speed_kmh = max(0.0, float(limit))

    def apply_atp_result(self, atp_result):
        self.set_external_speed_limit(atp_result.allowed_speed_mps * 3.6)
        self._state.allowed_speed_kmh = atp_result.allowed_speed_mps * 3.6
        self._state.static_speed_limit_kmh = atp_result.static_speed_limit_mps * 3.6
        self._state.temp_speed_limit_kmh = (
            None
            if atp_result.temp_speed_limit_mps is None
            else atp_result.temp_speed_limit_mps * 3.6
        )
        self._state.ma_end_km = atp_result.ma_end_m / 1000.0
        self._state.protection_curve_points = list(atp_result.protection_curve_points)
        self._state.base_curve_points = list(atp_result.base_curve_points)
        self._state.target_braking_curve_points = list(atp_result.target_braking_curve_points)
        self._state.atp_controlling_source = atp_result.controlling_source
        self._state.atp_target_name = atp_result.target_name
        self._state.atp_target_position_km = (
            None if atp_result.target_position_m is None else atp_result.target_position_m / 1000.0
        )
        self._state.atp_target_speed_kmh = (
            None if atp_result.target_speed_mps is None else atp_result.target_speed_mps * 3.6
        )
        self._state.atp_brake_model_version = atp_result.brake_model_version
        self._state.atp_safety_margin_m = atp_result.safety_margin_m
        self._state.atp_reaction_time_s = atp_result.reaction_time_s
        self._state.overspeed = bool(atp_result.overspeed)
        if atp_result.emergency_brake:
            self.trigger_emergency_brake("atp")
        else:
            self.clear_emergency_brake("atp")

    def apply_atp_protection(self, atp_result):
        self.apply_atp_result(atp_result)

    def start(self):
        self.running = True

    def stop(self):
        self.running = False
        self._motion_authorized = False

    def set_motion_authorized(self, authorized: bool):
        self._motion_authorized = bool(authorized)
        if not self._motion_authorized:
            self._freeze_at_current_position()

    def trigger_emergency_brake(self, reason: str = "manual"):
        self.cmd_ele_level = 0.0
        self._emergency_brake_reasons.add(reason)
        self._refresh_emergency_state()

    def clear_emergency_brake(self, reason: str = ""):
        if reason:
            self._emergency_brake_reasons.discard(reason)
        else:
            self._emergency_brake_reasons.clear()
        self._refresh_emergency_state()

    def set_guard_position_km(self, position_km: float):
        self._guard_position_limit_km = float(position_km)

    def set_guard_position_limit(self, position_km: float):
        self.set_guard_position_km(position_km)

    def clear_guard_position_km(self):
        self._guard_position_limit_km = None
        self._state.clamped_position_km = None

    def clear_guard_position_limit(self):
        self.clear_guard_position_km()

    def _refresh_emergency_state(self):
        priority = ["atp", "overspeed", "tracking_guard", "manual"]
        active_reason = next(
            (reason for reason in priority if reason in self._emergency_brake_reasons),
            "",
        )
        if not active_reason and self._emergency_brake_reasons:
            active_reason = sorted(self._emergency_brake_reasons)[0]
        self._state.emergency_brake = bool(self._emergency_brake_reasons)
        self._state.emergency_brake_source = active_reason
        self._state.tracking_guard_active = "tracking_guard" in self._emergency_brake_reasons

    def get_state_copy(self) -> TrainDynamicState:
        return TrainDynamicState(**asdict(self._state))

    def publish_state(self) -> TrainDynamicState:
        self.state_updated.emit(self._state)
        return self._state

    def _build_command(self) -> ManualCommand:
        emergency = bool(self._emergency_brake_reasons) or self.cmd_air_brake_level == -1.0
        traction_level = int(round(max(0.0, self.cmd_ele_level)))
        electric_brake_level = int(round(max(0.0, -self.cmd_ele_level)))
        air_reduction = int(round(max(0.0, self.cmd_air_brake_level)))
        if emergency:
            traction_level = 0
        return ManualCommand(
            traction_level=traction_level,
            electric_brake_level=electric_brake_level,
            air_brake_reduction_kpa=air_reduction,
            is_relief=air_reduction == 0 and not emergency,
            is_emergency=emergency,
        )

    def _absolute_position_km(self, progress_m: float) -> float:
        offset_km = progress_m / 1000.0
        if self.direction == "down":
            return self._origin_position_km + offset_km
        return self._origin_position_km - offset_km

    def _progress_for_absolute_position(self, position_km: float) -> float:
        if self.direction == "down":
            return (position_km - self._origin_position_km) * 1000.0
        return (self._origin_position_km - position_km) * 1000.0

    def _freeze_at_current_position(self) -> TrainDynamicState:
        self.cmd_ele_level = 0.0
        current_position_km = self._state.effective_position()
        progress_m = self._progress_for_absolute_position(current_position_km)
        engine_state = self.engine.clamp_head_position(progress_m)
        self._apply_engine_state(engine_state)
        return self._state

    def _guard_crossed(self, position_km: float) -> bool:
        if self._guard_position_limit_km is None:
            return False
        if self.direction == "down":
            return position_km > self._guard_position_limit_km
        return position_km < self._guard_position_limit_km

    def _apply_engine_state(self, engine_state, clamped_position: float | None = None) -> None:
        self._state.speed_kmh = max(0.0, float(engine_state.speed_kmh))
        self._state.position_km = self._absolute_position_km(engine_state.position_m)
        self._state.main_res_pressure_kpa = 800.0
        self._state.brake_pipe_pressure_kpa = float(engine_state.brake_pipe_pressure_kpa)
        self._state.air_brake_phase = str(engine_state.air_brake_phase)
        self._state.air_brake_available = bool(engine_state.air_brake_available)
        self._state.air_release_remaining_s = float(engine_state.air_release_remaining_s)
        self._state.air_charge_remaining_s = float(engine_state.air_charge_remaining_s)
        self._state.clamped_position_km = clamped_position
        if not self._emergency_brake_reasons and engine_state.emergency_active:
            self._state.emergency_brake = True
            self._state.emergency_brake_source = "manual"
        else:
            self._refresh_emergency_state()

    def step(self, dt: float, *, emit_signal: bool = True) -> TrainDynamicState:
        if not self.running:
            return self._state
        if not self._motion_authorized:
            if emit_signal:
                self.state_updated.emit(self._state)
            return self._state

        engine_state = self.engine.step(self._build_command(), dt)
        absolute_position = self._absolute_position_km(engine_state.position_m)
        clamped_position = None
        if self._guard_crossed(absolute_position):
            clamped_position = self._guard_position_limit_km
            progress_m = self._progress_for_absolute_position(clamped_position)
            engine_state = self.engine.clamp_head_position(progress_m)
        self._apply_engine_state(engine_state, clamped_position)
        if emit_signal:
            self.state_updated.emit(self._state)
        return self._state
