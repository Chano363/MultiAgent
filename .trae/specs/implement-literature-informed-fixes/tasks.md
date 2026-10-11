# Tasks

> 顺序 = 成本/风险递增。**P0 基线必须在改代码之前跑**（它是"改动前"参照）。

- [x] Task 1: 根 `AGENTS.md` 文档索引去重为 README 指针
  - [x] SubTask 1.1: 删除「何时读什么（文档索引）」逐条清单 → 指向 `traffic_rl_project/docs/README.md`（唯一索引入口）+ `docs/rules/README.md`；保留「校验能力边界」警示
  - [x] SubTask 1.2: 复核 `docs/README.md`「快速导航」+「核心思想→文档映射」已覆盖改/建/审/排障/优化触发；缺则补一行（不新建索引文件）
  - [x] SubTask 1.3: 验证 `python scripts/check_agents_links.py` exit 0；`audit.py .` 无新增违规

- [x] Task 2: P0 三行基线（53km 完整剖面）
  - 执行说明（2026-10-01 修正）：三条命令改为在**冻结代码副本** `/mnt/d/Code/_p0freeze`（`git worktree`，冻结 SHA `d6ba3540`，即改动前工作树）中运行——因为三条是串行 python 进程，若在主树改代码会污染"改动前"语义。主树由此解锁。日志 `/mnt/d/Code/_p0freeze/traffic_rl_project/outputs/log_p0_baseline_20261001.txt`。
  - ⚠️ **命名与归属更正（重要）**：副本里跑出的 `_p0_*` 三个文件**实为"改动后"**——副本只是磁盘静态代码，`cd` **不等于**冻结（editable 安装的 path hook 把 `src` 无条件映射回主树；见 LRN-20261001-006）。**现行口径三行**以主树 `outputs/results_decompose/*_p0_*.json` 为准（`reward_schema` 特征字段可辨）；真正的"改动前"另起 `_pre_*` 后缀、经 `tmp_p0_freeze_boot.py`（显式插 `sys.path[0]` + 断言 `src.metadata.__file__`）重跑。
  - [x] SubTask 2.1: M0 规则行 —— `--mode decompose_m0 --grade shuozhou_real_53km --max_steps 36000 --n_seed 1 --eval_seed 0 --decision_interval 10 --out_suffix _p0_m0_rule_53km`
  - [x] SubTask 2.2: M1 `last` 行 —— **ckpt 路径更正**：规格原写的 `outputs/checkpoints_formation/seed0_nep1400/mappo_fleet_last_ep841_dec_ad2_cp_seed0_seed0.pt` **已不存在**（全仓仅 `final_seed1/..._ep841_..._seed1_seed1.pt`）。改用同一训练代（seed0、`last`、ADR-020 已引用的守线权重）`outputs/checkpoints_formation/final_seed0/mappo_fleet_last_ep1623_dec_ad2_cp_seed0_seed0.pt` + `--mode decompose_m1 --out_suffix _p0_m1_last_53km`
  - [x] SubTask 2.3: M1+mask 行 —— 同 ckpt/seed/剖面，仅加 `--mask_lever ab --out_suffix _p0_m1_maskab_53km`
  - [x] SubTask 2.4: 记录三条完整命令 / seed / `physics_version`；JSON 已落盘且**不覆盖**旧文件（新后缀）
  - [x] SubTask 2.5: 三行对比表已入 `DIAGNOSTICS_2026-10.md`「诊断-2026-10-01-P0 三行基线与 AB 通道裁定」+ ADR-021「执行闭环」②③
    - 结果：M0 **812.87 kN / 0 破线 / 98.01% band**；M1 **1643.49 kN / 77 破线 / 91.58%**；M1-maskab **1037.50 kN / 44 破线 / 95.85%** ⇒ **AB 通道（旧权重）裁定 = 净负**
  - [x] SubTask 2.6（追加）：改动前 `_pre_*` 全剖面对照（量化 A 的净效应）——三条 `_pre_*` 全部落地
    - **M0 行逐位相同** ⇒ A 不触发（规则层自身循环制动排程本就满足 222 s 充风窗）
    - **A 的有效域（修正表述）**：`_ab_gate` 在控制器里、**不分来源**；一旦 RL 扰动轨迹（M1-仅 ED：AB 步 1441→1105，−23.3%）A 即连带拦到规则层排程 ⇒ 正确表述 = "**在 222 s 充风窗内请求新增 AB 源**这一动作，与来源无关；纯规则轨迹恰好不触发"
    - **A 在全剖面上是"混合"效应（三配置一致）**：A 总是压低 AB 用量，但在 RL 参与的配置里**峰值一律升高、band 一律变差**（M1：1350→1643.49 kN / 99.62%→91.58%；仅 ED：1023→1037.50 kN / 97.07%→95.85%）⇒ **A 必须与 C+B 一起重训**；破线步数符号随配置变（M1 905→77 大降、仅 ED 21→44 反升）

