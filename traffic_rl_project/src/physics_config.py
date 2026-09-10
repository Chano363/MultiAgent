"""参数中心化：训练/验证/评估共用的物理配置（单一事实源）。

【重构 2026-09-05】避免各处手写 v_max/mass 等物理值导致训练/验证动力学不一致。
所有脚本 import 本配置，禁止再手写默认物理参数。
"""
from dataclasses import dataclass, asdict, fields


@dataclass(frozen=True)
class PhysicsConfig:
    """唯一物理配置对象（正式朔黄工况基线）。

    任何脚本一律 use 本对象取值；要改物理参数 → 改这里，别到处写字面量。
    """
    v_max_mps: float = 80.0 / 3.6          # 线路限速（朔黄线 80 km/h）
    v_min_mps: float = 40.0 / 3.6          # 最小缓解速度（40 km/h）
    dt: float = 0.1
    max_accel: float = 1.0
    target_speed_mps: float = 20.0          # 巡航参考速度（限速带中值）
    target_gap_m: float = 100.0
    consist_preset: str = '10kt_1plus0'     # 论文编组（重构后多列用 1+1 时在此改）
    grade_profile: str = 'shuozhou_real_53km'  # 主训练真实剖面（朔黄完整纵断面 53.2km）；history 'shuozhou_23800'=23.8km 仅作 Zhang2024 复现
    coupler_force_limit_n: float = 1.0e6    # 1000 kN 底线
    # （无 enable_etcs 开关：ATP/ETCS 真 ATP 为永久启用的安全底线，恒启）
    enable_cyclic_degrade: bool = True      # 【R0-D 2026-09-06】B3 段间衰减=基线物理

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def field_count(cls) -> int:
        return len(fields(cls))


# 供各脚本入口默认值（勿再写字面量 80/3.6、40/3.6、1.0）
_OFFICIAL = PhysicsConfig()