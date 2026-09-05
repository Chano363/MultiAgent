# decompose\_pre\_release\_fix —— 废弃（ab\_command=None bug 期，2026-09-05）

> **为什么废弃**：这些 decompose 训练/评估发生在 `train_env._step_decomposed` **无 AB 源时发** **`None`（≠ RELEASE）** 的阻塞 bug 修复**之前**——规则/RL 会把列车拖停（残留制动不缓解）。它们的结果不可用作正式结论。
> **仅回溯**：论文**禁止引用**本目录任何数值。

## 含

- `results_dec_full/`、`checkpoints_dec_full/`：`ab_command=None` bug 期 15000 步全量训练与评估（ab 滥用/拖停）。

- 正式替代 = `outputs/checkpoints_dec_full_iv10/`、`outputs/results_dec_full_iv10/`（interval=10, RELEASE 修复后）。

## 复现/核对

- 参照 `docs/records/DIAGNOSTICS.md`「decompose换架构」诊断节；迁移自 `outputs/`。

