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
# 阶段二列车动力学/环境测试（69 个测试）
cd /mnt/d/Code/MultiAgent/traffic_rl_project
python -m pytest tests/ -q

# 阶段二 MAPPO 训练（长大下坡 + 万吨级 1+0）
cd /mnt/d/Code/MultiAgent/traffic_rl_project
python src/trainer/train_train.py --episodes 500 --preset 10kt_1plus0 --grade long_downhill

# 阶段一无人机训练（历史命令，MAPPO 唯一收敛；其仿真器 gym_pybullet_drones 已移除）
cd /mnt/d/Code/MultiAgent/traffic_rl_project
python src/main.py --mode train --algorithm MAPPO --episodes 500
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

> **权威出处（SSOT）**：`traffic_rl_project/docs/RESEARCH_POSITIONING.md` §1.5 + `docs/records/DECISIONS.md` ADR-010。这里只放一句话要点，细看原文。
> 原则：先想清楚"哪些不可让、哪些才叫卖点、MPC 怎么比才不失公允"，再写论文/做消融/加对比。

- **主轴**：多列编队 + 队内车钩力≤1000kN + 安全列距 = 不可逾越底线；AB+ED 分工、1+1 = 锦上添花（不当主线）。
- **MPC 对比 Regime A/B**：不按坡道换 MPC 模型；A=每线重喂 grade_at（公平，main/E1/E3）、B=不重辨识演不泛化（E4/E4-H，须声明 no-re-identification）。Protocol 逐实验标 A/B。
- **车钩异构**：每车钩/每列车物理不同（实例异构≠离散），是泛化卖点（E4-H，需 `--hetero` 逐参数抽样 + held-out）。
- 细看：`docs/RESEARCH_POSITIONING.md` §1.5；决策：`docs/records/DECISIONS.md` ADR-010。

## 阶段二当前进度

| 子任务                                                                                                                                        | 状态                                         |
| :----------------------------------------------------------------------------------------------------------------------------------------- | :----------------------------------------- |
| P0 列车动力学 Gym 环境（`train_env.py` + `train_dynamics/`）                                                                                        | ✅ 完成                                       |
| P0.5 仿真升级：电制动/空气制动波速传播/ATP 安全层/车钩力指标                                                                                                       | ✅ 完成（54 测试）                                |
| P0.5 研究定位 + 文献库搭建（docs/papers/）                                                                                                            | ✅ 完成                                       |
| P0.75 验证基准：提取 6 篇论文数据 + coupler 间隙死区 + 多源制动 + 紧急制动上限                                                                                       | ✅ 完成（54 测试通过）                              |
| P1 第9条 环境验证：修复 Davis 阻力 bug + 验证 20m/s 可达                                                                                                  | ✅ 完成（65 测试通过）                              |
| **P1.5 题目对齐前置**：长大下坡变坡剖面 + 万吨级 1+0 编组 + Zhang2024 验证基准                                                                                     | ✅ 完成（65 测试通过）                              |
| P1 第15条 MAPPO 迁移到列车（train\_train.py）+ 冒烟/短训验证                                                                                              | ✅ 完成（69 测试通过）                              |
| 全项目审计修复 7 项（free\_length 尺度/log\_prob 重要性采样/安全层/一致性）                                                                                       | ✅ 完成（83 测试通过，2026-08-20）                   |
| 方案A：缓解波下重训 + 健康场景固化（M1 +44200、低40=0、车钩力892kN）                                                                                              | ✅ 完成（2026-08-21）                           |
| **最终战略：分层控制重构（第1层规则循环制动 + 第2层 RL 阈值协同）**                                                                                                   | ✅ 完成（M1 vs M3 协同增量 +67,597，论文核心结果）         |
| **论文冲刺（可发表性收尾）**：叙事收敛 + 公平 DQN baseline + curriculum + Yang2025 对标 + 复现性加固                                                                 | ✅ 完成（2026-08-23，`ITSC_PAPER.md/.tex` 达投稿级） |
| **弱点补全（2026-08-24）**：curriculum 全量 3 seed（3/3 泛化，双 checkpoint 协议）+ 第二剖面 20km 完整重训评估（M1/M3/M4/M-DQN-fair/压力消融/5列）+ Limitations 改写 + PDF 重编译 | ✅ 完成                                       |
| P1 第16条 正式基线训练（长大下坡循环制动自动控制）                                                                                                               | ✅ 完成                                       |
| P2 奖励消融/多算法对比/阶段二报告                                                                                                                        | 🔄 论文冲刺已覆盖核心对比，阶段二报告待完善                    |
| P3 层级一（多列群组）环境 + 对比实验                                                                                                                      | ✅ 完成（含压力消融/5列扩展/公平DQN/MPC探索）               |

