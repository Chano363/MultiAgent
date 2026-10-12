# Checklist

## Task 1 — 文档索引去重

- [x] 根 `AGENTS.md`「文档索引」区不含逐条 `docs/...` 清单，仅指向 `docs/README.md`（+ `docs/rules/README.md`）
- [x] 「校验能力边界」警示仍保留在 `AGENTS.md`
- [x] `python scripts/check_agents_links.py` → exit 0（实测 `[OK] ... 22 个已有 ADR`，EXIT=0）

## Task 2 — P0 三行基线

> ⚠️ **标签更正（2026-10-01，LRN-20261001-006）**：首轮"冻结副本"跑出的三行**实为改动后代码**
> （editable 安装把 `src` 无条件映射到主树）。**现行口径三行**以主树 `outputs/results_decompose/*_p0_*.json` 为准；
> 真·"改动前"另起 `_pre_*` 后缀、经 `tmp_p0_freeze_boot.py`（显式把副本根插入 `sys.path` + 断言解析）重跑，
> 属**追加项、不阻塞收口**（12000 步版 A 对照已完成；53km 版登记入长久计划）。

- [x] `outputs/results_decompose/` 下新增三份 `*_53km*.json`（M0 / M1 last / M1 mask-ab，主树）
- [x] 三份均含 `metadata.physics_version`（`1eab36352fd3`）与 `per_seed` 明细
- [x] 三行同剖面（`shuozhou_real_53km`）、同 `max_steps`(36000)、同 `eval_seed`(0)、同 ckpt、同代码，仅自变量不同
- [x] **未覆盖**任何既有结果 JSON（`--out_suffix _p0_*` 独立命名）
- [x] 命令 / seed / 剖面 / `physics_version` 已完整记录（`DIAGNOSTICS` P0 小节「三、复现命令」+ ADR-021「执行闭环」②）
- [x] **改动前全剖面对照**（`_pre_*` 三条，冻结 SHA `d6ba3540` + bootstrap 断言）：
      M0 **逐位相同**（A 不触发——规则层自身排程满足 222 s 充风窗）；
      M1-仅 ED：AB 步 1441→1105（−23.3%）、峰值 1023→1037.50 kN、band 97.07%→95.85%；
      M1 全通道：AB 16270→7656（−52.9%）、破线 905→77（−91.5%），**但**峰值 1350→1643.49 kN（+21.7%）、band 99.62%→91.58%（−8.04 pt）
      ⇒ **A 总是压 AB 用量，但在 RL 参与时峰值一律升高 / band 一律变差 ⇒ 不是纯改善，必须与 C+B 一起重训**；
      ⇒ **有效域修正**：A 对"新增 AB 源"**不分来源**，正确表述 = "在 222 s 充风窗内请求新增 AB 源"，纯规则轨迹恰好不触发；
      ⇒ 12000 步表的"峰值略降"**只在首 1200 s 成立**

## Task 3 — 改造 A（AB 最小充风时间）

- [x] `MultiLocoController` 存在逐机车 AB 计时状态与 veto 分支（充风不足禁新增 / 保持不足禁释放）
- [x] `ab_min_refill_s` / `ab_min_hold_s` 默认值**有文献或实测出处**；无出处则明确标注 `待核实`（不得编造）
      —— `222.0 s` 有出处（张二田 S6）；`ab_min_hold_s=0.0`
      ✅ **`待核实` 已结案（2026-10-01，负结果）**：扩检《铁路机车操作规则》（TG/JW104-2012）+ 赵紫宁2022 实测表 ⇒ 确认无"运行期最小 AB 保持时长"出处（详见 `DIAGNOSTICS_2026-10.md`「检索-2026-10-01」）
- [x] 参数进实验 YAML 与训练 metadata（`env_cfg.ab_min_refill_s / ab_min_hold_s`）
- [x] 单测覆盖三种情形（新增被拒 / 释放被拒 / 窗口外不干预）

## Task 4 — 改造 D（安全层对 AB 权限）

- [x] `_step_decomposed` 在 `protect()` 之后对本步**新增** AB 源做**丢弃**
- [x] ~~与 ED 投影**对称**：复用 ED 同一条 `0.8→0` 线性投影式（`scale<0.5 ⇒ 新源降级一档`）~~
      ⚠️ **更正：该梯度臂恒被 0.6 硬否决抢先 ⇒ 可证不可达，已删除**（`scale<0.5 ⟺ ratio>0.9`，
      而 veto 在 `p0 ≡ ratio·limit ≥ 0.6·limit` 即 True；分支序决定恒不可达）。D 因此 = **纯 0/1 禁新增源**。
      见 `LEARNINGS.md` LRN-20261001-007
