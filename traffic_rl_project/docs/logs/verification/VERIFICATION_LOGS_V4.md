---
title: 验证执行日志（V 系列：仿真器 / 算法验证过程记录）
date: 2026-09-01
status: active (按 V 块拆分)
owner: Agent + Owner
supersedes: partial（自 docs/records/VERIFICATION_LOGS.md 按 V4 块拆出）
---

> 本文件为 `docs/records/VERIFICATION_LOGS.md` 按 V4 系列拆出的部分。


# 验证执行日志（V 系列）

> 本文档由 `docs/VALIDATION_BASELINE.md`「三.5 验证结果记录」部分按行迁移而来，**内容零丢失**。
> 后续新的验证执行/结果记录在此 append（对照模板 `docs/rules/TEMPLATE_*`）。

## 三.5 验证结果记录（持续追加，保留工作痕迹）


### V4 MAPPO 迁移到列车验证（2026-08-13，P1 第15条）

**实现**：
- 新建 `src/trainer/train_train.py`：复用阶段一 `MAPPOAgent`（共享策略+集中式Critic+GAE+KL早停），迁移到 `TrainFormationEnv`（万吨级 1+0 + 长大下坡），**不动无人机代码**
- 迁移适配：列车 obs=(num_vehicles,4)，flatten 后传入 agent；每车 act_dim=1（throttle∈[-1,1]）
- 超参数：`lr=5e-5, entropy=0.005, epochs=4, batch_size=64`（按 PROJECT_PIPELINE 起步值）

**验证结果**：
- ✅ 4 冒烟测试通过（`tests/test_mappo_train.py`）：维度匹配、动作范围/reshape、store+update、万吨级完整 episode
- ✅ 短训 30 回合跑通：KL 早停多次触发（防坍缩）、loss 1.427 合理、总耗时 8.6s、模型保存成功
- ✅ 全部 69 测试通过，无回归

**短训观察（30 回合，未收敛）**：
- Reward -96.8（负，初期探索正常）
- 平均车钩力峰值 950 kN（接近 1000 kN 上限）
- 平均超限 145 次 → **提示**：奖励冲动惩罚权重（-0.15）可能偏低，需在 P2 消融时关注；短训后需更长时间（数百回合）验证收敛

📌 **说明**：短训仅验证"能跑通"，MAPPO 需数百回合才收敛（阶段一经验）；正式基线训练需较长训练时间（P1 第15条后续）

---

<!-- 该文档整理/压缩于 2026-09-22 -->
