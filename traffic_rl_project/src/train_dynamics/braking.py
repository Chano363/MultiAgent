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

# ------------------------------------------------------------------
# 【2026-09-02 P0-3 制动力重标定】牵规（列车牵引计算规程）常用制动模型
#
# 背景：原李蔚2023式(13)-(15)实算法（制动缸压力→闸瓦压力→实算摩擦系数）
#   量级系统性偏强 2~4 倍（SERVICE 60km/h 64 kN/车 vs 牵规/实测 ~31 kN/车），
#   直接导致：
#     - 张二田 S5（100kPa 减压、-12‰、68.4km/h）仿真 646 m << 实测 3302 m
#     - 2 万吨循环制动车钩力 2405 kN（+147%）vs 实测 1000~1800 kN
#   根因：李蔚参数（d_z=283mm、γ_z=8.5）在"缸压=减压量当量"的解释下，
#   制动缸压力被当作减压量直接喂入公式，制动力被系统性高估。
#   改用牵规 β_c 法（铁路标准算法，赵紫宁2022 实测标定，与张二田/王鼎/刘博阳
#   实测量级一致）：
#
#   常用制动  B_c = β_c(r) · φ_h(v) · K_h       （每车）
#   紧急制动  B   = φ_h(v) · K_h               （β_c = 1.0）
#   φ_h(v) = 0.322·(v+150)/(2v+150)            （牵规换算摩擦系数，v 单位 km/h）
#   β_c(r)（牵规表3-1，列车管定压 p₁=600 kPa）：
#     r=50/60/70/80/90/100/110 → 0.17/0.28/0.37/0.46/0.53/0.60/0.67
#     r>110 线性外推至 r=140（最大有效减压量）饱和 0.75（常用全制动）
#
# 换算闸瓦压力 K_h 标定（每车，kN）：
#   以赵紫宁2022 表3-5"2 万吨、50kPa 减压、50 km/h → 1541.5 kN"为单点锚：
#   ΣK_h = 1541.5 / (0.17 × φ_h(50=0.2576)) = 35197 kN
#   → 216 货车 + 2 机车等权：K_h ≈ 35197/218 ≈ 161.5 kN/车
#   （机车取与货车相同的换算闸瓦压力，占全列 2/218，影响 < 1%，见
#   docs/VALIDATION_BASELINE.md V3.5.8 诊断）
# ------------------------------------------------------------------

# 牵规常用制动系数 β_c（列车管定压 p₁=600 kPa：减压量 r kPa → β_c）
BETA_C_TABLE_KPA = {
    50: 0.17, 60: 0.28, 70: 0.37, 80: 0.46,
    90: 0.53, 100: 0.60, 110: 0.67,
}
BETA_C_SATURATION_REDUCTION_KPA = 140.0   # 货车最大有效减压量（kPa）
BETA_C_SATURATION = 0.75                  # 常用全制动饱和 β_c

# 各离散档位对应的减压量（kPa）。EMERGENCY 走独立全制动（β_c=1.0）。
BRAKE_NOTCH_REDUCTION_KPA = {
    AirBrakeNotch.MIN: 70.0,      # 最小常用（减压 ~50-70 kPa）
    AirBrakeNotch.SERVICE: 140.0, # 常用全制动（最大有效减压量）
}

# 换算闸瓦压力 K_h（kN/车），标定自赵紫宁2022表3-5（见上）。
FREIGHT_CONVERTED_SHOE_FORCE_KN = 161.5
LOCO_CONVERTED_SHOE_FORCE_KN = 161.5