- [x] Task 3: 改造 A —— AB 最小充风时间进动作空间（Zhang2024）
  - [x] SubTask 3.1: 核定 `ab_min_refill_s` / `ab_min_hold_s` 默认值（自 `papers/Zhang2024_DQN_CyclicBraking_Downhill.txt:250-255 / :287-295` + `VALIDATION_BASELINE.md` 充风时间项）；无出处则标 `待核实`
    - 结果：**文献依据已定位到式** —— Zhang2024 运行约束 (1) Air-refill time 的**式 (9)** `t_{b,j+1} − t_{r,j} ≥ T_a`（释放相 ≥ 最小充风时间），本实现与之一致；`ab_min_refill_s=222.0 s`（`T_a` 取 `VALIDATION_BASELINE.md:201` 张二田 S6 最短充风；范围 175~512 s 见 `:169` 赵紫宁2022）；`ab_min_hold_s=0.0` 且标 **`待核实`**——**已复查 Zhang2024 全文，其运行约束无"最短制动保持时长"一项**，故无出处、默认不激活（不编造）
    - **【2026-10-01 补：`ab_min_hold_s` 扩检结案（负结果）】** 追加检索《铁路机车操作规则》（铁运〔2012〕281 号 / TG/JW104-2012，国家铁路局公布文本）与赵紫宁2022 实测表 ⇒ **确认无"运行期最小 AB 保持时长"的可用出处**：Zhang2024 §2.2 仅三条运行约束；操规最接近的两条为"列检站减压 100 kPa 保压 **3 min**"（**站内保压试验**，非运行约束）与"重载列车 **v<30 km/h 不应缓解**"（**速度门限**非时长，且本场景 `v_min=40 km/h` ⇒ 空约束）；赵紫宁表 5-3 制动时长 212~1358 s 属**实测观测值**非下界。⇒ 标签由开放的 `待核实` 改为**已结案**，值保持 `0.0` 不激活。落点：`DIAGNOSTICS_2026-10.md`「检索-2026-10-01」、`REFERENCE_INDEX.md` 落地映射新增行、`configs/…yaml` + `multi_loco_controller.py` 注释同步、ADR-021 遗留② 状态更新、`PROJECT_PIPELINE.md` A 条目同步。
  - [x] SubTask 3.2: 在 `MultiLocoController` 维护逐机车 AB 计时状态，于 `get_action_decomposed()` 拒绝"充风不足新增源 / 保持不足释放源"，暴露 veto 计数
  - [x] SubTask 3.3: 参数经 config/实验 YAML 透传并进 metadata
  - [x] SubTask 3.4: 单测 —— 充风窗口内新增被拒 / 保持窗口内释放被拒 / 窗口外不干预

- [x] Task 4: 改造 D —— 安全层对 AB 的禁新增源权限（ADR-021 决策3 + Wabersich2021 预测式）
  - [x] SubTask 4.1: 在 `train_env._step_decomposed` 的 `safety.protect()` 之后，对本步**新增** AB 源按断面力 + 预测阈值做**丢弃**（**不含撤销已建立源**）
  - [x] SubTask 4.2: ~~复用 ED 支持 `scale<0.5` 时新源**降级一档**（SERVICE→MIN）~~ → ⚠️ **更正：该梯度臂经证明恒被 0.6 硬否决抢先 ⇒ 不可达，已删除**（`scale<0.5 ⟺ ratio>0.9`，而 veto 在 `p0 ≡ ratio·limit ≥ 0.6·limit` 时即返回 True；分支序决定恒不可达）。D 因此 = **纯 0/1 禁新增源**。详见 `LEARNINGS.md` LRN-20261001-007 / ADR-021「执行闭环」④
  - [x] SubTask 4.3: veto 计数进 `info`，供诊断 —— **并补** fleet 层 `TrainFleetEnv` 跨列车聚合（否则子环境计数被丢弃、生产接口看不见 D 是否生效）
  - [x] SubTask 4.4: 单测 —— 高力下新增被禁 / 低力不干预 / **无撤销分支**（断言不存在 revoke 路径）+ fleet 层聚合 + **源码级断言禁止"降级臂"回流**

