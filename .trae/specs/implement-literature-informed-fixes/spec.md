# 落实文献调研的 4 条实质改造（+ 文档索引去重 + P0 验证 harness）

change-id: `implement-literature-informed-fixes`
（**取代** 被否的 `run-adr021-p0-baselines`——后者只做"测量"，无实质改造）

## Why

用户指出：文献调研（`docs/logs/diagnostics/DIAGNOSTICS_2026-10.md`「调研-2026-10-01」）已经得出**四条有成熟解法可对位的改造**，但上一版规格只安排了重跑评估（测），**没有任何实质代码改动**（改）。根因归因出的断点仍在，MARL 仍会破线。

同时，根 `AGENTS.md` 的「何时读什么」逐条清单与 `docs/README.md`（唯一索引入口）重复，应改为单向指针。

## What Changes

四条改造**全部落地**（按成本/风险排序实施），P0 三行基线保留为**验证 harness**；并**列入长久计划**（重训里程碑另排算力）。

- **导航**：根 `AGENTS.md` 文档索引 → 单行指针指向 `docs/README.md`（去重复清单）。
- **A｜AB 最小充风时间进动作空间**（Zhang2024）：在规则层 + RL 新增源通道上加"最小充风时间 + 最小持续时间"约束，从源头断「缓解—再制动」循环。
- **D｜安全层对 AB 的"投影 / 禁新增"权限**（Wabersich & Zeilinger 2021 预测式思想 + ADR-021 决策 3）：`train_env._step_decomposed` 中 AB 源当前绕过安全层；补齐与 ED **对称**的权限。**不撤销已建立源**（X4-b 已反证恶化）。
- **C｜车钩力受控超限项进 reward**（Tang2020 / Wang2025）：奖励补"超限"非线性项（**量纲受控**，替代已回滚的 `-80·ov²`），且**峰值改用断面力口径**（现用每车净力，少报 ≈7.8× ⇒ reward 看不见真正的破线）。
- **B｜per-agent advantage + 信用视界对齐**（COMA Foerster2018 / PRD-MAPPO Kapoor2024）：把 `update()` 里"单标量 advantage 广播到 6 台机车"改为 per-agent；并把 γλ 视界从 17 s 拉到 ≥ 物理滞后窗口（≈90 s）。
- **长久计划**：以上改造的重训/多 seed/跨线验证里程碑登记进 `PROJECT_PIPELINE.md`（不在本次跑完）。

## Impact

- Affected specs：文档导航（SSOT = `docs/README.md`）；ADR-021 的 P0–P3 排序（本次把 P1/P2/P3 的**代码**落地，验证另排）。
- Affected code（**本规格唯一改代码的地方，均为最小实现**）：
  - `src/controllers/multi_loco_controller.py`（A）
  - `src/environments/train_env.py` + `src/safety_layer.py`（D）
  - `src/environments/train_fleet_env.py`（C）
  - `src/algorithms/mappo_agent.py` + `src/trainer/registry.py` + `config_schema.py`（B）
  - `tests/`（各改造的单测）
- Affected docs：`AGENTS.md`、`DIAGNOSTICS_2026-10.md`、`DECISIONS.md`（ADR-021 状态 + 必要时 ADR-022）、`PROJECT_PIPELINE.md`、`LEARNINGS.md`（踩坑）、`.codebuddy/memory/2026-10-01.md`。

## 事实核定（写规格时已核实，防止规格漂移）

