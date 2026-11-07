# -*- coding: utf-8 -*-
"""runtime 包：仿真运行域。

对外只暴露"提交运行 -> 后台执行 -> 归档结果"，执行器具体是
离线回放还是 NeTrainSim 联合仿真，由 backends 里的登记项决定。
"""
from .backends import BACKENDS, describe_backends, get_backend
from .jobs import STORE, JobStore, build_run_config, platform_overview

__all__ = ["BACKENDS", "describe_backends", "get_backend", "STORE", "JobStore",
           "build_run_config", "platform_overview"]