- [x] Task 5: 改造 C —— 车钩力受控超限项进 reward（Tang2020/Wang2025）
  - [x] SubTask 5.1: `_calculate_reward_decomposed` 峰值口径改**断面力**（`coupler_interface_forces()` 每列 peak）
  - [x] SubTask 5.2: 新增**有界**超限项 `-6.0·min(peak_norm-1, 2.0)`（上界 −12.0）；`W_ov` 与速度带同量级、`OV_CAP` 限幅（防 value 震荡）
  - [x] SubTask 5.3: metadata 记录 `reward_schema` 版本标识
  - [x] SubTask 5.4: 单测 —— `peak_norm≤1` 项为 0 / 跨 1 有界跳变 / 不出现 `-80·ov²` 量级

- [x] Task 6: 改造 B —— per-agent advantage + 信用视界对齐（COMA/PRD-MAPPO）
  - [x] SubTask 6.1: `CentralizedValueNetwork` 支持 N 维输出（per-agent 价值头）
  - [x] SubTask 6.2: `compute_gae` 支持 per-agent（shape `[T,N]`）；`update()` 去掉 `unsqueeze(-1)` 广播
  - [x] SubTask 6.3: 新增**枚举**配置 `critic: centralized_scalar | per_agent`（默认 `centralized_scalar`，零回归、兼容旧 ckpt）；经 `registry.py` 透传
  - [x] SubTask 6.4: γ/λ 经主实验 YAML 设定为 `0.999/0.99`，使 1/(1−γλ) ≥ ≈90 s；训练启动打印并进 metadata
  - [x] SubTask 6.5: 单测 —— per-agent advantage 形状/无广播 / 默认分支与旧行为一致 / γλ 视界计算正确
  - [x] **SubTask 6.6**（本轮新增，属 B 的完整性）：① 修正 `effective_horizon_s` 漏乘 `dt` 的 **10× 偏差**（`decision_interval` 是**原始步数**不是秒：`steps×DI×dt`）——否则默认 γ/λ 会**误报"覆盖"**；② `value(a).squeeze()` 改显式 `view`（batch=1 时 squeeze 会把 `[1,N]` 压成 `[N]`）；③ `evaluate_decompose.probe_critic_mode()` 按 ckpt 内嵌 metadata（或 value 末层形状）判定 critic，否则 per-agent 权重装不进标量头 → 评估链路断裂

