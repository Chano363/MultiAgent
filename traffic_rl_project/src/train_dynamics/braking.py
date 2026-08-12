"""
制动力模型（提取自 NeTrainSim）。

制动闸瓦摩擦系数采用 Karwatzki 模型（energyconsumption.cpp）：
    cast iron:     mu = 0.6 * (v_kmh + 100) / (5*v_kmh + 100)
    composition:   mu = 0.36 * (v_kmh + 150) / (2*v_kmh + 150)

单节车辆制动力（traincomponent.cpp getBrakingForce）：
    F = brakedWeightRatio * mass_kg * g * mu(v)
其中 brakedWeightRatio 为制动重量比（机车 0.9，货车 0.6，煤水车 0.7）。
"""

from enum import Enum

from .resistance import G


class BrakeShoeType(Enum):
    CAST_IRON = "cast_iron"
    COMPOSITION = "composition"


def brake_shoe_friction(speed_mps: float, shoe: BrakeShoeType = BrakeShoeType.CAST_IRON) -> float:
    """Karwatzki 制动闸瓦摩擦系数（输入速度 m/s）。"""
    v_kmh = speed_mps * 3.6
    if shoe == BrakeShoeType.COMPOSITION:
        return 0.36 * (v_kmh + 150.0) / (2.0 * v_kmh + 150.0)
    # 默认 cast iron
    return 0.6 * (v_kmh + 100.0) / (5.0 * v_kmh + 100.0)


def braking_force(
    mass_t: float,
    speed_mps: float,
    brake_notch: float,
    braked_weight_ratio: float = 0.6,
    shoe: BrakeShoeType = BrakeShoeType.CAST_IRON,
) -> float:
    """
    单节车辆制动力（牛顿）。

    Args:
        mass_t: 车辆总重（公吨）
        speed_mps: 车速（米/秒）
        brake_notch: 制动档位（0~1，0=无制动）
        braked_weight_ratio: 制动重量比
        shoe: 闸瓦类型

    Returns:
        制动力（牛顿，正值表示与运动方向相反）
    """
    if brake_notch <= 0.0:
        return 0.0
    mu = brake_shoe_friction(speed_mps, shoe)
    max_f = braked_weight_ratio * mass_t * 1000.0 * G * mu
    return float(max_f * min(brake_notch, 1.0))
