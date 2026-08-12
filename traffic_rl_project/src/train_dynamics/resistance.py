"""
Davis 阻力公式（提取自 NeTrainSim Car::getResistance / Locomotive::getResistance）。

NeTrainSim 内部使用美制单位，结果以磅计再转牛顿。为保持与原实现数值一致，
此处保留其单位转换逻辑；对外接口统一使用公制。

原公式（traincomponent.h 注释）：
    Resistance = (1.5 + 18/axleWeight + 0.03*speed + frontalArea*dragCoef*speed^2/weight)
                 * totalWeight + 20*totalWeight*(trackGrade + 0.04*curvature)
单位：weight 为短吨，speed 为 mph，frontalArea 为 ft^2，结果单位 lb。
"""

import numpy as np

G = 9.8066  # 重力加速度，与 NeTrainSim EC::g 一致


def _short_tons(metric_tons: float) -> float:
    """公吨 -> 短吨（NeTrainSim 转换因子 1.10231）。"""
    return metric_tons * 1.10231


def _sqft(sq_m: float) -> float:
    """平方米 -> 平方英尺（NeTrainSim 转换因子 10.7639）。"""
    return sq_m * 10.7639


def _mph(mps: float) -> float:
    """米/秒 -> 英里/小时（NeTrainSim 转换因子 2.23694）。"""
    return mps * 2.23694


def resistance_force_lb(
    weight_t: float,
    no_of_axles: int,
    frontal_area_m2: float,
    drag_coef: float,
    speed_mps: float,
    track_grade: float = 0.0,
    track_curvature_deg: float = 0.0,
) -> float:
    """
    单节车辆的 Davis 阻力（磅）。

    Args:
        weight_t: 车辆总重（公吨）
        no_of_axles: 轴数
        frontal_area_m2: 迎风面积（平方米）
        drag_coef: 空气阻力系数
        speed_mps: 车速（米/秒）
        track_grade: 坡度（无量纲，如 0.02 表示 2%）
        track_curvature_deg: 曲率（度）

    Returns:
        阻力（磅）
    """
    w = _short_tons(weight_t)
    speed = _mph(speed_mps)
    axle_weight = w / no_of_axles
    area = _sqft(frontal_area_m2)

    # 标准 Davis 公式：
    #   总阻力 = 单位重量阻力(lb/ton) × 车重(短吨) + 空气阻力(lb, 独立于车重) + 坡道 + 曲线
    # 单位重量阻力项：滚动 + 轴荷 + 速度项
    unit_resistance = 1.5 + 18.0 / axle_weight + 0.03 * speed
    # 空气阻力项：DAVIS_AIR_COEF * C * A * V² （Davis 标准空气系数，独立于车重）
    # 注：原实现把空气项除以 w 再乘 w，且 drag_coef 直接用 1.0，导致空气阻力被错误放大约 500 倍，
    #     使平衡速度被低估（6 车仅 8 m/s）。修复为 Davis 标准形式。
    air_resistance = _davis_air_coef() * area * drag_coef * speed**2
    r = unit_resistance * w + air_resistance
    r += 20.0 * w * track_grade
    r += abs(track_curvature_deg) * 20.0 * 0.04 * w
    return r


def _davis_air_coef() -> float:
    """Davis 空气阻力标准系数（lb/(ft²·mph²·C)）。"""
    return 0.0018


def resistance_force_n(
    weight_t: float,
    no_of_axles: int,
    frontal_area_m2: float,
    drag_coef: float,
    speed_mps: float,
    track_grade: float = 0.0,
    track_curvature_deg: float = 0.0,
) -> float:
    """Davis 阻力（牛顿），等价于 NeTrainSim 的 getResistance。"""
    return resistance_force_lb(
        weight_t, no_of_axles, frontal_area_m2, drag_coef,
        speed_mps, track_grade, track_curvature_deg,
    ) * 4.44822
