# -*- coding: utf-8 -*-
"""物理适配器层：第三方仿真器与车钩模型。

导入本包时把项目根目录与第三方仿真器目录加入 sys.path，
使 adapters / algorithms / dtwin 之间的导入与运行位置无关。
"""
import os
import sys

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_SIM_ROOT = r"d:\Z\first station\multi-agent-main\traffic_rl_project"
for _p in (_ROOT, _SIM_ROOT):
    if _p not in sys.path:
        sys.path.insert(0, _p)
