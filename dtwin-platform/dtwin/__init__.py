# -*- coding: utf-8 -*-
"""数字孪生仿真平台（骨架）。

功能域与实现文件：
  算法管理   algorithms/ + registry（契约 ControlAlgorithm.act）+ 算法发送
  仿真运行   engine.SimulationEngine + runtime（可替换执行器，当前为离线占位）
  数据记录   recorder（CSV / 指标 JSON）
  分析服务   消费 recorder 输出（webapp 提供对比视图）

平台不设场景管理域：一次运行的静态配置统一由 RunConfig 内置默认值 + 请求覆盖。
"""
from .contracts import (Action, ActuatorReport, ControlAlgorithm, Observation,
                        PlantAdapter, Protection, Reference, RunConfig,
                        TrainState)
from .engine import EpisodeResult, SimulationEngine
from .reference import ReferenceGenerator

__all__ = [
    "Action", "ActuatorReport", "ControlAlgorithm", "Observation", "PlantAdapter",
    "Protection", "Reference", "RunConfig", "TrainState",
    "EpisodeResult", "SimulationEngine", "ReferenceGenerator",
]