> **可投性结论（2026-08-24 更新）**：ITSC 论文 `docs/ITSC_PAPER.md/.tex` 已达投稿级且**三大弱点已补全**——① curriculum 全量 3 seed 训练：双 checkpoint（best/ep600）协议下 3/3 泛化成功，M1 随机化鲁棒性提升至 +35,464±966 / 0 碰撞；② 第二剖面（long\_downhill\_20km，-9.5\~-11.5‰）：Layer-1 免调参跨线验证 + Layer-2 完整重训，M1 协同增益/鲁棒性复现朔黄线结论（含压力消融单调性 +14,577→+23,298 与 5 列扩展）；③ Limitations 已改写为两剖面覆盖。PDF 已由 tectonic 编译生成（`docs/ITSC_PAPER.pdf`）。

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

## Algorithm status（阶段一结论，阶段二复用）

- **MAPPO**：唯一收敛算法（无人机 Best Reward 235.5），**迁移到列车复用**

- SAC：后期退化；PPO：不稳定；DQN：未验证

## Config files

- `traffic_rl_project/configs/train_config.yaml` — 每算法超参数（`training.hyperparameters.<algo>`，MAPPO 起步 `lr=5e-5, entropy=0.005`）

- `traffic_rl_project/configs/env_config.yaml` — 环境参数（阶段一 num\_drones 为主）

- `traffic_rl_project/configs/agent_lightning_config.yaml` — Agent Lightning 优化配置（阶段一）

YAML `.get()` 路径需与 YAML 结构严格匹配，否则静默回退默认值。

## Project docs（按阅读优先级）

> 文档治理与导航：**`traffic_rl_project/docs/README.md` 是唯一文档索引入口**——里面既有"按文档角色"的快导航，也有"**核心思想→文档**"的反向映射（找不到时先查它）。
> 规范/模板（工作计划、失败教训、历史经验、checklist）在 `docs/rules/`；新诊断→`docs/records/DIAGNOSTICS.md`、新决策→`docs/records/DECISIONS.md`。详见 `docs/rules/README.md`。
> **立论性规范（SSOT）**：主轴/MPC-Regime/车钩异构的权威出处 = `docs/RESEARCH_POSITIONING.md` §1.5 + `docs/records/DECISIONS.md` ADR-010（本文件「规范性问题」只保留要点指针）。

- `traffic_rl_project/docs/README.md` — **唯一文档索引入口**（文档角色导航 + 核心思想→文档映射）；先看这个
- `traffic_rl_project/docs/PROJECT_PIPELINE.md` — **pipeline 总览 + 任务列表（P0/P1/P2/P3，已完成的✅保留不删）+ 下一步，先读这个**
- `traffic_rl_project/docs/RESEARCH_POSITIONING.md` — **阶段二研究定位 + 创新点 + 文献库（20+ 论文）**；§1.5 = 规范性问题 SSOT

- `traffic_rl_project/docs/VALIDATION_BASELINE.md` — **论文→项目正确性验证基准**（仿真器公式/数据/算法对照 + 历史诊断留底）

- `traffic_rl_project/docs/records/DIAGNOSTICS.md` — 新的实验/诊断数据记录（承接文件）

- `traffic_rl_project/docs/records/DECISIONS.md` — 新的重大决策记录（ADR）

- `traffic_rl_project/docs/ITSC_PAPER.md` — 阶段二论文（唯一权威）｜`docs/ITSC_PAPER.tex/.pdf`

- `traffic_rl_project/docs/learning_report.md` — 阶段一报告（archived）

- `traffic_rl_project/docs/training_results_standardized.md` — 阶段一学术成果（archived）

- `.learnings/LEARNINGS.md` — 踩坑记录

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

