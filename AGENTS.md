# AGENTS.md

> **本文件 = 操作契约**：开工前的硬约束 + 指路牌。**不写项目介绍、不复制规则正文、不写"现在在做什么"。**
> 项目介绍与快速开始 → `traffic_rl_project/README.md`；现状与计划 → `traffic_rl_project/docs/PROJECT_PIPELINE.md` **§〇**；规则正本 → `traffic_rl_project/docs/rules/`。
> 职责边界由 `docs/rules/README.md` §六 定义：本文件只持有**导航元数据**与**不可外包的行为约束**，其余一律给指针。
> 下文 `docs/…` `src/…` `scripts/…` 路径均相对 `traffic_rl_project/`。

## 临时交接文档（HANDOFF）生命周期

- `HANDOFF_*.md`（含 `MPC_HANDOFF_*`）= **临时性文档，阅后即删**；**仓内最多同时存在一份**。
- 接手后先把仍生效的结论与待办迁入正式归宿（计划 → `docs/PROJECT_PIPELINE.md` §〇 / §0.4；决策 → `docs/logs/decisions/DECISIONS.md`；归因 → `docs/logs/diagnostics/`），迁移完成即删，**不留档、不追加**（git 历史可追溯，无需保留工作区文件）。

## 产出纪律（2026-11-18 自 HANDOFF 固化）

- 论文/文档类产出**仅在 owner 明确要求时写**（owner 多次纠偏：“我没让你写论文”“别写文档里”）；检索/调查结论默认只在对话给出，不新建 md、不未经要求塞进正式文档。

## 仓库布局

- `traffic_rl_project/` — 唯一研究项目（现行主战场）：重载列车群组协同控制。
- 阶段一（无人机编队）已完结，代码与产物均不存在。存档 `docs/logs/progress/ARCHIVE_PHASE1_UAV.md`；`history/` 是**阶段二早期代码**，不是阶段一成果。
- `.codebuddy/` `.trae/` `.workbuddy/` `defense_draft_work/` `reference/` = 工具侧 / 第三方资产，不参与研究构建。

## 环境

WSL2 Ubuntu 24.04 + Conda + Python 3.10 + NVIDIA GPU。**已装，不要重装。**

```sh
source ~/miniconda3/etc/profile.d/conda.sh && conda activate traffic_rl
cd /mnt/d/Code/MultiAgent/traffic_rl_project
```

- 联网/下载用 **Windows PowerShell**（不是 WSL）；MCP 等原生调用用 `D:\Anaconda\python.exe`。风格 PEP 8；`pyproject.toml` 有 `[tool.ruff]`（`line-length=100`，但只 select `E9/F63/F7/F82/F401`，**未启用 E501**）⇒ "ruff 没报错"不等于合规。

## 六条硬红线（违反即出事；正文只在指针里）

1. **云实例必须先审批**：只在正式规模训练那步开，且用户已批复规格与预算；开前给出规格 / 单价 / 预估总价 / 预计墙钟。**询价、probe、试开都算需审批范围**。关机须回查 `Status=Stopped` 且 `StoppedMode=StopCharging` 并贴回执。→ `docs/rules/SERVER_OPS.md`
2. **>5 分钟的长跑不得在 IDE 终端启动**：客户端关闭会连带杀掉 WSL 子进程（已发生 3 次）。用 `schtasks` 独立进程树；判活用 `pgrep` / `ps`，**不看日志末行**；完成判据 = `result.json` + `trajectory.npz` + `intervals.json` 三件齐，缺 `result.json` 即判中断；中断目录保留并写 `ABORTED_BY_INTERRUPTION.txt`，不得引用；同机多任务串行。→ `docs/rules/EXECUTION_RULES.md` §长跑
3. **验证默认整程**（49.6 km / `--steps 45000`）。短窗（≤6000 步）只作活性校验，**不得**当峰值或安全判据；必须短窗时须覆盖已知主峰 ±200 s 并写明依据。→ 同上 §验证协议
4. **三个输出目录必须一起换**：`checkpoint_dir` / `results_dir` / `figures_dir` 同时指向新 `run_tag`，否则覆写历史产物；禁止脚本往 `outputs/` 根级落盘。→ 同上 §产物目录规范
5. **训练/评估必须落权威 metadata**，否则结论不认可、不得引用；物理行为改动的验收口径 = 同 ckpt 同 seed 复跑 20 集，peak 逐位相同，**不另立判据**。
6. **训练/评估窗口开跑前必走管线 §0.8.2 训练窗口启动检查单**（判据锚有文献或 owner 依据 / 机制有文献对标物 / 从头训或奖励面完全不变的纯延长 / 快评协议已进启动脚本 / ADR-070 塌缩护栏在位 / **收账 closer 已以 schtasks 注册且心跳 rc=0**）：任一"否" = 不得开训，全部答案须留痕（ADR 或 ADR-072 式附段）；**开机与注册 closer 是同一动作序列，closer 不在位不得开机**（2026-11-17 空转三事故后的 owner 硬约束："机制层面确保不空转，而不是我提醒一次检查一次"）。→ `docs/PROJECT_PIPELINE.md` §0.8.2 · `docs/rules/SERVER_OPS.md` 铁律 12

