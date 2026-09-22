***

title: 重大决策记录（ADR）
date: 2026-09-01
status: active
owner: Owner
------------

# 重大决策记录（Architecture Decision Records）

> **为什么**：把"为什么这么做、当时考虑了哪些选项、最后选谁、代价是什么"固定下来。
> 防止几个月后 AI/人无法还原决策上下文。append-only，废弃决策标 `superseded` 加新条目，
> **不篡改已写入的旧决策**。

## ADR 模板

```
## ADR-编号 决策标题 - 日期
- 状态：决策 / 实施 / 修订 / superseded
- 背景：为什么需要决策（动机、约束）
- 选项与权衡：
  - 选项 A：...（优点/代价）
  - 选项 B：...（优点/代价）
- 结论：选 A，理由：...
- 后果：实施后验证结果、带来的新约束
- 相关：链接（对应 PIPELINE 条目 / 诊断 / LEARNINGS）
```

## 已补录的历史决策（ADR-002 \~ ADR-007）

> 2026-09-01 从各诊断/验证章节提炼补录：ADR-002 限速区间\[40,80]；ADR-003 加速度动作空间；
> ADR-004 分层架构重构（论文核心）；ADR-005 方案A回退+废弃APF；ADR-006 公平DQN；ADR-007 简化MPC双策略。
> 其余较细决策仍散落在 `VALIDATION_BASELINE.md` / `DIAGNOSTICS.md` / `VERIFICATION_LOGS.md` 各小节（留痕来源）。

***

## ADR-008 引入 ARIS 跨模型审阅通道（Auto-claude-code-research-in-sleep）- 2026-09-02

- 状态：实施

- 背景：论文重构期（MARL vs MPC 主轴）需**独立第二模型**对抗性审出单模型自审的盲区偏袒；现有 scholar-search MCP 只能检索，无法做裁决型评审。

- 选项与权衡：

  - A. 复制 ARIS skills 进项目 `.trae/skills/`：污染项目、升级难同步

  - B. `@` 引用 ARIS 仓库（不用），MCP 配 `llm-chat`，reviewer=OpenRouter `minimax/minimax-m3:free`（与 executor deepseek 跨族）→ 选用

  - 审阅后端选择：TRAE 无 codex MCP → 用 llm-chat 接 OpenAI 兼容端点（Minimal 依赖仅 httpx，`D:\Anaconda\python.exe`）

