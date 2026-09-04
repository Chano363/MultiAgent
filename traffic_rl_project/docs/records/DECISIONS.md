---
title: 重大决策记录（ADR）
date: 2026-09-01
status: active
owner: Owner
---

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

## 已补录的历史决策（ADR-002 ~ ADR-007）
> 2026-09-01 从各诊断/验证章节提炼补录：ADR-002 限速区间[40,80]；ADR-003 加速度动作空间；
> ADR-004 分层架构重构（论文核心）；ADR-005 方案A回退+废弃APF；ADR-006 公平DQN；ADR-007 简化MPC双策略。
> 其余较细决策仍散落在 `VALIDATION_BASELINE.md` / `DIAGNOSTICS.md` / `VERIFICATION_LOGS.md` 各小节（留痕来源）。

---

## ADR-008 引入 ARIS 跨模型审阅通道（Auto-claude-code-research-in-sleep）- 2026-09-02
- 状态：实施
- 背景：论文重构期（MARL vs MPC 主轴）需**独立第二模型**对抗性审出单模型自审的盲区偏袒；现有 scholar-search MCP 只能检索，无法做裁决型评审。
- 选项与权衡：
  - A. 复制 ARIS skills 进项目 `.trae/skills/`：污染项目、升级难同步
  - B. `@` 引用 ARIS 仓库（不用），MCP 配 `llm-chat`，reviewer=OpenRouter `minimax/minimax-m3:free`（与 executor deepseek 跨族）→ 选用
  - 审阅后端选择：TRAE 无 codex MCP → 用 llm-chat 接 OpenAI 兼容端点（Minimal 依赖仅 httpx，`D:\Anaconda\python.exe`）
