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


PROFILES = {
    'long_downhill': profile_long_downhill,
    'gradual_to_steep': profile_gradual_to_steep,
    'v_shape': profile_v_shape,
}
