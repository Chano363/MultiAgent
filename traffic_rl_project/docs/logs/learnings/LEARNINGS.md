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

## [LRN-20260930-001] correction（物理建模 / 指标口径）

**Logged**: 2026-09-30
**Priority**: high
**Status**: resolved（2026-09-30 落地并回归验证 —— 见 ADR-018 + `DIAGNOSTICS_2026-09B.md`「诊断-2026-09-30-治本改造回归验证」）
**Area**: train_dynamics / environments / safety

### 现象：训练/评估/违规计数/安全门控全用"每车净力"口径，与项目实测基准"单钩断面力"口径混用 → 少报约 7.8×，并在拉压交界处误判

- **期望 vs 实际**
  - 期望：违规计数与安全门控与论文/实测基准同口径（`coupler_interface_forces()`，单钩断面力，正=压）。
  - 实际：同一次 100ep 策略 rollout（seed 2000，1200 步）——净力口径 `车厢·步>1000kN = 110`，断面力口径 `= 857`（**少报 7.8×**）；且净力在拉压交界处把异号相邻钩叠加（峰值步 `异号相邻对=7/95`），使 **no_traction 场景净力 913kN"看似安全"、断面力实为 1242kN 破线**——据此得出的"单通道都安全"结论是**伪影**。
- **根因（三层追）**
  1. 表象：同一 episode 两口径给出不同违规数/不同峰值归属（train1 净/断比 0.87）。
  2. 机制：`_coupler_forces()` 是"每车净力"（相邻钩矢量和），`coupler_interface_forces()` 才是"单钩断面力"（实测口径）；安全层/评估/门控读了前者。
  3. 为什么没早发现：`src/train_dynamics/train.py` L347-357 注释已明写"**所有对照验证必须用它，避免用车厢净力造成误判**"，但训练/评估链路未复用该口径 → **缺"口径唯一来源"约束**（同一物理量存在两个 getter，却无强制调用约定）。
- **解决**：待决策——把安全层门控 / 违规计数 / 评估指标全部改用 `coupler_interface_forces()`。
- **止血与预防**
  - 本次：诊断结论一律以断面力口径为准（见 `docs/logs/diagnostics/DIAGNOSTICS_2026-09B.md` 诊断-2026-09-30）。
  - 长期：车钩力指标只保留一个权威口径 getter；`_coupler_forces()`（净力）如仅内部积分用，须显式命名/注释"非指标口径"并禁用于计数。
- **类型标签**：`物理建模` / `指标口径`

---

## [LRN-20260930-002] knowledge_gap（安全层权限）

**Logged**: 2026-09-30
**Priority**: high
**Status**: resolved（2026-09-30 落地并回归验证 —— 见 ADR-018 + `DIAGNOSTICS_2026-09B.md`「诊断-2026-09-30-治本改造回归验证」）
**Area**: safety_layer / environments

### 现象：`SafetyLayer`（ATP）对空气制动(AB)无物理权限 → "车钩力 ≤1000kN 硬兜底"名不副实

- **期望 vs 实际**
  - 期望：安全层能在动作喂给动力学前把车钩力钳到 ≤1000kN（ATP 硬兜底）。
  - 实际：逐机车 AB 波源绕过安全层（`train_env.py` L457-475：`ab_sources` 在 `safety.protect`（L493）**之前**组装、直接进动力学）；安全层钳制只下调 `ed_throttle`（L506-508），对 AB 只有"升级全局 EMERGENCY"的**加权限**、无"减权限"；两个反应式 AB 闸门（`_coupler_throttle_scale`、`AB_ADD_SOURCE_MAX_RATIO=0.6`）都读**上一时刻净力**，叠加 AB 波 ~5s 滞后 → 真断面力已破线时闸门不触发（实证：AB 首现 t=0 → 首破 t=901，滞后 90.1s）。
- **根因（三层追）**
  1. 表象：安全层触发条件用旧力、且作用域不含 AB。
  2. 机制：安全层接口只接收 `proj_throttle`（机车制动深度），AB 通道是独立 `ab_sources` 数组，未纳入安全层动作空间。
  3. 为什么没早发现：`MultiLocoController._safety`（L63-67）是**死代码从未被调用**，掩盖了"安全层看起来已接入"的假象。
- **解决**：待决策——给安全层对 AB 的实际权限（按位置+波速的**预测式峰值防护**），并消除死代码。
- **预防**：安全层应覆盖**全部执行通道**（ED 与 AB 缺一不可）；新增执行通道时必须同步登记进安全层动作空间（补 CHECKLIST 条目）。
- **类型标签**：`算法逻辑` / `安全机制`

---

## [LRN-20260930-003] correction（仿真环境 / 可复现性）

**Logged**: 2026-09-30
**Priority**: medium
**Status**: resolved（本次实验内已规避）
**Area**: environments

### 现象：`env.reset()` 未彻底清空列车动力学内部状态 → 同一 env 实例连跑多场景存在顺序依赖

- **期望 vs 实际**
  - 期望：`env.reset()` 后环境回到干净初态，同一场景多次连跑结果可复现。
  - 实际：1200 步四场景回归中，同一 env 实例**连续**跑多场景时 train0 断面力峰值在 **732.6↔756.8 kN** 间浮动；**逐场景重建 env** 后稳定。
- **根因**：`reset()` 只重置了 env 级累计量（`_peak_coupler_n` / `_coupler_limit_violations` / `_overspeed_violations` / `_safety_events`）与 `safety.last_events`；列车动力学对象 / 安全层峰值历史（`_peak_hist`）等**内部状态未完全归零** ⇒ 跨 episode 残留。
- **解决**：诊断 / 评估脚本**逐场景重建 env**（不复用实例）；如需在同一实例内连跑，须显式重建 `trains` / `dynamics` / `safety`。
- **预防**：写多条件对比实验时默认"**每条件独立 env + 固定 seed**"；把"reset 后是否完全无状态残留"纳入环境单测（`tests/`）。
- **类型标签**：`仿真环境` / `可复现性`

---

<!-- 该文档整理/压缩于 2026-09-22 -->