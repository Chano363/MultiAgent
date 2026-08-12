"""
车钩力模型（质量-弹簧-阻尼，多体扩展，NeTrainSim 无此建模）。

相邻两车通过车钩连接，车钩两端分别固定在前车尾部和后车头部。
以每节车的参考点位置建模，静止时（后车在前车后方 free_length 处）
车钩无应力，即伸长量 e = (x_back - x_front) + free_length == 0。

伸长量定义（e = (x_back - x_front) + free_length）：
- e < 0：车钩被拉长，弹簧力把两车拉向彼此 → 前车受负力（向后）
- e > 0：车钩被压紧，弹簧力把两车推开 → 前车受正力（向前）

弹簧力作用于前车：
    F_k = +k * e
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
) -> float:
    """
    车钩对前车施加的纵向力（牛顿，正=向前）。

    Args:
        x_front, v_front: 前车参考点位置与速度（米, 米/秒）
        x_back, v_back: 后车参考点位置与速度
        stiffness: 车钩刚度（N/m）
        damping: 车钩阻尼（N·s/m）
        free_length: 车钩自由长度（米）

    Returns:
        车钩对前车的力（牛顿）
    """
    e = (x_back - x_front) + free_length
    # 弹簧项：e<0 表示拉长（后车远离前车），弹簧把两车拉向彼此，
    # 前车受向后力（负）；e>0 表示压紧，前车受向前力（正）。
    # 因此弹簧力作用于前车 = +stiffness*e。
    # 阻尼项阻碍相对运动：分离速度 (v_front - v_back)，
    # 前车受阻尼力 -damping*(v_front - v_back)。
    return stiffness * e - damping * (v_front - v_back)