- [x] Task 7: 固定窗口 before/after 机制验证 + 全量回归
  - [x] SubTask 7.1: 对 A/D 做 **on/off 隔离对照**（**遵循 ADR-020 验收规程**：在确定性驱动策略上、量化机制自身贡献、声明有效域）
    - **窗口更正**：A 的默认充风窗 `ab_min_refill_s=222 s` ≈ **2220 原始步**，故 A 的对照**不能只用 1200 步窗口**（120 s 内该门几乎不触发）。A 用 **12000 步（=1200 s，含 ≥1 个完整循环制动周期）**。D 同样改用 **12000 步**：实测 1200 步窗口内 `ab_steps=0`（该窗口策略不走 AB 新增源通道）⇒ 无法区分 on/off。
    - A 的对照方式：同 ckpt / 同 seed / 同剖面，`ab_min_refill_s=222.0`（开）vs `0.0`（关）；报告 `ab_refill_veto_count` / `ab_hold_veto_count` 与断面力峰值、破线步、band_rate。
      - 结果：off 926.95 kN / AB 4447 步 / band 99.975% / 末速 78.18；on **914.37 kN** / **AB 2565 步（−42.3%）** / band 99.983% / 末速 64.26 / `ab_refill_veto` 6657 ⇒ **门强绑定、降 AB 用量、峰值略降、无破线**
    - D 的对照方式：同窗口下安全层 AB 新源权限开/关（harness 级把 `safety.ab_new_source_veto` 猴补为恒 False；**不新增生产开关**），报告 `info` 计数与峰值/末速变化。
      - 结果：env 侧真丢弃 **35/12000**（off 组 0）；**峰值逐位相同**（914.3721888138994 kN）、band/末速相同 ⇒ **D = 安全保证，不是性能杠杆**
      - ⚠️ **计数口径更正**：`veto_fired_calls`(1216) **含控制器侧既有调用点**（`multi_loco_controller.py:305`，每原始步 1 次），**≠** D 的贡献；生产键 `ab_safety_vetoed` 才是"env 侧真丢弃非空新源"的步数（35）。首版留痕曾把二者混为一谈，已在 `DIAGNOSTICS_2026-10.md` 更正。
  - [x] SubTask 7.2: 记录 C 的 reward 分项量级变化（新旧对比，验证超限项有界且可区分）
    - 结果（解析核对，Δ vs `peak_norm=1.0`）：pn=0.5 → 0；1.0 → 0；1.5 → **−3.0**；3.0 → **−12.0**（触顶）；5.0 → **−12.0**（限幅）⇒ 与 `−6·min(pn−1,2)` 一致，且**无 `−80·ov²` 量级**
  - [x] SubTask 7.3: `python -m pytest tests/ -q` 全量回归（记录 passed 数与退出码）
    - 结果：**222 passed / exit 0**（1039.55 s = 17 min 19 s；`pytest.ini` 的 `-qq` 抑制末行，故运行时用 `-o addopts=` 覆盖以取汇总行），见 `outputs/log_pytest_final.txt`
    - 注：D 的那条"梯度臂"误导性单测已随不可达分支一并删除（见 SubTask 4.2 更正）
  - [x] SubTask 7.4: 明确声明边界：C/B 改变训练目标/算法 ⇒ **旧权重失效**，最终性能结论需重训
    - 声明落在：`DIAGNOSTICS_2026-10.md`「改造…」五-⚠️ 边界 + 「P0…」二-⚠️三条边界 + ADR-021「执行闭环」⑥ + `PROJECT_PIPELINE.md` 长久计划 1

- [x] Task 8: 留痕 + 决策闭环 + 长久计划登记
  - [x] SubTask 8.1: `DIAGNOSTICS_2026-10.md` 追加两个小节：`### 诊断-2026-10-01-P0 三行基线与 AB 通道裁定`、`### 改造-2026-10-01-文献四改造落地（A/D/C/B）`（数据表 + 完整命令 + seed + 物理/机制解释）
  - [x] SubTask 8.2: `DECISIONS.md`：更新 ADR-021 状态 + 写入末节 **「执行闭环」**（四改造落地表 / P0 三行 / **AB 通道裁定 = 净负（旧权重）+ 不据此砍动作维度 + 重训后复核义务** / D 梯度臂删除 / 验收 / 边界 / 遗留）
    - **不新增 ADR-022**：reward 口径版本标识（`reward_schema`）与 `critic` 枚举属**接口契约**，已写在 ADR-021「执行闭环」① 与 `REFERENCE_INDEX.md` 落地映射中；单独立 ADR 会与 ADR-021 重复（防文档膨胀）
  - [x] SubTask 8.3: `PROJECT_PIPELINE.md` 登记**长久计划**（5 项：重训里程碑 / 跨线 / 完整预测式 safety filter / 重训后复核 AB 通道去留 / 改动前全剖面对照）
  - [x] SubTask 8.4: `LEARNINGS.md` 记本改造踩坑（LRN-20261001-006 冻结副本击穿、LRN-20261001-007 不可达梯度臂 + 猴补式单测）；`REFERENCE_INDEX.md` 落地映射同步 D 的更正；`.codebuddy/memory/2026-10-01.md` 同步