| 事实 | 位置 | 对规格的约束 |
| :--- | :--- | :--- |
| 规则基线由 `self.multi_loco_controllers` **持久持有**（每列一个，`__init__` 建） | `train_fleet_env.py:239-252` | A 的"充风计时"状态可挂在 controller 上，无需新增全局状态 |
| `mask_lever=='ab'` ⇒ `ab_mod=0.0` | `multi_loco_controller.py:261-262` | 语义 = **RL 完全退出 AB 决策**（既不能抑制也不能提前触发），比 ADR-021 原文更宽，留痕须写明 |
| `ab_sources` 在安全层**之前**组装，安全层只回写 `ed_throttle` | `train_env.py::_step_decomposed` 组装段 vs `protect()` 段 | D 的落点明确：在 `protect` 之后对 `ab_sources` 施加权限 |
| 车钩力峰值**已传入** reward，但取的是 `_coupler_forces()`（**每车净力**） | `train_fleet_env.py:680-682, 691-692, 763-766` | C 必须**改口径为断面力**，否则超限项看不见破线 |
| `CentralizedValueNetwork` 输出 **1** 维 | `mappo_agent.py:150` | B 的 per-agent 需 N 维输出 ⇒ 改 **critic 结构**（枚举，非布尔开关） |
| `MAPPOAgent(device=..., **cfg.algo_params)` | `trainer/registry.py:40-42` | γ/λ 等已可由实验 YAML 注入 ⇒ B 的"视界对齐"部分靠配置即可 |
| `--mode decompose_m0` = "规则基线(RL 调制恒 0)" | `evaluate_decompose.py:256-258` | P0 的 M0 行无需新代码 |

## 深度界定（"做到什么程度合适"）

**做**：每条改造的**最小文献忠实实现** + 单测 + **固定窗口（1200 步，确定性）before/after 机制验证**。目的 = 证明机制**确实生效且不回归**。

**本次不做**（列入长久计划）：
- 不做超参数大扫、不做多 seed / 1400ep 重训（C/B 改训练目标与算法 ⇒ **旧权重失效**，最终性能结论必须重训后才有；算力单列）。
- 不实现 **完整 predictive safety filter**（Wabersich 的 MPC 形式）——D 只做 ADR-021 决策 3 要求的"安全层对 AB 与 ED 对称的投影/禁新增"；全 MPC 形式列为长久计划备选。
- 不动核心缓解物理、不改 MT-2、不改断面力口径 SSOT。

## ADDED Requirements

### Requirement: AGENTS.md 文档索引单一化

根 `AGENTS.md` SHALL NOT 复制逐条文档清单；SHALL 以单行指针将"找任何文档"路由到 `docs/README.md`（唯一索引入口），保留 `docs/rules/README.md` 规范指针与「校验能力边界」警示。

#### Scenario: 索引去重
- **WHEN** 检查根 `AGENTS.md` 的「文档索引」区
- **THEN** 不含逐条 `docs/...` 清单，仅指向 `docs/README.md` / `docs/rules/README.md`

#### Scenario: 引用卫生不回退
- **WHEN** 在 `traffic_rl_project/` 运行 `python scripts/check_agents_links.py`
- **THEN** exit 0

### Requirement: P0 三行基线（验证 harness，在改代码之前）

系统 SHALL 在**改动前**的现行代码（断面力口径 + 已修 viol 计数）下，于 `shuozhou_real_53km` 完整剖面产出三行可比结果：M0（规则）、M1（`last` 权重）、M1+`--mask_lever ab`；SHALL 内嵌 `build_metadata` 并时间戳归档、不覆盖旧文件。

#### Scenario: 三行产出
- **WHEN** 依序执行三条 `evaluate_decompose.py` 命令（同剖面/同 max_steps/同 eval_seed，仅自变量不同）
- **THEN** 得到三份结果 JSON，含 `metadata.physics_version` 与逐列明细，可横向对比

### Requirement: A — AB 最小充风时间约束

`MultiLocoController` SHALL 对**每一台机车**维护"最近一次 AB 源释放/应用的时刻"，并在 `get_action_decomposed()` 中 SHALL 拒绝：① 在充风时间不足（< `ab_min_refill_s`）时**新增** AB 源；② 在持续时间不足（< `ab_min_hold_s`）时**释放**已有 AB 源。参数 SHALL 进实验 YAML 与 metadata。

#### Scenario: 抑制缓解—再制动循环
- **WHEN** 策略在充风窗口内请求新增 AB 源，或在保持窗口内请求释放
- **THEN** 该请求被拒（动作回落到规则基线），且 controller 暴露计数（`ab_refill_veto_count` / `ab_hold_veto_count`）供诊断

#### Scenario: 默认值不得拍脑袋
- **WHEN** 设定 `ab_min_refill_s` / `ab_min_hold_s` 默认值
- **THEN** 必须从 `docs/papers/02_rl/Zhang2024_DQN_CyclicBraking_Downhill.txt:566-577` 与项目既有实测（`VALIDATION_BASELINE.md` 空气充风时间项）核定；**无出处则标注 `待核实`，不得编造**