- 结论：选 B。跨族对抗评审（`family_relation=different`）对 [ITSC_PAPER.md](file:///D:/Code/MultiAgent/traffic_rl_project/docs/ITSC_PAPER.md) 独立戳中 3 条硬伤（title-内层失配 / fair-MPC strawman / 证据薄）。
- 后果：
  - 集成遇 TRAE 密钥遮罩坑（`sk-...` env 被替换成 `\u2026`），已用 `LLM_CRED_FILE`<本地 key 文件路径>绕开（[server.py L52-72](file:///D:/Code/MultiAgent/Auto-claude-code-research-in-sleep/mcp-servers/llm-chat/server.py#L52-L72)）
  - 评审结论反哺论文：标题改 "Hierarchical Hybrid MARL"、补 "MPC+规则内层" 公平基线、20km/5 列结果补全指标升独立小节
  - 新依赖约束：OpenRouter 公端点 `independence_verified=unverified`；更严格独立需私有部署 ump/challenge 端点
- 相关：`docs/records/DIAGNOSTICS.md`（诊断-2026-09-02-ARIS 试点）；`docs/PROJECT_PIPELINE.md` ARIS 条目；ARIS 仓库 `docs/TRAE_ARIS_RUNBOOK_CN.md`

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

## ADR-002 限速区间 [45,65] → [40,80] - 2026-08-17
- 状态：实施
- 背景：用户质疑限速区间不能仅凭1-2篇论文取；需核对研究对象/研究问题/行业标准。
- 选项与权衡：
  - [45,65]（樊运新3万吨参数）：吨位与对象（1万吨朔黄线）不一致，物理不可行（已验证车钩力超限540次/掉速）
  - [40,80]（Zhang2024 + 行业规则 + 《重载铁路设计规范》）：上限80=朔黄线实际线路限速；下限40=2万吨最小缓解速度
- 结论：改 [40,80]。依据：线路/行业标准与研究对象一致 + 物理验证（第1层成功，车钩力150kN/速度71km/h）。
- 后果：`train_fleet_env.py` v_max 65→80、v_min 45→40；82 测试过。
- 相关：`docs/records/VERIFICATION_LOGS.md`（V5.24）

## ADR-003 动作空间：目标速度 → 目标加速度 - 2026-08-15
- 状态：实施（后被 ADR-004 分层架构取代第1层策略，但"控加速度能学"原则保留）
- 背景：列间 RL 用"目标速度"动作，但长大下坡物理极限(16.7m/s)低于目标(20m/s)→动作饱和、Reward 无区分度→策略不学习（KL早停=0、best 不更新）。
- 选项与权衡：
  - 目标速度：动作被物理锁死，RL 学无可学（诊断：动作+1/+0 60步奖励与末速完全相同）
  - 目标加速度：直接影响物理，有真实学习区分度（对齐 Zhang2021/Hua2024）
- 结论：改用目标加速度 `a∈[-max_accel,max_accel]`（方案B）。Reward 单调改善40%（-885→-546），列间 MARL 首次真正学习协同制动。
- 代价：加速度更激进致 peakCoupler 偶尔超 1000kN（viol~1）。
- 相关：`docs/records/VERIFICATION_LOGS.md`（V5.10）

## ADR-004 最终架构：放弃"RL 学单列循环制动"→ 分层（第1层规则 + 第2层 RL 阈值协同）- 2026-08-22
- 状态：实施（论文核心结构）
- 背景：RL 学单列循环制动结构性失败（缓解波长时延6s→PPO信用分配失效 + 车钩力多体耦合→探索即爆炸）。论文/行业标准均用规则循环制动。
- 选项与权衡：
  - RL 学单列循环制动：失败（时长/信用分配+碰撞）
  - 分层：第1层规则循环制动（领域最优 523kN）+ 第2层 RL 只做阈值协同（v_max_adj/v_min_adj ±5km/h，不动 throttle）
- 结论：分层重构（`HierarchicalController`）。协同增量 M1(+33494) vs M3(-76548) = **+110042**；M1 追尾0/车钩力864kN/间距182m 全健康，M3 追尾392。
- 后果：成为论文核心创新点；83 测试过。
- 相关：`docs/records/DIAGNOSTICS.md`（诊断-2026-08-22 最终战略分层重构）

## ADR-005 方案A 人为坡段错开 → 回退；废弃 APF 势场控制器 - 2026-08-20
- 状态：已回退
- 背景：方案A（`start_offset_m` 中段起步 + `spacing_m` 静态坡段错开）是人为制造的相位差，偏离"各列同坡段起步、随间距保持自然产生动态相位差"方针，且前列/后列缓解不同步→车钩力持续超限(1218-1226kN)+M1 不收敛。
- 选项与权衡：
  - 引入 Zhang2021/Guo2025 APF 势场控制器解耦重构：生搬硬套（他们=地铁平直/单质点/忽略车钩力/无坡度，可自由±加速；而长大下坡向下可制动、向上无牵引）
  - 移除人为错开，恢复普通场景（各列同坡段起步）
- 结论：废弃 APF，回退移除 `start_offset_m`/`spacing_m`。正确分层 = 列间 RL 宏观协同 + 列内规则循环制动 + 车钩力安全层。35 测试过，无回归。
- 相关：`docs/records/DIAGNOSTICS.md`（诊断-2026-08-20 E25 方案A / 回退方案A）

## ADR-006 引入公平 DQN baseline（M-DQN-fair）消解审稿质疑 - 2026-08-23
- 状态：实施
- 背景：主结果用朴素 M-DQN（Zhang2024 式：学单列循环制动、无安全层、无协同）对标，审稿人可质疑"DQN 输是因为没协同/没安全层而非 DQN 不如 MAPPO"。
- 选项与权衡：
  - 保持朴素 DQN：公平性不足，结论易被击穿
  - 补同架构公平 DQN：第1层规则循环制动 + 车钩力安全层（与 M1/M3/M4 完全相同），第2层换每列独立 DQN 输出离散 coor_adj（同 obs/reward，完全同架构）
- 结论：引入 M-DQN-fair。完整评估仍追尾229步(固定65)/89.2±109.4(随机化)，与 M3 相当、远不如 M1(MAPPO, 0追尾)；车钩力守住900kN（证明安全层生效，排除干扰）。
- 相关：`docs/records/DIAGNOSTICS.md`（诊断-2026-08-23 公平DQN baseline）

## ADR-007 简化 MPC baseline 双策略（Yang2025 参考线 + 公平 DQN 主基线）- 2026-08-23
- 状态：实施
- 背景：需对标 MPC 范式，但完整多质点 QP MPC 复现代价高。
- 选项与权衡：
  - 用简化 MPC 作严格公平对比：预测模型粗糙+无车钩力约束编码，不公平
  - 双策略：主 baseline 用公平 DQN（干净）；Yang2025 作文献参考线引用其单列 MPC 数据；说明"完整 MPC 复现为未来工作"
- 结论：采用双策略。诚实呈现简化 MPC 在多列协同的固有挑战（需精确车钩力预测模型），但不冒充公平对比。
- 相关：`docs/records/DIAGNOSTICS.md`（诊断-2026-08-23 简化 MPC 协同 baseline）

## ADR-009 智能体分解重构：多机车分布式动力 × 电空双制动分工（融合） - 2026-09-02
- 状态：决策（方向已定，待仿真器改动方收尾后实施）
- 背景：导师批评"3 列 1+0 群组叫多智能体不合适"——1+0 每列仅 1 台动力源，把"列车"当智能体本质是 3 条曲线的宏观优化，与单体优化缺乏本质区分，'多智能体' 名不符实（宋宗莹2026 同风险）。需重构智能体分解，锚定在**物理独立动力源**上。
- 选项与权衡：
  - **A. 1+0→1+1/多机车分布式动力**：多台物理动力源的牵引/电制动/缓解错峰分配=真多智能体。依据 Tang2020/姚小沛2013/赵紫宁2022/樊运新2024。优点：物理锚定扎实；代价：改编组+多机车协同训练。
  - **B. 电制动/空气制动分离为双智能体**：同一列内 ED(连续)/AB(离散) 分工决策。依据 Yu2022（电空联合制动，Actuators 11(6)145）。优点：列内即多智能体、不依赖多车；风险：需论证为何不单策略多输出头。
  - **C. A×B 融合（选用）**：多机车作"体"、每机车同时决策电/空制动→列内真多智能体分工，与既有分层兼容。最扎实；代价最大，需彻底重构编组+环境+训练。
  - D. 先不做仅立论：工作量最小，但无法回应导师批评、无法产出新结果。
- 结论：选 **C（融合）**。渐进式：立论（本文档+RESEARCH_POSITIONING 1.3.1）→ 仿真器稳定后编组改造 → 短训冒烟 → 全量训练。
- 可行性（2026-09-02 确认）：`TrainConsist.vehicles` 按序 + `locomotive_indices` + `LocomotiveParams` → 多机车原生支持；ED/AB 已分离 + `ab_sources` 多源。改动面集中于 `train_env.py` 编组 + 动作空间，不涉积分核心。
- 代价/风险：动作空间维度上升（每机车独立电/空决策）→ 样本复杂度上升、训练更久；需论证"多机车+电空分离"协同相比"单机+单控"的**增量收益**才能立住（预期：错峰缓解降车钩力）。
- 暂缓原因：`train_env.py`/`train.py`/`coupler.py`/`tractive.py` 为他人改仿真的未提交（M）状态，不冲突不改造。
- 相关：`docs/RESEARCH_POSITIONING.md`（1.3.1 立论）；`docs/PROJECT_PIPELINE.md`（立项）；`docs/records/DIAGNOSTICS.md`

## ADR-009.1 阶段方案修订：空电分工（B）先行、多机车（A）后叠 - 2026-09-03
- 状态：决策（修订 ADR-009 实施路径，聚焦"空气制动难优化如何解决"）
- 背景：①导师提醒"空气制动很难优化"；②用户确认先解决"空气制动难优化"技术问题，搁置论文措辞；③emergence 实验证伪"标准 RL 学精细错峰时序"（共享策略收敛对称解）；④A×B 全自由度融合训练风险高。
- 结论：**C（融合）降级为最终目标；本阶段先做 B（空电分工），且先单列 1 机车（不绑多机车）；A（多机车=智能体）后叠**。理由：解决"空气制动难优化"不需要多机车，单列即可更快验证；多机车是"多智能体锚定"的独立目标，可解耦后置。
- **空电分工技术方案（4 层）**：
  1. **规则化档位**：AB 档位由规则循环制动触发（超上限→SERVICE、低于下限→缓解、紧急→EMERGENCY），不进连续优化（第 1 层已做）。
  2. **ED 优先 + AB 兜底**：ED 连续（即时、无波速、功率+粘着约束）承担主制动；AB 仅当 ED 不足（需求减速度 > ED 上限）或失效时按规则档位补位——把难优化的 AB 使用量压到最小。
  3. **AB 状态作观测**：暴露 `train.py` 的 `_air_brake_releasing`（缓解剩余）、`_brake_segment`（段序号）、充风状态进 obs，让策略"感知"AB 动态而非"预测"它。
  4. **RL 只学宏观分配**：RL 学"当前用多少 ED / 是否触发 AB / 协同偏移"，不学 AB 连续档位（若未来要学，用离散动作空间匹配 AB 离散性）。
- 验证前提：验证"多次循环制动下空电分工有效性"需要足够循环制动次数 → **评估时域须升级为完整 23.8km**（当前 3000 步只覆盖 ~5km，见 WP2）。
- 门控：环境冒烟 → 短训验证"ED 优先、不足转 AB"分配可学 → 通过才全量训练；失败止损并记录（DIAGNOSTICS）。
- 相关：`docs/records/DIAGNOSTICS.md`（emergence 证伪 / MPC 缩放）；`.trae/documents/plan_2026-09-03_空气制动难优化解决-空电分工.md`