- [x] 代码中**不存在**"撤销/削减已建立 AB 源"的分支（单测源码级断言）
- [x] veto 计数可从 `info` 读取 —— 子环境 `train_env` + fleet 层 `TrainFleetEnv` **跨列车聚合并暴露**
- [x] 单测覆盖高力禁新增 / 低力不干预 / 无 revoke 路径 / fleet 层计数聚合 / **禁止梯度臂回流（源码级断言）**

## Task 5 — 改造 C（车钩力超限项进 reward）

- [x] 车钩力项峰值口径 = **断面力**（非每车净力）
- [x] 超限项**有界**（`OV_CAP=2.0` 限幅，上界 −12.0），`peak_norm ≤ 1` 时为 0
- [x] 量级与速度带同档（`W=6.0`，不出现 `-80·ov²` 式大系数）
- [x] metadata 记录 `reward_schema`（实测 `v2-bounded-overlimit-section-force`）
- [x] 单测覆盖 0 项 / 有界跳变 / 量级上限

## Task 6 — 改造 B（per-agent advantage + 视界）

- [x] per-agent 分支下 `update()` 使用 `[batch, N]` advantage，**无** `unsqueeze(-1)` 广播
- [x] critic 形态用**枚举**（非布尔开关）；默认 `centralized_scalar` 与旧行为一致
      （旧 ckpt `metadata.critic=None` 仍按标量头加载，实测通过）
- [x] γ/λ 可经实验 YAML 设定（主 YAML 已置 `0.999 / 0.99`）；启动时打印有效视界 `1/(1−γλ)`
      并进 metadata（实测 `有效视界 91.0s → 覆盖`；`metadata.critic=per_agent`）
      —— ⚠️ 同时修正了视界换算漏乘 `dt` 的 10× 偏差（`decision_interval` 是**原始步数**不是秒）
- [x] 单测覆盖形状/无广播 / 默认分支等价 / 视界计算 / **ckpt→critic 探测**
- [x] 评估链路可用：`evaluate_decompose.probe_critic_mode()` 按 ckpt 内嵌 metadata（或末层形状）重建价值头

## Task 7 — 验证与回归

- [x] A/D 有 **on/off 隔离对照**（量化机制自身贡献，非"开了之后变好"）
      —— A：12000 步，AB 步 4447→2565（−42.3%）、峰值 926.95→914.37 kN、0 破线；
      D：12000 步，env 侧真丢弃 35/12000 步、**峰值逐位相同** ⇒ D = 安全保证而非性能杠杆
- [x] 对照在**确定性驱动策略**上给出（`select_actions(deterministic=True)`，同 ckpt/seed/剖面）
- [x] 明确声明各机制的**有效域**（A：AB 源新增/释放时序；D：本步全部新申请源、不撤销已建立源；C：仅"超限"段；B：训练侧）
- [x] 计数口径更正：`veto_fired_calls`(1216，含控制器侧既有调用点) **≠** 生产键 `ab_safety_vetoed`(35，env 侧真丢弃)
- [x] `python -m pytest tests/ -q` 全绿 —— **222 passed / exit 0**（1039.55 s；`-qq` 抑制末行，用 `-o addopts=` 取汇总；见 `outputs/log_pytest_final.txt`）
- [x] 报告中明确：C/B 使旧权重失效，最终性能结论需重训
- [x] **P0 三行 + AB 通道裁定**：M1 全通道 1643.49 kN / 77 破线 vs M1 仅 ED 1037.50 kN / 44 破线 ⇒ 旧权重上 **AB 通道净负**

## Task 8 — 留痕与长久计划

- [x] `DIAGNOSTICS_2026-10.md` 追加两个小节（「改造-2026-10-01-文献四改造落地」/「诊断-2026-10-01-P0 三行基线与 AB 通道裁定」），含数据表 + 完整命令 + seed + 机制解释
- [x] `DECISIONS.md` ADR-021 状态更新 + 末节「执行闭环」（四改造落地 / P0 三行 / AB 通道净负裁定 + 不据此砍动作维度 / D 梯度臂删除 / 验收 / 边界 / 遗留）
- [x] **不新增 ADR-022**（reward 口径版本标识与 `critic` 枚举属接口契约，已在 ADR-021「执行闭环」① + `REFERENCE_INDEX.md` 落地映射中，单独立 ADR 属重复）
- [x] `docs/logs/progress/PROGRESS_2026-10.md` 登记长久计划（重训里程碑 / 跨线 / 完整预测式 safety filter / 重训后复核 AB 通道 / 改动前全剖面对照）
- [x] `LEARNINGS.md`（-006 冻结副本击穿 / -007 不可达梯度臂 + 猴补式单测）+ `.codebuddy/memory/2026-10-01.md` 同步
- [x] 未对 append-only 日志做历史改写（仅追加；`DIAGNOSTICS`/`LEARNINGS`/`DECISIONS` 均追加，逻辑类文件为覆盖式修订）

