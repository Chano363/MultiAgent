# AGENTS.md

## Repo layout

根目录下的研究项目：

- **`traffic_rl_project/`** — 实际的研究项目（**当前主战场**）。两阶段递进式 RL 研究：

  - 阶段一：无人机编队控制（已完成，历史成果，其仿真器依赖已移除）

  - 阶段二：**重载列车群组协同控制（进行中，核心工作）**

## Environment

WSL2 Ubuntu 24.04 + Conda (miniconda3) + Python 3.10 + NVIDIA GPU。
Python、conda、WSL 已装，不要重装。

```sh
source ~/miniconda3/etc/profile.d/conda.sh && conda activate traffic_rl
```

- 网络访问/下载用 **Windows PowerShell**（不是 WSL）。

- Windows Anaconda 位于 `D:\Anaconda\python.exe`（用于 CodeBuddy 原生调用 MCP 等）。

## Key commands

```sh
# 阶段二列车动力学/环境测试
cd /mnt/d/Code/MultiAgent/traffic_rl_project
python -m pytest tests/ -q

# 阶段二主训练（53km，formation-aware 机车级 ED/AB）
cd /mnt/d/Code/MultiAgent/traffic_rl_project
python run_training.py --experiment configs/experiments/formation_ed_ab_3train_1plus1.yaml --seed {0..4}
```

无 linter/typechecker/formatter 配置。遵循 PEP 8。

## 阶段二研究定位（重要）

**论文题目**：面向长大下坡场景基于多智能体强化学习的重载列车群组自动控制方法
**研究对象**：一万吨级 1+0 重载列车群组（单机牵引万吨列车，1机+\~100节货车，群组由多列组成）

**核心创新点：车钩力 + 多列群组 + 长大下坡 协同控制**（编队=最终目的，MARL=实现手段）。

现有长大下坡 RL 工作（Zhang2024 DQN、Liu2021 DDQN、Wang2025 DQN）**均明确忽略车钩力**；
本项目在长大下坡循环制动场景下**显式建模车钩力**，并扩展到多列群组协同。
实现方式（2026-09-08 ADR-013）＝ **RL 定策 + 底层控制器安全执行**（非纯 RL 直控 100 车厢）。

> **⚠️ 主轴与 RL 落位（2026-09-08，ADR-013，铁律）**：论文**最终目的是"编队"**（多列重载列车群组长大下坡保持安全列距 + 速度带一致 + 车钩力≤1000kN）；MARL 只是手段。**仅保留一套 formation-aware RL＝机车级 ED/AB 分工**（每台机车=智能体，ED 连续 / AB 离散档位，以编队为上下文）；底层由列内规则循环制动 + 车钩力安全层确定性执行。**废止**"编队层(列车级)RL + 列内层(机车级)RL 两层叠加 = T-MARL"表述（ADR-012→013）；编队层阈值 RL（`hierarchical` 每列 `coor_adj`）已下线，其 R0 +110042 不作当前主结果。来源：ADR-009/009.1（机级 ED/AB 机制）、ADR-013（唯一 RL 落位）。详见 `traffic_rl_project/docs/RESEARCH_POSITIONING.md` §1.3/§1.3.1、`DECISIONS.md` ADR-013。

分层框架：

```
编队目标（最终目的，非 RL）: 多列群组长大下坡协同（安全列距 + 速度带一致 + 车钩力≤1000kN）
       ↓ 由同一套 RL 承载（编队上下文）
RL 落位（唯一手段）: 机车级 ED/AB 分工，每台机车=智能体（ED 连续 / AB 离散档位）
       ↓ 目标速度/档位
底层执行（确定性）: 列内规则循环制动 + 车钩力安全层（enforce_coupler≤1000kN）
```

详见 `traffic_rl_project/docs/RESEARCH_POSITIONING.md`。

## 规范性问题（对比 / 立论铁律）

