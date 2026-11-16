"""
线路坡度剖面建模（长大下坡场景）。

参考樊运新等《编组方式对3万吨重载列车循环制动工况纵向冲动的影响》的 3 种典型线路剖面：
- A: 长大下坡道（连续下坡，如 -10.2‰，需循环制动调速）
- B: 缓坡变陡坡（前后坡度差，如 3.6‰~9.5‰ A 型变坡）
- C: V 型坡（坡度差大，如 12.0‰~1.5‰，坡度差 ≤10.5‰）

坡度剖面由一系列 (起点位置 m, 坡度 ‰) 段组成，按列车位置实时查询每节车所在坡度。
坡度 sign 约定：正值=上坡（阻力），负值=下坡（助力）。
"""

from dataclasses import dataclass, field
from functools import cached_property
from typing import List, Optional, Tuple
import numpy as np


@dataclass
class GradeSegment:
    """一段坡道：从 start_m 到下一个段的起点，坡度为 grade_permille（‰）。"""
    start_m: float
    grade_permille: float  # 正=上坡, 负=下坡


@dataclass
class CurveSegment:
    """一段曲线：[start_m, end_m) 内曲线半径 radius_m（米）。

    【ADR-060 线路数据全量入模】来源 = 统一线路表曲线行（曲线起点/终点/半径）。
    """
    start_m: float
    end_m: float
    radius_m: float