- [x] Task 9（收口时自查发现的缺口）：主训练 YAML 按 **ADR-017** 对齐 + 训练入口验证
  - 背景：主训练配置 `configs/experiments/formation_ed_ab_3train_1plus1.yaml` 与 ADR-017 硬要求**不一致**——`episodes: 120`（不足达标量）、缺 `n_env` / `warm_start` / `long_eval_*`、注释仍留已 SUPERSEDED 的"53km 全程由多段 1200 步拼接覆盖"、`env_cfg.max_steps: 36000` 注释误标"53km 全程训练"。不改则主训练线仍落在不足量上、注释继续误导。
  - [x] SubTask 9.1: `episodes: 120 → 1400`（ADR-017 §4）+ 注释"快速迭代用 `--episodes N`，勿改本值"
  - [x] SubTask 9.2: 新增 `n_env: 4` / `parallel_traj_len: 0`（§1 + 诊断-2026-09-10）、`warm_start: true` / `bc_episodes: 3` / `bc_epochs: 30`（诊断-2026-09-15）、`long_eval_interval: 50` / `long_eval_steps: 36000`（§2 + 诊断-2026-09-22）
  - [x] SubTask 9.3: 更正 `max_steps` / `curriculum` 注释为 ADR-017 §1/§2 口径（训练时域 = curriculum ≤1200 步，`TrainRunner` 每集覆盖 env 上限；评估 = 独立完整剖面）
  - [x] SubTask 9.4: **训练入口验证**（`--episodes 2` 覆盖，exit 0，280.7 s）：日志 `curriculum 边界: [(0,500),(10,1000),(20,1200)]` + `有效视界 91.0s → 覆盖` + `Fleet BC warm start: 采集 27000 条 … 30 epochs`；`metadata.json` 实测 `episodes=2`（覆盖链通 ⇒ YAML 1400 可解析）/ `n_env=4` / `parallel_traj_len=0` / `warm_start=true` / `bc_epochs=30` / `long_eval_interval=50` / `critic=per_agent` / `reward_schema=v2-bounded-overlimit-section-force`；2 集 `viol 0`。
  - [x] SubTask 9.5: 登记 —— `REPRODUCIBILITY.md` §十（主训练口径 + 覆盖纪律）、`DECISIONS.md` ADR-017「执行闭环」、`DIAGNOSTICS_2026-10.md`「验证-2026-10-01-主训练 YAML 按 ADR-017 对齐」、`PROJECT_PIPELINE.md` 缺口⑧、`docs/README.md` 映射行、根 `AGENTS.md`「Key commands」
  - ⚠️ SubTask 9.6（教训，非计划内）：首跑**漏覆盖 `dirs.figures_dir`** ⇒ 覆写了 09-25 历史学习曲线 PNG；已从原始 CSV 经同一绘图路径重建（无信息丢失）+ 记 `LRN-20261001-009`（此后冒烟跑必须同时重定向三个输出目录）

- [x] Task 10（为 1400 ep 长跑 + 主对比表做前置审计）：评估链路**四处**口径缺陷修复
  - 背景：重训是唯一合法性能路径，而"选哪个权重当 best"（`_long_eval`）与"主对比三行怎么出"（`evaluate_decompose --mode all`）分别是**选优器**与**主表生成器**——二者错了，重训再久也白费。故在启动长跑前逐条审计这两条链路。
  - [x] SubTask 10.1（①）：`TrainRunner._long_eval` 违规计数 O(n²) 放大（累计计数器逐步相加）⇒ 改每步增量；`evaluate_decompose.py` 09-25 已修同一处、此处漏改（LRN-20261001-010）
  - [x] SubTask 10.2（②）：`--mode all` 因 `--enable_mpc` 默认 False **静默只出 2 行（缺 MPC）**，且三行 Δ 摘要静默跳过 ⇒ 解析后即归一（置于 `build_metadata` 之前）（LRN-20261001-011）
  - [x] SubTask 10.3（③）：MPC 控制器逐回合状态未清零 ⇒ `--n_seed 3` 回合不独立 ⇒ `rollout()` 内逐回合 reset（`n_seed=1` 等价，旧数值不变）（LRN-20261001-012）
  - [x] SubTask 10.4（④）：`FairMPCController` 无 `solve_statuses` 而 `rollout` 直接下标取用 ⇒ **收尾 AttributeError、结果 JSON 未落盘 ⇒ 已跑完的 M0/M1 也一起白丢** ⇒ 补状态记录（口径与 NMPC 同构）+ 评估侧 `getattr` 降级保护（LRN-20261001-013）
  - [x] SubTask 10.5：新增 `tests/test_metric_accounting.py`（9 项，行为级 + 源码级防回流）；定向 9 passed
  - [x] SubTask 10.6：**实跑验证** —— ①`_long_eval` 每集触发（真 env，exit 0）：`viol 0 / peak 540kN / 达标=True` + best 与 `long_eval_best.json` 落盘；②`--mode all --n_seed 2`（fair）：**3 行齐全** + `fail 0` + 三行 Δ 摘要 + JSON 落盘
  - [x] SubTask 10.7：顺带测出算力事实并落文档：MPC 单次求解 ≈1025 ms ⇒ 53km MPC 行 ≈10.3 h/seed、`--n_seed 3` ≈31 h（已补进 `REPRODUCIBILITY.md` §十）
  - [x] SubTask 10.8：留痕 —— `DIAGNOSTICS_2026-10.md`「修复-2026-10-01」+「修复-2026-10-01b」两节（含完整命令/输出/危害定级）；`LEARNINGS.md` LRN-20261001-010~013；`PROJECT_PIPELINE.md` 缺口 ⑨~⑫；`docs/README.md` 映射行
  - ⚠️ SubTask 10.9（刻意不做，登记备查）：3 个 live 脚本同源 `viol` 计数写法（`compare_m1_baselines.py:53` / `evaluate_fleet_hier_80.py:46` / `compare_m1_init80.py:46`）属已废止 hierarchical 方案且全仓零引用 ⇒ 不静默改历史复现资产；若旧表引用其 `viol` 须按 O(n²) 膨胀处理

