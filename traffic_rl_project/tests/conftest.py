"""测试公共配置：把项目根加入 sys.path，替代各测试文件逐个 sys.path.insert。

（2026-09-10 工程治理：12 个测试文件原来各自插一遍路径，收敛到这一处；
若已 `pip install -e .` 则此文件为冗余兜底，无副作用。）
"""
import sys
from pathlib import Path

_PROJECT_ROOT = str(Path(__file__).resolve().parent.parent)
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)
