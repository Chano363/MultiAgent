"""
制动力模型（提取自 NeTrainSim + 重载列车空气制动/电制动扩展）。

空气制动：
    制动闸瓦摩擦系数采用 Karwatzki 模型（NeTrainSim energyconsumption.cpp）：
        cast iron:     mu = 0.6 * (v_kmh + 100) / (5*v_kmh + 100)
        composition:   mu = 0.36 * (v_kmh + 150) / (2*v_kmh + 150)
    单节车辆空气制动力（traincomponent.cpp getBrakingForce）：
        F = brakedWeightRatio * mass_kg * g * mu(v)
    其中 brakedWeightRatio 为制动重量比（机车 0.9，货车 0.6，煤水车 0.7）。

    空气制动为**离散档位**（EB/SB），且沿车列以有限制动波速传播，
    导致后部车辆制动力施加存在延迟 —— 这是纵向冲动（车钩力）的主要来源。

电制动（机车再生/电阻制动）：
    为**连续可调**制动力，仅机车具备，与速度相关：
        F_ED = min(k_ed * throttle_ed * M * g, P_ed / v, mu_ed * M * g)
    电制动不向邻车传播，即时施加于机车本身。
"""

from enum import Enum

import numpy as np

from .resistance import G


class BrakeShoeType(Enum):
    CAST_IRON = "cast_iron"
    COMPOSITION = "composition"


class AirBrakeNotch(Enum):
    """离散空气制动档位。"""

    RELEASE = "release"          # 缓解（无制动）
    MIN = "min"                  # 最小常用制动
    SERVICE = "service"          # 常用制动（全）
    EMERGENCY = "emergency"      # 紧急制动（EB）


# 各离散档位对应的制动输出系数（相对最大制动力）
AIR_BRAKE_RATIO = {
    AirBrakeNotch.RELEASE: 0.0,
    AirBrakeNotch.MIN: 0.2,
    AirBrakeNotch.SERVICE: 0.75,
    AirBrakeNotch.EMERGENCY: 1.0,
}


def brake_shoe_friction(speed_mps: float, shoe: BrakeShoeType = BrakeShoeType.CAST_IRON) -> float:
    """Karwatzki 制动闸瓦摩擦系数（输入速度 m/s）。"""
    v_kmh = speed_mps * 3.6
    if shoe == BrakeShoeType.COMPOSITION:
        return 0.36 * (v_kmh + 150.0) / (2.0 * v_kmh + 150.0)
    # 默认 cast iron
    return 0.6 * (v_kmh + 100.0) / (5.0 * v_kmh + 100.0)


def max_air_brake_force_n(
    mass_t: float,
    speed_mps: float,
    braked_weight_ratio: float = 0.6,
    shoe: BrakeShoeType = BrakeShoeType.CAST_IRON,
) -> float:
    """单节车辆空气制动最大制动力（牛顿，正=减速方向）。"""
    mu = brake_shoe_friction(speed_mps, shoe)
    return float(braked_weight_ratio * mass_t * 1000.0 * G * mu)


def air_brake_force_n(
    mass_t: float,
    speed_mps: float,
    notch: AirBrakeNotch,
    braked_weight_ratio: float = 0.6,
    shoe: BrakeShoeType = BrakeShoeType.CAST_IRON,
) -> float:
    """
    单节车辆空气制动力（牛顿，离散档位）。

    Args:
        mass_t: 车辆总重（公吨）
        speed_mps: 车速（米/秒）
        notch: 离散空气制动档位（AirBrakeNotch）
        braked_weight_ratio: 制动重量比
        shoe: 闸瓦类型

    Returns:
        制动力（牛顿，正值表示与运动方向相反）
    """
    if notch == AirBrakeNotch.RELEASE:
        return 0.0
    ratio = AIR_BRAKE_RATIO.get(notch, 0.0)
    return max_air_brake_force_n(mass_t, speed_mps, braked_weight_ratio, shoe) * ratio