> **权威出处（SSOT）**：立论细节只认 `traffic_rl_project/docs/RESEARCH_POSITIONING.md` §1.5/§1.6 + `docs/logs/decisions/DECISIONS.md`（ADR 为准，最新见 ADR-016/ADR-017，覆盖旧的 ADR-010/ADR-014）；**勿从本文件/旧版本妄猜规范**——本文件仅放一句话指针，细看原文。
> 原则：先想清楚"哪些不可让、哪些才叫卖点、MPC 怎么比才不失公允"，再写论文/做消融/加对比。
> **文档规范出处**：文档治理/角色/三态/判断树 = `docs/README.md` + `docs/rules/README.md`（唯一规范，勿凭 AGENTS.md 猜测哪些真相定）。

- **主轴**：多列编队 + 队内车钩力≤1000kN + 安全列距 = 不可逾越底线；AB+ED 分工、1+1 = 锦上添花（不当主线）。
- **MPC 对比只留 Regime A（2026-09-16 ADR-016，B 已废止）**：不按坡道换 MPC 模型；MPC 逐线重喂该线 `grade_at` 图纸 + 在线标定 b0（公平标定），D-RL 跨线严格零微调（声明 no fine-tuning on target line）。立论 ="免重辨识成本"（零重标定代价的 MARL ≈ 逐线重标定后的 MPC）；不再提供"MPC 不重辨识失配"论证（领域常识，不证）。Protocol 逐实验标 A。
- **车钩异构（E4-H）【2026-09-16 SUPERSEDED，不承担立论】**：每车钩/每列车物理不同（实例异构≠离散）。**已从立论移除**——主 claim 只押"免重辨识成本"（ADR-016），与异构无关；`--hetero` 代码保留为可选鲁棒性（默认齐次零回归），不作泛化卖点、不进正文主表。
- **训练/评估时域（2026-09-16 ADR-017，铁律）**：三条独立维度不可混——①**单条 rollout 时域**（on-policy 窗口）②**评估时域**（覆盖剖面）③**总训练量**（episodes 预算）。本项目 on-policy MAPPO **训练=短窗口**，**评估=独立完整剖面单独跑（非"多段拼接"）**；训练量现状需对齐同类论文量级。跨线方向=长复杂剖面训→未见过剖面验。**具体数值/论文佐证见 ADR-017，勿在本文件复制以免随 SSOT 漂移**。
- 细看：`docs/RESEARCH_POSITIONING.md` §1.5；决策：`docs/logs/decisions/DECISIONS.md` ADR-016（覆盖 ADR-010 的 A/B）。

## 阶段二当前进度

> **进度流水（任务清单/✅ 历史项）已迁至 `traffic_rl_project/docs/PROJECT_PIPELINE.md`**（append-only 任务总览，唯一权威）。本文件仅为导航/立论指针入口，不承载进度表。当前主线：53km 主训练完成 5 seed，免重辨识跨线泛化评估推进中；详见 PROJECT_PIPELINE §P3 与 `docs/logs/diagnostics/`。

## 阶段二列车仿真设计

**动力学**（`src/train_dynamics/`，NeTrainSim 公式 + 多体扩展）：

- 多体积分器 `train.py`：每车独立质点，受力 = 牵引 − 制动 − Davis阻力 ± 坡度 + 车钩力；空气制动支持**双向传播 + 多源制动**（`ab_sources`，分布式动力/尾部动力）

- **制动** `braking.py`：

  - **电制动（ED）**：连续可调，仅机车，功率+粘着约束

  - **空气制动（AB）**：离散档位（RELEASE/MIN/SERVICE/EMERGENCY），**沿车列按制动波速向后传播**（常用 200m/s、紧急 250m/s）——纵向冲动的主要物理来源