@dataclass
class GradeProfile:
    """线路坡度剖面（分段线性）。

    Attributes:
        segments: 按起点位置升序排列的坡段列表
        limit_segments: 分段限速表（可选，None = 无表 → limit_at 返回 None，
            恒坡等其它剖面零回归）
        curve_segments: 曲线分段表（可选，None = 无表 → curve_radius_at 返回
            None，即全线直线）
    """
    segments: List[GradeSegment] = field(default_factory=list)
    # SpeedLimitSegment 定义在本文件后部（限速表常量区），用字符串注解延迟求值。
    limit_segments: Optional[List["SpeedLimitSegment"]] = None
    curve_segments: Optional[List["CurveSegment"]] = None

    def grade_at(self, position_m: float) -> float:
        """查询位置 position_m 处的坡度（无量纲，= ‰ / 1000）。"""
        if not self.segments:
            return 0.0
        # 找到 position 所在的段（最后一个 start_m <= position 的段）
        grade_permille = self.segments[0].grade_permille
        for seg in self.segments:
            if position_m >= seg.start_m:
                grade_permille = seg.grade_permille
            else:
                break
        return grade_permille / 1000.0

    @cached_property
    def _starts_and_grades(self) -> Tuple[np.ndarray, np.ndarray]:
        """坡段起点数组与坡度数组（无量纲），供批量查询用。段表构造后不变 → 缓存。"""
        starts = np.array([float(seg.start_m) for seg in self.segments], dtype=float)
        grades = np.array([float(seg.grade_permille) for seg in self.segments],
                          dtype=float) / 1000.0
        return starts, grades

    def grades_for_positions(self, positions: np.ndarray) -> np.ndarray:
        """批量查询多节车位置的坡度（返回无量纲数组）。

        【2026-10-21 性能】原实现逐点调用 `grade_at`（每步 218 次 Python 调用 + 线性扫描
        段表，实测 ~68080 次/10 步、占 cumtime 7%）→ 改为 searchsorted 向量化。

        数值语义与 `grade_at` **逐点一致**：取「最后一个 start_m <= position」的坡段；
        position 小于首段起点时沿用首段坡度（`grade_at` 的初值行为），越出末端沿用末段。
        """
        starts, grades = self._starts_and_grades
        pos = np.asarray(positions, dtype=float)
        idx = np.searchsorted(starts, pos, side='right') - 1
        np.clip(idx, 0, len(starts) - 1, out=idx)
        return grades[idx]

    # ------------------------------------------------------------------
    # 【ADR-060 线路数据全量入模】分段限速 / 曲线半径查询接口。
    # 约定：无表（limit_segments / curve_segments 为 None）时返回 None，
    # 调用方（env / 安全层 / 控制器 / 动力学）一律回退常数限速或直线（零回归）。
    # ------------------------------------------------------------------

    def limit_at(self, position_m: float) -> Optional[float]:
        """查询 position_m 处的线路限速（km/h）。

        无限速表 → None（调用方回退常数限速）；有表时取「最后一个
        start_m <= position」的段（与 grade_at 同语义），首段之前沿用首段。
        """
        if not self.limit_segments:
            return None
        limit = self.limit_segments[0].limit_kmh
        for seg in self.limit_segments:
            if position_m >= seg.start_m:
                limit = seg.limit_kmh
            else:
                break
        return float(limit)

    @cached_property
    def _curve_arrays(self) -> Optional[Tuple[np.ndarray, np.ndarray, np.ndarray]]:
        """曲线段 (起点, 终点, 半径) 数组；无表时 None。构造后不变 → 缓存。"""
        if not self.curve_segments:
            return None
        starts = np.array([seg.start_m for seg in self.curve_segments], dtype=float)
        ends = np.array([seg.end_m for seg in self.curve_segments], dtype=float)
        radii = np.array([seg.radius_m for seg in self.curve_segments], dtype=float)
        return starts, ends, radii

    def curve_radius_at(self, position_m: float) -> Optional[float]:
        """查询 position_m 处的曲线半径（米）；直线/无表 → None。

        取「最后一个 start_m <= position」的候选段，且 position 落在
        [start, end) 内才算曲线（源表曲线段存在少量过渡交叠，此语义下
        交叠区取更晚起始段，与逐段扫描一致）。
        """
        arrays = self._curve_arrays
        if arrays is None:
            return None
        starts, ends, radii = arrays
        idx = int(np.searchsorted(starts, position_m, side='right')) - 1
        if idx < 0 or position_m >= ends[idx]:
            return None
        return float(radii[idx])

    def curve_radii_for_positions(self, positions: np.ndarray) -> np.ndarray:
        """批量查询多节车位置的曲线半径（米；直线处 = +inf）。

        与 `curve_radius_at` 逐点一致（searchsorted right − 1 + 终点检查），
        供动力学每步按每车位置向量化查询曲线附加阻力。
        """
        arrays = self._curve_arrays
        pos = np.asarray(positions, dtype=float)
        if arrays is None:
            return np.full(pos.shape, np.inf)
        starts, ends, radii = arrays
        idx = np.searchsorted(starts, pos, side='right') - 1
        valid = idx >= 0
        idx_clipped = np.clip(idx, 0, len(starts) - 1)
        in_seg = valid & (pos < ends[idx_clipped])
        r = np.where(in_seg, radii[idx_clipped], np.inf)
        return r


# ---------------------------------------------------------------------------
# 樊运新 3 种典型线路剖面（预置）
# 注：坡度值参考论文量级（-10.2‰ 长大下坡等），位置为示意（可按实际线路调整）。
# 下坡为负，上坡为正。

def profile_long_downhill() -> GradeProfile:
    """A 型：长大下坡道（连续下坡 ~-10.2‰，需循环制动调速）。"""
    return GradeProfile(segments=[
        GradeSegment(0.0, -2.0),       # 起始缓坡
        GradeSegment(500.0, -10.2),    # 长大下坡（K19+731~K32+531 量级）
        GradeSegment(3000.0, -2.0),    # 出坡缓坡
    ])


def profile_gradual_to_steep() -> GradeProfile:
    """B 型：缓坡变陡坡（A 型变坡，3.6‰~9.5‰，坡度差 ~5.9‰）。"""
    return GradeProfile(segments=[
        GradeSegment(0.0, -3.6),       # 缓下坡
        GradeSegment(800.0, -9.5),     # 变陡坡（坡度差 5.9‰）
        GradeSegment(2500.0, -3.6),    # 出坡
    ])


