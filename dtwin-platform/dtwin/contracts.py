# -*- coding: utf-8 -*-
"""数字孪生平台 —— 契约层（算法 / 物理对象 / 保护层的唯一接口）。

三条硬边界：
  1. 算法只看 Observation、只输出 Action，不得 import 仿真器，不得做文件 I/O；
  2. 物理对象只经 PlantAdapter 暴露（reset / observe / step / diagnostics），
     第三方 TrainDynamics 一行不改；
  3. 列间安全包络、ATP / 循环制动、电-空仲裁属平台保护层，
     在算法输出之后、物理执行之前对 Action 二次钳制（换算法不丢安全约束）。

平台不设"场景管理"域：一次运行的全部静态配置由 RunConfig 承载，
默认值即朔黄线真实区段（宁武西 -> 北大牛 49.527 km）复现场景，
可在运行请求中按需覆盖（车钩模型 / 制动监督方式 / 起止里程等）。
"""
from __future__ import annotations

import copy
from dataclasses import dataclass, field
from typing import Any, Dict, Protocol, Sequence, Tuple


# ----------------------------------------------------------------------
# 运行配置（默认值 = 朔黄线真实区段复现场景）
# ----------------------------------------------------------------------
DEFAULT_REFERENCE: Dict[str, Any] = {
    "a_dec": 0.08,          # 减速规划减速度 m/s^2
    "a_acc": 0.15,          # 加速规划加速度 m/s^2
    "ds_tbl": 10.0,         # 目标曲线查表间隔 m
    "d_des": 2000.0,        # 期望列间头对头间距 m
    "t_adj": 120.0,         # 间距误差调节时间常数 s
    "v_adj": 1.5,           # 间距调节叠加速度上限 m/s
    "v_cap_kmh": 80.0,      # 目标曲线速度上限
}

DEFAULT_PROTECTION: Dict[str, Any] = {
    "speed_envelope": {"a_eb": 0.15, "d_min": 150.0},
    "brake_supervisor": "atp",          # atp / cyclic
    "t_ai": 45.0,                       # 最短充风时间 s
    "v_release_min_kmh": 30.0,          # 最低缓解速度
    "atp": {
        "dv_on_kmh": 1.0,
        "dv_off_mps": 0.5,
        "b_base_kpa": 50.0,
        "b_gain_kpa": 100.0,
        "b_max_kpa": 170.0,
    },
    "cyclic": {"reduction_kpa": 50.0, "dv_apply": 0.5, "dv_release": 0.5},
    "ed_max": 0.8,
    "ed_air_cap": 0.2,
    "dv_air_cap_margin": 0.3,
}


@dataclass
class RunConfig:
    """一次运行的静态配置（引擎 / 参考层 / 保护层共用）。"""
    name: str = "shuohuang_49527"
    line: str = "shuozhou_real_53km"    # 仿真器 PROFILES 键（真实线路数据）
    s_start: float = 1932.0             # 头车初始里程 m
    s_end: float = 51459.0              # 头车终止里程 m
    n_trains: int = 3
    train_head_gap: float = 2000.0      # 初始头对头间距 m
    dt_mpc: float = 1.0                 # 控制采样周期 δ
    dt_dyn: float = 0.1                 # 物理控制步长
    sub_steps: int = 10                 # 每个 δ 内的物理子步数（ZOH 保持）
    coupler_model: str = "linear"       # mt2 / linear / zero
    line_length: float = 53600.0        # 目标曲线覆盖的线路长度
    reference: Dict[str, Any] = field(default_factory=lambda: copy.deepcopy(DEFAULT_REFERENCE))
    protection: Dict[str, Any] = field(default_factory=lambda: copy.deepcopy(DEFAULT_PROTECTION))

    @property
    def d_des(self) -> float:
        return float(self.reference["d_des"])

    def clone_with(self, **overrides: Any) -> "RunConfig":
        """浅拷贝并覆盖顶层字段；reference / protection 按需深拷贝。"""
        cfg = RunConfig(**{k: copy.deepcopy(v) for k, v in self.__dict__.items()})
        for key, value in overrides.items():
            if value is None or not hasattr(cfg, key):
                continue
            setattr(cfg, key, value)
        return cfg

    def with_brake_mode(self, mode: str) -> "RunConfig":
        cfg = self.clone_with()
        cfg.protection = copy.deepcopy(cfg.protection)
        cfg.protection["brake_supervisor"] = mode
        return cfg


