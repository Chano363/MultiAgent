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

## [LRN-20260930-004] correction（训练框架 / 续训）

**Logged**: 2026-09-30
**Priority**: high
**Status**: resolved（ADR-019 已治本）
**Area**: trainer

### 现象：`--resume` 路径写错 / 文件不存在 → **静默从头重训**，不报错、白跑数小时

- **期望 vs 实际**
  - 期望：给定 `--resume <ckpt>` 就该从该权重接着训。
  - 实际：旧实现是 `if resume_pt and Path(resume_pt).exists():` —— **路径不存在就直接跳过加载分支**，既不报错也不提示，直接 from-scratch 重训。现实复现：`PROJECT_PIPELINE.md` 记载 5-seed 长训"**原 launch resume 源已 MISS**"，权重停在 ep 992/992/521/661/671。
- **根因**：把"是否续训"交给 `Path.exists()` 的**静默布尔**决定，且没有任何"我打算续训但没成功"的守卫；`--episodes` 语义又只是"再跑 N 集"，人工算剩余集数时连"其实没续上"也看不出来。
- **解决**：
  1. `resolve_checkpoint()` 对不存在的路径**直接抛 `FileNotFoundError`**（禁止静默从头）；支持具体文件 / `latest|last` / 目录自动取最新 `_ep{N}`。
  2. `--episodes` 改为**总目标集数**语义，`plan_run_episodes()` 算实跑集数并校验（目标 ≤ 已训 → 抛错）；启动即打印 `[resume] 源权重 … | 已训 N ep | best …`。
  3. 进度**内嵌 checkpoint**（`metadata.done_ep`），换目录/丢 history 也能续上。
- **预防**：凡是"可选地做某件重活"的分支，**默认必须显式报告它是否真的做了**（日志 + 缺省报错），不能靠 `if exists()` 静默降级；入口参数语义要在 `--help` 与启动日志里写明。
- **类型标签**：`训练框架` / `续训` / `静默降级`

---

## [LRN-20260930-005] correction（checkpoint / CUDA 设备）

**Logged**: 2026-09-30
**Priority**: medium
**Status**: resolved
**Area**: algorithms

### 现象：续训恢复 torch RNG 时 `TypeError: RNG state must be a torch.ByteTensor`

- **期望 vs 实际**
  - 期望：`load()` 恢复 `torch_rng_state` 后续训可复现（CPU 单测通过）。
  - 实际：训练端 `device=cuda`，`torch.load(path, map_location=self.device)` 把 `torch.get_rng_state()`（CPU `ByteTensor`）**一并搬到 GPU** ⇒ `torch.set_rng_state()` 只接受 CPU `ByteTensor`，**抛 TypeError**。CPU 单测**测不出来**（map_location='cpu' 不产生搬移）。
- **根因**：`map_location=device` 作用于 checkpoint 的**所有** tensor，包括"非模型参数的状态量"（RNG 状态、可能还有别的标量张量）；而这类状态量的**消费方对 device 有隐式要求**。
- **解决**：`torch.set_rng_state(st.cpu() if torch.is_tensor(st) else st)`；并补 **CUDA 条件单测**（`skipif not torch.cuda.is_available()`）复现该路径。
- **预防**：凡"把非模型状态塞进 checkpoint"必须问一句"**它被搬到 GPU 后消费方还认吗**"；涉及 device 的加载路径不能只在 CPU 上测。
- **类型标签**：`checkpoint` / `CUDA` / `测试盲区`

---

## [LRN-20260930-006] correction（训练框架 / off-by-one）

**Logged**: 2026-09-30
**Priority**: medium
**Status**: resolved
**Area**: trainer

### 现象：`last.pt` 内嵌 `done_ep` 比文件名 `ep{N}` **少 1** → `--resume latest` 少算已训集数

- **期望 vs 实际**
  - 期望：`mappo_fleet_last_ep3_*.pt` 的内嵌 `done_ep` = 3；`--resume latest` 报告"已训 3 ep"。
  - 实际：内嵌 `done_ep` = 2（文件名 3）⇒ `--resume latest --episodes 5` 报"已训 2 ep，本轮跑 3 ep"，**多跑 1 集**。