## Task 9 — 主训练 YAML 按 ADR-017 对齐（收口自查缺口）

- [x] `episodes: 1400`（ADR-017 §4 总训练量达标；原 120 不足）+ 注释指明"快速迭代用 `--episodes N`，勿改本值"
- [x] `n_env: 4` / `parallel_traj_len: 0`（§1 短窗口并行 rollout）、`warm_start: true` / `bc_episodes: 3` / `bc_epochs: 30`、`long_eval_interval: 50` / `long_eval_steps: 36000`（§2 完整剖面独立评估）
- [x] `max_steps` / `curriculum` 注释更正为 ADR-017 口径（训练时域 = curriculum ≤1200，`TrainRunner` 每集覆盖 env 上限；评估 = 独立完整剖面，**不再**写"多段 1200 步拼接"）
- [x] 训练入口验证（`--episodes 2`，exit 0）：curriculum 边界打印正确、`有效视界 91.0s → 覆盖`、BC 热启动被触发、`metadata.json` 全部新字段生效且无解析报错 / 无 schema 异常
- [x] 登记：`REPRODUCIBILITY.md` §十、ADR-017「执行闭环」、`DIAGNOSTICS_2026-10.md` 新节、`docs/logs/progress/PROGRESS_2026-10.md` 缺口⑧、`docs/README.md` 映射行、根 `AGENTS.md` Key commands
- [x] ⚠️ 验证跑**未**污染历史产物（首跑漏覆盖 `figures_dir` 已修复：从原始 CSV 重建 PNG；`outputs/_cfgcheck/`、临时脚本、`/tmp/_figfix` 全部清理；记 LRN-20261001-009）

## Task 10 — 评估链路四处口径缺陷（长跑 + 主对比表前置审计）

- [x] ① `_long_eval` 违规计数改为**每步增量累加**（源码级断言 `viol += cur_viol - prev_viol`，禁止 `viol += int(info.get(...))` 回流）
- [x] ② `--mode all` 归一 `enable_mpc=True`（位置在 `build_metadata` 之前，保证 metadata 与实跑一致；MPC 块内旧条件兜底已删）
- [x] ③ `rollout()` 内逐回合 `_mpc.reset()`（行为级：3 回合 ⇒ `reset_calls==3`；`n_seed=1` 与旧行为等价）
- [x] ④ `FairMPCController` 补 `solve_statuses`（`__init__` + `reset()` + 每次 `minimize` 后 append，口径 = 求解器自身收敛标志）+ `rollout` 收尾 `getattr` 降级保护（缺状态源不崩、不产键）
- [x] 实跑验证：`_long_eval` 每集触发（`viol 0 / 达标=True` / best 落盘）；`--mode all --n_seed 2`（fair）⇒ **3 行齐全 + fail 0 + 三行 Δ 摘要 + JSON 落盘**
- [x] 新增 `tests/test_metric_accounting.py`（9 项，行为级 3 + 源码级 6）
- [x] 留痕：`DIAGNOSTICS_2026-10.md` 两节 / `LEARNINGS.md` LRN-010~013 / `docs/logs/progress/PROGRESS_2026-10.md` 缺口⑨~⑫ / `docs/README.md` 映射行 / `REPRODUCIBILITY.md` §十（含 MPC 算力提示）
- [x] 未静默改动 3 个已废止脚本的同源 `viol` 写法（登记备查，避免动历史复现资产）
- [x] **未改变任何已发布数值**：①只影响日志显示（判据语义等价）；③仅 `n_seed>1` 生效（`n_seed=1` 等价）；④此前**该路径根本跑不到**（②挡住），故不存在"已有 fair MPC 全剖面数值"被改动

## 边界（不得越界）

- [x] 1400ep×5seed 重训**未在本规格内完成**（仅登记长久计划）；⚠️ 收口后已**另起 Task 11 启动 seed0**（见下），seed1~4 仍未启动
- [x] 未实现完整 MPC 形式 predictive safety filter（仅登记为长久计划备选）
- [x] 未改动 MT-2 物理、未改断面力口径 SSOT
- [x] 未新增布尔开关（critic 用枚举）
- [x] **未因"AB 通道净负"而砍掉 RL 的动作维度**（ADR-013 的 ED/AB 分工结构保持；裁定只在旧权重上成立，重训后须复核）