- **车钩力** `coupler.py`：**MT-2 摩擦式迟滞缓冲器**（于宗泽2025/李蔚2023，Stribeck 静 750/动 500 kN、v_er=0.2、预压 200 kN、饱和 2270 kN @ 83mm 行程）+ **车钩间隙死区**（`_dead_zone`，`CouplerParams.coupler_gap_m` 默认 0.01m），复现杨敏"间隙→车钩力"规律，牛顿第三定律成对抵消；**【2026-09-07 ADR-011】统一回 MT-2**：机车 QKX100 弹性胶泥分区已彻底移除，全列（含机-货连挂钩）均 MT-2，WSL 两处实现（`coupler.py` 标量 + `train.py` 向量化）数值一致

- **坡度剖面** `grade_profile.py`：`GradeProfile` 分段剖面 + 3 种预置（樊运新：长大下坡-10.2‰/缓坡变陡坡/V型坡），每步按车辆位置实时更新坡度

**环境**（`src/environments/train_env.py`，`TrainFormationEnv`）：

- 状态（每车 4 维）：速度误差、与前车间距误差、车钩力、位置

- 动作（每车 1 维）：throttle ∈ \[-1,1]，>0 牵引（仅机车）、<0 制动

- **编组预设**：`consist_preset: '10kt_1plus0'`（1机+100货=10188t，论文研究对象）或 `default`

- **坡度剖面**：`grade_profile: 'long_downhill'/'gradual_to_steep'/'v_shape'`（长大下坡场景）

- 奖励：−0.5·速度误差 − 0.3·间距误差 − 0.15·平均冲动 − 0.15·峰值冲动 + 超限惩罚

**安全层**（`src/safety_layer.py`，`SafetyLayer`）：

- 规则式 ATP：限速、车钩力上限（**正常运行 1000kN / 紧急制动 2250kN**，Fu2019）、列车间距下限

- 在动作喂给动力学前修正，纯规则无学习参数

- 后续可叠加 CBF（QP 求解）做理论对标

## Gotchas（会坑你）