def profile_v_shape() -> GradeProfile:
    """C 型：V 型坡（12.0‰~1.5‰，坡度差 ~10.5‰）。"""
    return GradeProfile(segments=[
        GradeSegment(0.0, -12.0),      # 陡下坡
        GradeSegment(1000.0, -1.5),    # 变缓（V 型谷底，坡度差 10.5‰）
        GradeSegment(2500.0, -12.0),   # 再变陡
    ])


def profile_shuozhou_23800() -> GradeProfile:
    """朔黄线 Longgong→Beidaniu 段 23,800m 真实剖面（Zhang2024 Algorithms 2024,17,190 Table 2）。

    这是 Zhang2024 复现用的**真实线路**，坡度在 -1.5‰~-11.4‰ 间交替变化（多段变坡），
    用于校准我们动力学能否复现其"长大下坡循环制动"结果（5 次制动、速度 40-80km/h 区间）。
    负值=下坡（与全局约定一致）。
    """
    return GradeProfile(segments=[
        GradeSegment(0.0, -1.5),        # 0–1000: -1.5
        GradeSegment(1000.0, -7.5),     # 1000–1400: -7.5
        GradeSegment(1400.0, -10.9),    # 1400–6200: -10.9
        GradeSegment(6200.0, -9.0),     # 6200–6750: -9.0
        GradeSegment(6750.0, -11.3),    # 6750–12430: -11.3
        GradeSegment(12430.0, -10.5),   # 12430–14080: -10.5
        GradeSegment(14080.0, -11.4),   # 14080–16330: -11.4
        GradeSegment(16330.0, -10.6),   # 16330–19130: -10.6
        GradeSegment(19130.0, -10.9),   # 19130–22260: -10.9
        GradeSegment(22260.0, -3.3),    # 22260–23800: -3.3
    ])


def profile_long_downhill_20km() -> GradeProfile:
    """第二长下坡剖面（20km，第二线路普适性验证）。

    与 shuozhou_23800 不同的长大下坡形态：更长（20km）但坡度更均匀（-9.5‰~-11.5‰
    交替变坡），作为"第二线路"验证协同价值对下坡长度的依赖性（短剖面如 long_downhill
    3km 时 M3 独立也能保持间距，长剖面下 M3 独立控制长距离后追尾，体现协同价值）。
    形态依据：大秦线/朔黄线长大下坡多段变坡特征，坡度差 ≤10.5‰（樊运新约束）。
    """
    return GradeProfile(segments=[
        GradeSegment(0.0, -2.0),        # 0–1000: 起始缓坡
        GradeSegment(1000.0, -9.5),     # 1000–6000: 长大下坡段1
        GradeSegment(6000.0, -11.0),    # 6000–12000: 陡坡段
        GradeSegment(12000.0, -10.0),   # 12000–16000: 下坡段
        GradeSegment(16000.0, -11.5),   # 16000–20000: 最陡段（追尾压力区）
        GradeSegment(20000.0, -2.0),    # 20000: 出坡缓坡
    ])


def profile_long_downhill_35km() -> GradeProfile:
    """第三长下坡剖面（≈35km，**全新设计，标注 synthetic**）。

    学长建议验证 30-40km 长大下坡；现有 shuozhou_23800（真实 23.8km）与
    long_downhill_20km（设计 20km）均不足。故新建设计剖面 ≈35km（35000m）：
    连续长大下坡 -9.5‰~-11.5‰ 多段变坡（坡度差 ≤10.5‰，樊运新约束），
    长鼻段制造持续追尾压力，用于第三线路 / 外推 / 压力验证。

    ⚠ 语义标注：**synthetic（设计/外推验证线，非真实线路纵断面）**，不冒充真实数据；
    用途 = 验证"长坡长度↑ → M3 独立追尾压力↑ → 协同价值↑"的趋势与外推鲁棒性。
    坡度 sign：负值=下坡（与全局一致）。
    """
    return GradeProfile(segments=[
        GradeSegment(0.0, -2.0),        # 0–1500: 起始缓坡
        GradeSegment(1500.0, -9.5),     # 1500–8000: 下坡段1
        GradeSegment(8000.0, -11.0),    # 8000–15000: 陡坡段
        GradeSegment(15000.0, -10.0),   # 15000–21000: 下坡段
        GradeSegment(21000.0, -11.5),   # 21000–28000: 最陡段（追尾压力区）
        GradeSegment(28000.0, -10.8),   # 28000–33000: 下坡段
        GradeSegment(33000.0, -7.0),    # 33000–34500: 渐缓
        GradeSegment(34500.0, -2.0),    # 34500+: 出坡缓坡
    ])