- 结论：选 B。跨族对抗评审（`family_relation=different`）对 [ITSC\_PAPER.md](file:///D:/Code/MultiAgent/traffic_rl_project/docs/ITSC_PAPER.md) 独立戳中 3 条硬伤（title-内层失配 / fair-MPC strawman / 证据薄）。

- 后果：

  - 集成遇 TRAE 密钥遮罩坑（`sk-...` env 被替换成 `\u2026`），已用 `LLM_CRED_FILE`<本地 key 文件路径>绕开（[server.py L52-72](file:///D:/Code/MultiAgent/Auto-claude-code-research-in-sleep/mcp-servers/llm-chat/server.py#L52-L72)）

  - 评审结论反哺论文：标题改 "Hierarchical Hybrid MARL"、补 "MPC+规则内层" 公平基线、20km/5 列结果补全指标升独立小节

  - 新依赖约束：OpenRouter 公端点 `independence_verified=unverified`；更严格独立需私有部署 ump/challenge 端点

- 相关：`docs/logs/diagnostics/DIAGNOSTICS_2026-09.md`（诊断-2026-09-02-ARIS 试点）；`docs/PROJECT_PIPELINE.md` ARIS 条目；ARIS 仓库 `docs/TRAE_ARIS_RUNBOOK_CN.md`

## 条目区

## ADR-001 文档规范化治理（Docs-as-Code） - 2026-09-01

- 状态：实施

- 背景：`VALIDATION_BASELINE.md` 膨胀至 177KB（验证基准+诊断+踩坑混装）；根目录残留多个临时脚本；
  文档无规范模板、无统一导航；阶段一/ITSC 衍生版职责不清。

- 选项与权衡：

  - A. 物理切碎重排所有大文件 → 打断历史链接、可发现性丢失，信息"在但找不到"，违背"信息不丢"

  - B. 治理层 + 导航 + front-matter + 归档标记 + 承接文件（选用）→ 历史原样保留，新增走规范，链接不断

- 结论：选 B。**信息安全的判据是"可发现性 + 可复现"**，不是"物理落到哪个文件"。

- 后果：

  - 新建 `docs/rules/`（规范+3 模板+checklist）、`docs/records/DIAGNOSTICS.md+DECISIONS.md`、`docs/logs/README.md`、`docs/README.md`（导航地图）

  - 根目录临时脚本移 `docs/archive/scripts/`（原文保留），`server_editable.py` → `tools/`

  - 阶段一与 ITSC 衍生版标 `status: archived`（不移路径，防碎链）

  - `VALIDATION_BASELINE.md` 顶部加导航头 + 承接说明，正文不删

- 相关：`docs/rules/TEMPLATE_*.md`、`docs/README.md`；工作日志 `.codebuddy/memory/2026-09-01.md`

## ADR-002 限速区间 \[45,65] → \[40,80] - 2026-08-17

- 状态：实施

- 背景：用户质疑限速区间不能仅凭1-2篇论文取；需核对研究对象/研究问题/行业标准。

- 选项与权衡：

  - \[45,65]（樊运新3万吨参数）：吨位与对象（1万吨朔黄线）不一致，物理不可行（已验证车钩力超限540次/掉速）

  - \[40,80]（Zhang2024 + 行业规则 + 《重载铁路设计规范》）：上限80=朔黄线实际线路限速；下限40=2万吨最小缓解速度

- 结论：改 \[40,80]。依据：线路/行业标准与研究对象一致 + 物理验证（第1层成功，车钩力150kN/速度71km/h）。

- 后果：`train_fleet_env.py` v\_max 65→80、v\_min 45→40；82 测试过。

- 相关：`docs/logs/verification/VERIFICATION_LOGS_V5.md`（V5.24）

## ADR-003 动作空间：目标速度 → 目标加速度 - 2026-08-15

- 状态：实施（后被 ADR-004 分层架构取代第1层策略，但"控加速度能学"原则保留）

- 背景：列间 RL 用"目标速度"动作，但长大下坡物理极限(16.7m/s)低于目标(20m/s)→动作饱和、Reward 无区分度→策略不学习（KL早停=0、best 不更新）。

- 选项与权衡：

  - 目标速度：动作被物理锁死，RL 学无可学（诊断：动作+1/+0 60步奖励与末速完全相同）

  - 目标加速度：直接影响物理，有真实学习区分度（对齐 Zhang2021/Hua2024）

- 结论：改用目标加速度 `a∈[-max_accel,max_accel]`（方案B）。Reward 单调改善40%（-885→-546），列间 MARL 首次真正学习协同制动。

- 代价：加速度更激进致 peakCoupler 偶尔超 1000kN（viol\~1）。

- 相关：`docs/logs/verification/VERIFICATION_LOGS_V5.md`（V5.10）

## ADR-004 最终架构：放弃"RL 学单列循环制动"→ 分层（第1层规则 + 第2层 RL 阈值协同）- 2026-08-22

- 状态：实施（论文核心结构）

- 背景：RL 学单列循环制动结构性失败（缓解波长时延6s→PPO信用分配失效 + 车钩力多体耦合→探索即爆炸）。论文/行业标准均用规则循环制动。

- 选项与权衡：

  - RL 学单列循环制动：失败（时长/信用分配+碰撞）

  - 分层：第1层规则循环制动（领域最优 523kN）+ 第2层 RL 只做阈值协同（v\_max\_adj/v\_min\_adj ±5km/h，不动 throttle）

- 结论：分层重构（`HierarchicalController`）。协同增量 M1(+33494) vs M3(-76548) = **+110042**；M1 追尾0/车钩力864kN/间距182m 全健康，M3 追尾392。

- 后果：成为论文核心创新点；83 测试过。

- 相关：`docs/logs/diagnostics/DIAGNOSTICS_2026-08.md`（诊断-2026-08-22 最终战略分层重构）

## ADR-005 方案A 人为坡段错开 → 回退；废弃 APF 势场控制器 - 2026-08-20

- 状态：已回退

- 背景：方案A（`start_offset_m` 中段起步 + `spacing_m` 静态坡段错开）是人为制造的相位差，偏离"各列同坡段起步、随间距保持自然产生动态相位差"方针，且前列/后列缓解不同步→车钩力持续超限(1218-1226kN)+M1 不收敛。

- 选项与权衡：

  - 引入 Zhang2021/Guo2025 APF 势场控制器解耦重构：生搬硬套（他们=地铁平直/单质点/忽略车钩力/无坡度，可自由±加速；而长大下坡向下可制动、向上无牵引）

  - 移除人为错开，恢复普通场景（各列同坡段起步）

- 结论：废弃 APF，回退移除 `start_offset_m`/`spacing_m`。正确分层 = 列间 RL 宏观协同 + 列内规则循环制动 + 车钩力安全层。35 测试过，无回归。

- 相关：`docs/logs/diagnostics/DIAGNOSTICS_2026-08.md`（诊断-2026-08-20 E25 方案A / 回退方案A）

## ADR-006 引入公平 DQN baseline（M-DQN-fair）消解审稿质疑 - 2026-08-23

- 状态：实施

- 背景：主结果用朴素 M-DQN（Zhang2024 式：学单列循环制动、无安全层、无协同）对标，审稿人可质疑"DQN 输是因为没协同/没安全层而非 DQN 不如 MAPPO"。

- 选项与权衡：

  - 保持朴素 DQN：公平性不足，结论易被击穿

  - 补同架构公平 DQN：第1层规则循环制动 + 车钩力安全层（与 M1/M3/M4 完全相同），第2层换每列独立 DQN 输出离散 coor\_adj（同 obs/reward，完全同架构）

- 结论：引入 M-DQN-fair。完整评估仍追尾229步(固定65)/89.2±109.4(随机化)，与 M3 相当、远不如 M1(MAPPO, 0追尾)；车钩力守住900kN（证明安全层生效，排除干扰）。

- 相关：`docs/logs/diagnostics/DIAGNOSTICS_2026-08.md`（诊断-2026-08-23 公平DQN baseline）

## ADR-007 简化 MPC baseline 双策略（Yang2025 参考线 + 公平 DQN 主基线）- 2026-08-23

- 状态：实施

- 背景：需对标 MPC 范式，但完整多质点 QP MPC 复现代价高。

- 选项与权衡：

  - 用简化 MPC 作严格公平对比：预测模型粗糙+无车钩力约束编码，不公平

  - 双策略：主 baseline 用公平 DQN（干净）；Yang2025 作文献参考线引用其单列 MPC 数据；说明"完整 MPC 复现为未来工作"

- 结论：采用双策略。诚实呈现简化 MPC 在多列协同的固有挑战（需精确车钩力预测模型），但不冒充公平对比。

- 相关：`docs/logs/diagnostics/DIAGNOSTICS_2026-08.md`（诊断-2026-08-23 简化 MPC 协同 baseline）

## ADR-009 智能体分解重构：多机车分布式动力 × 电空双制动分工（融合） - 2026-09-02

- 状态：决策（方向已定，待仿真器改动方收尾后实施）

- 背景：导师批评"3 列 1+0 群组叫多智能体不合适"——1+0 每列仅 1 台动力源，把"列车"当智能体本质是 3 条曲线的宏观优化，与单体优化缺乏本质区分，'多智能体' 名不符实（宋宗莹2026 同风险）。需重构智能体分解，锚定在**物理独立动力源**上。

- 选项与权衡：

  - **A. 1+0→1+1/多机车分布式动力**：多台物理动力源的牵引/电制动/缓解错峰分配=真多智能体。依据 Tang2020/姚小沛2013/赵紫宁2022/樊运新2024。优点：物理锚定扎实；代价：改编组+多机车协同训练。

  - **B. 电制动/空气制动分离为双智能体**：同一列内 ED(连续)/AB(离散) 分工决策。依据 Yu2022（电空联合制动，Actuators 11(6)145）。优点：列内即多智能体、不依赖多车；风险：需论证为何不单策略多输出头。

  - **C. A×B 融合（选用）**：多机车作"体"、每机车同时决策电/空制动→列内真多智能体分工，与既有分层兼容。最扎实；代价最大，需彻底重构编组+环境+训练。

  - D. 先不做仅立论：工作量最小，但无法回应导师批评、无法产出新结果。

- 结论：选 **C（融合）**。渐进式：立论（本文档+RESEARCH\_POSITIONING 1.3.1）→ 仿真器稳定后编组改造 → 短训冒烟 → 全量训练。

- 可行性（2026-09-02 确认）：`TrainConsist.vehicles` 按序 + `locomotive_indices` + `LocomotiveParams` → 多机车原生支持；ED/AB 已分离 + `ab_sources` 多源。改动面集中于 `train_env.py` 编组 + 动作空间，不涉积分核心。

- 代价/风险：动作空间维度上升（每机车独立电/空决策）→ 样本复杂度上升、训练更久；需论证"多机车+电空分离"协同相比"单机+单控"的**增量收益**才能立住（预期：错峰缓解降车钩力）。

- 暂缓原因：`train_env.py`/`train.py`/`coupler.py`/`tractive.py` 为他人改仿真的未提交（M）状态，不冲突不改造。

- 相关：`docs/RESEARCH_POSITIONING.md`（1.3.1 立论）；`docs/PROJECT_PIPELINE.md`（立项）；`docs/logs/diagnostics/`

## ADR-009.1 阶段方案修订：空电分工（B）先行、多机车（A）后叠 - 2026-09-03

- 状态：决策（修订 ADR-009 实施路径，聚焦"空气制动难优化如何解决"）

- 背景：①导师提醒"空气制动很难优化"；②用户确认先解决"空气制动难优化"技术问题，搁置论文措辞；③emergence 实验证伪"标准 RL 学精细错峰时序"（共享策略收敛对称解）；④A×B 全自由度融合训练风险高。

- 结论：**C（融合）降级为最终目标；本阶段先做 B（空电分工），且先单列 1 机车（不绑多机车）；A（多机车=智能体）后叠**。理由：解决"空气制动难优化"不需要多机车，单列即可更快验证；多机车是"多智能体锚定"的独立目标，可解耦后置。

- **空电分工技术方案（4 层）**：

  1. **规则化档位**：AB 档位由规则循环制动触发（超上限→SERVICE、低于下限→缓解、紧急→EMERGENCY），不进连续优化（第 1 层已做）。
  2. **ED 优先 + AB 兜底**：ED 连续（即时、无波速、功率+粘着约束）承担主制动；AB 仅当 ED 不足（需求减速度 > ED 上限）或失效时按规则档位补位——把难优化的 AB 使用量压到最小。
  3. **AB 状态作观测**：暴露 `train.py` 的 `_air_brake_releasing`（缓解剩余）、`_brake_segment`（段序号）、充风状态进 obs，让策略"感知"AB 动态而非"预测"它。
  4. **RL 只学宏观分配**：RL 学"当前用多少 ED / 是否触发 AB / 协同偏移"，不学 AB 连续档位（若未来要学，用离散动作空间匹配 AB 离散性）。

- 验证前提：验证"多次循环制动下空电分工有效性"需要足够循环制动次数 → **评估时域须升级为完整 23.8km**（当前 3000 步只覆盖 \~5km，见 WP2）。

- 门控：环境冒烟 → 短训验证"ED 优先、不足转 AB"分配可学 → 通过才全量训练；失败止损并记录（DIAGNOSTICS）。

- 相关：`docs/logs/diagnostics/DIAGNOSTICS_2026-09.md`（emergence 证伪 / MPC 缩放）；`.trae/documents/plan_2026-09-03_空气制动难优化解决-空电分工.md`

## ADR-010 主轴回调：多列 platoon + 车钩力为底线，ED/AB 分工与 1+1 降级为增强；MPC 对比采用 Regime A/B - 2026-09-05

- 状态：决策

- 背景：消融（`mask_lever`）证明单列 1+1 下"ED 够用、多源 AB 低冲动"→ 单杠杆可刷标量分，AB+ED 分工"意义不大"（ED 杠杆=车钩力安全、AB 杠杆=吞吐；AB-only 在标量 reward 反超双杠杆）。若把 1+1 电空分工当论文主线，消融会尴尬、立论不成立。

- 选项与权衡：

  - A. 继续以"单列 1+1 电空分工"为主线，强化吞吐/冲量奖励（②）：改动小，但抽象向上游仍是"分工必要性"被消融拷问。

  - B. **回调主轴（选用）**：以**多列 platoon + 队内车钩力≤1000kN + 安全列距**为不可逾越底线；ED/AB 分工、1+1 为**锦上添花/增强**，不当论文主线。MARL 的卖点 = 多列下"不协同则失步/追尾、车钩力越限"，协同 + 车钩异构鲁棒是真正价值。对比 MPC 采用 Regime A/B（见下）。

- 结论：选 B。核心立论放在**多列 + 车钩力 + 列距**交汇处；ED/AB 分工保留为真物理杠杆（增强），不再单独立论。

- **MPC 对比 Regime A/B（配套规范）**：MPC 预测模型是通用物理、坡度只是输入馈给，**不按坡道换 MPC 模型**。分两 regime——A（每线重喂正确 `grade_at`，公平标定，用于 main/E1 滚动窗/E3 模型精度）；B（不重辨识、专演"不泛化"，**必须声明 no-re-identification**，只用于 E4 跨线/E4-H 车钩异构）。论文 Protocol 逐实验标 A/B，否则视为对比失公允。

- **异构性泛化（E4-H）**：每个车钩/每列车物理参数不同（实例异构 ≠ 数学离散）；当前 `train.py` 用单套共用 `CouplerParams`（齐次），须改逐车钩/逐列车独立参数 + 分布抽样 + held-out 评估（`--hetero`，默认齐次零回归）作为泛化卖点；对位 MPC 锁单套参数 → 偏差下越限。

- 后果：

  - 论文/实验以多列 platoon（3×1+1=6 智能体）为主线，21/35km 剖面 + 车钩异构演变 E1–E4-H 实验矩阵（详见计划：`.trae/documents/plan_2026-09-05_多列platoon重构与MPC对比异质泛化.md`）。

  - ED/AB 分工 + `mask_lever` 消融结论保留为"增强层证据"，不承担主线叙事。

- 相关：`docs/research/RESEARCH_POSITIONING.md`（SSOT：主轴与底线 / MPC Regime A/B / 车钩异构）；ADR-009 / 009.1（机制决策，地位降级为增强）；根 `AGENTS.md`「规范性问题」

## ADR-011 车钩缓冲器统一回 MT-2（移除机车 QKX100 弹性胶泥分区）- 2026-09-07

- 状态：决策（已完成实施）

- 背景：R0 建模（2026-09-06）为机车引入 QKX100 弹性胶泥缓冲器分区（月牙形两段刚度 + 胶泥幂律阻尼 C|v|^n + F_d + f），与货车 MT-2 摩擦式并置。但：① 成熟论文主流是"分车型归一对"（同一编组常用单一缓冲器类型，如 MT-2 + 个体差异），机车叠 QKX100 属简化研究域里少见的双类型并置；② QKX100 的 C/n/F_d/f/k1/k2 为形状标定值（文献未给正文拟合常数），引入 5 个无独立敏感性扫描的标定参数，审稿人会质疑边界与诚实性；③ 车钩异构（E4-H）卖点本就走"逐车钩物理参数抽样"，统一回 MT-2 后仍保留个体差异空间。

- 选项与权衡：

  - A. **统一回 MT-2（选用）**：全列（含机车-货车连挂钩）均用 MT-2 摩擦式（Stribeck 750/500 kN、v_er=0.2、2270 kN 饱和），彻底移除 QKX100。贴合成熟论文范式、消除 5 个无解析值标定参数、降低可投性风险；代价是放弃对机车胶泥缓冲器特性的显式刻画（对 1 万吨单机牵引编组的车钩力主轴影响有限）。
  - B. 保留双类型并置：保留更多物理细节，但引入难以诚实标定的参数、偏离主流范式，被审稿拷问风险高。

- 结论：选 A，统一回 MT-2。这是对 R0（2026-09-06）车钩地基改进的**收口简化**：保留 R0 的 Stribeck 摩擦、卸载刚度复核（MT-2=1.0）、循环段间衰减、两段式缓解排气等有效物理，仅移除机车胶泥分区。

- 后果：

  - 代码层：`params.py`（移除 buffer_type/k2_nm/knee_x_m/viscous_c/viscous_n_exp/static_damp_n 与 qkx100_params）、`coupler.py`、`train.py`（齐次默认全列 MT-2，含机车-货车连挂钩）已同步清理；训练/绘图 metadata physics 串更新。
  - 测试层：删除 QKX100 相关测试，派发断言改为"全列统一 MT-2（2270 kN）"。
  - 文档层：`VALIDATION_BASELINE.md` 对 R0 之 C（QKX100）小节打 superseded 标注；本 ADR 为该决策的出处。
  - 历史产物：R0 后（2026-09-06）产出的含 QKX100 分区的结果（若存在）须附建模版本声明，不得与统一后直接混比。

- 相关：R0 建模（`docs/VALIDATION_BASELINE.md`「地基级建模体检 R0」）；ADR-010（车钩异构泛化 E4-H，个体差异空间保留）

## ADR-012 主轴收敛为「列车编队 + 两层融合 MARL（T-MARL）」；单列车 decompose 降级为列内层机制 - 2026-09-08

- 状态：决策（已立项实施）

- 背景：规划文档一度把**单列车 decompose 换架构**当成主线，与项目主轴（**列车编队 + 多智能体强化学习**）冲突（用户明确纠正：主战场是重载列车群组协同控制，t-marl 两层融合才是正题，我完全没提过单列车作为主轴）。同时历史代号（M1/M2/M3）含义歧义（M2=车钩力擦除已被移除并并入安全层消融），必须换成语义代号，统一全项目口径。

- 主轴定义（T-MARL，两层融合）：
  - **编队层（列车级）**：多列 MARL 协同，每列万吨级列车=智能体，保持安全列距 → 生成宏观驾驶曲线。编队层**已历史跑通**（2026-08 协同增量 +110042、10 seed 稳定），但属 R0 旧物理、checkpoint 空 → **真实缺口 = MT-2 统一物理重跑/重评**（不是"从未跑通"）。
  - **列内层（机车级）**：列内多机车分布式动力，每机车=智能体，ED（连续）/AB（离散档位）分工（详见 ADR-009/009.1 机制）。
  - **单列车 1+0 独立分解 = 方向性偏差**，从主战场移除，降级为"列内层机制"的实验记录，不承担论文主线证据链。

- 语义代号统一（SSOT，全项目文档/沟通用）：
  - **D-RL**：分布式动力 + MAPPO 决策；**D-Rule**：分布式动力 + 规则控制；**S-Loco**：单机车规则基线（纯规则 0 训练，仅 MT-2 重评，作架构增量锚点 M0 vs single=+74%）。
  - **M-MARL**（编队协同，旧 M1）、**No-C**（无协同，旧 M3）、车钩力擦除消融（旧 M2，已并入安全层消融）、**ED-only/AB-only**（杠杆隔离消融）、**1+0 MAPPO**（mt2_l1，非主证据链，不引用）。
  - **M1/M2/M3 数字代号全部废止**，文档/实验/沟通一律语义代号。

- 选项与权衡：A. 维持单列车 decompose 主线（能快速产出单列结果，但与"群组协同"研究定位相悖、无法回应导师"多智能体名不符实"批评）；B. **回调两层融合主轴（选用）**（对齐 AGENTS.md / RESEARCH_POSITIONING 既有定位，编队层历史资产可复用，单列车仅留机制证据）。

- 结论：选 B。两大可复现落地（本文档为出处）：
  1. **文档对齐**：`RESEARCH_POSITIONING.md` 加主轴共识 banner、`ITSC_PAPER.md` 加定位偏差声明（单列车降级）、`PROJECT_PIPELINE.md` 加代号图例（M1/M3/M2 → M-MARL/No-C/车钩力擦除消融，历史章节按图例读、不批量改写）、`DECISIONS.md` 本 ADR 立项。
  2. **结果可复现**：`src/metadata.py` 新增 `simulator_model` 型号串（NeTrainSim-multibody|coupler=MT-2|braking=ED+AB-relief-wave + simcase/编组/坡度/cyclic_degrade）；`train_runner/train_fleet/train_cyclic_braking` 经 `extra` 落超参；`evaluate_decompose/evaluate_l1_long/evaluate_l1_rule_baseline` 评估结果 JSON 内嵌 metadata（git_commit/physics_version/simulator_model/全物理配置/seed/checkpoint），按时间戳归档不覆盖旧文件。凡是产出论文数据的脚本都必须走该机制，实验数值以 metadata.json 为准。

- 后果：① 训练/评估脚本统一仿真实型号 + 超参可复现（已完成并 smoke 验证，见 ADR-011 后 metadata 机制）；② 后续新增实验线一律语义代号 + 走 `metadata`；③ 编队层 MT-2 重跑为当前真实执行起点（空 checkpoint 补齐）。

- 相关：ADR-010（主轴回调多列 platoon + 车钩力底线）；ADR-009/009.1（列内层分布式动力 × 电空分工机制）；`docs/RESEARCH_POSITIONING.md` / `docs/ITSC_PAPER.md` / `docs/PROJECT_PIPELINE.md`；根 `AGENTS.md`「阶段二研究定位 / 规范性问题」

> **修订（2026-09-08，ADR-013）**：ADR-012 将主线表述为"编队层 RL + 列内层 RL **两层叠加**（T-MARL）"——该"两套 RL 层叠加"框架被 ADR-013 废止/修订（编队=唯一目的、单套 formation-aware RL=唯一手段）。本 ADR 其余内容（语义代号统一 SSOT、metadata 可复现机制）延续有效。

## ADR-013 主线回归「编队=最终目的，MARL=手段」；仅保留单套 formation-aware RL（机车级 ED/AB），废止"两层 RL 叠加" - 2026-09-08

- 状态：决策（立项实施）

- 背景：ADR-012 把主线表述为"两层融合 MARL（T-MARL）= 编队层 RL（列车级）+ 列内层 RL（机车级）叠加"，导致**两套 RL 长期并存**（`platoon_mappo` 编队层阈值 RL + `decompose_loco_ed_ab` 机车级 ED/AB RL），规范与代码互相矛盾：
  - 主线表述（曾见于 `RESEARCH_POSITIONING` §1.3）把两个 RL 层当"要叠加融合"的目标 → **主动制造**两套并存；
  - 同时 `decompose_loco_ed_ab.yaml` 为 `num_trains:1` 单列车、无编队上下文，文档却已判其为"方向性偏差"（脱离编队语境）→ 代码与文档不同步。
  用户明确纠偏：**论文主线是"编队"（多列重载列车群组协同控制），多智能体只是实现编队的手段**；长期把"多智能体"当目的、或同时保留两套 RL，是方向性错误。

- 选项与权衡：
  - A. 保留"编队层 RL + 列内层 RL 两层叠加"：两个 RL 权威点抢同一批牵引/制动执行器 → 信用分配模糊、编队失稳（已观测列间串级震荡），且论文讲不清"智能体到底是谁"。
  - B. **编队=唯一目的，单套 formation-aware RL=唯一手段（选用）**：目的 = 多列编队在长大下坡保持安全列距 + 速度带一致 + 车钩力 ≤1000kN；手段 = 机车级 ED/AB 分工（每机车=agent，ED 连续 / AB 离散档位），但 RL 以**编队为上下文**（每机车 obs 含前列间距误差/相对速度/前方坡度/群组车钩力，reward 以编队目标为主）—— 编队目标由这一套 RL 承载，不再设第二套"编队层阈值 RL"层。

- 结论：选 B。具体落地（本 ADR 为出处）：
  1. **废止**"编队层（列车级）RL + 列内层（机车级）RL 叠加"表述；编队层阈值 RL（`hierarchical`，每列车输出 `coor_adj`）下线废弃。
  2. **一套 RL**：formation-aware 机车级 ED/AB decompose（`num_trains≥3` 编队上下文 × 每列机车=agent）。
  3. **现存单列车 R0 decompose**（`decompose_loco_ed_ab.yaml`, num_trains=1）＝偏差产物，仅作"列内分工机制"实验记录保留、不承主线、不得当主结果；config 标 deprecated。
  4. 终止后台 `platoon_mappo`（编队层阈值 RL）训练并清理残留（已执行）。

- 后果：
  - 文档统一：`RESEARCH_POSITIONING.md` 主线段落去"两层叠加"表述+banner 对齐"编队=目的、MARL=手段"；统一"层级"命名反转为一套；`ITSC_PAPER.md` / `PROJECT_PIPELINE.md` 同步措辞；根 `AGENTS.md` 同步单 RL 落位。
  - 代码：`decompose_loco_ed_ab.yaml` 标 deprecated；后续只训 formation-aware 变体（并入编队上下文）。
  - 旧叙事（编队层阈值 RL、两套 RL 叠加、"编队协同增量 +110042 由编队层 RL 承载"）不再作为当前主线证据引用；编队协同结果改由 formation-aware 机车级 RL 承载后重跑（MT-2 物理）。

- 相关：ADR-012（T-MARL，本 ADR 修订其"两层"框架、保留其列内机制与语义代号/可复现机制）；ADR-010（多列 platoon + 车钩力 + 列距 = 底线，与本 ADR 一致）；ADR-009/009.1（列内层分布式动力 × 电空分工机制）；`docs/RESEARCH_POSITIONING.md` §1.3 / `docs/ITSC_PAPER.md` / `docs/PROJECT_PIPELINE.md`；根 `AGENTS.md`

## ADR-014 立论定调：免重辨识 claim + 车钩力=约束 + 动作结构 Q 固化 - 2026-09-09

- 状态：决策
- 背景：论文立论需一个"扛部署"的可量刑差异化 claim。导师口径"把车钩力保持在 1000kN 以内"经辨析 = "约束"而非"优化目标"；claim 不应与 MPC 比"控制品质"（MPC 在保真车钩+长大下坡已证明能把车钩力压到 330kN，宋宗莹 2026，正面拼品质基本会输），而应比"谁扛得住部署"（免调参迁移 vs 每线重标定+在线求解）。
- 选项与权衡：
  - 选项 A 车钩力=优化目标（reward）：→ 必须与 MPC 在车钩力品质上正面竞争，面对有 330kN 实证的 MPC 基本会输，claim 动摇。
  - 选项 B 车钩力=安全约束+观测上下文：→ 不与 MPC 拼品质、拼"免重辨识部署"，claim 站得住。**【选此】**
  - 泛化方向：主训练已切 53km 真实朔黄；跨线目标应为**域外真实剖面（20/35km）**而非 23.8（23.8 是已拟合过的合成锚、"见过"了，无跨线泛化证明力）。
- 结论：
  - **claim**：同一环境/安全层/53km 下，免重辨识 D-RL 跨线守住底线（车钩力≤1000kN、不越 ATP、列距不破界），对公平 MPC=需重标定/失配/耦合区求解失败。不与 MPC 比控制品质，只比扛部署。
  - **车钩力 = 硬安全层 + 观测上下文，不进 reward**（约束语言，原则性定稿）。
  - **动作结构 Q 固化**：`get_action_decomposed` 规则循环制动 + 逐机车 RL 调制 `[ed_mod,ab_mod]`。claim 落"协同调制"层；规则层管单车安全制动、RL 管多车编队协同。
  - **主指标**：跨线免调参级联失败率 / MPC 求解失败次数 / **ATP 触发次数**（替代"追尾"——安全层已杜绝物理追尾）。补遗：车钩力/列距/速度带/求解耗时。
  - **放弃 SAC/QMIX/DQN-fair 主表**（claim 不依赖 RL 算法选择，仅 Related Work 一句）；ED/AB 隔离、No-ETCS、No-C 不进正文（接续 ADR-013 删除项）。
- 后果：立论口径写入 `RESEARCH_POSITIONING.md` §1.6（**覆盖式修订** ADR-010 已过时"23→35km"假设）；运行时规范待落到 `EXECUTION_RULES.md`；`ITSC_PAPER.md` 手感及主表待对齐。
- 相关：ADR-013（formation-aware 机车级 ED/AB=唯一 RL 手段）；ADR-010（多列 platoon+车钩力+列距=底线）；§1.6；宋宗莹 2026（MPC 330kN 靶点）

## ADR-015 编队目标改"相对列距锚定"以解除 53km 物理性发散 - 2026-09-10

- 状态：决策（实施中）
- 背景：53km 主训练（`shuozhou_real_53km`，3×1+1，curriculum→36000 步）在历史奖励（逐列锚**绝对**速度带 v_center=20m/s + 全局 `rel_vel_penalty`=std(全列速度)）下发散。发散短训 35ep 完整复现：ep1-16 正常（R≈4-6k，车钩力≤900kN，viol=0），**ep17 起持续崩塌**至 -5万~-33万、车钩力 1400-1760kN、violation 100-1824。根因（`trace_53km_rule` 规则裸跑亦发散）是**物理性**的：初始列距 ≈1.34km（列车长1.14km+动态间距200m）使各列同时位于 53km 不同相对坡段 → 各自平衡速度不同 → **绝对速度带一致性物理不可达**（位置差→坡度差→速度差→间距扩大正反馈）。
- 选项与权衡（`AskUserQuestion`，用户选 1）：
  - 选项 1 **改编队目标为相对列距锚定**【选此】：领航列(ti==0)仍锚绝对带（编队节奏），跟随列(ti>0)镜像前列可行轨迹（相对速度 + 相对列距 gap）。删全局绝对同速惩罚。物理可收敛（同坡序相位差，非绝对同速）。
  - 选项 2 接受发散为诚实负结果（重构"安全层+规则层扛部署"叙事，RL 只做短期调节）。
  - 选项 3 先做收敛性研究再定训练域。
- 结论：
  - `train_fleet_env.py::_calculate_reward_decomposed`：`speed_band_reward` 仅作用于领航列；跟随列新增 `rel_anchor_reward`（相对前列速度镜像，尺度 3m/s、权重 2.0）；删除全局 `rel_vel_penalty`(std 全列速度)。新增常量 `REL_ANCHOR_SPD_SCALE/W`。控制侧（leader 迁就尾列 / follower 级联追前列）不动。
  - **初步诊断（发散短训 40ep，方向1，2026-09-10）**：ep17 单次短暂 -41216（viol=0，车钩力 807kN）后 **ep18-20 立即恢复 +5200~6300**、车钩力维持 ≤1031kN、viol 仅两天单点——与旧奖励"ep17 起持续崩塌"形成对照，**方向1 解除终端发散**。ep21-40 长时程最终确认见 `DIAGNOSTICS_2026-09.md`。
- 后果：若长时程确认收敛，则任务3「主训练 D-RL 53km 全量 5 seed」按新奖励推进；主对比/跨线/消融复用本 env（reward 口径一致）。
- 相关：ADR-014（claim/动作结构 Q/车钩力=约束）；预研日志见 `docs/logs/diagnostics/DIAGNOSTICS_2026-09.md`
- **2026-09-10 长时程复核（supersede 上"初步诊断 positive"之短-中时程乐观面）**：40ep 诊断至 ep30 数据证实——相对锚定只修好短-中时程（≤1000 步，ep17→18-20 恢复 +5~6.3k），**长时程（2000-3000 步，ep21-30）仍发散**：coupler 1200-1735kN、viol 数百、reward ±。方向1 单独不构成 53km 全程收敛；车钩力底线保障的"更硬手段"（09-09 已留待用户决策）成为下一步必选项。明细见 `DIAGNOSTICS_2026-09.md`「诊断-2026-09-10-发散根因」。
- **2026-09-10 方向2（车钩力惩罚强化）验证失败 + 回滚（supersede 09-09"更硬手段"的 reward 化实现）**：30ep 短训（`diag_53km_coupler_pen`，奖励改本步全列真实峰值 + 破线二次硬惩罚 `-80·ov²` + `0.9×limit` 早触发）实测 ep0-15 稳定（车钩力 522-917kN）但 **ep16 起间歇性溃败**（1505-1699kN、viol 482、reward -88787）。且该杠杆本身**违反 SSOT**：车钩力定位 = 硬安全层 enforce≤1000kN + 观测上下文，**不进 reward、不作最小化对象**（RESEARCH_POSITIONING §1.3）。`-80·ov²` 量纲（|−80| >> 带内收益 ~6）直接放大 value 目标震荡、KL 频繁早停。**已回滚**：`train_fleet_env.py` 恢复车钩力为观测塑形（用本步全列真实峰值 `_step_coupler_peak_n`），移除二次硬惩罚，破线回归由底层 enforce_coupler 硬安全层兜底。
  - **最终诊断结论（2026-09-10）**：破线根因 = **训练不稳定 / 间歇性策略坍塌**（best ckpt 在 ep12 车钩力 804kN 安全，后续更新把策略学崩），而非策略固有发散（规则基线 53km 裸跑仅 793kN）。下一步**不再在 reward 层打补丁**，转**修训练稳定性**（校验 lr/entropy/KL 早停是否适配新奖励量纲），重跑 30ep 短训验证 ep21-30 收敛后才谈 5-seed 主训练。

## ADR-016 MPC 对比只保留 Regime A（逐线公平标定），废止 Regime B（不重辨识）- 2026-09-16

- 状态：决策（覆盖式修订 ADR-010/ADR-014 的 Regime B 相关部分）
- 背景：原规范（ADR-010 §mpc、ADR-014）设 Regime B「MPC 不重辨识 → 专演不泛化、失配」，作为跨线立论补充。辨析后暴露非对称硬伤：**D-RL 携带 53km 训练所得策略跨线（仅不微调），而 Regime B 的 MPC 却不携带 53km 源域标定（`grade_at=None` → 回退前5车平均坡度）**——一个保源域学习成果、一个连源域图纸都删，对象不对称，审稿一句"不公平/strawman"即危险。且"MPC 不标定即失配→须重标定"属重载列车换线必做符规标定的领域常识，**无需本论文重复证明**，占用篇幅却无增量信息。
- 选项与权衡（用户定夺，选 1）：
  - 选项 1 **只留 Regime A，删 B**【选此】：MPC 每条测试线重喂该线 `grade_at` + 在线标定 b0（每线公平标定）；D-RL 策略严格零微调跨线。立论改押"**免重辨识成本**"：以零重标定代价的 MARL，达到 MPC 逐线专门重标定后的同档性能（实测 MARL 泛化 ≈ 重标定 MPC）。
  - 选项 2 保留 A+B：需为 B 的公平性辩护并承担篇幅与 strawman 争议，与"篇幅少、claim 干净"目标相悖。
- 结论：
  - **对比协议只保留 Regime A**：MPC 每线注入正确 `grade_at`（剖面图纸）+ 在线 b0 标定；**不做 no-re-identification、不演失配**。
  - **D-RL 严格零微调跨线**，文中公开声明"MARL no fine-tuning on target line"。
  - **claim 从"扛部署（MPC 失配 vs 免调参）"reframe 为"免重辨识成本"**：MARL 以零重标定代价 ≈ MPC 需逐线重标定后才有的性能。
  - **不证明、不依赖**"MPC 不标定会失配"——此结论不写入论证（领域常识，不占篇幅）。
  - **主指标随 reframe 调整**：对齐"成本"口径——MARL 跨线零微调（声明）、MPC 每线重标定（量化标定代价：`solve_times`/辨识所需步数或数据）；ATP 触发/车钩力/列距落地率作底线达成证据，非"谁控得准"。
  - **Protocol 逐实验标 A**（无 B，故不再需要 A/B 双标）。
- **标定成本量化（2026-09-16 补，SSOT 口径见 RESEARCH_POSITIONING §1.6「标定成本量化口径」）**：口径 1 先验注入量清单表（主证，必做）+ 口径 2 标定预算曲线（视觉证据，篇幅允许再加）+ 口径 3 `solve_times` 求解代价（现成数据，顺手补）；口径 4 b0 改 RLS/KF 辨识收敛时间不做。量化对象 = **先验注入量**（`grade_at` 图纸），非计算耗时（b0 在线差分免费）。
- **车钩异构（E4-H）明确退出立论（2026-09-16 补）**：ADR-016 收窄 claim 后与主 claim（免重辨识成本）无关；`--hetero` 仅代码可选鲁棒性、默认齐次零回归，不作泛化卖点、不进正文主表。SSOT 处 `RESEARCH_POSITIONING.md` §1.5 E4-H 节已标 SUPERSEDED、AGENTS.md 同步。
- 后果：`RESEARCH_POSITIONING.md` §1.5「MPC 对比 Regime A/B」改写为只留 A；§1.6 立论与跨线方向（L184 B 模式）按 reframe 覆盖修订；`AGENTS.md`「规范性问题」同步删除 B 表述；跨线评测入口须显式控制 `grade_at` 注入（避免 `compute_actions_from_env` 的 `grade_profile` 自动重建把 B 悄悄变 A 或偷到目标域）。
- 相关：ADR-010（Regime A/B 原判据，本 ADR 覆盖其 B）、ADR-014（claim/动作结构 Q/车钩力=约束，本 ADR 覆盖其"失配求解失败"依赖）、RESEARCH_POSITIONING §1.5/§1.6

## ADR-017 训练时域与评估时域解耦；训练量达标为硬要求 - 2026-09-16

- 状态：决策
- 背景：既有计划/配置写"主训练 36000 步 / 53km 多段 1200 步评估拼接覆盖"，自相矛盾且误导。经 7 篇同领域论文原始文献交叉验证，正反给出统一口径。
- 概念澄清（SSOT 级）：
  - **三条独立维度**：①单条 rollout 时域（on-policy 经验窗口）；②评估时域（覆盖剖面）；③总训练量（episodes/steps 预算）。不可混为一谈。
  - **on-policy（MAPPO/PPO，本项目）**：更新须用"当前策略刚采的 rollout"，窗口越长数据新鲜度/自举误差越差 → 单条只能短窗口。实证：Guo2025 LSTM-MAPPO horizon 1024/512、Zhang2021 ~1200；本项目 `curriculum` 上限 1200 步达标。
  - **off-policy（DQN 等）**：体验回放不要求新鲜轨迹 → 单条可全长（Zhang2024 单集 15 步跑完 23.8km，Δt=100s，总训 10 万 episodes；Δt 大只是刻意压步数，非必需）。
  - **成熟范式（on-policy）**：训练=短窗口，评估=独立完整剖面单独跑（Guo2025 用 combined trip 训练 1024 窗口、NEDC 完整剖面评估 ~3900 步）。`dt` 小不是障碍（Guo2025 dt=0.1 照样完整剖面评估）。
  - **训练量现状不足**：本项目 ~120 episodes/seed，同类 on-policy 论文 Guo2025 用 1400 episodes、Hua2024 用 6×10⁵ 总步。**补足=保窗口、增 episodes**，非拉长窗口。
- 结论：
  1. **训练时域 = 短窗口**（curriculum ≤1200），绝不设 36k 全程（重引入 on-policy 长时程自举误差滚雪球不收敛）。
  2. **评估时域 = 独立完整剖面**（35km 等目标剖面单独跑全程），**不做"多段 1200 步拼接覆盖"**。
  3. **跨线方向正确**：长且复杂剖面（53km）训练 → 未见过剖面（35km）验证；验证剖面须满足"未在训练见过 + 落训练状态分布内"。短/简单训练 → 复杂验证（反向）错误，因 OOD 失守。
  4. **总训练量达标为硬要求**：收敛 ≠ 训练充分。120 episodes 不足，目标对齐同类 on-policy 论文量级。
- 后果：`PROJECT_PIPELINE.md` ADR-014 阶段1 加 superseded 注明时域修正；配置文件 L44 注释待同步；`RESEARCH_POSITIONING.md` 若含"全程/拼接"表述依此覆盖修订；`AGENTS.md` 规范性问题区补本条指针。
- 相关：ADR-013（formation-aware RL=唯一手段）、ADR-014（claim/动作结构 Q）、ADR-016（免重辨识成本、跨线 Regime A）；文献实证见 `docs/papers/`（Zhang2024/Guo2025/Zhang2021/Hua2024）

