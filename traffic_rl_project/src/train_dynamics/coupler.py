"""车钩缓冲器力模型（MT-2 摩擦式，标量接口）。

【2026-08-30 基线对齐重建】结构对齐三篇文献（杨敏2023/李蔚2023/于宗泽2025）：
MT-2 为弹簧摩擦式缓冲器，阻抗 = 预压力 + 弹性力 ± 库仑摩擦（迟滞环耗能）。

【2026-09-06 R0 地基改进】（于宗泽2025《重载列车车钩缓冲装置纵向动力学
精细化模型》明确、此前缺失的三项物理，见 params.py 说明）：
    A 卸载刚度软化：unload_stiffness_ratio 机制（MT-2 经式(1)复核标定 = 1.0，
      即弹性对称、迟滞全由摩擦产生）；
    B Stribeck 摩擦：μ(|v|) 静摩擦 μs·FN → |v|≥v_er 动摩擦 μd·FN（式(2)）。
    C【2026-09-07 superseded】原机车弹性胶泥（QKX100，式(3)(4) 月牙形+速度幂律
      阻尼）实现已按 ADR 彻底移除，统一回 MT-2（A 范式）。历史见
      docs/records/DECISIONS.md 与 VALIDATION_BASELINE.md「诊断-2026-09-07」。

MT-2 阻抗（加载/卸载由缓冲器运动方向 s_e·dv 判定，加载 ⟺ s_e·dv<0）：

    F_mag = contact·(F0 ± F_fric(|dv|)) + k_eff·x_el + rigid
    k_eff = k·(u + (1−u)·load_factor)，load_factor∈[0,1]（1=加载满刚度，0=卸载 u·k）
    F_on_front = sgn(e)·F_mag，|F_mag| ≤ F_max

- e = (x_back - x_front) + free_length：e>0 压缩（前车受向前力），
  e<0 拉伸（前车受向后力），|e|≤gap 游隙内无力。
- 库仑摩擦恒反对相对运动 dv = v_front - v_back（纯耗散），
  加载/卸载阻抗差形成迟滞环，每循环耗散 > 2·F_fric·x 能量。
  低速反弹时不消失（区别于线性阻尼 c·dv）——MT-2 耗能主机制。
- dv→0 时摩擦→0、k_eff→(1+u)k/2：静止阻抗介于加载/卸载曲线之间
  （于宗泽式(5) 弱锁定状态），无伪漂移。
- 参数标定：F0=200kN（于宗泽2025实测）、动摩擦 500kN（落锤迟滞环，
  3.3 m/s >> v_er 落在动摩擦区）、静摩擦 750kN=1.5×动摩擦（式(2) 标定）、
  k=(2270−200−500)/0.083≈1.89e7 N/m（行程打满恰达最大阻抗 2270 kN）。

与 train.py 的向量化实现 _coupler_interface_forces_vec() 数值一致。
"""

import numpy as np


def _dead_zone(x: float, gap: float) -> float:
    """车钩游隙（死区）函数：|x| ≤ gap → 0；超死区返回剩余位移（带符号）。

    对应 MT-2 模型"|e| ≤ gap 游隙内无力"，x 为相对自由位置的位移。
    gap=0（无游隙）时为恒等映射（向后兼容）。
    """
    gap = max(float(gap), 0.0)
    if abs(x) <= gap:
        return 0.0
    return x - gap if x > 0.0 else x + gap