- [x] Task 11（长久计划第 1 项首次落地）：启动 ADR-021 口径 seed0 1400 ep 重训
  - 背景：四改造改变目标/算法 ⇒ **旧权重失效**，性能结论只能由重训产生；此前仅"登记为长久计划"，从未真正启动。
  - [x] SubTask 11.1: 启动器 `outputs/launch_retrain_adr021_seed0.sh`（`set -e` + conda 激活 + `exec python`），**三输出目录全部改指全新路径**（`outputs/checkpoints_formation/adr021_1400ep_seed0/{,results,figures}`）⇒ 零覆盖历史产物
  - [x] SubTask 11.2: 排障"长跑进程持久化"—— 两次 `nohup`/`setsid` 脱壳**均静默失败**（无进程、log 文件未创建）；存活探针 `nohup setsid sleep 90 …` 下次调用即查不到 ⇒ 判定 IDE Shell 工具**返回时回收本次调用的全部派生进程**（LRN-20261001-014）
  - [x] SubTask 11.3: 改用 IDE Shell 工具 `run_in_background: true` + **前台等待**启动 ⇒ **成功**：`PID 673` / 89.1% CPU / 输出目录已建；日志打出 `episodes=1400 / simcase=official / [信用视界] 91.0s → 覆盖`
  - [x] SubTask 11.4: 登记 —— `REPRODUCIBILITY.md` §十「重训里程碑」（启动器 / 两种调用场合 / 输出路径 / `--resume latest` 恢复命令 / 机时 ≈3.4 天 —— ⚠️ **该项机时已作废**，实跑实测更正为 **≈11.7 天/seed**，见 SubTask 11.6）；`PROJECT_PIPELINE.md` 长久计划 1 状态 🟡；`DIAGNOSTICS_2026-10.md`「启动-2026-10-01…」；`LEARNINGS.md` LRN-20261001-014；启动器注释更正为"两种场合行为不同"
  - ⚠️ SubTask 11.5（边界，显式登记）：本次由 **IDE 后台作业**承载 ⇒ 进程随 IDE 会话存活；**数天级无人值守须由用户在自己的 WSL 终端重跑启动器**（命令已写入 `REPRODUCIBILITY.md` §十）。seed1~4 待排算力。
  - [x] **SubTask 11.6（实跑后更正机时，本轮）**：启动时登记的 **≈3.4 天/seed 作废**（低估 **3.4×**）。实跑由训练自身进度条实测 500 步课时 **271 / 276 / 274 / 278 s/集**（`n_env=4`）+ BC ≈11 min；按 curriculum 折算 1400 集 ≈10.6 天，加 28 次 `long_eval` ≈1.1 天 ⇒ **≈11.7 天/seed**；**`1400 ep × 5 seed` 单机串行 ≈58 天**（原按 3.4 天会误得"两周可完成"）。两个低估来源：① 拿短训总墙钟 ÷ 集数当每集耗时（分子被 BC 稀释）；② tqdm 的 ETA 按当前课时线性外推（`105~108 h`），不随 curriculum 升到 1000/1200 步调整。更正落点：`REPRODUCIBILITY.md` §十（含推导）/`PROJECT_PIPELINE.md` 长久计划 1/`DIAGNOSTICS_2026-10.md`「启动-2026-10-01」四、/`docs/README.md` 映射行/`EXECUTION_RULES.md` 背景行；教训 `LEARNINGS.md` **LRN-20261001-016**。
    - ⚠️ **遗留裁决（需用户定）**：`1400 ep × 5 seed` 单机 ≈58 天不可行 ⇒ 须在「减课时/减集数」与「并行多机/多卡」之间抉择（**涉及 ADR-017 训练量铁律 ⇒ 属决策，不由 Agent 单方改**）。

