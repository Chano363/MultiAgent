---
title: Learnings（踩坑 / 失败教训 / 经验）
status: active
owner: Agent + Owner
---

# Learnings

> 这是项目**失败教训 + 可复用经验**的权威文件。新条目请遵循模板：
> - 失败/踩坑 → `docs/rules/TEMPLATE_FAILURE.md`（现象/期望vs实际/根因三层/解决/预防）
> - 可复用经验 → `docs/rules/TEMPLATE_EXPERIENCE.md`（适用/不适用/证据/速记）
> 既有条目 **append-only 保留**。本文件规范见 `docs/rules/README.md`。

Corrections, insights, and knowledge gaps captured during development.

**Categories**: correction | insight | knowledge_gap | best_practice

---

## [LRN-20260530-001] best_practice

**Logged**: 2026-05-30T11:40:00Z
**Priority**: high
**Status**: pending
**Area**: docs

### Summary
README 必须极简省 token：优先链接到详细文档而非内联内容。用户原话：README "太冗余，浪费我的token"——旧 README 内联了算法对比/动作观测空间/reward 函数/文献引用/阶段二计划等表格，均已在 learning_report.md 与 project_rules.md 中。
Lesson：README = **导航索引 + 关键坑**，读者（另一 agent）会跟随链接看细节。

### Suggested Action
1. 只写：what / status / 入口 / 关键坑
2. 任何 >2 句且别处已有的内容 → 改链接
3. 项目结构树可留但保持扁平
4. 训练命令可留但保持绝对最少

### Metadata
- Source: user_feedback
- Related Files: d:\Code\MultiAgent\traffic_rl_project\README.md
- Tags: docs, token_efficiency, readability

---

<!-- 该文档整理/压缩于 2026-09-22 -->