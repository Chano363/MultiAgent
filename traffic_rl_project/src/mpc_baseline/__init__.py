# -*- coding: utf-8 -*-
"""src.mpc_baseline：Tube MPC 基线（ADR-042 两基线之一）。

移植自 `zba` 分支 `MPC-baseline/song2026_tubempc/`（Song2026 复现，忠实性证据见
复现报告 §1）。设计规格：`docs/knowledge/MPC_BASELINE_KNOWLEDGE_BASE.md` §6。
"""
from src.mpc_baseline.tube_mpc import TubeMPC, pair_A  # noqa: F401