- **根因**：`TrainingLogger.ckpt_meta=lambda: self._ckpt_meta_now(global_ep, best_reward)` 闭包捕获的是**自增前**的 `global_ep`（循环体内 `global_ep` 是"已完成集数"，在 `global_ep += 1` 之后才等于本集编号），而 `save_last(namer)` 命名用的是 `global_ep + 1` ⇒ 命名与 metadata **各用一套口径**。
- **解决**：lambda 改 `self._ckpt_meta_now(global_ep + 1, best_reward)`；此后 `metadata.done_ep` / history 行数 / 文件名三信号一致。
- **预防**：同一"集编号"在**命名、metadata、日志**三处必须来自**同一个表达式**；`dump 前算一次、存到局部变量**再复用，避免闭包里被后续自增悄悄改值。诊断入口加"多信号一致性打印"（`[resume] 进度信号 {…}`）能在续训时立刻暴露这类偏差。
- **类型标签**：`训练框架` / `off-by-one` / `闭包陷阱`

---

## LRN-20260930-007 · 「发散」结论必须落到可观测口径；安全层**权限边界**须与文档一致

- **现象**：PPT 问题页与项目叙事长期写着"长训后期**价值函数发散**、策略破线后**难以回退**"，用作解释 5-seed 训练中的车钩力破线。本次复核（见 `DIAGNOSTICS_2026-09B.md`「诊断-2026-09-30-『长训后期 value 发散』复核」）发现该表述**与可观测量不符**。
- **期望 vs 实际**：
  - 期望：长训后期 `value_loss`/回报出现单调恶化，破线后不可回退。
  - 实际：① 分箱回报**无退化**（seed0 跑到 ep1662，100 集分箱 R_avg 恒在 10.2k–11.3k）；② 破线是**孤立 episode 且次集即自恢复**（v2 seed1 ep1045 pk 1429 kN/viol 1248 → ep1046 viol 0）；③ **破线相位因 seed 而异**（seed3 最差在 ep100–199，seed0 最差在 ep1400–1499 且其后归零）——无共同"后期"拐点。
- **根因（三层追）**
  1. **表象**：PPT/叙事把"车钩力破线"解释成"value 发散"，但拿不出 `value_loss` 曲线。
  2. **机制（两条，各自独立）**：
     - **结论先于测量**：`src/trainer/logger.py:116-121` 只落盘 6 个 scalar，**没有 `value_loss` / `value_norm_mean/std` / `entropy` / `approx_kl`**；history CSV/JSON 只有 4 列。`mappo_agent.py` 明明算出了这些量（`:538-564`）却没写出去 ⇒ "value 发散"**不可证伪**，属于把推测当结论。
     - **安全层权限边界与文档不一致**：`SafetyLayer.protect()` 在 decompose 路径的返回值**只回写 ED 通道**（`train_env.py:522-524`），`ab_sources`（`:474-490` 组装）**原样**送入动力学（`:528`）；安全层能把 `ab_command` **升级**为 EMERGENCY（`:517-520`）却**从不削减已发出的 AB 源**。而 `_step_decomposed` docstring 声称"再映射回 (ED,AB)"——**文档承诺了没有实现的权限**，导致"已下发安全层为何还破线"长期无法解释。此外闸门的两条判据（反应式 `p0≥0.6·limit`、预测式 `rate·horizon`）在 **AB 波起始处同时静默**（实测力低、上升率≈0），波前叠加 ~70 步后才穿越 1000 kN。
  3. **为什么没早发现**：`logger.py` 落盘字段清单从未与 `mappo_agent` 的返回量做过对照（无"返回即落盘"的单测）；docstring 声明的通道改写也没有断言该通道真的被改写；闸门效果只用 **100 集短训玩具 ckpt**（`outputs/checkpoints/ab_gate100`）验证过（`outputs/logs/diagnostics/log_diag_regress_20260930.json` 的 `ckpt` 字段），**从未在生产 checkpoint 分布上验证**。
- **解决（进行中）**：
  - 叙事改为可观测口径："孤立、自恢复的车钩力破线 episode"，并把"value 发散"降级为**待测量**项。
  - 待做 X1（用生产 checkpoint 重跑闸门回归，检验闸门是否只在 100 集玩具 ckpt 上有效）/ X2（补落盘 value/entropy/KL）/ X3（记录在飞 AB 源）/ X4（给安全层"在飞波"锁或削减权限的反事实）。
  - **证明已修好（部分）**：诊断数据已入档（`DIAGNOSTICS_2026-09B.md`「诊断-2026-09-30-『长训后期 value 发散』复核」）；X2 落盘后须复测并回填本条目。
- **止血与预防**：
  - **写结论前先问"这个量有落盘吗"**：无测量 → 只能写"待测量"，禁止用"发散/崩溃/失稳"这类**有量纲后果**的词描述未观测现象。
  - **文档-代码一致性**：凡 docstring 声明"映射回 (ED,AB)"之类的**权限承诺**，必须有一条单测断言该通道真的被改写；本次已发现该 docstring 与实现不符。
  - 闸门/安全层的验证 checkpoint 必须与**生产训练分布**同源；用短训玩具 ckpt 验证得到的"0 步超限"不得作为生产保证（E7）。
- **类型标签**：`训练数值` / `工具链`
- **回填（2026-09-30 同日，本条目"待测量"项的进展）**：X1/X4 已完成（见
  `DIAGNOSTICS_2026-09B.md`「诊断-2026-09-30-X1/X4 判别性实验」）；X2 已落代码并单测通过
  （见「改造-2026-09-30-X2」+ `LRN-20260930-011`）；X3（在飞 AB 源时序）由 X4-a 的
  `_air_brake_pending`/`_air_brake_releasing` 观测部分覆盖（在飞命中 1199/1200 步），
  **未**单独落盘逐源时序。新增教训见 `LRN-009`（采样态）与 `LRN-010`（闸门 no-op）。

---

## LRN-20260930-008 · metadata 的 `physics` 块固报固版默认编组（1+0），与运行实况（1+1）不一致

- **现象**：复现路径 —— 读任意一次主实验产出的
  `outputs/checkpoints/formation/final_seed1_v2/results/metadata.json`，见
  `env_cfg.consist_preset=10kt_1plus1` 与嵌套 `physics.physics.consist_preset=10kt_1plus0` 并存；
  `simulator_model` 串内为 `consist=10kt_1plus0`，`simulator_model_version` 连带走样。
  溯源见 `DIAGNOSTICS_2026-09B.md`「诊断-2026-09-30-metadata 编组不一致溯源」。
- **期望 vs 实际**
  - 期望：metadata 的 `physics` 块反映**本次运行**的物理配置，与 `env_cfg` 一致
    （铁律「训练/验证复用同一套物理配置对象」+「结果数值以 metadata 为准」）。
  - 实际：`world_cfg = official_world_config(PhysicsConfig())`（`src/trainer/train_runner.py:77`）
    由 `PhysicsConfig()` **固版默认值**构造，不派生自本次 run 的 env_cfg；
    `src/physics_config.py:21` 的 `consist_preset` 默认值仍是 `10kt_1plus0`
    （同文件 `grade_profile` 已于 2026-09-09 改为 `shuozhou_real_53km` ⇒ 更新不完整）。
- **根因（三层追）**
  1. **表象**：`metadata.json` 中 `env_cfg` 与 `physics` 两处编组互相矛盾。
  2. **机制**：official 快照的定位是"固版/哈希/断言基线"（本就不跟随 env_cfg），
     但 metadata 的 `physics` 块**直接复用了它** ⇒ "基线快照"被当"运行配置"上报；
     且 `PhysicsConfig.consist_preset` 全仓**零读取者**（消费方走
     `config.get('consist_preset')`，如 `src/environments/train_fleet_env.py:90`）——
     死字段无人读，过期无人察。
  3. **为什么没早发现**：守卫只比对 `_OFFICIAL_LEGAL` 里 3 个调试开关
     （`src/physics_governance.py:27-34`），`consist_preset` 不在其中 ⇒
     `assert_case_allows` 对该键不比对、静默放行；且没有任何测试断言
     `metadata.physics` 与本次 `env_cfg` 一致。
- **解决**：改 `src/physics_governance.py` —— 新增 `RUN_DERIVED_KEYS=("consist_preset",)`，
  `official_world_config(physics, env_cfg=None)` 按该清单用 `dataclasses.replace`
  从本次 env_cfg 派生（不传 env_cfg 则行为与旧版完全一致）。四处入口接线：
  `train_runner.py:77-79`、`train_fleet.py:136`、`train_cyclic_braking.py:268`、
  `evaluate_decompose.py:40-45/243-249`（后者新增 `run_consist(mode)`，与 `make_env` 共用同一表达式）。
  **证明已修好**：新增 `tests/test_physics_governance.py`（6 项：不传 env_cfg 保持旧行为 /
  派生生效 / 其余物理项不漂移 / 空值不覆盖 / `simulator_model` 与哈希随编组变化 / 派生键已登记），
  `python -m pytest tests/test_physics_governance.py -q` → **6 passed**；全量
  `python -m pytest tests/ -q` → **198 passed（exit 0）**（产物
  `outputs/logs/diagnostics/log_pytest_20260930_metadata_fix.txt`；因 `pytest.ini` 已含 `-q`，CLI 再传 `-q`
  合成 `-qq`，日志仅打进度点、末行汇总被抑制，计数由点数 198 + 退出码 0 共同判定）。
- **止血与预防**
  - 本次怎么绕开：读 metadata 判定编组一律以 `env_cfg` 为准，`physics` 块只信物理项；
    既有 `final_seed*_v2` 的 `consist=` 与 `physics_version` 仍为旧值，未重跑即不改写。
  - 长期如何不再犯：
    ①**"固版快照"与"运行配置"在 metadata 里必须分列**，凡"由默认值构造"的 dict
    落进 metadata 都要问"它真的代表本次运行吗"；
    ②凡进入 `simulator_model` / `physics_version` 指纹的字段，都应登记进
    `RUN_DERIVED_KEYS` 或 `_OFFICIAL_LEGAL`，否则哈希覆盖不到它、
    "型号变更必改哈希"的承诺失效（已由 `test_run_derived_keys_are_declared` 兜住）；
    ③无人读取的新物理字段视为**待接线/待删债务**，不是"已实现"；
    ④`grade_profile` 属同族残留风险（跨线换剖面时同样需登记并传参）。
- **类型标签**：`参数配置` / `工具链`

---

## LRN-20260930-009 · 诊断 rollout 的动作产生方式（确定性 vs 采样）决定能否复现"破线"数值

- **现象**：用生产/玩具 ckpt 重跑闸门回归时，**确定性** `select_actions(deterministic=True)`
  下玩具 ckpt 全程 **0 破线**（628.1 kN），无法复现历史
  `log_diag_regress_20260930.json` 记录的 `full_nogate 1156.7 kN / 17 步破线`；
  改成**采样**（`deterministic=False`，同 `seed=2000`）后得 **1268.9 kN / 29 步**——同量级、不同值。
- **期望 vs 实际**
  - 期望：同一 ckpt + 同一 harness + 同一 seed ⇒ 同一曲线，可逐位复现。
  - 实际：历史脚本的动作按**分布采样**产生，本 harness 用**均值**（确定性）；
    两者是不同策略行为，前者的"破线"属**采样探索态**，且依赖采样流（同一 seed 不同脚本
    RNG 消耗次序不同 ⇒ 数值亦不同）。
- **根因（三层追）**
  1. **表象**：同一 ckpt 在同剖面同窗口，一次"破线 1156.7"、一次"0 破线 628.1"。
  2. **机制**：破线由**策略输出的极端动作**驱动；采样会踩到均值分布之外的 AB 新增源，
     均值则是温和的"驱动策略"。因此"破线"是**动作分布尾部**的性质，不是该权重的
     确定性性质。`select_actions(deterministic=...)` 一个布尔量就切换了这两种世界。
  3. **为什么没早发现**：诊断脚本未在文档/产物中记录 rollout 模式；harness 一致性只被
     `no_rl`（纯规则、与策略无关）间接锚定，恰好绕过该差异。本 harness 的 `no_rl`
     768.1 与历史 767.7（Δ0.4 kN）一致 ⇒ 两 harness 同构，差异只可能来自策略动作的产生方式。
- **解决**：在临时诊断脚本中新增 `--stochastic` 并**两种模式都跑**，把模式写进产物 JSON
  （`"stochastic": true/false`）与条目表格；历史 regress 的 `full/full_nogate/no_traction*`
  绝对值标注为"采样探索态、不可逐位复现"（不变更历史产物，只加引用纪律）。
- **止血与预防**
  - **诊断/评估脚本必须显式声明并落盘 rollout 模式**（确定性 or 采样 + seed），
    否则数值不可复现、不可比；
  - **跨脚本比对前先跑一个"与策略无关"的锚**（如 `no_rl`/`no_ab`），它能把
    "harness 差异"与"策略行为差异"分开——本次正是靠它定位到采样假设；
  - 论文/文档引用破线数值时，必须与**同模式**的评估并列，禁止把采样态数值写成"该策略的性能"。
- **类型标签**：`工具链` / `训练数值`

---

## LRN-20260930-010 · 只约束"RL 新增 AB 源"的安全闸门，在不用该通道的确定性策略上是 no-op

- **现象**：ADR-018 的 AB 闸门（`AB_ADD_SOURCE_MAX_RATIO=0.6` + `AB_MAX_CONCURRENT_ADD=1`
  + `SafetyLayer.ab_new_source_veto`）在生产 ckpt 上 **on/off 轨迹逐位相同**：
  `final_seed0_v2/last_ep1043` 两种设置同为 **761.0 kN / 0 破线**，
  `final_seed1_v2/last_ep1043` 同为 **627.1 / 0**（`veto` 命中 361/60 步却零影响）；
  玩具 ckpt 确定性 639.5 (on) vs 628.1 (off)，也近乎无差别。只有在**采样探索态**
  闸门才显出效果（1165.6 on vs 1268.9 off，−103 kN / −7 破线步，且**仍未守住 1000 kN**）。
- **期望 vs 实际**
  - 期望：闸门"已验证有效"（历史短训：AB 激活 + 末段 pkCpl 980.9 kN）。
  - 实际：闸门只拦 `final[i,1]` 由 **RL 提前触发**新 AB 源这一条路径
    （`multi_loco_controller.get_action_decomposed` 的 `ab_mod < -0.15` 分支）；
    若策略（驱动态）根本不走这条分支，闸门再"命中"也不改变任何动作 ⇒ **no-op**。
- **根因（三层追）**
  1. **表象**：同一闸门在玩具 ckpt 上"有效"、在生产 ckpt 上"完全无效"。
  2. **机制**：安全机制的**有效域 = 它约束的动作子集 ∩ 策略实际使用的动作子集**；
     本项目闸门约束的是"RL 新增 AB 源"，而规则基线循环制动触发的 AB 源**不经过闸门**
     （`get_action_cyclic_braking` 的兜底路径），故基线通道的 AB 冲击始终不受闸门管辖。
  3. **为什么没早发现**：验证只在"会用 AB 杠杆"的 100ep 探索态 ckpt 上做，
     且未做**on/off 隔离对照**（未量化闸门自身贡献）；验收时把"探索态峰值下降"
     读成了"闸门有效"。
- **解决**：完成 on/off 隔离对照（X1）+ 反事实（X4-a 在飞波锁：把新增源锁死后
  1268.9→777.1 kN、破线 29→0，机制确证但 1199/1200 步全锁、等于废掉 AB 杠杆；
  X4-b 允许削减已发 AB 源：1268.9→1323.5 kN、破线 29→103，**反证恶化**）。
  结论：**修订 ADR-018 的效力表述**，闸门不得写作"已在生产策略上验证有效"。
- **止血与预防**
  - **安全机制的 KPI 必须用 on/off 隔离对照给出**（关掉它，看指标差多少），
    而不是"开了它之后指标变好"（后者混入了探索/训练变化）；
  - **验证权重必须与目标分布同源**：驱动（确定性）策略与探索（采样）策略是两种分布，
    安全机制的效力须在**驱动态**上给结论；
  - **写"闸门有效"前先问：策略真的走这条通道吗？**（本条即"约束子集 ∩ 使用子集 = ∅"）；
  - 撤销/削减已发 AB 源会制造"缓解—再制动"循环（与"缓解不同步是车钩力主因"同源），
    **不要**把它当解法。
- **类型标签**：`算法逻辑` / `物理建模`

---

## LRN-20260930-011 · 算了但没落盘的指标 = 不可证伪（"value 发散"曾因此无法判定）

- **现象**：复核"训练后期 value 发散"时，`results/train_history_*.csv` 只有
  `total_loss`；`value_loss / entropy / grad_norm` 在 `MAPPOAgent.update()` 里算完
  **直接丢弃**，`approx_kl`（早停判定量）与 `value_norm_mean/std`（PopArt 尺度）
  **压根没进返回 dict** ⇒ 该叙事既不能证真也不能证伪。
- **期望 vs 实际**
  - 期望：任何被用来解释训练行为的量，都在日志/CSV/TB 里。
  - 实际：日志白名单只放行 `total_loss` 一个标量；其余计算纯属浪费。
- **根因（三层追）**
  1. **表象**：`update()` 返回 5 个标量，落盘 1 个。
  2. **机制**：日志层（`TrainingLogger.log_episode`）参数表只声明了
     `total_loss`，训练框架调用处也只传它 ⇒ **"算了"与"记了"之间没有强耦合**。
  3. **为什么没早发现**：`total_loss` 一直是"够用"的看板指标；
     只有当需要判断**value 尺度漂移**这类二阶现象时，缺列才暴露。
- **解决**：`update()` 补 `approx_kl/value_norm_mean/value_norm_std` 并统一 4 处早退路径
  的字段（`_zero_stats()`）；`TrainingLogger` 新增**独立** `train_loss_{tag}.csv`
  （plus TB scalars + 终端显示）；刻意不给 `train_history_*.csv` 加列以免破坏续训 append
  的行列一致性（ADR-019）。单测 `tests/test_logging_metrics.py`（4 项）；
  **证明已修好**：`python -m pytest tests/test_logging_metrics.py tests/test_mappo_train.py -q`
  → 10 passed，全量 `python -m pytest tests/ -q` → **202 passed（exit 0）**
  （产物 `outputs/logs/diagnostics/log_pytest_20261001_x2.txt`）。
- **止血与预防**
  - **"算了的量"要么落盘、要么删掉**——不落盘的中间量是"不可证伪的伪证据"；
  - 新增日志字段时**优先新开窄表**（按主题分文件），避免给既有 CSV 加列导致 schema 漂移
    （与"续训不截断既有 CSV"的约定冲突）；
  - 早退/跳过路径的返回 dict **字段必须与正常路径一致**，否则下游按列读会静默错位。
- **类型标签**：`工具链` / `训练数值`

---

## LRN-20261001-001 · 断言"数据不存在"前必须按**实验语义**全仓复查（不能只搜变量名/只看 deprecated）

- **现象**：我据一次 `grep decompose_M0` 的结果断言"**全剖面（53km）D-RL vs D-Rule 头对头在当前物理下不存在**"，
  并据此提议先重跑；用户直接指出"**都有结果了你自己找找**"。复查后证实用户正确：`outputs/results/decompose/`
  下现存多份 `decompose_m1_*_53km`（`ep841`(5 seed) / `ep1623` / `ep1521` / `best_s0` / `best_s1` / `ep2265`），
  且方向与我的暗示**相反**（`last` 权重守得住红线且不输规则层）。
- **期望 vs 实际**
  - 期望：说"没有证据"之前，已确认现有资产里确实没有可回答该问题的数据。
  - 实际：缺的只是**M0（规则行）这一行**，被我扩大成"**整张表**都不存在"；
    且我默认了"历史跨线/长程评估只在 `deprecated/`"，忽略了 `outputs/results/decompose/` 里按
    `_53km` 命名的 M1 评估。
- **根因（三层追）**
  1. **表象**：一次 grep 的 0 命中 → 直接写成"不存在"。
  2. **机制**：我按**变量名/目录名**（`decompose_M0` 字符串；`deprecated/` 语义）检索，
     而资产是按**实验语义**命名与摆放的（`*_53km`、`results/decompose/`）——
     检索口径与资产组织口径不一致，必然漏检。
  3. **为什么没早发现**：把"某一行的缺失"当成了"整张表的缺失"，且**没有先问用户**
     （用户显然知道资产在哪，这是当场被纠正的直接原因）。
- **解决**：按实验语义全仓复查（`*_53km`、`results/decompose/`），把 `last` / `best` / `ep120` / `ep2265`
  四类权重在 53km 的表现一并列表；在 `DECISIONS.md` ADR-020 与 `DIAGNOSTICS_2026-09B.md` 对应条目
  **原位追加"更正"行**（不复写历史）。
- **止血与预防**
  - 断言"**无数据**"前，必须按**实验语义**（场景 / 剖面 / 步数 / 权重代数）遍历一遍，
    而不是只搜某个变量名或只看某个目录；
  - 严格区分「**某一行缺失**」与「**整张表缺失**」——前者只需补齐一行，后者才需重跑；
  - **先问用户**：涉及"要不要花算力重跑"时，先确认既有资产，再谈新增实验（本次用户即为纠正者）。
- **类型标签**：`工具链`

---

## LRN-20261001-002 · "AB 用得多 ⇒ 车钩力峰值高"是**未被数据支持的直觉**（跨权重单调相关被否证）

- **现象**：归因"MARL 破线"时，一度把"奖励倒逼用 AB"直接推到"**AB 步数越多 → 峰值越高**"的结论。用既有 53km 资产核对后**不成立**：
  `s0_ep1623` `ab_steps=10753`（全表最高之一）却 **863.5 kN / band 99.7%（安全）**；
  而 `best_s1` `ab_steps=6591`（更低）反而 **1250.9 kN（破线）**。
- **期望 vs 实际**
  - 期望：AB 是冲击主源 ⇒ 用量应与峰值正相关，可作为"减 AB 用量"的改造依据。
  - 实际：跨权重无单调关系；真正的判别量是 **AB 新增源的时空分布**（同一时刻多源叠加 / 集中在列尾时才破线）。
- **根因（三层追）**
  1. **表象**：受控实验（X4-a「在飞波锁」：禁止在飞波期间新增源 → 1268.9→777.1 kN / 0 破线）确实显示"新增源"是破线通道，于是把"通道重要"误读成"用量正比"。
  2. **机制**：`ab_steps` 是**整段累计计数**，丢失了"何时 / 在哪节机车 / 同时几个源"的信息；而破线是**时空叠加**现象（同刻多源 + 列尾位置）。累计量对时空分布不敏感 ⇒ 两者本就不该单调挂钩。
  3. **为什么差点写错**：受控实验支持的是"**限制新增源**"（机制），不是"**减少用量**"（剂量）；把机制结论外推成剂量结论，缺一步数据核对。
- **解决**：改用"**新增源时空分布**"作为解释与改造靶点（ADR-021 方向 2：错峰 / 单位长度源密度上限 / 有界配额）；把否证过程写入
  `DIAGNOSTICS_2026-10.md`「诊断-2026-10-01」§六（诚实留痕，不删直觉版结论）。
- **止血与预防**
  - **别把"机制重要"外推成"剂量正比"**：控制/物理里"某通道必要"≠"用量越大越差"；
  - **累计标量对时空分布不敏感**——下这类结论前先取**逐列 / 逐时刻**明细（项目规范本就要求"逐列逐工况记录"）；
  - 提出相关性论断时**先用手头既有资产核对**，再决定是否值得重跑（沿用 LRN-20261001-001）。
- **类型标签**：`算法逻辑` / `物理建模`

---

## LRN-20261001-003 · 「改动前基线」与「并行改代码」冲突：须用冻结代码副本（`git worktree`）解耦

- **现象**：要跑"改造前"的 53km 三行基线（P0），同时又想立刻在**同一工作树**里改 A/C/D/B 四处代码。但基线是**三条串行 python 进程**——第 2、3 条会在**启动时重新导入源码**，于是只有第 1 条真的是"改动前"，后两条会被污染成"改动后"，而结果看起来完全正常（静默错误）。
- **期望 vs 实际**
  - 期望：要么全程串行等完（浪费 1~2 h 且阻塞所有改动），要么并行又保住语义。
  - 实际：一开始"让后台任务自己跑、我同时改代码"是**错的**——同一工作树里，后启动的进程读到的是新代码。
- **根因**：Python 在**进程启动时**导入模块；"基线"语义取决于**进程启动那一刻的磁盘内容**，不取决于"我在什么时候开始动手"。
- **解决**：用 `git stash create`（**不动工作树**、不入 stash 列表）取当前工作树的 commit SHA，再 `git worktree add --detach <持久路径> <SHA>` 建**冻结副本**，在副本里跑基线；主树立刻可自由改代码。评估的 metadata 仍正确（`git_commit` = 该冻结 SHA，可精确定位代码状态）。
- **止血与预防**
  - "改动前/后对照"这类**语义依赖代码版本**的长跑，必须**冻结副本**（worktree / 独立 clone），不要靠"我快一点"；
  - 冻结副本要放**持久文件系统**（见下条），别放 `/tmp`；
  - 结果 JSON 需**回拷**主树并声明其 `git_commit` / `physics_version`（本次冻结 SHA `d6ba3540`）。
  - ⚠️ **本条不足以冻结代码**：`git worktree` 副本会被 editable 安装击穿（`import src` 仍走主树），
    必须配合 `tmp_p0_freeze_boot.py` 把副本根显式插入 `sys.path` 并断言 —— 见 **LRN-20261001-006**。
- **类型标签**：`工具链` / `训练数值`

---

## LRN-20261001-004 · WSL `/tmp` 是 tmpfs（VM 重启即清空）；`pkill -f` 会命中自身命令行

- **现象（两个独立工具链坑，同轮踩到）**
  1. 把冻结副本建在 `/tmp/p0freeze` 后，后台任务**反复莫名失败**；复查发现 `/tmp` 已被清空、worktree 被标 `prunable` —— **WSL 虚拟机重启（无进程时自动休眠）会清掉 tmpfs**，连带杀掉后台进程。
  2. 用 `pkill -f "evaluate_decompose.py"` / `pkill -f "p0freeze/traffic_rl_project"` 清理进程时，**把自己也杀了**（命令自身的命令行里就含该字符串），Shell 返回 exit 15（SIGTERM），清理反而中断。
- **期望 vs 实际**：期望"写进 /tmp 的长跑产物在会话间存活"、"按名字杀进程只杀目标"；实际两者都不成立。
- **根因**：① `/tmp` = tmpfs（内存，VM 生命周期）；② `pkill -f` 匹配的是**完整命令行**，而发起清理的那条命令自身也含有该模式。
- **解决**：① 长跑产物与冻结副本一律放**持久路径**（如 `/mnt/d/Code/_p0freeze`）；② 清理用**正则括号技巧**（`pkill -f "evaluate_decompose[.]py"`，自身命令行里的字面量是 `[.]` 不匹配该正则）或**按 PID** 精确 kill。
- **止血与预防**
  - 长跑/冻结/中间产物**默认放 `/mnt/d/...`**，不用 `/tmp`；
  - 改完代码后要重启长跑时，先确认旧进程真的还在（`ps -eo pid,etimes,args | grep "[p]attern"`），再决定是否清理；
  - `pkill` 前先自查：**我这条命令的命令行里是否包含要匹配的模式**。
- **类型标签**：`工具链` / `物理建模`

---

## LRN-20261001-005 · 规格/评估命令里引用的 checkpoint 路径会失效：写前必须 `ls` 验证

- **现象**：规格里写死 M1 的权重 `outputs/checkpoints/formation/**seed0_nep1400**/mappo_fleet_last_ep841_...pt`（来源是历史评估 JSON 里的 `eval_args.checkpoint`），实际该目录**已不存在**；全仓仅剩 `final_seed1/..._ep841_..._seed1_seed1.pt`（seed1 那一代）。
- **期望 vs 实际**：期望"历史 JSON 里记的路径今天仍可用"；实际训练产物目录被改名/清理过（`seed*_nep1400` → `final_seed*`），路径早已失效。
- **根因**：把"历史 JSON 的**记录值**"当成了"**当前可用路径**"——记录是**当时**的事实，不等于**现在**的事实。
- **解决**：改用同代同语义的现存在权重 `final_seed0/mappo_fleet_last_ep1623_dec_ad2_cp_seed0_seed0.pt`（seed0、`last`、ADR-020 已引用的"守线"权重），并在 tasks/留痕**原位记更正**（不改历史 JSON）。
- **止血与预防**：写任何评估/训练命令**之前先 `ls`/`Glob` 验证权重路径存在**；引用历史 JSON 的 `eval_args` 时一律标注"记录值，须核实"。
- **类型标签**：`工具链`

---

## LRN-20261001-006 · "冻结副本（worktree）"会被 **editable 安装**击穿：`import src` 仍指向主树

- **现象**：按 LRN-20261001-003 建了冻结副本 `/mnt/d/Code/_p0freeze`（`git worktree`，冻结 SHA `d6ba3540`，**已核实**该副本 `train_fleet_env.py` / `multi_loco_controller.py` / `train_env.py` / `mappo_agent.py` / `metadata.py` 里四处改造的标记**全部为 0 命中 = 确属改动前**），在副本里 `cd` 后跑评估，结果 JSON 的 `metadata` 却出现了**只有主树才有的**字段（`reward_schema: v2-bounded-overlimit-section-force`）。即：**副本代码是改动前，跑的却是改动后**。
- **期望 vs 实际**：期望"副本里跑 = 用副本代码"；实际副本只是**磁盘上**的一份静态代码，`sys.path` 并没有指向它。
- **根因**：conda env 装了 editable 安装 `site-packages/__editable__.traffic_rl-0.1.0.pth`，它把路径占位符 `__editable__.traffic_rl-0.1.0.finder.__path_hook__` 追加进 **sys.path**，对应一个**无条件**把 `src` 映射到 `/mnt/d/Code/MultiAgent/traffic_rl_project/src`（**主树**）的 path hook。而 `python <script>.py` 的 `sys.path[0]` 是**脚本所在目录**（`<root>/src/evaluation`），**cwd 不在 sys.path**，故 `import src` 走不到副本 → 落到占位符 → 主树。**结果看起来完全正常**（静默错误）。
- **解决**：用 bootstrap harness 把**冻结树根插到 `sys.path[0]`**（先于占位符命中），再 `runpy` 执行目标脚本；并**断言** `src.metadata.__file__` 落在冻结树内（`tmp_p0_freeze_boot.py`）。
- **止血与预防**
  - "冻结副本"只有在**显式把副本根放进 `sys.path` 且断言解析结果**之后才算真的冻结；**只 `cd` 不算**；
  - 任何"版本A vs 版本B"的长跑，结果 JSON 必须回查一个**只可能来自该版本**的特征字段（本次靠 `reward_schema` 才发现）；
  - 修复前那批"改动前基线"（`*_p0_m0_rule_53km.json` / `*_p0_m1_last_53km.json`）**须重打标签**为"**改动后（A/D 生效）**"，不得再称"改动前"。
- **类型标签**：`工具链` / `可复现性`

---

## LRN-20261001-007 · 嵌套阈值让"梯度投影臂"静默失效；而单测**靠猴补关掉上游机制**才通过 = 在验证一条不可达路径

- **现象**：改造 D 按 ED 同款投影式实现了"高力时新源**降一档**（SERVICE→MIN）"的梯度臂，并且**有一条单测通过**。但生产上该臂**从未执行**：`ab_safety_downgraded` 在 12000 步窗口恒为 0（另一路 `ab_safety_vetoed` 只触发 35 次）。
- **期望 vs 实际**：期望"投影臂在 ratio∈(0.9, …) 时提供比硬否决更温和的梯度权限"；实际**永远不可达**。
- **根因（可证）**：
  1. `SafetyLayer.ab_new_source_veto()` 的反应式判据 = `p0 ≥ coupler_veto_ratio(0.6)·limit`（`safety_layer.py:69/156`，`coupler_veto_ratio` 全仓无覆盖，恒 0.6）；
  2. `p0 = max(obs_state['coupler_forces'])`，而 `_state_snapshot()` 喂的正是 `coupler_interface_forces_per_vehicle()` —— **与梯度臂算 `scale` 用的是同一个数组**，且该函数 `np.abs()` 后取相邻两钩最大幅值、**恒 ≥ 0**（`train.py:374-376`）⇒ `p0 ≡ ratio·limit`；
  3. 梯度臂条件 `scale<0.5 ⟺ ratio>0.9` ⇒ **恒蕴含** `veto=True`；分支序为 `if veto: … elif scale<0.5: …` ⇒ 梯度臂恒被抢先。
  4. 那条单测之所以通过，是因为它**猴补 `ab_new_source_veto = lambda: False`**（把上游否决关掉）——即**测试在验证一条生产上不可达的分支**，读者会误以为该能力已具备。
- **解决**：删除该梯度臂 + 计数键 `ab_safety_downgraded` + 那条误导性单测；新增**源码级断言**禁止其回流（`tests/test_ab_refill_and_safety_authority.py::test_step_decomposed_has_no_revoke_path`）。**纯重构、零行为变化**（分支本就不可达）⇒ 既有 on/off 验证结论不受影响。含义：**veto 阈值停在 0.6 时，AB 无法表达渐变投影**（禁新增是任何梯度降级的超集）；真·梯度 AB 权限必须**连同阈值一起**重定。
- **止血与预防**：
  - 新增"分级/投影"类机制时，**先证明其触发域与既有硬阈值的触发域不互相包含**（画区间的包含关系），再写代码；
  - **单测不得猴补掉上游安全机制**来使自己通过——需要"关掉上游"才能测，就说明该路径在生产不可达；此时应改测**上游阈值本身**；
  - 生产 `info` 里的机制计数要**分口径**统计（本次 `veto_fired_calls`(含控制器调用点, 1216) 曾与 `ab_safety_vetoed`(env 侧真丢弃, 35) 被混为一谈，导致把 D 的贡献高估 ~35×）。
- **类型标签**：`安全层` / `测试有效性` / `不误导`

---

## LRN-20261001-008 · 短窗口 on/off 的机制结论**不能外推到全剖面**：改造 A 的峰值符号会反转

- **现象**：改造 A（AB 最小充风门）在 **12000 步**窗口的 on/off 对照里表现"全好"——AB 用量 −42.3%、**峰值略降**（926.95→914.37 kN）、band 不变、0 破线。据此写下"门强绑定、峰值略降"。后来在 **53km 全剖面（36000 步）** 上做改动前/后对照，**峰值符号反转**：M1 全通道 改动前 1350 kN → 改动后 **1643.49 kN**（+21.7%），band 从 99.62% 掉到 91.58%。
- **期望 vs 实际**：期望"短窗口量化出的机制好处可以代表机制本身"；实际**同一机制在不同时间尺度上的效应可以反号**。
- **根因**：
  1. `ab_min_refill_s=222 s` 的**充风相位是分钟级**，12000 步（1200 s）只覆盖**约 1 个**完整循环制动周期，且只覆盖 53km 剖面的**起始段**（坡度结构单一）；
  2. A 的效果**依赖策略在什么坡度/相位上更依赖 AB**：起始段不需要额外 AB ⇒ 掐掉它无害、还压低了 AB 源密度；全剖面的陡坡段策略**本来靠 AB 保速度带** ⇒ 掐掉它就丢控速能力、并在个别时刻出现更高峰值；
  3. 这正是 **ADR-017** 反复强调的三维时域区分（单条 rollout 窗口 / 评估剖面 / 总训练量）在**机制验收**上的翻版——机制验收也必须声明**它在哪个时域上定义**。
- **解决 / 现在怎么写**：
  - `DIAGNOSTICS_2026-10.md` 的 12000 步 A 表**加显式窗口口径限定**（"峰值略降只在首 1200 s 成立"），全剖面**三配置**（M1 全通道 / M1 仅 ED / M0）另立表并给出"混合效应"判定；
  - 结论改为：**A 不是纯改善**——A **总是**压低 AB 用量，但在 **RL 参与的配置里峰值一律升高、band 一律变差**（M1：+294 kN / −8.04 pt；仅 ED：+14.5 kN / −1.22 pt），破线步数符号还随配置改变（M1 905→77 大降；仅 ED 21→44 反升）。**必须与 C（车钩力进目标）+ B（信用分配）一起重训**才可能兑现价值；
  - ADR-021「执行闭环」补记该条与"未分离残余（A(+D)，非 A 单独）"。
- **附带教训（同一个对照的第二层错）**：**"在某个配置上 no-op"≠"有效域就是另一个通道"**。M0（RL 全程为 0）改动前/后**逐位相同**，一度被写成"A 对规则层 no-op ⇒ A 只管 RL 新增源"。但 `_ab_gate` 装在**控制器**里、**不分来源**；补跑 **M1-仅 ED** 后 A 同样拦到规则层排程（AB 步 1441→1105，−23.3%）。正确解读是：**规则层自身的循环制动排程本就满足 222 s 充风窗**（所以纯规则轨迹上不触发），而**轨迹一旦被 RL 从 ED 通道扰动，规则层排程也会落入充风窗内**。
  ⇒ 判断机制有效域**不能只做一组 on/off**；至少要在一个"策略另一个通道仍活跃"的配置上复测。
- **止血与预防**：
  - 机制 on/off 对照**必须标注时域**（多少步 / 覆盖哪个剖面段 / 是否含完整循环制动周期），并在**至少一个完整剖面**上复核**结论方向**；
  - 报告"机制有效"时，把**指标方向**（不只数值）列出来，任何**方向反转**都要显式写清"在哪个时域反号"；
  - 判断**有效域**至少要在两个"另一通道活跃度不同"的配置上复测（本例：M0 全静 / 仅 ED / 全通道），并优先看**动作层面的计数**（`ab_refill_veto` / `ab_steps`）而非只看得分；
  - 与 LRN-20260930-010 同类（短窗口/采样态得到的"机制有效"不可当部署保证），本条把它推广到**确定性策略 + 短窗口**的组合。
- **类型标签**：`机制验收` / `时域口径` / `有效域判定` / `不误导`

---

## LRN-20261001-009 · 短训验证必须同时覆盖三个输出目录，否则静默覆盖历史产物

- **现象**：为验证"主 YAML 已按 ADR-017 对齐"，跑了一次 `--episodes 2` 的短训，命令只覆盖了 `--checkpoint_dir` 与 `--results_dir`，**漏了 `dirs.figures_dir`**。结果 `figures_dir` 仍取 YAML 默认值 `outputs/checkpoints/formation/seed0/figures`，短训结束时 `save_training_artifacts` **覆写了 09-25 那次 100-ep 历史训练的学习曲线 PNG**（`fig_learning_curve_dec_ad2_cp_seed0.png`，3 子图 → 只剩 2 个点）。
- **期望 vs 实际**：期望"只要把 checkpoint/results 指到临时目录就隔离干净了"；实际 **figure 是第三个独立配置项**，且 `save_training_artifacts` **每次全量覆写**（这是它刻意的设计——防前台超时丢数据），因此一次误指就把历史图**无提示地**冲掉。
- **根因**：
  1. 配置 schema 里 `checkpoint_dir` / `results_dir` / `figures_dir` 是**三个平级字段**，CLI 只提供 `--checkpoint_dir` / `--results_dir` 两个便捷开关，`figures_dir` **只能走 `--override dirs.figures_dir=…`**；只写前两个时极易以为"已全套隔离"；
  2. `results_dir` 的**图表输出不读 `figures_dir`**（绘图目录独立传入），所以"results 隔离了"不等于"图隔离了"。
- **解决 / 现在怎么做**：
  - 从原始 `train_history_dec_ad2_cp_seed0.csv`（**未被本次短训触碰**，因 results 已重定向）经**同一** `save_training_artifacts` 绘图路径重建了该 PNG ⇒ 内容与"从未被覆盖"等价（无信息丢失）；
  - 立即清理：临时 `tmp_figfix.py`、`/tmp/_figfix`、`outputs/_cfgcheck/` 全部删除。
- **止血与预防**：
  - **任何验证/冒烟短训必须同时重定向三者**：`--checkpoint_dir` + `--results_dir` + `--override dirs.figures_dir=…`（写进验证命令模板）；
  - 或者更好：短训一律先 `--override dirs.<三项>` 到一个一次性 `outputs/smoke/_smoke_*/` 目录，跑完即删；
  - 历史实验目录（`outputs/checkpoints/formation/seed{0..4}`、`final_seed*`）**不得作为任何验证跑的输出目标**；即便只是"顺带验证一下配置"，也必须先确认三个目录都已重定向；
  - 与 LRN-20260930 系列（"验证跑污染主实验目录"）同类，本条把污染面从 checkpoint/results 扩到 **figures**。
- **类型标签**：`验证纪律` / `产物污染` / `可复现性`

---

## LRN-20261001-010 · 同一"累计计数器"坑在**评估脚本修了、训练框架漏了**：`_long_eval` 的 viol O(n²) 放大

- **现象**：`TrainRunner._long_eval`（周期性完整剖面选优，2026-09-22 新增）写成
  `viol += int(info['coupler_limit_violations'])`。而 env 的 `coupler_limit_violations` / `coupler_force_peak`
  是 **episode 级单调累计**（`reset()` 清零、step 间不清零，见 `train_fleet_env.py:320/519`），
  所以这个写法 = **把累计值逐步相加** ⇒ `viol ≈ Σ_i c_i`，随步数 **O(n²)** 增长
  （36000 步可达 1e8 量级），而真实违规总数只是 `c_final`。
- **期望 vs 实际**：期望 `viol` 是"本回合违规总数"（判据 `int(viol)==0` 与日志展示都用它）；
  实际得到一个天文数字并打进 `[long_eval]` 日志行。**同一 bug 在 `evaluate_decompose.py:160-163`
  已于 2026-09-25 修过并写了注释，但 `_long_eval` 当时漏改** —— 属于"修了一处、留了同源第二处"。
- **根因**：
  1. 两处代码**各自实现**了"遍历 env 取指标"的循环（`evaluate_decompose` 与 `train_runner._long_eval`），
     没有共用工具函数 ⇒ 修一处不覆盖另一处；
  2. `_long_eval` 的**异常被包在 try/except 里"失败不中断训练"**（这是刻意的健壮性设计），
     所以即便口径错了也**不会报错**，只会静默地把错误数值写进日志/元数据；
  3. **没有单测**：`grep long_eval tests/` 零命中 —— 新机制加进来时没配测试。
- **实际影响（诚实定级，不夸大）**：
  - **持久化元数据的数值没有被污染**：`best_eval` 只在 `ok=True` 时写入，而 `ok` 要求 `int(viol)==0`；
    由于计数器从 0 单调不减，"逐步累加和 == 0" ⇔ "全程无违规" ⇔ "真实总数为 0"，**判据语义等价**。
    所以已落盘的 `long_eval_best.json` / checkpoint 内嵌 `long_eval_best` 的 `viol` 恒为 0（正确）。
  - **真正的危害 = 日志误导 + 脆弱性**：未达标的评估会打印 `viol 1234567` 这类天文数字，
    读日志的人会误判"机制完全失效/仿真坏了"；且一旦将来放宽判据（如允许少量违规），
    错误数值会直接进入元数据。
- **解决**：改为与评估脚本一致的**每步增量累加**：
  ```python
  cur_viol = float(info.get('coupler_limit_violations', 0))
  viol += cur_viol - prev_viol
  prev_viol = cur_viol
  ```
  并补 `tests/test_metric_accounting.py`（该文件同时承载本条与 LRN-011/012 的回归，见下）：① stub 复现"累计序列 0,0,1,2,3,4"断言取到 **4**（旧写法为 **10**）；
  ② 零违规仍 `达标=True` 且 best 落盘（防修复改坏 ok 门）；③ **源码级断言**禁止 `viol += int(info.get(...))` 回流。
- **端到端预检**（真 env，`--episodes 2 --override long_eval_interval=1 --override long_eval_steps=400`，exit 0）：
  `[long_eval] ep1: reward +3249 | peak 540kN | viol 0 | band 100.0% | 末速 66.8km/h | 达标=True`、
  best 与 `long_eval_best.json` 正常落盘（数值合理）⇒ 长跑（每 50 ep 触发）不会在 ep50 静默失选优。
- **止血与预防**：
  - **同一"读 env 累计指标"的需求应只有一个实现**（理想做法是抽一个 `collect_episode_metrics(env, ...)` 工具，
    评估脚本与 `_long_eval` 共用）；当前至少要求**两处口径逐字一致**并互相指认；
  - **"失败不中断"的 try/except 不等于可以不管正确性**：这类静默降级路径必须配单测，
    否则错误只会在日志里以"看似合理但离谱的数字"出现；
  - **凡是 2026-09-25 那类"计数器口径"修复，必须全仓 grep 同类循环**逐一确认（本次按 `coupler_limit_violations`
    全仓 grep，共 39 处命中 / 17 个文件）；
  - **新增附加机制（如 long_eval 选优）必须同步加测试**——它是决定"哪个权重当 best"的判定器，
    错了会直接选错权重（本次靠 `ok` 语义侥幸未致错选，不能依赖这种巧合）。
- **同源残留（已定位、本轮刻意未改，登记备查）**：全仓 grep 后另有 **3 个 live 脚本**是同一种
  `viol += info['coupler_limit_violations']` 写法：
  `src/evaluation/compare_m1_baselines.py:53`、`src/evaluation/evaluate_fleet_hier_80.py:46`、
  `src/evaluation/compare_m1_init80.py:46`。
  **未修改的理由（不静默改历史资产）**：三者均属**已废止的 hierarchical 编队层阈值 RL 方案**
  （`hierarchical: True` + `shuozhou_23800`，ADR-013 已废止），且**全仓零引用**（Grep 无任何
  doc/script/pipeline 指向）；改它们会变动"历史复现脚本"的产出数值。⇒ **若任何旧表格引用过这三者的
  `viol` 数值，必须按"O(n²) 膨胀"处理，不得当真实违规数**；正解是随该批脚本一并归档（`archive/`）
  或在使用前统一修正口径，而不是逐个悄悄改。
- **类型标签**：`指标口径` / `静默降级` / `测试覆盖` / `不误导` / `同源重复实现`

---

## LRN-20261001-011 · `--mode all` **静默只出 2 行**：CLI 默认值把"all"变成了"部分"

- **现象**：`REPRODUCIBILITY.md` §十 把主对比评估写成
  `python src/evaluation/evaluate_decompose.py --mode all --checkpoint <best.pt> --n_seed 3`
  并注明产出"**主对比三行 D-RL / D-Rule / MPC @53km**"。实际跑 `--mode all` **只得到 2 行**
  （`decompose_M0_rule` / `decompose_M1_rl`），**MPC 行缺失**；证据：`outputs/results/decompose/eval_decompose_all_ms300_smoke_x1.json`
  的 `results` 只有两个键。
- **期望 vs 实际**：期望"mode 名叫 `all` ⇒ 出全部行"；实际 `all` 被一个 CLI 默认值悄悄削成 2 行。
- **根因**：
  1. MPC 行被写在 `if args.mode in ('all','mpc'):` 里，但其内部又套了一层
     `if getattr(args,'enable_mpc',False) or args.mode=='mpc':`；而 `--enable_mpc` 是
     `action='store_true'` ⇒ **默认 False** ⇒ `--mode all` 永远进不去；
  2. **连带静默**：三行 Δ 摘要的条件是 `len(results) >= 3`，只有 2 行时它整块跳过、只打印
     Δ(D-RL − D-Rule) —— 输出看起来"正常且自洽"，**不给任何缺行提示**；
  3. 文档（§十）与代码默认值**从未对过账**：命令照文档抄，行数照代码出，两次都"没报错"。
- **危害**：读者会以为"MPC 没做/不支持"或直接把两行当"三行主表"填进论文 —— 而 MPC 恰恰是
  **ADR-016 唯一保留的对比基线**（claim = 免重辨识成本 vs 逐线重标定的 MPC），缺它主表不成立。
- **解决**：解析参数后**立即归一**（放在 `build_metadata` 之前，避免 metadata 记 `enable_mpc=false`
  而实跑挂了 MPC 的自相矛盾）：
  ```python
  if args.mode in ('all', 'mpc'):
      args.enable_mpc = True
  ```
  并删掉 MPC 块内的条件式兜底。安全性论证：`make_env` 里的 MPC 挂载对 M0/M1 行**无行为影响**
  （`_mpc_controller` 只在评估脚本的动作函数里被读取，`env.step` 从不读它）。
- **验证**：新增 `tests/test_metric_accounting.py::test_eval_mode_all_normalizes_enable_mpc`
  （源码级：归一存在 + 位置在 `build_metadata` 之前 + 旧兜底不得回流）；
  **实跑冒烟** `--mode all --max_steps 120` 见 `DIAGNOSTICS_2026-10.md`「修复-2026-10-01」②。
- **预防**：① **凡"模式名 = 全部"的 CLI，必须给出**缺行/缺项的显式提示**（而非静默少出）；
  ② 文档里的命令**必须实跑一次并核对**产出结构（本次正是"文档抄了、代码没对账"）；
  ③ 用 `store_true` 的开关若承载"某行是否产出"，要立刻想到"默认 False 时该行会静默消失"。
- **类型标签**：`CLI 契约` / `静默缺项` / `文档↔行为不一致` / `不误导`

---

## LRN-20261001-012 · MPC 控制器**逐回合状态未清零**：`--n_seed 3` 的"3 个回合"并不独立

- **现象**：`evaluate_decompose.rollout()` 里 `_mpc = getattr(env,'_mpc_controller',None)` 只被
  `_mount_mpc` 在**挂载时** reset 一次（`evaluate_decompose.py:137`）；而 `eval_method` 是
  `rs = [rollout(env, ...) for _ in range(args.n_seed)]` —— **同一条 env / 同一个控制器**跑 n_seed 个回合。
  ⇒ 第 2、3 个回合会继承上一回合的**每回合状态**：`_gap0_init`（初始间距基准，初值 1e9）、
  `_gap_ref`、`_last_vel`、`_meas_accel`（见 `FairMPCController.reset`）。
- **期望 vs 实际**：期望 n_seed 个回合是"同初速、独立复现"的独立样本（脚本注释也写明
  "快照本回合新增段，**避免跨 seed 累计混淆**"——说明作者本意就是回合独立）；
  实际**只有 solve_times 做了跨回合快照**，控制器状态没有。
- **根因**：
  1. `_mpc_controller` 是**评估脚本动态挂到 env 上的属性**，不在 `env.reset()` 的复位清单里
     （`env.reset()` 只 reset `self.controllers` 与 `self.multi_loco_controllers`）⇒ 复用 env 时它不会被清；
  2. `reset()` 方法**存在且正确**，只是调用点少了一处 —— 属于"机制齐备、接线漏一根"。
- **危害**：主对比 MPC 行的 `--n_seed 3` 聚合不是 3 个独立回合（尤其 `_gap0_init` 决定间距约束基准，
  会影响 MPC 行为），**聚合统计与方差不可靠**；且因 `n_seed=1` 的旧记录不受影响，
  问题只在"按文档跑 3 seed"时才显形 —— 更难被发现。
- **解决**：把 reset 移到 `rollout()` 内、`env.reset()` 之后、`st0` 快照之前：
  ```python
  if _mpc is not None and hasattr(_mpc, 'reset'):
      _mpc.reset()
  ```
  **对既有数值的影响面（诚实声明）**：`n_seed=1` 时"挂载后立即 reset"与"回合开始时 reset"之间
  没有任何 step ⇒ **完全等价，旧单 seed MPC 数值不变**；只有 `n_seed>1` 的行为被修正。
- **验证**：`tests/test_metric_accounting.py::test_rollout_resets_mpc_each_episode`
  （stub MPC 计数：3 回合 ⇒ `reset_calls == 3`）+ `::test_rollout_resets_mpc_source`（源码级防删）。
- **预防**：① 任何"每回合状态"的对象，**复位点必须与"回合开始"的语义绑定**，而不是与"对象被创建"绑定；
  ② 复用同一条 env 跑多 seed 时，必须逐个清点"env.reset() 管不到的动态属性"（本次是 `_mpc_controller`）；
  ③ 看到脚本里**只有部分量**做了跨回合快照（solve_times）时，要问"为什么另一个带状态的量没做"。
- **类型标签**：`状态残留` / `多 seed 独立性` / `评估可信度` / `接线遗漏`

---

## LRN-20261001-013 · fair MPC 行**从未跑通**：读一个不存在的字段 ⇒ 崩在最后一步，连累已跑完的行也丢失

- **现象**：修完 LRN-011（`--mode all` 补回 MPC 行）后的**第一次实跑**立刻崩：
  ```
  AttributeError: 'FairMPCController' object has no attribute 'solve_statuses'
    File ".../evaluate_decompose.py", line 190, in rollout
  ```
  位置在 `rollout()` **收尾组装指标**处：先打印完 `decompose-M0` 与 `decompose-M1` 两行的结果，
  再在 MPC 行组装 `mpc_solve_fail` 时抛异常。
- **为什么长期没被发现（关键）**：
  1. MPC 行被 LRN-011 的 CLI 默认值挡在门外 ⇒ `--mode all` **从来不进 MPC 分支**，这段代码**从未被执行**；
  2. 已有的 MPC 冒烟用的是 `--mpc_type nmpc`（`outputs/results/decompose/eval_decompose_mpc_ms60_smoke_nmpc.json`），
     而 **NMPCController 有 `solve_statuses`**（`nmpc_controller.py:113`），恰好绕开了这条路径；
  3. 于是"默认 fair + `--mode all`"这个**文档推荐的组合**从来没跑过一次。
- **危害（比"MPC 行缺失"更糟）**：异常发生在**收尾**，此时 M0/M1 已算完（各 36000 步、机时数十分钟）
  但**结果 JSON 尚未落盘**（保存在第 344 行）⇒ 整轮评估**全部白跑**，且只在终端留一个 traceback；
  若用 `| tail` 或 `nohup` 跑，`exit code` 还会被管道/后台吞掉（本次冒烟就报 exit 0），**极易被当成成功**。
- **根因**：
  1. `rollout` 里 `hasattr(_mpc,'solve_times')` 只守卫了 `solve_times`，**紧跟着直接下标取
     `_mpc.solve_statuses[st0:]`** —— 守卫与使用对象不一致；
  2. `FairMPCController` 只记录 `solve_times`，**没有** `solve_statuses`（而"求解失败次数"是
     记忆里明列的**主指标**："级联失败率 / 求解失败次数 / ATP 触发次数；MPC 每步记录 solve_times"）
     ⇒ 两个控制器对同一指标的记录能力不一致，评估侧却按"都有"来写。
- **解决（两处，缺一不可）**：
  1. **补齐数据源**：`FairMPCController` 增加 `solve_statuses`（`__init__` + `reset()` 清空 +
     每次 `minimize` 后 append），**口径与 NMPC 对齐**——都取**求解器自身的收敛标志**：
     NMPC 用 IPOPT 异常 ⇒ `'fail:<msg>'`，Fair 用 `res.success` ⇒ `'optimal' / 'fail:<msg>'`；
     （Fair 失败时仍沿用 `res.x`，保持既有行为不变）；
  2. **降级保护**：`rollout` 收尾改为 `sts = getattr(_mpc,'solve_statuses',None)`，无状态源时
     **不产出** `mpc_solve_fail` 而不是崩 —— "附加诊断指标缺失"绝不该让主结果一起丢。
- **验证**：`tests/test_metric_accounting.py`（共 9 项）新增 3 项：
  `test_rollout_tolerates_missing_solve_statuses`（stub 无状态源 ⇒ 不崩、不产键）、
  `test_fair_mpc_records_solve_statuses`（源码级：记录 + `reset()` 清空 + 收敛标志口径）、
  `test_rollout_metric_assembly_guards_statuses`（源码级：禁止退回直接下标）。
  外加实跑冒烟（`--mode all --n_seed 2 --max_steps 120`，fair）见 `DIAGNOSTICS_2026-10.md`。
- **止血与预防**：
  - **守卫对象必须与使用对象一致**：写了 `hasattr(x,'a')` 就必须确认块内只碰 `a`；
  - **"附加/诊断指标"的读取一律用 `getattr(..., default)` 兜底**，绝不用直接下标 ——
    因为它们的存在性取决于"另一个类的实现细节"；
  - **收尾组装必须放在落盘之后**（或包 try/except），否则"最后一行的可选指标"能毁掉全部主结果；
  - **同一语义的指标必须在所有同类实现上都有定义**（fair / nmpc 两个 MPC 控制器口径必须同构），
    否则比较本身不公平；
  - **最危险的组合 = "被默认值挡住的代码路径"**：它既不会报错也不会被测试覆盖 ⇒ 本次'"修好缺行"后第一次跑'
    才发现——**恢复一条被静默关闭的路径后，必须立刻实跑它**（本次正是如此才炸出本 bug）。
- **类型标签**：`指标缺失` / `守卫不一致` / `收尾崩溃` / `未被执行路径` / `公平性`

---

## LRN-20261001-014 · `nohup`/`setsid` 救不了长跑：IDE 的 Shell 工具**返回时回收本次调用派生的全部进程**

- **现象**：为本轮 1400 ep 重训写好了启动器 `scripts/launchers/launch_retrain_adr021_seed0.sh`，两次"脱壳"启动均**静默失败**：
  1. `cd && source && conda activate && setsid nohup python … > log 2>&1 < /dev/null &` ⇒ 报 `LAUNCHED`，
     但随后 `pgrep -af run_training.py` 无进程、`ls` 连 **log 文件都不存在**；
  2. 改为 `nohup setsid bash scripts/launchers/launch_retrain_adr021_seed0.sh > log 2>&1 < /dev/null &` ⇒ 同样无进程、无 log。
- **定位手段（关键，可直接复用）**：写**存活探针** ——
  ```
  nohup setsid sleep 90 > /tmp/surv_probe.txt 2>&1 < /dev/null &   # 本次调用返回
  pgrep -af "sleep 90"; ls -la /tmp/surv_probe.txt                 # 下一次调用
  ```
  结果两边都空（exit 1）⇒ **不是"训练脚本的问题"，而是"进程根本不跨调用存活"**。
- **根因**：IDE 的 Shell 工具把每次调用放在**受管的进程组/作业**里，调用返回即**整组回收**
  （`setsid` 新会话 + `nohup` 忽略 SIGHUP 都挡不住——回收不是靠信号，是直接收进程组/容器）。
  ⇒ 在**工具内部**用 shell 手法做"脱壳后台"是**方向性错误**，不是参数没调对。
- **解决（两条正路）**：
  1. **用工具自己的后台模式**：`run_in_background: true`。此时 `wsl -e bash -lc "… bash launcher.sh > log 2>&1"`
     是一条**前台等待**的长命令（`launcher.sh` 里 `exec python` 顶替 bash、成为该调用的直接子进程），
     作业归 tool-host 管理 ⇒ 进程**跨调用存活**（本次实测：`PID 673`，`ps -o etime,pcpu` = 89% CPU，输出目录已建）。
     上限 = 该后台作业的生命周期（随 IDE 会话）。
  2. **交给用户的真实 WSL 终端**跑 `nohup setsid bash <launcher> > log 2>&1 < /dev/null &` ——
     退出 IDE 也不受影响，这是**数天级**任务的唯一稳妥方式。
- **判活/留痕要点**：`pgrep -af run_training.py` + `ps -o etime,time,pcpu -p <pid>`；
  日志用 `>` 重定向 ⇒ **块缓冲**，分钟级延迟属正常，**不能用"日志没更新"判死**（本次 BC 阶段 GPU 0%、CPU 89%）。
- **预防**：
  - 凡"跑得比一次工具调用久"的任务，**先在目标运行环境里做存活探针**，再投入真实负载；
  - **不要**用"后台启动成功"的打印（`echo LAUNCHED`）当成功证据 —— 必须**下一轮独立调用复查 `pgrep` + 产物目录**；
  - 长训入口一律写成**独立启动器脚本**（含 `set -e` / 环境激活 / `exec`），同时登记**恢复命令**（ADR-019 `--resume latest`）。
- **类型标签**：`进程生命周期` / `工具边界` / `静默失败` / `长跑运维`

---

## LRN-20261001-015 · CLI 默认值**静默决定语义**（第二次）：`--decision_interval` 默认 1 而训练用 10

- **现象**：`evaluate_decompose.py` 的 `--decision_interval` 默认写死 **1**，而主训练 YAML 是
  `decision_interval: 10`（进 metadata `hyperparameters.decision_interval=10`）。
  `REPRODUCIBILITY.md` §十 的**主对比命令未显式传该参数** ⇒ 照文档跑出来的 D-RL 行会以
  **每原始步都重新决策**执行，而策略是在**10 步动作保持**（semi-MDP）下训练的。
- **为什么长期没暴露**：真正跑过的主结果（ADR-021 的 P0 三行）都**显式带了 `--decision_interval 10`**；
  而"照文档命令跑"从未被当作验收步骤 ⇒ 与 LRN-20261001-011（`--mode all` 静默缺 MPC 行）
  是**同一个病根**：`--mode all` 那个是 `store_true` 默认 False，这个是 `type=int` 默认 1。
- **危害**：
  1. **训练/评估失配**（项目铁律："训练和评估必须用一致的参数"）⇒ D-RL 行数值不可信、
     与规则行/MPC 行的比较不公平（RL 行被放在了它没被训练过的动作分辨下）；
  2. **文档与实现互相矛盾** —— 文档说"三行主对比按此命令复现"，实现却默认换了语义；
  3. 定为**主表生成器**路径 ⇒ 一旦带着这个默认值出主表，错误会直接进论文。
- **根因（模式化）**：**凡是"语义必须与训练一致"的参数，都不该由 CLI 默认值决定**。
  默认值要么显式等于训练口径，要么**从产物本身读取**（本项目已有"ckpt 自描述协议"：
  `save()` 把 `metadata` 嵌进 `.pt`）—— 后者才是唯一不会随训练配置漂移的做法。
- **解决**：
  1. `--decision_interval` 默认改 **`None` = 自 ckpt 内嵌 metadata 的
     `hyperparameters.decision_interval` 读取**（与既有 `probe_critic_mode` 同源同思路）；
     读不到（旧 ckpt / 文件缺失）⇒ 退回**训练标准值 10**并**明确打印**，绝不静默；
  2. 解析必须在 `build_metadata` **之前**（否则 `metadata.eval_args` 记 None、实跑却用了具体值 ——
     与 LRN-011 的修复纪律一致）；
  3. 显式传 `--decision_interval N` 时行为与此前**完全一致** ⇒ 不改动任何已显式指定的既有数值。
- **验证**：① `tests/test_metric_accounting.py` 新增 5 项（行为级 4 + 源码级 1，含"防退回写死默认"）；
  ② 真 ckpt 实跑 `--mode decompose_m1 --max_steps 120`：打印
  `[decision-interval] 自 ckpt metadata 读取 decision_interval=10（与训练一致）`、
  行标签 `interval=10`、JSON 的 `metadata.eval_args.decision_interval=10` 与 `args.decision_interval=10`
  **三处一致**（`outputs/results/decompose/eval_decompose_decompose_m1_ms120_di_fix_check.json`）。
- **预防**：
  - **新增/复用 CLI 参数前先问："它与训练配置有没有必须一致的关系？"** 有 ⇒ 不许用写死的默认值，
    必须"读产物"或"默认即训练口径 + 打印"；
  - **调用链审计要覆盖"默认值分支"**：只测"显式传参"等于没测默认路径（本 bug 藏了整整一轮）；
  - 把"照文档命令跑一次"当作验收步骤之一。
- **类型标签**：`静默语义漂移` / `CLI 默认值` / `训练评估失配` / `文档实现矛盾`

---

## LRN-20261001-016 · 机时估算**低估 3.4×**：拿"短训总墙钟 ÷ 集数"当每集耗时，且照抄 tqdm 的线性 ETA

- **现象**：为 seed0 长训登记的机时预期 = **≈3.4 天/seed**（"每集 ≈140 s（500 步）⇒ 1400 ep ≈2.3 天 + 28 次 `long_eval` ≈1.1 天"）。
  实跑后由训练**自身进度条**测得：500 步课时 **271 / 276 / 274 / 278 s/集**（`n_env=4`），BC 另耗 ≈11 min
  ⇒ 按 curriculum（`500:0,1000:10,1200:20`）折算 1400 集 ≈10.6 天，加 `long_eval` ≈1.1 天
  ⇒ **实测 ≈11.7 天/seed**。**低估 3.4×**；`1400 ep × 5 seed` 单机串行实际 ≈**58 天**，不是 ≈17 天。
- **两个独立的低估来源（都会复发，必须分别堵）**：
  1. **"短训总墙钟 ÷ 集数" ≠ 每集耗时**：`140 s/集` 是从一次短训的**总耗时（含 BC ≈11 min）÷ 集数**
     倒推的，而短训的 BC 占比与课时口径都和长跑不同 ⇒ 分子被 BC 稀释、分母口径不同。
     **正确做法 = 读长跑自己的 `s/ep`（tqdm 进度条 / `train_history` 的 `time_s` 列差分）**，
     它才是真实每集耗时。
  2. **tqdm 的 ETA 会系统性低估 curriculum 任务**：它按**当前课时**的速率线性外推，
     打印 `105~108 h`（≈4.5 天）—— 而课时稍后会升到 1000 / 1200 步，
     每集耗时随之近似**翻倍 / ×2.4** ⇒ ETA 低估约 2.5×。**有 curriculum 的任务，ETA 只作下界看。**
- **危害**：排期错误直接影响研究决策 —— 按 ≈3.4 天会得出"5 seed 两周可完成"，
  实际要 ≈58 天 ⇒ 必须先裁决"减课时/减集数"还是"并行多机/多卡"。**错的机时会误导方向性决策**，
  与"文档不误导"是同一条铁律。
- **解决（本轮）**：
  1. `REPRODUCIBILITY.md` §十、`PROJECT_PIPELINE.md` 长久计划 1、`DIAGNOSTICS_2026-10.md`
     「启动-2026-10-01」四处把 ≈3.4 天**原地更正为 ≈11.7 天**，并**写明原估算作废**（不留旧数）；
  2. 更正文里**带上可复核的推导**（实测 `s/ep` → 按 curriculum 分段折算 → 加 `long_eval`），
     使下一位读者能自己重算，而不是再抄一个数字。
- **预防**：
  - **机时一律取"长跑实跑的 `s/ep`"**，不许用短训总耗时除集数；
  - **有 curriculum（课时递增）的任务，禁用线性 ETA**，必须**分段折算**；
  - 机时数字进文档时必须**同时写推导与数据来源**，否则下一个读者只能照抄。
- **类型标签**：`机时估算` / `排期` / `ETA 误导` / `文档不误导`

---

## LRN-20261001-017 · 桥接代码**跨通道搬迁**时，动作**语义/量纲**没跟着改：MPC 行被静默 strawman 化

- **现象**：`evaluate_decompose.py` 的 `mpc_act` 把 MPC 的每列目标加速度经 `get_action_accel`
  转成 **绝对 ED 深度 ∈[0,1]**，再**当成加性调制 `ed_mod`**（×0.5）喂给 decompose 通道
  （`final_ed = clip(baseline_ed + 0.5·ed_mod, 0, 1)`）。
  实测后果：指令 `ED=0.75` → 实际 `clip(1.0+0.375)=1.0` **打满**；
  同一窗口 `MPC(Fair) meanED = 1.000` 而 `M0 规则 = 0.850`；且 AB 通道恒 0
  （`ab_mod=0` 落在 ±0.15 死区）⇒ **MPC 只剩"单调加 ED"一根杠杆**，永远不能减闸/牵引。
- **根因（关键，不是"写错一行"）**：桥接本身**不是错的** —— 它在**旧通道里是对的**。
  `evaluate_m1_m3_long.py`（**已按 ADR-022 删除**，git 历史可查）的 MPC 走**非 decompose** 通道
  （`hierarchical=False`），那里的动作语义就是**每列绝对目标加速度**，所以 `get_action_accel` 的量纲匹配。
  搬进 decompose 通道（动作 = 规则基线的**加性调制** `[ed_mod, ab_mod]`）时，
  **消费端语义变了、生产端没变** ⇒ 同一个函数从"正确"变成"错 2× 且单向"。
- **为什么有测试却没抓到**：`tests/test_nmpc_controller.py::test_nmpc_magnitude_comparable_to_rule_baseline`
  的**意图完全正确**（"同量级，非粗糙靶子"），但判据是 `abs(mean_ed 差) < 0.6`，
  实测差仅 **≈0.15**（0.85 vs 打满 1.0）⇒ **绿灯通过**。
  ⇒ **教训**：**容差型"同量级"断言对方向性失真（撞界/饱和）不敏感**；
  同量级必须同时断言**不撞界**（如 `mean_ed < 0.99`）或直接比对"指令 vs 实到"。
  （与 LRN-20261001-013 同型："有测试" ≠ "测试覆盖了该要求"。）
- **解决**：桥接改为**反解加性关系**（甲方）：先复算规则基线（`_rule_baseline_edab`，
  调用前后**保存/还原 `_cyclic_braking` 闩锁**以免评估侧"预演"污染 env 状态），
  再 `ed_mod = clip((desired_ed − baseline_ed)/0.5, ±1)`，并按 MPC 意图给 `ab_mod`
  ⇒ **MPC 与 D-RL 动作权限完全一致**（同 ±0.5 ED 调制 / 同 AB 阈值 / 同无牵引通道），
  差异回到"决策来源"。单测 5 项（含"交付 ED == 期望 ED"的行为级反解断言 + 编码可达性断言）。
- **预防**：
  - **动作/观测的语义与量纲属于"接口契约"，随通道走**；跨通道复用桥接前，
    必须先核对**消费端**的语义（本例：`get_action_decomposed` 的 `ed_mod` 是"增量"不是"绝对量"）。
  - **对比基线不得只靠"同量级"容差守住**：须同时断言**不饱和/不撞界**，或直接断言"指令 = 实到"。
  - **新增通道/模式时，把旧通道的每个桥接逐个过一遍**（本轮 E 段审计共发现 MPC 侧 4 处：
    M1 量纲、M2 牵引死赋值、M3 `inner_rule_cyclic` 能力回退、M4 默认值静默决定协议）。
- **类型标签**：`接口语义漂移` / `对比不公允（strawman）` / `容差断言失效` / `跨通道复用`

> **后续（2026-10-02，ADR-023）**：本条所述的"MPC 与 D-RL 同 ±0.5 ED 调制"中的**带宽**已按用户裁定**全局放宽为 `ed_mod_coef = 1.0`（全幅）**（两侧仍同款同带宽）；同时把 `evaluate_decompose.ED_MOD_COEF` 从**硬编码镜像常量**改为**从控制器默认值派生** —— 本条教训的"接口契约随通道走"由此升级为"接口契约只有一个来源（控制器默认值）"。见 `DIAGNOSTICS_2026-10.md`「放宽-2026-10-02」。

---

## LRN-20261002-001 · 评估脚本 `--out_suffix` 默认为空 ⇒ 同名结果 JSON 被**静默覆盖**

- **现象**：ADR-023 验证时用 `--mode mpc --max_steps 300`（**未带** `--out_suffix`）跑评估，输出落在 `outputs/results/decompose/eval_decompose_mpc_ms300.json` —— 该文件名**不含任何后缀**，与任何同参数的早前运行**同名**，写入即覆盖（`evaluate_decompose.py:526-529` 按 `mode + max_steps + rand + suffix` 拼名后直接 `open(..., 'w')`），且打印"已保存"不提示覆盖。
- **预期 / 实际**：预期 = "评估结果按时间戳归档、不覆盖旧文件"（`rules/EXECUTION_RULES.md` 第 3 条）；实际 = 默认后缀为空时**同名覆盖**，改前内容不可回溯（`outputs/**` 未纳入 git，部分文件虽被跟踪但该名不在其中）。
- **根因**：改名责任被完全外推给调用方（`--out_suffix` 靠人手填），默认 `''` 使"照文档原样复现命令"与"保留旧证据"直接冲突 —— 与 LRN-20261001-011 / 013 / 015「CLI 默认值静默决定语义」同一族。
- **解决**：凡**产出证据**的评估命令**一律显式带 `--out_suffix`**（本次 = `_adr023_coef1_check`，见与该次运行对应的结果 JSON 名）。
- **预防**：把 `--out_suffix` 当**必填**看待（`REPRODUCIBILITY.md` §十 各命令均已带后缀）；要根治须让脚本默认追加时间戳 —— 本次**未做**（会改变既有文档命令的产物名），登记为待议。
- **类型标签**：`证据覆盖` / `CLI 默认值静默决定语义` / `可复现性`

---

## LRN-20261007-001 · `Pool.map` 的**自由调度**配**有状态的 env** ⇒ 同 seed 训练结果不可复现

- **现象**：为把 `n_env=4` 的串行 rollout 改成进程并行（提速），先用 `multiprocessing.Pool.map`
  提交 4 条轨迹。冒烟（`--episodes 2`，同 seed）**连跑 3 次**，ep1 逐位相同，**ep2 的 reward 每次都不一样**
  （4063.10 / 4082.19 / 4083.80）。同一组冒烟换回**串行**路径连跑 2 次 ⇒ **完全逐位相同**
  （ep1/ep2 全列一致），证明串行是可复现的，不确定来自新并行路径。
- **期望 vs 实际**：期望"同 seed ⇒ 同结果"（项目铁律）；实际并行路径每次 ep2 都漂。
- **根因**：`Pool.map` 把任务分给**当时空闲**的 worker，**任务↔进程映射每次运行都不同**。
  而 worker 进程内的 env 是**跨回合复用**的（构造一次），其底层控制器（AB 最小充风/保持计时等）
  在 `reset()` 之间**存在少量跨回合残留状态**。于是"轨迹 ei 在第 ep 集拿到什么残留状态"
  取决于它**上一条任务落在哪个 worker** ⇒ 结果随调度漂移。（串行路径只有**一个** env、
  按固定顺序复用，残留状态确定 ⇒ 可复现。）
- **解决**：**轨迹 ei 固定绑定第 ei 个进程**——放弃 `Pool`，改为 `n_env` 个常驻进程
  （`Pipe` 一对一，先全下发再全回收，保持真正并行）。改后同 seed 连跑 2 次 **CSV 逐位相同**。
  另需在 worker 里 `torch.set_num_threads(1)`（多线程浮点归约顺序不确定，同样破坏可复现）。
- **止血与预防**：
  - **"并行加速"改的是执行调度，先问"被并行的单元是否无状态"**；有状态对象（env / 控制器 / 计时器）
    只要被复用，就必须**固定任务↔进程映射**，否则调度漂移 = 静默的不可复现；
  - 并行改造的验收**必须含"同 seed 连跑 ≥2 次逐位比对"**（本次正是靠它才发现——只看单次运行
    "数值合理"完全看不出来）；
  - 对照组同样重要：先证明**原路径可复现**，才能把不确定归因到新路径（否则会误判为项目本来就不可复现）。
- **类型标签**：`并行/调度` / `可复现性` / `有状态复用`

---

## LRN-20261007-002 · 后台长跑用 `| tail -N`（无 `-f`）⇒ 全程日志被吞、证据不可挽回

- **现象**：起 3 个 1400 ep 并行训练，命令末尾写成 `python -u run_training.py ... 2>&1 | tail -30`。
  后台 `output.log` **从启动到运行 7 小时始终 0 行**；每 50 ep 一次的 long_eval（peak / viol / 末速 三判据）
  **完全无法查看** —— 而 long_eval 恰是"是否达标"的唯一判据。
- **期望 vs 实际**：期望"后台 job 可随时看进度、看 long_eval 明细"；实际 = 运行中 0 可见，
  退出后**只剩最后 30 行**（中间全部丢失）。
- **根因（两层，缺一不可）**：
  1. **`tail -N` 不带 `-f` 的语义是"读完整条 stdin，保留最后 N 行再输出"** —— 它必须读到 **EOF**
     才知道哪 N 行是"最后 N 行" ⇒ ① 上游进程不退出，它一行都不吐；② 除最后 N 行外**全部丢弃**，不落盘。
  2. **训练侧只把 long_eval 明细 `print` 到 stdout**，落盘产物（`train_history.csv/json`、
     `train_loss.csv`、`metadata.json`、TensorBoard）**都不含**这三判据 ⇒ stdout 一被吞就**没有第二份**，
     属"单通道证据"。
- **解决**：后台长跑一律**重定向到文件**（`> outputs/logs/<语义前缀>.log 2>&1`，配 `python -u` 无缓冲），
  查看用 `tail -f` / `grep`；**不再用截断型管道**。
- **止血/补数**：本次 3 个 run 日志已不可挽回，但每 10 ep 有 checkpoint ⇒
  可用**离线评估任意快照**补出数值（评估脚本产出到独立结果 JSON），不受影响。
- **预防（铁律，用户明确要求"务必保证完整详细日志输出"）**：
  1. **禁止**对任何长跑（训练 / 评估 / 仿真）使用 `| tail` / `| head` 等**截断型管道**：
     `tail` 缓冲到 EOF、`head` 提前 SIGPIPE 掐断上游 —— 两者都会丢日志或误杀进程。
  2. **后台长跑必须完整落盘**：stdout + stderr 同时重定向到 `outputs/logs/` 下的日志文件
     （文件名带语义前缀），且 `python -u` 关缓冲；查看只看文件，不看后台 stdout。
  3. **凡"只 print、不进结构化产物"的信息都属高风险**：新增长跑输出时**必须同时**写结构化产物
     （CSV / JSON），让"证据"落盘、可回溯、可离线复查；**只 print = 迟早丢**。
  4. **判活/看进度靠产物**：`ps` + CSV 行数 + checkpoint mtime，不要依赖后台 stdout。
- **类型标签**：`日志丢失` / `证据不可挽回` / `后台作业` / `单通道证据` / `可复现性`

### 小节-2026-10-07 · 这次实际误了多少事 + 结构性修复（不再只靠人的纪律）

- **损失清单**：3 个 1400 ep 并行 run 的 **12 条 long_eval 记录全部不可挽回**（ep50/100/150/200 × 3 seed），
  连带全部 `logger.warning`（KL 早停、AB 闸门触发等）。已落盘的 `train_history.csv` 只有
  `episode/reward/peak/viol`，**不含 long_eval 的三条判据**（viol / peak / 末速）⇒
  "为什么没达标、卡在哪条判据、随训练如何演化"三个问题一个都答不了。
- **实际代价**：为重建证据被迫重跑 53 km 确定性评估（每次 ~30 min，为看轨迹需补多个快照）≈ 半天机时。
- **根因不是"忘了 tee"，而是产物设计**：达标才写 `long_eval_best.json`、未达标只 `print`
  ⇒ **失败不留痕**；叠加截断管道 = 证据归零。
- **结构性修复（已落地，取代纯纪律）**：
  1. `_long_eval` 每次评估**无条件**追加 `results_dir/long_eval_history.jsonl`
     （含未达标与异常行）——失败也留痕，`grep` 即得全轨迹（[train_runner.py](file:///d:/Code/MultiAgent/traffic_rl_project/src/trainer/train_runner.py#L509-L514)）。
  2. `run_training.py` 启动即给 root logger 加 `FileHandler` 写 `results_dir/run.log`（`mode='a'` 追加、`python -u` 无缓冲）
     ——调用方 shell 怎么写都丢不了（[run_training.py](file:///d:/Code/MultiAgent/traffic_rl_project/run_training.py#L55-L63)）。
  ⇒ 纪律（禁用 `| tail` / `| head`）仍是要求，但**即使有人再犯，证据也不会再丢**。

---

<!-- 该文档整理/压缩于 2026-10-01 -->