## 云凭据

`.aliyun_ak.txt` 在 **Windows 用户目录**：第 1 行 AK ID、第 2 行 Secret，无字段名。Windows 用 `$env:USERPROFILE`；WSL 经 `/mnt/<盘>/Users/<用户名>/` 读——**`~` 是 Linux home，不是 Windows 用户目录**。明文禁止进回复 / 日志 / 诊断 / commit；脚本只读、不复制。细则 → `docs/rules/SERVER_OPS.md` §四。

## 开工前必读（改什么 → 读什么）

| 要改的东西 | 先读 | 不读的后果 |
| :--- | :--- | :--- |
| 动力学 / 车钩 / 制动 / 坡度 | `docs/knowledge/TRAIN_DYNAMICS_KNOWLEDGE_BASE.md` | 口径漂移 ⇒ 训练与评估不同源 |
| 观测 / 动作 / 奖励 / 安全层 / curriculum | `docs/knowledge/TRAIN_ENV_SAFETY_KNOWLEDGE_BASE.md` | 破坏 1000 kN 硬约束或 log_prob 一致性 |
| 训练/评估链路、trainer、配置 | `docs/knowledge/RL_TRAINING_EVAL_KNOWLEDGE_BASE.md` | metadata 不合规、覆写历史产物 |
| 立论 / 论文措辞 / 对比基线 | `docs/RESEARCH_POSITIONING.md` §1.2 / §1.5 / §1.6 · `docs/knowledge/MPC_BASELINE_KNOWLEDGE_BASE.md` | 写出已被 ADR 废止的主张（把"分层架构"当卖点）；把已删的 NMPC 当基线；或引用 MPC 数字前没读 `MPC_BASELINE_KNOWLEDGE_BASE.md` §10（正式对照行 + 作废产物清单 + `viol`/`rear_end_steps` 语义分家都在那里） |
| 引用数值 / 文献 | `docs/REFERENCE_INDEX.md` · `docs/VALIDATION_BASELINE.md` | 二手当一手、已决当待定 |
| **要拍板 / 判断"该不该请示"** | `traffic_rl_project/docs/rules/EXECUTION_RULES.md` §决策权限 | 过度请示（把判断成本推回 Owner）或擅自改方向（ADR-066 立案诱因） |

## 真源优先级（冲突时按此顺序，不是"看哪份"）

`DECISIONS.md` / `RESEARCH_POSITIONING.md`（立论）> `docs/rules/*`（执行规范）> `PROJECT_PIPELINE.md` §〇（计划）> `README.md` / `AGENTS.md`（导航）。
两个入口文件**无权对任何事实作终局解释**：它们互相打架 = 两份都错，回正本改。

## 证据使用纪律（本文件唯一不可外包的内容）

1. **一手优先**：来源 / 口径 / 是否已决策，一律回一手核实——`docs/papers/` 实际文件清单、`DECISIONS.md`、`RESEARCH_POSITIONING.md`。索引与二手记录不得当终结论。
2. **先读已定稿再开口 + 分清证据层次**：SSOT + ADR 是硬约束；不把已决策的事当"待定"重提。**方向层（ADR / 文献 / 数学论证）不被单次实测推翻**——实测只作诊断素材，要改方向必须针对其论证本身（正本 `docs/rules/EXECUTION_RULES.md` §证据三层分层）。
3. **检索无命中 ≠ 不存在**：Grep 未命中时改用 Glob / 列目录确认，再下结论。
4. **分清"明写"与"推断"**：只有文档明写的可用于下结论；推断必须标为推断，禁止冒充事实。
5. **两侧物理同源**：训练 / 评估 / 对比基线共用同一物理模型；禁止"一边改物理、一边做对比"。
6. **配置声明 ≠ 运行时生效（ADR-077 教训，不可外包）**：YAML/env_cfg 里写了某个机制开关，**不等于它在运行时真的生效**。ADR-077 查出三个 AB 门键只写在 YAML 里、env 从未读取下发 ⇒ 相关机制在两个训练窗口中**从未起作用**，而 ADR 与诊断都声称它生效 ⇒ 归因链失实。⇒ **凡声称某机制在训练中起作用，必须有运行时证据**（构造 env 后读 controller 属性 / 比对配置值），不能凭"配置里写了"下结论。新增 env_cfg 键必须同时做 **env 侧读取 + 逐列下发**，否则就是死配置；机器守卫 = `scripts/check_env_cfg_effectiveness.py`。探针必须走 env 的正规 `config.get` 读取路径（**不得手动 setattr 绕过**），否则探针与训练不同源，读数只能作 OOD 对照。
7. **读数跨机器不可互引，且形态量跨机器会翻转（2026-11-21 判决，不可外包）**：同一 ckpt 同参数，云端 ep6 快评 peak 1256.72、本地两次均 1478.85（差 17.7%，本地逐位可复现 ⇒ 差异来自机器不是代码），且**峰值列在跨机器下会翻转**（本地两次均为中列承压、云端为尾列承压）⇒ **任何"某列承压 / 某形态出现"的结论必须在同机同码同参下得出**；引用他机读数**只能引用"是否破线 + 量级"**；**判据的靶子必须是后果量（peak / 超限步），形态量只作辅助**。另：**`metadata.git_commit` 字段本身可能失真**（W4 窗口期间为真）⇒ "字段显示同源"与"实际同源"是两件事，须用**三重旁证**交叉验证：① `.preflight_ok` 的 `commit=`（实际上云标记）② 该 commit 的**提交祖先核验** ③ `git diff --stat <commit> HEAD -- src/ configs/` 确认数值路径无差异（§19.43 (1)）。另：**跨机器差异的浮点候选层已排除两项——线程序/BLAS 线程归约顺序、JIT 目标 ISA（均实测 md5 唯一）**，不得再重复怀疑；且"浮点微差会放大"**必须用受控扰动实测的放大系数回答，不得当假设写进结论**（§19.43 (2)(3)(4)）。正文 → `docs/rules/EXECUTION_RULES.md` §评估读数的机器口径与形态可迁移性。

