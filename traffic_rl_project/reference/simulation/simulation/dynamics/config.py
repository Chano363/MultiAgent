from __future__ import annotations

import csv
from pathlib import Path

import pandas as pd

from .models import ConsistItem, LocomotiveParams, Segment, TrainConfig, VehicleParams


SUPPORTED_WEIGHT_KEYS = ("5000t", "10000t", "20000t")


def _float(row: dict[str, str], name: str) -> float:
    return float(row[name])


def _load_locomotive(path: Path) -> LocomotiveParams:
    with path.open(encoding="utf-8-sig", newline="") as stream:
        row = next(csv.DictReader(stream))
    return LocomotiveParams(
        id=row["id"],
        name=row["name"],
        mass_t=_float(row, "mass_t"),
        length_m=_float(row, "length_m"),
        max_traction_kn=_float(row, "max_traction_kn"),
        max_electric_brake_kn=_float(row, "max_electric_brake_kn"),
        res_a_n_per_t=_float(row, "res_a_n_per_t"),
        res_b_n_per_t_kmh=_float(row, "res_b_n_per_t_kmh"),
        res_c_n_per_t_kmh2=_float(row, "res_c_n_per_t_kmh2"),
    )


def _load_vehicles(path: Path) -> dict[str, VehicleParams]:
    result = {}
    with path.open(encoding="utf-8-sig", newline="") as stream:
        for row in csv.DictReader(stream):
            vehicle = VehicleParams(
                id=row["id"],
                name=row["name"],
                mass_t=_float(row, "mass_t"),
                length_m=_float(row, "length_m"),
                res_a_n_per_t=_float(row, "res_a_n_per_t"),
                res_b_n_per_t_kmh=_float(row, "res_b_n_per_t_kmh"),
                res_c_n_per_t_kmh2=_float(row, "res_c_n_per_t_kmh2"),
            )
            result[vehicle.id] = vehicle
    return result


def _load_consist(path: Path, weight_key: str) -> list[ConsistItem]:
    items = []
    with path.open(encoding="utf-8-sig", newline="") as stream:
        for row in csv.DictReader(stream):
            if row["weight_key"] != weight_key:
                continue
            items.append(
                ConsistItem(
                    sequence=int(row["sequence"]),
                    vehicle_id=row["vehicle_id"],
                    quantity=int(row["quantity"]),
                    role=row["role"],
                )
            )
    if not items:
        raise ValueError(f"Unsupported train weight configuration: {weight_key}")
    return sorted(items, key=lambda item: item.sequence)


def _read_line_segments(path: Path, value_kind: str) -> list[Segment]:
    df = pd.read_excel(path, sheet_name="Sheet1")
    if value_kind == "grade":
        start_col, length_col, value_col = "起始公里标", "长度", "坡度"
    elif value_kind == "curve":
        start_col, length_col, value_col = "起始公里标", "曲线长", "半径"
    else:
        start_col, length_col, value_col = "起始公里标", "长度", "限速值"

    segments = []
    for _, row in df.iterrows():
        if pd.isna(row.get(start_col)) or pd.isna(row.get(length_col)) or pd.isna(row.get(value_col)):
            continue
        start_m = float(row[start_col]) * 1000.0
        end_m = start_m + float(row[length_col])
        if end_m > start_m:
            segments.append(Segment(start_m, end_m, float(row[value_col])))
    return sorted(segments, key=lambda segment: segment.start_m)


def _line_end_m(data_line_root: Path, segment_groups: list[list[Segment]]) -> float:
    block_path = data_line_root / "闭塞分区表.xlsx"
    if block_path.exists():
        df = pd.read_excel(block_path, sheet_name="Sheet1")
        end_values = []
        for _, row in df.iterrows():
            if pd.isna(row.get("起始公里标")) or pd.isna(row.get("长度")):
                continue
            end_values.append(float(row["起始公里标"]) * 1000.0 + float(row["长度"]))
        if end_values:
            return max(end_values)
    return max(segment.end_m for segments in segment_groups for segment in segments)


def _map_segments(
    segments: list[Segment],
    origin_m: float,
    route_end_m: float,
    direction: str,
    rear_extent_m: float,
    *,
    negate_value: bool = False,
) -> list[Segment]:
    mapped = []
    absolute_left = max(0.0, origin_m - rear_extent_m) if direction == "down" else 0.0
    absolute_right = (
        route_end_m
        if direction == "down"
        else min(route_end_m, origin_m + rear_extent_m)
    )
    for segment in segments:
        left = max(segment.start_m, absolute_left)
        right = min(segment.end_m, absolute_right)
        if right <= left:
            continue
        if direction == "down":
            start_m = left - origin_m
            end_m = right - origin_m
        else:
            start_m = origin_m - right
            end_m = origin_m - left
        value = -segment.value if negate_value else segment.value
        mapped.append(Segment(start_m, end_m, value))
    return sorted(mapped, key=lambda segment: segment.start_m)


def load_train_config(
    project_root: Path,
    weight_key: str,
    initial_position_km: float,
    direction: str,
) -> TrainConfig:
    if weight_key not in SUPPORTED_WEIGHT_KEYS:
        raise ValueError(f"Unsupported train weight configuration: {weight_key}")
    if direction not in {"up", "down"}:
        raise ValueError(f"Unsupported direction: {direction}")

    model_root = project_root / "data" / "train_model"
    line_root = project_root / "data" / "data_line"
    locomotive = _load_locomotive(model_root / "locomotives.csv")
    vehicles = _load_vehicles(model_root / "vehicles.csv")
    consist = _load_consist(model_root / "consist.csv", weight_key)
    grades = _read_line_segments(line_root / "line_grade.xlsx", "grade")
    curves = _read_line_segments(line_root / "line_rad.xlsx", "curve")
    limits = _read_line_segments(line_root / "speed_limit.xlsx", "speed")
    line_end_m = _line_end_m(line_root, [grades, curves, limits])
    origin_m = float(initial_position_km) * 1000.0
    if not 0.0 <= origin_m <= line_end_m:
        raise ValueError(f"Initial position is outside line range: 0..{line_end_m / 1000.0:.3f} km")

    remaining_m = line_end_m - origin_m if direction == "down" else origin_m
    train_length_m = 0.0
    for item in consist:
        params = locomotive if item.role == "locomotive" else vehicles[item.vehicle_id]
        train_length_m += params.length_m * item.quantity
    return TrainConfig(
        locomotive=locomotive,
        vehicles=vehicles,
        consist=consist,
        grades=_map_segments(
            grades,
            origin_m,
            line_end_m,
            direction,
            train_length_m,
            negate_value=direction == "up",
        ),
        curves=_map_segments(curves, origin_m, line_end_m, direction, train_length_m),
        speed_limits=_map_segments(limits, origin_m, line_end_m, direction, train_length_m),
        route_end_m=remaining_m,
        weight_key=weight_key,
        direction=direction,
        origin_position_m=origin_m,
    )
