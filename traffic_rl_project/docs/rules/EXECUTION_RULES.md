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

> **背景**：历史训练有的含/不含"缓解波"（空气制动缓解波速传播）建模，建模变更前产出的历史结论会失真（同类：Newmark 欠松弛修复前后，见根 AGENTS Gotchas）。为防引用错误历史资产：

1. **追加任何历史资产（实验/诊断/评估/图表）时必须一并记录**（写入 DIAGNOSTICS 或对应卡）：

   - **训练路况**：`--grade`（剖面/场景）、`consist_preset`、ETCS 开关、初始化速度；

   - **完整训练命令**（可整段复制重跑的 CLI）；

   - **seed / 超参 / 配置片段 / checkpoint 标签**（`cp_tag`、`checkpoint_dir`、`results_dir`）；

   - **建模版本声明**：本次运行所用的物理建模集合（含/不含缓解波、是否 100% 动力学、AB 衰减、列尾压强等）。
2. **引用任何历史结论前**：先确认该结论产出于当前建模集合之后；否则**不得直接引用**，须在当前物理上重跑确认后才可引用或引用时显式标注"旧建模下产物，待重跑"。
3. **不得删除**含建模差异的历史记录；但若历史结论被当前建模推翻，在所引处**追加一条 superseded 标注**（不篡改旧文），并指向重跑结果。

## 训练/评估入口必须落权威元数据 metadata（2026-09-08 强制）

> **背景**：结论必须可复现——数值只认 metadata.json / 评估 JSON（禁止从代码注释抽数据），故把 metadata 落盘硬化为入门口令。

1. **训练入口只有两条合法路径，缺一不可，否则该次训练结论视为不成立、不许引用**：

   - **统一框架（推荐，新实验线一律走此）**：`run_training.py` + `TrainRunner.run`，用 `training_metadata_guard`（`with` 包裹含训练循环的全过程）→ 进入自动写 `metadata.json`，训练结束 `finally` 强制 `assert_training_metadata`（缺失抛错）+ 每 ep 自动 best/periodic checkpoint。

   - **legacy 独立入口（仅存量）**：`train_fleet.py` / `train_cyclic_braking.py`，循环前 `save_metadata`（含超参 + 仿真器型号）+ 结尾 `assert_training_metadata` 兜底。

2. **裸写训练循环 / 自定义入口不调 `save_metadata` 或 `training_metadata_guard` 的，一律不认可其结论**；必须补 metadata 落盘后才可采信。

3. **产出论文数据的评估脚本**：必须把 `build_metadata`（git_commit / physics_version / simulator_model 型号 + 全物理配置 / seed / checkpoint 等）内嵌进结果 JSON，并按时间戳归档到 `outputs/`，**不覆盖旧文件**；评估一律 `official_entry_guard`（工况 OFFICIAL，无调试物理）。

4. **新增实验线/新算法** = 写 `configs/experiments/*.yaml` + 注册（自动继承统一框架的 metadata/checkpoint 保护）；不在此框架外的训练结果不得写入论文证据链。

5. **实验数值一律以 `metadata.json` / 评估 JSON 为准**，禁止从代码注释或记忆粘贴实验数值当结论。

## 长训在跑期间的行为性代码冻结（2026-10-01 强制）

> **背景**：1400 ep 级长训要跑很久（ADR-017 / ADR-021 口径**实测 ≈11.7 天/seed**；`REPRODUCIBILITY.md` §十）。训练进程在启动时即把代码载入内存，**之后再改磁盘代码不会影响该进程**——但产出的 ckpt 会与工作树**不再对应**，metadata 里记的 `git_commit` 也无法覆盖未提交改动 ⇒ 结果不可复现、可能误当"当前代码的结果"引用。