def braking_force(
    mass_t: float,
    speed_mps: float,
    brake_notch: float,
    braked_weight_ratio: float = 0.6,
    shoe: BrakeShoeType = BrakeShoeType.CAST_IRON,
) -> float:
    """
    单节车辆制动力（牛顿，兼容旧接口，brake_notch ∈ [0,1] 连续映射）。

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


def electric_brake_force_n(
    mass_t: float,
    speed_mps: float,
    throttle_ed: float,
    max_power_kw: float = 9600.0,
    transmission_efficiency: float = 0.85,
    friction_coef: float = 0.9,
    max_ed_ratio: float = 0.85,
) -> float:
    """
    机车电制动（再生/电阻）制动力（牛顿，连续可调，仅机车）。

    电制动受功率与粘着双重约束，且最大制动力约为牵引粘着极限的 max_ed_ratio 倍。

    Args:
        mass_t: 机车总重（公吨）
        speed_mps: 车速（米/秒）
        throttle_ed: 电制动指令（0~1，连续）
        max_power_kw: 机车最大电制动功率（千瓦）
        transmission_efficiency: 传动效率
        friction_coef: 轮轨摩擦系数
        max_ed_ratio: 电制动相对粘着极限的比例上限

    Returns:
        电制动力（牛顿，正值表示与运动方向相反）
    """
    if throttle_ed <= 0.0:
        return 0.0
    throttle_ed = float(np.clip(throttle_ed, 0.0, 1.0))
    # 粘着极限（电制动受轮轨粘着限制）
    adhesion_limit = friction_coef * mass_t * 1000.0 * G
    f_limit = adhesion_limit * max_ed_ratio
    if speed_mps <= 1e-6:
        return f_limit * throttle_ed  # 静止时按粘着极限
    # 功率约束：P_ed / v
    p_eff = transmission_efficiency * throttle_ed * max_power_kw * 1000.0  # W
    f_power = p_eff / speed_mps
    return float(min(f_power, f_limit))


# ------------------------------------------------------------------
# 【2026-08-30 基线对齐】实算法制动力（李蔚2023式(13)-(15) + 表2参数，
# 制动缸稳态压力取周占松2026实测：常用全制动~140kPa、紧急~470kPa）
#
# 每块闸瓦压力 K = (π/4)·d_z²·P_z·η_z·γ_z·(n_z/n_k)·1e-6   [kN]
# 高摩合成闸瓦（货车）实算摩擦系数：
#   φ_k1 = 0.481·(K+200)/(4K+200)·(3v+150)/(2v+150)
# 机车合成闸片（盘形制动）：
#   φ_k2 = 0.441·(K+200)/(4K+200)·(3v+150)/(2v+150)
# 单节制动力 F_B = n_k · K · φ   [kN]
#
# 校验（60km/h）：
#   C80 常用全制动 → 64.3 kN/车（a≈0.64 m/s²）；紧急 → 160 kN（a≈1.6）
#   HXD2 常用全制动 → 89 kN/台；紧急 → 248 kN
# ------------------------------------------------------------------

# 各档位制动缸稳态压力（kPa）。常用全制动=列车管减压170kPa（李蔚β_c口径
# 的稳态当量），紧急制动=470kPa（周占松2026实测）。
BRAKE_CYLINDER_PRESSURE_KPA = {
    AirBrakeNotch.MIN: 70.0,        # 最小常用（减压~50-70kPa）
    AirBrakeNotch.SERVICE: 140.0,   # 常用全制动（减压170kPa 稳态）
    AirBrakeNotch.EMERGENCY: 470.0, # 紧急制动
}

# 制动系统参数（李蔚2023表2）：
#   (制动缸直径 d_z mm, 传动效率 η_z, 制动倍率 γ_z, 制动缸数 n_z, 闸瓦数 n_k, 摩擦系数前置项)
_FREIGHT_BRAKE_PARAMS = (283.0, 0.9, 8.5, 2, 8, 0.481)    # C80 高摩合成闸瓦
_LOCO_BRAKE_PARAMS = (254.0, 0.9, 2.41, 12, 24, 0.441)    # HXD 机车盘形制动


def air_brake_force_real(
    speed_mps: float,
    notch: AirBrakeNotch,
    is_locomotive: bool = False,
) -> float:
    """实算法单节制动力（牛顿）——李蔚2023式(13)-(15)，基线对齐标准。

    替代简化映射 air_brake_force_n（braked_weight_ratio 口径），量级
    与文献一致：C80 常用全制动 64 kN/车（原简化映射给 106 kN，偏大
    1.66 倍，直接导致车钩力准静态分量同比例虚高）。

    Args:
        speed_mps: 车速（米/秒）
        notch: 离散空气制动档位
        is_locomotive: 机车（盘形制动+合成闸片参数）或货车（闸瓦制动）

    Returns:
        制动力（牛顿，正值=与运动方向相反）
    """
    p_kpa = BRAKE_CYLINDER_PRESSURE_KPA.get(notch, 0.0)
    if p_kpa <= 0.0:
        return 0.0
    d_z, eta_z, gamma_z, n_z, n_k, c_phi = (
        _LOCO_BRAKE_PARAMS if is_locomotive else _FREIGHT_BRAKE_PARAMS
    )
    # 每块闸瓦压力（kN）
    k_shoe = (
        (np.pi / 4.0) * d_z * d_z * p_kpa * eta_z * gamma_z
        * (n_z / n_k) * 1e-6
    )
    v_kmh = max(speed_mps * 3.6, 0.0)
    phi = (
        c_phi * (k_shoe + 200.0) / (4.0 * k_shoe + 200.0)
        * (3.0 * v_kmh + 150.0) / (2.0 * v_kmh + 150.0)
    )
    return float(n_k * k_shoe * phi * 1000.0)   # kN → N


def notch_from_throttle(throttle: float) -> AirBrakeNotch:
    """将连续负动作（-1~0）映射为离散空气制动档位。

    Args:
        throttle: 连续动作（-1~0，-1 对应紧急制动）

    Returns:
        对应的离散空气制动档位
    """
    x = float(np.clip(-throttle, 0.0, 1.0))
    if x < 1e-6:
        return AirBrakeNotch.RELEASE
    if x < 0.3:
        return AirBrakeNotch.MIN
    if x < 0.8:
        return AirBrakeNotch.SERVICE
    return AirBrakeNotch.EMERGENCY