def beta_c(reduction_kpa: float) -> float:
    """牵规常用制动系数 β_c（减压量 r kPa → 0~0.75）。

    r ≤ 0 → 0（无制动）；r ∈ (0,50) 线性从 0 升至 0.17；
    r ∈ [50,110] 查表线性内插；r ∈ (110,140) 线性外推至饱和 0.75；r ≥ 140 饱和。
    紧急制动（全制动，β_c=1.0）不经此函数，由调用方单独处理。
    """
    r = float(reduction_kpa)
    if r <= 0.0:
        return 0.0
    if r < 50.0:
        return BETA_C_TABLE_KPA[50] * (r / 50.0)
    if r >= BETA_C_SATURATION_REDUCTION_KPA:
        return BETA_C_SATURATION
    keys = sorted(BETA_C_TABLE_KPA)
    if r <= keys[-1]:
        i = np.searchsorted(keys, r)
        lo_k, hi_k = keys[i - 1], keys[i]
        return BETA_C_TABLE_KPA[lo_k] + (BETA_C_TABLE_KPA[hi_k] - BETA_C_TABLE_KPA[lo_k]) * (
            r - lo_k) / (hi_k - lo_k)
    return BETA_C_TABLE_KPA[keys[-1]] + (BETA_C_SATURATION - BETA_C_TABLE_KPA[keys[-1]]) * (
        r - keys[-1]) / (BETA_C_SATURATION_REDUCTION_KPA - keys[-1])


def converted_friction_coeff(v_kmh: float) -> float:
    """牵规换算摩擦系数 φ_h（赵紫宁2022 式3-2，v 单位 km/h）。"""
    return 0.322 * (v_kmh + 150.0) / (2.0 * v_kmh + 150.0)


def air_brake_force_real(
    speed_mps: float,
    notch: AirBrakeNotch,
    is_locomotive: bool = False,
    reduction_kpa: float = None,
) -> float:
    """牵规法单节制动力（牛顿）——【2026-09-02 重标定】。

    常用制动 B_c = β_c(r) · φ_h(v) · K_h；紧急制动（EMERGENCY）β_c=1.0。
    量级对照（50 km/h）：MIN(70kPa)≈15.4、SERVICE(140kPa)≈31.2、
    紧急≈41.6 kN/车 —— 与牵规/赵紫宁表3-5 一致（原李蔚法 35.3/64.2/160 偏强）。

    Args:
        speed_mps: 车速（米/秒）
        notch: 离散空气制动档位
        is_locomotive: 机车或货车（K_h 目前相同，预留区分）
        reduction_kpa: 可选连续减压量（kPa）覆盖档位默认值
            （None=按 notch 查 BRAKE_NOTCH_REDUCTION_KPA；EMERGENCY=全制动）。

    Returns:
        制动力（牛顿，正值=与运动方向相反）
    """
    if notch == AirBrakeNotch.EMERGENCY and reduction_kpa is None:
        bc = 1.0
    else:
        r = (BRAKE_NOTCH_REDUCTION_KPA.get(notch, 0.0)
             if reduction_kpa is None else float(reduction_kpa))
        bc = beta_c(r)
    if bc <= 0.0:
        return 0.0
    v_kmh = max(speed_mps * 3.6, 0.0)
    kh = (LOCO_CONVERTED_SHOE_FORCE_KN if is_locomotive
          else FREIGHT_CONVERTED_SHOE_FORCE_KN)
    return float(bc * converted_friction_coeff(v_kmh) * kh * 1000.0)  # kN → N


def air_brake_force_by_reduction(
    speed_mps: float,
    reduction_kpa: float,
    is_locomotive: bool = False,
) -> float:
    """按常用制动减压量 r（kPa）计算单节制动力（牛顿）——连续减压入口。

    用于定量复现张二田 S5（减压 100 kPa）、赵紫宁循环制动操纵序列（表 5-6，
    常见减压 50~110 kPa）等连续减压工况。
    """
    return air_brake_force_real(speed_mps, AirBrakeNotch.SERVICE,
                                is_locomotive=is_locomotive,
                                reduction_kpa=reduction_kpa)


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


