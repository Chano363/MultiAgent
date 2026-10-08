"""工程治理：工况枚举 + 运行时断言（校验写在运行时，不依赖人读文档）。

【重构 2026-09-05】禁止用布尔开关关闭错误物理；改为「工况枚举」显式分流：
- SimCase.OFFICIAL          ：正式朔黄工况，只允许官方物理配置；
- SimCase.DEBUG_SIMULATION  ：调试/探针/消融，允许调试物理开关。
调试仿真工况进入训练/验证 → 立即抛异常；官方脚本不 import 调试模块。
"""
from dataclasses import replace
from enum import Enum

from src.physics_config import PhysicsConfig


class SimCase(Enum):
    OFFICIAL = "official"
    DEBUG_SIMULATION = "debug"


# 【2026-09-30】运行派生键：这些字段由**本次运行的 env_cfg**（实验 YAML 的 .env_cfg）
# 决定，而非 PhysicsConfig 的固版默认值。metadata 的 physics 块必须反映本次运行，
# 否则会静默误报——实例：主实验已切 `10kt_1plus1`（3列×1+1=6 机车智能体），
# 但 physics 块仍报固版默认 `10kt_1plus0`，污染 simulator_model / simulator_model_version。
# 溯源见 docs/logs/diagnostics/DIAGNOSTICS_2026-09B.md「诊断-2026-09-30-metadata 编组不一致溯源」。
RUN_DERIVED_KEYS = ("consist_preset",)


# 调试物理开关的"正式工况合法值"（黑名单外的都必须是这些值才放行）
# 【2026-09-06 R0-D】enable_cyclic_degrade 升级为主场景基线物理（赵紫宁表5-5
# C_β 段间衰减，首段=1.0），正式工况必须启用；显式关闭属调试物理（debug 工况）。
_OFFICIAL_LEGAL = {
    "enable_cyclic_degrade": True,    # AB 循环制动段间衰减 B3（R0-D 起基线物理）
    "tail_pressure_kpa": None,        # 列尾压强平衡梯度 L1（仍为调试物理）
    "brake_reduction_override_kpa": None,  # 连续减压量覆盖 P0-3
}


def official_world_config(physics: PhysicsConfig = None, env_cfg: dict = None) -> dict:
    """返回正式工况的物理配置（供 metadata 固版与断言比对）。

    env_cfg：本次运行的实验环境配置（实验 YAML 的 `.env_cfg`）。`RUN_DERIVED_KEYS`
    列出的字段以 env_cfg 为准覆盖固版默认值，使 metadata 的 physics 块**反映本次运行**；
    其余物理项仍锚定 official 默认（固版基线，不随实验漂移）。
    不传 env_cfg → 与旧行为完全一致（纯固版快照）。
    """
    physics = physics or PhysicsConfig()
    if env_cfg:
        overrides = {k: env_cfg[k] for k in RUN_DERIVED_KEYS if env_cfg.get(k)}
        if overrides:
            physics = replace(physics, **overrides)
    return {**_OFFICIAL_LEGAL, "physics": physics.to_dict()}


def assert_case_allows(case: SimCase, world_cfg: dict, entry: str):
    """入口断言：调试物理开关出现在正式流程 → 立即抛异常。

    entry：入口脚本 __file__（仅作报错定位）。
    """
    if case is SimCase.OFFICIAL:
        bad = []
        for k, legal in _OFFICIAL_LEGAL.items():
            got = world_cfg.get(k)
            if got != legal:
                bad.append(f"{k}={got!r} (合法={legal!r})")
        if bad:
            raise RuntimeError(
                f"[case-guard] 调试物理进入正式流程被拒 (entry={entry}): {'; '.join(bad)}")
    # DEBUG_SIMULATION 不拦（用于探针/消融）


def official_entry_guard(entry: str):
    """轻量入口守卫：评估/验证脚本 main 入口一行接入（official 工况断言）。"""
    assert_case_allows(SimCase.OFFICIAL, official_world_config(PhysicsConfig()), entry)