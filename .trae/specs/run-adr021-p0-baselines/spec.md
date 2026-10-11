# AGENTS.md 索引去重 + ADR-021 P0 现行口径基线

change-id: `run-adr021-p0-baselines`

## Why

两件事相互衔接：

1. 根 `AGENTS.md` 的「何时读什么（文档索引）」逐条清单与 `docs/README.md`（**唯一索引入口**）内容重复 —— 双份导航违反 SSOT、且必然随文档增删漂移。应改为**单向指针**。
2. `docs/logs/decisions/DECISIONS.md` **ADR-021** 已把「P0（零架构改动、不涉重训）」定为下一步第一优先，但**尚未执行**：目前 53km 的 M0（规则）/ M1（`last`）两行仍是旧口径下的历史产物，且**缺 `--mask_lever ab` 对照**，因此"AB 通道对最终性能是净正还是净负"无法裁定，P1/P2/P3 的取舍没有判据。

## What Changes

- **导航层（BREAKING 于导航职责，不涉代码）**：删除根 `AGENTS.md`「何时读什么」中的逐条文档清单，改为指向 `docs/README.md` 的单行指针；`docs/README.md` 保持唯一索引入口地位（其「快速导航」+「核心思想 → 文档映射」已等价承载该信息）。
- **执行 ADR-021 P0**（复用既有评估器，**不改任何物理/算法代码**）：在现行代码（**断面力口径 + 已修 viol 计数**）下，对 `shuozhou_real_53km` **完整剖面**产出三行可比结果：
  - `M0` = 规则基线（`--mode decompose_m0`）
  - `M1` = `last` 权重（`--mode decompose_m1`）
  - `M1 + --mask_lever ab` = RL 失去 AB 调制权（仅 ED 杠杆）
- 三行结果按 `build_metadata` 内嵌结果 JSON、**时间戳归档不覆盖**；结论追加到 `DIAGNOSTICS_2026-10.md`（append-only），并更新 ADR-021 状态行。

## Impact

- Affected specs：文档导航（SSOT = `docs/README.md`）；ADR-021 P0 判据。
- Affected code：**无代码改动**（仅调用 `traffic_rl_project/src/evaluation/evaluate_decompose.py`）。
- Affected docs：`AGENTS.md`；`traffic_rl_project/docs/logs/diagnostics/DIAGNOSTICS_2026-10.md`；`traffic_rl_project/docs/logs/decisions/DECISIONS.md`（ADR-021 状态）；必要时 `traffic_rl_project/docs/README.md`。

## 事实核定（写规格时已核实，避免规格漂移）

- `src/environments/train_env.py::_update_metrics()` **已是断面力口径**（`coupler_interface_forces()`），违规计数为 `+= int(np.sum(interface > limit))`（车厢·步），**无历史 O(n²) 累加缺陷** ⇒ P0 无需先修计数，只需重跑。
- `src/controllers/multi_loco_controller.py::get_action_decomposed()` 中 `mask_lever == 'ab'` ⇒ **`ab_mod = 0.0`** ⇒ RL **同时失去"抑制 AB"与"提前触发 AB"两种调制**，仅保留规则基线的 AB 与 RL 的 ED 调制。故 `--mask_lever ab` 的准确语义是**"RL 完全退出 AB 决策"**（比 ADR-021 原文"收走 RL 的 AB 新增源通道"更宽），规格以代码为准并在留痕中写明。
- 评估器已支持：`--mode {all,decompose_m1,decompose_m0,mpc,single}`、`--grade shuozhou_real_53km`、`--max_steps 36000`、`--mask_lever {none,ed,ab}`、`--out_suffix`。

## ADDED Requirements

### Requirement: AGENTS.md 文档索引单一化

根 `AGENTS.md` SHALL NOT 复制逐条文档清单；SHALL 以单行指针把"找任何文档"路由到 `docs/README.md`（唯一索引入口），并保留文档规范指针（`docs/rules/README.md`）与校验能力边界警示。

#### Scenario: 索引去重

- **WHEN** 检查根 `AGENTS.md` 的「文档索引」区
- **THEN** 该区不含逐条 `docs/...` 文件清单与"何时读什么"明细，仅有指向 `docs/README.md` / `docs/rules/README.md` 的指针

#### Scenario: 引用卫生不回退

- **WHEN** 在 `traffic_rl_project/` 运行 `python scripts/check_agents_links.py`
- **THEN** exit 0（无断链、无 ADR 编号越界）

### Requirement: ADR-021 P0 现行口径三行基线

系统 SHALL 在现行代码（断面力口径 + 已修 viol 计数）下，于 `shuozhou_real_53km` 完整剖面产出三行可比结果：M0（规则基线）、M1（`last` 权重）、M1+`--mask_lever ab`；SHALL 以 `build_metadata` 内嵌结果 JSON 时间戳归档、**不覆盖**旧文件；SHALL 记录完整命令、seed、剖面与 `physics_version`。

#### Scenario: 三行产出且可比

- **WHEN** 依次执行三条评估命令（同剖面、同 `max_steps`、同 `eval_seed`，仅自变量不同）
- **THEN** 得到三份结果 JSON，均含 `metadata.physics_version` 与逐列明细，可直接横向对比

#### Scenario: 结论留痕与 ADR 状态更新

- **WHEN** 三行数据齐备
- **THEN** `DIAGNOSTICS_2026-10.md` 追加 `### 诊断-2026-10-01-P0 三行基线（现行口径）` 小节（数据表 + 完整命令 + seed/配置 + 物理/机制解释），并在 `DECISIONS.md` 的 ADR-021 状态行标注 **P0 已完成** 与 **AB 通道净正/净负裁定**

## MODIFIED Requirements

### Requirement: 根 AGENTS.md 导航职责

根 `AGENTS.md` 仍为"导航 + 立论指针入口"，但导航职责收敛为**指向** `docs/README.md`；不承担二级清单、不承载进度表、不复制研究阶段细节。

## REMOVED Requirements

### Requirement: AGENTS.md 内逐条文档索引清单

**Reason**：与 `docs/README.md`（唯一索引入口）重复；双份导航违反 SSOT 且随文档增删必然漂移。

**Migration**：等价信息已存在于 `docs/README.md`（「快速导航」表 + 「核心思想 → 文档映射」表）；`AGENTS.md` 改为指针，无信息丢失。