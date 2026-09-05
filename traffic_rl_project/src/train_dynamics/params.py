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
    - C 机车缓冲器分区：buffer_type='qkx100'（弹性胶泥，于宗泽式(3)(4)），
      月牙形两段刚度 + 速度幂律阻尼 C|v|^n（n<1，速度越快阻尼越大）。
    """

    stiffness: float = 1.89e7
    """缓冲器弹性系统总刚度（N/m，加载第一段）。k=(F_max−F0−F_fric)/stroke，
    使缓冲器在 83mm 行程打满时恰达 2270 kN 最大阻抗力（加载、动摩擦）。"""
    preload_n: float = 2.0e5
    """缓冲器预压力 F0（牛顿）。MT-2 实测约 200 kN（于宗泽2025：
    "精细化模型中采用的 MT-2 型缓冲器模型设置了约 200 kN 的预压力"）。
    接触即有阻抗（摩擦楔块预压缩），是列车尾部车钩力的重要来源。"""
    friction_n: float = 5.0e5
    """动摩擦项 μd·FN（牛顿）。MT-2 弹簧摩擦式的摩擦迟滞力幅值（高速渐近值），
    加载/卸载阻抗差 ≥ 2×此值。取 500 kN（落锤试验迟滞环宽度量级，
    落锤冲击 ~3.3 m/s >> v_er，落在动摩擦区）。
    这是主要冲击耗能机制：恒反对相对运动，低速时不像线性阻尼那样消失。"""
    friction_static_n: float = 7.5e5
    """【R0-B Stribeck】静摩擦 μs·FN（牛顿，|v|→0 上界）。于宗泽式(2)：
    "MT-2 型缓冲器运动速度越慢，摩擦力越大"。默认 1.5× 动摩擦（750 kN）。
    缓解冲击（相对速度 ~0.1 m/s 量级 < v_er）处于静/动过渡区，阻抗高于
    旧常数摩擦模型 —— 这是"卸载初期阻抗较小"现象的另一面。"""
    friction_v_er: float = 0.2
    """【R0-B Stribeck】动、静摩擦之间转换速度阈值 v_er（米/秒，于宗泽式(2)）。
    |v|≥v_er 全动摩擦；|v|=0 全静摩擦；中间线性过渡。设 0 退化为常数摩擦。"""
    friction_v_eps: float = 0.05
    """摩擦方向 tanh 平滑速度阈值（米/秒）。tanh 平滑近似 sign(dv)，
    避免 stick-slip 硬切换的数值抖动（于宗泽式(2) 的 v_er 平滑对应物）。"""
    unload_stiffness_ratio: float = 1.0
    """【R0-A】卸载回程弹性刚度比（卸载刚度/加载刚度）。

    【2026-09-06 文献复核标定 = 1.0（MT-2 弹性对称）】于宗泽式(1)
    F_M = F0 + kx + sgn(v)·μF_N 对加载/卸载用**同一 k**——"阻抗在卸载初期
    较小"的机制是摩擦项翻转（+μF_N → −μF_N），不是弹性软化。经典分段线性
    构造（卸载支从 loading_max − 2F_fric 出发）数值上恰对应 u=1.0：
    F_u(83mm) = 200 + 1568 − 500 = 1268 ≈ 2270 − 2×500 kN。
    【实测带门禁】u=0.4（HANDOFF 建议值）使 1万吨循环制动峰值 +894 kN
    （1372→2266），突破王鼎 46 次 2250 kN 上限与四源 1800 kN 带，故不采用。
    机制保留为参数：QKX100 胶泥迟滞用 0.6（弹性胶泥卸载迟滞宽于纯摩擦式）。
    """
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
    # ---------------- 【R0-C】QKX100 弹性胶泥缓冲器扩展 ----------------
    # 结构 = 于宗泽2025式(3)(4)：F_Q = F_k(x) + sgn(v)·(C|v|^n + F_d + f)。
    # 文献只给结构 + 静压/落锤曲线形状（月牙形），未在正文给出拟合常数，
    # 下列数值为形状标定（约束：2500 kN@83mm、月牙形两段刚度、小压缩量
    # 阻抗 < MT-2、速度幂律阻尼 n<1），非文献拟合值 —— 使用时须知此边界。
    buffer_type: str = "mt2"
    """缓冲器类型：'mt2'（货车摩擦式，默认）或 'qkx100'（机车弹性胶泥）。"""
    k2_nm: float = 0.0
    """月牙形第二段刚度（N/m，x>knee_x_m 段）。0 = 单段刚度（MT-2）。
    QKX100 月牙形：加载初期上升快、末期变缓 → k1 > k2（凹形/软化）。"""
    knee_x_m: float = 0.02
    """两段刚度转折点（米）。"""
    viscous_c: float = 5.0e5
    """胶泥阻尼系数 C（N·s⁻ⁿ/mⁿ，于宗泽式(4) F_r = C|v|^n + F_d + f）。"""
    viscous_n_exp: float = 0.55
    """胶泥阻尼速度指数 n（0<n<1，于宗泽式(4)；"运动速度越快，胶泥的阻尼越大"）。
    落锤 3.3 m/s 时阻尼远大于运行速度 → 直角梯形；正常运行低速 → 月牙形。"""
    static_damp_n: float = 3.0e4
    """静止状态阻尼力 F_d（牛顿，于宗泽式(4)；胶泥静压仍有少量流动阻力）。"""


def qkx100_params() -> CouplerParams:
    """机车 QKX100 弹性胶泥缓冲器参数（于宗泽2025式(3)(4) 结构 + 形状标定）。

    文献锚点（硬约束）：
    - 最大阻抗 2500 kN、行程 83 mm（李蔚2023表1：机车 QKX100 / 货车 MT-2）；
    - 月牙形阻抗特性（正常运行低速）：加载初期上升快、末期变缓 → 两段刚度
      k1=6e7（60 kN/mm）> k2=2.14e7（21.4 kN/mm），F(83mm)≈2500 kN；
    - "小压缩量下的阻抗小于 MT-2"（于宗泽图9：QKX100 车钩位移明显大于 MT-2）；
    - 速度幂律阻尼 C|v|^n（n=0.55<1）+ 静止阻尼 F_d + 移动摩擦 f；
    - 加载/卸载曲线存在明显差别（静压试验，于宗泽图4）→ 卸载刚度比 0.6
      （胶泥迟滞窄于 MT-2 摩擦式）。

    标定边界：C/F_d/f/k1/k2 为形状标定值（文献未给拟合常数），量级合理性
    由 tests/test_coupler_model_refined.py 断言（2500 锚、月牙形、小压缩量 < MT-2）。
    """
    return CouplerParams(
        buffer_type="qkx100",
        stiffness=6.0e7,        # k1：第一段（0~20mm，60 kN/mm，月牙形陡升段）
        k2_nm=2.14e7,           # k2：第二段（20~83mm，21.4 kN/mm，趋缓段）
        knee_x_m=0.02,
        preload_n=1.0e5,        # 胶泥初始阻抗低（无摩擦楔块预压；UM 平台 ~50 kN 量级参考）
        friction_n=1.0e5,       # 移动摩擦力 f（式(4)）
        friction_static_n=1.0e5,   # QKX100 不用 Stribeck（阻尼随速度增大，方向相反）
        friction_v_er=0.0,         # 0 = 禁用 Stribeck 过渡
        unload_stiffness_ratio=0.6,
        max_impulse_n=2.5e6,    # 2500 kN（李蔚2023表1）
        stroke_m=0.083,
        viscous_c=5.0e5,
        viscous_n_exp=0.55,
        static_damp_n=3.0e4,
    )


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
    关联参数随主参数同步缩放：k2_nm 随 stiffness、friction_static_n 随 friction_n、
    viscous_c 独立扰动（力相关）。布局与饱和不扰动：free_length_m（决定静止
    间距/编组尺度）与 max_impulse_n（缓冲器饱和上限）保持不变，避免破坏编组
    布局与安全。buffer_type 不扰动（货车 MT-2 研究域；机车 QKX100 分区由
    TrainDynamics 按编组自动分派）。

    rng：numpy random Generator（调用方须传已 seed 的 rng，如 np.random.default_rng(seed)，
    保证评估可复现；held-out 用不同 seed 即可得到训练未见参数）。
    base：None 用文献标定基值 CouplerParams()。
    """
    b = base if base is not None else CouplerParams()
    lo, hi = force_scale
    f = lambda x: float(x * rng.uniform(lo, hi))
    fk = float(rng.uniform(lo, hi))   # stiffness 关联因子（k2 同步）
    ff = float(rng.uniform(lo, hi))   # friction 关联因子（静摩擦同步）
    return CouplerParams(
        stiffness=fk * b.stiffness,
        k2_nm=fk * b.k2_nm,
        preload_n=f(b.preload_n),
        friction_n=ff * b.friction_n,
        friction_static_n=ff * b.friction_static_n,
        viscous_c=f(b.viscous_c),
        coupler_gap_m=f(b.coupler_gap_m),
        stroke_m=f(b.stroke_m),
        rigid_stiffness_nm=f(b.rigid_stiffness_nm),
        friction_v_eps=b.friction_v_eps,
        friction_v_er=b.friction_v_er,
        unload_stiffness_ratio=b.unload_stiffness_ratio,
        static_damp_n=b.static_damp_n,
        damping=b.damping,
        free_length_m=b.free_length_m,
        max_impulse_n=b.max_impulse_n,
        buffer_type=b.buffer_type,
        knee_x_m=b.knee_x_m,
        viscous_n_exp=b.viscous_n_exp,
    )