def profile_long_downhill_50km() -> GradeProfile:
    """第四长下坡剖面（≈50km，**设计/边界合成线，标注 synthetic**）。

    用途：第三线路/泛化/边界压力验证的**长侧边界点**，与 20km/35km 构成
    "长度-协同增益"的多点扫掠（短 shuozhou23.8/20km → 中 35km → 长 50km）。

    【关键设计：坡度剧变点】变坡点是纵向冲动/车钩力最凸显处（Wan2025 JVC、
    常崇义2023：前后车辆坡度阻力差 → 变坡点纵向冲动/压钩力↑）。
    - 进坡剧变点：首缀缓坡 -2‰ → 立即进入最陡 -11.5‰（坡度差 9.5‰，≤10.5‰ 樊运新约束）
    - 出坡剧变点：最陡段 -11‰ → 凸形坡出坡 -2‰（坡度差 9.0‰，缓解时拉钩力压力区）
    - 中部 -9.5~-11.5 多段缓变（差 ≤1.5‰），形成持续追尾压力长鼻段。

    ⚠ 语义标注：synthetic（设计/外推验证线，非真实线路纵断面），不冒充真实数据。
    坡度 sign：负值=下坡（与全局一致）。
    """
    return GradeProfile(segments=[
        GradeSegment(0.0, -2.0),        # 0–1500: 起始缓坡
        GradeSegment(1500.0, -11.5),    # 1500–6000: 剧变点①剧降进入最陡段（差9.5‰）
        GradeSegment(6000.0, -10.0),    # 6000–14000: 下坡段
        GradeSegment(14000.0, -11.5),   # 14000–24000: 最陡段（长鼻追尾压力区）
        GradeSegment(24000.0, -10.5),   # 24000–36000: 下坡长段
        GradeSegment(36000.0, -9.5),    # 36000–44000: 缓下中段
        GradeSegment(44000.0, -11.0),   # 44000–48000: 出坡前再陡段
        GradeSegment(48000.0, -2.0),    # 剧变点②凸形坡出坡（差9.0‰）
        GradeSegment(50000.0, -2.0),    # 50000: 出坡尾部
    ])


@dataclass
class SpeedLimitSegment:
    """一段限速：从 start_m 到下一个段的起点，限速 limit_kmh（km/h）。"""
    start_m: float
    limit_kmh: float


@dataclass
class SpeedLimitProfile:
    """线路限速剖面（分段线性，单位 km/h）。

    【来源 = 真实线路数据，非设计/合成】数据出处：同行提供的 朔黄线宁武西→北大牛
    真实线路纵断面原始数据（`simulation(1)/data_line/speed_limit.xlsx`），
    供按里程做 per-position 限速监督（ATP 安全层）使用。

    注意：当前 SafetyLayer/TrainFormationEnv 的线路限速仍是**单一标量**
    `line_speed_limit_mps`（编队训练默认 80 km/h 统一限速）。本剖面为真实限速
    数据块，**默认不启用**（启用需把安全层限速升级为按头车位置查询，会改变
    编队训练限速语义，不默认接入）。
    """
    segments: List[SpeedLimitSegment] = field(default_factory=list)

    def limit_at(self, position_m: float) -> float:
        """查询 position 处的限速（km/h），最后一段之后取最后段限速。"""
        if not self.segments:
            return 80.0
        limit = self.segments[0].limit_kmh
        for seg in self.segments:
            if position_m >= seg.start_m:
                limit = seg.limit_kmh
            else:
                break
        return limit


