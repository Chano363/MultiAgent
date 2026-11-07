# -*- coding: utf-8 -*-
"""算法插件层：每个算法只实现 ControlAlgorithm.act(Observation) -> Action。

导入本包即完成所有插件的注册（"算法管理"域的算法清单由此而来）。
新增算法只需在本目录添加文件并在下方 import。
"""
import os
import sys

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from . import pid_cruise_plugin, rule_follow_plugin, tube_mpc_plugin  # noqa: F401,E402