| 问题                                  | 解决                                                                                                                                                                                  |
| ----------------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| YAML `3e-4` 解析成字符串                  | 用十进制：`0.0003`                                                                                                                                                                       |
| Action dim mismatch                 | 环境交互 reshape `(num_drones,4)`；transition 存储拉平 12 维（阶段一遗留）                                                                                                                           |
| Loss 恒 0                            | 确保 `batch_size ≤ n_steps`，否则 buffer 永远不满                                                                                                                                            |
| INFO 日志不打印                          | 脚本入口 `logging.basicConfig(level=logging.INFO)`                                                                                                                                      |
| **Davis 阻力被放大 w 倍**                 | 空气阻力必须是标准 Davis 形式 `0.0018*C*A*V²`（独立于车重），不能 `area*cd*v²/w` 再乘 w（会把阻力放大数百倍，平衡速度被低估到 8m/s，20m/s 不可达）。已修复（见 VALIDATION\_BASELINE V2）                                                  |
| **制动传播被 dt 吞掉**                     | 传播延迟按**车辆累计长度/波速**算（真实重载数百米→数秒延迟），不要用车钩 free\_length                                                                                                                                |
| **安全层修正 → log\_prob 失配 → 策略发散**     | SafetyLayer 修正动作后必须用**实际执行动作**重算 log\_prob 存储（`info['executed_actions']` + `agent.get_log_prob`），否则重要性采样失效，viol 每 10ep 爆 85 倍（V5.1 三层 bug 链之一）                                      |
| **R0 车钩地基改版（2026-09-06）→ 历史车钩力绝对值作废** | 车钩模型升级：Stribeck 摩擦（静 750/动 500kN，v_er=0.2）+ 循环段间衰减启用（official 基线）+ 缓解排气两段式（波传播期满制动+exp(-t/τ=6s) 排风）。**【2026-09-07 ADR-011】统一回 MT-2**：机车 QKX100 弹性胶泥分区（月牙形两段刚度+胶泥幂律，2500kN@83mm）已彻底移除，仅作文献追溯。SSOT=`traffic_rl_project/docs/VALIDATION_BASELINE.md`「地基级建模体检 R0」+「诊断-2026-09-07」节；R0 前训练产物/评估 JSON/fig3-6 绝对值引用须附建模版本声明 |
| **Newmark 欠松弛污染最终状态 → 动力学整体缩水 25%** | 迭代欠松弛（α<1）只用于防发散，**收敛后必须取未松弛候选解** `(x_cand, v_cand)`。曾把松弛中间量当最终状态，稳态等效 v\_{n+1}=0.75·真解（2026-09-02 三层锚交叉测试发现，修复后多体 vs 独立 RK4 差异 8.77%→0.0005%）。**历史训练/验证绝对值都在 75% 动力学下产生，重跑前勿直接引用** |
| **缓解波建模差异 → 历史资产结论可能失真** | 历史训练**有的含缓解波(空气制动缓解波速传播)、有的不含**，产出于建模变更**之前**的结论不得直接引用；追加任何历史资产必须**并入记录训练路况+完整命令+seed/配置+建模版本声明**（规范见 `docs/rules/EXECUTION_RULES.md`「历史资产复现元数据与建模差异声明」） |
| **`ab_command=None`** **≠ 缓解**      | `None` = 不使用空气制动，须在 `_advance_control_once` 单独分支 `pass`（`None != RELEASE` 为真会把头车挂上 None 档 active 态，静止列车蠕动/能量不守恒）                                                                    |
| **静止起步牵引力泄漏**                       | `tractive_force` 在 `v<=1e-6` 分支必须先判 `throttle<=0 → 0`，否则 throttle=0 也输出满粘着牵引（\~882kN\@100t），平坡静止列车被推走                                                                               |
| **半隐式 Euler 不能做长时程交叉基准**            | 一阶方法数百年时程惰行系统性高估减速 \~9%；独立实现对照（`rigid_multi_particle.py`）用 **RK4**                                                                                                                  |
| **缓坡不超限等"规律类"文献判据需复现适用前提**          | 张二田"缓坡<1000kN"成立前提=同坡缓解+充分充风+平缓操纵；缓解不同步是单机车编组缓解冲击的主因（与坡度弱相关）。照搬绝对阈值会误报                                                                                                              |
| **value\_loss 爆炸 → 阈值误杀**           | 多智能体累计 returns \~1e4-1e5，value 网络初始输出 0 → value\_loss \~1e8 → 用 ValueNorm（PopArt）归一化 value 目标，不要用 `total_loss>1000` 硬编码阈值                                                           |
| **mcp 2.0 崩溃**                      | scholar-search-mcp 需 `mcp==1.9.3`（2.0 移除 `@app.list_tools`）                                                                                                                         |
| **程序化下载论文被 403**                    | MDPI/Wiley/IEEE/Hindawi 反爬，开放获取论文用**浏览器手动下载**                                                                                                                                       |
| 网络下载                                | 用 Windows PowerShell，别用 WSL                                                                                                                                                         |

## Config files（阶段二相关）

- `traffic_rl_project/configs/experiments/formation_ed_ab_3train_1plus1.yaml` — **主训练配置**（formation-aware 机车级 ED/AB，3 列×1+1=6 agent，53km，curriculum 上限 1200 步）
- 阶段一历史配置（`train_config.yaml` / `env_config.yaml` / `agent_lightning_config.yaml`）见归档，非当前主战场。

YAML `.get()` 路径需与 YAML 结构严格匹配，否则静默回退默认值。

## Project docs（何时读什么——按任务触发）

