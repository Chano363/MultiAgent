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
    """车钩缓冲器模型参数（MT-2 摩擦式迟滞模型，容嘉欣2025 速度法 + fl/fu 查表）。

    【2026-10-11 装载缓释曲线重建 — 容嘉欣2025 速度法】阻抗形状改由
    容嘉欣2025 图4(b) 货车 MT-2 迟滞曲线（fl/fu 数字化查表）+ 速度法
    sign(Δv) 选支承担（见 coupler.py 模块头），废止「预压+线性刚度±Stribeck」
    解析式——旧式在准静态 0.01 m/s 加载下摩擦只剩 19.7%（tanh 方向因子 ×
    Stribeck 双重削减），迟滞环面积仅为参考的 1/5.3，车钩"太滑"。
    字段影响：
    - stiffness → 文献表的**全局刚度增益**（默认基值 1.89e7 = 增益 1.0，
      逐字复现文献曲线）；
    - friction_v_eps → 速度法方向切换平滑带宽，默认收窄 0.05 → 0.002 m/s
      （准静态 0.01 m/s 加载即达 99.99% 分支分离）；
    - preload_n / friction_n / friction_static_n / friction_v_er /
      unload_stiffness_ratio → plant 侧已被 fl/fu 查表取代（保留字段：
      NMPC 符号代理与历史标定追溯仍引用）。
    动机与量化见 docs/logs/diagnostics/DIAGNOSTICS_2026-10.md「诊断-2026-10-11-外部反馈两问」。

    【2026-08-30 基线对齐重建】三篇文献（杨敏2023/李蔚2023/于宗泽2025）一致：
    MT-2 为弹簧摩擦式缓冲器，阻抗 = 弹性力 + 预压力 ± 库仑摩擦（迟滞环耗能）。
    原线性弹簧+线性阻尼模型缺摩擦迟滞耗能机制 → 冲击在 101 质点链中
    无损传播叠加 → 车钩力虚高约 10 倍（B基准 6634 vs 文献 634 kN）。

    阻抗幅值（于宗泽2025式(1)(2)）：
        F_mag = F0 + k·x ± μ(|v|)·FN（加载取+，卸载取−，|F| ≤ 2270 kN）
    参数由约束反推：F0=200kN（于宗泽实测）、动摩擦项 500kN（迟滞环宽度，
    落锤试验特征，对应 |v|>>v_er 的动摩擦 μd）、
    k=(2270−200−500)/0.083 ≈ 1.89e7 N/m（行程内达到最大阻抗力）。

    【2026-09-06 R0 地基改进】（于宗泽2025 明确、此前缺失的物理）：
    - A 卸载刚度软化：unload_stiffness_ratio=0.4，卸载回程弹性项 ×ratio
      （于宗泽："阻抗在卸载初期较小"；李蔚2023 加载/卸载分段线性分离）。
    - B 速度相关摩擦（Stribeck）：|v|=0 → 静摩擦 μs·FN，|v|≥v_er 线性过渡到
      动摩擦 μd·FN（于宗泽式(2)；"MT-2 运动速度越慢，摩擦力越大"）。
      friction_n = 动摩擦 μd·FN（保留历史标定值 500 kN = 迟滞环锚），
      friction_static_n = 静摩擦 μs·FN（默认 1.5× 动摩擦）。
      【2026-10-11 superseded】A/B 已由容嘉欣速度法取代（见本类头部说明），
      保留字段仅为向后兼容与 NMPC 代理/历史追溯。
    - C 机车缓冲器分区：buffer_type='qkx100'（弹性胶泥，于宗泽式(3)(4)），
      月牙形两段刚度 + 速度幂律阻尼 C|v|^n（n<1，速度越快阻尼越大）。
      【2026-09-07 superseded】经 ADR（docs/records/DECISIONS.md）统一回 MT-2
      （A 范式，成熟论文"分车型归一对"），QKX100 实现已彻底移除，本文档该历史
      项仅作文献/决策追溯保留。
    """

    stiffness: float = 1.89e7
    """缓冲器弹性系统总刚度（N/m）。【2026-10-11 起 = 文献表全局增益】
    增益 = stiffness / 1.89e7，默认基值 → 逐字复现容嘉欣图4(b) fl/fu 曲线；
    E4-H 异构扰动它 = 整体阻抗强弱 ±15%。"""
    preload_n: float = 2.0e5
    """缓冲器预压力 F0（牛顿）。MT-2 实测约 200 kN（于宗泽2025）。
    【2026-10-11 起 plant 侧由 fl/fu 表承担（预压效果已含在 fl 曲线形态内），
    本字段仅 NMPC 符号代理与历史标定追溯仍引用，不参与 coupler_force 计算。】"""
    friction_n: float = 5.0e5
    """动摩擦项 μd·FN（牛顿）。历史标定值 500 kN = 迟滞环宽度锚。
    【2026-10-11 起 plant 侧由 fl/fu 表承担（半宽随行程变化，非恒定），
    本字段仅 NMPC 符号代理与历史标定追溯仍引用。】"""
    friction_static_n: float = 7.5e5
    """（【R0-B Stribeck】已废止，2026-10-11 由容嘉欣速度法取代）静摩擦 μs·FN
    （牛顿）。Stribeck 幅值调制与方向因子相乘造成准静态双重削减，是装载缓释
    曲线失真根因之一；plant 侧不再使用，保留字段仅为向后兼容/NMPC 代理。"""
    friction_v_er: float = 0.2
    """（【R0-B Stribeck】已废止，2026-10-11 由容嘉欣速度法取代）动、静摩擦
    转换速度阈值（米/秒，于宗泽式(2)=杨亮亮2017式(3)）。plant 侧不再使用，
    保留字段仅为向后兼容/NMPC 代理。"""
    friction_v_eps: float = 0.002
    """速度法方向切换的 tanh 平滑带宽（米/秒）。tanh(s_e·dv/ε) 平滑近似
    sign(Δv)（容嘉欣式(2) 速度法），避免 dv=0 附近硬切换抖振。
    【2026-10-11 收窄 0.05 → 0.002】旧 0.05 下准静态加载（0.01 m/s）只有
    tanh(0.2)=19.7% 分支分离 → 摩擦名存实亡；0.002 使 0.01 m/s 即达 99.99%，
    |dv|<6 mm/s 才进入过渡带。"""
    unload_stiffness_ratio: float = 1.0
    """（【R0-A】已废止，2026-10-11 由容嘉欣速度法取代）卸载回程弹性刚度比。
    加载/卸载刚度差已由 fl/fu 两条查表曲线直接承担，本字段 plant 侧不再使用，
    保留仅为向后兼容。历史复核（=1.0、u=0.4 突破实测带）见
    docs/logs/diagnostics/DIAGNOSTICS_2026-09.md（R0 改造小节）。"""
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
    """缓冲器最大阻抗力（牛顿）。MT-2 = 2270 kN（李蔚 2023）。设为 0 禁用（向后兼容）。"""
    stroke_m: float = 0.083
    """缓冲器最大行程（米）。行程 = 83mm。

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


def sample_coupler_params(rng, base: CouplerParams = None,
                          force_scale: tuple = (0.85, 1.15)) -> CouplerParams:
    """逐车钩物理参数异构抽样（实例异构，E4-H 泛化卖点）。

    在一个车钩内独立扰动**力相关的物理参数**：stiffness/preload_n/friction_n/
    coupler_gap_m/stroke_m/rigid_stiffness_nm 各乘 [force_scale] 内的均匀抽样因子。
    关联参数随主参数同步缩放（stiffness 关联 k2 已随 QKX100 移除、friction_static_n
    随 friction_n）。布局与饱和不扰动：free_length_m（决定静止间距/编组尺度）与
    max_impulse_n（缓冲器饱和上限）保持不变，避免破坏编组布局与安全。

    【2026-10-11 fl/fu 查表后】plant 侧实际生效的扰动 = stiffness（文献表全局
    增益）/coupler_gap_m/stroke_m/rigid_stiffness_nm；preload_n/friction_n/
    friction_static_n 扰动不改变 plant 阻抗（仅 NMPC 符号代理仍引用）。

    rng：numpy random Generator（调用方须传已 seed 的 rng，如 np.random.default_rng(seed)，
    保证评估可复现；held-out 用不同 seed 即可得到训练未见参数）。
    base：None 用文献标定基值 CouplerParams()。
    """
    b = base if base is not None else CouplerParams()
    lo, hi = force_scale
    f = lambda x: float(x * rng.uniform(lo, hi))
    ff = float(rng.uniform(lo, hi))   # friction 关联因子（静摩擦同步）
    return CouplerParams(
        stiffness=f(b.stiffness),
        preload_n=f(b.preload_n),
        friction_n=ff * b.friction_n,
        friction_static_n=ff * b.friction_static_n,
        coupler_gap_m=f(b.coupler_gap_m),
        stroke_m=f(b.stroke_m),
        rigid_stiffness_nm=f(b.rigid_stiffness_nm),
        friction_v_eps=b.friction_v_eps,
        friction_v_er=b.friction_v_er,
        unload_stiffness_ratio=b.unload_stiffness_ratio,
        damping=b.damping,
        free_length_m=b.free_length_m,
        max_impulse_n=b.max_impulse_n,
    )