## 校验能力边界（勿当万灵药）

`scripts/check_agents_links.py` 只保证**引用卫生**（ADR 编号存在 / 路径非断链 / 个别数值内联警示），**不保证**内容正确、不误导、不循环论证。三者分别靠：① 内容规范 = ADR review + 人审；② 防误导 = 写前自问"这是流水还是立论、推测是否写成结论"；③ 防循环论证 = 引用必须锚定外部独立权威（原始论文 / DOI），**禁止用"本项目自己的历史"当外部标准**。

## 领域地图（doc-init；**维护 2026-11-12**；只作导航，勿当现状引用）

| 领域 | 入口锚点 | 状态 / 注意 |
| :--- | :--- | :--- |
| 物理引擎（动力学 / 车钩 / 制动 / 坡度） | `src/train_dynamics/` · `src/physics_config.py` · `src/physics_governance.py` | 在役；改物理前读动力学 KB |
| 环境与执行层 | `src/environments/train_fleet_env.py`（顶层）· `src/environments/train_env.py`（单列子环境）· `src/safety_layer.py` · `src/controllers/` | 在役；控制器 = 规则基线（**不是 MPC**），1000 kN 钳制在安全层 |
| 训练与策略 | `run_training.py` · `src/trainer/` · `src/algorithms/` · `src/networks/__init__.py` | 在役；trainer 只有一条主链（runner → fleet / cyclic → specs），网络类写在 init |
| 评估与诊断 | `src/evaluation/` | 155 个脚本多为一次性诊断，在役清单未裁（→ PIPELINE §0.6 C2） |
| 实验配置 | `configs/experiments/formation_ed_ab_3train_1plus108.yaml`（主配置）· `configs/experiments/` | 以 _pilot / _probe / _debug 开头的是探针，不是论文配置 |
| 立论与决策 | `docs/RESEARCH_POSITIONING.md` · `docs/logs/decisions/DECISIONS.md` · `docs/CLAIM_LEDGER.yaml` | 立论唯一真源；claim 台账有机器守卫 |
| 知识库（改码前必读） | `docs/knowledge/`（动力学 / 环境安全 / 训练评估 / MPC 基线） | 在役；MPC 那本：NMPC 部分已随代码删除降为历史参考，**Tube MPC 现状 = §10** |
| 验证与规范 | `tests/` · `docs/VALIDATION_BASELINE.md` · `docs/rules/` · `scripts/check_{agents_links,claim_ledger,outputs_layout}.py` | 三个守卫只查形式，见上节边界 |
| 文献与引用 | `docs/papers/` · `docs/REFERENCE_INDEX.md` · `docs/REPRODUCIBILITY.md` | PDF 仍入库（待移出，§0.6 A2）；引用先查 INDEX |
| 实验证据 | `outputs/sim_validation/` · `docs/logs/verification/` · `docs/logs/diagnostics/` | 10 GB+ 级、非可再生，勿当缓存删；证据目录不进 git |
| 对外交付与汇报 | `docs/reports/` · `ppt_talk/` · `publication_archive/` · `tools/server_editable.py` | 不参与构建；`tools/` 只是 PPT 预览服务 |