# 朔黄线宁武西→北大牛真实限速剖面（来源：simulation(1)/data_line/speed_limit.xlsx）
# 注意：限速值单位 km/h。与 grade 剖面同一条线路，供 per-position 限速监督用。
SHUOZHOU_REAL_SPEED_LIMIT = SpeedLimitProfile(segments=[
    SpeedLimitSegment(0.0, 45.0),        # 0.0–3865   区间限速 45 km/h（进出站区段）
    SpeedLimitSegment(3865.0, 75.0),     # 3865–23669 75
    SpeedLimitSegment(23669.0, 70.0),    # 23669–25935 70
    SpeedLimitSegment(25935.0, 60.0),    # 25935–29743 60
    SpeedLimitSegment(29743.0, 75.0),    # 29743–49527 75
    SpeedLimitSegment(49527.0, 45.0),    # 49527–53392 45（进北大牛区段）
    SpeedLimitSegment(53392.0, 75.0),    # 53392+     75
])


# ---------------------------------------------------------------------------
# 【ADR-060 线路数据全量入模】shuozhou_ningwuxi_beidaniu_49km 的分段限速与
# 曲线半径常量表（与坡度段同源：统一线路表，K15.9–65.5，0.1km 粒度）。
# 里程口径 = 相对里程 m（= (公里标 − 15.9) × 1000），与坡度段重基一致。
# 限速段边界取相邻 0.1km 行中点（行中心粒度的自然分界）；曲线段直接取
# 表中 曲线起点/终点/半径（0.1km 行重复行已去重，共 32 处，最小 R=400）。
# 提取口径由 tests/test_grade_profile.py 从 xlsx 重新读取比对把关。

SHUOZHOU_49KM_LIMIT_SEGMENTS = [
    # (start_m, limit_kmh)   km 范围
    SpeedLimitSegment(0.0, 70.0),        # K15.9–20.15  70 km/h
    SpeedLimitSegment(4250.0, 75.0),     # K20.15–39.85 75 km/h
    SpeedLimitSegment(23950.0, 70.0),    # K39.85–41.35 70 km/h
    SpeedLimitSegment(25450.0, 75.0),    # K41.35–65.5+ 75 km/h
]

SHUOZHOU_49KM_CURVE_SEGMENTS = [
    CurveSegment(980.0, 1949.0, 400.0),      # K16.880–17.849
    CurveSegment(2050.0, 2404.0, 400.0),     # K17.950–18.304
    CurveSegment(2430.0, 2772.0, 400.0),     # K18.330–18.672
    CurveSegment(3350.0, 3860.0, 800.0),     # K19.250–19.760
    CurveSegment(16620.0, 17179.0, 500.0),   # K32.520–33.079
    CurveSegment(17590.0, 17983.0, 500.0),   # K33.490–33.883
    CurveSegment(18920.0, 19785.0, 600.0),   # K34.820–35.685
    CurveSegment(21230.0, 22428.0, 1000.0),  # K37.130–38.328
    CurveSegment(22600.0, 24573.0, 500.0),   # K38.500–40.473
    CurveSegment(25000.0, 25161.0, 800.0),   # K40.900–41.061
    CurveSegment(27100.0, 27311.0, 500.0),   # K43.000–43.211
    CurveSegment(27700.0, 28353.0, 600.0),   # K43.600–44.253
    CurveSegment(28150.0, 28527.0, 1500.0),  # K44.050–44.427（与前段过渡交叠）
    CurveSegment(28700.0, 29451.0, 800.0),   # K44.600–45.351
    CurveSegment(32700.0, 33319.0, 500.0),   # K48.600–49.219
    CurveSegment(33300.0, 33925.0, 500.0),   # K49.200–49.825
    CurveSegment(34650.0, 35138.0, 600.0),   # K50.550–51.038
    CurveSegment(35500.0, 36274.0, 1000.0),  # K51.400–52.174
    CurveSegment(36500.0, 37087.0, 500.0),   # K52.400–52.987
    CurveSegment(37900.0, 38266.0, 500.0),   # K53.800–54.166
    CurveSegment(38450.0, 39119.0, 500.0),   # K54.350–55.019
    CurveSegment(39350.0, 40200.0, 500.0),   # K55.250–56.100
    CurveSegment(40150.0, 40386.0, 2000.0),  # K56.050–56.286（与前段过渡交叠）
    CurveSegment(41400.0, 42152.0, 500.0),   # K57.300–58.052
    CurveSegment(42450.0, 42793.0, 500.0),   # K58.350–58.693
    CurveSegment(43320.0, 44814.0, 500.0),   # K59.220–60.714
    CurveSegment(44800.0, 45251.0, 1000.0),  # K60.700–61.151（与前段过渡交叠）
    CurveSegment(45500.0, 46229.0, 500.0),   # K61.400–62.129
    CurveSegment(46300.0, 46883.0, 500.0),   # K62.200–62.783
    CurveSegment(47460.0, 48492.0, 500.0),   # K63.360–64.392
    CurveSegment(48420.0, 48708.0, 500.0),   # K64.320–64.608（与前段过渡交叠）
    CurveSegment(48980.0, 49516.0, 1000.0),  # K64.880–65.416
]


