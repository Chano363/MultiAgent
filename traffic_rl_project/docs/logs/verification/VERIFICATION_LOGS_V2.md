---
title: 验证执行日志（V 系列：仿真器 / 算法验证过程记录）
date: 2026-09-01
status: active (按 V 块拆分)
owner: Agent + Owner
supersedes: partial（自 docs/records/VERIFICATION_LOGS.md 按 V2 块拆出）
---

> 本文件为 `docs/records/VERIFICATION_LOGS.md` 按 V2 系列拆出的部分。


# 验证执行日志（V 系列）

> 本文档由 `docs/VALIDATION_BASELINE.md`「三.5 验证结果记录」部分按行迁移而来，**内容零丢失**。
> 后续新的验证执行/结果记录在此 append（对照模板 `docs/rules/TEMPLATE_*`）。

## 三.5 验证结果记录（持续追加，保留工作痕迹）


### V2 Davis 阻力公式修复（2026-08-12，仿真器验证）

**来源**：标准 Davis 阻力公式（AAR 标准）+ 物理合理性验证。

**❌ 失败/问题记录**：
- **问题**：P1 第 9 条环境验证发现目标速度 20 m/s（72 km/h）物理不可达——单机牵引 6 节车平衡速度仅 ~8 m/s，奖励被速度误差主导（-10 占 99%）
- **根因诊断**：Davis 阻力公式 bug（从 NeTrainSim 复制）——空气项写成 `area*cd*v²/w`，被错误放大约 **w 倍**（单车 100t@10m/s 阻力 241kN，而真实应 ~1.8kN）

**✅ 修复**：
- `resistance.py`：改为标准 Davis 公式 `(1.5 + 18/W_axle + 0.03V)*W + 0.0018*C*A*V²`，空气阻力独立于车重
- 修复后：20 m/s **可达且可维持**（P 控制器稳定 15.5 m/s），保持运输效率；奖励分布显著改善（前50 -8.6 → 后50 -2.3）

**✅ 测试更新**：
- `tests/test_train_dynamics.py`：Davis 测试从"复现 NeTrainSim 错误值"改为"标准公式验证"（含注释说明修复原因）
- 全部 **54 测试通过**

📌 **教训**：从参考实现复制的公式也可能有 bug，必须用物理合理性 + 论文/标准验证；验证基准能暴露此类隐藏错误。

---

<!-- 该文档整理/压缩于 2026-10-01 -->
