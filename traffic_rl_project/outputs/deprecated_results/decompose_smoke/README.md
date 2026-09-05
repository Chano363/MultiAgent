# decompose_smoke —— 废弃（冒烟门控历史轮次，2026-09-05）

> **为什么废弃**：decompose 早期**门控/冒烟**阶段（3000 步、含 ab_command=None bug 期与决策间隔试跑）的产物，只用于演进回溯。
> **仅回溯**：论文**禁止引用**本目录任何数值。

## 含
- `results_dec_smoke{1..6}/`、`checkpoints_dec_smoke/`：逐轮冒烟训练历史（AB 成本/entropy/curriculum 试标定）。

## 替代
- 正式路径 = `outputs/checkpoints_dec_full_iv10/`、`outputs/results_dec_full_iv10/`（interval=10 终版）。
- 迁移自 `outputs/`；日志见 `outputs/train_logs/train_dec_smoke*.log`（未被迁移，仍在原处供 grep）。