def profile_shuozhou_ningwuxi_beidaniu_49km() -> GradeProfile:
    """朔黄线宁武西→北大牛真实长大下坡纵断面（49.6km，**真实线路数据**）。

    【来源 = 真实线路数据，非设计/合成】取自
    `reference/simulation/data_line/朔黄铁路_完整线路信息表_表3表4补充版.xlsx`
    （`统一线路表` sheet，表头在第 2 行；宁武西 K15.9 → 北大牛 K65.5），
    0.1km 粒度里程-坡度数据合并为 50 个坡段，逐段（米）衔接自洽（脚本校验通过）。
    坡度 -1.3‰~-12.0‰ 连续变坡，属典型长大下坡循环制动剖面；该表同时被
    表4 标注为长大下坡区段（≥6‰ 且 ≥8km 判定）。

    用途：主训练真实线路剖面（长坡多段变坡下循环制动 / 车钩力守 1000kN）。
    坡度 sign：负值=下坡（与全局一致）。总长 49600m（0–49.6km，重基到 0）。

    【ADR-060】本剖面附带同源分段限速表（70/75 km/h 交替 4 段）与曲线半径表
    （32 处，R=400~2000m），供限速逐段联动（env/安全层/循环制动触发）与曲线
    附加阻力 w_r=600/(R−55) N/kN 入模；其它剖面无表 → 联动自动关闭（零回归）。
    """
    return GradeProfile(
        segments=[
            GradeSegment(0.000, -1.5),
            GradeSegment(544.500, -5.0),
            GradeSegment(1044.500, -1.3),
            GradeSegment(1594.500, -9.0),
            GradeSegment(2124.500, -10.0),
            GradeSegment(2629.500, -6.2),
            GradeSegment(3544.500, -10.2),
            GradeSegment(9944.600, -10.2),
            GradeSegment(16344.700, -10.8),
            GradeSegment(16894.700, -12.0),
            GradeSegment(17394.700, -10.7),
            GradeSegment(17694.700, -12.0),
            GradeSegment(18694.700, -9.6),
            GradeSegment(19444.700, -10.8),
            GradeSegment(20794.700, -11.3),
            GradeSegment(21444.700, -10.1),
            GradeSegment(21994.700, -10.8),
            GradeSegment(22244.700, -9.4),
            GradeSegment(24313.500, -11.3),
            GradeSegment(24513.500, -8.9),
            GradeSegment(25013.500, -1.5),
            GradeSegment(26683.500, -8.0),
            GradeSegment(27103.500, -10.9),
            GradeSegment(27729.680, -11.2),
            GradeSegment(28479.680, -10.8),
            GradeSegment(31879.680, -9.0),
            GradeSegment(32429.680, -10.9),
            GradeSegment(33505.930, -12.0),
            GradeSegment(34255.930, -10.6),
            GradeSegment(34605.930, -11.0),
            GradeSegment(34805.930, -11.4),
            GradeSegment(35155.930, -11.2),
            GradeSegment(36005.930, -11.0),
            GradeSegment(36755.930, -12.0),
            GradeSegment(37605.930, -11.0),
            GradeSegment(38105.930, -10.5),
            GradeSegment(39755.930, -11.5),
            GradeSegment(40305.930, -12.0),
            GradeSegment(41105.930, -11.0),
            GradeSegment(42005.930, -10.0),
            GradeSegment(43255.930, -10.5),
            GradeSegment(44305.930, -11.5),
            GradeSegment(44805.930, -12.0),
            GradeSegment(45186.020, -10.6),
            GradeSegment(46536.020, -12.0),
            GradeSegment(46938.690, -10.5),
            GradeSegment(47938.690, -8.3),
            GradeSegment(48161.360, -6.5),
            GradeSegment(48361.360, -2.5),
            GradeSegment(48561.360, -1.5),
        ],
        limit_segments=SHUOZHOU_49KM_LIMIT_SEGMENTS,
        curve_segments=SHUOZHOU_49KM_CURVE_SEGMENTS,
    )