1. **冻结范围 = 该 run 的"产物依赖闭包"**：即**训练进程会导入/执行**的一切 —— `src/train_dynamics/**`、`src/environments/**`、`src/controllers/**`、`src/algorithms/**`、`src/trainer/**`、`src/metadata.py`、`src/physics_governance.py`、`run_training.py`，以及它读的 `configs/**`。**做这类改动前，必须先停掉在跑的长训**，或把该 run 的产出标记为"与工作树不一致、不可引用"。
2. **不受冻结约束**（不在闭包内）：`docs/**`、`tests/**`、**纯注释**（不改变任何取值/分支的解释性文字），以及**不被训练进程导入的独立入口脚本**（如 `src/evaluation/evaluate_decompose.py` —— 全仓无任何模块 import 它，训练进程从不加载；它产出的结果 JSON 自带 `git_commit`/`eval_args`，与训练 ckpt 各自独立溯源）。
3. **判定口径（两问）**：①"这处改动会不会改变该 run 的**任何一次 `env.step` / 一次梯度更新 / 一个 YAML 解析结果**？"②"该文件**是否被训练进程导入**（`grep 'import' 全仓确认）？"—— ①会且②是 ⇒ 冻结；否则安全。**别把"在 `src/` 下"当成冻结判据**，判据是"在不在闭包里"。
4. **长训启动时必须登记**：启动器路径、输出目录、日志路径、`metadata.json` 的 `git_commit`、恢复命令（`--resume latest`）与预期机时（见 `REPRODUCIBILITY.md` §十「重训里程碑」模板）。
5. **判活不看日志**：日志为 `>` 重定向 ⇒ 块缓冲，分钟级无新行属正常；一律用 `pgrep -af run_training.py` + `ps -o etime,pcpu -p <pid>`（教训 `LEARNINGS.md` LRN-20261001-014）。

## claim 实验执行规范（2026-09-09 立；2026-10-12 ADR-032 覆盖——claim 改为"编队上下文协同增益"，本节协议仍有效，主指标以 `RESEARCH_POSITIONING.md` §1.6 为准）

> **【superseded（2026-09-16，ADR-016 覆盖 ADR-014 的 Regime B 相关部分）→ 【2026-10-16，ADR-037 废止 Regime A 协议】**：本节旧协议（下方第 2 条）随 Regime B（ADR-016）与 Regime A（ADR-037）先后废止。**当前协议（ADR-037，2026-10-16）**：对比不设"逐线重喂 `grade_at`/在线标定 b0"协议——坡度是 MPC 固有输入（图纸天然先于运营存在），所有方法共用同一仿真器、环境与坡度数据、同档调参力度；D-RL 跨线**严格零微调**（公开声明 "MARL no fine-tuning on target line"）；不作"免重辨识成本"叙事（ADR-032）。SSOT = `RESEARCH_POSITIONING.md` §1.5/§1.6 + `DECISIONS.md` ADR-037。下方旧协议文字原样保留，仅作历史。

> **本节为当前实验体系运行时口径（覆盖式修订，不追加历史）**。SSOT 见 `RESEARCH_POSITIONING.md` §1.6 + `DECISIONS.md` ADR-032（旧 ADR-014/016"免重辨识"立论口径已废止，协议部分仍有效）。旧口径（如主剖面默认 23.8、跨线方向 23→35km）已过时，以本节为准。

