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
- 结论：选 B。跨族对抗评审（`family_relation=different`）对 [ITSC_PAPER.md](file:///D:/Code/MultiAgent/traffic_rl_project/docs/ITSC_PAPER.md) 独立戳中 3 条硬伤（title-内层失配 / fair-MPC strawman / 证据薄）。
- 后果：
  - 集成遇 TRAE 密钥遮罩坑（`sk-...` env 被替换成 `\u2026`），已用 `LLM_CRED_FILE`<本地 key 文件路径>绕开（[server.py L52-72](file:///D:/Code/MultiAgent/Auto-claude-code-research-in-sleep/mcp-servers/llm-chat/server.py#L52-L72)）
  - 评审结论反哺论文：标题改 "Hierarchical Hybrid MARL"、补 "MPC+规则内层" 公平基线、20km/5 列结果补全指标升独立小节
  - 新依赖约束：OpenRouter 公端点 `independence_verified=unverified`；更严格独立需私有部署 ump/challenge 端点
- 相关：`docs/logs/diagnostics/DIAGNOSTICS_2026-09.md`（诊断-2026-09-02-ARIS 试点）；`docs/PROJECT_PIPELINE.md` ARIS 条目；ARIS 仓库 `docs/TRAE_ARIS_RUNBOOK_CN.md`

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
- **MPC 对比 Regime A/B（配套规范）**：MPC 预测模型是通用物理、坡度只是输入馈给，**不按坡道换 MPC 模型**。分两 regime——A（每线重喂正确 `grade_at`，公平标定，用于 main/E1 滚动窗/E3 模型精度）；B（不重辨识、专演"不泛化"，**必须声明 no-re-identification**，只用于 E4 跨线/E4-H 车钩异构）。论文 Protocol 逐实验标 A/B，否则视为对比失公允。
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
- 后果：`PROJECT_PIPELINE.md` ADR-014 阶段1 加 superseded 注明时域修正；`RESEARCH_POSITIONING.md` 若含"全程/拼接"表述依此覆盖修订；`AGENTS.md` 规范性问题区补本条指针。
- **执行闭环（2026-10-01）**：主训练配置 `configs/experiments/formation_ed_ab_3train_1plus1.yaml` 曾**未达本条硬要求**（`episodes: 120`、缺 `n_env`/`warm_start`/`long_eval_*`、注释仍留"多段 1200 步拼接覆盖"旧表述；`env_cfg.max_steps: 36000` 注释误标"53km 全程训练"）。已按本条对齐并验证：`episodes: 1400`（§4）+ `n_env: 4` / `parallel_traj_len: 0`（§1）+ `warm_start: true`（BC 热启动）+ `long_eval_interval: 50` / `long_eval_steps: 36000`（§2 完整剖面独立评估）+ `max_steps` 注释更正为"env 截断上限 / 评估口径（训练时域由 curriculum 决定，`TrainRunner` 每集覆盖）"。验证方式 = `--episodes 2` 覆盖短训（exit 0），`metadata.json` 实测上述字段全部生效（criterion：CLI 覆盖生效 ⇒ YAML 值可被正确解析）。**快速迭代用 `--episodes N` 覆盖，勿改 YAML 主值**。详见 `PROJECT_PIPELINE.md` 四改造「本轮补齐的完整性缺口」⑧、`REPRODUCIBILITY.md` §十。
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
  1. **静默从头重训**：`if resume_pt and Path(resume_pt).exists()` —— 路径写错/文件不存在直接跳过加载，**不报错、直接白跑数小时**。现实复现：`PROJECT_PIPELINE.md` 记载 5-seed 长训"原 launch resume 源已 MISS"（`final_seed{0..4}` 停在 ep 992/992/521/661/671）。
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
- **相关**：`docs/PROJECT_PIPELINE.md` P3「训练框架续训改造 - 2026-09-30」；`docs/logs/diagnostics/DIAGNOSTICS_2026-09B.md`「诊断-2026-09-30-续训框架端到端验证」；`docs/logs/learnings/LEARNINGS.md` LRN-20260930-004/005/006。

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
- **⑦ 遗留 / 长久计划**（见 `PROJECT_PIPELINE.md`）：① 按 C+B 重训（1400 ep × 5 seed）并出主表 —— **🟡 seed0 已于 2026-10-01 启动**（`scripts/launchers/launch_retrain_adr021_seed0.sh` ⇒ `outputs/checkpoints/formation/adr021_1400ep_seed0/`，登记见 `REPRODUCIBILITY.md` §十 / `PROJECT_PIPELINE.md` 长久计划 1）；② `ab_min_hold_s` 与 `ab_min_refill_s=222 s` 的实车核实 —— **`ab_min_hold_s` 已文献结案（2026-10-01，负结果：无运行期最小保持时长出处 ⇒ 保持 0.0 不激活；见 `DIAGNOSTICS_2026-10.md`「检索-2026-10-01」+ `REFERENCE_INDEX.md` 落地映射）；`ab_min_refill_s=222 s` 已由两独立来源同量级佐证（张二田 S6 实测 222 s + 大秦线报道 ≈210 s），仅余"实车数据正式核实"一项**需线下获取实车记录，非本环境可完成**；③ 完整预测式 safety filter（含 veto 阈值与梯度 AB 权限、来源感知、filter/策略一致性，Pfrommer 2022）；④ **立论侧已同步**：`RESEARCH_POSITIONING.md` §1.6「车钩力定位」的"待修订"标记已改为**"已修订并落地"**（含 `−6·min(pn−1,2)` / 上界 −12 / 仍不作均值最小化）；`AGENTS.md` 同项同步；`ITSC_PAPER.md` 已加**【2026-10-01 口径/目标/算法三重变更声明】**（正文旧数值不得作现行结果引用）。**待重训裁定的只是"该超限项权重是否保留/放大"**，不再是措辞修订。
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
  - `P0 三行基线`、`AB 通道裁定（--mask_lever ab）` 等基于**旧 ckpt + 旧带宽**的结论一并作废，随 A/B/C/D 重训后的复核同批重做（见 `PROJECT_PIPELINE.md` 长久计划）。
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