- [x] Task 12（长训在跑期间做的主表路径第三轮审计）：评估链路**第五处**口径缺陷
  - 背景：前两轮审计（任务 10）修了四处；本轮在 seed0 长训运行期间继续审计"主表生成器"，再中一处**同源**缺陷。改动文件 `src/evaluation/evaluate_decompose.py` 属**独立入口脚本**（全仓无模块 import ⇒ 不在训练进程的"产物依赖闭包"内），故不违反本轮新立的「长训在跑期间行为性代码冻结」规范；该规范也据此由"`src/**` 一刀切"精确化为**闭包判定**（两问：会不会改变该 run 的 `env.step`/梯度/YAML 解析 + 该文件是否被训练进程导入）。
  - [x] SubTask 12.1: 定位缺陷 —— `--decision_interval` 默认 **1**，而训练 YAML/metadata 是 **10**；`REPRODUCIBILITY.md` §十 主对比命令**未传该参数** ⇒ 照文档跑即**训练/评估半 MDP 失配**
  - [x] SubTask 12.2: 修复 —— 默认改 `None` = **自 ckpt 内嵌 metadata 的 `hyperparameters.decision_interval` 读取**（自描述协议，与 `probe_critic_mode` 同源）；读不到退回训练标准值 `10` 且**明确打印**；解析置于 `build_metadata` **之前**（保证 `metadata.eval_args` 与实际一致）；显式传参行为不变
  - [x] SubTask 12.3: 顺带修正模块 docstring 中**不可用**的示例 `--mode decompose`（不在 `choices` 内，会 argparse 报错）⇒ `--mode decompose_m1`
  - [x] SubTask 12.4: 单测 +5（`tests/test_metric_accounting.py` ⇒ **14 passed**）：显式透传 / 自 ckpt 读取 / 缺失退回 10 / 旧 ckpt 无字段退回 / 源码级防回流（默认必须为 `None` + 解析须早于 `build_metadata`）
  - [x] SubTask 12.5: **真 ckpt 实跑验证**（`--mode decompose_m1 --max_steps 120 --n_seed 1 --out_suffix _di_fix_check`）：打印 `[decision-interval] 自 ckpt metadata 读取 decision_interval=10`；行标签 `interval=10`；JSON 的 `metadata.eval_args.decision_interval` 与 `args.decision_interval` **三处一致**；旧标量 ckpt 仍可装载（`critic=centralized_scalar` 兜底生效）
  - [x] SubTask 12.6: 登记 —— `DIAGNOSTICS_2026-10.md`「修复-2026-10-01c」+ 索引；`LEARNINGS.md` LRN-20261001-015（并归纳"CLI 默认值静默决定语义"这一**模式**，第二次复发）；`PROJECT_PIPELINE.md` 缺口⑬；`REPRODUCIBILITY.md` §十；`EXECUTION_RULES.md` 冻结规范精确化；`.codebuddy/memory/2026-10-01.md` 补充 8
  - ⚠️ SubTask 12.7（边界）：不改动任何**已显式指定** `--decision_interval` 的历史结果；唯一行为变化发生在"未传该参数"这一此前**未被用作主结果**的路径上

