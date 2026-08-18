"""Trainer module for RL training loops.
阶段二训练脚本（架构正确，见 V5.6 重构）：
- train_fleet.py：多列编队 MAPPO（每列=智能体，列内底层控制器）——主训练脚本
- train_cyclic_braking.py：第1层单列循环制动 MAPPO（对齐 Zhang2024 DQN）
（train_train.py 已删除：V5.6 废弃的错误架构，把101节车厢当智能体）
"""

__all__ = []