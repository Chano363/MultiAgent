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
    """车钩缓冲器模型参数（MT-2 摩擦式迟滞模型，于宗泽2025式(1)结构）。

    【2026-08-30 基线对齐重建】三篇文献（杨敏2023/李蔚2023/于宗泽2025）一致：
    MT-2 为弹簧摩擦式缓冲器，阻抗 = 弹性力 + 预压力 ± 库仑摩擦（迟滞环耗能）。
    原线性弹簧+线性阻尼模型缺摩擦迟滞耗能机制 → 冲击在 101 质点链中
    无损传播叠加 → 车钩力虚高约 10 倍（B基准 6634 vs 文献 634 kN）。

    阻抗幅值（于宗泽2025式(1)(2)）：
        F_mag = F0 + k·x ± μ·FN（加载取+，卸载取−，|F| ≤ 2270 kN）
    参数由约束反推：F0=200kN（于宗泽实测）、摩擦项 500kN（迟滞环宽度，
    卸载曲线≈加载曲线一半，孙树磊/落锤试验特征）、
    k=(2270−200−500)/0.083 ≈ 1.89e7 N/m（行程内达到最大阻抗力）。
    """

    stiffness: float = 1.89e7
    """缓冲器弹性系统总刚度（N/m）。k=(F_max−F0−F_fric)/stroke，
    使缓冲器在 83mm 行程打满时恰达 2270 kN 最大阻抗力。"""
    preload_n: float = 2.0e5
    """缓冲器预压力 F0（牛顿）。MT-2 实测约 200 kN（于宗泽2025：
    "精细化模型中采用的 MT-2 型缓冲器模型设置了约 200 kN 的预压力"）。
    接触即有阻抗（摩擦楔块预压缩），是列车尾部车钩力的重要来源。"""
    friction_n: float = 5.0e5
    """库仑摩擦项 μ·FN（牛顿）。MT-2 弹簧摩擦式的摩擦迟滞力幅值，
    加载/卸载阻抗差 = 2×此值。取 500 kN（落锤试验迟滞环宽度量级）。
    这是主要冲击耗能机制：恒反对相对运动，低速时不像线性阻尼那样消失。"""
    friction_v_eps: float = 0.05
    """摩擦静/动切换速度阈值（米/秒）。tanh 平滑近似 sign(dv)，
    避免 stick-slip 硬切换的数值抖动（于宗泽式(2) 的 ver）。"""
    damping: float = 5.0e4
    """（已弃用）线性阻尼（N·s/m）。被 friction_n 库仑摩擦取代，
    保留字段仅为向后兼容，新模型不再使用。"""
    free_length_m: float = 12.0
    """车钩自由长度（两车参考点间距，米，决定静止间距）。

    【bug修复 2026-08-20】由 1.0 修正为 12.0（对应 C80 货车车长，物理车钩间距）。
    原值 1.0 导致位置排列严重压缩（100 车仅占 100m，真实列长应 ~1212m），
    编队 reset 中 train_len≈100m → 3 列总长仅 ~667m（真实应 ~4km），
    各列在坡度剖面上被压在一个点，"相位天然错开"物理上无法发生。
    修正后列内跨度 ~1212m，编队总长 ~4km，与真实尺度一致。

    注：车钩力计算 e=(pos差)+free_length_m 在静止时 =0 仍自洽（自动适配）；
    制动传播延迟用 length_m（真实车长）计算，不受此值影响。
    """
    coupler_gap_m: float = 0.01
    """车钩间隙/游隙死区（米）。0 表示无死区（纯线性弹簧）。
    死区内 |e|<=gap 不产生弹簧力，只有阻尼；间隙越大→车钩力峰值越大。
    默认 0.01m 对应杨敏论文研究的间隙量级。"""
    max_impulse_n: float = 2.27e6
    """缓冲器最大阻抗力（牛顿）。真实重载货车缓冲器 MT-2 = 2270 kN（李蔚 2023），
    机车 QKX100 = 2500 kN。设为 0 禁用（向后兼容）。"""
    stroke_m: float = 0.083
    """缓冲器最大行程（米）。MT-2 / QKX100 行程 = 83mm。

    【2026-08-30 标准 LTD 重构】真实缓冲器行程是硬限位：位移超过行程后
    金属接触，刚度剧增（几乎不可压缩）。原 tanh 软饱和只封顶力、不限位位移，
    导致列车在制动力差下被"慢慢拉开"（实测车钩位移漂移到 23.9 m）→
    位置发散。加行程限位后：|e|<=stroke 时按阻抗特性（软饱和逼近 F_max），
    |e|>stroke 时刚性限位力剧增，位移被约束在行程内。
    """
    rigid_stiffness_nm: float = 5.0e7
    """行程限位后的刚性接触刚度（N/m）。约为正常阻抗刚度（5e6）的 10 倍，
    模拟缓冲器打满后的金属接触（位移被约束在行程内）。
    不宜过大（如 1e9），否则 Newmark 迭代对剧增力发散产生 NaN。"""


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