### Requirement: D — 安全层对 AB 的对称权限

`train_env._step_decomposed` SHALL 在 `SafetyLayer.protect()` 之后，对**本步 RL 新增的 AB 源**施加与 ED 对称的**投影 / 禁新增**权限（按**断面力每车视图** + 波速/列长预测式阈值）；SHALL NOT 撤销已建立的 AB 源。

#### Scenario: 高力下禁新增
- **WHEN** 断面力预测峰值 ≥ 阈值且 RL 本步申请新增 AB 源
- **THEN** 该新增源被丢弃（保留规则基线源），并在 `info`/controller 暴露 veto 计数

#### Scenario: 与 ED 权限对称
- **WHEN** 安全层按下调比例钳制 ED
- **THEN** 同一比例应作用于本步新增 AB 源的**深度**（投影），而非只调 ED

#### Scenario: 不恶化（不接受 X4-b 反模式）
- **WHEN** 检查实现
- **THEN** 无"撤销/削减已建立 AB 源"的分支（仅拦新增与投影）

### Requirement: C — 车钩力受控超限项进 reward（断面力口径）

`_calculate_reward_decomposed` SHALL：
1. 车钩力项峰值改用**断面力**（`coupler_interface_forces()` 每列 peak），不再用每车净力；
2. 新增**有界**超限项 `-W_ov · min(peak_norm - 1, OV_CAP)`（`peak_norm<1` 时为 0），`W_ov` 取与速度带项**同量级**、`OV_CAP` 限幅以**避免** `-80·ov²` 式的 value 震荡；
3. 保留原有小幅整形项；SHALL NOT 作"均值最小化"（维持 ADR-014 边界）。

#### Scenario: 破线与不破线可区分
- **WHEN** 峰值 `peak_norm` 跨过 1.0
- **THEN** 奖励出现**有界**的非线性跳变；`peak_norm ≤ 1` 时超限项恒为 0

#### Scenario: 语义可溯源
- **WHEN** 新 reward 生效
- **THEN** metadata 记录 `reward_schema` 版本标识；旧产物可按标识区分

### Requirement: B — per-agent advantage + 信用视界对齐

`MAPPOAgent` SHALL 支持**per-agent 价值头 / per-agent advantage**（CTDE 个体优势；对应 COMA/PRD-MAPPO 一族），替代现行"单标量 advantage 广播到所有 agent"；并 SHALL 支持经实验 YAML 设定 γ/λ 使有效信用视界 ≥ AB→峰值物理滞后窗口（≈90 s）。

#### Scenario: 信用不再被广播
- **WHEN** `critic` 配置为 per-agent
- **THEN** `update()` 的 surrogate 使用 shape `[batch, N]` 的 per-agent advantage，无 `unsqueeze(-1)` 广播

#### Scenario: 结构变更为枚举而非布尔
- **WHEN** 配置 critic 形态
- **THEN** 使用枚举键（如 `critic: centralized_scalar | per_agent`），**不新增布尔开关**；默认值保持 `centralized_scalar` 以零回归、兼容既有 checkpoint

#### Scenario: 视界对齐可验证
- **WHEN** 训练启动
- **THEN** 日志/metadata 打印 γ、λ 与推导出的有效视界（1/(1−γλ) 步 ≈ 秒），并与 ≈90 s 滞后对照

## MODIFIED Requirements

### Requirement: 根 AGENTS.md 导航职责

根 `AGENTS.md` 仍为"导航 + 立论指针入口"，但导航职责收敛为**指向** `docs/README.md`；不承担二级清单、不承载进度表。

### Requirement: ADR-021 状态与排序

ADR-021 的 P0–P3 由"待裁决"推进为"**代码已落地 + 验证另排**"；P0 三行基线作为**改动前**的验证 harness；重训里程碑登记进 `PROJECT_PIPELINE.md` 长久计划。

## REMOVED Requirements

### Requirement: AGENTS.md 内逐条文档索引清单

**Reason**：与 `docs/README.md`（唯一索引入口）重复，双份导航违反 SSOT 且必然漂移。
**Migration**：等价信息已在 `docs/README.md`「快速导航」+「核心思想 → 文档映射」；`AGENTS.md` 改为指针，无信息丢失。