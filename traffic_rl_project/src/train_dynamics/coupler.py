"""
车钩力模型（质量-弹簧-阻尼 + 车钩间隙死区，多体扩展，NeTrainSim 无此建模）。

相邻两车通过车钩连接，车钩两端分别固定在前车尾部和后车头部。
以每节车的参考点位置建模，静止时（后车在前车后方 free_length 处）
车钩无应力，即伸长量 e = (x_back - x_front) + free_length == 0。

伸长量定义（e = (x_back - x_front) + free_length）：
- e < 0：车钩被拉长，弹簧力把两车拉向彼此 → 前车受负力（向后）
- e > 0：车钩被压紧，弹簧力把两车推开 → 前车受正力（向前）

车钩间隙（死区）建模（杨敏等论文揭示的非线性规律）：
真实重载车钩存在缓冲器游隙（dead zone），在游隙范围内弹簧不产生弹性应力，
只有阻尼。仅当相对位移超过死区才产生弹簧力：

    e_eff = sign(e) * max(|e| - gap, 0)

效果：车钩间隙越大 → 达到相同弹簧力所需位移越大 → 纵向冲击时车钩力峰值越大
（近似线性增加，符合杨敏论文"车钩间隙→最大车钩力"规律）。

弹簧力作用于前车：
    F_k = +k * e_eff
阻尼力作用于前车（阻碍相对运动，分离速度为 v_front - v_back）：
    F_c = -c * (v_front - v_back)

对后车施加反作用力：F_on_back = -F_on_front
"""


def coupler_force(
    x_front: float,
    v_front: float,
    x_back: float,
    v_back: float,
    stiffness: float,
    damping: float,
    free_length: float,
    coupler_gap: float = 0.0,
) -> float:
    """
    车钩对前车施加的纵向力（牛顿，正=向前）。

    Args:
        x_front, v_front: 前车参考点位置与速度（米, 米/秒）
        x_back, v_back: 后车参考点位置与速度
        stiffness: 车钩刚度（N/m）
        damping: 车钩阻尼（N·s/m）
        free_length: 车钩自由长度（米，决定静止间距）
        coupler_gap: 车钩间隙/游隙死区（米）。默认 0（无死区，向后兼容）。
            在死区范围内 |e| <= gap 时弹簧力为 0，只保留阻尼。

    Returns:
        车钩对前车的力（牛顿）
    """
    e = (x_back - x_front) + free_length
    # 车钩间隙死区：相对位移在游隙内不产生弹簧力
    if coupler_gap > 0.0:
        e_eff = _dead_zone(e, coupler_gap)
    else:
        e_eff = e
    # 弹簧项：e_eff<0 表示拉长（后车远离前车），弹簧把两车拉向彼此，
    # 前车受向后力（负）；e_eff>0 表示压紧，前车受向前力（正）。
    # 因此弹簧力作用于前车 = +stiffness*e_eff。
    # 阻尼项阻碍相对运动：分离速度 (v_front - v_back)，
    # 前车受阻尼力 -damping*(v_front - v_back)。
    return stiffness * e_eff - damping * (v_front - v_back)


def _dead_zone(e: float, gap: float) -> float:
    """
    死区函数：|e| <= gap 时返回 0；否则返回 e 减去对应死区幅值（带符号）。

    Args:
        e: 伸长量（米）
        gap: 死区半宽（米，>0）

    Returns:
        死区处理后的有效伸长量（米）
    """
    if gap <= 0.0:
        return e
    if e > gap:
        return e - gap
    if e < -gap:
        return e + gap
    return 0.0