> 找任何文档先看 `traffic_rl_project/docs/README.md`（**唯一文档索引入口**：角色导航 + 核心思想→文档反向映射）。文档角色/模板/判断树见 `docs/rules/README.md`。
> **立论性规范（SSOT）**：主轴/MPC-Regime/车钩异构的权威出处 = `docs/RESEARCH_POSITIONING.md` §1.5 + `docs/logs/decisions/DECISIONS.md` ADR-016（本文件「规范性问题」只保留要点指针）。
> **⚠️ 校验能力边界（2026-09-16，勿当万灵药）**：`scripts/check_agents_links.py`（见 `docs/rules/EXECUTION_RULES.md`）只保证**引用卫生**（ADR 编号存在 / docs 路径非断链 / 个别数值内联警示），**不保证**内容规范、不误导、不循环论证。这三件事分别靠：①内容规范=ADR review + 人审（机器查不了语义）；②防误导=写前追问"这是流水还是立论、措辞是否含糊、推测是否写成结论"；③**防循环论证=引用必须锚定外部独立权威**（原始论文 / DOI / 领域公认），**禁止用"本项目自己的历史"当作"外部标准证明"**——那会制造 A 证 B 而 A 源自 B 的循环。任何校验脚本都不检查"你引用的那个权威是否独立于本项目"。**请勿因存在校验而省略 ①②③ 的人工判断。**

- **看进度 / 下一步 / 任务清单** → `traffic_rl_project/docs/PROJECT_PIPELINE.md`（P0/P1/P2/P3，已完成✅保留不删；先读这个）
- **写论文 / 立论 / 查创新点与文献 / 改规范** → `traffic_rl_project/docs/RESEARCH_POSITIONING.md`（§1.5=立论 SSOT）＋ `traffic_rl_project/docs/ITSC_PAPER.md`（论文唯一权威，含 `.tex`/`.pdf`）
- **写公式引用 / 技术→论文速查** → `traffic_rl_project/docs/REFERENCE_INDEX.md`
- **验证仿真器公式/数据/算法正确性、查历史诊断** → `traffic_rl_project/docs/VALIDATION_BASELINE.md`（论文→项目验证基准）
- **复现训练/评估结果** → `traffic_rl_project/docs/REPRODUCIBILITY.md`
- **做实验/诊断后留痕** → `traffic_rl_project/docs/logs/diagnostics/DIAGNOSTICS_YYYY-MM.md`（按月拆分，append-only）
- **做重大决策 / 改立论** → `traffic_rl_project/docs/logs/decisions/DECISIONS.md`（ADR，append-only）
- **踩坑 / 报错 / 参数不生效** → `traffic_rl_project/docs/logs/learnings/LEARNINGS.md`（append-only）
- **新建/改文档的规范与模板** → `traffic_rl_project/docs/rules/README.md`（判断树 + TEMPLATE_* + CHECKLIST_NEW_DOC）
- 阶段一历史（`learning_report.md` / `training_results_standardized.md`）＝ archived，仅回溯

## 修改 / 追加文档方法论（强，Docs-as-Code）

> 目标：文档不膨胀、不误导、SSOT 不破坏。日志类一律 **append-only**。

**4 条判断规则（改/增前先问）**

1. **这条信息属于哪个角色？** 实验/诊断数据 → `logs/diagnostics/`（按月文件）；重大决策 → `logs/decisions/DECISIONS.md`；踩坑/教训 → `logs/learnings/LEARNINGS.md`；工作计划 → `PROJECT_PIPELINE.md`；流水 → `.codebuddy/memory/`。判断树见 `docs/rules/README.md` 第四节。
2. **核心立论 vs 流水？** 立论（RESEARCH_POSITIONING/论文/规范）因观点演进可**覆盖式修订**（动机存档进 ADR）；流水（诊断/决策/教训）**只追加**，历史结论绝不篡改，被推翻就在原位标 `superseded` 并指向新结果。
3. **文件会不会过大？** 单文件接近 ~200KB 必须**物理拆分**：日志类按 `类型/时间` 分子目录新文件（如 `DIAGNOSTICS_YYYY-MM.md`、`VERIFICATION_LOGS_V*.md`）；**删除文档时不留 stub，而是一次性 Grep 全仓改写所有旧路径**（2026-09-10 已删 `docs/records/`、`docs/guides/`、`docs/archive/`，`docs/` 现仅含 logs/ papers/ rules/ + 顶层核心文档）。
4. **导航是否登记？** 新建/移动/拆分任何文档必须同步 `docs/README.md`（唯一索引入口）；若移动了引用集中的文件，用 Grep 全仓改一遍指向它的旧路径，指向仍存在的文件（跳现存文件而非留 stub 或断链）。

