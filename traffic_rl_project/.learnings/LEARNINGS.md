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
README must be extremely concise to save tokens; prefer linking to detailed docs instead of inline content.

### Details
User explicitly stated README was "太冗余，浪费我的token". The previous README contained inline tables for algorithm comparisons, action/observation spaces, reward functions, literature references, and phase2 plans — all of which are already detailed in learning_report.md and project_rules.md.

Lesson: README should be a **navigation index** + **critical gotchas only**. Assume the reader (another agent) will follow links for details.

### Suggested Action
When writing README docs:
1. Keep it to: what, status, entry point, critical gotchas
2. ANY content > 2 sentences that exists elsewhere → link instead
3. Project structure tree OK but keep it flat
4. Training commands OK but absolute minimum

### Metadata
- Source: user_feedback
- Related Files: d:\Code\MultiAgent\traffic_rl_project\README.md
- Tags: docs, token_efficiency, readability

---