1. **主训练剖面颗粒**：主训练走 `grade_profile: shuozhou_ningwuxi_beidaniu_49km`（真实朔黄，2026-10-12 换统一线路表重建，原 `shuozhou_real_53km` 已删除）；跨线域外目标 = `long_downhill_20km` / `long_downhill_35km`；`shuozhou_23800` 仅作已知基线锚，**不作跨线泛化证明**。
2. **跨线免调参协议**：RL 跨线零微调直接评估；MPC 跨线不设重喂/重标定。**【2026-09-16 ADR-016 修订 Regime B → 2026-10-16 ADR-037 废止 Regime A】当前协议**：坡度为 MPC 固有输入，对比共用同一仿真器/环境/坡度数据、同档调参力度，**不标 re-identification、不作成本叙事**；D-RL 跨线**严格零微调**，声明 "no fine-tuning on target line"。
3. **指标口径**：主指标 = **跨线免调参级联失败率** / **MPC 求解失败/终端无解次数** / **ATP 触发次数**（替代"追尾"——安全层已杜绝物理追尾，ATP 触发=策略踩线兜底依赖度） / **列距误差（编队底线，与车钩力并列，2026-10-02 升入主表）**。列距误差口径 = 平均绝对列距误差 / 峰值绝对列距误差 / 全程最小实际列距 / 追尾（物理穿透）步数；由 `evaluate_decompose.py` 结果 JSON 汇报，**多列编组才产出该组键**（单列无列间距）。补遗口径：车钩力峰/超限、速度带落地率、求解耗时（MPC 每步记录 `solve_times`）。
4. **protocol 标注**：每实验表逐行标 `inner_rule_cyclic`、seed、`simulator_model` 版本（`coupler=MT-2 | braking=ED+AB-relief-wave`）（原"标 re-identification"要求已随 ADR-037 废止）。
5. **全部走 `metadata` 守卫**（`training_metadata_guard`/`save_metadata`）+ 结果 JSON 按时间戳归档到 `outputs/`，**不覆盖旧文件**（复用既有 `src/metadata.py`；评估入口 = `evaluate_decompose.py`，MPC 行 `--mpc_type nmpc`。原 `evaluate_m1_m3_long.py` 的 M-MPC 模式入口**已按 ADR-022 删除**）。

## AGENTS.md 引用一致性校验（2026-09-16 强制，防"妄猜规范"）

> **背景**：AGENTS.md 是导航/立论指针层（只放一句话指针、不内联数值，数值随 SSOT 漂移）。为防止把指针当规范来源"妄猜"，用脚本强制校验引用一致性。

- **入口**：`python scripts/check_agents_links.py`（在 `traffic_rl_project/` 下运行）。退出码非 0 即存在引用问题。
- **校验内容**：
  1. AGENTS.md 引用的每个 `ADR-<N>` 主编号必须在 `DECISIONS.md` 中真实存在（防 ADR 编号越界/乱编）；
  2. AGENTS.md 引用的 `docs/` 相对路径必须存在（防断链）；
  3. 启发式发现 AGENTS.md 疑似内联"episodes 数值对比"等易腐化数值 → 警告，要求改回指针。
- **强制场景**：任何人/agent 改动 AGENTS.md 或新增 ADR 后、以及正式提交前，运行该校验必须通过（exit 0）。不通过的改动不得合入。
- **SSOT 原则**：AGENTS.md 只许放"指向 SSOT 的一句话指针"；**具体数值/论文佐证一律放 ADR 或 RESEARCH_POSITIONING**，不复制进 AGENTS.md（违背即被此校验警告）。

## 产物目录规范（outputs/ 布局，2026-10-02 强制）

> **背景**：`outputs/` 长期由各脚本各自落盘，已出现三类乱象：① **同义异构**——`checkpoints_*` / `results_*` / `logs_*` / `report_figures` / `sim_validation` / `phys_validation` / `training_results` 各成一级，分类维度不统一；② **层级错位**——脚本硬编码 `outputs/phys_validation/`，在项目根目录运行时又在根下生出一级目录；③ **无意义目录名**——运行归档叫 `run_<时间戳>`，看名字不知是哪个实验。本规范统一布局与命名，防止继续膨胀。

### 1. 目标目录树（按产物类型分组，不按脚本）

```
outputs/
├── checkpoints/        # 模型权重（实验线子目录：formation/ ab_gate/ ab_smoke/ …）
├── results/            # 结果 JSON/CSV（实验线子目录 + 时间戳文件）
├── figures/            # 展示/论文图（主题子目录；策展目录，允许覆盖）
├── logs/               # 训练日志 + tensorboard
├── sim_validation/     # 物理仿真验证（figures/ + phys_validation/<run>/ 原始归档）
├── smoke/              # 冒烟/调试产物（可随时删）
└── deprecated/         # 作废资产（gitignored，仅回溯；含 README 声明）
```

**一级分类只按"产物是什么"（权重/结果/图/日志/验证/临时/作废），不按"哪个脚本生成"。** 新增一级目录必须登记本规范。

