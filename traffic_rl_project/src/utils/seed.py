"""统一的随机种子设置（2026-09-10 自 6 个文件逐字重复定义收编）。

所有训练/评估入口一律 `from src.utils.seed import set_seed`，
保证 numpy / torch / cuda 种子行为全项目一致。
"""
import random

import numpy as np
import torch


def set_seed(seed: int, seed_python: bool = True) -> None:
    """设置 numpy/torch/cuda 随机种子（可选连带 Python random）。

    Args:
        seed: 随机种子
        seed_python: 是否同时固定 Python random（默认 True；
            DQN 家族用 random 做探索采样，训练入口保持默认即可）
    """
    np.random.seed(seed)
    torch.manual_seed(seed)
    if torch.cuda.is_available():
        torch.cuda.manual_seed(seed)
        torch.cuda.manual_seed_all(seed)
    if seed_python:
        random.seed(seed)
