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

## 免重辨识 claim 实验执行规范（2026-09-09，覆盖式修订，当前口径）

> **本节为当前实验体系运行时口径（覆盖式修订，不追加历史）**。SSOT 见 `RESEARCH_POSITIONING.md` §1.6 + `DECISIONS.md` ADR-014。旧口径（如主剖面默认 23.8、跨线方向 23→35km）已过时，以本节为准。

1. **主训练剖面颗粒**：主训练走 `grade_profile: shuozhou_real_53km`（真实朔黄）；跨线域外目标 = `long_downhill_20km` / `long_downhill_35km`；`shuozhou_23800` 仅作已知基线锚，**不作跨线泛化证明**。
2. **跨线免调参协议**：RL 跨线零微调直接评估；MPC 跨线**不重喂 `grade_at`**，并**必须声明 `no-re-identification`**（否则当 strawman）。
3. **指标口径**：主指标 = **跨线免调参级联失败率** / **MPC 求解失败/终端无解次数** / **ATP 触发次数**（替代"追尾"——安全层已杜绝物理追尾，ATP 触发=策略踩线兜底依赖度）。补遗口径：车钩力峰/超限、列距误差、速度带落地率、求解耗时（MPC 每步记录 `solve_times`）。
4. **protocol 标注**：每实验表逐行标 MPC 是否 re-identification / `inner_rule_cyclic`、seed、`simulator_model` 版本（`coupler=MT-2 | braking=ED+AB-relief-wave`）。
5. **全部走 `metadata` 守卫**（`training_metadata_guard`/`save_metadata`）+ 结果 JSON 按时间戳归档到 `outputs/`，**不覆盖旧文件**（复用既有 `metadata.py` / `evaluate_m1_m3_long.py` M-MPC 模式入口）。

## AGENTS.md 引用一致性校验（2026-09-16 强制，防"妄猜规范"）

> **背景**：AGENTS.md 是导航/立论指针层，只放一句话指针，不内联数值（数值会随 SSOT 漂移）。为防止把指针当规范来源去"妄猜"，用脚本在工程层面强制校验引用一致性，不依赖人读。

- **入口**：`python scripts/check_agents_links.py`（在 `traffic_rl_project/` 下运行）。退出码非 0 即存在引用问题。
- **校验内容**：
  1. AGENTS.md 引用的每个 `ADR-<N>` 主编号必须在 `DECISIONS.md` 中真实存在（防 ADR 编号越界/乱编）；
  2. AGENTS.md 引用的 `docs/` 相对路径必须存在（防断链）；
  3. 启发式发现 AGENTS.md 疑似内联"episodes 数值对比"等易腐化数值 → 警告，要求改回指针。
- **强制场景**：任何人/agent 改动 AGENTS.md 或新增 ADR 后、以及正式提交前，运行该校验必须通过（exit 0）。不通过的改动不得合入。
- **SSOT 原则**：AGENTS.md 只许放"指向 SSOT 的一句话指针"；**具体数值/论文佐证一律放 ADR 或 RESEARCH_POSITIONING**，不复制进 AGENTS.md（违背即被此校验警告）。