### 2. 命名规则

1. **运行级目录 = 语义前缀 + 时间戳**：`<entry>_<scenario>_<YYYYMMDD_HHMMSS>`
   - 例：`phys_curves_1plus1_53km_20261002_164518`
   - **禁止**裸 `run_<时间戳>` 这类"看名不知义"的目录名。
2. **语义代号**：用清晰代号（`1plus1` / `53km` / `formation` / `decompose`），**禁用 M1/M2/M3** 等无语义编号。
3. **同一图重生成即可覆盖策展目录**（`figures/**`），但**原始归档 `<run>/` 一律不覆盖**（时间戳目录天然隔离）。

### 3. 硬性规则

- **R1 禁止脚本往 `outputs/` 根级或项目根写产物**。必须走统一 `dirs.*` 配置（`checkpoint_dir` / `results_dir` / `figures_dir`）或模块内统一 `outdir` 常量；**禁止硬编码相对路径后在任意 cwd 下运行**。
- **R2 每次"跑"落 `<类别>/<实验线>/<run>/`**，运行目录按 §2.1 命名。
- **R3 结果 JSON/CSV 不覆盖旧文件**（时间戳归档，`EXECUTION_RULES` 既有口径）；展示图允许覆盖。
- **R4 冒烟/调试产物必须落 `smoke/`**，禁止与正式产物混放。
- **R5 作废资产进 `deprecated/`**，保留 + README 声明（物理参数错误 / 仅回溯 / 论文禁引）。
- **R6 短跑（smoke）验证必须同时覆盖 `checkpoint_dir` / `results_dir` / `dirs.figures_dir` 三者**（否则覆写历史，见 `LEARNINGS.md` LRN-20261001-009）。

### 4. 现状 → 目标 映射（已于 2026-10-08 全量执行）

| 现状（一级） | 目标 | 迁移状态 |
|---|---|---|
| `checkpoints_formation/` | `checkpoints/formation/` | 已迁移（2026-10-08） |
| `checkpoints_ab_gate/` `_gate100/` `_smoke/` | `checkpoints/ab_gate/` … | 已迁移（2026-10-08） |
| `results_decompose/` | `results/decompose/` | 已迁移（2026-10-08） |
| `training_results/` | `results/training/`（图并入 `figures/`） | 已迁移（2026-10-08） |
| `report_figures/` | `figures/report/` | 已迁移（2026-10-08） |
| `sim_validation/` | **保持**（已符合） | 已符合 |
| `logs_final_v2/` `logs_final_parallel/` | `logs/final_v2/` … | 已迁移（2026-10-08） |
| `_smoke_pa/` | `smoke/_smoke_pa/` | 已迁移（2026-10-08） |
| `deprecated/` | **保持** | 已符合 |

> **迁移纪律**：批量移动会改到脚本/文档里硬编码的路径，必须**同步 Grep 全仓改旧路径**后再动；长训在跑期间禁止迁移其 `checkpoint_dir`（见本文件「行为性代码冻结」节）。
>
> **进度**：**P1 + P2 完成（2026-10-08）**。P1——`outputs/` 根级 92 个散文件清零：启动器 12 → `scripts/launchers/`；诊断日志 62 → `outputs/logs/diagnostics/`；诊断 JSON 15 → `outputs/results/diagnostics/`；图 1 → `outputs/figures/report/`；历史口径 md 2 → `outputs/deprecated/`。P2——§4 映射表 12 个遗留一级目录全量迁入目标树（`training_results/figures` → `figures/training/`，其余 → `results/training/`），并同步改写全仓引用 178 文件 / 927 处**（含归档 `metadata.json` 内嵌路径，经用户拍板接受；`deprecated/**` 作为冻结作废资产不改写）**。迁移后 `check_outputs_layout.py --strict` 通过。

### 5. 机器校验（守卫入口）