# ----------------------------------------------------------------------
# 物理对象 -> 平台
# ----------------------------------------------------------------------
@dataclass(frozen=True)
class TrainState:
    """单列车的可观测量。算法侧拿不到任何仿真器对象。"""
    train_id: int
    s_head: float                  # 机车头端里程 m
    v_head: float                  # 机车速度 m/s
    v_group: Tuple[float, float]   # 两个货车质量点组的平均速度 m/s
    s_group: Tuple[float, float]   # 两个货车质量点组的平均位置 m
    gap_lead: float                # 与前车头对头间距 m（头车为 inf）
    v_lead: float                  # 前车速度 m/s（头车为 inf）


@dataclass(frozen=True)
class ActuatorReport:
    """物理层实际执行的执行器量（用于记录，不参与控制）。"""
    throttle: float
    ed: float


# ----------------------------------------------------------------------
# 平台 -> 算法
# ----------------------------------------------------------------------
@dataclass(frozen=True)
class Reference:
    """参考层输出 + 量测派生量（算法无需自己保存历史）。"""
    v_ref: float
    a_ref: float
    v_sup: float                   # 本车位置处的线路监督速度（原始限速上包络）
    v_allow: float = float("inf")  # 列间安全包络允许速度
    intra_dev: float = 0.0         # 机车-货车组1 间距相对初始几何的偏差
    d2: float = 0.0                # 货车组等效加速度（式19 量测实现）


@dataclass(frozen=True)
class Observation:
    """算法唯一可见的输入。"""
    train_id: int
    t: float
    s_head: float
    v_head: float
    v_group: Tuple[float, float]
    intra_dev: float
    v_ref: float
    a_ref: float
    v_sup: float
    v_allow: float
    d2: float
    gap_lead: float
    v_lead: float
    is_leader: bool


@dataclass
class Action:
    """算法输出 + 保护层可写入的钳制字段。"""
    u_hat: float = 0.0             # 归一化控制输入（m/s^2，正=牵引）
    brake_apply: bool = False      # 空气制动施加（保护层填写）
    brake_kpa: float = 0.0         # 减压量 kPa（0=缓解）
    ed_cap: float = 1.0            # 电制动输出率上限（电-空仲裁填写）


# ----------------------------------------------------------------------
# 协议
# ----------------------------------------------------------------------
class ControlAlgorithm(Protocol):
    name: str

    def reset(self, config: RunConfig) -> None:
        ...

    def act(self, obs: Observation) -> Action:
        ...


class PlantAdapter(Protocol):
    def reset(self, v_init: float) -> Sequence[TrainState]:
        ...

    def observe(self) -> Sequence[TrainState]:
        ...

    def step(self, commands: Sequence[Action],
             sub_steps: int) -> Sequence[ActuatorReport]:
        ...

    def coupler_peak_forces(self) -> Sequence[float]:
        """各列车当前最大 |车钩接口力|，单位 kN（步前采样，供记录/告警）。"""
        ...

    def energy_kwh(self) -> Sequence[float]:
        ...

    @property
    def train_length(self) -> float:
        """单列车头端到尾端长度 m（列间包络净空计算用）。"""
        ...


class Protection(Protocol):
    def reset(self) -> None:
        ...

    def apply(self, obs: Observation, action: Action) -> Action:
        ...