# ------------------------------------------------------------------
# 【2026-09-03 B3 循环制动性能衰减】赵紫宁2022 表5-5（V3.5.4 判据 B3）
#
# 背景：长大下坡循环制动时，历史缓解时间不充分（列车管充风不足）+ 反复制动
#   抱闸（闸瓦温度升高）→ 后续制动段空气制动力发挥下降。赵紫宁 2 万吨 1+1
#   -12‰ 实车辨识（表 5-5，遗传算法标定）：
#
#       制动段   λ_s    K_s    k_s     C_β
#       1      0.24   7.61   0.008   1.379
#       2      1.55   5.26  -0.012   0.972
#       3      4.08   2.23  -0.29    0.932
#
#   C_β 为制动性能修正系数（相对牵规基准），首段 1.379 表示"精细模型相对牵规
#   基准略强"，后续段单调下降 → 循环制动效率相对首段衰减约 32%
#   （0.972/1.379=0.705、0.932/1.379=0.676，即 ~29.5%/~32.4%）。
#
# 本实现建模**段间衰减**（C_β 相对首段归一化，制动力乘子 0.705/0.676），
# 这是 B3 的主效应且参数直接来自文献实测辨识，可靠。
#
# 【诚实边界】赵紫宁式(3-6)~式(3-10) 的 P_s(t) **段内时间演化**子模型需要
#   S_tmp 闸瓦温度-时间拟合曲线（文献[50]陈旭2014），本项目未获取该曲线数据，
#   故不臆造温度参数——保留扩展点（见 cyclic_braking_degrade 注释），
#   只实现有实测数据支撑的段间 C_β 衰减。段≥3 取 0.676 保守饱和（不再继续衰减，
#   与实车"充风充分后恢复"一致）。
# ------------------------------------------------------------------

# 赵紫宁2022 表5-5 C_β 序列（相对牵规基准）
ZHAO_CBETA_SEQ = [1.379, 0.972, 0.932]
# 归一化基准 = 首段 C_β（相对首段归一，仅体现衰减；首段=1.0 不改变既有制动力）
ZHAO_CBETA_BASE = ZHAO_CBETA_SEQ[0]
# 段≥3 饱和（相对首段）：0.932/1.379
CYCLIC_DEGRADE_SATURATION = ZHAO_CBETA_SEQ[-1] / ZHAO_CBETA_BASE


def cyclic_braking_degrade(brake_segment: int) -> float:
    """第 brake_segment 次（从 1 计）空气制动段的制动力衰减乘子（≤1）。

    归一化到首段（首段=1.0，不改变既有制动力量级/全部历史验证）：
      段1 → 1.0
      段2 → 0.972/1.379 ≈ 0.705
      段3 → 0.932/1.379 ≈ 0.676
      段≥3 → 0.676（保守饱和，与实车"充风充分后恢复"一致）
    """
    if brake_segment <= 1:
        return 1.0
    if brake_segment >= len(ZHAO_CBETA_SEQ):
        return CYCLIC_DEGRADE_SATURATION
    return ZHAO_CBETA_SEQ[brake_segment - 1] / ZHAO_CBETA_BASE


# 【B3 段内时间演化扩展点（暂未启用，缺文献[50]闸瓦温度曲线 S_tmp）】
# 赵紫宁式(3-6)~式(3-10) 完整形式：
#   P_s(t) = 1 + (L_s - 1)/(1 + e^{-λ_s·(t - Q_off)·T_s})      （式3-6）
#   L_s    = K_s · (T_LastREL / T_SetREL)                      （式3-7）
#   Q_off  = k_s · S_tmp + b_s,  b_s = a0·L_s² + b0·L_s + c0   （式3-8/3-9）
#   S_tmp  = a1·e^{-b1·t} + c1·e^{-d1·t}                       （式3-10，文献[50]拟合）
# 其中 T_LastREL=上一制动段缓解时间、T_SetREL=缓解充风至标定管压所需时间、
# S_tmp=闸瓦温度曲线、λ_s/K_s/k_s=表5-5 特性参数。
# 待获取 S_tmp 拟合常数（陈旭2014）后，可在此实现段内制动力随制动时间的
# "由弱转强"演化，并与段间 C_β 衰减叠加。


