"""
列车车辆参数定义
参考 NeTrainSim（VTTI-CSM）默认参数与重载列车常见值。
"""

from dataclasses import dataclass, field


@dataclass
class VehicleParams:
    """单节车厢（机车/货车）物理参数。重量单位为吨(t)。"""

    mass_t: float = 100.0
    """车辆总重（吨，含货物）。"""
    no_of_axles: int = 4
    """轴数。"""
    frontal_area_m2: float = 10.0
    """迎风面积（平方米）。"""
    drag_coef: float = 1.0
    """空气阻力系数（无量纲）。"""
    length_m: float = 20.0
    """车长（米）。"""
    braked_weight_ratio: float = 0.6
    """制动重量比（UIC 制动率 lambda）。"""
    is_locomotive: bool = False
    """是否为机车。"""


@dataclass
class LocomotiveParams(VehicleParams):
    """机车参数，继承车辆参数并补充牵引特性。"""

    max_power_kw: float = 9600.0
    """最大功率（千瓦）。"""
    transmission_efficiency: float = 0.85
    """传动效率。"""
    max_speed_mps: float = 30.0
    """最高速度（米/秒）。"""
    n_notches: int = 8
    """牵引手柄档位数。"""
    is_locomotive: bool = True
    braked_weight_ratio: float = 0.9


@dataclass
class CouplerParams:
    """车钩模型参数（质量-弹簧-阻尼 + 车钩间隙死区）。"""

    stiffness: float = 5.0e6
    """车钩纵向刚度（N/m）。"""
    damping: float = 5.0e4
    """车钩纵向阻尼（N·s/m）。"""
    free_length_m: float = 1.0
    """车钩自由长度（两车参考点间距，米，决定静止间距）。"""
    coupler_gap_m: float = 0.01
    """车钩间隙/游隙死区（米）。0 表示无死区（纯线性弹簧）。
    死区内 |e|<=gap 不产生弹簧力，只有阻尼；间隙越大→车钩力峰值越大。
    默认 0.01m 对应杨敏论文研究的间隙量级。"""


@dataclass
class TrainConsist:
    """列车编组：按从前到后顺序排列的车辆。"""

    vehicles: list = field(default_factory=list)

    @property
    def num_vehicles(self) -> int:
        return len(self.vehicles)

    @property
    def total_mass_t(self) -> float:
        return sum(v.mass_t for v in self.vehicles)

    @property
    def locomotive_indices(self) -> list:
        return [i for i, v in enumerate(self.vehicles) if v.is_locomotive]