- **入口**：`python scripts/check_outputs_layout.py`（在 `traffic_rl_project/` 下运行）。退出码非 0 即存在违规。
- **校验内容**：
  1. `outputs/` 根级不得出现任何普通文件（R1 的病灶——历史 92 个散文件正是这样堆出来的）；
  2. 一级目录只能是目标树成员（§1）；未登记的新增一级目录直接判错（P2 后 `LEGACY_TOP` 已清空，无需 `--strict`）；
  3. `--strict` 保留为"迁移期"开关（届时回填 `LEGACY_TOP` 把遗留目录降级为警告）。
- **强制场景**：任何人/agent 往 `outputs/` 落产物后、以及正式提交前，运行该校验必须通过（exit 0）。
- **为何校验"落盘位置"而非"训练入口"**：历史守卫（`run_training.py` 的 `dirs.*` 校验 / `official_entry_guard` / `training_metadata_guard`）全在 **Python 入口内**，拦不住"临时脚本 + shell 重定向"（`python tmp_x.py | tee outputs/log_x.txt`）；本校验**不看写入方、只看落点**，与之互补。
- **回归防线**：`tests/test_outputs_layout.py` 已把上述第 1、2 条锁进 pytest。

## 生图规范（图表 / 曲线，2026-10-02 强制）

> **背景**：生图脚本原把"仿真"与"绘图"耦合——每次改图都**重跑整段仿真**（如 53km 32000 步，单次 5 min+），且不看数据是否存在就新建目录；后果是产物堆积、改一次样式要等很久，甚至因选中被中断运行留下的**空壳目录**而误判"缺数据"再重跑。本规范强制分离数据与绘图，并统一图内文字口径。

### 1. 数据与绘图分离（铁律）

- 生图脚本（`src/evaluation/plot_*.py`）必须支持**复用已归档数据重画**：默认自动读取最近一次**含数据的**归档，**不重跑仿真**。
- 仅显式 `--source new`（或等价开关）时才重新仿真，并**新建**时间戳归档。
- 归档必须携带**全部**图的源数据（分场景各一份，如 `scenario_a.npz` + `traj_cyclic_shuozhou.csv` + `coupler_matrix.npz`），**不能只存一部分**；缺的场景数据应在下次运行时**补存**，使下次改样式可全程复用。
- 选"最近归档"时**必须校验该目录确实含所需数据文件**，**禁止只按目录名排序取最新**（否则会选中被中断运行留下的空壳目录，导致误判缺数据而重跑）。

### 2. 落盘二分

- **图 → 策展目录** `outputs/sim_validation/figures/<主题>/`：允许覆盖（对应 §3 R3）。
- **原始数据 → 时间戳归档** `outputs/sim_validation/phys_validation/<语义前缀_时间戳>/`：不覆盖；**复用运行时不得覆写既有归档，也不得新建目录**（仅可补存缺失数据文件）。
- 禁止为"只改样式"另建目录；禁止把图写进归档目录（**图属展示，归档只放数据 + meta**）。

### 3. 图内文字口径

- **一律英文**（图题 / 轴标签 / 图例 / 注释 / colorbar）；中文只出现在代码注释与日志。
- **标题**：陈述式短语，写清"什么物理 / 什么条件"；**禁用** `vs`、斜杠堆术语（如 `A / B propagation (10 kt 1+1 vdp, 200 m/s)`）、`A → B → C` 箭头串、中英混排。需要比较时用 `A under B` 或 `A and B`，**不用 `vs`**。
- **轴标签**：必须写明**物理量 + 单位**（`Coupler force (kN)` / `Speed (km/h)` / `Time (s)` / `Distance (km)` / `Buffer displacement (mm)`）；位置轴写清含义（如 `Vehicle position (0 = head locomotive, 96 = tail locomotive)`）。
- **色标 / 状态**：给可读状态语义（`Air brake state (1 = applied)`），不用裸 `(0/1)`。
- 长轴用**稀疏刻度**；图例 / 字号保证可读。

### 4. 指标口径

- 车钩力一律用**每车钩断面力（kN）**（ADR-018），安全线 1000 kN。

> **SSOT**：AGENTS.md 只放要点 + 本节指针；细节以本节为准。

<!-- 该文档整理/压缩于 2026-10-01 -->
