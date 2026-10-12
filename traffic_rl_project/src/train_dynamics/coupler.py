"""车钩缓冲器力模型（MT-2 摩擦式迟滞，标量接口）。

【2026-10-11 装载缓释曲线重建 — 容嘉欣2025 速度法】
阻抗不再用「预压 + 线性刚度 ± Stribeck 摩擦」解析式，改为直接查
容嘉欣2025《更大牵引质量重载列车动力学建模与仿真分析》（机械 52(7):57-64）
图4(b) 货车 MT-2 缓冲器迟滞特性曲线的数字化 fl（加载支）/fu（卸载支），
按该文式(2)「速度法」由相对速度方向选支：

    f0(x) = [fl(x) + fu(x)] / 2              （Δv=0 基准曲线）
    f     = f0 − sign(s_e·Δv)·[fl(x) − fu(x)]/2

    加载（s_e·Δv < 0，压缩/拉伸加深）→ fl；卸载 → fu；代码中 sign 用
    tanh(s_e·dv / friction_v_eps) 平滑（ε=0.002 m/s）。

根因（旧模型为何错，见 DIAGNOSTICS_2026-10.md「诊断-2026-10-11-外部反馈两问」问②）：
旧实现把方向因子 dir_sm 乘进摩擦幅值、又叠加 Stribeck(|dv|) 衰减 —— 准静态
加载（0.01 m/s）下 tanh(0.2)≈0.197，摩擦只剩理论值 19.7%，迟滞环面积仅为
于宗泽参考的 1/5.3，车钩"太滑"→ 纵向冲动衰减不掉。速度法下摩擦幅值**不随
速度大小衰减**，只由方向选支；ε=0.002 使 0.01 m/s 准静态加载即达 99.99%
分支分离，同时 dv→0 时连续回到 f0（无硬切换）。

数字化来源与误差：PDF 第 4 页 400 dpi 渲染，按图内 500 kN / 20 mm 网格标定后
逐列追踪，覆盖校验图目视确认贴合；读数误差约 ±30 kN；fl(83 mm)=2270 kN 锚定
MT-2 额定最大阻抗（于宗泽2025/李蔚2023 表1），fu 近似过原点直线（80 mm≈699 kN）。

其余机制不变：游隙 gap + tanh 接触渐入 + 行程刚性限位 + [0, max_impulse] 封顶。
刚度参数 = 文献表的全局增益（stiffness / 1.89e7，默认 1.0 = 逐字复现文献曲线）。

与 train.py 的向量化实现 _coupler_interface_forces_vec() 数值一致。
"""

import numpy as np


# ---------------------------------------------------------------------------
# 容嘉欣2025 图4(b) 货车 MT-2 迟滞曲线（数字化读点，单位 mm / kN）
# fl = 加载支、fu = 卸载支；两支张开成月牙形，半宽随行程增大。
RONG2025_X_MM = (0, 5, 10, 15, 20, 25, 30, 35, 40, 45, 50, 55, 60, 65, 70, 75, 80, 83)
RONG2025_FL_KN = (0, 117, 332, 538, 741, 903, 1057, 1130, 1182, 1234,
                   1268, 1314, 1363, 1473, 1588, 1810, 2031, 2270)
RONG2025_FU_KN = (0, 44, 87, 120, 164, 208, 252, 301, 345, 385,
                   434, 476, 520, 564, 606, 655, 699, 725)

RONG2025_X_M = np.array(RONG2025_X_MM, dtype=float) / 1000.0
RONG2025_FL_N = np.array(RONG2025_FL_KN, dtype=float) * 1000.0
RONG2025_FU_N = np.array(RONG2025_FU_KN, dtype=float) * 1000.0
# stiffness 基值（CouplerParams.stiffness 默认）：增益归一基准，默认增益 1.0
STIFFNESS_BASE_N_PER_M = 1.89e7


def _dead_zone(x: float, gap: float) -> float:
    """车钩游隙（死区）函数：|x| ≤ gap → 0；超死区返回剩余位移（带符号）。

    对应 MT-2 模型"|e| ≤ gap 游隙内无力"，x 为相对自由位置的位移。
    gap=0（无游隙）时为恒等映射（向后兼容）。
    """
    gap = max(float(gap), 0.0)
    if abs(x) <= gap:
        return 0.0
    return x - gap if x > 0.0 else x + gap