def friction_magnitude_n(
    dv: float,
    friction_n: float,
    friction_static_n: float = None,
    friction_v_er: float = None,
) -> float:
    """摩擦幅值（牛顿，恒 ≥0；方向由调用方乘 −tanh(s_e·dv/ε)）。

    MT-2（Stribeck，于宗泽式(2)）：|v|=0 → μs·FN，|v|≥v_er → μd·FN，线性过渡。
    """
    abs_dv = abs(float(dv))
    # MT-2：Stribeck 线性过渡（friction_v_er<=0 或未设静摩擦 → 常数动摩擦）
    if not friction_v_er or friction_v_er <= 0.0 or friction_static_n is None:
        return friction_n
    r = min(abs_dv / friction_v_er, 1.0)
    return friction_static_n + (friction_n - friction_static_n) * r


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
    friction_v_eps: float = 0.05,
    stroke_m: float = 0.083,
    rigid_stiffness_nm: float = 5.0e7,
    unload_stiffness_ratio: float = 1.0,
    friction_static_n: float = None,
    friction_v_er: float = None,
) -> float:
    """
    车钩对前车施加的纵向力（牛顿，正=向前）。MT-2 迟滞模型。

    Args:
        x_front, v_front: 前车参考点位置与速度（米, 米/秒）
        x_back, v_back: 后车参考点位置与速度
        stiffness: 缓冲器弹性系统总刚度（N/m，加载第一段）
        damping: （已弃用，仅为向后兼容保留，不参与计算）
        free_length: 车钩自由长度（米，决定静止间距）
        coupler_gap: 车钩间隙/游隙（米）。|e|<=gap 内无接触无力。
        max_impulse: 缓冲器最大阻抗力（牛顿），MT-2 = 2270 kN。
        preload_n: 缓冲器预压力 F0（牛顿），MT-2 实测约 200 kN。
        friction_n: 动摩擦项 μd·FN（牛顿），迟滞环半宽。
        friction_v_eps: 摩擦方向平滑速度阈值（米/秒）。
        stroke_m: 缓冲器最大行程（米），打满后刚性限位。
        rigid_stiffness_nm: 行程限位后刚性接触刚度（N/m）。
        unload_stiffness_ratio: 【R0-A】卸载回程弹性刚度比（MT-2 文献标定 = 1.0，见 params.py）。
        friction_static_n: 【R0-B】静摩擦 μs·FN（None → 1.5×friction_n）。
        friction_v_er: 【R0-B】动静摩擦转换阈值（None → 0.2 m/s；0 = 禁用）。

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

    # 加载/卸载方向因子：loading ⟺ s_e·dv<0（压缩加深或拉伸加深）。
    # load_factor→1 加载、→0 卸载、dv=0 时 0.5（静止阻抗介于两曲线之间，
    # 于宗泽式(5) 弱锁定），与摩擦共用同一 tanh 平滑，无硬切换。
    s_dv = s_e * dv
    dir_sm = np.tanh(s_dv / friction_v_eps)
    load_factor = 0.5 * (1.0 - dir_sm)

    # 【R0-A】卸载刚度软化：k_eff = k·(u + (1−u)·load_factor)
    # （加载 load_factor=1 → 满刚度；卸载 → u·k；静止 0.5 → (1+u)k/2）
    u = float(np.clip(unload_stiffness_ratio, 0.0, 1.0))
    k_eff = stiffness * (u + (1.0 - u) * load_factor)
    k_term = k_eff * x_el

    # 摩擦幅值按 Stribeck，方向反对相对运动
    if friction_static_n is None:
        friction_static_n = 1.5 * friction_n
    if friction_v_er is None:
        friction_v_er = 0.2
    fric_amp = friction_magnitude_n(dv, friction_n, friction_static_n, friction_v_er)
    fric_mag = -fric_amp * dir_sm
    # 【对齐 2026-08-30 向量化修复】刚性限位力必须在饱和封顶之外独立叠加：
    # 若把 rigid 一起 clip 到 max_impulse，行程打满后限位力被封顶削弱，
    # 位移无法约束（此前标量/向量化两实现不一致，本测试链发现）。
    f_imp = contact * (preload_n + fric_mag) + k_term
    f_imp = float(np.clip(f_imp, 0.0, max_impulse))
    f_mag = f_imp + rigid
    return s_e * f_mag