def _slice_profile(profile: GradeProfile, start_m: float, end_m: float) -> GradeProfile:
    """从既有剖面切出 [start_m, end_m) 并**重基到 0**。

    仅用于构造"训练方法调试沙盒"剖面（物理工况不变，只是更短）。切割点落在段内时，
    起点沿用该位置的实际坡度，保证切出来的剖面与母剖面逐点一致。
    """
    segs: List[GradeSegment] = []
    for seg in profile.segments:
        if start_m - 1e-6 <= seg.start_m <= end_m + 1e-6:
            segs.append(GradeSegment(seg.start_m - start_m, seg.grade_permille))
    if not segs or segs[0].start_m > 1e-6:
        segs.insert(0, GradeSegment(0.0, round(profile.grade_at(start_m) * 1000.0, 4)))
    return GradeProfile(segments=segs)


def profile_shuozhou_ningwuxi_beidaniu_49km_slice16k() -> GradeProfile:
    """【训练方法调试沙盒，**非论文工况**】shuozhou_ningwuxi_beidaniu_49km 的 20.79–36.76 km 切片（≈16.0 km）。

    目的：训练方法（奖励 / 信用分配 / 动作权限）迭代时的快速沙盒——物理模型、编组、
    安全层与主剖面**完全一致**，仅剖面更短（含 -12‰ 陡坡 + -1.5‰ 缓坡交替，保留
    变坡/循环制动难点），使单集长程评估便宜、便于高频 A/B。

    ⚠️ 纪律：本剖面**只作 debug 沙盒**，其训练/评估结果**不得进论文正文主表、不得引用**
    （ADR-017 §3：长且复杂剖面训练→未见剖面验证才成立，短训长验方向错误）。
    """
    return _slice_profile(profile_shuozhou_ningwuxi_beidaniu_49km(), 20794.7, 36755.93)


PROFILES = {
    'long_downhill': profile_long_downhill,
    'gradual_to_steep': profile_gradual_to_steep,
    'v_shape': profile_v_shape,
    'shuozhou_23800': profile_shuozhou_23800,  # Zhang2024 复现场景
    'long_downhill_20km': profile_long_downhill_20km,  # 第二长下坡剖面（普适性）
    'long_downhill_35km': profile_long_downhill_35km,  # 第三长下坡剖面（35km，synthetic）
    'long_downhill_50km': profile_long_downhill_50km,  # 第四长下坡剖面（50km，synthetic，剧变点/边界）
    'shuozhou_ningwuxi_beidaniu_49km': profile_shuozhou_ningwuxi_beidaniu_49km,  # 朔黄线宁武西→北大牛真实纵断面 49.6km（统一线路表）
    'shuozhou_ningwuxi_beidaniu_49km_slice16k': profile_shuozhou_ningwuxi_beidaniu_49km_slice16k,  # ⚠️ 仅训练方法调试沙盒，不进正文/主表
}