def coupler_force(
    x_front: float,
    v_front: float,
    x_back: float,
    v_back: float,
    stiffness: float,
    damping: float,
    free_length: float,
    coupler_gap: float = 0.01,
    max_impulse: float = 2.27e6,
    preload_n: float = 2.0e5,
    friction_n: float = 5.0e5,
    friction_v_eps: float = 0.002,
    stroke_m: float = 0.083,
    rigid_stiffness_nm: float = 5.0e7,
    unload_stiffness_ratio: float = 1.0,
    friction_static_n: float = None,
    friction_v_er: float = None,
) -> float:
    """
    车钩对前车施加的纵向力（牛顿，正=向前）。MT-2 迟滞模型（查表 + 速度法）。

    Args:
        x_front, v_front: 前车参考点位置与速度（米, 米/秒）
        x_back, v_back: 后车参考点位置与速度
        stiffness: 缓冲器弹性系统总刚度（N/m）。**文献表的全局增益**：
            增益 = stiffness / 1.89e7，默认基值 → 逐字复现容嘉欣图4(b) 曲线。
        damping: （已弃用，仅为向后兼容保留，不参与计算）
        free_length: 车钩自由长度（米，决定静止间距）
        coupler_gap: 车钩间隙/游隙（米）。|e|<=gap 内无接触无力。
        max_impulse: 缓冲器最大阻抗力（牛顿），MT-2 = 2270 kN。
        preload_n: （已被 fl/fu 表取代，仅为向后兼容保留，不参与计算）
        friction_n: （已被 fl/fu 表取代，仅为向后兼容保留，不参与计算）
        friction_v_eps: 速度法方向切换的 tanh 平滑带宽（米/秒）。0.002 →
            |dv|>6 mm/s 即满分支分离（准静态 0.01 m/s 达 99.99%）。
        stroke_m: 缓冲器最大行程（米），打满后刚性限位。
        rigid_stiffness_nm: 行程限位后刚性接触刚度（N/m）。
        unload_stiffness_ratio: （已被 fl/fu 表取代，保留仅为向后兼容）
        friction_static_n: （Stribeck 已废止，保留仅为向后兼容）
        friction_v_er: （Stribeck 已废止，保留仅为向后兼容）

    Returns:
        车钩对前车的力（牛顿，正=向前）
    """
    e = (x_back - x_front) + free_length
    dv = v_front - v_back
    gap = max(coupler_gap, 1e-9)
    s_e = np.tanh(e / gap)
    d = abs(e) - gap
    contact = 0.5 * (1.0 + np.tanh(d / 0.004))
    x_el = max(d, 0.0)
    rigid = rigid_stiffness_nm * max(x_el - stroke_m, 0.0)

    # 速度法方向因子（容嘉欣式(2)）：加载 ⟺ s_e·dv < 0（压缩/拉伸加深），
    # sign(Δv) 用窄带 tanh 平滑——dv→0 连续回到中线 f0，无硬切换抖振。
    s_dv = s_e * dv
    dir_sm = np.tanh(s_dv / friction_v_eps)

    # 查文献 fl/fu 表（刚度 = 全局增益）→ 中线 f0 与半宽 half
    gain = float(stiffness) / STIFFNESS_BASE_N_PER_M
    fl_x = float(np.interp(x_el, RONG2025_X_M, RONG2025_FL_N))
    fu_x = float(np.interp(x_el, RONG2025_X_M, RONG2025_FU_N))
    f0 = 0.5 * (fl_x + fu_x) * gain
    half = 0.5 * (fl_x - fu_x) * gain

    # 阻抗幅值（可饱和部分）：接触渐入门控的选支结果，
    # 封顶于缓冲器最大阻抗力（MT-2 2270 kN）
    f_imp = contact * (f0 - dir_sm * half)
    f_imp = float(np.clip(f_imp, 0.0, max_impulse))
    # 刚性限位力必须在饱和封顶之外独立叠加：
    # 若把 rigid 一起 clip 到 max_impulse，行程打满后限位力被封顶削弱，
    # 位移无法约束（标量/向量化两实现须保持同一约定）。
    f_mag = f_imp + rigid
    return s_e * f_mag
