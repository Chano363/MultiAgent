***

title: 重大决策记录（ADR）
date: 2026-09-01
status: active
owner: Owner
------------

# 重大决策记录（Architecture Decision Records）

> **为什么**：固定"为什么这么做、考虑过哪些选项、选谁、代价是什么"，防 AI/人几个月后无法还原决策上下文。
> append-only：废弃决策标 `superseded` 加新条目，**不篡改已写入旧决策**。

## ADR 模板

```
## ADR-编号 决策标题 - 日期
- 状态：决策 / 实施 / 修订 / superseded
- 背景（动机、约束）/ 选项与权衡 / 结论（选 X，理由）/ 后果（验证结果、新约束）/ 相关（PIPELINE / 诊断 / LEARNINGS 链接）
- **SSOT 联动（必查）**：若本决策改变立论口径 → 落 ADR 当次同步核对/覆盖 `docs/RESEARCH_POSITIONING.md` 对应节（先例：ADR-022 覆盖 §1.6 基线表述），并在「相关」写明；改完在本文件核对清单打钩即视为联动完成
```

## 已补录的历史决策（ADR-002 \~ ADR-007）

> 2026-09-01 从各诊断/验证章节提炼补录 ADR-002~007（限速区间\[40,80] / 加速度动作空间 / 分层架构重构 / 方案A回退+废弃APF / 公平DQN / 简化MPC双策略）；其余较细决策仍散落在 `VALIDATION_BASELINE.md` / `DIAGNOSTICS.md` / `VERIFICATION_LOGS.md` 各小节（留痕来源）。

***

## ADR-008 引入 ARIS 跨模型审阅通道（Auto-claude-code-research-in-sleep）- 2026-09-02

- 状态：实施
- 背景：论文重构期需**独立第二模型**对抗性审单模型自审盲区偏袒；scholar-search MCP 仅能检索、不能裁决型评审。
- 选项与权衡：
  - A. 复制 ARIS skills 进项目 `.trae/skills/`：污染项目、升级难同步
  - B. `@` 引用 ARIS 仓库（不复制），MCP 配 `llm-chat` 接 OpenAI 兼容端点（TRAE 无 codex MCP；Minimal 依赖仅 httpx，`D:\Anaconda\python.exe`），reviewer=OpenRouter `minimax/minimax-m3:free`（与 executor deepseek 跨族）→ 选用