- [x] Task 12.8（同轮追加，纯读取 + 文档）：主表 checkpoint 选取审计
  - [x] 发现：`train_runner.py` 三类 checkpoint **存在性不同** —— `last_ep{N}`（含末集）**保证存在**；`ep{N}` periodic 存在多份；**`best_{cp_tag}` 仅当某次 `long_eval` 达标才写 ⇒ 可能根本不存在**（`long_eval>0` 时 `_maybe_save_best` 被跳过，`:300-302`）
  - [x] 危害：`REPRODUCIBILITY.md` §十 主对比命令写的是 `--checkpoint <best.pt>` ⇒ 若不存在会报路径错，而**实际训练成功** ⇒ 易误判"训练失败"
  - [x] 落地：`REPRODUCIBILITY.md` §十 补"存在性对照表 + 跑前 `ls` 确认"；`PROJECT_PIPELINE.md` 长久计划 1 登记待裁决；`DIAGNOSTICS_2026-10.md`「审计-2026-10-01-主表 checkpoint 选取」+ 索引
  - [ ] ⚠️ **待用户裁决①**：主表 D-RL 行取 `last_ep1400`（端态、无条件可复现）还是 `best`（long_eval 评估选优）？—— 既有口径"主结果用完整训练的 last"与 ADR-017 §2 的"long_eval 选优"在 `best` 改由**评估指标**选出后**不再互斥**；**裁决前不要只跑一行就下结论**
  - [ ] ⚠️ **待用户裁决②**：`1400 ep × 5 seed` 单机 ≈**58 天** ⇒ 「减课时/减集数」vs「并行多机/多卡」（涉 ADR-017 训练量铁律，不由 Agent 单方改）
  - [x] 边界：**未改动任何代码**（纯读取 + 文档），不触及长训的代码冻结边界

- [x] Task 12.9（同轮追加，纯读取 + 临时探针，已删）：主表 MPC 行"动作桥接量纲错配"审计
  - 背景：`DIAGNOSTICS_2026-09.md:53` 已记"fair-MPC 是 strawman"为 **still-unresolved**（处方 = 补规则内层）。本轮进一步发现**第二层缺陷**：即使开了规则内层，桥接量纲仍错。
  - [x] SubTask 12.9.1: 定位两套冲突语义 —— `get_action_accel`（`multi_loco_controller.py:377-394`）产**绝对 ED 深度 ∈[0,1]、永不为负**；`get_action_decomposed`（`:272-323`）按**加性调制**消费 `clip(baseline + 0.5·ed_mod)`；`mpc_act` 把前者直接当后者，**Fair 与 NMPC 共用**
  - [x] SubTask 12.9.2: **实测确认**（临时探针，跑完即删）：`mpc_act` col0=[0.75]×6 / col1=0；同态规则基线 `ed=[1.0,0.7]` ⇒ 实际 `final_ed` **打满 1.0**。与 `MPC(Fair) meanED=1.000` vs `M0 0.850` 观测一致 ⇒ ① 指令不兑现 ② 结构性不能减闸/牵引
  - [x] SubTask 12.9.3: 附带发现 —— 默认 `--mpc_type fair` 未开 `inner_rule_cyclic`（NMPC 开了），而该类注释称该开关正是"消解 strawman"手段 ⇒ 文档默认路径恰是没开的那条
  - [x] SubTask 12.9.4: 登记 —— `DIAGNOSTICS_2026-10.md`「审计-2026-10-01b」+ 索引（含实测输出与三层证据）；`REPRODUCIBILITY.md` §十 🔴 警示；`PROJECT_PIPELINE.md` 长久计划 2b
  - [ ] ⚠️ **待用户裁决（立论铁律，Agent 不单方改）**：(甲) 反解加性关系 / (乙) MPC 直接权限 / (丙) 仅开 `inner_rule_cyclic`（只修默认不一致）。**任选都会改 MPC 行数值 ⇒ 出主表前必须裁决**
  - [x] 边界：**未改任何代码**（仅新增/删除一个临时探针脚本）；与 `DIAGNOSTICS_2026-09.md:53` 的既有 unresolved 条目是**两层不同问题**（本条即使按旧处方"加规则内层"也修不好）

# Task Dependencies

- Task 2 **必须在 Task 3–6 之前**完成（提供"改动前"参照）
- Task 1 独立，可与 Task 2 并行
- Task 3 → Task 4 建议顺序（都动 AB 通道，A 先落地便于 D 的对照）
- Task 5 与 Task 3/4 独立（动 reward）；Task 6 独立（动算法）
- Task 7 依赖 Task 3/4/5/6 全部完成
- Task 8 依赖 Task 2 与 Task 7
- **不在本次范围**：1400ep×5seed 重训、多 seed 统计、跨线 20/35km 评估（登记为长久计划）