## Task 11 — 启动 ADR-021 口径 seed0 1400 ep 重训（长久计划第 1 项首次落地）

- [x] 启动器 `outputs/launch_retrain_adr021_seed0.sh` 存在且可执行；内含 `set -e` / conda 激活 / `exec python`
- [x] **三输出目录全部指向全新路径**（`outputs/checkpoints_formation/adr021_1400ep_seed0/{,results,figures}`）⇒ 不覆盖任何历史产物
- [x] 未传 `--episodes` ⇒ 取 YAML 的 1400（总目标集数语义，ADR-019）
- [x] 进程**跨工具调用存活**已实证（非"启动打印"）：`pgrep` 到 PID 673、`ps -o etime,time,pcpu` = 04:42/04:34/96.8% CPU、输出目录已建
- [x] 启动日志证实配置按 ADR-021 生效：`episodes=1400 / simcase=official` + `[信用视界] gamma=0.999 gae_lambda=0.99 | 有效视界 91.0s → 覆盖`
- [x] ⚠️ **持久化边界已显式登记**：本次由 IDE 后台作业承载（随 IDE 会话）；数天级无人值守须由用户在自己的 WSL 终端重跑启动器（命令见 `REPRODUCIBILITY.md` §十，教训 LRN-20261001-014）
- [x] 登记：`REPRODUCIBILITY.md` §十「重训里程碑」/ `docs/logs/progress/PROGRESS_2026-10.md` 长久计划 1（🟡）/ `DIAGNOSTICS_2026-10.md`「启动-2026-10-01…」/ `LEARNINGS.md` LRN-20261001-014 / `docs/README.md` 映射行
- [x] **机时实测更正**：≈3.4 天/seed **作废**（低估 3.4×）⇒ 实测 500 步课时 271/276/274/278 s/集 + BC ≈11 min，按 curriculum 折算 1400 集 ≈10.6 天 + 28 次 `long_eval` ≈1.1 天 ⇒ **≈11.7 天/seed**；`5 seed` 单机串行 ≈58 天。四处文档同步更正（含可复核推导）
- [ ] seed1~4 重训（待排算力，不属本条）
- [ ] ⚠️ **遗留裁决（需用户定，涉 ADR-017 训练量铁律）**：≈58 天/5seed 不可行 ⇒ 「减课时/减集数」vs「并行多机/多卡」
- [ ] 重训完成后：完整 53km 主对比三行评估 + 跨线 20/35km + AB 通道复核（长久计划 2/4）

## Task 12 — 评估链路第五处口径缺陷（主表路径第三轮审计，长训期间）

- [x] 缺陷定位：`--decision_interval` 默认 **1** ≠ 训练 **10**，而 `REPRODUCIBILITY.md` §十 主对比命令**未传该参数** ⇒ 照文档跑即**训练/评估半 MDP 失配**（与缺口⑩`--mode all` 静默缺 MPC 行同源）
- [x] 修复：默认 `None` = **自 ckpt 内嵌 metadata 读取**；读不到退回训练标准值 `10` 并**明确打印**；显式传参行为不变
- [x] 解析置于 `build_metadata` **之前**（`metadata.eval_args.decision_interval` 与实际行为一致）
- [x] 顺带修正 docstring 中不可用示例 `--mode decompose` ⇒ `--mode decompose_m1`
- [x] 单测 +5 ⇒ `tests/test_metric_accounting.py` **14 passed**（含源码级防回流：默认必须为 `None`、解析须早于 `build_metadata`）
- [x] 真 ckpt 实跑：打印读到 `10`、行标签 `interval=10`、JSON `metadata.eval_args` 与 `args` 三处一致；旧标量 ckpt 仍可装载
- [x] 留痕：`DIAGNOSTICS_2026-10.md`「修复-2026-10-01c」/ LRN-20261001-015 / `docs/logs/progress/PROGRESS_2026-10.md` 缺口⑬ / `REPRODUCIBILITY.md` §十 / `EXECUTION_RULES.md`（冻结规范精确化为"产物依赖闭包"）
- [x] 边界：**不违反**长训期间的代码冻结 —— 该文件全仓无模块 import，不在训练进程的产物依赖闭包内
- [x] **未改变任何已显式指定 `--decision_interval` 的历史结果**（唯一行为变化在"未传参"这一此前未被用作主结果的路径上）