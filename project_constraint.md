# project\_constraint.md — 重载列车 MAPPO 仿真项目约束与规范

> 本文件是**本项目专用**工程/资产约束。**不要封装为全局 Skill**；复制本文件到同类新项目后修改即可复用。
> **使用方式**：按需手动加载（进入本项目时读一遍），不常驻上下文，避免 token 浪费与跨项目污染。
> 本文档仅记约束；项目的立论性规范见 `traffic_rl_project/docs/RESEARCH_POSITIONING.md §1.5`、`DECISIONS.md ADR-010`；文档治理见 `traffic_rl_project/docs/rules/README.md`。

***

## 一、项目参数黑名单（禁止用于正式训练/验证/评估）

以下物理参数/档位**只允许在调试仿真工况**出现；进入官方训练/验证/评估时触发运行时断言异常。

| 黑名单项                                                  | 说明                   | 在何处                           |
| :---------------------------------------------------- | :------------------- | :---------------------------- |
| `enable_cyclic_degrade=True`（AB 循环制动段间衰减 B3）          | 正式工况=关               | `train.py`                    |
| `tail_pressure_kpa != None`（列尾压强平衡梯度 L1）              | 正式工况=None            | `train.py`                    |
| `_brake_reduction_override_kpa != None`（连续减压量覆盖 P0-3） | 正式工况=None            | `train.py`                    |
| `enable_disturbance=True`（牵引扰动注入）                     | 仅扰动鲁棒实验用、非主线         | `train_fleet.py`              |
| Newmark 欠松弛中间量当最终状态                                   | 已修复，禁再用（75% 动力学污染）   | 见 AGENTS Gotchas              |
| 缓解波缺失/含旧 75% 动力学的历史资产                                 | 物理隔离至 `deprecated` 区 | `outputs/deprecated_results/` |

> **原则**：不用 `use_buggy_dynamics=False` 这类布尔关闭开关。改为「工况枚举」显式分流——官方/调试，一体定真象。

## 二、禁止使用的历史/旧开关列表

| 旧开关/旧意图                                      | 处置                      |
| :------------------------------------------- | :---------------------- |
| 三/四层任意布尔关闭错误物理（如 False 关闭衰减、None 关闭梯度）       | 废除，改为**工况枚举** `SimCase` |
| `action_dim=1` 整带平移阈值协同（旧"学无可学"）             | 摒弃为正式架构；保留仅供回溯          |
| `--enable_disturbance` 扰动                    | 仅扰动场景专项用，正式主线禁用         |
| `--no_coupler`（关安全层车钩力钳）                     | 仅安全层消融用，正式禁用            |
| 方案 A（人为坡段错开）逻辑                               | 已移除；正式同坡段起步             |
| `gradle long_downhill` 等"默认 3km 前提型"实验当作正式结论 | 只作单测/形态验证，不进论文          |

## 三、实验引用规范（禁从注释提取数据）

1. **唯一数据源 = 运行时** **`metadata.json`** **+ 评估 JSON**：所有实验数值必须来自运行落盘的 metadata / results JSON，**禁止**从代码注释、文档里复制实验数值当结论。
2. **每运行必需元数据**（自动写入实验目录 `metadata.json`）：

   - git commit 哈希；物理工况版本（`SimCase` 枚举 + 物理配置哈希）；

   - 全部关键动力学参数（mass/v\_max/v\_min/max\_accel/dt/grade/consist/ETCS）；

   - 随机种子（训练/评估 seed）；是否调试模式；入口脚本文件（`__file__`）。
3. **引用历史结论前**：先核对 `metadata` 的物理工况版本与当前一致；产出于建模变更前的结论须在当前物理上重跑或标 superseded（`docs/rules/EXECUTION_RULES.md`）。
4. **资产目录**：`experiments/official/`=正式可论文；`outputs/deprecated_results/`=错误物理历史资产（README 声明"仅回溯、论文禁止引用"）。
5. **评估 JSON 内嵌元数据**（2026-09-06）：评估脚本（如 `evaluate_decompose.py`）把 `build_metadata()`（git commit + 物理哈希 + simcase + seed + eval_args）直接内嵌进每次运行的结果 JSON（`metadata` 字段）——评估每次运行独立成文件，比共享 `metadata.json` 更可溯源。

## 四、训练/评估入口规范（2026-09-06 补录）

| 用途                                       | 唯一正式入口                                                                                | 说明                                       |
| :--------------------------------------- | :------------------------------------------------------------------------------------ | :--------------------------------------- |
| decompose 训练（ADR-009 正式架构）               | `python src/trainer/train_fleet.py --decompose loco_ed_ab --decision_interval 10`     | 已接 SimCase 门禁 + metadata 落盘              |
| decompose 评估                             | `python src/evaluation/evaluate_decompose.py`                                         | 已接入口守卫 + 元数据内嵌结果 JSON                    |
| 旧架构评估（l1_long / m1\_m3\_long / fleet\_hier） | 仅供回溯对比，论文不引用                                                                          | 已插入 `official_entry_guard`，结论引用前须核对物理版本   |

> **原则**：decompose 是唯一正式架构入口；其余训练脚本（train\_cyclic\_braking / train\_dqn\_cyclic / train\_fleet\_dqn）与旧评估脚本属于历史架构，产出仅供回溯，不得作为论文结论来源。

## 五、工程范式速记

- **工况枚举**：`SimCase.OFFICIAL / DEBUG_SIMULATION`，以物理配置对象驱动，不做布尔关闭开关。

- **参数中心化**：训练/验证/测试共用同一 `PhysicsConfig`；任何脚本 `import` 它，禁止手写 v\_max/mass 等物理值。

- **运行时断言**：train/validate/evaluate 入口先 `assert_case_allows()`,调试仿真工况进入训练/验证立即抛异常；官方脚本不 import 调试模块。

- **物理隔离**：`deprecated_results` 独立 README + 迁移错误物理的日志/权重；代码注释里的错误数值清空。

