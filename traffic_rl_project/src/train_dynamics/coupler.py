"""车钩缓冲器力模型（MT-2 摩擦式迟滞模型，标量接口）。

【2026-08-30 基线对齐重建】结构对齐三篇文献（杨敏2023/李蔚2023/于宗泽2025）：
MT-2 为弹簧摩擦式缓冲器，阻抗 = 预压力 + 弹性力 ± 库仑摩擦（迟滞环耗能）。

    F_mag = contact·(F0 ± F_fric) + k·x_el + rigid
    F_on_front = sgn(e)·F_mag，|F_mag| ≤ F_max

- e = (x_back - x_front) + free_length：e>0 压缩（前车受向前力），
  e<0 拉伸（前车受向后力），|e|≤gap 游隙内无力。
- 库仑摩擦恒反对相对运动 dv = v_front - v_back（纯耗散），
  加载/卸载阻抗差形成迟滞环，每循环耗散 2·F_fric·x 能量。
  低速反弹时不消失（区别于线性阻尼 c·dv）——MT-2 耗能主机制。
- 参数标定：F0=200kN（于宗泽2025实测）、F_fric=500kN（落锤试验迟滞环）、
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
) -> float:
    """
    车钩对前车施加的纵向力（牛顿，正=向前）。MT-2 摩擦式迟滞模型。

    Args:
        x_front, v_front: 前车参考点位置与速度（米, 米/秒）
        x_back, v_back: 后车参考点位置与速度
        stiffness: 缓冲器弹性系统总刚度（N/m）
        damping: （已弃用，仅为向后兼容保留，不参与计算）
        free_length: 车钩自由长度（米，决定静止间距）
        coupler_gap: 车钩间隙/游隙（米）。|e|<=gap 内无接触无力。
        max_impulse: 缓冲器最大阻抗力（牛顿），MT-2 = 2270 kN。
        preload_n: 缓冲器预压力 F0（牛顿），MT-2 实测约 200 kN。
        friction_n: 库仑摩擦项幅值（牛顿），迟滞环半宽。
        friction_v_eps: 摩擦静/动切换速度阈值（米/秒）。
        stroke_m: 缓冲器最大行程（米），打满后刚性限位。
        rigid_stiffness_nm: 行程限位后刚性接触刚度（N/m）。

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
    fric_mag = -friction_n * np.tanh(s_e * dv / friction_v_eps)
    f_mag = contact * (preload_n + fric_mag) + stiffness * x_el + rigid
    f_mag = float(np.clip(f_mag, 0.0, max_impulse))
    return s_e * f_mag
