"""
牵引力模型（提取自 NeTrainSim Locomotive::getTractiveForce 与 getHyperbolicThrottleCoef）。

牵引力受两个约束：
1. 功率约束：F = P_eff / v，其中 P_eff = 传动效率 * throttle * maxPower
2. 粘着约束：F <= frictionCoef * mass_kg * g

throttle（0~1）由双曲 Sigmoid 在速度比 dv=v/v_max 上生成：
    lambda = 1 / (1 + exp(-7.82605 * (dv - 0.42606)))
随后离散化到 Nmax 档位（档位值 = (N/Nmax)^2）。
"""

import numpy as np

from .resistance import G

# NeTrainSim 的离散化档位计算公式 (N/Nmax)^2 中的 N 从 1 到 Nmax
def _discretize_throttle(lambda_cont: float, n_notches: int) -> float:
    """将连续 throttle 离散化到最近档位。"""
    if n_notches <= 0:
        return float(np.clip(lambda_cont, 0.0, 1.0))
    levels = np.array([(n / n_notches) ** 2 for n in range(1, n_notches + 1)])
    idx = int(np.argmin(np.abs(levels - lambda_cont)))
    return float(levels[idx])


def throttle_coefficient(speed_mps: float, max_speed_mps: float, n_notches: int = 8) -> float:
    """计算当前速度下允许的最大 throttle（0~1），考虑档位离散化。"""
    if max_speed_mps <= 0:
        return 1.0
    dv = speed_mps / max_speed_mps
    lam = 1.0 / (1.0 + np.exp(-7.82605 * (dv - 0.42606)))
    lam = float(np.clip(lam, 0.0, 1.0))
    return _discretize_throttle(lam, n_notches)


def tractive_force(
    max_power_kw: float,
    transmission_efficiency: float,
    throttle: float,
    speed_mps: float,
    mass_t: float,
    friction_coef: float = 0.9,
    max_tractive_n: float = None,
) -> float:
    """
    机车牵引力（牛顿）。

    Args:
        max_power_kw: 最大功率（千瓦）
        transmission_efficiency: 传动效率
        throttle: 手柄 throttle（0~1）
        speed_mps: 当前速度（米/秒）
        mass_t: 机车总重（公吨）
        friction_coef: 轮轨摩擦系数
        max_tractive_n: 可选最大牵引力上限（牛顿），覆盖粘着约束

    Returns:
        牵引力（牛顿）
    """
    f1 = friction_coef * mass_t * 1000.0 * G  # 粘着极限
    if max_tractive_n is not None:
        f1 = min(f1, max_tractive_n)

    if speed_mps <= 1e-6:
        return f1  # 静止时按粘着极限，与 NeTrainSim 一致

    p_eff = transmission_efficiency * throttle * max_power_kw * 1000.0  # W
    f_power = p_eff / speed_mps
    return float(min(f_power, f1))
