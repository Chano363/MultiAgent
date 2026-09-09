***

title: 执行规范（贯穿所有阶段）
date: 2026-09-01
status: active
owner: Owner
supersedes: partial（自 PROJECT\_PIPELINE.md 抽出，内容零丢失）
----------------------------------------------------

## 七、执行规范（贯穿所有阶段）

- 环境：WSL2 + conda 环境 `traffic_rl`，GPU 训练，不重复安装

- 代码：PEP 8；临时脚本用后即删

- 训练：检查点定期保存、断点续训、收敛检测；**只使用专业仿真器环境**

- 配置：YAML 用十进制小数（`0.0003` 而非 `3e-4`）；`.get()` 路径与 YAML 严格匹配

- 日志：脚本入口必须 `logging.basicConfig(level=logging.INFO)`

## 历史资产复现元数据与建模差异声明（2026-09-05 强制）

> **背景**：历史训练有的含"缓解波"（空气制动缓解波速传播建模）、有的不含；这类**建模/物理差异**会让产出于建模变更**之前**的历史结论失真（与 Newmark 欠松弛修复后"历史训练/验证都在 75% 动力学下"同类，见根 AGENTS Gotchas）。为防再次引用错误历史资产：

1. **追加任何历史资产（实验/诊断/评估/图表）时必须一并记录**（写入 DIAGNOSTICS 或对应卡）：

   - **训练路况**：`--grade`（剖面/场景）、`consist_preset`、ETCS 开关、初始化速度；

   - **完整训练命令**（可整段复制重跑的 CLI）；

   - **seed / 超参 / 配置片段 / checkpoint 标签**（`cp_tag`、`checkpoint_dir`、`results_dir`）；

   - **建模版本声明**：本次运行所用的物理建模集合（含/不含缓解波、是否 100% 动力学、AB 衰减、列尾压强等）。
2. **引用任何历史结论前**：先确认该结论产出于当前建模集合之后；否则**不得直接引用**，须在当前物理上重跑确认后才可引用或引用时显式标注"旧建模下产物，待重跑"。
3. **不得删除**含建模差异的历史记录；但若历史结论被当前建模推翻，在所引处**追加一条 superseded 标注**（不篡改旧文），并指向重跑结果。

## 训练/评估入口必须落权威元数据 metadata（2026-09-08 强制）

> **背景**：实验数值必须可复现（结论来自 metadata.json / 评估 JSON，禁止从代码注释抽数据）。为保证"规范入口下 100% 自动落盘"，把是否走 metadata 硬化为入门口令。

1. **训练入口只有两条合法路径，缺一不可，否则该次训练结论视为不成立、不许引用**：

   - **统一框架（推荐，新实验线一律走此）**：`run_training.py` + `TrainRunner.run`，用 `training_metadata_guard`（`with` 包裹含训练循环的全过程）→ 进入自动写 `metadata.json`，训练结束 `finally` 强制 `assert_training_metadata`（缺失抛错）+ 每 ep 自动 best/periodic checkpoint。

   - **legacy 独立入口（仅存量）**：`train_fleet.py` / `train_cyclic_braking.py`，循环前 `save_metadata`（含超参 + 仿真器型号）+ 结尾 `assert_training_metadata` 兜底。

2. **裸写训练循环 / 自定义入口不调 `save_metadata` 或 `training_metadata_guard` 的，一律不认可其结论**；必须补 metadata 落盘后才可采信。

3. **产出论文数据的评估脚本**：必须把 `build_metadata`（git_commit / physics_version / simulator_model 型号 + 全物理配置 / seed / checkpoint 等）内嵌进结果 JSON，并按时间戳归档到 `outputs/`，**不覆盖旧文件**；评估一律 `official_entry_guard`（工况 OFFICIAL，无调试物理）。

4. **新增实验线/新算法** = 写 `configs/experiments/*.yaml` + 注册（自动继承统一框架的 metadata/checkpoint 保护）；不在此框架外的训练结果不得写入论文证据链。

5. **实验数值一律以 `metadata.json` / 评估 JSON 为准**，禁止从代码注释或记忆粘贴实验数值当结论。