**日志类文件操作纪律**

- **追加**：文件末尾加 `### 小节-日期`，保留全部历史，不覆盖、不删除既有行。
- **移动/拆分**：物理挪文件至新位置，跨文件引用改指新路径；`docs/README` 更新角色表；涉及路径变更的历史留痕在原文标 `supersedes`。
- **删除旧文档**：不留 stub，一次性 Grep 全仓把旧路径改指向现存等价文件（或删违规引用行），确保无断链。
- **禁止**：为不存在的文档建空白占位页；把多条信息堆进同一文件不拆分；移动文件后留下断链。

**反冗余三铁律（每次改动自查，2026-09-10 沉淀）**

1. **孤儿文件即删**：不被任何文档索引、与其他文件字节相同（可 `Get-FileHash` 核对）且零引用的重复副本，无保留价值（实例：历史 `logs/dianostics_backup.md`）。
2. **构建垃圾进 .gitignore**：LaTeX `*.aux` / `*.log`、`tmp_*` 脚本一律不提交；根 `.gitignore` 已含 `*.aux` / `*.log`，遇到新型构建产物先补规则再删文件。
3. **备份可用 git 历史替代**：大文件一旦被 git 跟踪（`git log` 可恢复），拆分后的旧整文件快照即可删除；不要长期囤"手工整文件备份"。区分：绝不可删的是**曾被提交过、现在仍是 SSOT 的原始大文件**；可删的是**拆分/改版时复制的临时快照**。

## 文献库（docs/papers/）

**论文的双重用途**：既是文献引用，更是**项目正确性的验证基准**（见 `docs/VALIDATION_BASELINE.md`）——

- 仿真器公式/数据对照：Zhang2025（制动减压-压钩力）、杨敏（车钩间隙-车钩力）、樊运新（编组-冲动）、Tang2020（车钩力建模）、Fu2019（钩缓约束）

- 算法对照：Tang2020（多目标奖励）、Wang DQN（纵向冲动降幅基准）、Li CBF（安全层强化）、魏咪（分层框架）

- **PDF（10 篇）**：Tang 2020（多机车 RL+车钩力）、Fu 2019（钩缓约束）、Huang 2025（专家系统+DRL）、Zhang 2025（20kT 制动）、Heineken 2023（最优控制节能）、Yang 2024（蚁群节能）、Guo 2025（MARL 车队）、魏咪（车钩力分层）、樊运新（3万吨纵向冲动）、杨敏（车钩间隙）

- **arXiv 源码（3 篇）**：2504.19480（LLM 奖励设计）、2003.03327（智能列车运行）、2312.06858\_full（车队 MARL）

- **MCP**：`scholar-search` 已配置（Semantic Scholar + arXiv 双通道）

## Code conventions

- PEP 8

- 训练脚本入口配置 logging

- 临时脚本用后即删

- 检查点定期保存；只使用专业仿真器，禁止 mock 环境

- **训练/评估必须落权威 metadata**（强制，见 `docs/rules/EXECUTION_RULES.md`）：训练走统一框架 `run_training.py`（`training_metadata_guard`）或 legacy 入口 `train_fleet/`train_cyclic_braking`（`save_metadata`+`assert`）；评估用 `build_metadata` 内嵌结果 JSON 并时间戳归档。不进此路径的训练结论不认可、不得引用

- **`.codebuddy/mcp.json`** **已 gitignore**（含 API key，勿提交）

