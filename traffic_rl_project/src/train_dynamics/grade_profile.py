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
from typing import List, Tuple
import numpy as np


@dataclass
class GradeSegment:
    """一段坡道：从 start_m 到下一个段的起点，坡度为 grade_permille（‰）。"""
    start_m: float
    grade_permille: float  # 正=上坡, 负=下坡


@dataclass
class GradeProfile:
    """线路坡度剖面（分段线性）。

    Attributes:
        segments: 按起点位置升序排列的坡段列表
    """
    segments: List[GradeSegment] = field(default_factory=list)

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

    def grades_for_positions(self, positions: np.ndarray) -> np.ndarray:
        """批量查询多节车位置的坡度（返回无量纲数组）。"""
        return np.array([self.grade_at(float(p)) for p in positions])


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


PROFILES = {
    'long_downhill': profile_long_downhill,
    'gradual_to_steep': profile_gradual_to_steep,
    'v_shape': profile_v_shape,
    'shuozhou_23800': profile_shuozhou_23800,  # Zhang2024 复现场景
    'long_downhill_20km': profile_long_downhill_20km,  # 第二长下坡剖面（普适性）
    'long_downhill_35km': profile_long_downhill_35km,  # 第三长下坡剖面（35km，synthetic）
    'long_downhill_50km': profile_long_downhill_50km,  # 第四长下坡剖面（50km，synthetic，剧变点/边界）
}