- 结论：选 B。跨族对抗评审（`family_relation=different`）对 [ITSC_PAPER.md](traffic_rl_project/docs/ITSC_PAPER.md) 独立戳中 3 条硬伤（title-内层失配 / fair-MPC strawman / 证据薄）。
- 后果：
  - 集成遇 TRAE 密钥遮罩坑（`sk-...` env 被替换成 `\u2026`），已用 `LLM_CRED_FILE`<本地 key 文件路径>绕开（[server.py L52-72](Auto-claude-code-research-in-sleep/mcp-servers/llm-chat/server.py#L52-L72)）
  - 评审结论反哺论文：标题改 "Hierarchical Hybrid MARL"、补 "MPC+规则内层" 公平基线、20km/5 列结果补全指标升独立小节
  - 新依赖约束：OpenRouter 公端点 `independence_verified=unverified`；更严格独立需私有部署 ump/challenge 端点
- 相关：`docs/logs/diagnostics/DIAGNOSTICS_2026-09.md`（诊断-2026-09-02-ARIS 试点）；`docs/docs/logs/progress/PROGRESS_2026-09.md` ARIS 条目；ARIS 仓库 `docs/TRAE_ARIS_RUNBOOK_CN.md`

## 条目区

## ADR-001 文档规范化治理（Docs-as-Code） - 2026-09-01

- 状态：实施
- 背景：`VALIDATION_BASELINE.md` 膨胀至 177KB（验证基准+诊断+踩坑混装）；根目录残留临时脚本；文档无规范模板、无统一导航；阶段一/ITSC 衍生版职责不清。
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
- 背景：用户质疑限速区间不能仅凭 1-2 篇论文取；需核对研究对象/研究问题/行业标准。
- 选项与权衡：
  - \[45,65]（樊运新3万吨参数）：吨位与对象（1万吨朔黄线）不一致，物理不可行（已验证车钩力超限540次/掉速）
  - \[40,80]（Zhang2024 + 行业规则 + 《重载铁路设计规范》）：上限80=朔黄线实际线路限速；下限40=2万吨最小缓解速度
- 结论：改 \[40,80]。依据：线路/行业标准与研究对象一致 + 物理验证（第1层成功，车钩力150kN/速度71km/h）。
- 后果：`train_fleet_env.py` v_max 65→80、v_min 45→40；82 测试过。
- 相关：`docs/logs/verification/VERIFICATION_LOGS_V5.md`（V5.24）

## ADR-003 动作空间：目标速度 → 目标加速度 - 2026-08-15

- 状态：实施（后被 ADR-004 分层架构取代第1层策略，但"控加速度能学"原则保留）
- 背景：列间 RL 用"目标速度"动作，但长大下坡物理极限(16.7m/s)低于目标(20m/s)→动作饱和、Reward 无区分度→策略不学习（KL早停=0、best 不更新）。
- 选项与权衡：
  - 目标速度：动作被物理锁死，RL 学无可学（诊断：动作+1/+0 60步奖励与末速完全相同）
  - 目标加速度：直接影响物理，有真实学习区分度（对齐 Zhang2021/Hua2024）
- 结论：改用目标加速度 `a∈[-max_accel,max_accel]`（方案B）。Reward 单调改善40%（-885→-546），列间 MARL 首次真正学习协同制动。
- 代价：加速度更激进致 peakCoupler 偶尔超 1000kN（viol~1）。
- 相关：`docs/logs/verification/VERIFICATION_LOGS_V5.md`（V5.10）

## ADR-004 最终架构：放弃"RL 学单列循环制动"→ 分层（第1层规则 + 第2层 RL 阈值协同）- 2026-08-22

- 状态：实施（论文核心结构）
- 背景：RL 学单列循环制动结构性失败（缓解波长时延6s→PPO信用分配失效 + 车钩力多体耦合→探索即爆炸）。论文/行业标准均用规则循环制动。
- 选项与权衡：
  - RL 学单列循环制动：失败（时长/信用分配+碰撞）
  - 分层：第1层规则循环制动（领域最优 523kN）+ 第2层 RL 只做阈值协同（v_max_adj/v_min_adj ±5km/h，不动 throttle）
- 结论：分层重构（`HierarchicalController`）。协同增量 M1(+33494) vs M3(-76548) = **+110042**；M1 追尾0/车钩力864kN/间距182m 全健康，M3 追尾392。
- 后果：成为论文核心创新点；83 测试过。
- 相关：`docs/logs/diagnostics/DIAGNOSTICS_2026-08.md`（诊断-2026-08-22 最终战略分层重构）

## ADR-005 方案A 人为坡段错开 → 回退；废弃 APF 势场控制器 - 2026-08-20

- 状态：已回退
- 背景：方案A（`start_offset_m` 中段起步 + `spacing_m` 静态坡段错开）制造人为相位差，偏离"各列同坡段起步、随间距自然产生动态相位差"方针；前列/后列缓解不同步→车钩力持续超限(1218-1226kN)+M1 不收敛。
- 选项与权衡：
  - 引入 Zhang2021/Guo2025 APF 势场控制器：生搬硬套（对方=地铁平直/单质点/忽略车钩力/无坡度，可自由±加速；长大下坡向下可制动、向上无牵引）
  - 移除人为错开，恢复普通场景（各列同坡段起步）
- 结论：废弃 APF，回退移除 `start_offset_m`/`spacing_m`。正确分层 = 列间 RL 宏观协同 + 列内规则循环制动 + 车钩力安全层。35 测试过，无回归。
- 相关：`docs/logs/diagnostics/DIAGNOSTICS_2026-08.md`（诊断-2026-08-20 E25 方案A / 回退方案A）

## ADR-006 引入公平 DQN baseline（M-DQN-fair）消解审稿质疑 - 2026-08-23

- 状态：实施
- 背景：主结果用朴素 M-DQN（Zhang2024 式：学单列循环制动、无安全层、无协同）对标，审稿人可质疑"DQN 输是因为没协同/没安全层而非 DQN 不如 MAPPO"。
- 选项与权衡：
  - 保持朴素 DQN：公平性不足，结论易被击穿
  - 补同架构公平 DQN：第1层规则循环制动 + 车钩力安全层（与 M1/M3/M4 完全相同），第2层换每列独立 DQN 输出离散 coor_adj（同 obs/reward，完全同架构）
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
- 背景：导师批评"3 列 1+0 群组叫多智能体不合适"——1+0 每列仅 1 台动力源，"列车当智能体"本质是 3 条曲线宏观优化，'多智能体' 名不符实（宋宗莹2026 同风险）。需重构智能体分解，锚定在**物理独立动力源**上。
- 选项与权衡：
  - A. 1+0→1+1/多机车分布式动力：多台物理动力源牵引/电制动/缓解错峰分配=真多智能体（Tang2020/姚小沛2013/赵紫宁2022/樊运新2024）。优点：物理锚定扎实；代价：改编组+多机车协同训练。
  - B. 电制动/空气制动分离为双智能体：同一列内 ED(连续)/AB(离散) 分工决策（Yu2022，电空联合制动，Actuators 11(6)145）。优点：列内即多智能体、不依赖多车；风险：需论证为何不单策略多输出头。
  - C. A×B 融合（选用）：多机车作"体"、每机车同时决策电/空制动→列内真多智能体分工，与既有分层兼容。最扎实；代价最大，需彻底重构编组+环境+训练。
  - D. 先不做仅立论：工作量最小，但无法回应导师批评、无法产出新结果。
- 结论：选 C（融合）。渐进式：立论（本文档+RESEARCH_POSITIONING 1.3.1）→ 仿真器稳定后编组改造 → 短训冒烟 → 全量训练。
- 可行性（2026-09-02 确认）：`TrainConsist.vehicles` 按序 + `locomotive_indices` + `LocomotiveParams` → 多机车原生支持；ED/AB 已分离 + `ab_sources` 多源。改动面集中于 `train_env.py` 编组 + 动作空间，不涉积分核心。
- 代价/风险：动作空间维度上升（每机车独立电/空决策）→ 样本复杂度上升、训练更久；需论证"多机车+电空分离"相比"单机+单控"的**增量收益**才能立住（预期：错峰缓解降车钩力）。
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
- 验证前提：验证"多次循环制动下空电分工有效性"需足够循环制动次数 → **评估时域须升级为完整 23.8km**（当前 3000 步只覆盖 ~5km，见 WP2）。
- 门控：环境冒烟 → 短训验证"ED 优先、不足转 AB"分配可学 → 通过才全量训练；失败止损并记录（DIAGNOSTICS）。
- 相关：`docs/logs/diagnostics/DIAGNOSTICS_2026-09.md`（emergence 证伪 / MPC 缩放）；`.trae/documents/plan_2026-09-03_空气制动难优化解决-空电分工.md`

## ADR-010 主轴回调：多列 platoon + 车钩力为底线，ED/AB 分工与 1+1 降级为增强；MPC 对比采用 Regime A/B - 2026-09-05

- 状态：决策
- 背景：消融（`mask_lever`）证明单列 1+1 下"ED 够用、多源 AB 低冲动"→ 单杠杆可刷标量分，AB+ED 分工"意义不大"（ED 杠杆=车钩力安全、AB 杠杆=吞吐；AB-only 在标量 reward 反超双杠杆）。若把 1+1 电空分工当论文主线，消融会尴尬、立论不成立。
- 选项与权衡：
  - A. 继续以"单列 1+1 电空分工"为主线，强化吞吐/冲量奖励（②）：改动小，但抽象向上游仍是"分工必要性"被消融拷问。
  - B. **回调主轴（选用）**：以**多列 platoon + 队内车钩力≤1000kN + 安全列距**为不可逾越底线；ED/AB 分工、1+1 为**锦上添花/增强**，不当论文主线。MARL 的卖点 = 多列下"不协同则失步/追尾、车钩力越限"，协同 + 车钩异构鲁棒是真正价值。对比 MPC 采用 Regime A/B（见下）。
- 结论：选 B。核心立论放在**多列 + 车钩力 + 列距**交汇处；ED/AB 分工保留为真物理杠杆（增强），不再单独立论。
- **MPC 对比 Regime A/B（配套规范）**【整体 SUPERSEDED 2026-10-16，ADR-037：Regime A 协议废止，当前口径见 ADR-037；以下原文仅作历史】：MPC 预测模型是通用物理、坡度只是输入馈给，**不按坡道换 MPC 模型**。分两 regime——A（每线重喂正确 `grade_at`，公平标定，用于 main/E1 滚动窗/E3 模型精度）；B（不重辨识、专演"不泛化"，**必须声明 no-re-identification**，只用于 E4 跨线/E4-H 车钩异构）。论文 Protocol 逐实验标 A/B，否则视为对比失公允。
- **异构性泛化（E4-H）**：每个车钩/每列车物理参数不同（实例异构 ≠ 数学离散）；当前 `train.py` 用单套共用 `CouplerParams`（齐次），须改逐车钩/逐列车独立参数 + 分布抽样 + held-out 评估（`--hetero`，默认齐次零回归）作为泛化卖点；对位 MPC 锁单套参数 → 偏差下越限。
- 后果：
  - 论文/实验以多列 platoon（3×1+1=6 智能体）为主线，21/35km 剖面 + 车钩异构演变 E1–E4-H 实验矩阵（详见计划：`.trae/documents/plan_2026-09-05_多列platoon重构与MPC对比异质泛化.md`）。
  - ED/AB 分工 + `mask_lever` 消融结论保留为"增强层证据"，不承担主线叙事。
- 相关：`docs/research/RESEARCH_POSITIONING.md`（SSOT：主轴与底线 / MPC Regime A/B / 车钩异构）；ADR-009 / 009.1（机制决策，地位降级为增强）；根 `AGENTS.md`「规范性问题」

## ADR-011 车钩缓冲器统一回 MT-2（移除机车 QKX100 弹性胶泥分区）- 2026-09-07

- 状态：决策（已完成实施）
- 背景：R0 建模（2026-09-06）为机车引入 QKX100 弹性胶泥缓冲器分区（月牙形两段刚度 + 胶泥幂律阻尼 C|v|^n + F_d + f），与货车 MT-2 摩擦式并置。问题：① 成熟论文主流是"分车型归一对"（同一编组常用单一缓冲器类型，如 MT-2 + 个体差异），机车叠 QKX100 属简化研究域里少见的双类型并置；② QKX100 的 C/n/F_d/f/k1/k2 为形状标定值（文献未给正文拟合常数），5 个无独立敏感性扫描的标定参数会被审稿人质疑边界与诚实性；③ 车钩异构（E4-H）卖点本就走"逐车钩物理参数抽样"，统一回 MT-2 后仍保留个体差异空间。
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
- 背景：ADR-012 把主线表述为"两层融合 MARL（T-MARL）= 编队层 RL（列车级）+ 列内层 RL（机车级）叠加"，导致**两套 RL 长期并存**（`platoon_mappo` 编队层阈值 RL + `decompose_loco_ed_ab` 机车级 ED/AB RL），规范与代码互相矛盾：主线表述把两个 RL 层当"要叠加融合"的目标（**主动制造**两套并存）；同时 `decompose_loco_ed_ab.yaml` 为 `num_trains:1` 单列车、无编队上下文，文档却已判其为"方向性偏差"→ 代码与文档不同步。用户明确纠偏：**论文主线是"编队"（多列重载列车群组协同控制），多智能体只是实现编队的手段**；长期把"多智能体"当目的、或同时保留两套 RL，是方向性错误。
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
> **【SUPERSEDED 2026-10-16，ADR-037】**：本 ADR 的 Regime A 协议（逐线重喂 `grade_at` + 在线标定 b0）**已整体废止**，"免重辨识成本" claim 已由 ADR-032 废止。当前对比口径见 ADR-037。以下原文仅作历史。

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
- 后果：`docs/docs/logs/progress/PROGRESS_2026-09.md` ADR-014 阶段1 加 superseded 注明时域修正；`RESEARCH_POSITIONING.md` 若含"全程/拼接"表述依此覆盖修订；`AGENTS.md` 规范性问题区补本条指针。
- **执行闭环（2026-10-01）**：主训练配置 `configs/experiments/formation_ed_ab_3train_1plus1.yaml` 曾**未达本条硬要求**（`episodes: 120`、缺 `n_env`/`warm_start`/`long_eval_*`、注释仍留"多段 1200 步拼接覆盖"旧表述；`env_cfg.max_steps: 36000` 注释误标"53km 全程训练"）。已按本条对齐并验证：`episodes: 1400`（§4）+ `n_env: 4` / `parallel_traj_len: 0`（§1）+ `warm_start: true`（BC 热启动）+ `long_eval_interval: 50` / `long_eval_steps: 36000`（§2 完整剖面独立评估）+ `max_steps` 注释更正为"env 截断上限 / 评估口径（训练时域由 curriculum 决定，`TrainRunner` 每集覆盖）"。验证方式 = `--episodes 2` 覆盖短训（exit 0），`metadata.json` 实测上述字段全部生效（criterion：CLI 覆盖生效 ⇒ YAML 值可被正确解析）。**快速迭代用 `--episodes N` 覆盖，勿改 YAML 主值**。详见 `docs/logs/progress/PROGRESS_2026-10.md` 四改造「本轮补齐的完整性缺口」⑧、`REPRODUCIBILITY.md` §十。
- 相关：ADR-013（formation-aware RL=唯一手段）、ADR-014（claim/动作结构 Q）、ADR-016（免重辨识成本、跨线 Regime A）；文献实证见 `docs/papers/`（Zhang2024/Guo2025/Zhang2021/Hua2024）

## ADR-018 车钩力口径统一（断面力）+ 安全层对 AB 的"减"权限（治本落地） - 2026-09-30

- **状态**：决策（已落地 + 已回归验证）
- **⚠️ 修订（2026-10-01）**：**第 3 条（AB 新增源闸门）的"效力"表述被 [ADR-020](#adr-020-修订-adr-018-第-3-条效力表述ab-新增源闸门在确定性驱动策略上是-no-op并否决削减已发-ab-源方向---2026-10-01) 修订**——X1 判别性实验证明该闸门在**确定性驱动策略**上是 **no-op**（生产 ckpt on/off 轨迹逐位相同），只在**采样探索态**下部分有效且仍破 1000 kN。第 1 条（断面力口径统一）不受影响，仍为生效基准。原文保留不删。
- **背景**：`诊断-2026-09-30-100ep破线根因` 定位两个**代码级根因**——① 训练/评估/违规计数/安全门控读"**每车净力**"（`_coupler_forces()`），与项目实测基准"**单钩断面力**"（`coupler_interface_forces()`）混用 → 少报约 7.8×，且在拉压交界处叠加/抵消造成误判；② 安全层对 AB **无物理权限**：逐机车 `ab_sources` 在安全层之前组装、绕过安全层，安全层钳制仅下调 `ed_throttle`，两个 AB 闸门反应式且读净力，叠加 AB 波 ~5s 传播滞后 ⇒"≤1000kN 硬兜底"名不副实（实证：AB 首现 t=0 → 首破 t=901，滞后 90.1s）。
- **决策**：
  1. **指标口径唯一化**：车钩力"**门控 / 违规计数 / 评估指标**"一律用 `coupler_interface_forces()`（单钩断面力，SSOT）；新增 `coupler_interface_forces_per_vehicle()`（长度 n 的每车断面力视图）供安全层 / 门控按车索引取值。
  2. **obs 与 reward 刻意保留每车净力口径**（代码内显式注释说明）——避免作废既有 checkpoint（5-seed 主训练 + `ab_gate100`），使 1200 步回归可在**既有权重**上复测。净力口径此后仅用于"内部积分 + obs + reward 塑形"。
  3. **安全层新增对 AB 的"减"权限**：`SafetyLayer.ab_new_source_veto()` —— 反应式（当前每车断面力峰值 ≥ `0.6·limit`）+ 预测式（按"列长 / 波速 / dt"外推 `horizon` 步峰值 ≥ `0.9·limit`）⇒ **禁止本步新增 AB 源**；只禁新增、**不撤销**已建立的制动源（避免制造缓解冲击）。
  4. **消除死代码**：`MultiLocoController._safety`（从未被调用）删除；车钩力源头门控改为直接咨询 `train_env.safety`。
- **验证**（`诊断-2026-09-30-治本改造回归验证`，同一 1200 步窗口 / seed2000）：四场景**全部 0 步破线**（full 1238.4→**783.4 kN**、no_traction 1242.3→**955.2 kN**、no_rl 767.7 不变、no_ab 870.1→769.0）；**闸门开/关隔离对照**确认闸门贡献（17/35→0 步）与口径统一的行为贡献（124→17 步）；速度控制未受损（<40 km/h 比例 42.8%→3.4%）。
- **后果 / 待办**：① 抑制 AB 不均匀缓解（列尾拉力来源，逐机车错峰缓解）；② **1400ep 全量 5-seed 重训** + 完整剖面评估（接受探索瞬态）。**现有 5-seed / `ab_gate100` 产物未作废**（obs/reward 未改），但其"违规计数"若由旧代码产生需按断面力口径**重算**。全部改造**尚未 git 提交**。
- **相关**：`docs/logs/diagnostics/DIAGNOSTICS_2026-09B.md`（诊断-2026-09-30 两节）；`docs/logs/learnings/LEARNINGS.md` LRN-20260930-001/002/003；ADR-013（formation-aware 机车级 ED/AB = 唯一 RL 手段）、ADR-014（车钩力 = 约束，不进 reward）。

## ADR-019 统一训练框架续训（resume）改造：总目标集数语义 + 完整状态恢复 - 2026-09-30

- **状态**：实施（已落地 + 单测 + 端到端冒烟验证）
- **背景**：统一训练框架 `run_training.py` → `TrainRunner` 的旧 `--resume` 是"半成品"，三个硬伤：
  1. **静默从头重训**：`if resume_pt and Path(resume_pt).exists()` —— 路径写错/文件不存在直接跳过加载，**不报错、直接白跑数小时**。现实复现：`docs/docs/logs/progress/PROGRESS_2026-09.md` 记载 5-seed 长训"原 launch resume 源已 MISS"（`final_seed{0..4}` 停在 ep 992/992/521/661/671）。
  2. **集数语义混乱**：`--episodes` = "再跑 N 集"，须人工算剩余（诊断记录曾致 seed2 超跑到 ep70）。
  3. **进度/历史/最优态不恢复**：`TrainingLogger._init_csv` 与 `save_training_artifacts` **全量覆写** CSV/JSON/学习曲线 PNG ⇒ 曲线只剩续训段；`best` 只从**新** `results_dir` 的 history 读 ⇒ 换目录即丢。
- **选项与权衡**：
  - 集数语义：A. 保持"再跑 N 集"+ 人工 `--override start_ep`（易错，已致超跑） / **B. `--episodes` 按「总目标集数」解释（选用）** → 与"训到 1400ep"的表述一致，零心算。
  - 恢复范围：C. 一律只加载权重（丢优化器动量，跨物理才需要）/ **D. 默认恢复完整训练状态 + `--resume-weights-only` 显式退出（选用）** → 满足"同物理续训"与"旧物理 → ADR-018 新物理迁移"两种需求。
- **结论**：选 **B + D**，改动全部落在统一框架内（legacy `train_fleet.py` / `train_cyclic_braking.py` 不在范围）。
  1. 新增 `src/trainer/resume.py`：`resolve_checkpoint`（**路径不存在抛 `FileNotFoundError`**，禁止静默从头；支持具体文件 / `latest|last` / 目录取最新 `_ep{N}`）、`plan_run_episodes`（总目标语义；目标 ≤ 已训 → 抛错并提示用 `start_ep` 校正）、`read_progress`（`done_ep` 优先级 `start_ep` > `metadata.done_ep` > 源 history 行数 > 文件名 `_ep{N}`）、`load_source_history`（拼接源目录既有曲线）。
  2. **进度内嵌 checkpoint**：`_ckpt_meta_now(done_ep, best_reward)` 把 `done_ep` / `best_reward` / `long_eval_best` / `resume_from` 动态写进**每个** `.pt` ⇒ 权重单文件即可续训、可溯源（对标 YOLO `best.pt`）。
  3. **RNG 随 checkpoint 存取**（`np` / `py` / `torch`）⇒ 完整续训在确定性 env 下可复现。
  4. `--resume-weights-only`：剥离 `optimizer_state_dict` / `value_norm_*` / `reward_rms_*` / RNG（`BaseRLAgent._WEIGHTS_ONLY_STRIP`），适配 `final_seed` 旧物理 → ADR-018 新物理迁移。
  5. `TrainingLogger` 续训**不截断**既有 CSV、tqdm `initial=已训集数`；`episode_rewards/peak_coupler/violations` 以源 history 为初值 append ⇒ 学习曲线连续。
  6. list-agent（`coor_dqn`）续训**直接报错**（该产线已下线，避免隐性错配）。
- **验证**：
  - **单测** `tests/test_resume.py`（14 项）：路径不存在抛错 / `latest` 选取（best 不参与）/ 总集数语义 / 进度优先级 / 历史拼接 / `weights_only` 重置优化器与 value_norm / RNG 往返（含 CUDA 回归）。
  - **全量回归** `pytest tests/ -q` → **192 passed**（原 172 基线 + 20 新增，0 回归）。
  - **端到端冒烟**（小窗口 60 步，`/tmp/rs2`、`/tmp/rs3`）：1 ep → `--resume --episodes 3` 输出"**已训 1 ep，目标总 3 ep，本轮跑 2 ep**"、CSV **3 行连续**（ep1/2/3）、`best` 继承（+400.5 未重置）；`--resume latest` 三信号一致（`metadata.done_ep=3` / history 3 行 / 文件名 `ep3`）；路径不存在 → `FileNotFoundError`（不再静默重训）；`--resume-weights-only` 正常。
  - **冒烟中修掉的两处真实缺陷**（详见 LEARNINGS）：① `device=cuda` 下 `torch.get_rng_state()` 经 `map_location=cuda` 变成 GPU ByteTensor → `set_rng_state` 抛 `TypeError`（补 `.cpu()`）；② logger 的 `ckpt_meta` lambda 用**自增前**的 `global_ep` → `last.pt` 内嵌 `done_ep` 比文件名少 1（改 `global_ep + 1`）。
- **后果 / 待办**：① legacy 训练入口不享受本改造（如需须另行迁移）；② "续训 `final_seed{0..4}` best 到 1400ep" 现可安全执行（建议新输出目录 `final_seed{N}_v2` 防覆盖）；③ 本次改动**尚未 git 提交**。
- **相关**：`docs/docs/logs/progress/PROGRESS_2026-09.md` P3「训练框架续训改造 - 2026-09-30」；`docs/logs/diagnostics/DIAGNOSTICS_2026-09B.md`「诊断-2026-09-30-续训框架端到端验证」；`docs/logs/learnings/LEARNINGS.md` LRN-20260930-004/005/006。

## ADR-020 修订 ADR-018 第 3 条效力表述：AB 新增源闸门在确定性驱动策略上是 no-op；并否决"削减已发 AB 源"方向 - 2026-10-01

- **状态**：决策（已实验裁决；**不改代码**，只修订效力表述 + 方向取舍 + 验收规程）
- **背景**：ADR-018 第 3 条引入 AB 新增源闸门（`AB_ADD_SOURCE_MAX_RATIO=0.6` + `AB_MAX_CONCURRENT_ADD=1` + `SafetyLayer.ab_new_source_veto`），其"验证"来自 **100ep 短训玩具 ckpt** 的末段峰值改善（980.9 kN / viol≈0）——**未做 on/off 隔离对照**，**未在生产权重上验证**。补做判别性实验 X1/X4（`docs/logs/diagnostics/DIAGNOSTICS_2026-09B.md`「诊断-2026-09-30-X1/X4 判别性实验」）。
- **证据**（1200 步窗口 / `shuozhou_real_53km` 起始段 / 断面力口径 / `seed=2000` / DI=10）：
  1. **闸门在生产 ckpt 上是 no-op**：`final_seed0_v2/last_ep1043` 闸门 on/off 同为 **761.0 kN / 0 破线**；`final_seed1_v2/last_ep1043` 同为 **627.1 kN / 0 破线**（轨迹逐位相同）；玩具 ckpt 确定性 639.5 (on) / 628.1 (off)。
  2. **仅采样探索态有效且不足**：玩具 ckpt 1165.6 (on) vs 1268.9 (off)——−103 kN / −7 破线步，**但仍破 1000 kN**。
  3. **机制确证（在飞波锁）**：把"新增 AB 源"锁死 → 1268.9 → **777.1 kN / 0 破线**，与闸门开关无关；代价 = 1199/1200 步全锁、**AB 杠杆失效**（≈规则基线 768.1）⇒ 只证明病根，不是解。
  4. **反事实否定（削减已发 AB 源）**：1268.9 → **1323.5 kN / 103 破线步**（撤销 334 次）⇒ "缓解—再制动"循环恶化冲击。
- **决策**：
  1. **修订 ADR-018 第 3 条的效力表述**：该闸门的**有效域 = "RL 新增 AB 源"通道 ∩ 策略实际使用的动作子集**；规则基线循环制动触发的 AB 源**不经过闸门**。**禁止**再把闸门写作"已在生产策略上验证有效 / 已守住 ≤1000 kN"。**代码保留**（对"会用 AB 杠杆的策略"仍有防护价值，且是 `ab_gate100` 复现条件），但降级为**可选防护**，**不再承担 ≤1000 kN 的保证**。
  2. **否决"削减已发 AB 源"方向**（实验反证恶化），不进入任何设计或论文。
  3. **"在飞波锁"仅作机制确证工具**，不作解决方案（废掉 AB 杠杆与 ADR-013 的"机车级 ED/AB 分工"冲突）。
  4. **安全/兜底机制验收新规程（强制）**：①必须给出 **on/off 隔离对照**（量化机制自身贡献，而非"开了之后变好"）；②必须**在目标分布（确定性驱动策略）上**给结论，**探索态效果不得当作部署保证**；③必须声明机制的**有效域**（它约束哪些动作、策略是否真走这些动作）。
  5. **≤1000 kN 的当前保证来源**：断面力口径统一（ADR-018 第 1 条，仍生效）+ 底层规则层自身；若需更强保证，候选新机制 = ①约束 AB 源**时空分布**（按列车位置错峰 / 单位长度源密度上限）②"新增源"改为 **RL 与规则共同决定的有界配额** ③在断面力口径下对 **AB 相关动作做投影**（ED 已有投影，AB 无）——需另立实验裁决。
- **后果 / 待办**：① 论文"安全"叙事的落点从"闸门"回到"**口径统一 + 底层规则确定性执行**"；② **全剖面（53km）D-RL vs D-Rule 头对头评估在当前物理/口径下尚不存在**（历史对比位于 `outputs/deprecated/`，属旧物理 → 不可引用）⇒ 列为下一步第一优先；③ git 提交待确认。
- **⚠️ 更正（2026-10-01，同日后补）**：上面第 ② 条**表述过强**。事后全仓复查：**(a)** 现存 D-RL **@53km** 的评估**并非只存在于 `deprecated/`**——`outputs/results/decompose/` 下有多份 `decompose_m1_*_53km`（`ep841`(5 seed) / `ep1623` / `ep1521` / `best_s0` / `best_s1` / `ep2265`），均 `physics_version=29569dcaf78a`；**(b)** 结论方向与"缺证据"相反——**`last` 权重守得住红线且不输规则层**：`ep841` 824.6 kN / band 97.1% / 末速 61.2 km/h / reward +221k；`ep1623` 863.5 / 99.7% / 72.0；`ep1521` 928.7 / 99.4% / 64.1（规则层 `827.5 / 98.4% / 50.5 / −145k`）；**破线的都是"选错权重/训练不足"**：`best`（训练窗口 reward 选优）1682.5 / 1250.9、`ep120` 1162.1、`ep2265`(seed0 退化 ED 蠕行 `ab_steps=0`) 1248.0。**(c) 仍真正缺失的**只有：现行 **断面力口径 + 修好的 viol 计数**下重算的两行（M0 规则 / M1 `last`），以及 **`--mask_lever ab`（收走 RL 的 AB 新增源通道）的对照**。修正确认本条核心决策（闸门不作保证）**不变**，但"缺头对头证据"的说法作废，且不得再把 53km 破线归因于架构。
- **相关**：ADR-018（被修订原文，已在原位标修订指向本条）、ADR-013（RL 定策 + 底层确定性执行）、ADR-014（车钩力=约束，不进 reward）、ADR-016（免重辨识成本 claim）；`LEARNINGS.md` LRN-20260930-009（采样态不可复现）/ LRN-20260930-010（闸门 no-op）。

## ADR-021 「MARL 破线」根因归因后的改造方向与优先级（车钩力进目标 / AB 时间约束 / 信用分配修复） - 2026-10-01

- **状态**：方向决策 → **2026-10-01 执行更新：代码已落地（A/D/C/B 四处，见本节末「执行闭环」）；机制 on/off 已按 ADR-020 规程验证；P0 三行与 AB 通道裁定见「执行闭环」**
- **背景**：判定"当前 MARL 不行"（长剖面破 1000 kN、不敌规则层）。`诊断-2026-10-01-「MARL 不行」根因归因`（`docs/logs/diagnostics/DIAGNOSTICS_2026-10.md`）以**代码锚 + 既有资产**归因出断点，并**否证**"AB 用量↔峰值单调相关"；同文件「调研-2026-10-01」确认各断点均有成熟文献解法。
- **证据**（摘要，全文见诊断条目）：
  1. **奖励**：车钩力 shaping 上限 **−0.4** vs 速度带 **+6/列**（`train_fleet_env.py:739/766`），且 `−80·ov²` 超限跳变已回滚（`:757-760`）⇒ 破线 / 不破线在目标里几乎不可区分；`needy 无 AB → −0.5`（`:822-824`）反向倒逼用 AB。
  2. **AB 通路**：`ab_sources` 在安全层之前组装（`train_env.py:474-491`），安全层只回写 `ed_throttle`（`:522-524`）⇒ AB 无 ≤1000 kN 兜底。
  3. **闸门**：有效域仅"RL 新增 AB 源"，且在确定性驱动策略上 **no-op**（X1；ADR-020）。
  4. **信用分配**：标量 advantage 广播（`mappo_agent.py:464-465`）+ 视界 **17 s**（γλ=0.9405）≪ 物理滞后 **90 s**。
  5. **否证**：`s0_ep1623` `ab_steps=10753` → 863.5 kN / band 99.7%（安全）；`best_s1` `ab_steps=6591` → 1250.9 kN（破线）⇒ 决定破线的是**新增源时空分布**，不是用量。
- **候选方向与权衡**：
  - **方向 A｜AB 最小充风时间进动作空间**（Zhang2024）：在 `MultiLocoController` / 规则层令两源间隔 ≥ 最小充风时间。**成本最低、不动 RL 结构**，直接抑制"缓解—再制动"循环。风险：可能与"下坡须及时加闸"冲突，验收须确认不牺牲 band。
  - **方向 B｜per-agent advantage 修复信用分配**（COMA / PRD-MAPPO）：把 `:464-465` 的广播标量改为 per-agent，并把视界拉到 ≥ 滞后窗口（n-step / λ）。直击断点 5；风险=改动算法核心 → 需重训。
  - **方向 C｜车钩力进目标（受控的非线性超限项）**：恢复"超限"非线性但**控量纲**（避免 2026-09-10 的 value 震荡 / KL 早停），或按 Tang2020/Wang2025 多目标加权。**限"超限项"，不作"均值最小化"**。
  - **方向 D｜安全层升级为预测式 safety filter 并接管 AB**（Wabersich & Zeilinger 2021）：给 AB 真"减"权限 + 预测式（覆盖 ≈90 s 滞后）+ 新增源时空配额。最根本；但文献警示 filter 与策略解耦会振荡（Pfrommer 2022），与 X4-b 同源 ⇒ 必须处理一致性。
- **决策**：
  1. **优先级排序（先零成本、后架构改动）**：
     - **P0（先做，零架构改动、不涉重训）**：① 在现行**断面力口径 + 修好的 viol 计数**下重算 53km 的 M0（规则）/ M1（`last`）两行；② 做 **`--mask_lever ab`**（收走 RL 的 AB 新增源通道）对照 → 判定"AB 通道对最终性能是净正还是净负"。
     - **P1**：方向 A（AB 最小充风时间，成本最低）。
     - **P2**：方向 B（信用分配修复）。
     - **P3**：方向 C / D **二选一**（车钩力进目标 vs 预测式 safety filter），由 P0/P1 结果裁决。
  2. **修订 ADR-014「车钩力不进 reward」的绝对表述**：允许**"超限"非线性项**进目标（量纲受控），前提是**不作均值最小化**、且安全叙事**不归功于 MARL**（ADR-014 / `RESEARCH_POSITIONING.md` §1.6 立论边界不变）。
  3. **AB 通路的安全权限缺口必须补**（方向 D 的核心，独立于是否采用完整 filter）：安全层对 AB 须与 ED **对称**地具备"投影 / 减"权限——这是 ADR-018"≤1000 kN 硬兜底"名实相符的前提。
  4. **禁止**把"在飞波全锁"当解决方案（ADR-020）；**禁止**"撤销已发 AB 源"（X4-b 反证恶化）。
  5. **验收沿用 ADR-020 第 4 条规程**：任何新安全机制必须 **on/off 隔离对照** + **在确定性驱动策略上**给结论 + **声明有效域**。
- **后果 / 待办**：① P0 两件事列为**下一步第一优先**（不涉重训，且是"是否值得重训"的判据）；② 任一方向落地后须按 ADR-017 补 **1400ep × 5 seed** 重训 + 完整剖面评估；③ 立论侧 `RESEARCH_POSITIONING.md` §1.6「车钩力定位」已加"待修订（ADR-021）"标记；④ 教训记入 `LEARNINGS.md` LRN-20261001-002。
- **相关**：ADR-014（被修订的"不进 reward"绝对表述）、ADR-018 / ADR-020（AB 权限与闸门）、ADR-017（训练量）；`docs/logs/diagnostics/DIAGNOSTICS_2026-10.md`（根因 + 文献调研）。

### ADR-021 执行闭环（2026-10-01）—— 四改造落地 + P0 裁定

- **规格**：`.trae/specs/implement-literature-informed-fixes/`（已获批执行）。**留痕 SSOT** = `docs/logs/diagnostics/DIAGNOSTICS_2026-10.md`「改造-2026-10-01-文献四改造落地」+「诊断-2026-10-01-P0 三行基线与 AB 通道裁定」两节。
- **① 四方向落地（代码）**：

  | 方向 | 落点 | 关键参数 |
  | :--- | :--- | :--- |
  | **A** AB 最小充风时间 | `src/controllers/multi_loco_controller.py::_ab_gate`（逐机车源时序状态机） | `ab_min_refill_s=222.0`（有实测出处）；`ab_min_hold_s=0.0`（**待核实**，默认不激活） |
  | **D** 安全层禁新增 AB 源 | `src/environments/train_env.py::_step_decomposed`（`protect()` 之后）+ `train_fleet_env.py` 跨列聚合计数 | 复用 `SafetyLayer.ab_new_source_veto`（反应式 `≥0.6·limit` / 预测式 `≥0.9·limit`） |
  | **C** 车钩力受控超限项 | `src/environments/train_fleet_env.py`（`REWARD_SCHEMA='v2-bounded-overlimit-section-force'`；峰值口径改**断面力**） | `−6.0·min(peak_norm−1, 2.0)`，上界 **−12.0** |
  | **B** per-agent advantage + 信用视界 | `src/algorithms/mappo_agent.py`（`critic` 枚举 / N 维价值头 / per-agent GAE / 去广播）；`src/trainer/registry.py`；`src/metadata.py`；`src/evaluation/evaluate_decompose.py::probe_critic_mode` | 主 YAML `critic: per_agent`、`γ=0.999`、`λ=0.99` ⇒ 视界 **91.0 s ≥ 90 s** 物理滞后 |

- **② P0 完成（ADR-021 决策 1 的 P0，零架构改动、不涉重训）**：53km / 36000 步 / 确定性 / 同 ckpt `last_ep1623` / 同 seed，**现行断面力口径**（`physics_version=1eab36352fd3`）：

  | 行 | 断面力峰值 | 破线（车厢·步） | AB 源·步 | band 率 | 末速 |
  | :--- | ---: | ---: | ---: | ---: | ---: |
  | M0 规则基线 | 812.87 kN | 0 | 3212 | 98.01% | 46.27 km/h |
  | M1 RL 全通道 | 1643.49 kN | 77 | 7656 | 91.58% | 73.67 km/h |
  | M1 RL **仅 ED**（`--mask_lever ab`） | **1037.50 kN** | 44 | **1105** | 95.85% | 56.89 km/h |

- **③ AB 通道裁定（旧权重）= 净负**：收走 RL 的 AB 新增源通道后峰值 **−606 kN（−36.9%）**、破线 **−33**、band **+4.27 pt**、AB 用量 **−85.6%**，reward **−345340 → −160384**。
  - **判定**：在**旧权重**上，RL 新增的那 ≈6551 步 AB（7656−1105）就是把峰值从 1038 抬到 1643 kN 的部分 ⇒ **"RL 用 AB 换性能"在当前目标/算法下不成立**。
  - **⚠️ 不据此改架构（刻意不做的事）**：**不**把 AB 从 RL 动作空间收走、**不**改 ADR-013 的"机车级 ED/AB 分工"结构。理由：本裁定测的是**旧目标**（"多用 AB 得速度带奖励"）训出的策略；C + B 改了目标与信用分配后，"RL 能否**有用地**用 AB"并未被否定。**在重训前砍掉一个动作维度，等于永久失去再验证的机会**。
  - **重训后的复核义务**：按 C+B 重训后**必须重做同一 `--mask_lever ab` 对照**，再裁定 AB 通道去留（保留为可消融项 / 收走 / 或转为"有界配额"）。这是本裁定的**条件性结论**，不是终局。
  - **不受影响的部分**：D（安全层对 AB 的禁新增权限）与 A（充风门）**继续保留**——它们是安全/物理约束，不依赖 RL 是否用 AB。
  - **另一条硬结果**：M1-maskab **仍破线**（1037.50 kN / 44 步）⇒ **单靠收通道不足以守住 ≤1000 kN**，必须叠加 C + B 后重训。
- **④ D 的"梯度投影臂"经证明不可达，已删除（纯重构、零行为变化）**：`scale<0.5`（⇔ ratio>0.9）恒被 `ab_new_source_veto`（阈值 0.6，且 `p0 ≡ ratio·limit`、恒 ≥0）抢先 ⇒ 该臂、计数键 `ab_safety_downgraded`、以及**靠猴补关掉 veto 才通过**的那条误导性单测一并移除；新增源码级断言防回流。**含义**：veto 阈值停在 0.6 时 AB 无法表达渐变投影，真·梯度 AB 权限须连同阈值一并重定 → 归入**完整预测式 safety filter**。
- **⑤ 验收（ADR-020 第 4 条规程，全部在确定性驱动策略上）**：A on/off 12000 步（AB 用量 −42.3%、峰值 926.95→914.37 kN、band 不变、0 破线）；D on/off 12000 步（env 侧真丢弃 35/12000 步、峰值逐位相同 ⇒ **D = 安全保证而非性能杠杆**）；C 解析核对（0/0/−3.0/−12.0/−12.0 与 `−6·min(pn−1,2)` 一致）；B 端到端冒烟（`critic=per_agent` / `reward_schema=v2-bounded-overlimit-section-force` 落 metadata、视界打印 91.0 s 覆盖 90 s）。
  - **A 的完整有效域（全剖面对照得出，修正表述）**：`_ab_gate` 装在**控制器**里、**对"新增 AB 源"一视同仁**（不分规则层 / RL 层）。证据：**纯规则轨迹**（M0，RL 全程 0）改动前 vs 改动后**逐位相同**（−288742 / 812.87 kN / 0 破线 / AB 3212 / band 98.01%）⇒ A 不触发，因为**规则层自己的循环制动排程本就满足 222 s 充风窗**（印证 `VALIDATION_BASELINE.md:201` 张二田 S6）；而**RL 从 ED 通道扰动轨迹后**（M1-maskab）A 就连带拦到"被扰动后的规则层 AB 排程"（AB 步 1441→1105，−23.3%），全通道更达 −52.9%。
    ⇒ 准确表述：**A 的有效域 = "在 222 s 充风窗内请求新增 AB 源"这一动作，与来源无关；纯规则轨迹恰好不触发，轨迹被 RL 扰动后必然触发**。**禁止**再写作"A 只管 RL 通道 / 规则层不受影响"。论文叙事 = "把**充风纪律**变成硬约束，使 RL 无法为短期速度收益破坏它"。
  - ⚠️ **A 在全剖面上的净效应是"混合"，不是纯改善（必须与 C+B 一起用）**：三个配置一致显示 —— A **总是压低 AB 用量**（M1 −52.9% / 仅 ED −23.3% / M0 0），但**在 RL 参与的两个配置里都使峰值升高、band 变差**（M1：1350 → 1643.49 kN，+21.7%；band 99.62% → 91.58%，−8.04 pt。仅 ED：1023 → 1037.50 kN；band 97.07% → 95.85%）。破线步数则符号不一致（M1 905 → 77 大降；仅 ED 21 → 44 反升）。物理解读：旧权重靠 AB 保速度带，A 掐掉 RL 的 AB 新增源后策略"想用却用不了"⇒ 控速变差并在个别时刻出现更高峰值。⇒ **A 的价值必须叠加 C（车钩力进目标）+ B（信用分配修复）重训后才可能兑现**。**窗口口径警示**：12000 步 A on/off 表的"峰值略降"**只在首 1200 s 成立**，全剖面上符号反转（LRN-20261001-008）。
  - **未分离残余**：上述全剖面对照是"A(+D)"而非"A 单独"（冻结副本不含 D 的 env 侧否决；D 在 12000 步与 M0 行上均表现为 no-op，全剖面贡献未单独量化）。
- **⑥ 强制边界**：**C 改 reward 口径 + B 改训练算法 ⇒ 全部旧 ckpt 失效**，任何最终性能结论**必须**按 ADR-017 跑 **1400 ep × 5 seed** 重训 + 独立完整剖面评估后才成立。本节 P0 三行仅作**方向性判据**。
- **⑦ 遗留 / 长久计划**（见 `docs/logs/progress/PROGRESS_2026-10.md`）：① 按 C+B 重训（1400 ep × 5 seed）并出主表 —— **🟡 seed0 已于 2026-10-01 启动**（`scripts/launchers/launch_retrain_adr021_seed0.sh` ⇒ `outputs/checkpoints/formation/adr021_1400ep_seed0/`，登记见 `REPRODUCIBILITY.md` §十 / `docs/logs/progress/PROGRESS_2026-10.md` 长久计划 1）；② `ab_min_hold_s` 与 `ab_min_refill_s=222 s` 的实车核实 —— **`ab_min_hold_s` 已文献结案（2026-10-01，负结果：无运行期最小保持时长出处 ⇒ 保持 0.0 不激活；见 `DIAGNOSTICS_2026-10.md`「检索-2026-10-01」+ `REFERENCE_INDEX.md` 落地映射）；`ab_min_refill_s=222 s` 已由两独立来源同量级佐证（张二田 S6 实测 222 s + 大秦线报道 ≈210 s），仅余"实车数据正式核实"一项**需线下获取实车记录，非本环境可完成**；③ 完整预测式 safety filter（含 veto 阈值与梯度 AB 权限、来源感知、filter/策略一致性，Pfrommer 2022）；④ **立论侧已同步**：`RESEARCH_POSITIONING.md` §1.6「车钩力定位」的"待修订"标记已改为**"已修订并落地"**（含 `−6·min(pn−1,2)` / 上界 −12 / 仍不作均值最小化）；`AGENTS.md` 同项同步；`ITSC_PAPER.md` 已加**【2026-10-01 口径/目标/算法三重变更声明】**（正文旧数值不得作现行结果引用）。**待重训裁定的只是"该超限项权重是否保留/放大"**，不再是措辞修订。
- **相关**：ADR-014 / ADR-018 / ADR-020（被本闭环修订执行面）、ADR-013（RL 定策 + 底层执行）、ADR-017（训练量）；`docs/REFERENCE_INDEX.md`（四改造的文献→代码映射）；`LEARNINGS.md` LRN-20261001-006（冻结副本事故）/ -007（不可达梯度臂）/ -008（短窗口结论不可外推 + 有效域判定）。

## ADR-022 MPC 对比基线唯一化为 NMPC；删除 fair / 简化 MPC 及其旧评估脚本 - 2026-10-01

- **状态**：决策（**覆盖式修订 ADR-016 / `RESEARCH_POSITIONING.md` §1.6 中"对比基线 = `fair_mpc_controller`"的指名**；ADR-016 的 **Regime A 协议本身不变**）
- **背景**：仓库里长期并存**三个** MPC，命名与锚点混乱：
  1. `FairMPCController`（`fair_mpc_controller.py`）——列内**聚合列模型** + 车钩力**代理** + scipy SLSQP；被 `RESEARCH_POSITIONING.md` §1.6 指名为主表 MPC；且是 `evaluate_decompose --mpc_type` 的**默认值**；
  2. `NMPCController`（`nmpc_controller.py`，2026-09-17 立项）——列内**集中质量(lumped)多体** + **MT-2 符号化车钩** + 车钩力 ≤1000 kN 硬约束 + casadi/IPOPT；其立项口径明写"**替换粗糙 FairMPCController**…不要留粗糙 MPC 当靶子，目标是 MARL 效果达到与成熟 MPC 相当"；
  3. `MPCController`（`mpc_controller.py`）——简化线性 MPC，`--mpc_simple`；全仓（含全部历史结果 JSON）**从未启用**。
  ⇒ 现状是"**文档锚 A、默认跑 A、立项口径要换 B**"，且 A 还是被明确判为"粗糙靶子"的那条；另叠加当日审计出的 fair 路径**桥接量纲错配**（见 `DIAGNOSTICS_2026-10.md`「修复-2026-10-01d」，已修，但该类控制器本就是待替换对象）。用户裁定：**"只留 nmpc，其他的都删除"**。
- **选项与权衡**：
  - 选项 1 **维持三者并存**：命名/锚点继续混乱，主表取值实际由 CLI 默认值决定（与"默认值不得静默决定协议"直接冲突）。
  - 选项 2 **只留 NMPC，另两个 `git mv` 到 `archive/`**：符合"历史代码资产进 archive"规范，但**保留死代码与"副本与生产并行演化"风险**（正是 LRN-20261001-017 的成因形态）。
  - 选项 3 **只留 NMPC，彻底删除（含依赖旧脚本的评估/制图链）**【**选此**，用户裁定】：消除命名歧义与"粗糙靶子"风险；代价 = 丧失 fair 基线的现成复现能力（靠 git 历史 + 本 ADR 记录动机与判据）。
- **决策**：
  1. **唯一 MPC 对比基线 = `NMPCController`**（casadi + IPOPT；列内集中质量(lumped)多体 + MT-2 符号化车钩 ≤1000 kN 硬约束；Regime A 逐线重喂 `grade_at` + 在线标定 b0）。
  2. **删除** `src/controllers/fair_mpc_controller.py`（`FairMPCController`）与 `src/controllers/mpc_controller.py`（`MPCController`）。
  3. `evaluate_decompose.py` 收敛为 **nmpc-only**：去 `fair` / `mpc_simple` 分支；移除 `--mpc_simple` 与随之失效的 `--mpc_enforce_coupler`；**`--mpc_type` 保留为单值枚举 `{'nmpc'}`（默认 `nmpc`）** —— 保留只为让既有文档命令（显式带 `--mpc_type nmpc`）按原样可复现，**不再是"默认值静默决定协议"**（LRN-20261001-011）。
  4. **删除依赖旧脚本的评估/制图链**：`src/evaluation/evaluate_m1_m3_long.py`、`make_m1m3_figures.py`、`make_5train_fig.py`、`eval_phys2_m1_5seed.py`、`eval_phys2_5train.py`、`eval_dqn_multitrain.py`。这些脚本承载的 **M1/M3/M4 旧语义代号已废止**，不再作现行路径。
  5. **术语统一（防"乱其名字"）**：`nmpc_controller.py` 所述"多体" = **集中质量(lumped)多体**（`n_lump` 块/列），**不是**逐车 ~101 节全耦合多体；文件头已加术语声明与 ADR 指针。
- **后果 / 待办**：
  - **SSOT 覆盖式修订**：`RESEARCH_POSITIONING.md` §1.6 的 `fair_mpc_controller` 指名 → 改为 `NMPCController`；`AGENTS.md` / `docs/README.md` / `REPRODUCIBILITY.md` / `PROJECT_PIPELINE.md` / `EXECUTION_RULES.md` 等现行路径同步。
  - ⚠️ **MPC 行历史数值全部作废**（控制器更换 + 桥接口径已修）⇒ 主表须按 Regime A 重跑（显式 `--mpc_type nmpc`）。
  - `requirements.txt` 中的 `scipy` 在 `src/` 内**已无引用**（原仅 fair/simple 用）⇒ 暂留，避免连带风险；如需精简另议。
  - `history/**` 内引用 `evaluate_m1_m3_long` 的旧脚本成为**悬空引用**（历史区，按设计不复现）；`outputs/deprecated/**`、`outputs/results/decompose/*.json` 等历史结果**原样保留**。
  - **未裁决项（不变）**：① 主表 D-RL 行取 `last_ep1400` 还是 `best`；② `1400ep × 5 seed` 的算力（单机 ≈58 天，减量 vs 并行）；③ **NMPC 的制动深度受"两重上限"约束** —— (a) `accel_lo=-0.75` ⇒ 期望 ED 上限 0.75，而规则层/RL 的 ED 可达 1.0；(b) 桥接的 ±0.5 ED 调制权限带（实测 300 步窗口中 NMPC 有 **455 次**越权被 clip，historical fair 行为 0）。二者都是**控制器/接口参数**而非桥接错误，且 (b) 的带宽与 D-RL **完全相同** ⇒ 放宽须同步评估 D-RL 的同一限制，勿造新的不对称。
- **验证（实跑）**：`check_agents_links.py` ⇒ `[OK] … 23 个已有 ADR`；定向测试 46 passed；`--mode mpc --mpc_type nmpc --max_steps 300` ⇒ `viol 0 / band 100% / meanED 0.512 / 求解 74ms均值 / 桥接越权请求 455 步·机车`（求解成本较已删除的 fair/SLSQP 快约 9× ⇒ 53km MPC 行 ≈0.74 h/seed）。
- **相关**：ADR-016（其 MPC 指名被本 ADR 覆盖；Regime A 协议延续）、ADR-007（简化 MPC baseline 的引入，其产物由本 ADR 删除）、ADR-021（四改造 + AB 通道裁定）；`DIAGNOSTICS_2026-10.md`「修复-2026-10-01d」+「删除-2026-10-01」；`LEARNINGS.md` **LRN-20261001-017**。

## ADR-023 ED 调制带宽放宽为全幅（`ed_mod_coef` 0.5 → 1.0）；带宽只由控制器默认值唯一定义 - 2026-10-02

- **状态**：决策（**覆盖式修订** ADR-022「未裁决项③(b)」与 `DIAGNOSTICS_2026-10.md`「删除-2026-10-01」的"±0.5 权限带对 NMPC 偏窄"待裁决项；ADR-021 的 A/B/C/D 四改造、reward schema、信用视界口径**不变**）
- **背景**：ADR-022 验证时实测唯一 MPC 基线 NMPC 行出现 `桥接越权请求 455 步·机车`（300 步 × 3 列 × 2 机车 = 1800 个"机车-步"机会，≈25%，非偶发）。根因 = decompose 通道的**动作权限带宽**：`final_ed = clip(baseline_ed + ed_mod_coef(0.5)·ed_mod, 0, 1)` ⇒ 可交付 ED 仅 = 规则基线 ± 0.5；而 MPC 桥接的期望 ED ∈ [0, 0.75]（受 `accel_lo=-0.75` 约束）、规则基线 ∈ [0, 1] ⇒ 二者之差可达 **1.0 > 0.5** ⇒ 请求被 clip（截到边界而非丢弃）。用户裁定：**"放宽 ① 吧，这个只是作为一个 baseline，所以细节不重要，你自主决策即可"**。
- **选项与权衡**：
  - 选项 1 **只放宽 MPC 侧**（桥接输出 `|ed_mod| > 1`）：不动 D-RL，但制造**新不对称**（MPC 带宽 > D-RL 带宽），与 ADR-016 "不失公允"口径冲突 ⇒ 否。
  - 选项 2 **保持 0.5、仅在论文声明**：省一次重训，但把"作者自己的 baseline 被自己的接口卡住"留在审稿人视野内（strawman 反质疑），且四分之一的请求交付失真 ⇒ 否。
  - 选项 3 **全局放宽为全幅 `ed_mod_coef = 1.0`**【**选此**】：`ed_mod ∈ [-1,1]` 恰好覆盖全部可达差（`|Δ| ≤ 1.0`）⇒ 桥接零截断；**两个通道（MPC 与 D-RL）权限依旧完全相同**（对称，不是只放宽 MPC）。
- **决策**：
  1. `MultiLocoController.get_action_decomposed` 的 `ed_mod_coef` 默认值 **0.5 → 1.0**。这是全仓**唯一改点位**（无任何调用方显式传该参数）⇒ 训练与评估同时生效，不存在"训练按 A、评估按 B"。
  2. **带宽只由控制器默认值唯一定义**：`evaluate_decompose.ED_MOD_COEF` 从**硬编码镜像常量**改为 `inspect.signature(...).default` 派生 —— 消灭 LRN-20261001-017 同族的"两处并行演化 ⇒ 静默失配"。
  3. `build_metadata` 新增键 `ed_mod_coef`（**动作空间语义**：换值即换策略含义，同一 ckpt 行为不同）⇒ 历史运行可比对。
  4. **不改** `accel_lo = -0.75`（ADR-022 未裁决项③(a)）：它是**控制器自身**的制动深度参数，且 0.75 m/s² 电制动已大于最陡 −10‰ 的重力分量（≈0.098 m/s²），物理上不是瓶颈 ⇒ 保持原值并在此**登记为已声明差异**（规则层 ED 可达 1.0 vs NMPC 期望 ED ≤ 0.75）；若日后要彻底对齐另立 ADR。
- **后果 / 待办**：
  - ⚠️ **动作空间语义变更 ⇒ 按旧带宽（0.5）产出的 D-RL 训练与评估数值对新口径失效**。本次已**主动停掉** seed0 长训（PID 673，ep55/1400，elapsed 5h22m）并按新口径**重启**（新输出目录 `adr023_1400ep_seed0`）；旧目录 `adr021_1400ep_seed0` 的 55 集产物**原样保留**（不覆盖、不删除），按"旧带宽口径、待重跑"标注。
  - `P0 三行基线`、`AB 通道裁定（--mask_lever ab）` 等基于**旧 ckpt + 旧带宽**的结论一并作废，随 A/B/C/D 重训后的复核同批重做（见 `docs/logs/progress/PROGRESS_2026-10.md` 长久计划）。
  - 放宽的是**决策可见的动作范围，不是安全边界**：安全仍由 SafetyLayer（ETCS 限速/防追尾）、车钩力安全层（`enforce_coupler`）、`_coupler_throttle_scale`、AB 充风门与单步并发门共同约束。
- **验证（实跑）**：`evaluate_decompose --mode mpc --mpc_type nmpc --max_steps 300 --n_seed 1` ⇒ `桥接越权请求 **0** 步·机车`（改前 455），其余指标几乎不变（`reward +2221 / peak 318kN / viol 0 / band 100% / meanED 0.500 / 末速 73.4km/h / 求解 69ms 均值 / fail 0`）；定向测试 **39 passed**；全量回归与 `check_agents_links.py` 见 `DIAGNOSTICS_2026-10.md`「放宽-2026-10-02」。
- **相关**：ADR-022（其未裁决项③(b) 由本 ADR 裁决）、ADR-021（reward / 信用视界改造，动作语义按其口径继续）、ADR-009.1（decompose 动作结构）、ADR-016（Regime A 不失公允口径）；`DIAGNOSTICS_2026-10.md`「放宽-2026-10-02」；`LEARNINGS.md` LRN-20261001-017（同族：镜像常量 / 跨通道语义搬迁）。

## ADR-024 ED 调制带宽回退为半幅（`ed_mod_coef` 1.0 → 0.5）：放宽对 MPC 无收益、对 RL 有害 - 2026-10-02

- **状态**：决策（**覆盖式修订** ADR-023 决策 1「带宽 0.5 → 1.0」；ADR-023 决策 2/3/4（派生常量、metadata 键、`accel_lo` 保持）**继续有效**，不回退）
- **背景**：ADR-023 放宽带宽的唯一动机是消除 NMPC 桥接的"越权请求"截断（455→0，已达成）。但随后**完整剖面 A/B 实测**显示该放宽**得不偿失**：
  1. **对 MPC 无可用收益**：53km 完整剖面（36000 步）MPC 裸跑 `reward −813 642 / band 61.98% / 求解 fail 1936`，加规则内层护盾（M3，`--mpc_inner_rule_cyclic`）后 `fail 1936→0`、ATP 事件 3.94M→622k、band 61.98%→71.04%，但 `reward −3 635 838`、末速 40.5 km/h（擦下限）—— 两种配置**都远弱于规则基线**（D-Rule `+92 950 / band 97.28%`）。⇒ 放宽带宽并未让 NMPC 变得可用；"越权请求归零"只是观测指标改善（且 MPC 细节按 ADR-023 原话"不承担立论"）。
  2. **对 RL 明确有害**：除 `ed_mod_coef` 外**完全同构**的两次长训 A/B 对照 —— 旧口径（0.5）ep51–55 `peak 826–906 kN / viol 0` **连续零破线**；新口径（1.0）同区间 `peak 1188–1390 kN / viol 327–694`。新 run 的四次 53km 长程评估仅 ep150 一次达标（`viol 0 / band 99.9% / 末速 68.0`），ep50/100/200 均不达标，ep200 末速崩至 **30.3 km/h**（远低于下限 40）⇒ 训练**振荡不稳**。根因：`ed_mod = 1.0` 允许策略**整幅撤销规则层的 ED**（Δ=−1.0），在长下坡上直接击穿 1000 kN 底线。
- **选项与权衡**：
  - 选项 1 **保持 1.0 并继续长训**：给策略更长时间/更稳探索，但每次长程评估周期机时代价高，且 A/B 已显示结构性伤害（可整幅撤销 ED）而非随机波动 ⇒ 否。
  - 选项 2 **回退 0.5**【**选此**】：恢复 ADR-023 之前的稳定训练（旧口径 ep51 起连续零破线），代价 = NMPC 桥接重新出现 ~25% 越权截断（仅影响 MPC baseline 细节，不承担立论，已在 `DIAGNOSTICS` 记录为观测指标）。
  - 选项 3 **改成非对称**（RL=0.5、MPC=1.0）：再次制造通道不对称，违反 ADR-016 不失公允口径 ⇒ 否。
- **决策**：
  1. `MultiLocoController.get_action_decomposed` 的 `ed_mod_coef` 默认值 **1.0 → 0.5**（仍是全仓唯一改点位；`evaluate_decompose.ED_MOD_COEF` 与 `metadata.ed_mod_coef` 均**派生**，自动跟随，无需手改）。
  2. **保留 ADR-023 的两项结构性改进**：派生常量（消灭镜像常量失配）+ metadata 键 `ed_mod_coef`（动作空间语义可比对历史）。
  3. **保留** `accel_lo = -0.75` 与"MPC 期望 ED 上限 0.75 < 规则/RL 可达 1.0"这一**已声明差异**（ADR-023 决策 4 不变）。
  4. 「桥接越权请求」计数**保留为观测指标**（不再作为调整带宽的依据）；MPC 主表行评估时如实记录，论文中不作 strawman 讨论。
- **后果 / 待办**：
  - ⚠️ **动作空间语义再次变更 ⇒ 一切按 1.0 口径产出的 D-RL 训练/评估数值对新口径失效**。本次已**停掉** `adr023_1400ep_seed0` 长训（ep205/1400，elapsed 14h20m）并按 0.5 口径**重启**（新输出目录 `adr024_1400ep_seed0`）；`adr023_1400ep_seed0` 与 `adr021_1400ep_seed0` 产物**原样保留**（不覆盖、不删除），分别标注"1.0 口径、已回退""0.5 口径、旧 reward/结构"。
  - 主表两行 baseline（D-Rule / MPC）在 0.5 口径下的数值**待与新 ckpt 同批重跑**（本次 `_adr023_*` 结果按"1.0 口径"存档，可作 ADR-023 宽带的对照证据）。
  - M3 消融（MPC + 规则内层护盾）结论**不受本回退影响**：它测的是 MPC 是否缺内层护盾，与新 ckpt 无关，结论可留用（`fail 1936→0`、ATP 事件降 6×，但更保守、末速擦下限）。
- **验证（实跑）**：定向测试 **39 passed**（`test_metric_accounting` / `test_fleet_decompose` / `test_nmpc_controller`，含饱和计数测试按 0.5 口径重写为"U=−0.4 不越界 / U=−0.75 越界"二态对照）；全量回归与 `check_agents_links.py` 见 `DIAGNOSTICS_2026-10.md`「回退-2026-10-02」。
- **相关**：ADR-023（其决策 1 由本 ADR 覆盖，决策 2/3/4 保留）、ADR-022（未裁决项③(b) 的完整轨迹：0.5 → 1.0 → 0.5）、ADR-021（reward/信用视界，不受影响）、ADR-016（不失公允口径）；`DIAGNOSTICS_2026-10.md`「放宽-2026-10-02」「冒烟与基线-2026-10-02」「回退-2026-10-02」；`LEARNINGS.md` LRN-20261001-017。

<!-- 该文档整理/压缩于 2026-10-01 -->

## ADR-025 训练震荡根因修复（AB 新增源否决覆盖 90s 滞后 + ValueNorm 指数遗忘 + KL 早停判据标准化） - 2026-10-03

- **状态**：决策（代码已落地 + 回归通过 + **沙盒 80 ep 验证：震荡消除、完整剖面达标**）
- **背景**：`adr024_1400ep_seed0`（ed_mod_coef=0.5 口径）长训至 **ep341** 呈现**严重震荡且越练越差**，已按用户裁定**停训**（优雅 SIGINT，ep340 ckpt 保留）。日志量化（682 条回合记录）：
  - 干净回合（viol=0）占比 **62%(ep0-49) → 22%(50-99) → 16%(300-341)**；峰值>1200kN 占比 34%→**63%**。
  - `value_norm.std` 在 **ep50 前后从 ~4118 阶跃到 ~11515，此后不再回落**；KL 早停几乎每回合触发。
  - 坏回合特征：pkCpl **1.6~1.8 MN**、viol 2~4 万、`gap_min` 出现**负值**（物理上不该发生）⇒ 单回合回报 ≈ **-34000**。
- **根因（三条，按因果顺序）**：
  1. **激励不对称（上游）**：速度带正奖励稠密（领航列 **+6.0/步**），车钩力项权重仅 **0.2**、超限项封顶 **-12/步** ⇒"压着 1000 kN 上限换速度带"仍是局部最优，RL 缺"守线"梯度（继承 `诊断-2026-10-01` 断点 1，未治本）。
  2. **坏模式自我强化（下游直接机制）**：一次暴力 AB 爆发 → 极端负回报 → **P(S|G) 双峰** → 全程 Welford 的 `ValueNorm` 尺度被早期极端回报**永久抬高** → 归一化失真 + KL 早停常态化 → 策略更新被压制、退不出坏模式 → 脏回合占比随训练上升。
  3. **动作权限（触发源）**：`SafetyLayer.ab_new_source_veto` 的预测式时域取 **"列长/波速≈6s"**（波到达时间），而实测 **AB 首现→车钩力首破 ≈90.1s** 是**力建立滞后**，两者被混同 ⇒ 预测式 horizon 过短，拦不住滞后峰值（安全层只钳"指令"、不撤已建立 AB 源，故滞后峰值照冲）。
- **决策（三项最小改动）**：
  1. **AB 新增源否决覆盖真实滞后**（`src/safety_layer.py`）：新增物理参数 `coupler_veto_lag_s=90.0`（新增源→峰值建立滞后），预测式 `horizon = lag_s/dt`（取代"列长/波速"）；预测式需 **≥max(30s, 半个时域)** 历史才启用（防短历史噪声被 90s 外推放大成"全禁 AB"）。`coupler_veto_lag_s=0` 回退旧口径。反应式阈值 `0.6`、预测式 margin `0.9` **不变**。
  2. **`ValueNorm` 支持指数遗忘**（`src/algorithms/mappo_agent.py`）：`ValueNorm(decay=...)`，每次 update 先把历史有效样本数乘 `decay`；agent 默认 `value_norm_decay=0.98`（半衰期≈34 次更新）。`decay=1.0` = 旧全历史 Welford（零回归）。
  3. **KL 早停判据标准化**（`src/algorithms/mappo_agent.py`）：`approx_kl` 由 `mean((Δlogp)²)`（**平方差**、非 KL、量纲随 log-prob 尺度漂移）改为标准 PPO 一阶估计 **`mean(Δlogp)`**（近似 KL(π_old‖π_new)）；阈值语义 `target_kl*1.2` 不变。
- **刻意不做**：① **不动奖励权重**（激励侧"贴上限跑"的治本留待第二步，避免一次改太多、丧失因果归因）；② **不从 RL 收走 AB 动作维度**（ADR-021 已裁定不在重训前砍动作空间）；③ 不做任何"布尔 debug 开关"，沙盒以**独立剖面 + 独立配置**承载。
- **验证（实跑）**：
  - 全量回归 **`tests/` 244 passed**（含 `test_safety_layer` / `test_ab_refill_and_safety_authority` / `test_grade_profile` / `test_per_agent_critic` / `test_metric_accounting`）。
  - 否决行为差异（合成上升峰值 100→500 kN @1000 N/步，当前 500 kN 未到反应式 600 kN 阈）：**旧口径预测式 veto=False，新口径 veto=True** ⇒ 新闸门确实更早封住滞后峰值。
- **后果 / 待办**：
  - ⚠️ 训练效果**尚未验证**：须按主口径重跑并**监控干净率轨迹**（ep50/ep100 应与旧 run 的 22%/16% 对照改善）；若仍震荡，进入奖励侧修改（第二步）。
  - 新增**训练方法调试沙盒**剖面 `shuozhou_real_53km_slice16k`（53km 的 21.06–37.02km 切片≈15.7km，物理/编组/安全层与主口径一致）与配置 `configs/experiments/_debug_train_method_slice16k.yaml`。⚠️ **纪律：沙盒只作方法迭代，结果不得进正文主表**（ADR-017 §3）。
  - 沙盒**不缩短单集窗口**（保持 curriculum ≤1200 步=120s ≥90s 滞后）：否则 90s 滞后峰值不出现，测不到真机制。故沙盒的加速来自"更短的完整剖面评估（12000 vs 36000 步）"，非单集。
- **相关**：ADR-017（训练/评估时域，沙盒纪律依据）、ADR-018（AB 减权限，本 ADR 修其预测时域口径）、ADR-021（信用分配/reward 定位，"不动奖励"的依据）、ADR-024（被停训的口径）；`DIAGNOSTICS_2026-10.md`「停训-2026-10-03」。

## ADR-026 编队间距奖励改"ATP 对齐两段式"（贴安全底线跑、间距尽量小） - 2026-10-04

- **状态**：决策（代码已落地 + 单测/形状核对通过；**训练效果待沙盒 A/B**）
- **用户目标（原话）**："保证车钩力不破线的同时，运输效率尽量大，也就是说维持一个安全高效的间距，间距小但是不至于触发 ATP。"
- **背景（实测，同剖面 15.7km 切片）**：RL(best ep80) 最小列距 **19.0 m**、列距误差 80.3/357.2 m，**且峰值(880>788)、band(93.12%<99.78%)、末速(49.3<55.4) 全面输给规则基线**（规则最小列距 87.4 m）⇒ RL 的调制**把间距搞坏**，非场景问题。
- **根因（代码级）**：旧间距奖励 = `+1.0·exp(-(ge/140)²)` 小高斯丘（对固定 VCTS 200 m 双向惩罚）+ `max(-2(80-gap)², -200)` **饱和**势场 + 一次性 `-10` 碰撞项。缺陷：① **无"贴紧"奖励**（200 m 目标与"越小越好"相悖）；② **危险区无梯度**（gap≤70 m 后恒为 −200）；③ 间距权重（≤1.0/对）远小于速度带（6.0/列）。
- **关键事实**：ATP 对间距的判据**不是固定距离，是 ETCS 制动曲线**——后列须在追上前列尾前降到前列当前速度（`train_fleet_env.py:503-508` 注入 `EbdTarget(kind='gap')`），边界 = `EtcsBrakingCurve.braking_distance`（含制动建立期 + 坡度）。
- **决策**：
  1. **d_safe(t) = ETCS 制动距离**（`TrainFleetEnv._atp_safe_gap` 复用 `etcs_curve.braking_distance`）——**奖励底线与 ATP 介入线同源**，"小但不触发 ATP"逐字兑现。
  2. **效率目标 `d_eff = GAP_EFF_MARGIN(1.1)·d_safe`**（10% 裕量，用户选定）。
  3. **效率项** `+GAP_EFF_W(3.0)·max(0, 1-(gap-d_eff)/GAP_EFF_SCALE_M(150))`：gap≥d_eff 时越接近 d_eff 越高，再大衰减到 0。
  4. **危险项** `-GAP_DANGER_W(60.0)·((d_safe-gap)/d_safe)²`，`gap<d_safe` 时生效、**不封顶**（取代旧 −200 饱和）。
  5. `REWARD_SCHEMA` → `'v3-atp-aligned-gap'`；保留硬安全层（ETCS EBI / min_gap / 车钩钳制）与车钩力机制（ADR-021 超限项**不动**）。
- **文献依据**：Guo2025 式5（安全距离随速度动态变化）／Zhang2021（设点 + 越界悬崖式奖惩）／Hua2024 式2（平滑跟踪项 + 独立防撞项）。已登记 `docs/REFERENCE_INDEX.md`。
- **验证（已做）**：① 定向 `pytest` **44 passed**（`test_coupler_reward_overlimit` 断言同步 v3）；② 奖励形状核对（stub `d_safe=100`，相对 gap=110）：gap 120→+2.8、200→+1.2、≥260→0、90→−0.6、50→−15.0、10→−48.6 ⇒ 效率项单调递减、危险项陡且**不封顶**，符合设计。
- **未决 / 待办**：⚠️ **训练效果待验证**：同配置同 seed 的沙盒 A/B（旧 v2 奖励 80 ep vs 新 v3 奖励 80 ep），判据 = **最小列距贴近 d_safe 且不低于、band 不掉、峰值 ≤1000、且三项 ≥ 规则基线**。reward 语义变更 ⇒ 旧 ckpt 全部失效（须重训）；沙盒结果仍**不得进正文主表**（ADR-017 §3）。
- **相关**：ADR-017（沙盒纪律）、ADR-021（车钩力超限项，本 ADR 不动）、ADR-025（同期稳定性修复）、ADR-018（列距为编队底线指标）；`DIAGNOSTICS_2026-10.md`「沙盒结果-2026-10-04」。

## ADR-027 ATP 制动不可被车钩力缓和放掉（安全层规则重排） - 2026-10-04

- **状态**：决策（代码已落地 + 定向回归通过 + 全量 **245 passed**；**沙盒训练效果待验证**）
- **用户质疑（原话）**："负间距是什么意思？追尾了？ATP 干什么吃的"／"改成CTCS的ATP会改善这个问题吗？不能追尾啊，这证明ATP没有多大作用"
- **背景（实测）**：v3 间距奖励沙盒（`_debug_gapv3_slice16k`，80 ep）ep21–24 `gap_min` 64/155/147/54 m 好转，但 **ep25 仍出现 `gap_min −53 m` + 单回合 R −9,185,419 + vstd 17105** ⇒ v3 降低了负间距频率、**未根除**，与 ADR-025 的"坏模式自我强化"同一签名。
- **根因（代码级，`src/safety_layer.py` `protect()`）**：规则施加顺序 = ETCS（规则0）→ 反应式超速（规则1）→ 车钩力缓和（规则2）→ 间距（规则3）。规则 2 在 `coupler_override='release'`（fleet 子环境默认、未显式传参）下把制动**钳回 0**；因它在 ETCS **之后**，会把 ATP 刚下的制动**放掉**。形成**自毁闭环**：
  后列刹不住逼近前列 → 列间受压车钩破 1000 kN → 车钩力规则 release 放掉 ETCS 电制动（AB 紧急建立需 ~10 s）→ 后列在下坡失去即时制动继续下探 ⇒ **间距穿负**。
- **澄清（换 CTCS 解决不了）**：CTCS-2/3 与 ETCS 的 ATP 同族（目标距离制动曲线 + SBI/EBI 介入），换标只换参数不换机制；问题不在制式，在**本实现的规则优先级**。
- **决策（最小改动：规则施加顺序 = 优先级）**：`protect()` 改为 **A 车钩力缓和 → B 间距防挤压 → C 反应式超速 → D ETCS（前瞻）**；后施加者用 `np.minimum` 覆盖前者 ⇒ **ETCS 制动最后施加、不可被放掉**。规则语义/阈值/`coupler_override` 行为**均不变**（唯一变化 = ATP 制动不再被覆盖）。
- **刻意不做**：① 不改 `coupler_override` 默认值（Layer-1 单列 release 语义保留；单列无 ETCS 目标 ⇒ 行为零变化）；② 不改 ETCS 曲线参数/建立期假设；③ 不动奖励。
- **验证（已做）**：
  - 定向回归 `tests/test_safety_layer.py::test_safety_atp_brake_not_released_by_coupler_rule`：ETCS EBI（目标 50 m）+ 车钩 1200 kN + 默认 release ⇒ 断言紧急制动**保留**（`corrected ≤ -0.9`），且两条规则均命中。
  - 全量 `tests/` **245 passed**（既有 `test_safety_coupler_force_limit_blocks_braking_release_default` 仍通过：无 ETCS 时 release 语义不变）。
- **待办 / 验证**：沙盒重跑 `_debug_gapv3_atpfix_slice16k`（同配置同 seed）监控 `gap_min<0` 是否归零、vstd 是否不再被单回合放大；判据 = 与 v3 基线对照 + 峰值/band/最小列距**三项 ≥ 规则基线**。
- **相关**：ADR-025（同期稳定性，同一"坏模式自我强化"签名）、ADR-026（间距奖励）、ADR-018（断面力口径）、ADR-017（沙盒纪律）；`DIAGNOSTICS_2026-10.md`「负间距根因-2026-10-04」。

### ADR-027 修订（2026-10-04 同日）—— 原"自毁闭环"根因假设被证据推翻

- **证据（逐位一致）**：修复版沙盒 `_debug_gapv3_atpfix_slice16k`（同配置同 seed + 新安全层）跑出的 ep20/ep25 与修复前**逐位一致**：
  - ep25 修复前/后均为 `R -9185419 | pkCpl 880kN | viol 0 | loss 1.743 | vloss 1.742 | vstd 17106 | gap_min -53m`；
  - ep20 修复前/后均为 `R -2961 | pkCpl 846kN | viol 0 | loss 3.421 | vloss 3.411`。
- **推论**：这两条负间距轨迹**从未走到"车钩力规则放掉 ATP 制动"的代码分支**（否则重排必然改变动作、轨迹不可能逐位相同）⇒ 原"自毁闭环"根因**不成立**。
- **保留**：规则重排（A 车钩→B 间距→C 超速→D ETCS）+ 回归单测**保留**——ATP 优先级语义更正确、且**零回归**（245 passed）；但**不得**再宣称它"解决了负间距"。
- **修正后的致因链**：负间距回合 R≈-9.18e6 的真正放大器是**间距危险项在穿透时退化为"米²"**（`over` 分母塌缩），见 **ADR-028**。负间距**本身**（虚拟穿透）为何发生仍**未决**。

## ADR-028 间距危险项穿透炸裂修复（`d_safe→0` 使 `over` 退化为"米²"） - 2026-10-04

- **状态**：决策（代码已落地 + 定向回归通过；**沙盒重跑待验证**）
- **背景（实测）**：`_debug_gapv3_atpfix_slice16k` ep25 `gap_min −53 m` + `R −9,185,419` + `vstd 17105`；ep26–45 vstd 仅从 17k 缓降到 ~10.5k。该单集巨负值比正常回合（+3000~+7000）大 **3 个数量级** ⇒ 污染 ValueNorm（ADR-025 的 `decay=0.98` 不足以快速回落）⇒ 后续数十集 advantage 被压缩、训练停滞。
- **根因（代码级，`src/environments/train_fleet_env.py` `_calculate_reward_decomposed`）**：
  - `_atp_safe_gap(i)` 在 `lead_tail <= head`（即 `actual_gap<=0`，穿透）时**恒返 0.0**；
  - 危险项原式 `over = (d_safe − actual_gap) / max(d_safe, 1.0)`；`d_safe=0` ⇒ 分母 = **1.0 米** ⇒ `over = |actual_gap|`（穿透**米数**）⇒ `over²` 是"米²"，`−60·53² ≈ −1.7e5/步`；
  - 单步穿透持续 ~54 步即 ≈ −9.18e6，与实测 ep25 回报**量级吻合**。
  - 本质 bug：`over` 本应是**无量纲比值**（0~1+），分母塌缩到 1.0 m 时退化成米。
- **决策（最小改动）**：危险项分母加固定参考尺度 `GAP_DANGER_REF_M = 100.0`（m）：`denom = d_safe if d_safe > 1.0 else GAP_DANGER_REF_M`。**非穿透路径（d_safe>1）行为逐位不变**；穿透时 `over` 保持无量纲、量级有界（53 m ⇒ over=0.53 ⇒ ≈ −16.9/步）。
- **schema**：`REWARD_SCHEMA` `'v3-atp-aligned-gap'` → **`'v4-atp-aligned-gap'`**（reward 语义在穿透路径改变 ⇒ 按 ADR-026 同款纪律，旧 v3 结果与新 run 不可直接比较）。
- **刻意不做**：① 不改 `GAP_DANGER_W`（危险项仍陡、保留"不封顶"精神，只是不再无量纲炸裂）；② 不引入 reward clipping（治标，且截断真实大惩罚梯度）；③ 不动 ADR-026 效率项与硬安全层。
- **验证（已做）**：定向回归 `tests/test_train_fleet_env.py::test_fleet_gap_danger_penalty_bounded_on_penetration`（两对 53 m 穿透 ⇒ 断言 `reward > −3000`；修复前 ≈ −3.4e5）。
- **待办 / 验证**：沙盒重跑监控 —— `gap_min<0` 时单集 `|R|` 是否回到 ~1e4 量级、`vstd` 是否不再阶跃到 1e4+。
- **未决（另案）**：负间距**本身**（虚拟穿透）为何发生——ADR-027 的权限假设已排除，仍需定向诊断（加载 ckpt 复现 ep20/ep25，逐步记录 ETCS 是否介入 / 制动是否被放掉 / 速度-坡度-间距趋势）。
- **相关**：ADR-026（间距奖励）、ADR-025（ValueNorm 遗忘）、ADR-027（本 ADR 即其修订指向）、ADR-017（沙盒纪律）；`DIAGNOSTICS_2026-10.md`「负间距根因-2026-10-04」。

## ADR-029 虚拟穿透根因修复：牵引必须进入安全层 + EBI 紧急不被动作 AB 源压过 - 2026-10-04

- **状态**：决策（代码已落地 + 定向回归通过 + 全量 **248 passed** + 定向压测探针由穿透转安全；**沙盒重跑待验证**）
- **背景（未决问题）**：ADR-027 的"自毁闭环"假设被逐位一致证据推翻后，负间距**本身**（虚拟穿透）为何发生仍**未决**。本轮以**定向压测探针**（单列 decompose，合成更慢前列，gap0=300 m，−12‰ 陡坡，80→54 km/h，全长 3000 步）复现并定位根因。
- **决定性证据（三档后列动作对照，同场景）**：

  | 后列动作 | 最小间距 | 穿透 | EBI 步数 |
  | --- | --: | :--: | --: |
  | 全牵引 `[-1,0]` | **−65.3 m** | **是** | 2316/3000 |
  | 惰行 `[0,0]` | +82.5 m | 否 | 1354/3000 |
  | 全制动 `[1,-1]` | +192.2 m | 否 | 205/3000 |

  ⇒ **牵引是唯一穿透因子**；EBI 已触发（2316 步）却压不住间距 ⇒ 怀疑"安全层无法取消牵引"。
- **根因（代码级，`src/environments/train_env.py` `_step_decomposed`）**：原投影把**牵引动作映射为 0**（`proj_throttle[loco] = -max(act[k,0],0)`，牵引仅取负深度）⇒ **牵引从不进入安全层**，与 `protect()` 约定（`>0`=牵引、`<0`=制动）不符。后果：安全层规则 A(车钩力缓和)/B(间距防挤压)/D(ETCS EBI) 声称的"抑制/禁止加速"对牵引**全部落空**——EBI 触发时列车仍满牵引，"边牵引边紧急制动"，下坡重力+牵引共同加速 ⇒ 虚耦合穿透。
- **次因（同源缺陷）**：`step_vehicles_ed_ab` 中 **`ab_sources` 优先级高于 `ab_command`**（`train.py:556-559`）⇒ 动作已发 AB 源（MIN/SERVICE）时，EBI 的紧急升级被**静默丢弃**，紧急制动降级为动作档位。
- **决策（最小改动，3 处编辑，均在 `_step_decomposed`）**：
  1. `proj_throttle` 改为**带符号**投影：牵引以**正号**进入安全层（`>0`=牵引），使规则 A/B 能置 0 取消、规则 C/D 能用 `np.minimum` 覆盖为制动；制动/ED 深度逻辑不变。
  2. ETCS EBI 触发时**清空 `ab_sources`**，只发车头 `ab_command=EMERGENCY`（沿波速传全列），确保紧急不被动作源压过。
  3. 安全层修正后的 `proj_throttle` **回写** `throttle`（`min(throttle, max(proj,0))`）与 `ed_throttle`（`min(ed_throttle, max(−proj,0))`）——牵引被安全层压到 ≤0 时 `throttle` 必须同步归零，否则牵引绕过安全层。
- **刻意不做（延后，先验证再定）**：① EBI **无迟滞 latch**（chattering 可能在撤销步 release 刚下的 AB，建立期 4.68 s 建不满）；② EBI **不强制把 ED 打满**（现 `min()` 只封顶不加深）。两项待沙盒重跑判据决定是否追加。
- **验证（已做）**：
  - 定向回归（`tests/test_fleet_decompose.py`）：`test_etcs_ebi_cancels_traction_and_forces_emergency`（满牵引+极近慢目标 ⇒ `throttle.max()≤0` 且 `ab_command==EMERGENCY`）、`test_etcs_ebi_emergency_overrides_action_ab_sources`（动作发 SERVICE 源 ⇒ 紧急压过、`ab_sources` 清空）。**2 passed**。
  - 压测探针重跑（同场景）：全牵引档 **−65.3 m → +75.4 m**（穿透=否）；惰行 +82.5 m、全制动 +192 m 行为不变（零回归）。
  - 全量 `tests/` **248 passed**（编队路径 `TrainFleetEnv._step_decomposed_fleet` 经子环境 `decompose` 委托到本路径，修复对训练生效）。
- **待办 / 验证**：沙盒重跑 `_debug_gapv4_*`（或 v3 同配置）监控 `gap_min<0` 是否归零、vstd 是否无阶跃；判据 = 与规则基线对照 + 峰值/band/最小列距三项 ≥ 规则基线。
- **相关**：ADR-028（穿透放大器，本 ADR 修其**上游成因**）、ADR-027（权限假设被推翻，本 ADR 为真正权限根因）、ADR-026（间距奖励）、ADR-017（沙盒纪律）；`DIAGNOSTICS_2026-10.md`「负间距根因-2026-10-04 · 定案（ADR-029）」；`src/environments/train_env.py` `_step_decomposed`、`tests/test_fleet_decompose.py`。

### ADR-029 验证结果（2026-10-04 同日）—— 训练级确认根除虚拟穿透

- **运行**：沙盒 `_debug_gapv5_adr029_slice16k`（与 v3/v4 **同配置同 seed 0**，仅含 ADR-029 src 修复）；启动器 `scripts/launchers/launch_debug_gapv5_adr029_seed0.sh`，日志 `outputs/logs/diagnostics/log_debug_gapv5_adr029_slice16k_seed0_20261004.txt`；**80 ep / 183.8 min**。
- **判据一（穿透根除，决定性）**：**全 80 集 `gap_min<0` 出现 0 次**（最小 `gap_min` = **46 m @ep33**）。对照 v3/v4 修复前同 seed 对应回合：**ep20 −7 m → +166 m；ep25 −53 m → +143 m**（ep22 +96 m、ep33 +46 m 等均正）。
- **判据二（vstd 不中毒）**：`vstd` 全程稳定在 **819→~2,105**（ep25 = 2,106），**无阶跃到 1e4+**（v3 曾阶跃 17,105）。
- **判据三（性能）**：best reward **9,015.77**、末段平均车钩力峰值 **859.9 kN**、末集 ep80 `pkCpl 1045kN / viol 1 / gap_min 105m`。
- **结论**：ADR-029 在**训练级**确认**根除虚拟穿透**（`gap_min<0` 由 v3/v4 的多回合转为 0）。**遗留（另案，非穿透）**：车钩力仍有零星破线（ep31 `pkCpl 1017kN / viol 2`、ep80 `1045kN / viol 1`）——属车钩力控制精度问题，与本 ADR 修的空间穿透不同轴。
- **仍延后未做**：EBI 迟滞 latch、EBI 强制 ED 打满（现只封顶不加深）——本轮 0 穿透说明现有修复已足够守间距，暂不追加。
- **证据边界**：沙盒（`slice16k`）为方法迭代，按 ADR-017 §3 **不进正文主表**；主口径 53km/1400ep 复核仍需另跑。

## ADR-030 诊断方法定调 +「改法须文献对齐」：AB 充风计时进观测（替代拉长窗口）；车钩力 claim 收窄 - 2026-10-07

- **状态**：决策（原则固化 + 代码已落地 `obs_dim 11→12` + 定向回归 32 passed；冒烟运行中；**主口径复核未做**）
- **背景（为什么"诊断了很多轮仍无结论"）**：把责任归到**方法论**，不是缺第 N 个改法：
  1. **进攻方向选错**：为覆盖 AB 最小充风 222 s 的长滞后，一直在**拉长单条 rollout 窗口**（1200→2500/3000 步），而这是最易溃散的一条路；
  2. **多变量同改**：ADR-021/025/026/027/028/029 每轮把"奖励 + 安全层 + ValueNorm"一起动，**无法归因**；
  3. **无可信基线**：不知道 3 seed 的正常波动带宽，"改好/改坏"分不清信号与噪声。
- **决策（三条原则，写死以后照做）**：
  1. **改法必须文献对齐**：动代码前先在文献里找**同一失效模式的解法**，再落地；禁止"先改再看"。
  2. **单变量 + 受控基线**：固定配置；一次只改**一个**变量；改动前后须能对同一症状指标比较。
  3. **不 overclaim**：立论表述必须与文献实况一致（见下"claim 收窄"）。
- **落地（本轮唯一变量）**：把 **AB 充风计时编码进观测**，替代"拉长窗口"——
  - `train_fleet_env._get_obs_decomposed` 新增 `obs[a, 11] = clip(距上次 AB 释放的充风时长 / ab_min_refill_s, 0, 1)`；`obs_dim 11→12`（`src/environments/train_fleet_env.py` L320 / L670-674）。
  - **文献依据**：Wang2026（IET ITS，重载长大下坡分层 RL）把**累计缓解时间 t_r** 与最大车钩力 f_c 编进状态（`Wang2026_hierRL_fulltext.txt` L631），Si2025（Dueling DQN）状态含 AB 阶段、Zhang2024 约束最小充风时间——即**学界用"状态编码"而非"拉长窗口"处理长时制动滞后**。
  - 口径 = 把 222 s 长时约束做成**可观测量**，让策略在**短窗（≤1200 步，ADR-017 §1）**下即可感知，避免为它拉长 horizon。
- **claim 收窄（防被审稿人一击即破）**：
  - 不能说"文献都忽略车钩力"。**Wang2026（2026）已在单列重载长大下坡 RL 中显式含车钩力**（安全限值 1100 kN，进奖励与状态）；**Song2026 的多列虚拟编组 Tube-MPC 显式含车钩力约束**（±1500 kN，峰值 330.4 kN）。
  - 真正的空白仍是 **"多列群组 × 车钩力 × MARL"** 的交集（Wang2026 单列、Song2026 是 MPC 非 MARL）；立论应表述为"把凭证从单列挪到多列群组"，而非"别人不管车钩力"。→ 待办：`RESEARCH_POSITIONING.md` §1.2 补 Wang2026/Song2026 两条限定。
- **文献对齐的改进项候选（下次单变量对照用）**：
  - MARL：① AB 历史/计时进状态（本 ADR，已落地）；② 序列/预测模块替代长窗口（Hu2026 的 Mamba 状态预测，针对长序列依赖）；③ 分层 / 空间分段（Wang2026）；④ 课程式奖励权重 + 优先经验回放（Hu2026）。
  - MPC 基线：① 车钩力显式进代价与约束函数（Song2026）；② Tube/补偿器抗 AB 时滞（Song2026）；③ 循环制动 GA 寻优作额外对照（He2025，车钩力降 21–23.9%）。
- **验证（已做）**：`tests/test_fleet_decompose.py`（形状/取值域）、`test_train_fleet_env.py`、`test_train_env.py` **32 passed**；冒烟（`--episodes 2`，输出重定向 `outputs/smoke/_smoke/adr030_*`）运行中。
- **刻意不做**：本轮**不动**奖励、安全层、地平线（保持单变量）；受控基线（3 seed + 统一症状口径）待本变量冒烟通过后另立规格。
- **相关**：`DIAGNOSTICS_2026-10.md`「文献对齐-2026-10-07」（逐篇差异与可借鉴项，append-only）；ADR-017（训练时域 ≤1200 步）；ADR-021（车钩力进目标的口径）；`src/environments/train_fleet_env.py`、`tests/test_fleet_decompose.py`；文献 `docs/papers/02_rl/Wang2026_hierRL_fulltext.txt`、`Song2026_TubeMPC_fulltext.txt`、`Hu2026_PMMASAC_fulltext.txt`、`He2025_CyclicGA_fulltext.txt`、`Si2025_DuelingDQN_fulltext.txt`、`Zhang2024_QLearning_fulltext.txt`。


## ADR-031 车钩物理口径切换：容嘉欣2025 图4(b) 查表 + 速度法 sign(Δv)（废止 Stribeck 解析式）；step_vehicles 积分统一 Newmark - 2026-10-12

- **状态**：决策（已落地：`coupler.py` / `train.py` / `params.py` / `nmpc_controller.py` 改完；车钩专项 51 测试 + 全量回归通过；曲线对照与开环对照已归档出图；**旧 checkpoint 重评未做**）
- **背景（两轮外部反馈）**：导师①"车速完全不符合预期，震荡太厉害"→ 开环对照（`verify_rong2025_openloop.py`）判别锅在控制器；②"装载缓释曲线也是错的"→ 定量诊断（`DIAGNOSTICS_2026-10.md`「修复-2026-10-11」）出旧模型根因：`tanh(s_dv/0.05)` 方向因子 × Stribeck 幅值**双重削减**，准静态 0.01 m/s 下摩擦只剩 19.7%，迟滞环面积仅为文献 1/5.3（23193 vs 62091 kN·mm）。
- **决策**：经用户确认，换用学姐推荐的**容嘉欣2025《更大牵引质量重载列车动力学建模与仿真分析》机械 52(7):57-64 图4(b) 货车 MT-2** 口径：
  1. **fl/fu 数字化查表**（400dpi 渲染 + 网格标定，读数误差 ±30 kN；fl(83mm)=2270 kN 锚定 MT-2 额定阻抗）；
  2. **速度法选支**：f0=(fl+fu)/2，f = f0 − sign(s_e·Δv)·(fl−fu)/2（加载→fl、卸载→fu、Δv=0→f0）；摩擦幅值不随速度衰减，只由方向选支（`dir_sm = tanh(s_e·dv/ε)` 平滑近似）；
  3. `friction_v_eps` 0.05→0.002（准静态 0.01 m/s 即 99.99% 分支分离）；NMPC 侧 `v_eps = max(ε, 0.05)` 下限保护 IPOPT。
- **连带修复（数值稳定性，唯一真 bug）**：`train.py::step_vehicles` 旧半隐式 Euler（dt=0.1）在新模型 0–10mm 段局部斜率 ~43 kN/mm（旧线性 18.9）下车钩链振荡指数发散（`test_grade_updates_with_position` 实证：3 步撞刚性限位爆炸）→ 改为 **≤0.01s 子步 + Newmark-β 隐式积分**，与 `step_vehicles_ed_ab` 同源，消除两条积分路径的稳定性差异。
- **测试基准重标定（3 项，均为新物理真实响应，非回归）**：
  - S4：−6‰ 缓坡缓解峰值 1248 kN = fl(47mm) 查表值（旧 659 kN 是 Stribeck 衰减失真产物）→ 断言 1000→1300 kN；
  - L1：拉钩力 1847/1553/1349 kN **反单调**（弱制动→缓解拉伸行程大→查表 fl 高段），旧"单调递增"是旧 Stribeck 模型标定 → 保留"峰值出现于缓解段"机理断言（L3）+ 量级区间 400–2200 kN；
  - decompose：缓解后 −2‰ 坡度 + Davis 阻力净减速 ≈ −0.01 m/s² 为真实物理 → 改"速度不塌缩（v>20 m/s）+ 缓解 15s 钩力 <300 kN"双断言。
- **验证**：装载缓释曲线对照（分支分离 772.4 vs 文献 772.5 kN；迟滞环 61894 vs 62091 kN·mm = **1.00×**，最大偏差 加载 20.9/卸载 7.9 kN）；容嘉欣图8/图9 开环对照重跑（归档 `rong2025_openloop_20261012_001654`）；全量 `pytest tests/ -q` 除既有 `outputs/deprecated/results_mpc_baseline/` 未登记外 **0 失败**。
- **影响与待办**：**旧 checkpoint 在新物理下数值不可直接引用**（两侧物理同源铁律），重评另案（用户已同意"随后"）；S4 主表"缓坡不超限"的 claim 措辞需按 1300 kN 新口径复核（实车 1000 kN 含液体缓冲器因素，仿真器纯 MT-2 摩擦缓冲器）。
- **相关**：`DIAGNOSTICS_2026-10.md`「诊断-2026-10-11-外部反馈两问」「修复-2026-10-12-装载缓释曲线」；ADR-011（MT-2 统一，不变）；ADR-018（断面力口径，不变）；`REFERENCE_INDEX.md` 容嘉欣2025 条目 + `docs/refs.bib` `rong2025_heavyhaul_dynamics`；产物 `outputs/sim_validation/figures/mt2_coupler/`、`outputs/sim_validation/phys_validation/mt2_load_release_cmp_20261012_001039/`。

## ADR-032 立论重构：废止"免重辨识成本"claim，改押"编队上下文协同增益"；主表四行（含 NMPC） - 2026-10-12

- **状态**：决策 + 已落地（`RESEARCH_POSITIONING.md` §1.6 覆盖式修订；`AGENTS.md` / `rules/EXECUTION_RULES.md` 免重辨识节 / `knowledge/MPC_BASELINE_KNOWLEDGE_BASE.md` / `REPRODUCIBILITY.md` 指针同步；`tasks.md` #9 关闭）
- **背景（grill-me 拷打会话，2026-10-12，用户亲自处决旧 claim）**：
  1. **成本差不可量化**：标定成本"人天清单表"无可靠可引出处；且**坡度图纸天然先于线路运营存在**（不存在"先通车再补测坡度"），同门指出 MPC 本无"缺坡度数据"问题——免重辨识的事实前提不成立；
  2. **叙事不算学术贡献**：省工程标定功夫是工程收益，不构成 research claim；
  3. ADR-016 删除 Regime B 后，claim 失去"MPC 不重辨识失配"这一（本就）不占篇幅的支撑，仅剩的成本叙事也塌了。
- **决策**：
  1. **废止** ADR-014/ADR-016 的"免重辨识成本"主 claim，连带废止 §1.6「标定成本量化口径」口径 1–4（口径 4 本就"不做"）。
  2. **新主 claim（M1，唯一必做）= 编队上下文协同增益**：面向长大下坡多列重载列车群组，**以编队为上下文**的机车级 MARL 协同调制，相比**列车独立决策**（编队上下文遮蔽消融组，新增训练）与 **D-Rule**，显著改善列距误差（spacing error）与速度带一致性，车钩力 ≤1000kN 落地率不劣化。
  3. **主表四行**：D-RL（独立）/ D-RL（formation）/ D-Rule / **NMPC**。NMPC 进表依据：① 领域标准方法（本地库先例 = Zhang & Zhuan 2014 ECP-MPC 开山、Lu2025 多机车协同 NMPC〔本项目基线来源〕、Yang2025 朔黄 NMPC 循环制动同场景、Liu2022 ATO）；② 导师点名。**Regime A 逐线公平标定协议（ADR-016）与 NMPC 唯一基线（ADR-022）不变**，但 NMPC 行**不承载 claim**——claim 证据来自消融列。同类论文调研佐证：同域重载/列车 RL 四篇（Zhang2024/Si2025/Wang2026/Hu2026）均不比 MPC；比 MPC 的先例 = Guo2025（道路车队，其场景标准控制器即 MPC）。
  4. **证伪与止损**：独立组先 **1 seed 冒烟**，编队增益（列距/速度带）不显著即止损（转降级策略：改 claim 或换对照），不烧满 5 seed 预算。
  5. **辅证储备（不入本轮 claim）**：**M2** = 跨线零微调 + 车辆参数变化泛化轴（`long_downhill_20km/35km` 剖面就绪后并入；导师范畴）；**M3** = 分层架构安全段（ATP 缺口 1/2 **主训练开跑前一次修**，见 `LITERATURE_FINDINGS.md` §4.3；架构叙述、不承载 claim）。
  6. **达标口径**：spacing error **±5%** / velocity error **±2%** 借 Hu2026（`Hu2026_PMMASAC_fulltext.txt:1234`）；主表安全指标 = ATP 触发次数（口径 SSOT = `LITERATURE_FINDINGS.md` §2）。
- **保留不变**：编队三底线（多列编队 + 车钩力 ≤1000kN + 安全列距）、单套 formation-aware RL 落位（ADR-013）、Regime A 公平标定（ADR-016）、NMPC 唯一基线（ADR-022）、D-RL 跨线严格零微调协议（降为 M2 储备）、安全不归功 MARL（ADR-014/021）、断面力口径（ADR-018）、训练/评估时域三维度（ADR-017）。
- **相关**：ADR-014（旧 claim 源头）、ADR-016（免重辨识 reframe + Regime A，协议部分仍生效）、ADR-022、ADR-013、ADR-030（claim 措辞收窄）；证据调研 = 2026-10-12 会话对比设计调研（本地 10 篇精读 + 网络 5 源）。

## ADR-033 真空白表述精确化 + Wang2025 归组修正 + 禁用"绝对首创" - 2026-10-13

- **状态**：决策 + 已落地（`RESEARCH_POSITIONING.md` §1.2 表行 28/30 与收窄注 33/35、`AGENTS.md` 立论段、`PROJECT_PIPELINE.md` 立论条 覆盖式修订）
- **背景（2026-10-13 首创性质疑会话，用户要求"只搜几个关键词"核验）**：
  1. 用户担心"多列群组 × 车钩力 × MARL 真空白"被夸大——做编组的工作物理模型里可能考虑车钩力但不写进 RL 目标；
  2. 5 组关键词网络检索 + 本地库一手反查，核验中发现 **§1.2 表自相矛盾**：行 28 把 Wang2025 与 Zhang2024/Liu2021 并列写"明确忽略车钩力"，但 `REFERENCE_INDEX.md:37` 与 `DIAGNOSTICS_2026-10.md:136/178` 一致记 Wang2025（ICIRT, DOI 10.1109/ICIRT66379.2025.11216684）车钩力**已进 reward 多目标**（拉 −9.64%/压 −28.77%）；
  3. 原文核对：那句 "interaction forces between cars are not taken into account" 仅出自 `Zhang2024_DQN_CyclicBraking_Downhill.txt:153` → **行 28 属误列**。
- **核验命中（边界全景）**：
  - **Song2026 MAPPO**（宋宗莹等，中国科技论文在线，`03_formation/Song2026_MAPPO_HeavyHaulGroup.html`）：**多列群组 + MARL**，但车钩力**不进奖励/指标**（奖励 = 势场安全引导 + 速度同步 + 牵引能耗；页面全文无"车钩/coupler"）→ **最接近的对手**；
  - Song2026 Tube-MPC：多列 + 车钩约束，但 MPC 非 RL；Wang2025 ICIRT / Wang2026 / Tang2020：车钩进 RL 目标，但单列；
  - 网络新初筛（未精读，标待核）：IEEE 11487264（虚拟耦合 MAPPO 制动）、MDPI Electronics 15-01823（高速虚拟耦合 MASAC）、IEEE 11245469（单列车厢级势场+DRL）——均无"多列+车钩进 RL 目标"证据。
- **决策**：
  1. **Wang2025 ICIRT 从"忽略车钩力"组移至边界组**（单列、车钩进 reward），引用误列修正；Liu2021 无本地一手，标注保留按同组引用；
  2. **真空白精确化为 "多列群组 × 车钩力进 RL 目标 × MARL"**（原 "× 车钩力 ×" 未区分"物理建模"与"进 RL 目标"，会被 Song2026 MAPPO 这类工作顶破）；
  3. **论文措辞纪律：禁用"绝对首创"，写"据系统检索未见"**（检索无命中 ≠ 不存在，证据纪律）；已知边界四篇（Wang2025/Wang2026 单列、Song2026 Tube-MPC 非 RL、Song2026 MAPPO 车钩不进目标）在 §1.2 主动引用划界；
  4. **安全三层归因维持不变**（ADR-014/021）：底线 ≤1000kN = 安全层（不归功 MARL）；MARL 安全价值 = 峰值更低 + 安全层介入频率更低（可量化，进消融对比）；列距/速度带 = 编队上下文 + MARL（主 claim 领域）。
- **相关**：ADR-030（claim 收窄源头）、ADR-032（主 claim）、ADR-014/021（安全归因）。

## ADR-034 论文对比体系定稿：三范式定义 + 主表重构（NMPC 退表 / Formation-MPC 进表）+ 不可主张清单 + 三项不加 + H1–H3 预注册 - 2026-10-13

- **状态**：决策 + 已落地（`RESEARCH_POSITIONING.md` §1.6 覆盖式修订、`AGENTS.md` 规范性问题段同步）
- **背景（grill-me 拷问会话续，2026-10-13，用户多轮挑战立论漏洞）**：
  1. 用户三连问："标准 RL 为什么做不到？其他虚拟编组论文怎么可能没有编队观测？我们是应用还是改进标准算法？"——暴露"标准方法"无定义、"唯一差别是编队观测"站不住；
  2. 一手核验：Wang2026 全文（动作空间 L660-690 / 奖励 L708-715 / 1100kN 三处措辞 L22/L1203/L1315）、刘博阳2022 信息卡、Zhang2024 约束集、Hu2026/Zhang2021 贡献段；
  3. 用户纠正两处我的错误：①"MPC 逐线标定=部署负担"违反 ADR-032 定稿（图纸天然存在）②"软通道无论文做硬机制"当**前人缺点**属拿我们的目标审判别人 = 稻草人；
  4. Wang2026 撞车发现：同 1+1 编组、同 ED 21 级离散 + AB 0/1 混合动作、同 f_c 进状态、同 AB 最小充风时间（已登记借鉴 Zhang2024）。
- **决策**：
  1. **"标准方法"= 三范式**（从事实文献推导，非主观定义）：①行业规则/驾驶规程（刘博阳2022 试闸判据 + 张二田2021 实测 + Zhang2024 循环制动血统）②模型优化（MPC/MILP：Fu2019 / Lu2025 / Song2026 Tube-MPC）③RL（单列 DQN/DDQN → 多列 vanilla MARL）。**"标准方法做不了"的精确表述**：不是算法不行，是四个场景硬需求（车钩硬底线 / 90s 充风时滞决策频率 / 编队上下文观测 / 异构动作）无一能被"原样泛化、零附加机制"满足。
  2. **主表重构（覆盖 ADR-032 决策 3 的"四行含 NMPC"）**：
     - **NMPC 退出主表**→ related work 文本，措辞"方法与场景不匹配，忠实复现不成立"（忠实复现解决不了本场景问题、改动则失去权威性——用户裁定自建变体无说服力）；
     - **新增 Formation-MPC 行**：following Song2026 虚拟编组 MPC 架构、**显式关掉车钩约束**（送编队自由度 = 防稻草人核心论据）；公允标定三条件 = 同仿真器 + 逐线喂坡度图纸（Regime A 公平标定协议，**非成本/劣势叙事**）+ 同档调参力度；**写作红线：只主张编队指标（列距/速度带）胜出，绝不主张车钩指标胜出**（他们缺的正是车钩约束，赢车钩是废话）；
     - **最终主表**：D-Rule / 单列 RL 范式行 / Formation-MPC / D-RL(formation) + **D-RL(独立) 消融列（claim 唯一承载）**；防守句式 "all comparisons hold the algorithm fixed to isolate the contribution of the formation-aware formulation"。
  3. **贡献表述去首创化公式**（四篇一手文献核验，无一篇用"首次/first/to the best of our knowledge"）："机制 + 与具体基线对照（Unlike / Compared to / 与XX基准相比）+ 量化收益"；ADR-033 决策 3（禁"绝对首创"、写"据系统检索未见"）不变。
  4. **Wang2026 撞车清单（不可主张，写作红线）**：机车级 ED/AB 分工、车钩进状态/奖励、AB 最小充风——**均不得写为创新点**；可主张 delta 收敛为两条 = **多列群组 MARL + 硬保证通道（安全层）**（与 ADR-033 真空白边界吻合）。
  5. **承诺等级论证的定位**：软承诺（"Simulation results demonstrate that..."——证据挂靠 runs：Wang2026 摘要/结果/结论三处均如此）vs 硬承诺（证据挂靠机制：约束写进优化 / 安全层 by construction）——**只用于解释我们自己为什么加安全层，不作前人缺点**（前人从未承诺硬保证，批评其"没机制"= 稻草人，用户裁定）。**前人缺点收敛为一条**：前人局限于单列场景，无人在多列车组层面处理车钩力（描述性空白，衔接 ADR-033）。
  6. **规则层定位与措辞**：血统 = 文献锚定（三把闸/试闸判据：刘博阳2022 §二、张二田2021；浅档分级对齐"最小常用制动"）+ 自研调参（ADR-026 原话）+ 三条闭环反馈分支（接近上限预缓和 / `SafetyLayer.protect()` / AB 禁新增源 veto）为我们所加；措辞只许 **"literature-anchored rule baseline"，禁 "industry standard"**。规则范式盲区的文献论据 = **刘博阳2022 §3**：三列车试闸判据全过、列尾压强差 8 kPa（司机不可感知），第一把闸缓解时最大拉钩力 742→1337 kN（+80%）——代理判据与车钩力真值之间的结构性盲区。
  7. **三项不加（实验裁剪）**：
     - **不做安全层关断消融**（用户否决）：规则层/安全层非贡献物，不证价值；纯 RL 直控 1439 kN 失败实证（`src/controllers/low_level_controller.py` L75-L79 注释）仅作架构动机文字；
     - **不加外部 MARL 算法行**：自建外部实现 = 稻草人风险（用户已用同一逻辑枪毙自建 NMPC 变体）；Song2026/Zhang2021 基线均为自己 vanilla 版或更弱方法，领域无外部算法行标配；防守句式替代，审稿人点名时 revision 补；
     - **不加单智能体参照行**：裸比混淆四变量（信息量 / 联合动作探索难度 / 奖励结构 / 网络容量），归因不干净；why-MARL 用结构性论证（分散执行可部署性 + 逐机车信用分配 + 规模可扩展性）；revision 预案同上。
  8. **分维度对比结构**：多列编队 × 车钩主表与单列车钩维度**分开，不跨维度合并**；**单列车钩附录 = 防御展品**（对照 Wang2026/Tang2020 软通道形态：f_c 仅状态编码 + reward 加权、无安全层；只作架构形态对照与承诺等级说明，**无胜负主张**）——防"你们单列车钩不如软通道方法"攻击（三篇编组论文基线全是算法，无人与单列比）。
  9. **H1–H3 预注册（预期效果可证伪化）**：**H1** formation 观测相对独立观测，列距违规/列距误差显著下降；**H2** 两组车钩超限 = 0 且 formation 峰值更低（MARL 安全价值 = 峰值更低 + 安全层介入频率更低，ADR-033 决策 4 口径）；**H3** 旅行时间/能耗不劣于 D-Rule（安全不以效率崩塌为代价）。达标口径 ±5%/±2% 借 Hu2026（ADR-032 决策 6 不变）。
  10. **写作组装项**：论文加"前人效果量化表"（Wang2026 1100kN/均值 72.82/−105.91 kN、Song2026、Hu2026、Zhang2024；数据已在 `REFERENCE_INDEX.md` 与 §1.2，纯组装活）。
- **保留不变**：编队三底线与单套 formation-aware RL 落位（ADR-013）、Regime A 公平标定协议（ADR-016，**成本叙事仍废止**）、断面力口径（ADR-018）、训练/评估时域三维度（ADR-017）、主 claim = 编队上下文协同增益 + 1 seed 冒烟止损（ADR-032）、真空白表述与安全三层归因（ADR-033）、受控超限项（ADR-021）。
- **相关**：ADR-032（主 claim 与四行主表的被覆盖方）、ADR-033（真空白边界 / 禁首创）、ADR-016（Regime A）、ADR-026（规则层自研调参出处）、ADR-013（两层 RL 废止背景）。

### ADR-034 补录（2026-10-13 同日）—— Song2026 MAPPO 全文入库，三项核验 + 决策 5 的动机锚升级

- **触发**：用户下载宋宗莹2026 原文全文 PDF（20 页，中国科技论文在线 DOI 10.61951/SciencepaperOnline.202605.0114），已重命名入库 `docs/papers/03_formation/Song2026_MAPPO_HeavyHaulGroup.pdf`（`.html` 保留为旧摘要页存档），三处登记（papers/README、REFERENCE_INDEX、refs.bib）同步。
- **一手核验（此前仅凭 HTML 页面，现升级为全文一手）**：
  1. **奖励 = 三段加权**（§2.2：cooperative tracking + safety potential field guidance + operational energy efficiency，式 6/7/8），**无任何车钩项**——"车钩力不进目标"由 PDF 全文坐实（中文"车钩"0 命中；safety reward = 势场 U(d)，只管间距）；
  2. **基线 = 标准 MAPPO 基准**（摘要"与标准的多智能体近端策略优化基准相比"），全文**无消融**（"消融"0 命中）、**无安全层**（"安全层"0 命中）——决策 7 中"领域无外部算法行/消融标配"的判断进一步坐实；
  3. **⚠️ 决定性发现（动机锚升级）**：其 Introduction 自述挑战 1 原文——*"classic RL relies on the 'soft constraints' of reward functions, **which cannot mathematically guarantee hard physical constraints such as coupler forces**. In exploration phases or Out-of-Distribution (OOD) scenarios, this can easily lead to prohibited actions, violating the 'Fail-Safe' criterion of industrial control."*
- **对决策 5 的影响（不推翻，升级）**：仍不将"软通道无硬机制"写作前人缺点（对方未作硬承诺），但**"硬保证通道"delta 的动机锚从"我方自述"升级为"最接近对手自述的领域公认挑战"**——论文写法：引 Song2026 自述挑战 1 作动机（引用其承认的 open problem，非批评其工作），再给我们的确定性安全层作答。**零稻草人风险**：对手论文自己说软约束不行，我们补硬机制 = 应答而非审判。
- **状态**：证据补录 + 登记完成；决策 1–10 均不变。

## ADR-035 研究对象编组对齐朔黄线实际运营：万吨首/尾 1+1 → 2 万吨头/中部 1+1（`20kt_1plus108_1plus108`）- 2026-10-13

- **状态**：决策 + 已落地（主训练 YAML、`RESEARCH_POSITIONING.md` §研究对象/§1.1/§1.4、`AGENTS.md`、`evaluate_decompose.py`、`test_physics_governance.py`、`physics_governance.py` 注释同步）
- **背景（学姐建议 + 调查核验，2026-10-13）**：
  1. 学姐意见 = "最好用现实中已经在运营的编组模式"；用户问"头尾 1+1 可以吗"。
  2. 调查结论（一手 = `张二田2021_朔黄2万t车钩力_fulltext.txt` + `Zhao2022` 全文 + `Zhang2024_DQN` 全文 §4.1 + 网络核实）：**朔黄线实际运营编组 = 头车 + 108 C80 + 中部车 + 108 C80 + 可控列尾（2 万吨「1+1」，2016 起常态化、破 10 万列）**；3 万吨「1+1+1+1」= 4 机车（头+中×2+尾，2025 常态化）。**"头尾双机车、无中部机车"的万吨编组在朔黄线无运营先例**（尾部补机仅见于宝成秦岭/嫩林线等区段临时加挂）。
  3. **同类论文编组逐位一致**：Zhang2024 DQN（"1 HXD1 + 108 freight cars + 1 HXD1 + 108 freight cars"）、Zhao2022（同型「1+1」）、张二田2021（实车同型）——我们原 `10kt_1plus1`（1+94+1 头尾）与全部对标文献不同构，审稿可质疑编组真实性。
- **选项与权衡**：① 每列 2 万吨头/中部（逐位对齐文献，立论 SSOT 研究对象改口径）② 保留万吨仅移机车到中部（改动最小但吨位仍无运营先例）③ 先冒烟后改文档。**用户拍板 = ①**。
- **结论**：主训练编组切 `consist_preset: 20kt_1plus108_1plus108`（预设已存在，`train_env.py:73`，原为编组规模效应验证而建）；每列 = 头/中部双机车（index [0,109]）+ 216 货车 ≈ 21976 t（与张二田实车 21600 t 同量级）；3 列群组 = 6 机车智能体不变（`loco_indices` 从编组定义动态推导，decompose/观测/奖励结构零代码改动）。
- **后果（⚠️ 执行影响，均待重跑）**：
  1. **旧 checkpoint 全部失效**（编组规模/观测归一化随编组变），主训练须重跑；YAML 其余参数（curriculum/γ/BC/long_eval）暂不动，冒烟若发散再按 ADR-017 调参纪律处理。
  2. **物理量级变化**：单列 2 万吨循环制动车钩力实测锚 = 均值 1021 kN / 峰值 1429 kN（张二田 S1）——预期超限频率上升，安全层介入更频繁；这反而**强化**"车钩力在长大下坡群组中不可忽略"的立论。
  3. **术语联动**：论文"1+1"从此**双义须区分**——单列内部 = 朔黄实际运营组合列车（头+中部机车）；列间 = 虚拟耦合群组（本项目编队对象）。
  4. `20kt_1plus1_validation`（赵紫宁参数版）保留作验证专用，不作研究对象；`10kt_1plus1` 预设保留（历史 runs 复现用），不再作主实验。
- **SSOT 联动**：`RESEARCH_POSITIONING.md` 研究对象行 / §1.1 / §1.4 已覆盖式修订（动机存本 ADR）；`AGENTS.md` 研究对象行同步；日志类（DIAGNOSTICS/PROGRESS/LEARNINGS 历史条目）按 append-only 不改。
- **相关**：ADR-009（智能体分解重构，1+1 起源）、ADR-013（RL 落位不变）、ADR-017（重训时域纪律）、张二田2021（编组与实车锚）、Zhang2024（对标编组）、Zhao2022（同型编组）。

## ADR-036 2 万吨车钩力指标档位化：1000（正常运行/优化目标）/ 1500（制动工况验收）/ 2250（安全硬顶） - 2026-10-14

- **状态**：决策 + 文档层已落地；代码门限（安全层 enforce、reward limit）为**待执行项**
- **背景**：研究对象切 2 万吨（ADR-035）后，原"车钩力 ≤1000 kN = 不可逾越底线"对 2 万吨长大下坡循环制动场景是否合适需复核。用户指出"指标须看编组与场景，不能直接和 Song2026 比"——**正确**：Song2026 用弹簧-阻尼钩缓模型（无 MT-2 迟滞/游间）、完整运行周期场景、编组参数不同源，其 ±1000 kN 只能作"文献存在以 1000 为控制目标"的事实背书，**不进指标论证链**。
- **证据结构（场景匹配一手源，全部为 2 万吨）**：
  1. **靳新元2018**（朔黄公司，2 万 t 动态试验，编组与 `20kt_1plus108_1plus108` 同款）§2.2.1 评定指标**分工况分档**：常用/全制动 ≤1500 kN；正常运行 ≤1000 kN；从控机车偏转角 ≤6°；安全性评定 ≤2250 kN。
  2. **张二田2021**（朔黄 2 万 t，19 趟）：长大下坡峰值均值 1021 / 最大 1429 kN，**11/19 超 1000 但 <1500**；≤−7‰ 缓坡全程 <1000（R3）。
  3. **王鼎2023**（大秦线 2 万 t，46 趟）：正常运行最大车钩力恒 < 安全限值 2250 kN。
  4. **Fu2019**：1000/2250（正常/紧急）两档，与靳新元分档同族互证。
  → 一致结论：**1000 kN 是正常运行档判据，不是制动工况判据；制动工况运营判据 = 1500 kN，绝对安全顶 = 2250 kN**（MT-2 钩缓饱和 2270 kN@83mm 为物理顶，与之吻合）。
- **选项与权衡**：① 维持 1000 全工况硬顶（比运营标准严；规则层应力窗实测峰 2000–4800 kN，−9.4‰ 循环制动下达不到，硬压只能牺牲速度带 → 速度带指标崩）② 弃 1000 只用 2250（安全叙事弱化、失文献可比性）③ **档位化**：1000 保留为优化目标/正常运行指标，制动工况验收改 1500，安全层硬执行顶格 2250（对齐运营标准 + 实车锚）。**用户拍板 = ③**。
- **结论**：指标论证链只锚 靳新元2018 + 张二田2021 + 王鼎2023 + Fu2019；Song2026 不进指标论证链，论文与其对比（Formation-MPC 行）须显式声明车钩模型/工况/编组差异。编队目标三件套措辞相应档位化，"≤1000 kN"表述必须带工况档限定。
- **后果（⚠️ 执行影响）**：
  1. **代码待改**（不在本 ADR 内执行；须与编队线负责人同步 + train.py 物理联审）：安全层 `enforce_coupler` 门限 1000→1500（制动工况）+ 2250 顶格；reward `peak_norm` 的 `coupler_force_limit_n` 常量与超限项阈值随之。**调整前训练/评估仍按旧 1000 门限跑，两档结果不得混比**。
  2. 单列车钩力训练计划验收线：≤900 kN（1000 留 10%）→ **≤1350 kN（1500 留 10%）**，同时报告 1000 档（正常运行目标）达成率。
  3. 论文措辞：不得暗示"2 万 t 实车制动恒 ≤1000"（张二田实车直接反证）。
  4. `RESEARCH_POSITIONING.md` §1.5（底线 + 车钩力定位）与 `AGENTS.md` 对应条目已就地修订（动机存本 ADR）。
- **SSOT 联动**：`RESEARCH_POSITIONING.md` §1.5；`REFERENCE_INDEX.md`（新增靳新元2018 行 + bibtex key + 三处登记）；`docs/papers/01_coupler_physics/靳新元2018_朔黄2万t长大下坡车钩受力.md`（新建卡）；`docs/refs.bib`（`jin2018_shuohuang20kt`）；`.trae/documents/single-train-coupler-rl-plan.md`（验收线）。
- **相关**：ADR-014（车钩力定位）、ADR-018（断面力口径）、ADR-021（超限非线性项）、ADR-035（2 万吨编组切换——本 ADR 为其指标配套）。


## ADR-037 废止 MPC"逐线重喂坡度图纸 + 在线标定 b0"对比协议（Regime A），对比口径改为同环境同数据同调参 - 2026-10-16

- **状态**：决策 + 文档层已落地（AGENTS.md / RESEARCH_POSITIONING.md §1.5/§1.6 / 
ules/EXECUTION_RULES.md / knowledge/MPC_BASELINE_KNOWLEDGE_BASE.md / knowledge/TRAIN_DYNAMICS_KNOWLEDGE_BASE.md / REPRODUCIBILITY.md / docs/README.md / papers/LITERATURE_FINDINGS.md 覆盖式修订；历史日志 logs/progress/ logs/diagnostics/ ppt_talk/ 原样保留仅作历史）
- **背景（2026-10-16 用户裁定）**："MPC 每条线喂正确坡度图纸（逐线重喂 grade_at + 在线标定 b0）"这类表述**已被证实是错误观点，极易误导**，须全仓剔除而非仅改单个文档。ADR-032 已证伪其前提（坡度图纸天然先于运营存在，MPC 本无"缺坡度数据"问题），但 Regime A 协议文字本身（ADR-016）仍残留在立论/执行/知识库多处，本轮一并废止。
- **决策**：
  1. **废止 Regime A 协议本身**（ADR-016），不再有"逐线重喂 grade_at/在线标定 b0/逐线公平标定"任何协议或表述；"免重辨识成本"叙事维持 ADR-032 废止状态（不复活）。
  2. **当前 MPC 对比口径**：所有方法共用同一仿真器、同一环境与坡度数据、同档调参力度；坡度是 MPC 预测模型的**固有输入**（=命令+g·坡度+b0，图纸天然先于运营存在），既不作为"给足信息的优势"也不作为"重标定的劣势"叙事。
  3. **D-RL 跨线严格零微调**（"no fine-tuning on target line"）不变，作为 M2 储备协议继续有效。
  4. **历史不追改**：logs/progress/、logs/diagnostics/、ppt_talk/report_*/OUTLINE.md 等历史/演示产物按 append-only 保留原文字；仅当前立论与执行口径文档覆盖式修订。
- **后果**：EXECUTION_RULES.md 第 4 条"protocol 标注 re-identification"的标注要求随协议废止不再执行；MPC 基线代码 NMPCController 的 grade_at 读入行为不变（本就是固有输入），仅文档口径变更，**无代码改动**。
- **相关**：ADR-016（被本 ADR 废止）、ADR-010（Regime A/B 原出处）、ADR-032（成本叙事废止，前提证伪）、ADR-034（Formation-MPC 公允三条件中的"逐线喂图纸"表述由本 ADR 修正）。

## ADR-038 主对比表移除"单列 RL 范式行" - 2026-10-17

- **状态**：决策 + 文档层已落地（RESEARCH_POSITIONING.md §1.6 / AGENTS.md / docs/tasks.md / docs/杂项 两份对位文档覆盖式修订或加注；历史日志 logs/ 原样保留仅作历史）。
- **背景（2026-10-17 用户裁定）**：ADR-034 主表含"单列 RL 范式行"（预期 = 按 Zhang2024 论文设计在本仿真器上实现的单列 RL）。用户裁定移除，理由：本项目并未复刻该文献实现；若以自研网络逐列单独训练充当该行，本质 = 本方法拆掉协同成分，与 D-RL(独立) 消融列高度重复（一个遮编队观测、一个连训练都分开），**行标签与实现对不上，比少一行更糟**；与 NMPC 退表同理，自建变体无说服力。
- **决策**：
  1. **主表结构改为**：D-Rule / Formation-MPC / D-RL（formation）+ **D-RL（独立）消融列（claim 唯一承载，不变）**——由四行降为三行 + 消融列。
  2. **文献单列 RL（Zhang2024 / Liu2021 / Wang2026 等）降为 related work 文本**：只作范式描述与边界对照（措辞纪律沿 ADR-030/034："据系统检索未见"、不可主张清单不变），不占主表行、不作为可比基线实现。
  3. **RL 范式的现场代表 = 本文 D-RL 自身**；why-MARL 仍用结构性论证（ADR-034 三项不加不变）。
  4. **历史不追改**：logs/progress、logs/diagnostics、杂项讨论记录等历史/流水产物按 append-only 保留原文字；仅当前立论与口径文档覆盖式修订。
- **后果**：H1–H3 预注册、防守句式 "all comparisons hold the algorithm fixed..."、Formation-MPC 写作红线（只主张编队指标）均**不变**；对比实现工作量减少（无需实现单列 RL 行）；**无代码改动**。
- **SSOT 联动**：`RESEARCH_POSITIONING.md` §1.6（主表结构 / 主 claim 基线列举 / 主对比结构三处）；`AGENTS.md` 主表条目；`docs/tasks.md` 第 9 条；`docs/杂项/项目介绍和问题简述.md`（主对比行）；`docs/杂项/文献整理_论文方向讨论_20261016.md`（追加注记）。
- **相关**：ADR-034（原主表结构，被本 ADR 部分修订）、ADR-032（主 claim 不变）、ADR-030（文献边界措辞不变）、ADR-034 NMPC 退表裁定（同一逻辑：自建变体无说服力）。

## ADR-039 主研究编组改为三列万吨级1+0单元 - 2026-10-17

- 用户确认：每列1机车+108货车，三列共3个机车智能体；覆盖ADR-035的当前研究对象，保留历史两万吨试验。
- 预设 `10kt_1plus108`：沿用当前188t机车、100t货车参数，每列10988t，109辆；不是精确10000t，也不声称车型参数已与文献逐项对齐。
- 当前主配置：`configs/experiments/formation_ed_ab_3train_1plus108.yaml`。旧1+0的100节预设和两万吨配置保留，不改变其语义。
- 49.6km线路、单套formation-aware机车级ED/AB架构保留；新结果与旧两万吨资产隔离。旧6智能体权重不可直接作为新3智能体模型恢复。
- 继承的初速、充风时间、课程参数、安全门限均非新编组已验证结论；不按吨位自动缩放门限。先做单列、三列原生接口与底层规则验证，再训练。本文决策不证明该编组符合实际运营许可。


## ADR-040 万吨三列方案车钩力统一验收指标恢复1000kN - 2026-10-17

- 用户明确要求“指标换回1000kN”；覆盖ADR-036在当前ADR-039研究方案中的1500kN制动验收口径。
- 当前主配置 `formation_ed_ab_3train_1plus108.yaml` 显式设置 `env_cfg.coupler_force_limit_n: 1000000.0`，避免依赖默认值。该值传至列内环境、机车控制器、奖励归一化和超限统计；断面力绝对值峰值按1000kN验收，超过即未达标。
- 不再将1350/1500kN作为当前方案的通过标准。不额外引入900kN强制验收线；预留裕量若作诊断须另行注明。
- 本次改变验收指标，不将紧急保护触发阈值自动改为1000kN；紧急保护与验收是不同语义。安全层存在不代表1000kN已得到数学或实验保证。
- 旧两万吨配置、原始结果与历史档位原样保留，仅作历史，不能据其峰值声称当前方案通过。当前万吨三列效果须重新验证。

## ADR-041 实验矩阵单列维度全线移除（单列车钩附录废止 + 单列 RL 训练线终止） - 2026-10-18

- **状态**：决策 + 文档层已落地（RESEARCH_POSITIONING.md §1.6 / AGENTS.md / docs/tasks.md / HANDOFF_2026-10-17.md P3 加注 / `.trae/documents/single-train-coupler-rl-plan.md` 头部标终止；历史日志 logs/ 与 ADR 原文 append-only 不改）。
- **背景（2026-10-18 用户裁定，承接 2026-10-17 学长指导）**：学长指导第 6 条明确"三列必须基于群体跑（要基于定义），**没有必要做单列 RL**"；第 8 条指出应关注**群组运行的协同优势**而非车钩力单列表现。ADR-038 已移主表"单列 RL 范式行"，但实验矩阵仍残留两处单列项：① ADR-034 决策 8 的"单列车钩附录（防御展品）"；② 单列车钩力 RL 训练任务线（`.trae/documents/single-train-coupler-rl-plan.md`，其定位"充当主表单列 RL 范式行 + 与队友编队策略拼接"已被 ADR-038 与学长指导双重否定）。用户裁定：单列的东西全部移出实验矩阵。
- **决策**：
  1. **单列车钩附录（ADR-034 决策 8 防御展品）废止**：论文不再设"单列车钩维度"分册；对"单列车钩不如软通道方法"类攻击的防线改为 related work 文本（承诺等级说明，沿 ADR-034 决策 5 口径：软/硬通道只解释自家架构）+ 不可主张清单，不占实验与篇幅。
  2. **单列车钩力 RL 训练线终止**：`single_20kt_coupler_rulecal.yaml` 不再作 RL 训练入口（`run_training.py` 单列开训不再执行）；该线两个既有目的（充当单列 RL 范式行 / 单列策略与编队策略拼接）均不成立——编队上下文由 formation 主线一体承载（ADR-013），单列 RL 无落位。
  3. **明确保留（非实验矩阵项）**：**单列场景作为规则层标定试验台**（`rule-layer-operating-calibration-plan.md` P0–P3、A–AG 轮继续有效）——被标定的列内规则循环制动为编队线共用资产，标定属工程前置非论文实验；`single_20kt_coupler_rulecal.yaml` 保留为该标定专用配置（三列 1+108 方案的对应配置见 ADR-039 的 `single_10kt108_coupler_rulecal.yaml`，以队友落地为准）。
  4. **不变**：文献单列 RL = related work 文本（ADR-038）；D-RL（独立）消融列 = 多列独立决策，非单列，不变；H1–H3、防守句式、Formation-MPC 红线不变。
- **后果**：对比实现工作量进一步减少（无单列 RL 训练、无单列附录）；HANDOFF_2026-10-17 P3 待办中"single_20kt 开训实测"一项作废，P2 规则层标定达标后的下一 RL 训练 = formation 主线（三列 1+108，ADR-039）；**无物理与代码改动**（配置文件保留，仅用途降级）。
- **SSOT 联动**：`RESEARCH_POSITIONING.md` §1.6（分维度对比结构句覆盖修订）；`AGENTS.md`（最新 ADR 指针 + 主表条目补注）；`docs/tasks.md` 第 9 条；`docs/HANDOFF_2026-10-17.md` §6 加注；`.trae/documents/single-train-coupler-rl-plan.md` 头部标终止。
- **相关**：ADR-038（主表移除单列 RL 行，本 ADR 为其收尾）、ADR-039/ADR-040（三列 1+0 编组与 1000 kN 验收，本 ADR 落地时已合入 develop）、ADR-034（决策 5/8，被本 ADR 部分修订）、ADR-013（唯一 RL 落位=formation-aware，本 ADR 的立论依据）。

## ADR-042 废除独立消融列，核心命题改为相对传统基线的编队指标收益 - 2026-10-19

- **状态**：决策 + 文档层已落地（`RESEARCH_POSITIONING.md` §1.6/§1.5 覆盖修订、`AGENTS.md`、`docs/PROJECT_PIPELINE.md`、`docs/杂项/项目介绍和问题简述.md`、TRAIN_ENV_SAFETY / MPC_BASELINE 知识库、`docs/rules/EXECUTION_RULES.md`、`docs/REPRODUCIBILITY.md`、`ppt_talk/midterm_20261018/OUTLINE.md`；历史日志与旧版 PPT 归档不改）。
- **背景（2026-10-19 用户拍板）**：原核心 claim"编队上下文协同增益"（ADR-032）以 D-RL（独立）消融列为唯一证据承载。用户裁定废除独立消融，理由：① **真实运营场景不存在"三列群组各自独立运行"的工况**——虚拟编组的业务前提就是协同运行，独立组不是真实可对照的运行模式；② 独立消融把研究命题强行从"多列协同控制优于传统方法"扭到"编队信息增益分解"，偏离工程命题、说明不了核心问题。同期实验矩阵最终版确定：主对比场景**物理关闭车钩力**、只比编队指标；基线明确为 Tube MPC（Song2026 管式预测控制架构，即 ADR-034 之 Formation-MPC 的具体形态，车钩约束显式关闭）；跨线泛化升格为正式组别。
- **决策**：
  1. **废除 D-RL（独立）消融列**：退出实验矩阵，不再作为 claim 证据；观测屏蔽的代码能力保留（工程开关），不进论文主实验；被审稿人要求时的回应预案 = "真实运营无此运行模式，对比聚焦传统基线横向比较"（结构性论证，revision 预案，不作主表行）。
  2. **核心 claim 覆盖修订**：由"编队上下文协同增益（消融承载，ADR-032）"改为**"相对传统基线的编队指标收益"**——formation-aware 机车级 MARL 相比规则基线（D-Rule）与 Tube MPC，显著改善列距保持与列间速度差收敛；车钩力 ≤1000 kN 由安全防护架构保证，**不作对比胜出主张**。
  3. **主对比场景物理关闭车钩力**：三方法在关闭车钩力物理的同一剖面上只比编队指标（列距、列间速度差）；车钩力验收由本方法安全架构（规则循环制动 + 安全防护逻辑）与前期方案 49.6 km 全程评估（峰值 956 kN，须带"前期方案"标注，ADR-039 隔离令）承载，不进主对比评估。
  4. **跨线泛化升格正式组别**：训 49.6 km → 测 35 km（域外真实剖面），本文方法严格零微调（原 M2 储备并入矩阵）。
  5. **H1–H3 预注册覆盖**：H1 = 主对比列距保持优于两基线；H2 = 列间速度差收敛优于两基线；H3 = 跨线泛化性能保持（劣化有界）。原 ADR-034 的 H1（formation vs 独立）/H2（车钩超限对比）随消融废除一并废止。
  6. **证伪与止损更新**：废止"独立组 1 seed 冒烟"条款；新止损 = 主对比不优于规则基线时，先迭代规则层参数与奖励设计再重评。
  7. **"三项不加"沿革**（ADR-034）：安全层关断消融、外部 MARL 算法行、单智能体参照行仍不加，登记 revision 预案。
- **后果**：对比实验工作量下降（少一组同规模训练/评估）；claim 证据结构简化为"与两类传统基线对比 + 跨线保持"；"编队上下文"保留为方法设计概念（观测与 formation-aware 命名不变），不再作增益分解主张。
- **SSOT 联动**：`RESEARCH_POSITIONING.md` §1.6（覆盖修订）/§1.5（主对比结构、主指标）/§1.4 研究问题句；`AGENTS.md`（MPC 对比口径行 + 车钩异构行）；`docs/PROJECT_PIPELINE.md`；`docs/杂项/项目介绍和问题简述.md`（实验矩阵表 + 核心观点）；`docs/knowledge/TRAIN_ENV_SAFETY_KNOWLEDGE_BASE.md`、`docs/knowledge/MPC_BASELINE_KNOWLEDGE_BASE.md`；`docs/rules/EXECUTION_RULES.md`；`docs/REPRODUCIBILITY.md`。
- **相关**：ADR-032（旧 claim，被本 ADR 覆盖）、ADR-034（主表结构/H1–H3，被本 ADR 覆盖修订）、ADR-037（MPC 公允三条件，继续有效）、ADR-039/ADR-040（编组与 1000 kN 验收，继续有效）、ADR-041（单列维度移除，本 ADR 延续其矩阵收敛方向）。

## ADR-043 编队奖励重构 v6：13 项收敛为 6 个文献槽位，删车钩均值项 - 2026-10-20

- **状态**：决策 + 文档层落地（本 ADR / `knowledge/TRAIN_ENV_SAFETY_KNOWLEDGE_BASE.md` §4/§6 / `REFERENCE_INDEX.md` / `logs/diagnostics/DIAGNOSTICS_2026-10.md`）；代码改动（`src/environments/train_fleet_env.py` + 2 测试文件）随本 ADR 同批落地。
- **背景（2026-10-20 用户拍板）**：编队线奖励经历次训练事故补丁累积至 13 项，远超同类编队 RL 文献（本地 8 篇 + 网络补 5 篇精读，普遍 3–5 项目标项，约束下沉动作空间/安全层）。用户要求按文献槽位收敛。**Wang2026 一手 PDF 复核结论**：其车钩项 `Rf = −exp(−f_c,max/F_c,max)` 原文确为如此（此前"疑 OCR 漏 `(1−)`"的判断被一手证据推翻），该式 `f` 越小罚越重、单调方向与"车钩力约束"目的相反，**不可照抄**。
- **决策**：
  1. **速度槽**：领航列带内由"中心峰 `+6·(1−0.9δ)`"改**平顶 `+5`**（对齐 Zhang2024 式22 `Rd=+5`）；带外比例罚与超速硬罚**保留不合并**——复核算得"并入"会把超速罚由约 −8.6 削至约 −3.6 /(m/s)，与 v1"贴上限超速"教训冲突。
  2. **跟随列槽**：相对速度镜像 + 绝对线速兜底保留（Guo2025 leader/follower 异构奖励有先例）。
  3. **间距槽**：效率项 + 危险项保留（ADR-026 两段式；形状与 Song2026 倒数势场、Hua2024 ReLU 近距罚同型）。
  4. **车钩槽**：**删均值项** `−0.2·mean(obs[:,5])`（无文献锚，且口径为每车净力 ≠ 断面力 SSOT）——**部分推翻 ADR-021"不动 mean 权重"**；峰值比项改 **`−w_f·(1−exp(−p̂))`**（取 Wang2026 式17 同型有界饱和形、修正其单调方向），与 ADR-021 超限项 `−6·min(p̂−1,2)` 并联。
  5. **删 a² 项**（原误标"舒适"）：文献一致用 `jerk²`，且 Song2026 明写 jerk 与车钩力变化率直接相关——jerk 是车钩力的代理，本项目已直接量测断面力车钩力，**不加 jerk**（代理冗余）。
  6. **删追尾趋势罚与追尾硬罚**：危险项 `−60·õ²` 已不封顶；文献对碰撞的普遍处理 = 大罚 + 终止。
  7. **电空分工槽保留**：AB 需求罚锚由 Zhang2024 式22 补强为 Wang2026 式16 `Rb` 充风约束（与本项目 obs[11] 充风就绪度 ADR-030 同源）；ED 微成本保留。
- **后果**：`REWARD_SCHEMA` v5 → **v6**；v5 与 v6 结果**不可比，须重训**；奖励由 13 项收敛为 **6 槽位**（领航速度 / 跟随速度 / 间距效率 / 间距危险 / 车钩 / 电空分工）；新参数（平顶 `+5`、峰值比权重 `w_f`）随重训标定。历史 v5 归档与日志 append-only 不改。
- **SSOT 联动**：`knowledge/TRAIN_ENV_SAFETY_KNOWLEDGE_BASE.md` §4（奖励构成表 / 车钩项行）+ §6（奖励叙事）；`REFERENCE_INDEX.md`（新增"公式借鉴"行）；`logs/diagnostics/DIAGNOSTICS_2026-10.md`（改造记录）。
- **相关**：ADR-021（mean 权重被本 ADR 部分推翻；超限项及其上界 −12 保留）、ADR-026（间距两段式保留）、ADR-028（危险项穿透有界化保留）、ADR-014 / ADR-018（车钩力定位与断面力口径不变）、ADR-030（AB 充风就绪度观测）。

## ADR-044 立论级事实单一副本 + 渲染覆盖 + 临时工具文档豁免 - 2026-10-20

- **状态**：决策 + **已落地**（台账 `docs/CLAIM_LEDGER.yaml`、守卫 `scripts/check_claim_ledger.py` / `scripts/render_claims.py`、负结果台账 `docs/logs/verification/NEGATIVE_SEARCH_2026-10-20.md`、SSOT `RESEARCH_POSITIONING.md` §1.2/§1.6 覆盖修订、`AGENTS.md` 指针、`docs/README.md` 登记）
- **背景（2026-10-20 核验会话）**：用户指出"文献表述错误伴随项目几乎整个生命周期"，定性为**项目级失误、影响全部立论**。核验确认 Song2026 Tube-MPC **显式建模车钩力**（多质点动力学含车钩力、多目标代价含车钩力抑制、约束 ±1500 kN、长大下坡工况、峰值 330.4 kN = 限值 22%，本地全文 `docs/papers/03_formation/Song2026_TubeMPC_fulltext.txt:23-26 / 28-32 / 1400-1406`），据此全仓 16 处"无车钩力建模"类表述作废（**属文献事实纠错，不涉立论变更**）。
- **根因（6 条，均有留痕证据）**：
  1. **R1 否定命题用最弱证据**：ADR-033 据 `Song2026_MAPPO_HeavyHaulGroup.html`**摘要页**断言"页面全文无车钩/coupler"；
  2. **R2 全文入库未回验**：`REFERENCE_INDEX.md:51` 记全文 2026-10-13 入库，该判断未按全文复核；
  3. **R3 知识未传导（最严重）**：`DIAGNOSTICS_2026-10.md:1227`（10-07）已记"Song2026 TubeMPC 建模车钩力=是（±1500 kN）"，6 天后 ADR-034 仍写"无人在多列车组层面处理车钩力"，§1.2 至今写"几乎空白"；
  4. **R4 关键词偏置**：检索以 coupler 为中心，摘要用 `in-train force` 的 CCDC2025 DMPC、通篇不提车钩的 Ma2025 ITSC（GO-MADDPG，多列 MARL）被漏；
  5. **R5 检到却填错格**：`DIAGNOSTICS_2026-10.md:1429` 把 CCDC2025 DMPC 列入"车钩力进 MPC 代价项"，`:1434` 又写"多列 × 机械车钩力硬约束=空白（CCDC2025 无机械车钩）"——同节自我否证；
  6. **R6 无负结果台账**：每次复核从零开始，"没找到"不可审计、无法发现上次排除错了。
  - **结构性诊断**：事实被**抄写**在散文里 → 多副本 → **一个约束只要有两个入口就等于没有约束**；叠加规章通胀稀释权威，导致"该遵循的被绕过、装饰性规则天天拦人"。
- **决策**：
  1. **单一副本**：立论级事实的权威措辞只存在于 `docs/CLAIM_LEDGER.yaml`（字段：`statement` / `polarity` / `grade` / `evidence`（file+lines+anchor）/ `external_doi` / `search_ledger` / `ssot`）。**其它非临时文档禁止复述事实，只许引用 claim id**（如"见 §1.2 C-LIT-01"）。
  2. **渲染覆盖（消灭"抄写"动作）**：SSOT 用受控区块 `<!-- claim:ID begin/end -->` 承载事实，`scripts/render_claims.py` 从台账生成；手改区块 → `[DRIFT]`，`--write` 直接覆盖。**追认原则：被覆盖的区块不可能被绕过**（与 `outputs/` 不许覆写历史同类约束）。
  3. **证据分级与否定命题门槛**：A = 本地全文一手 / B = 摘要级或闭源 / C = 推断。**否定命题（空白 / 未见 / 无人）必须 grade=A 且挂 `search_ledger` 文件**，否则校验器 ERROR；措辞上限 = **"据系统检索未见（截至 <日期>，通道 <c>）"**，禁用"空白/首创/首次"。
  4. **负结果台账**：`docs/logs/verification/NEGATIVE_SEARCH_YYYY-MM-DD.md`——检索式 / 通道 / 年份 / 命中数 / 逐条排除理由 / **未覆盖通道声明**。缺此文件不得写否定结论。
  5. **临时工具文档豁免（用户 2026-10-20 裁定）**：`ppt_talk/**` 与 `docs/杂项/**` 与 PPT 大纲同质 = **临时工具文档**——① 允许事实重复、不保证严谨（校验器只记 WARN）；② **不得作证据源**（`evidence`/`ssot` 指向即 ERROR）；③ **查阅资料与立论引用时禁止检索这些目录**；④ **未经 owner 允许禁止修改**（`--check-protected` 用 git 脏文件检测，`--strict` 升 ERROR）。
  6. **合入门禁三件套**：`pytest tests/ -q` + `check_agents_links.py` + (`check_claim_ledger.py` && `render_claims.py`)，任一非 0 不许合入。
  7. **写入面约束**：agent 只允许写 `outputs/` 与 `docs/logs/`；台账与 SSOT 的改动须 owner 签（脚本防不住"有写权限的 agent"，只能靠权限面）。
- **同批修复（本次）**：清除 `AGENTS.md`(3) / `RESEARCH_POSITIONING.md`(6) / `PROJECT_PIPELINE.md`(1) / `MPC_BASELINE_KNOWLEDGE_BASE.md`(1) 共 **11 处**禁用措辞（另 4 处位于 `docs/杂项/`、2 处位于 `ppt_talk/`，按决策 5 保留）；§1.2 表 3 行改为"已有占位 + 见 C-LIT-xx"，边界段改为 9 个渲染区块；新增台账条目 C-LIT-07（Wang2025 ICIRT）、C-LIT-08（Zhang2024 原句 / Liu2021 无一手）。
- **校验结果**：`check_agents_links` → OK（44 个 ADR）；`check_claim_ledger` → **ERROR 0 / WARN 16**（历史日志 10 + 杂项 4 + PPT 2，均属豁免；另 1 条否定命题等级提示）；`render_claims` → 9 区块与台账一致。
- **遗留**：C-LIT-04/05/06 仍为 B 级（摘要级 / 闭源）；`C-GAP-01` 状态 `pending_cn_channel`——**CNKI/万方未跑**，故论文措辞只能是"英文通道据系统检索未见"；Ma2025 ITSC 闭源待核（其 MIQP"safety constraints"是否含车钩力未知）。
- **SSOT 联动**：`RESEARCH_POSITIONING.md` §1.2（表 + 渲染区块 + 措辞纪律）/ §1.6（Tube MPC 口径改指针）；`AGENTS.md`（最新 ADR 指针、§规范性问题两处）；`docs/README.md`（登记台账 + 负结果台账）；`PROJECT_PIPELINE.md`；`knowledge/MPC_BASELINE_KNOWLEDGE_BASE.md`。
- **相关**：ADR-030 / ADR-033（真空白边界，本 ADR 只补机制不改边界）；ADR-034（不可主张清单，继续有效）；ADR-042（实验矩阵，继续有效）；ADR-043（奖励 v6，无冲突）。

## ADR-045 中文库核验落地：万方通道打通 + 真空白收窄为三要素交集 - 2026-10-20

- **状态**：决策 + 已落地（`CLAIM_LEDGER.yaml` 新增 C-LIT-09~13、C-GAP-01 改写；`RESEARCH_POSITIONING.md` §1.2 渲染区块 14 条；`logs/verification/NEGATIVE_SEARCH_2026-10-20.md` 增中文通道两节）
- **背景（2026-10-20 工具链 + 核验）**：用户要求自行解决浏览器自动化。实测：`npx` 引导脚本损坏（`npm/node_modules/npx/index.js` 缺失），改用 **Python Playwright**（`pip install playwright` + 镜像下载 Chromium 1248）成功。通道可行性实测：**CNKI 被滑块验证拦截**（`knn.cnki.net` → `/verify/home?captchaType=blockPuzzle`，页面无检索框）、**百度学术同样被安全验证拦截**、**万方智搜可正常返回结构化结果**；维普可访问但检索式语义漂移。
- **核验命中（关键）**：
  1. **C-LIT-12 高济康（华东交通大学 2025 硕士）**《基于动态规划和深度强化学习的重载列车群组运行优化》：基于虚拟编组建立**群组运行模型 + 群组动态安全间隔**，翟方法求解组内多质点动力学，**EWM-DQN 群组多目标优化**，朔黄真实数据仿真**减小群组列车最大车钩力**并降能耗/提平稳/压缩追踪距离。**单智能体 DQN + 动态规划，非 MARL**。
  2. **C-LIT-13 谌墨（北京交通大学 2024 硕士）**《基于多智能体强化学习的虚拟编组列车协同控制方法》：CTDE + MADDPG，VCTS 协同控制；详情页关键词计数 **车钩力 = 0**，不涉机械车钩力。
  3. C-LIT-09 清华学位论文（IDS+IDQN 多机车、车钩力信息传播，单列车内）、C-LIT-10 王建华2023、C-LIT-11 万方多列车 DRL（节能/无车钩）。
- **决策**：
  1. **"车钩力进 RL 目标"这半格空白作废**——C-LIT-12 已占位（多列车组 + RL + 车钩力为优化目标之一）。全仓不得再写"无人在多列车组层面处理车钩力 / 车钩力进 RL 目标是空白"。
  2. **`C-GAP-01` 收窄为三要素交集**：「多列车组（智能体粒度 = 列车）× 车钩力进 RL 决策目标 × MARL」；最近邻三篇各缺一角（12 缺 MARL / 13 缺车钩力 / Song2026 Tube-MPC 非 RL）。状态升级为 `verified_three_channels`（S2 + arXiv + 万方），词条等级仍 **B**。
  3. **论文措辞定稿方向**（三条线各自走到边界，不是"没人做车钩力"）："multi-train RL with coupler force in the objective (Gao 2025, single-agent DQN) / multi-train MARL without coupler force (Chen 2024; Song 2026b; Ma 2025) / multi-train MPC with a hard coupler constraint (Song 2026a) —— 据系统检索未见三者同时满足者"。
  4. **通道纪律**：CNKI 结构性不可得（滑块），中文侧以万方题录为准并标注"题录级"；负结果台账必须写明未覆盖通道。
- **待核（升格前必须做）**：C-LIT-12 全文——车钩力是否进 DQN 奖励项 `r_t`；若已进，则"车钩力进 RL 目标"连 MARL 侧的 delta 也受压，`C-GAP-01` 需再次收窄，且触发 ADR-034 不可主张清单复核。
- **后果**：`RESEARCH_POSITIONING.md` §1.2 的立论差异由"加入车钩力"彻底改为"**把车钩力凭证从单列/单智能体挪到多列车组 × 多智能体**"（原表述本已被 ADR-030/033 收窄，本 ADR 提供了首个中文一手占位证据）。
- **相关**：ADR-030 / ADR-033（真空白边界，本 ADR 首次发现触碰该边界的实证）；ADR-034（若 C-LIT-12 车钩力进奖励落地，需复核不可主张清单）；ADR-044（台账机制，本次变更即在其机制下发生）。

## ADR-046 两篇邻居全文核验落地：C-LIT-04 硬约束纠错 + C-LIT-05 单质点确认 - 2026-10-20

- **状态**：决策 + 已落地（`CLAIM_LEDGER.yaml` C-LIT-04/05 升 grade A 并改判、C-GAP-01 最近邻补全；`RESEARCH_POSITIONING.md` §1.2 区块经 `render_claims.py --write` 重渲染；`docs/papers/03_formation/` 新增 PDF + fulltext 各 2 份；`papers/README.md`、`REFERENCE_INDEX.md`、`refs.bib` 三处登记；`NEGATIVE_SEARCH_2026-10-20.md` 追加"全文核验补记"节；`DIAGNOSTICS_2026-10.md` 追加同题小节）。
- **背景**：ADR-045 遗留"C-LIT-04/05 仍为 B 级、Ma2025 闭源待核"。用户自出版社下载两篇全文，并指出"若不人工看全文，投稿前会被错误表述带进去"。核验发现的**不是措辞瑕疵，而是方向相反的误判**：C-LIT-04 被写成"车钩力只进代价项、非硬约束"，而全文 (10e)/(12e) 恰是 ±2000 kN 硬约束（原文自述 "both are the hard constraints"）；C-LIT-05 被写成"闭源、车钩力是否入模未知"，而全文为单质点模型、通篇无车钩力。
- **决策**：
  1. **C-LIT-04 改判并升 A**：多列 DMPC = n 质点 + n−1 车钩弹簧-阻尼（工程取 d=0），车钩力**同时**进代价项与**硬约束**（±2000 kN）；5 列 × 2 万 t（2×HXD2 + 214 C80B、2.7 km）、大秦线、fence 法邻车并刚体降阶。全仓禁止再写"CCDC2025 DMPC 车钩力非硬约束 / 无机械车钩"。
  2. **C-LIT-05 升 A**：Ma2025 = 3 列重载群组 + GO-MADDPG（MARL）+ MIQP，**车辆为单质点模型**，车钩力不进状态/奖励/约束/结果指标 → 坐实「多列车组 × MARL，缺车钩力」，属反例侧的**英文全文级**证据。
  3. **C-GAP-01 三要素结论不变**，仅补全最近邻：缺 MARL 侧 = C-LIT-12；缺车钩力侧 = C-LIT-13（中文题录级）+ C-LIT-05（英文全文级）；非 RL 侧 = C-LIT-01 Song2026 Tube-MPC（±1500 kN）+ C-LIT-04 CCDC2025 DMPC（±2000 kN）。
  4. **全文抽取规范（工具层）**：IEEE 双栏 PDF 必须按**词级坐标分栏**重抽（`extract_words` 后按 x0 切栏再按 top 归行）；默认 `extract_text` 会把两栏交错，产生"读起来像原文、实为跨栏拼接"的假内容。本轮两篇 fulltext 均按此生成并在台账登记行号锚点。
  5. **MPC 基线备选（待决项，本轮不改实验矩阵）**：Wang2025 的 DMPC 形态可作为主表 MPC 行的第二参照（更贴近工程标准：多列 + 车钩硬约束 + 2 万 t 级）。是否替换由 owner 拍板；若替换，会连带改写"主对比物理关闭车钩力"的口径与防守句式，故不在本轮动手。
- **后果**：立论侧"多列层面对付车钩力"已无任何空白可主张（MPC 侧两个独立先例）；剩余唯一空格 = **MARL × 车钩力进 RL 决策目标**，措辞仍锁"据系统检索未见"。同类风险新增一条机械护栏：**禁止仅凭摘要页/题录页断言"某文献有没有建模"**（已属 FORBIDDEN 规则族，由 `check_claim_ledger.py` 守卫）。
- **连带收窄（"硬保证通道"的表述边界）**：C-LIT-05 全文显示 Ma2025 已有**动作掩码 + 安全保护曲线**双层安全（信号级动作过滤）。故"我们有硬保证、对手只有软奖励"对 Ma2025 **不成立**；ADR-034 的两条可主张 delta 中，"硬保证通道"必须限定为**保证对象 = 车钩力（≤1000 kN 物理量）**，而非泛指"有硬机制"。写作红线：对比 Ma2025 只谈"车钩力是否入目标/入硬保证"，不谈"谁更安全"。
- **相关**：ADR-030 / ADR-033（claim 收窄史）、ADR-044（台账 + 渲染机制）、ADR-045（中文通道与三要素收窄，本 ADR 关闭其遗留项）；`C-LIT-01/02`（Song2026 两篇的正确表述，ADR-045 已改）。

## ADR-047 创新点重述：对比—定位—启示（有效创新叙述层） - 2026-11-01

- **状态**：决策 + 已落地（`RESEARCH_POSITIONING.md` 新增 §1.2.1；`ppt_talk/midterm_20261018/OUTLINE.md` 页 2/页 4 更正 + 拍板 #27）。
- **背景**：① ADR-044/045/046 三轮文献纠错后，"多列群组 × 车钩力 × MARL"粗粒度空白被顶破一半——C-LIT-12 占"车钩力进 RL 目标（缺 MARL）"、C-LIT-04 占"多列 + 机械车钩力硬约束（非 RL）"，剩余空格收窄为三要素交集（C-GAP-01）；② 用户引入"会议有效创新"框架（创新分层：较小增量 → 新方法/新数据 → 显著扩展 → 新方法范式；会议评审要求创新可清晰识别、与会议层次和验证强度匹配），要求按该框架重述核心创新点并同步 PPT 大纲；③ PPT 页 2 仍残留"现有多列方法普遍缺车钩力约束"旧表述（ADR-045 已禁），需一并更正。
- **决策**：
  1. **可主张 delta 不变（ADR-034 两条）**，本轮只改"叙述层"：每条 delta 按"相对于什么而新（对比锚点）→ 带来什么启示（可讨论、可检验的命题）→ 检验设计（H1/H2 预注册）"组织；§1.2 渲染区块（事实层）不动。
  2. **Delta 1 叙述 = 问题设置层**："学习不生成循环制动时序，只在既定充风—制动—缓解节奏内做列间再分配"（对比锚点：多列学习类 C-LIT-02/05/13 把底层抽象为连续可调量；单列 RL C-LIT-03/08 无列间维度）；启示性命题 = 强时序约束分布式系统中，学习型协同的有效作用域是"约束内的再分配"而非"约束的重新生成"。
  3. **Delta 2 叙述 = 架构分工层**："硬保证对象 = 车钩力物理量（≤1000 kN，运行时确定性强制），学习层不背书安全"；启示性命题 = 安全约束分解原则（哪些决策由确定性逻辑锁定、哪些交给学习）；与 Ma2025 动作掩码的区别变量 = 约束对象是**物理量**而非信号量（落实 ADR-046 连带收窄）。
  4. **明确不作为创新点主张**："耦合感知奖励"式约束处理增量（自家车钩力擦除消融显示 RL 是否考虑车钩力无差异 + ADR-034 禁写清单）；车钩力—编队性能权衡（更紧间距 vs 更大钩力波动）只作 Discussion 问题提出，待主对比数据产出后再定能否升级。
  5. **PPT 更正**：页 2 主结论与文案改检索事实口径；页 4 两条创新点改对比定位式；最近邻备答补 Ma2025（四邻居各缺一角 + MPC 侧 C-LIT-01/04 两个硬约束先例）。
- **后果**：叙述层与事实层分离后，若后续 C-LIT 再纠错，§1.2.1 的对比锚点须同步复核；主 claim 仍为 ADR-042"相对传统基线的编队指标收益"，本 ADR 不改变实验矩阵与指标。
- **相关**：ADR-034 / ADR-042 / ADR-044 / ADR-045 / ADR-046；`CLAIM_LEDGER.yaml` C-GAP-01。

## ADR-048 生产积分器改为机械子步 0.0025 s（保留原 Newmark 公式） - 2026-11-04

- **状态**：决策 + 已落地（`src/train_dynamics/train.py` 新增类属性 `mechanical_max_step=0.0025`，`_advance_control_once` 在 0.01 s 气动子步内对力学方程细分；`src/evaluation/solver_registry.py` 的 `runtime_solver_record` 增记 `newmark_mechanical_max_step`）。
- **背景（事实）**：单列 70 km/h 冷起点 30 s 阶梯实验（同一控制器、同一冷起点）显示，生产 `h=0.01 s` 的 Picard-Newmark 每控制步 10 个力学子步中约 99%（2964/3000）打满 30 次迭代仍未收敛，随后回退到欠松弛态；车钩峰值 917.12 kN。固定记录输入的步长收敛序列（10 s 窗口）为 865.82 → 812.98 → 728.12 → 727.45 kN（h=0.01/0.005/0.0025/0.00125），即生产口径相对 h/8 参考高估 19.0%，h=0.0025 仅高 0.09%。同窗口 30 s 单列耗时：生产 0.0674 s/控制步，h=0.0025 为 0.0305 s/控制步（子步数 ×4，但每个子步 1 次迭代即满足判据，净耗时反而下降）。
- **逐项归因（事实）**：
  - 只抬迭代上限：历史诊断 max_iter=200 仍 2965/3000 未收敛、峰值更高（本轮按用户指示不重跑）。
  - 只换判据为界面力残差（Picard，0.01 N）：峰值 933.67 kN，2978/3000 未收敛，平均末端残差 989 kN → 仅改判据无效；h=0.01 下 Picard 根本达不到 0.01 N。
  - 只把 Picard 换解析切线 Newton（判据仍为位移 1e-5、h=0.01）：峰值 715.75 kN，0/3000 未收敛，平均 2.95 次迭代，0.0373 s/控制步 → 有效。
  - 只细化步长（公式/判据不变，h=0.0025）：峰值 729.18 kN，0/12000 未收敛，1.0 次迭代，0.0305 s/控制步 → 有效且最便宜。
  - 组合版（Newton + 力残差 0.01 N + 自适应步长）：峰值 719.05 kN，每次控制步 96.4 个接受半步、3.55 次拒绝，0.2885 s/控制步 → 有效但约 10 倍成本。
- **结论**：选"只细化步长"作为生产默认：保持 `β=1/4, γ=1/2` 的同一 Newmark 公式、同一 Picard 与同一位移判据，仅把力学子步上限由 0.01 s 改为 0.0025 s；气动波速/充风仍按 0.01 s 推进，不改变制动时序物理（ADR-011 车钩参数不变）。不引入新积分实现；Newton 与自适应误差控制保留为诊断显式开关。设 `mechanical_max_step=0.01` 可复现旧生产口径。
- **后果**：
  1. `src/train_dynamics/` 源码哈希变化 → 旧 fleet checkpoint 的 `native_source_hashes` 校验失效，旧 checkpoint 不可续跑；所有零 RL/基线结果需在 0.0025 s 口径下重跑，旧归档车钩峰值不可与新结果直接比较（单列 30 s 量级差约 19%）。
  2. metadata 必须同时记录 `solver=production_newmark` 与 `newmark_mechanical_max_step`；不得把 0.0025 口径写成新 solver 名称，也不得静默替换回 0.01。
  3. 论文实验矩阵（ADR-042）主对比与跨线实验全部按新口径重跑；已有 `publication_archive/` 与 round 归档保持原标签不动（D4），仅在引用时标注口径。
- **复现证据（相对仓库根）**：`traffic_rl_project/outputs/sim_validation/phys_validation/solver_ladder_single70_20261104/`（production_300、fine_300、picard_force_300、newton_displacement_300、error_controlled_300b、production_subcycle_300）；`traffic_rl_project/outputs/sim_validation/phys_validation/solver_reference_single70_20261104/convergence.json`。
- **相关**：ADR-011（车钩统一 MT-2）、ADR-017（训练/评估时域）、ADR-018（车钩力口径）、ADR-021（车钩力定位）、`docs/rules/EXECUTION_RULES.md`「生产与诊断必须同一数值实现」。

## ADR-049 起点条件规范化 + 三列主工况初速下调至 70 km/h - 2026-11-04

- **状态**：决策（D2 定案）+ 实验入口已按此执行；`train_fleet_env.reset` 的默认起点仍待同步（当前以评估入口显式参数落地）。
- **背景（事实）**：
  1. 三列 80 km/h 冷起点零 RL 全程未通过，且历史短窗累计出现 **329 次安全事件**。成因已定位为**起点条件**，不是设备/仿真故障：`init_speed_kmh: 80.0` 与 `env_cfg.v_max: 22.2222 m/s` 恰相等，安全层按 `vel >= max_speed_mps - 1e-6` 判 overspeed，3 列 × 109 辆在 t=0 即计入超速；跟随列车起点位于 km<0（编队以后车为基准向后排布），不在 ETCS 覆盖区，触发 `etcs_permitted`。
  2. 物理缺口：单机车满 ED 约 547 kN，而 49.6 km 长大下坡维持 80 km/h 所需约 903 kN；循环制动周期内掉速不可避免。`ab_min_refill_s = 222.0`（张二田 S6 充风门，文献锚）进一步限制 AB 源复用节奏。
- **决策**：
  1. **起点条件（硬约束）**：评估/训练的冷起点初速必须 **严格小于 `v_max`**（建议 `init_speed_kmh ≤ v_max_kmh − 1.0`，即 ≤79 km/h，留数值余量）；跟随列车的初始车头位置必须 **≥ km0**（落在 ETCS 覆盖区）。实现方式二选一：① 整编队沿剖面整体前移一个编队长度（领航列随之少跑等长距离，口径须注明）；② 将 ETCS 覆盖下界延伸到编组尾部。当前采用 ①。
  2. **三列主工况初速 80 → 70 km/h**（代价最低的备选，见下表），编组 `10kt_1plus108`、目标列距、充风门、车钩限值均不变。
  3. 新工况结果落**新目录**，不覆盖 `publication_archive/` 与既有 round 归档；metadata 必须记录 `init_speed_kmh`、起点整体偏移、编组与 `solver + newmark_mechanical_max_step`。
  4. **归档标签不改**（D4）：现有 80 km/h 冷起点归档保持原标签，引用时必须注明"旧起点口径"。
- **备选工况代价排序（低 → 高）**：

  | # | 方案 | 代价 | 牵动的论文设定 / 归档可比性 |
  |---|---|---|---|
  | 1 | 初速 80 → 70 km/h | 最低（改一个入口参数） | 主工况初速设定；起步段峰值与安全事件口径变化；旧 80 km/h 归档不可直接比 |
  | 2 | 加大初始间距（每对 +200 m 起） | 低（改布置参数） | 初始编队长度与 gap 指标起点；"安全列距"叙事不变，但初始相位差与旧归档不同 |
  | 3 | 放宽充风门 `ab_min_refill_s` 222 → 更小 | 高（改规则层物理参数） | 破坏 222 s 文献锚（张二田 S6），须补文献或标为假设；规则层行为不可与单列标定复用 |
  | 4 | 缩短编组（1+108 → 1+54） | 最高（改研究对象） | 与 ADR-039/040 研究对象（10988 t）不一致，全部归档与训练配置需重建，不建议 |

- **后果**：
  1. 70 km/h 冷起点三列结果的"通过/不通过"只在该工况下成立，不得写成"80 km/h 工况达标"。
  2. 论文主对比（ADR-042）须统一采用本 ADR 的起点口径；旧归档车钩峰值与安全事件数不可与新口径混表。
  3. 若 70 km/h 仍不通过，按上表依次尝试方案 2，方案 3/4 须先补文献或改研究对象，需另行决策。
- **复现证据（相对仓库根）**：
  - 单列 70 km/h 全程（ADR-048 定案子步口径）：`traffic_rl_project/outputs/sim_validation/phys_validation/single_production_subcycle_70kmh_full_20261104/run/result.json` —— `full_route_completed=true`、峰值 937.05 kN、violations 0、over 1000 kN 无、`max_vehicle_speed_kmh=80.34`（86 个列车步进超 80 km/h，安全层介入）、0 未收敛子步（1 227 000 机械子步，最大位移残差 5.87e-6 m）。
  - 三列 70 km/h 全程（本 ADR 工况）：`traffic_rl_project/outputs/sim_validation/phys_validation/fleet3_production_subcycle_70kmh_full_20261104/run/result.json` —— 在 t=103.5 s、行进 1.77 km 处车钩峰值 **1005.11 kN** 越 1000 kN 触发诊断早停，`full_route_completed=false`；超速列车步进 0，`negative_gap_steps=0`，未收敛子步 0。数值侧健康（残差 6.78e-6 m、平均迭代 1.0），**越线属规则层策略/工况问题而非求解器数值问题**。
  - 对照旧 80 km/h 冷起点（未做起点规范）：`traffic_rl_project/outputs/sim_validation/phys_validation/fleet_production_edramp02_80kmh_full_20261104/run/result.json` —— t=301.5 s、5.91 km 处峰值 1007.99 kN 早停，safety_events 329（含初始 3×109 辆超速判定）。
- **相关**：ADR-039（三列 1+0 研究对象）、ADR-040（1000 kN 验收）、ADR-048（求解器口径）、ADR-017（训练/评估时域）。

### ADR-049 补充（方案 2：加大初始列距）- 2026-11-05

- **状态**：已实施（实验入口），不改运行期 `target_gap`。
- **依据（事实）**：用环境同源 ETCS 曲线（`src/train_dynamics/etcs_braking.py`，减速度速度档 40/60/80 km/h = 0.426/0.401/0.382 m/s²、制动建立时间 = 车列长 1297 m ÷ 250 m/s ≈ 5.19 s、最陡下坡 −12‰）计算：70 km/h 在起点 km2.8 处的 EBD 制动距离 **693 m**（ADR-026 效率口径 1.1× = **763 m**）；80 km/h 为 912 m（1.1× = 1003 m）。旧的初始车头—车尾间距 100 m 仅为该值的 14%，故 `min_gap` 监督从第 1 秒起持续触发。
- **改动**：初始列距由 100 m 加大到 **700 m**（每对 +600 m，`--gap-offset-m 600`），取"≥ d_safe 的最小整百值"；编队初始总长变为 2×(1297+700) = **3994 m**，起点整体前移量相应由 2800 m 改为 **4000 m**，保证尾列车头 ≥ km0。
- **影响**：
  1. 只改**初始条件**，运行期目标列距（`target_gap`/headway 动态间距）不变，编队控制目标与论文"安全列距"叙事不变。
  2. 初始相位与旧归档不同，峰值与安全事件数不可与 100 m 初始间距的归档直接比；新结果另立目录。
  3. 领航列起点随之前移到 km4.0，实际覆盖 km4.0→49.6（46.6 km），论文口径须注明。
- **待验证**：新工况三列全程零 RL 的 `route_completed`、峰值、均速与安全事件分类计数（overspeed / etcs / min_gap）。
- **全程基线（不早停，2026-11-05）**：`traffic_rl_project/outputs/sim_validation/phys_validation/fleet3_production_subcycle_70kmh_full_unstopped_20261104/run/result.json` —— `full_route_completed=true`、均速 58.2 km/h、`max_vehicle_speed_kmh=80.86`、0 未收敛（378 万机械子步、残差 7.5e-6 m）。**有效路段（领航列 ≤ 49.6 km）峰值 1288.5 kN**（t=1846.7 s、km33.6、中列第 47 号车钩）；三列有效峰值 916.5 / 1288.5 / 1228.3 kN。全程记录峰值 1479.8 kN 出现在 km50.1，**已越出剖面终点、不作数**。安全事件分类（按车·步计）：overspeed 16634 / etcs_permitted 7339 / etcs_ebi 3695 / coupler_force_limit 14 / min_gap 0。⇒ 加大初始间距只解决起步段，**中后段循环制动压缩波才是主峰**。
- **复现（规划）**：`traffic_rl_project/outputs/sim_validation/phys_validation/fleet3_gap700_production_70kmh_full_20261105/`。

### ADR-049 补充修订（初始净空口径 800 m，2026-11-05）

- **口径定义（事实，代码依据）**：`--gap-offset-m X` 加在"动态基准间距"上（`src/environments/train_fleet_env.py` L142-147：`target_gap 100 m` + `headway_s 5.0 s × target_speed`；本工况实测基准 **185.27 m**）。该量是**前车最后一节车与后车第一节车之间的净空**；绝对净空 = 185.27 + X；车头—车头间距 = 列车计算长度 1294.06 m + 绝对净空。
- **取值修订（推导链，事实）**：70 km/h 的 EBD 制动距离 **693 m** → 项目 1.1× 效率口径 **763 m** → 决策取整为**净空下限 800 m**（800/763 = 1.049，余量 37 m ≈ 4.9%）。700 m 仅为 763 m 的 91.7%，属"刚好刹住、无余量"。严格 800 m 对应 `X = 615`（800.3 m）；本轮取 `X = 700` ⇒ **绝对净空 885.27 m**（763 m 的 1.160 倍，较 800 m 下限多 85 m ≈ 11%）。
- **自洽性（事实）**：编队总长 = 2 × (1294.06 + 885.27) = **4358.7 m**；`--start-m 4450` ⇒ 尾列车头 = 4450 − 4358.7 = **+91.3 m ≥ km0**；与重跑 `step=1` 的领航车头 4451.9 m 一致。
- **裁定（用户选项 2：口径差异，不是参数取错）**：净空 885 m 同时满足 ≥763 m（1.1×）与 ≥800 m（决策下限），**本重跑可直接作为主结果**；引用时必须写"初始净空 885 m（`--gap-offset-m 700`）"，**不得写"800 m"**，也不得出现"800 目标 / 885 实测"式含混表述。

- **状态**：已实施（实验入口）。700 m 轮**保留为对照记录**，不删除、不覆盖。
- **700 m 轮结果（事实，对照）**：`traffic_rl_project/outputs/sim_validation/phys_validation/fleet3_gap700_production_70kmh_full_20261105/run/result.json`
  - `full_route_completed=true`、`elapsed_s=3137.0`、均速 57.78 km/h、`max_vehicle_speed_kmh=80.63`；0 未收敛（376 万机械子步、最大位移残差 7.60e-6 m、平均迭代 1.0）；墙钟 2456.5 s（0.0783 s/控制步）。
  - 有效路段峰值 **1236.0 kN**（t=1778.4 s、33.01 km、中列第 44 号断面）；三列 922.0 / 1236.0 / 1147.4 kN；>1000 kN 记录 1100 行；记录峰值 1425.0 kN 在 km50.2 越出剖面终点，不作数。
  - 安全事件（车·步计）：coupler_force_limit 1296 / min_gap 0 / overspeed 14185 / etcs_ebi 3457 / etcs_permitted 6403。
  - **口径缺陷（事实，须更正上节措辞）**：`--gap-offset-m 600` 的实际初始车头—车尾净距为 **785 m**（基础间距 185 m + 偏移 600 m），而非上节所写的"700 m"；起点 4000 m 小于实际编队总长 ≈4165 m，尾列车头 t=0 位于 −158.7 m（越出 km0），与 ADR-049 决策 1 的"跟随列车车头 ≥ km0"硬约束不符。
- **编号口径更正**：上节"中列第 47 号车钩"是数组下标（0-based），1-based 应为**第 48 个断面**；本轮溯源统一按 1-based 书写。
- **影响**：只改初始条件；运行期 `target_gap` 不变；覆盖 km4.45→49.6（45.15 km），论文口径须注明；与 185 m / 785 m 初始净空归档不可直接比。
- **有效范围（事实 + 推断）**：初始净空 185.3 m → 起步段峰值 1254.5 kN、主峰 1288.5 kN；净空 785.3 m → 主峰 1236.0 kN。**间距只影响起步段，主峰仅降 ~4%（1288.5→1236.0），不构成对主峰的修复**；主峰机制见 `docs/logs/diagnostics/DIAGNOSTICS_2026-11.md`「主峰相位溯源-2026-11-05」。
- **两轮角色（用户决定 2026-11-05）**：
  - **主结果 = 净空 800.3 m**：`--gap-offset-m 615`，编队总长 2×(1294.06+800.3)=**4188.7 m**，`--start-m 4290`（尾列车头 +101.3 m ≥ km0），目录 `traffic_rl_project/outputs/sim_validation/phys_validation/fleet3_gap800_strict_production_70kmh_full_20261105/`。
  - **对照 = 净空 885.3 m**：`--gap-offset-m 700`，`--start-m 4450`，目录 `traffic_rl_project/outputs/sim_validation/phys_validation/fleet3_gap800_production_70kmh_full_rerun_20261105/`（已跑完/在跑）。
  - 主结果引用写"初始净空 800 m（`--gap-offset-m 615`）"；对照写"初始净空 885 m（`--gap-offset-m 700`）"。被中断的首轮目录已标 `ABORTED_BY_INTERRUPTION.txt`，不作结果引用。
- **885 m 对照轮结果（事实，2026-11-05）**：`full_route_completed`（31392 控制步、elapsed 3139.2 s）、均速 57.34 km/h、`max_vehicle_speed_kmh=80.28`、0 未收敛（376.7 万机械子步、残差 7.46e-6 m、平均迭代 1.0、0.0781 s/控制步）；**有效峰值 1255.2 kN**（t=1328.8 s、26.65 km、中列第 39 断面）；三列 1054.0 / 1255.2 / 1250.9 kN；>1000 kN 记录 820 行；安全事件（车·步）coupler 569 / min_gap 0 / overspeed 17257 / etcs_ebi 3742 / etcs_permitted 5477；`min_gap_m=78.8`、`negative_gap_steps=0`。
  - 峰值时刻四元组：ED −725.3 / −557.8 / −276.5 kN；AB RELEASE / EMERGENCY / RELEASE；循环相位 False / True / False；速度 40.5 / 52.7 / 44.5 km/h（与 100 m 轮 t=1846.7 s 的机制不同，主峰仍 >1000 kN）。
  - 病灶统计（与 100 m 轮基线同口径）：中列 veto 行占比 **36.57%**；被否决时段均值 **792.2 kN** / p95 **1053.1** / >1000 占比 **6.63%**（基线 792.8 / 1038.4 / 6.34%）。

## ADR-050【草案·未生效】训练方案口径调整 - 2026-11-05

> ⚠️ **状态：草案，未生效，待用户确认**。本 ADR 不修改 `configs/experiments/*.yaml`，不改变任何正在运行的配置。仅为把文献口径整理成可评审方案。

- **提案（文献口径）**：
  1. 决策步 = **1 s**（0.1 s 仿真步 × frame skip 10）。现行 `decision_interval: 10` 与 `dt: 0.1` 已等价，**此项无需改代码**，只是把"步"的计数单位统一到决策步。
  2. 每集 = **3600 决策步**（= 3600 s 全剖面）。折合 env 步 = 36000，与现行 `max_steps: 36000` **数值相同**。
  3. 课程：**600 s → 1800 s → 3600 s**（三档递进）。现行 `curriculum: 36000:0` = 从第 0 集起直接全剖面，**无课程**。
  4. BC 热启动 **200–500 集，且必须为全长集（每集 3600 s）**；不采用"课程短集做 BC"的折中。现行 `bc_episodes: 1` / `bc_max_steps: 36000`。
  5. 总环境步数目标 **1–3×10⁷**。现行 1400 集 × 36000 = **5.04×10⁷**，约为上限的 1.7–5 倍。
  6. 并行 **8–32 环境**。现行 `n_env: 4`（`n_env_parallel: true`）。
- **逐项对照**：

  | 项 | 现行生效（`configs/experiments/formation_ed_ab_3train_1plus108.yaml`） | 草案提案 | 是否需改 YAML |
  |---|---|---|---|
  | 每集 horizon | `max_steps: 36000` env 步 = 3600 s | 3600 决策步 = 3600 s | 值不变，语义统一 |
  | 课程 | `curriculum: 36000:0`（无课程） | 600→1800→3600 s 三档 | 需改 |
  | 集数 | `episodes: 1400`（总 5.04×10⁷ env 步） | 按 1–3×10⁷ 反推 ≈ 278–833 集 | 需改 |
  | BC | 1 集 × 36000 步 | 200–500 **全长集**（每集 3600 s） | 需改（且须等规则层验收） |
  | 并行 | `n_env: 4` | 8–32 | 需改（受本机核数/显存约束） |
  | 评估间隔 | `long_eval_interval: 0`（关闭） | 未提议变更；若恢复课程则须重新开启 | 待定 |
- **影响清单（推断，须逐条验证）**：
  1. **已有 checkpoint 全部不等价**：ADR-048 已改变源码哈希与数值口径，若再叠加课程与集数变化，`outputs/checkpoints/formation_10kt_1plus108/fullprof_20261021/` 只能作"链路跑通"证据，不能作效果基线。
  2. **归档可比性**：集数从 1400 降到 ~280–830 后，"训练量"维度与旧归档不可比；任何论文中的"训练步数/样本量"叙述须重写。
  3. **BC 合法性前置条件**：BC 教师来自规则基线零调制行为，规则层三列主工况尚未通过（见 ADR-049）→ BC 200–500 集在本 ADR 生效前**不具备合法性**，必须等 `route_completed` 达标。
  4. **论文设定**：课程 600 s 起步会改变早期训练场景覆盖，若论文声称"全程 49.6 km 训练"须注明课程分档；并行 8–32 与"单机训练"叙述可能冲突。
  5. **算力**：现行实测 ≈0.095 s/env 步（3 列）→ 1×10⁷ 步 ≈ 264 单核小时；8–32 并行需实机核数与内存评估。
- **不改动项**：奖励 schema（v6）、动作空间、观测维度、求解器口径均不变。
- **相关**：ADR-017（1400 集硬要求与短窗训练/独立评估）、ADR-048（求解器）、ADR-049（工况与起点）。

## ADR-051【草案·未生效】奖励速度带规格（贴近允许速度） - 2026-11-05

> ⚠️ **状态：草案，未生效**。**用户决定（2026-11-05）：暂不启用**；保持 `speed_band_mode: fixed`（项目当前无该字段，等价于 fixed），不改生效权重、不改观测。草案仅留档备查，后续不再主动建议启用。

- **现状（事实）**：`src/environments/train_fleet_env.py` L1151-1152 令 `v_center = 0.5*(v_min+v_max)`（=60 km/h）、`band_half = 0.5*(v_max-v_min)`（=±20 km/h），中心与半宽来自 YAML 固定 `v_min/v_max`，**不随 ETCS 允许速度变化**；带内平顶 +5（L1159-1161，无梯度），带外 `-0.2*(norm_dev-1)*100`（L1163），越 `v_max` 另加硬罚（L1166-1167）。规则层循环制动门 65/50 km/h（YAML L60-61）把运行窗口压在 50–65，故实测稳在 60。
- **规格（字段级 diff）**：

  | 字段 | 现行 | 提案 | 说明 |
  |---|---|---|---|
  | `v_top` | `v_max`（固定 22.222 m/s） | `min(v_max, v_etcs_permitted(t) − 制动距离余量)` | 上缘随 ETCS 允许速度动态变化 |
  | `v_bot` | `v_min`（固定 11.111 m/s） | 不变 | 下限仍按文献/规则 |
  | 带内奖励 | 常数 `+5` | `+5 * clip((v - v_bot)/(v_top - v_bot), 0, 1)`（或指数形式） | 越接近上缘正奖越多；保留 Zhang2024 式22 的 +5 量级 |
  | 带外（高于上缘） | `-0.2*(norm_dev-1)*100` + `-5*(v-v_max)` | `-c_lin*(v - v_top)` 连续负奖 + `-c_hard` 硬罚 | 连续项给梯度，硬罚抑制持续越线 |
  | 观测 | 速度误差锚固定 `target_speed`（L141/L919） | 建议同步改为 `v - v_top` | 否则策略看不到上缘变化 |
  | 开关 | 无 | 新增配置 `speed_band_mode: fixed \| etcs_top`，默认 `fixed`（零回归） | 可开关 |
- **需标定参数**：`margin_brake_m`（制动距离余量，建议初值 100–200 m，按 70 km/h d_safe≈693 m 的 15–30%取）、带内增益形式与斜率、`c_lin`、`c_hard`、是否指数衰减及其尺度。
- **风险（推断）**：上缘贴近允许速度会压缩速度裕度，在物理缺口工况（满 ED 547 kN < 80 km/h 需求 903 kN）下可能诱发更频繁的 AB 循环与更高车钩峰值；须与 ADR-049 的工况验收一起评估。
- **相关**：ADR-043（v6 奖励槽位与 +5 依据）、ADR-026（间距效率与 ATP 同源）、ADR-049（工况）。

## ADR-052 规则层诊断开关：否决期 ED 回升放大（C4）- 2026-11-05

- **状态**：已实施（**诊断开关，默认关闭**；`ed_veto_recovery_boost=1.0` 与原行为逐位一致）。**验证结果：已实测无效（峰值 +7.5%），按判据放弃，开关保留默认关闭。**
- **背景**：主峰溯源（`docs/logs/diagnostics/DIAGNOSTICS_2026-11.md`「主峰相位溯源-2026-11-05」）显示 t=1846.7 s 峰值时刻中列 `new_source_veto=True`、ED 仅输出约 72%（−393 kN / 额定 −547 kN），中列同时没有可用新增 AB 源，是主峰的直接放大器之一。
- **选项与权衡**：
  - A. 取消 ED 回升速率限制 → 可能生成新的纵向冲量（ADR-021 引入限制的初衷），风险高；
  - B. **否决期内把 ED 回升上限放大到 2×，仍封顶 1.0 并受车钩安全层约束（选用）**；
  - C. 不动 → 保留已定位病灶。
- **结论**：选 B。ED 不是空气制动源，**不触发** `ab_new_source_veto` 与 222 s 充风门；AB 准入、充风门、`enforce_coupler` 全部不变。
- **实现**：`src/controllers/multi_loco_controller.py` 新增构造参数 `ed_veto_recovery_boost`（默认 1.0，`>=1.0` 校验）；在 ED 回升限幅之后、`_previous_ed` 记录之前执行：`if boost>1.0 and ab_add_vetoed: final[:,0] = min(final[:,0]*boost, 1.0)`。`src/environments/train_fleet_env.py` 读取 env 键同名（默认 1.0）；诊断入口通过 `--override ed_veto_recovery_boost=2.0` 启用。
- **后果 / 验证口径**：单改、全程（`route_completed` + 有效峰值 <1000 kN + 峰值前后 30 s 的相位差/速度离散改善）；**必须同时报**中列 `new_source_veto` 行占比、被否决时段车钩均值/p95，与 B 基线 **792.8 / 1038.4 / 6.34%** 对比；若峰值下降但峰位迁移，须报迁移到的列车与车钩号。
- **风险（推断）**：① ED 抬升会改变中部机车前部压缩/后部拉伸，峰位可能迁移；② 逼近车钩硬限时安全层硬裁可能产生限幅抖动；③ 若无效则按"记录后放弃"处理。
- **口径更正（2026-11-05，事实）**：上条"72% = −393/−547 kN"的**分母错**。885 m 对照轮峰值时刻领航列 ED 实测 **−725.3 kN**，说明单列 ED 权限上限高于 −547 kN；B 峰值时刻中列 −393 kN 应按实测权限表述（约 54%），**"否决期 ED 未打满"的机制判断不变**，C4 实现不受影响。
- **实测结果（2026-11-05，事实，全程单改）**：`fleet3_c4_edboost2_strict800_rerun_20261105`（三件齐，生产 Newmark，70 km/h / 1+108 / 49.6 km / 严格 800 m）峰值 **1411.0 kN**（t=572.4 s、**尾列第 53 断面**、相位 `B|V|B`、三列 ED 全部打满），相对基线 1312.9 kN **+7.5%**；峰位由中列第 44 断面（t=1354.1 s）迁移到尾列中部；中列 veto 行占比 31.26%→**35.52%**、被否决时段均值 756.3→**778.0 kN**、p95 1011.4→**1062.9 kN**、>1000 占比 5.45%→**7.53%**。**不满足 `<1000 kN` 判据 → 无效，放弃**；开关保留默认关闭，不进入后续候选。详见 `docs/logs/diagnostics/DIAGNOSTICS_2026-11.md`「C4 规则层单改结果（否决期 ED 回升 2×）」与「代理指标失效记录」。
- **相关**：ADR-021（ED 回升限制）、ADR-036（车钩档位）、ADR-049（工况）、`docs/logs/diagnostics/DIAGNOSTICS_2026-11.md`。

## ADR-053 规则层诊断开关：C1 缓解错峰 / C3 充风判据纳入列距 / C5 速度协整 - 2026-11-05

- **状态**：已实施（**三个诊断开关，默认全关 = 零回归**）。**活性校验（2026-11-06，6000 步）三项全部通过**：C1 首次分叉 row 264 / t=26.5 s（尾列首次缓解延迟 60 s）、C3 row 2429 / t=243.0 s（净空 946.9 m 使充风门限缩短 5.51 s）、C5 row 685 / t=68.6 s（中列有符号速度超差触发）。**C1 全程单改结果（`fleet3_c1_stagger30_strict800_full_20261106`）：峰值 1296.0 kN（−1.3%，且由基线的压缩翻为拉伸），但 `|v尾−v领航|` 均值 7.09→**12.42 km/h**、中列-尾列净空最大 1008.7→**1841.5 m**、尾列 **17%** 时间 <40 km/h ⇒ **按编队指标判据无效/不利方向，开关保留默认关闭**。C3 / C5 全程单改轮次在串行队列中，结果待归档。
- **背景**：B 溯源给出主峰三因素（相位差 118.9 s、否决/充风差 0.5 s、速度离散 8.5 km/h）。C4 已落（ADR-052），C1/C3/C5 对应另外三环。
- **实现位置与默认值**：

| 项 | 开关键（env_cfg） | 默认 | 参数 | 作用点 |
|---|---|---|---|---|
| C1 缓解错峰 | `cyclic_release_stagger_per_train_s` / 控制器 `cyclic_release_stagger_s` | `0.0` | 每列递增延迟（s/列）+ 全局附加延迟（s） | `multi_loco_controller.py` 循环制动释放跃迁处：速度达缓解门后**保持制动** `delay/dt` 步 |
| C3 充风判据纳入列距 | `gap_aware_refill` + `refill_gap_reference_m` / `refill_gap_relax_max_s` / `refill_gap_relax_span` | `False` / `800.0` / `0.0` / `1.0` | 净空超出参考值的比例 → 门限最多缩短 `refill_gap_relax_max_s` | `_refill_gate_s()`，`_ab_gate` 使用；**222 s 锚不动**（只会因净空富余而缩短，不会加长/取消） |
| C5 速度协整 | `follower_speed_conformance` + `speed_conformance_tol_kmh` / `gain` / `max` | `False` / `1.8` / `0.20` / `0.30` | 容差、每 km/h 超差的 ED 增量、单步 ED 增量上限 | `_step_decomposed` 收尾：`|v_self−v_lead|>tol` 时先收牵引、再按增量加 ED，封顶 −1.0 |

- **C5 容差依据（事实）**：`AB_SUPPRESS_MARGIN_MPS = 0.5 m/s = 1.8 km/h`（控制器现有缓解抑制裕度），故默认容差取 1.8 km/h，不另造数。
- **编队接口（事实）**：`train_fleet_env.py` 在每步给跟随列设置 `formation_clear_gap_m`（前车尾−本车头）、`formation_leader_speed_kmh`、`formation_release_delay_s`；开关关闭时控制器不读取（`getattr` 缺省 None），行为逐位不变。
- **不触碰的约束（事实）**：AB 禁新增源、222 s 充风基值、`enforce_coupler`、ETCS/ATP 全部保留最终裁量；C3 只允许"净空富余时提前缓解"，不放宽安全上限。
- **验证口径**：单改、全程；`route_completed` + 有效峰值 <1000 kN + 峰值前后 30 s 相位/速度离散改善；每项都要报峰值时刻三列 ED/AB/相位/速度四元组，与 B 基线（t=1846.7 s：领航 ED −543/AB RELEASE、中列 ED −393/AB SERVICE/veto、尾列 62.6 km/h）对照。
- **风险（推断）**：C1 延迟缓解可能抬高整体温度/车速（缓解滞后→制动更久→速度更低，需看是否触发 overspeed/低速）；C3 提前缓解可能增加低充风下的二次压缩；C5 强制速度跟随可能把压缩转移到尾列或前部。
- **相关**：ADR-021、ADR-036、ADR-049、ADR-052、`docs/logs/diagnostics/DIAGNOSTICS_2026-11.md`。

## ADR-054 规则层诊断开关：前部列制动前馈（C6）- 2026-11-05

- **状态**：**已实施 + 已实测无效且方向不利（2026-11-06 定案：放弃 C6，开关保留默认关闭 = 零回归）**。**实测（rerun4 全程，修复后真实生效）**：`route_completed=True`、峰值 **1371.4 kN**（基线 1312.9 kN，**+4.5%**）、峰位由中列第 44 断面（t=1354.1 s）迁到中列第 38 断面（t=1324.8 s）、均速 57.38→**63.06 km/h（+5.68）**、`overspeed_train_steps` 199→**3286（16.5 倍）**、中列 veto 行 >1000 占比 5.45%→**2.14%**。判据（峰值不降）**不通过**；三项观测中两项（均速、超速）**方向不利**——实质是**把编队跑松（整体提速、放松跟踪），不是把车钩力压下来**，峰值仅随峰位迁移而抬高。→ **C6 放弃，不叠加进相位组合表主路径**。
- **第二轮预案已取消（事实 + 理由存档）**：原预案只把 `duration_s` 改 **146.0**（覆盖四轮局部峰提前量分布的 p90=146.8 s）。**不执行该轮**，理由：C4 轮实测提前量为 **243.8 s**，超出 p90=146.8 s 与最大值 149.1 s 的覆盖范围；即 `duration_s=146.0` 在该轮峰位前早已失效，无法验证"延长作用窗是否降峰"，跑该轮只会再消耗约一次全程机时而无判别力。**该预案保留为历史记录，不再排入队列**。
- **依据（事实）**：严格 800 m 主结果峰值四元组（t=1354.1 s）显示领航/中列 ED 仅 −23.6 / 0.0 kN、AB 均 RELEASE、循环相位仅尾列为 True、尾列速度最高（53.2 vs 41.2/43.7 km/h）→ "尾列单独制动、前两列空转滑行"的编队内拉伸/压缩。
- **开关键与参数（env_cfg，全部默认关闭/中性）**：

| 键 | 默认 | 含义 |
|---|---|---|
| `leader_brake_feedforward` | `False` | 总开关 |
| `leader_brake_ff_hold_s` | `2.0` | 触发需持续秒数（0 = 立即） |
| `leader_brake_ff_duration_s` | `10.0` | 每次触发的 ED 下限作用窗（秒） |
| `leader_brake_ff_ed_low_frac` | `0.20` | 后部列 ED 低于该比例视为"近零滑行"（触发条件之一） |
| `leader_brake_ff_ed_floor_frac` | `0.25` | 前部列必须建立的最小 ED（占 ED 归一化权限） |
| `leader_brake_ff_scope` | `immediate` | 生效列范围：`immediate`=仅紧邻前方一列；`all`=前方所有列 |

- **触发条件**：后部列 AB 已建立（任一 AB 源 `_ab_on`）**或** 后部列 ED 均值 < `ed_low_frac`，持续 `hold_s` 秒。
- **实现位置**：控制器 `_step_decomposed` 收尾（C5 之后）执行 `final[:,0] = max(min(final[:,0], -floor_frac), -1.0)`；`train_fleet_env.py` 每步按 scope 写入 `formation_rear_braking` / `formation_rear_ed_frac`（来自 `multi_loco_controllers[j]._ab_on` / `._previous_ed`）。
- **不触碰的约束（事实）**：只动 ED（非 AB 源），AB 禁新增源、222 s 充风门、`enforce_coupler`、ETCS/ATP 全部保留裁量。
- **风险（推断）**：① 前部列被迫制动会拉低整体速度，可能增加 overspeed 的"低速侧"或 etcs 触发；② 前部 ED 下限会在领航列制造额外压缩，峰位可能前移；③ 持续触发会造成 ED 抖动（`_previous_ed` 已记录下限值，回升限制会跟上）。
- **验证口径**：与其余 C 系列同一工况（净空 800.27 m、`--gap-offset-m 615`、`--start-m 4290`），对照 **1312.9 kN** 基线；单改全程；`route_completed` + 有效峰值 <1000 kN + 峰值四元组逐环归因 + 相位组合表更新。
- **参数标定依据（2026-11-05，实测）**——C6 首轮不采用初值，改用按提前量定标的一组：
  - 四轮峰值处的"尾列制动起点 → 峰值"提前量：185 m 基线 **128.4 s**、785 m **80.7 s**、885 m **0.0 s**、800 m 主结果 **79.2 s**。
  - 四轮全部 `>1200 kN` 局部峰（n=75）提前量分布：**p10 0.0 s / 中位 72.0 s / p90 146.8 s / 最大 149.1 s**（计算见 `docs/logs/diagnostics/DIAGNOSTICS_2026-11.md`「尾列制动起点相对峰值的提前量」）。
  - **首轮取值**：`hold_s=1.0`、`duration_s=80.0`、`floor_frac=0.25`、`scope=immediate`。理由：80 s 覆盖中位段（72 s），`hold` 只做去抖（1 s），下限与作用范围不动，保证"只调时间参数一组"。
  - **历史初值（保留，不删）**：`hold_s=2.0`、`duration_s=10.0`；按上表，10 s 窗在峰值前约 60 s 即失效，故首轮直接跳过该组，不再单独跑。
  - **第二轮预案（仅在首轮无效时启用）【已取消 2026-11-06，见状态行】**：只把 `duration_s` 改 **146.0**（覆盖 p90），`hold_s=1.0`、`floor_frac`、`scope` 不变；每轮只动一组参数，不叠加。
- **相关**：ADR-049、ADR-052、ADR-053、`docs/logs/diagnostics/DIAGNOSTICS_2026-11.md`。

## ADR-055 车钩力准静态可达下界：1+108 在 70 km/h 下不具备 EBD 包络能力 - 2026-11-06

- **状态**：已计算并登记（**纯计算，不占机时，未改动任何开关/配置**）。结论：**"3 列 × 1+108、70 km/h、含 −12‰ 与 EBD 要求"的 1000 kN 目标 = 结构上不可达**；只在"不要求 EBD/紧急权限、单步制动权限 ≤0.284 m/s²"的受限包络内才可达。
- **口径与模型（事实）**：准静态、逐车刚体、全列同一减速度，断面力 `C_k = S_m[k+1]·a − S_B[k+1] + S_FG[k+1] + S_R[k+1]`；制动波 `delay=距离/200（常用）或 250（紧急）`；编组 1+108 = 10 988 t / 1 317 m；牵规 `β_c·φ_h·K_h`（`K_h=161.5 kN`，70 km/h `φ_h=0.2443`）；Davis 与 `_davis_params` 同式；坡度取 `shuozhou_ningwuxi_beidaniu_49km` 全程 20 m 扫描。解析项 = `0.25·M·b`（波瞬态）+ `Σ_rear m g(ī−i)`（坡度差分）。近似 = 无车钩动态/无超调、波期位置冻结、出波即满出力、机车与货车同 `K_h`、不计充风约束。
- **数值（70 km/h / 1+108，下界 kN）**：匀速保持 −12‰（b=0.0845）**437**；CYCLIC(50 kPa) **386**；MIN(70 kPa) **599**；SERVICE(140 kPa) **1003.9**；EMERGENCY **1270.3**；EBD（不含坡度，b=0.3913）**1279.3**；EBD+−12‰坡度（b=0.5091）**1602.6**。坡度差分全程峰值 **216.6 kN @ s≈24.34 km**（列车头在 −1.5‰、尾压在 −10.9‰，跨 9.4‰）。
- **临界式（事实，可代数复算）**：`下界 ≈ 0.25·M·b + 216.6` ⇒ **b_crit=(1000−216.6)/(0.25×10 988)=0.284 m/s²**；SERVICE 的 0.2935 恰越过该线。
- **速度敏感性（事实）**：50/60/70/80 km/h → SERVICE 1047.4/1024.0/1003.9/986.4、EMERG 1328.3/1297.1/1270.3/1246.9、EBD+坡度 1661.1/1629.6/1602.6/1579.0 ⇒ **速度区间只值 −4.9%~+3.7%，不是有效杠杆**。
- **规则层可行的两条（事实+推断）**：① 单步拆两段（SERVICE 1003.9→**604.3 kN，−40%**）；② 常规调速只用 CYCLIC+ED（0.066+0.038=0.104 > −12‰ 所需 0.085）。③ 不在 s≈24.3–26.1 km 坡度差分峰叠加整档制动。**紧急制动只能作兜底**（其地板 ≥1270 kN）。
- **物理侧改动（事实）**：**编组 1+108→1+1（两制动源）**：SERVICE 1004→**701**、EMERG 1270→**899**、EBD 1279→**894**、EBD+坡度 1603→**1124**（改善 ~30%）；⇒ 对"EBD 不含坡度"已 ≤1000，对"EBD+坡度"仍差 124 kN（推断：3 源可到 ~0.80 MN，待算）。**速度区间改动**：仅 −4.9%~+3.7%，**不足以解决**。
- **对既有结果的定位（推断，量级有事实支撑）**：实测峰值 1312.9 / 1371.4 kN 落在 EBD（1279）与 EBD+坡度（1603）之间，峰位里程与坡度差分峰一致 ⇒ **C1/C3/C5/C6 只能挪峰位不能降峰，是"制动权限地板 + 坡度差分"的必然结果**，不是开关调度问题。
- **不做的事**：本节完成前不新增任何控制器开关/参数组合的全程实验；不以"挪峰位"为降峰判据。若确认 EBD 包络必须满足，则 1+108 @70 km/h 结构性不可行，唯一物理侧出路 = 改编组（≥2 制动源）。
- **相关**：ADR-014/021/036（车钩力定位与档位）、ADR-042（主 claim 口径）、ADR-053/054（C 系列开关）、`docs/logs/diagnostics/DIAGNOSTICS_2026-11.md`「车钩力准静态可达下界」。

## ADR-056 分段施加的制动距离代价与编组侧包络表；1000 kN 口径留白待定 - 2026-11-06

- **状态**：已计算并登记（**纯计算，不占机时、未改开关/配置/验收判据**）；**分级施加开关不实现，等口径拍板**。
- **背景（承接 ADR-055）**：ADR-055 给出"1+108 @70 km/h 若须 EBD 权限则结构性不可行"，并指出两条出路（分段施加 / 增加制动源）。本轮补上"分段施加愿不愿付距离"与"编组要改到什么程度"两笔账。
- **口径澄清（事实，先定语义再判读）**：`A_safe(v,d)=A_brake_safe(v)+A_gradient(d)`，70 km/h @−12‰ 为 `0.382 + (−0.1177) = 0.2643`；坡度只进"距离项"、不提升可用减速度。EBD 的 0.382 是**紧急制动能力**保证值，SERVICE（0.2935）**本就不在 EBD 距离承诺之内** ⇒ "SERVICE 停不进 EBD 距离"不是违规；日常调速的合法性由 **ATP 速度监督**（`v_allowed` 由 EBD 曲线反推）决定。
- **数值（距离，起 70 km/h@−12‰，D_EBD=801.8 m）**：单次 SERVICE 140 kPa **1 020.2 m（−218.3）**；2×70 kPa 间隔 3/5/8/10 s → **1 060.0/1 086.3/1 125.3/1 151.1 m**；单次紧急 **696.0 m（+105.8）**；紧急两段 5 s **756.9 m（+45.0）**；参考 140 kPa+ED **787.4 m（+14.4）**。
- **数值（峰值，同算例）**：单次 SERVICE 809.2 / 995.7 kN（起点 / s≈26.04 km）；2×70 gap3 **483.2/675.9**；gap≥5 **414.5/594.6**（**间隔 ≥5 s 峰值完全饱和，再拉长只付距离**，5→10 s 多付 64.8 m）；单次紧急 1 074.3/1 263.2；紧急两段 5 s 541.8/733.4。
- **二元结论（按口径分列，不选边）**：**口径 A（动作自身须停进 EBD 距离）**——SERVICE 路线**不可行且距离先破**（任何分段都差 218–349 m）；紧急路线**可行**，窗口 = 间隔约 **3–8 s**（<3 s 峰值破、>8 s 距离破）。**口径 B（EBD 仅为安全兜底、调速率由 ATP 提前量监督）**——**可行**：SERVICE 两段各 70 kPa 间隔 **3–5 s**，峰值 483/676（gap3）、415/595（gap≥5），距离代价仅 **+39.8/+66.1 m**（+3.9%/+6.5%），且不改变安全层紧急能力。
- **编组侧（新增表，1/2/3 制动源 × 四类包络；同一解析式、s∈[22,31] km 扫 50 m）**：1 源 1+108（10 988 t/1 317 m）436.4 / 1 016.4 / 1 252.6 / **1 575.5**；2 源 1+54+1+54（11 176 t/1 338 m）325.3 / 744.3 / 920.3 / **1 161.1**；3 源 1+36+1+36+1+36（11 364 t/1 359 m）297.1 / 556.2 / 685.5 / **863.1**。
- **结论**：① **"3 源能否接近 0.80 MN" = 能到 0.863 MN**（差 8%），到 0.80 需 4 源（~0.65 MN，**推断未算**）；② **守"全套包络（EBD+坡度）"必须 ≥3 源**（2 源差 161 kN、1 源差 575 kN），代价 = 编组 +3.4% 质量、+42 m 车长、结构改变研究对象；③ **守"常规调速包络"单源 1+108 已满足**（386–599 kN，余量 1.7–2.6 倍）。
- **留白（与指令第 4 条一致）**：1000 kN 守"全套包络"还是"常规调速包络"**由用户定**；在此之前**不写任何一条为"已达标"，不改验收判据**（仍为 `< 1312.9 kN` 有效峰值 + `route_completed`）。两种口径各自的下界与所需条件已并列写入诊断节。
- **不做的事**：不实现分级施加开关、不跑其活性校验/全程（结论依赖口径）；不新增其它参数组合穷举；不动 ED / 222 s 充风门 / 安全层。
- **相关**：ADR-055（下界模型）、ADR-014/021/036（车钩力定位）、`docs/logs/diagnostics/DIAGNOSTICS_2026-11.md`「分段施加的制动距离代价与编组侧补算」。

## ADR-057 C7 分级施加落地（默认关闭）；口径 B 为推定、非决议；六开关汇总表入档 - 2026-11-07

- **状态**：已实施（开关默认关闭）＋ 待用户确认口径（**推定 B，未成决议**）。
- **背景**：ADR-056 给出口径分歧（A 动作须停进 EBD 距离 / B EBD 仅作安全兜底、调速率受 ATP 提前量监督）并把口径留白。上级指示按 B 落地"分级施加"，同时要求：**B 未获用户明示前不得写成"已达标"**，C7 只做开关生效性验证。
- **本轮实施（事实）**：
  - `src/environments/train_env.py` 新增 `_ab_staged_command()` 与配置 `ab_staged_apply`（默认 `False`）、`ab_staged_gap_s`（默认 `3.0`）：SERVICE（140 kPa）首步降为 MIN（70 kPa），gap 秒后原样放行 SERVICE，触发 `train.py` 既有 notch 升级波（`_air_brake_upgrade_pending`）；**EMERGENCY 一律不拆**；只改 AB 指令，不碰 ED、不碰 222 s 充风门、不碰安全层。
  - `train_fleet_env.py` 透传两个键（`tr_cfg`）。
  - 单元级：`SERVICE→MIN`(0–3 s)→`SERVICE`(>3 s)、EMERGENCY 复位、RELEASE 复位 —— 已验证。
  - 诊断节 §八 第 1 条"分级施加暂不实现"为**当时状态**，由本条覆盖。
- **口径属性（关键，防误记）**：**口径 B 是推定采纳，不是用户明示决议**。ADR-056 的"留白待定"仍有效。因此：
  1. C7 的 6000 步活性校验只回答"开关是否生效"（首次分叉行号/时刻、AB 管压轨迹与断面力最大差）；
  2. **不写任何"口径 B 下达标"**，不改验收判据（`< 1312.9 kN` + `route_completed`）；
  3. 若用户改口守全套包络 → **C7 立即停**，转"3 制动波源编组"测算（下界 863.1 kN，编组 +3.4% 质量 / +42 m，ADR-056 表）。
- **新增归档（事实）**：诊断节新增「六开关（C1–C6）全程实测汇总」表——基线 1312.88 / 199 / 57.38 / 78.4 m / 27 140；C1 1295.99（−1.3%，超速 ×3）、C2 无作用对象、C3 1312.88（0%）、C4 1410.99（+7.5%）、C5 1817.73（+38.5%）、C6 1371.44（+4.5%，超速 ×16.5）。**六个开关全部只挪峰位/改编队松紧，无一降低 `b`**，与 ADR-055 下界（1003.9 / 1252.6 / 1575.5 kN）互相印证，作为论文"不做控制器微调"的直接依据。
- **后果**：C7 全程是否排入，取决于用户口径确认与活性校验结果；在此之前不排全程、不新增其它参数组合穷举。
- **相关**：ADR-055/056、`docs/logs/diagnostics/DIAGNOSTICS_2026-11.md`「六开关汇总」「口径 B 的推定属性与 C7 的定位」。

### ADR-057 补充-2026-11-07 · C7 6000 步活性校验结果（只验开关，不构成达标结论）

- **归档（事实）**：`fleet3_c7_staged_live6000_off_20261107`（开关关）与 `fleet3_c7_staged_gap3_live6000_20261107`（`ab_staged_apply=true`、`ab_staged_gap_s=3.0`），两轮同参、三件齐（`result.json` + `trajectory.npz` + `intervals.json`）。
- **开关生效性（过关）**：首次 AB 指令分叉 = **step 1752（175.3 s）**，第 2 列车 OFF `SERVICE` → ON `MIN`；断面力首次分叉 step 1783（滞后约 3.1 s）；管压系数分叉后 60 步内最大 Δβ = 0.0161。即"分级 + notch 升级波"链路真实工作，未绕过 ED / 充风门 / 安全层。
- **无结论（纪律）**：仅 600 s / 约 10.2 km 窗口、规则层固定策略，非全程剖面 → **不写"口径 B 下达标"、不写"C7 有效/无效"**，验收判据不变（`< 1312.9 kN` + `route_completed`）。
- **窗口内事实（只记录，不解释为机制）**：峰值 OFF 1073.82 / ON 1249.85 kN（+176.0）；超速步 199 → 235；`violations` 335 → 3 173；均速 63.85 → 64.08 km/h；最小净空 159.0 → 164.1 m；跟随列末速更低（16.17/15.84 → 14.07/13.43 km/h）。
- **后续**：按口径 B → 可排全程；用户改守全套包络 → C7 立即停，转 3 波源编组测算（ADR-056 表：863.1 kN）。

### ADR-057 补充-2026-11-07（二）· 时间分级方向废止，C7-S 空间分级落地；窗口判据未通过

- **方向更正（用户裁定，采纳）**：C7 的 600 s 负信号（+176 kN）不是"开关无效"，而是**实现方向错**——时间分级（全体先 70 kPa、gap 后放行 140 kPa）经 notch 升级波最终仍收敛到同一 b，只多一次跃变。**废止时间分级作为降峰手段**（`ab_staged_apply` 保留为已实现开关，但不再作为降峰候选）。
- **架构核对结论**：制动档位/管压/有效压力**均为每车独立数组**（`train.py:236, 599, 827-834`），但旧入口只有"源 + 波速传播"、多源硬编码双向 → 物理上支持空间分级、接口上不支持。**新增** `_apply_air_brake_command(stop_idx=)` + `TrainDynamics.apply_air_brake_zones(zones)` + `step_vehicles_ed_ab(ab_zones=)`；env 新增 `ab_zone_apply` / `ab_zone_count`（默认关，零回归）。
- **C7-S 实测（`fleet3_c7s_zone2_live6000_20261107`，k=2 前 SERVICE / 后 MIN，OFF 复用旧基线）**：首次分叉 step 1752（175.3 s），断面力分叉 step 1817；`physical_ab` 的段间档位差异持续 **163 个控制步**（非单步差）；600 s 峰值 **1105.20 kN** vs OFF **1073.82 kN（+31.4 kN）**；超速步 175（−24）、均速 63.96、净空 167.3 m（+8.3）、`safety_events` 16 774（−1 024）。
- **判据（用户增补，现已成为小窗口通行的硬门槛）**：600 s 窗口峰值**不得高于** OFF 基线 1073.82 kN → **未通过** → **不进入全程实验**；该归档仅作方向证据，不得引用为降峰结论。
- **假设 vs 实测（入 DIAGNOSTICS 表）**：k=2/3/4 的"用户公式"619.7/485.3/418.2（隐含非满段不制动）；70 kPa 下限 818.6/750.6/716.5；50 kPa 下限 711.1/607.2/555.2；实测 k=2 = 1105.2。**结论：单靠 k=2 前后二分不够，后续只做小窗口分配变体（k=3/4、后段改 50 kPa、前后反转）。**
- **3 波源编组方案**：`1+36+1+36+1+36`（机车 0/37/74，111 辆、11 364 t / 1 359 m、下界 863.1 kN）与论文改写清单已入 DIAGNOSTICS；属**研究对象变更**，须用户决策，未改任何 YAML/代码。
- **相关**：ADR-013（每台机车=智能体）、ADR-055/056、DIAGNOSTICS「C7-S 活性校验」「3 波源编组方案」。

### ADR-057 补充-2026-11-07（三）· k=3 两个变体：仅"后段 70 kPa"边际过窗口判据；50 kPa 因动态超调转差

- **实现（参数化，默认关）**：新增 `ab_zone_rear_notch`（`'min'` 默认 / `'cyclic'`，非法值构造期 `ValueError`），由 `_ab_zone_command()` 决定段 0 之外的档位；`train_fleet_env.py` 透传。段 0 固定 SERVICE；EMERGENCY 不分区；每段自段首发波、止于段末；不碰 ED / 222 s 充风门 / 安全层。构造期校验：k=3 → 段 `(0,37)/(37,73)/(73,109)`，`ab_active` 全列覆盖。
- **实测（6000 步，OFF 复用 `fleet3_c7_staged_live6000_off_20261107`，判据 = 窗口峰值 ≤ 1073.82 kN）**：

| 配置 | 归档 | 窗口峰值 kN | vs OFF | 准静态等效 | 实测/准静态**（口径已由补充（四）更正，本列作废）** | 判定 |
|---|---|---|---|---|---|---|
| k=3 后 MIN | `fleet3_c7s_zone3_min_live6000_20261107` | **1064.39** | **−9.4** | 750.6 | 1.418 | **通过（边际）** |
| k=3 后 CYCLIC | `fleet3_c7s_zone3_cyclic_live6000_20261107` | **1171.27** | **+97.5** | 607.2 | 1.929 | **不通过** |

- **副作用（同判据一并核对）**：k3-MIN 超速步 170（OFF 199）、均速 63.92（−0.1%）、净空 161.8 m（+2.8）、`violations` 92（OFF 335）→ 均不恶化；k3-CYCLIC 超速步 205（+6）、净空 152.6 m（−6.4）、`violations` 1 353（约 4 倍）→ 同时恶化。
- **首次分叉（两变体一致）**：`physical_ab` 首差 **step 1752（175.3 s）**；断面力差 >1 kN 于 step 1753/1754，>50 kN 于 step 1788/1796。组间档位共存 3 272 步（最长连续 2 678，k3-MIN）/ 2 782 步（最长连续 2 604，k3-CYCLIC）。
- **关键事实（比值分解）**：准静态等效随 k 与档位下调逐级下降（1003.9 → 818.6 → 750.6 → 607.2 kN），但动态超调同步上涨（69.9 → 286.6 → 313.8 → 564.1 kN）；**净变化 k2 +31.4、k3-MIN −9.4、k3-CYCLIC +97.5**。即"档位细分"带来的准静态收益被列内制动梯度造成的段界压缩力吃回。
- **k=3 不等于三档**：后两段共用同一后段档位，实际互异档位数仍为 2；k 的真实作用只是把 SERVICE 段由 1/2 缩到 1/3。若要真正的多档梯度，须给每段配不同档位。
- **口径更正**：补充（二）中"前 54 / 后 55"实为**前 55 / 后 54**（`divmod(109,2)` 段 0 多取 1）；"163 个控制步 / 断面力分叉 step 1817"阈值未记录，统一口径重算为 **2 093 步（最长连续 1 672）/ 力差 >1 kN 于 step 1754**。峰值与判定不变。
- **判定与待决**：仅 k3-MIN 具备排全程资格，但优势仅 0.9%（峰在 t = 570.3 s，近窗口末端）→ **是否排全程由用户决定**；k2 与 k3-CYCLIC 归档仅作方向证据。**本轮未跑任何全程；3 波源编组方案不动。**
- **相关**：ADR-055（下界结论）、ADR-056（编组包络）、DIAGNOSTICS「C7-S k=3 两个变体」。

### ADR-057 补充-2026-11-07（四）· k3-MIN 全程不通过；超调分解指向 ED/AB 协调而非制动波前

- **运行（事实）**：`fleet3_c7s_zone3_min_strict800_full_20261107`，`--steps 45000 --trains 3 --speed 70 --profile shuozhou_ningwuxi_beidaniu_49km --start-m 4290 --gap-offset-m 615 --finish-m 49600 --stop-on-coupler-kn 0`，三件齐；31 338 控制步、`elapsed_s=3133.8`、`full_route_completed=true`、均速 57.52 km/h、3 760 560 机械子步、0 未收敛、位移残差 7.56e-6 m、wall 2421.1 s。
- **四项判据（基线 = `fleet3_gap800_strict_production_70kmh_full_20261105`）**：`route_completed` true ✓；**有效峰值 1148.4 kN（−12.5%）** ✓；**超速步 278 vs 199（+39.7%）** ✗；**`min_gap_m` 75.10 vs 78.44（−3.34 m）** ✗ ⇒ **全程不通过（2/4 退化）**。峰值虽降，但代价明确，按既定判据不得写作"通过"。
- **两个峰值口径（必须分列）**：有效路段（领航头 ≤ 49.6 km）**1148.4 kN @ t=1443.2 s、尾列第 9 断面**（b=0.2601，`emergency` 58 车 + `min` 51 车，峰断面 `bpc=0.566` 波在途 ⇒ **EMERGENCY 波瞬态峰，非稳态分布峰**；准静态等效 931.1、超调 +217.2；相位 `V|R|B`）；不限路段（含越线后）**1246.6 kN @ t=2868.1 s、尾列第 25 断面**（= `result.json.summary.peak_kn`）。**引用时不得拿 1246.6 当有效峰值。**
- **窗口峰 1064.39（t=570.3 s）定位（事实）**：540–600 s 1064.4 / 600–660 s 942.1 / 660–720 s 1057.4 / 480–540 s 1032.4 ⇒ **是局部峰，不是主峰提前**（主峰晚 872.9 s，峰位由第 36 断面迁至第 9 断面）。
- **逐 100 s 超调（b=0.1961 稳态块，8 样本）**：+309.2 / +169.9 / +317.6 / +277.0 / +266.3 / +291.2 / +240.9 / +346.9，均值 **+277.4**、σ≈55 ⇒ **随相位波动，不是恒定值**；窗口内 313.8（前节）/309.2（按峰步实际 b 重算）属该区间偏高位置，未越界。b=0.3600（EMERGENCY）稳态块超调全为负；`b≈0` 时段剔除（常数项 216.6 无物理含义）。
- **分解方法与口径（本轮新增，纯分析未占机时）**：准静态部分改用**刚体解** `C_j = Σ_{i≤j}(m_i·a_r − T_i)`（容纳列内档位阶跃与车型分布），动态残差 `Σ_{i≤j} m_i(a_i − a_r)`；符号由动量平衡标定（准稳态步误差 0.0024 m/s²）。**峰瞬间不可精确分解**：峰步同一检验误差 0.307 m/s²（≈400 kN），故改为峰邻域 ±0.5 s 平均 + 单列"无法归因"。
- **k3-MIN 峰值四分（占瞬时峰值 1064.4）**：刚体/准静态（含**段界档位阶跃 + 坡度分布**）**446.3 kN（41.9%）**；持续相对加速度 **201.2（18.9%）**；亚秒波动（ED 往复 + 波前迁移）**260.3（24.5%）**；0.1 s 采样闭合差 **156.6（14.7%）**。
- **归因（事实）**：峰断面 **j=36 恰为段界（前 37 SERVICE / 后 72 MIN）**，峰时 `bpc` 全 1.000、压力变化率 0 ⇒ 波早已走完；71 个 ≥800 kN 断面峰中，波前沿 Δt 中位 **91 s**（不是波前峰），AB 指令 5.1 s vs 零假设 5.1 s（49%/49%，无关联），ED 斜坡 6.3 s vs 17.1 s（48%/27%，约 1.8 倍，有关联）；峰上升段紧随 ED 由 −538 回落至 −300 之后 1.0–1.4 s。
- **结论（推断）**：`313.8` 的可辨识动态来源是 **ED 与空气制动交替介入**，**制动波沿列传播不是峰值时刻的驱动项** ⇒ **下一个杠杆落在 ED/AB 协调**，多波源编组变更暂不成为首选；另有 41.9% 静态部分来自**段间档位差（0.149）本身**，属分配设计问题，与波前/ED 均无关。
- **推断边界**：以上为时序相关 + 量级一致性，非逐事件力分解；缺 0.0025 s 子步级逐断面力/加速度、逐车 ED/AB 指令时间戳，且 `controller_release_force_target_kn` / `controller_ed_hold_steps` 归档全 `nan`/0。
- **口径更正（三处）**：前节"实测/准静态 = 1.070/1.350/1.418/1.929"分母与峰时实际档位不匹配——OFF 与 k3-CYCLIC 峰发生在 EMERGENCY（b=0.3600），正确界 1205.5 kN，重算为 −131.7 / −34.2（均不构成超调），k2 +283.1、k3min +309.2；**"k3-CYCLIC 超调 +564.1"不成立**，其不通过依据改为峰值 1171.27 > 1073.82、超速 205 > 199、净空 152.6 < 159.0。
- **待决**：多波源编组改动仍等用户决策；k3-CYCLIC 判失败不重试；不再新增档位分配变体；本轮未改任何代码默认值（`ab_zone_apply` 仍默认关）。
- **相关**：ADR-055/056、ADR-014/021/036（车钩力定位）、`docs/logs/diagnostics/DIAGNOSTICS_2026-11.md`「C7-S k3-MIN 全程 + 动态超调分解」。

### ADR-057 补充-2026-11-07（五）· "紧急时禁用分区"前提不成立、缺陷实现已撤销；ED/AB 无交接空窗；档位细分静态收益有限

- **第 1 项前提核对（事实）**：k3-MIN 全程有效峰值 t=1443.2 s 的 "emergency 58 + min 51" 是**整列紧急波在途的瞬态剖面**：1441.2 s 16 车、1443.2 s 58 车、1445.7 s **109 车全 emergency**（峰后 2.5 s 波到列尾）。env 侧 `_ab_zone_command` 在 EMERGENCY 时本已返回 `None`（紧急期间不产生新分区命令），在途 MIN 波只会被更强档位升级 ⇒ **"分区在紧急时未失效"这一前提与归档事实不符**。
- **缺陷实现与撤销（事实）**：commit d9dae8b 在"分区→紧急"转换步清空 `_air_brake_pending`/`_air_brake_upgrade_pending`/`_air_brake_upgrade_delay` 以图重发整列波。单元复现：清空后 `_apply_air_brake_command(EMERGENCY, 0)` **入队 0 车**（源车已是 EMERGENCY，`train.py` 1094-1096 的源车秩条件为假）；6000 步窗口（`..._emgoverride2_live6000_20261107`）t=228.4–234.7 s 紧急波**冻结在 23 车**、后 72 车保持 MIN，EMERGENCY 命令时长 28.0 s → 60.2 s。⇒ 未实现"整列同一档位"，属**安全退化**，已 `git revert`（37f77e7），默认路径与 k3-MIN 逐位相同。
- **判据（事实）**：k3-MIN 基线窗口**本身已三项全过**（峰值 1064.4 ≤ 1073.82、超速 170 ≤ 199、净空 161.83 ≥ 159.0）；缺陷构建 1028.0 / 170 / 181.02 虽数值通过，但来源是紧急波冻结、后段少制动 6.3 s，**不得作为该改动的通过证据**，其归档不得引用。
- **第 2 项结论（事实 + 推断）**：38 个 ED 显著回落事件（幅度中位 124.1 kN、速率 1154.6 kN/s、回落到 439.4 kN 下限、事件时 AB 到位率中位 1.00）；17 个 ≥800 kN 局部峰中 83% 峰时 AB 到位率 ≥0.3、9 个峰 ED 落在 300.1–300.2 kN 下限；"ED 先撤、AB 未到"疑似空窗 n=19 且**全在缓解/自由运行相、0 个恢复 AB≥0.5** ⇒ **不存在交接空窗**，ED 回落时序开关（限幅/联动）**依据不成立、不实现**；推断上一节的 ED 相关实为"ED 到 −300 kN 下限 + AB 全列到位"共位，若做 ED/AB 协调，杠杆是 **AB 全到位时的 ED 幅值下限**。
- **第 3 项结论（事实）**：静态刚体解（c=0.1488 kN/(kPa·车)）现状 k3 段界阶跃 **246.5 kN**；4–6 档（ΔP 14–24 kPa）可压到 **164.5–183.2 kN**，代价为平均制动 +10–12%；保平均制动则尾档 48 kPa < MIN(70)。相对窗口峰 1064.4 仅 6–8% ⇒ **单靠档位细分不足以跨过 1000 kN，不排仿真**。
- **口径更正（补充）**：上一节"41.9% / 446.3 kN 静态段界阶跃"为刚体解合计，其中纯空气档位阶跃按本轮标定约 **246.5 kN**，其余约 200 kN 来自 ED 点力项与坡度分布；引用不得把 446.3 当"纯档位阶跃"。
- **未做（遵守边界）**：多波源编组、k3-CYCLIC 重试、档位分配变体穷举均未做；本轮未改任何默认值（`ab_zone_apply` 仍默认关）。
- **相关**：ADR-055/056、ADR-014/021/036、`docs/logs/diagnostics/DIAGNOSTICS_2026-11.md`「C7-S 紧急优先（第 1 项）：前提核对、实现缺陷与撤销；ED/AB 交接分析；档位细分静态估算」。

### ADR-057 补充-2026-11-08（六）· AB 全列到位时抬升 ED 下限（默认关）；400 kN 过窗口判据、450 kN 证伪；400 kN 已排全程

- **决策**：新增诊断开关 `ed_floor_ab_ready`（默认 **false**，零回归），仅在 AB 全列到位率 ≥ `ed_floor_ab_ready_ratio`（默认 0.9）时把循环期 ED 恒持下限由 300 kN 抬到 `ed_floor_ab_ready_kn`（默认 400）；其余时段保持 300 kN。实现落 `src/controllers/multi_loco_controller.py`（`_ab_arrival_ratio` / `_cyclic_ed_floor_kn`）两处同源替换（循环基线分支 + decompose 最终 floor 恢复），`src/environments/train_fleet_env.py` 透传，`src/evaluation/diagnose_low_level_control.py` 归档 `controller_ed_floor_kn`。ED 不新增 AB 源、不触碰充风门，抬高后仍经车钩力安全层与粘着/功率饱和。
- **依据（事实）**：17 个 ≥800 kN 窗口中 9 个峰时 ED 恰在 300.1–300.2 kN 下限且 AB 全列到位（上一节补充（五）第 2 项）；即制动需求被整体推给 AB，b 偏大。
- **窗口实测（6000 步，同参）**：ED400 → 峰值 **1048.59 kN**（k3-MIN 1064.39，−1.5%）、超速 170（=k3-MIN）、净空 161.96（≥161.83）、`violations` 92→**26**；ED450 → 峰值 **1070.52 kN（+6.1，退化）**、`violations` 119。分支进入 **12 240 车·步**（train0/1/2 占 91.3% / 77.5% / 35.2%）。生效期 |ED| 均值 437–491 kN、中位 438–485 kN。
- **判读**：**ED400 三项窗口判据同时满足 ⇒ 准予排全程**（已启动 `..._edfloor400_full_20261108`）；**ED450 不通过、不排全程**。400→450 有效 ED 分布几乎相同（400 已在多数高速步把分位顶到饱和），450 仅中列多约 50 kN 而峰值反而变大 ⇒ 该杠杆的有效自由度是"能否顶到饱和"，不是"限值再抬多少"（推断：ED 对峰值净效应非单调，中列继续加力加剧列间速度差）。
- **边界**：窗口不是全程验收；默认值未改（`ed_floor_ab_ready=false`）；全程结果出来前不得写"降峰达成"或"进入 1000 kN"。
- **相关**：`docs/logs/diagnostics/DIAGNOSTICS_2026-11.md`「小节-2026-11-08（三）」；ADR-014/021/036；`docs/logs/STATUS_2026-11-08.md`。

### ADR-057 补充-2026-11-08（七）· ED400 全程结果：有效峰 1183.9 kN，判不通过，开关保持默认关

- **结果（事实）**：`..._edfloor400_full_20261108` 三列全程有效峰（领航头 ≤ 49.6 km）**1183.9 kN**，高于 k3-MIN 的 **1148.4 kN（+3.1%）**；有效段 >1000 kN 步数 381→**473**、断面步次 2 254→**3 134**。峰位由「尾列第 9 断面、t=1443.3 s」迁到「**中列第 34 断面、t=1344.7 s**」。超速 278→170、净空 75.10→80.88 m、`violations` 8 104→6 460、均速 +0.82 km/h。
- **判定（决策）**：**ED400 全程不通过**（峰值劣于基线且 >1000 kN）。运营类指标改善不能抵扣峰值判据。开关 `ed_floor_ab_ready` **保持默认 false，不晋升**；不排 450 kN 全程（其 6000 步窗口已证伪）。
- **教训**：600 s 窗口的峰值收益（1048.59，−1.5%）**不可外推为全程结论**；ED 下限的有效自由度是"把 ED 顶到饱和"，400 kN 已饱和，继续抬（450）只会加剧列间速度差。剩余实质杠杆回到档位细分（静态峰收益 6–8%）。
- **相关**：`docs/logs/diagnostics/DIAGNOSTICS_2026-11.md`「小节-2026-11-08（四）」；`docs/logs/STATUS_2026-11-08.md`。