# ------------------------------------------------------------------
# 【2026-09-03 L1 列尾压强梯度】刘博阳2022 L6 制动缸平衡压梯度（V3.5.6）
#
# 背景：长大下坡循环制动缓解再充风不足时，列车管沿列车存在压降 → 列尾压强
#   低于前部 → 后部制动缸平衡压低于前部（L6 实测）：
#
#     列尾压强(kPa)   后部制动缸平衡压(kPa)   前部(kPa)   后部/前部
#     585             86.5                   110.5      0.783
#     589             95.3                   ~110.5     0.863
#     593             102.7                  ~110.5     0.929
#
#   物理链（L1 机理）：列尾压强高 → 充风充分 → 后部制动缸压高 → 缓解时后部
#   制动力保留多、缓解滞后 → 前拉后拽 → 拉钩力大（列尾压强 585/589/593 →
#   拉钩力 742/1058/1337 kN，单调）。低列尾压强 → 后部制动力弱 → 缓解时后部
#   先失去制动力 → 拉钩力小。
#
# 本实现建模"沿列车的制动缸平衡压梯度"（前部满压 → 后部按 ratio 衰减，线性
# 插值），制动力乘该梯度因子。ratio=1.0（默认）→ 无梯度，向后兼容。
#
# 【诚实边界】刘博阳 L5"缓解滞后"（列尾压强高 → 后部缓解延迟 17.8~20.9s）是
#   拉钩力放大的耦合机制之一，本实现用"后部制动力弱"近似其主效应；完整建模
#   需列车管充风动态，暂不实现（保留扩展点，见下）。
# ------------------------------------------------------------------

# 刘博阳 L6 标定点：列尾压强 → 后部/前部制动缸平衡压比（线性内插用）
LIU_TAIL_PRESS_KPA = [585.0, 589.0, 593.0]
LIU_TAIL_CYL_RATIO = [0.783, 0.863, 0.929]


def tail_pressure_to_cyl_ratio(tail_pressure_kpa: float) -> float:
    """列尾压强（kPa）→ 后部/前部制动缸平衡压比（刘博阳 L6 线性内插）。"""
    if tail_pressure_kpa <= LIU_TAIL_PRESS_KPA[0]:
        return LIU_TAIL_CYL_RATIO[0]
    if tail_pressure_kpa >= LIU_TAIL_PRESS_KPA[-1]:
        return LIU_TAIL_CYL_RATIO[-1]
    return float(np.interp(tail_pressure_kpa, LIU_TAIL_PRESS_KPA, LIU_TAIL_CYL_RATIO))


def cylinder_pressure_gradient(num_vehicles: int, tail_to_head_ratio: float = 1.0) -> np.ndarray:
    """沿列车每车的制动缸平衡压系数（前部 1.0 → 后部 tail_to_head_ratio，线性插值）。

    Args:
        num_vehicles: 车辆数
        tail_to_head_ratio: 后部/前部平衡压比（默认 1.0 = 无梯度，向后兼容）

    Returns:
        shape (num_vehicles,) 的乘子，第 0 车（前部）=1.0，末车 = ratio。
    """
    if tail_to_head_ratio >= 1.0 - 1e-9:
        return np.ones(num_vehicles)
    if num_vehicles <= 1:
        return np.ones(num_vehicles)
    return np.linspace(1.0, float(tail_to_head_ratio), num_vehicles)


# 【L1 缓解滞后扩展点（暂未启用）】刘博阳 L5：列尾压强高 → 从控机车后部缓解
#   滞后 17.8~20.9s。完整实现需"列车管充风动态"（缓解后再充风时间 T_LastREL →
#   后部制动缸恢复压强的时变过程），与 B3 的 L_s（充风不足）同源。当前用
#   "后部制动力弱（静态梯度）"近似其主效应，滞后耦合暂不建模。
