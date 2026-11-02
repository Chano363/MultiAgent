---
title: 文献讨论成果（逐篇证据 + 指标口径 + 防追尾机制 + ATP 诚实边界）
date: 2026-10-12
status: active
owner: Owner + Agent
supersedes: 无（新建；`docs/RESEARCH_POSITIONING.md` §1.7 的「机制对照」「指标术语对齐」两小节正文迁入本文件并扩写，原位留指针）
---

> **角色**：文献讨论的**证据层**——每条结论都带本地文件与行号，可逐行复核。
> **分工**：立论**结论**（能说到哪一步、怎么写进论文）以 [`RESEARCH_POSITIONING.md`](../RESEARCH_POSITIONING.md) §1.2 / §1.5 / §1.6 / §1.7 为准；本文件只回答"**依据是什么、在哪一行、方向别写反**"。两者冲突时以立论文档为准。
> **何时读**：写 Related Work / 安全章节 / 指标表 / 评估图表标签前；核对某条文献结论的原始出处时；写 Introduction 的 GAP 段或回应"前人不足"时先看 §七（原文 + 中译 + 行号）。

## 目录

- [一、来源分级（读本文每一行的前提）](#一来源分级读本文每一行的前提)
- [二、指标术语对照（项目指标 → 论文用词 → 行号 → 方向）](#二指标术语对照项目指标--论文用词--行号--方向)
- [三、同类型论文的防追尾机制对照](#三同类型论文的防追尾机制对照)
- [四、ATP 诚实边界的证据链（代码锚 + 修复方案）](#四atp-诚实边界的证据链代码锚--修复方案)
- [五、论文可写的安全证据清单](#五论文可写的安全证据清单)
- [六、其余文献结论：只给指针，不复制](#六其余文献结论只给指针不复制)
- [七、核心文献结论处的不足（原文 + 中译 + 行号）](#七核心文献结论处的不足原文--中译--行号)

***

## 一、来源分级（读本文每一行的前提）

每条结论标注来源等级，**等级不同，可写进论文的强度不同**。

| 等级 | 含义 | 标记 | 写进论文的强度 |
| :--- | :--- | :--- | :--- |
| **P** | 本地文献原文，已定位到 `文件:行号`，可逐行打开复核 | `[P 文件:行号]` | 可直接引述（引号或转述均可） |
| **C** | 本项目代码/配置的实现事实，已定位到代码锚 | `[C 路径:行号]` | 只能写"我们实现为…"，**不是**文献贡献 |
| **I** | 由 P/C 推出的判断，文献未明写 | `[I]` | **必须**在论文里标为讨论/推测，**禁止**写成文献结论 |

三条纪律：

1. **P 未核实 = 不许用**。Grep 无命中时改用 Glob/LS 列目录确认，再下"不存在"的结论（PDF 提取文本会断词，如 `indica-tor`，须用宽松正则 + 读上下文）。
2. **C 不冒充 P**。ATP 分层、四条自辩、缺口描述全是本项目实现与判断，不是任何论文的结论。
3. **I 不冒充 C/P**。本文所有 `[I]` 条目在论文里只能进 Discussion / Limitations / Future Work。

**本轮一次关键复核（P 级，2026-10-12）**：全库 `docs/papers/**/*.txt|*.md` 检索 `safety violation rate` = **0 命中** ⇒ 该词**不是任何本地文献用词**，属自造词，禁用。

***

## 二、指标术语对照（项目指标 → 论文用词 → 行号 → 方向）

> 用途：写指标表、图表轴标签、Related Work 用词时**对齐文献原词**，不自造词。
> ⚠️ **方向列不能写反**——`1/TTC`、`TET`、`TIT` 三个都是**越小越安全**，直觉上容易记成"越大越安全"。

| 本项目指标 | 文献原词（英文） | 一手出处 | 方向（好在哪边） |
| :--- | :--- | :--- | :--- |
| 列距误差 | `spacing error` | Guo2025 `:43`（−8.3%）、Hu2026 `:1234`（±5% 达标）、Song2026 `:78`（收敛 0.66 m） | 越小越好 |
| 保持安全距离 | `safe distance` | Guo2025 `:63`、`:569`；Hu2026 `:189` | 保持即可 |
| 不碰撞 | `collision avoidance`（写成**约束**，非指标） | Hu2026 `:566` | 满足即可（0 违反） |
| 速度误差 | `velocity error` | Hu2026 `:1234`（±2% 达标）；Song2026 `:78`（0.44 m/s） | 越小越好 |
| 车头时距 | `time headway` / 可变车头时距 `VTH` | Guo2025 `:262`、`:368` | — （策略参数） |
| 碰撞风险 | `TTC` / `1/TTC` | Guo2025 `:832`（"critical safety indicator"）、`:834`（**higher 1/TTC = 风险更高**）、`:840`（临界阈值 = **3 s**，取自 Yuanzheng et al. 2023） | **1/TTC 越小越安全**；TTC 越大越安全 |
| 暴露型碰撞时间 | `TET`（time-exposed TTC） | Guo2025 `:1105-1125`（表 6）、`:1147-1153` | **越小越安全**（`:1152-1153`："higher TIT and TET … potentially compromised safety"） |
| 积分型碰撞时间 | `TIT`（time-integrated TTC） | 同上 | **越小越安全** |
| 车钩力 | `coupler force (kN)`（本项目口径 = **断面力**） | 本地编队类文献**无同类多列车钩指标** `[I]` | ≤ 1000 kN（硬底线，[ADR-018](../logs/decisions/DECISIONS.md)） |
| ATP 触发次数 | 无对应词（本项目主表安全指标） | 实现键 `safety_events` `[C]` | **越少越好**；= 控制失败次数（[§1.7](../RESEARCH_POSITIONING.md)） |

**用词裁定（已定稿，勿再议）**：

- 主表安全指标 = **ATP 触发次数**（`safety_events`）。
- 通称"安全违约（列距 < 5 m）" = `constraint violation`，**仅用于历史图表**，不进主表。
- 自造词「**追尾步数**」已从评估与图表删除（根因：2026-09 的决策只落在被 ADR-022 删除的旧入口，现行入口已补）→ 见 [`DIAGNOSTICS_2026-10.md`](../logs/diagnostics/DIAGNOSTICS_2026-10.md)「指标口径修复-2026-10-12」。
- 评估打印标签统一：车钩超限 / ATP 触发次数 / 空气制动步 / 速度带内占比 / 列距误差·最小列距（= spacing error / min spacing）。
- 训练进度行 `pkCpl/viol/band` 是**日志缩写**，不进主表、不进论文。

***

## 三、同类型论文的防追尾机制对照

> 用途：回答"同行怎么防追尾、我们的保证属于哪一档、论文怎么写才不失真"。
> 分级只看**保证强度**（有无数学/优化层硬约束），不看新旧。

### 3.1 总表

| 论文 | 机制 | 保证强度 | 一手出处 |
| :--- | :--- | :--- | :--- |
| Li2024 | CBF + CLF，安全约束经 QP 求解 | **硬**，有数学证明 | `Li2024_CBF_fulltext.txt:82-90`（CBF/CLF→QP）、`:166-168`（**Definition 4 Forward Invariant Set**） |
| Li2025 | 高阶 CBF（HOCBF），同族方法 | **硬**，有数学证明 | `Li2025_HOCBF_fulltext.txt:1-3`（题名：High Order Control Barrier Functions） |
| Song2026 | Tube-MPC：鲁棒管束 + 严格间距约束进优化器 | **硬**，有界 | `Song2026_TubeMPC_fulltext.txt:77-79`（spacing 收敛 0.66 m、speed 0.44 m/s） |
| Hu2026 | 安全距离进 reward 与约束，`collision avoidance` 作评价 | **软** | `Hu2026_PMMASAC_fulltext.txt:189`、`:369-372`、`:566`、`:1234` |
| Guo2025 | 可变车头时距（VTH）共识 + 1/TTC、TET、TIT 指标证据 | **软**（指标证据） | `Guo2025_MARL_PlatoonConsensus.txt:262`、`:832-848`、`:1105-1153` |
| Zhang2021 | APF 势场**写进奖励** | **软** | `Zhang2021_MADRL_TrainPlatoon.txt:152-158` |
| Wang2025（CCDC，多列 DMPC） | 追踪间隔 `D_i ≥ D_min` **进 MPC 硬约束**；车钩力同样进硬约束 `\|f_in\| ≤ 2000 kN` | **硬**（优化层约束，无稳定性证明章节） | `Wang2025_CCDC_DMPC_VC_HeavyHaul_fulltext.txt:443-453`（12e/12f）、`:404-407`（"both are the hard constraints"） |
| Ma2025（ITSC，多列 MARL） | 最小间隔按相对制动距离算 + **双层安全：安全保护曲线定动作范围 + 动作掩码**；越限另有罚项 Θ | **半硬**（动作级过滤，信号安全口径；**无车钩力**） | `Ma2025_MADDPG_HeavyHaulGroup_fulltext.txt:565-576`（dual-layer safety）、`:530-534`（奖励与罚项） |

### 3.2 分篇要点

**Li2024（CBF/CLF+QP）** — 硬保证的样板。CBF 处理安全、CLF 处理指数稳定，两者合起来把带约束最优控制**化成 QP**（`:82-90`），安全性由 **Forward Invariant Set**（前向不变性，`:166-168`）给出数学背书：只要初始状态在安全集内，之后永远在安全集内。

**Li2025（HOCBF）** — Li2024 同族（高阶版本），处理相对速度/高阶状态约束更自然。**注意**：这是同一研究线的后续，引用时不要当成两个独立证据源。

**Song2026（Tube-MPC）** — 硬保证的另一条路：用"管"包住不确定扰动，优化器里写死严格间距约束，闭环误差有界。实测收敛到 spacing 0.66 m / speed 0.44 m/s（`:77-79`）。**这是唯一"含车钩力约束"的多列工作**，引用边界见 §1.2 + ADR-030。

**Hu2026（MARL 虚拟耦合）** — 安全靠 reward 项 + 约束表达，`collision avoidance` 只作为评价语（`:566`）。达标判据写作 `spacing error within ±5%` + `velocity error within ±2%`（`:1234`）——**这个 ±5% 可以直接借来当我们的达标阈值口径**。

**Guo2025（MARL 编队）** — 用 VTH 共识（`:262`）维持间距，安全**证据**用 1/TTC + TET + TIT（不是硬约束）。三个方向都要记住：`:834` 明确 higher 1/TTC = 风险高；`:1152-1153` 明确 higher TET/TIT = 安全性受损；`:840` 临界 TTC 阈值 = 3 s。

**Zhang2021（APF 势场）** — 势场**写进奖励**（`:152-158`）提供先验。**本项目已判"生搬硬套"并禁用**，理由：对方场景 = 地铁平直 / 单质点 / 忽略车钩力 / 无坡度，可自由正负加速；本项目 = 朔黄长大下坡 + 循环制动，向下可制动、向上无牵引。出处见 [DECISIONS.md:98](../logs/decisions/DECISIONS.md)、[DIAGNOSTICS_2026-08.md:209-213](../logs/diagnostics/DIAGNOSTICS_2026-08.md)。

### 3.3 我们的定位（结论指针）

层2 + 层3 **比 MARL 同行硬**，**比 CBF 类少一个数学证明** ⇒ 论文写法 = 工程硬保证（ATP 不可释放 + 零穿透断言）+ TTC/TET 可比指标，**CBF 列 future work**（`safety_layer.py` 已预留接口，不占正文）。立论结论以 [§1.7](../RESEARCH_POSITIONING.md) 为准。

> **⚠️ 2026-10-20 限定（C-LIT-05 全文核验后）**："比 MARL 同行硬"**不能对 Ma2025 说**——Ma2025 已有动作掩码 + 安全保护曲线（信号级动作过滤）。可主张的差异只在**保证对象**：我方 `enforce_coupler` 硬约束的是**车钩力（物理量，≤1000 kN）**，Ma2025 的掩码只约束速度/间距（其单质点模型无车钩力）。因此"硬保证通道"这条 delta 必须写成"**车钩力**硬保证"，不得写成"只有我们有硬机制"。

***

## 四、ATP 诚实边界的证据链（代码锚 + 修复方案）

> §1.7 给**逐字口径**（论文里能怎么写）；本节给**证据链**（为什么只能这么写、改哪一行、改完能升级到什么口径）。
> 四层分工（层0 RL 定策 / 层1 ETCS 规则前瞻 / 层2 EBI 硬介入 / 层3 事后断言）与"编队不能只靠 ATP 的四条"见 [§1.7](../RESEARCH_POSITIONING.md)，此处不复制。

### 4.1 缺口 1：`d_safe` 隐含"前车不减速"

- **代码锚** `[C]`：`src/environments/train_fleet_env.py::_atp_safe_gap` 里 `EbdTarget(speed_mps=lead_v)` —— 安全距离曲线的**目标速度取前车当前速度**。
- **含义** `[I]`：EP 曲线按"前车保持当前速度"生成 ⇒ 只要前车真不减速（或只缓减速），本车就有足够距离；**前车紧急制动时，该曲线不构成保证**。
- **修前口径（只能这么写）**："对前车**保持速度 / 缓减速**安全"。
- **修法**：目标速度改 `max(lead_v − a_assumed·t, 0)`，`a_assumed` 用已标定实测紧急减速度 **0.38–0.43 m/s²**（最保守可取 0）。
- **修后口径（才能这么写）**："对前车**紧急制动**安全"。

### 4.2 配套缺口 2：只有位置–速度曲线，没有 closing-rate 监督

- 现状 `[C]`：ETCS 层只看"本车位置相对目标距离曲线"，不看**相对速度**。
- 后果 `[I]`：两车快速接近但尚未越线时，无任何提前动作。
- 建议：补 **1/TTC 阈值触发 service brake**（阈值可对标 Guo2025 `:840` 的 3 s；方向 = 1/TTC 越小越安全，触发逻辑别写反）。

### 4.3 影响面与时机（⚠️ 待拍板）

- 修缺口 + 补 TTC/TET **会改变 ATP 触发次数** ⇒ 历史评估数值不再严格可比。
- ⇒ 宜在 **1400 ep × 5 seed 主训练开跑前**一次性切干净口径。
- 状态：🟡 **待用户拍板**（截至 2026-10-12 未决）。

***

## 五、论文可写的安全证据清单

> 每条 = 指标 + **方向** + 口径来源。方向写反 = 结论反了，故单列一栏。

| 证据 | 口径 / 阈值 | 方向 | 出处 |
| :--- | :--- | :--- | :--- |
| ATP 触发次数 | `safety_events`（主表安全指标） | **越少越好** = 控制失败次数越少 | [§1.7](../RESEARCH_POSITIONING.md) `[C]` |
| 零穿透断言 | `assert rear_end_steps == 0`（非 0 该行作废） | 必须为 0 | [§1.7](../RESEARCH_POSITIONING.md) `[C]` |
| 断面车钩力 | ≤ **1000 kN** 硬底线 | **越小越安全**，破线 = 失败 | [ADR-018](../logs/decisions/DECISIONS.md)（口径）、[ADR-011](../logs/decisions/DECISIONS.md)（MT-2 统一） |
| 列距误差 | `spacing error`，可借 Hu2026 的 **±5%** 达标 | 越小越好 | `Hu2026_PMMASAC_fulltext.txt:1234` |
| 最小列距 | `min spacing` | 越大越好 | 本项目评估字段 `[C]` |
| 速度带内占比 | `band`（速度带一致） | 越大越好 | 本项目评估字段 `[C]` |
| 碰撞风险 | `1/TTC`，临界阈值 **3 s** | **越小越安全** | `Guo2025:834`、`:840` |
| 暴露/积分碰撞时间 | `TET` / `TIT` | **越小越安全** | `Guo2025:1152-1153` |
| 速度误差 | `velocity error`（可借 ±2%） | 越小越好 | `Hu2026:1234` |

**归因铁律**：安全**不归功 MARL**（ADR-014/021）。MARL 拿"少触发、少超限"，ATP 拿"最后一道不失守"。

***

## 六、其余文献结论：只给指针，不复制

> 这些结论**已有权威出处**，本文件不再复制正文（复制 = 双份登记必然漂移）。查原文走下表。

| 主题 | 去哪读 |
| :--- | :--- |
| 车钩力入模的文献空白边界（哪些工作确实忽略了车钩力、哪些没有） | [`RESEARCH_POSITIONING.md`](../RESEARCH_POSITIONING.md) §1.2 + ADR-030 |
| 车钩力定位（硬安全层 + 观测上下文 + 受控超限项） | `RESEARCH_POSITIONING.md` §1.6 + ADR-014 / ADR-021 |
| 车钩统一 MT-2（QKX100 移除） | ADR-011 |
| 指标口径 = 断面力（非每车净力） | ADR-018 |
| APF 势场禁用（"生搬硬套"判定全文） | [DECISIONS.md:98](../logs/decisions/DECISIONS.md)、[DIAGNOSTICS_2026-08.md:209-213](../logs/diagnostics/DIAGNOSTICS_2026-08.md) |
| ETCS 制动曲线（EBI/SBI 单调表 + searchsorted）来源 = ERA 2020 | [`REFERENCE_INDEX.md:67`](../REFERENCE_INDEX.md) |
| 最短充风 222 s 的出处与 `ab_min_refill_s` 落地 | [`REFERENCE_INDEX.md:29`](../REFERENCE_INDEX.md)、`:144`；Zhang2024 `:250-255` / `:287-295`（式 (9) `t_{b,j+1} − t_{r,j} ≥ T_a`） |
| `ab_min_hold_s` 文献检索**负结果**（全文/规章/实测均无可用出处 ⇒ 默认 0.0） | [`DIAGNOSTICS_2026-10.md`](../logs/diagnostics/DIAGNOSTICS_2026-10.md)「检索-2026-10-01」 |
| MPC 对比 = 同仿真器/环境/坡度数据/调参力度（ADR-037 废止逐线重标定 Regime A 协议） | ADR-037、ADR-022（`NMPCController` 唯一基线） |
| 训练/评估/总训练量三条时域不可混 | ADR-017 |
| 文献 → 技术点 → 本地文件的速查表 | [`REFERENCE_INDEX.md`](../REFERENCE_INDEX.md) |
| 文献全清单（题名 / DOI / 用途） | [`docs/papers/README.md`](README.md) |

***

## 七、核心文献结论处的不足（原文 + 中译 + 行号）

> **用途**：写 Introduction / Related Work 的 GAP 段、回应"前人不足"质疑、对照论文 Limitations 时，按行引用。
> **读表前提**：来源分级（P/C/I）与三条纪律见本文 §一；立论措辞只认 [`RESEARCH_POSITIONING.md`](../RESEARCH_POSITIONING.md) §1.2，事实措辞只认 [`CLAIM_LEDGER.yaml`](../CLAIM_LEDGER.yaml)。
> **两类不足必须分清**：
> - **自陈** = 作者在结论 / future work 里自己写下的局限 → 可引为 "the authors acknowledge / 原文自陈"。
> - **全文核实** = 作者未写、我方据全文核读得出（如"奖励与观测均不含车钩力"）→ 论文里只写**可核事实**，**禁止**写"作者忽视/未意识到车钩力"。
> **原文保真**：英文按本地提取文本逐词照录（PDF 断词、合并词已还原空格，未改字词）；中文文献为 PDF 提取文本，**已去字间空格，未改字词**；长引文用 `…` 明确省略。
> **禁**：写"首次/首创"，禁"文献都忽略"，否定命题一律写"据系统检索未见"（覆盖敞口见 [`NEGATIVE_SEARCH_2026-10-20.md`](../logs/verification/NEGATIVE_SEARCH_2026-10-20.md)）。

### 7.1 英文文献（原文 + 中译）

| # | 文献（本地文件） | 结论主张（要点） | 结论处的不足：英文原文 | 中文翻译 | 类型 | 证据（文件:行号） |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| 1 | **Song2026 MAPPO**（群组 MAPPO，C-LIT-02）`03_formation/Song2026_MAPPO_fulltext.txt` | 全数据驱动框架在安全、速度同步、能耗、平稳性上显著优于传统方法（结论 1–3 条） | 结论段**无任何 limitation / future work 陈述**。全文核实（决策目标）："The total reward r<sub>t</sub><sup>i</sup> for agent i at time t is defined as the weighted sum of three sub-reward terms: cooperative tracking, safety potential field guidance, and operational energy efficiency."；观测："o<sub>i</sub><sup>t</sup> = [v<sub>i</sub>(t), a<sub>i</sub>(t), Δv<sub>i,i−1</sub>(t), Δs<sub>i,i−1</sub>(t), e<sub>v,i</sub>(t), φ(s<sub>i</sub>(t))]" | 「智能体 i 在时刻 t 的总奖励定义为其三项子奖励的加权和：协同跟踪、安全势场引导与运行能耗。」；「第 i 个智能体的局部观测 = [本车速度、加速度、与前车相对速度、与前车相对间距、速度误差、线路特征]」 | 全文核实（无自陈） | `:1533-1558`（结论）、`:356-364`（奖励）、`:233-243`（观测）、`:1376-1379`（车钩力仅作评价） |
| 2 | **Wang2025 CCDC DMPC**（多列虚拟耦合，C-LIT-04）`03_formation/Wang2025_CCDC_DMPC_VC_HeavyHaul_fulltext.txt` | 多列 DMPC 达同速度、最小追踪间隔、最小列内力与能耗；随机扰动下仍有效 | "It will be our future work to further consider the highly nonlinear operation process of heavy-haul trains, and to propose a virtual coupling strategy that is more suitable for the cooperative operation of HHT group with long formations." | 「进一步考虑重载列车高度非线性的运行过程，并提出更适合长编组重载列车群组协同运行的虚拟耦合策略，将是我们未来的工作。」 | 自陈（future work） | `:751-767`（结论全段） |
| 3 | **Ma2025 GO-MADDPG**（多列车组 MARL，C-LIT-05）`03_formation/Ma2025_MADDPG_HeavyHaulGroup_fulltext.txt` | MIQP 参考速度 + 改进 MARL 给出各车驾驶曲线，3 列仿真验证有效可行 | "Future research will focus on the integrated rescheduling of timetables and collaborative optimization of speed curves for train groups, aiming to eliminate the hierarchical architecture between these two aspects and enhance the overall operational efficiency of heavy-haul railways."（全文为单质点动力学，结论与 future work **均未涉车钩力**） | 「未来研究将聚焦时刻表重排与群组速度曲线协同优化的一体化，以消除两者之间的分层架构，提升重载铁路整体运行效率。」 | 自陈（future work）+ 全文核实（单质点） | `:689-708`（结论）、`:339-345`、`:365-372`（单质点动力学） |
| 4 | **Guo2025 LSTM-MAPPO 车队共识**`03_formation/Guo2025_MARL_PlatoonConsensus.txt` | MARL + 共识控制维持编队内部一致性与对外部车的耦合关系；间距误差 −8.3% | "While the LSTM-MAPPO framework enhances platoon coordination, three limitations persist: first, homogeneous assumptions misrepresent mixed fleets. Second, V2X uncertainties degrade decision synchronization. Third, labeled data dependency limits scenario generalization." | 「尽管 LSTM-MAPPO 框架提升了编队协同，但仍有三点局限：其一，同质化假设无法刻画混合车队；其二，V2X 不确定性会削弱决策同步；其三，对标注数据的依赖限制了场景泛化。」 | 自陈（limitations） | `:1201-1232`（结论与未来工作段） |
| 5 | **Hu2026 PM-MASAC**（高铁虚拟编组 MARL）`03_formation/Hu2026_PMMASAC_fulltext.txt` | Mamba 增强状态表征 + CTDE，在跟踪精度、舒适性、稳态间距合规上优于 MASAC/MADDPG/MATD3 | "In terms of simulation environment modeling for data-driven training, future research could be extended in two directions. First, adopting a multi-mass model that captures inertial effects between carriages to enable finer motion control. Second, moving beyond simulation-based modeling to directly leverage real train operational data for training agents and learning control policies." | 「在面向数据驱动训练的仿真环境建模方面，未来研究可从两个方向扩展：其一，采用能够刻画车厢间惯性效应的多质点模型，以实现更精细的运动控制；其二，超越基于仿真的建模，直接利用真实列车运行数据训练智能体并学习控制策略。」 | 自陈（future work；即承认现模型不含车厢间惯性/车钩力） | `:1769-1804`（结论全段） |
| 6 | **Li2024 CBF/CLF-QP**（虚拟耦合安全控制）`03_formation/Li2024_CBF_fulltext.txt` | CBF + CLF 化约束优化为 QP，两车 VC 可达期望间距并保证安全 | "Future work will extend the proposed control method to more complex scenarios in the VC, such as the convoy entering or leaving the station, unexpected braking by the leader, as well as other realistic line profiles. …"（安全保证对象 = 相对距离，无车钩力） | 「未来工作将把所提控制方法扩展到虚拟编组中更复杂的场景，例如编队进站或出站、前车意外制动，以及其他真实线路纵断面。……」 | 自陈（future work） | `:647-654` |
| 7 | **Zhang2024 DQN 循环制动**（长大下坡，C-LIT-08）`02_rl/Zhang2024_DQN_CyclicBraking_Downhill.txt` | DQN + 优先经验回放生成满足约束的速度曲线，为长大下坡循环制动提供参考 | 模型层："In this study, the interaction forces between the cars are not taken into account when calculating the additional resistance."；自陈层："However, during the research phase, we failed to comprehensively consider all environmental factors that could affect braking effectiveness. In particular, weather conditions (such as temperature, humidity and wind speed), track conditions (such as track flatness and friction coefficient) and variations in train load were not within the scope of our research." | 「本研究在计算附加阻力时未考虑车辆之间的相互作用力。」；「然而在研究阶段，我们未能全面考虑所有可能影响制动效果的环境因素。特别是天气条件（温度、湿度、风速）、线路条件（轨道平顺性与摩擦系数）以及列车载荷变化，均不在本研究范围内。」 | 自陈（模型假设 + limitation） | `:151-156`（模型）、`:1007-1039`（结论与不足） |
| 8 | **Zhang2024 Q-Learning 循环制动**`02_rl/Zhang2024_QLearning_fulltext.txt` | 有限 Q 表 + 状态离散化，最小空走距离/最大效率的循环制动策略 | "During the operation of heavy haul trains, various factors such as track gradient, train formation, and on-board mass exert diverse forces on each train. However, in this study, the forces of the interactions between carriages were not considered in the calculation of additional resistance."；未来工作："the impacts of other environmental factors … should be further explored—for example, considering different weather conditions, track conditions, or train load conditions" | 「重载列车运行中，线路坡度、编组方式与车辆自重等因素会对列车施加多种作用力。然而本研究中，在计算附加阻力时未考虑车厢之间的相互作用力。」；「未来应进一步研究其他环境因素对循环空气制动方法的影响，例如不同天气条件、线路条件或列车载荷条件。」 | 自陈（模型假设 + future work） | `:128-133`、`:713-738` |
| 9 | **Wang2026 分层 RL**（单列重载长距离，C-LIT-03）`02_rl/Wang2026_hierRL_fulltext.txt` | 事件驱动任务分解 + D3QN 子策略，车钩力限制在 1100 kN，收敛回合数较全局训练提升近 40% | "However, more substantial environmental variations may still require retraining or online fine-tuning, which will be investigated in future work. Future research directions include extending this framework to heterogeneous multi-locomotive coordination scenarios and designing more scenario-specific tasks to achieve efficient parallel optimization." | 「然而，更显著的环境变化仍可能需要重新训练或在线微调，这将在未来工作中研究。未来方向包括把该框架扩展到异构多机车协同场景，并设计更多场景化任务以实现高效的并行优化。」 | 自陈（future work；对象为单列 340 km 线路） | `:1285-1352` |
| 10 | **Si2025 Dueling-DQN**（长陡下坡驾驶策略）`02_rl/Si2025_DuelingDQN_fulltext.txt` | 计及空气制动力时滞的多质点模型 + Dueling DQN，较 DQN 提速并缩短空气制动总时长 | "In order to improve the efficiency of model training, the following two measures are taken: the choice of time granularity is large, and 13 trailers are regarded as one section for processing, which leads to the reduction of simulation accuracy. These two problems need to be solved in the future work, and the actual train operation strategy should be further considered." | 「为提高模型训练效率，采取了两项措施：时间粒度取值较大，且把 13 辆货车合并为一个区段处理，这导致仿真精度下降。这两个问题需在后续工作中解决，实际列车运行策略也需进一步考虑。」 | 自陈（limitation） | `:608-624` |
| 11 | **Zhang2026 JAS 分布式制动**（车钩力补偿）`04_safety_mpc/Zhang2026_JAS_CouplerCompensation.txt` | 车钩力补偿器把带车钩力的列车模型降为车队模型，各车本地 CPU 独立设计控制器 | **注意：这不是该文自身的不足，而是它对 MPC 路线的批评**——"However, MPC requires solving a quadratic programming problem using methods such as those described in [19]-[21]. This makes it difficult to meet the real-time computational and memory requirements for implementing the controller in long heavy-haul trains. … In fact, all existing controllers based on a centralized (holistic) design scheme share these limitations and must be redesigned when car masses change." | 「然而，MPC 需要借助 [19]-[21] 之类的方法求解二次规划问题，这使其难以满足在长编组重载列车上实现该控制器所需的实时计算与内存要求。……事实上，所有基于集中式（整体式）设计方案的控制方法都存在这些局限，并且在车辆质量改变时必须重新设计。」 | 第三方批评（非自陈） | `:122`（引言）；该文自身结论节本地文本缺失（提取仅至 §II） |

### 7.2 中文文献（原文直引，无需翻译）

| # | 文献（本地文件） | 结论主张（要点） | 结论处的不足：中文原文 | 类型 | 证据（文件:行号） |
| :--- | :--- | :--- | :--- | :--- | :--- |
| 12 | **Song2026 Tube-MPC**（虚拟编组 + 传统空气制动，C-LIT-01）`03_formation/Song2026_TubeMPC_fulltext.txt` | 平缓坡道速度误差 0.44 m/s、间距误差 0.66 m；长大下坡最大车钩力约 330.4 kN，远低于 1500 kN 阈值 | 「然而，MPC 在求解优化问题时计算规模较大，尤其在面对列车规模扩大、运行环境更加复杂的情况下，时效性难以保障。未来可从多个角度入手进行优化，如引入快速求解器、高效近似算法、分布式并行优化策略、稀疏优化方法等，从而显著降低在线计算开销。此外，还可探索基于强化学习策略的预测控制方法，如基于深度强化学习的 MPC 近似策略，进一步提升系统的响应速度与自适应能力……」 | 自陈（limitation + future work） | `:2976-3013`（结论全段，含 4 条结论与不足段） |
| 13 | **Li2025 FSMPC + HMM**（地铁精准停车）`04_safety_mpc/Li2025_FSMPC_BrakeNotch.txt` | FSMPC + HMM 预测电空转换点，停车误差 ≤10 cm | 「然而，本研究存在一定的局限性，例如在仿真过程中未考虑复杂线路环境下的地铁车辆制动的影响，可能导致结果的适用范围受到限制。此外，仅选取了某一段线路，对该线路下的地铁车辆的制动过程进行分析，可能会影响结果的普遍性。」（场景为地铁平直线路，仅作"结论处自陈局限"的写法对照，不作对标） | 自陈（limitation） | `:213-218` |
| 14 | **刘博阳2022**（制动力判断标准与纵向冲动，C-DIFF-01 一手支撑）`01_coupler_physics/刘博阳2022_制动力判断标准_fulltext.txt` | 列尾压强显著影响缓解拉钩力；制动力判断须纳入列尾压强 | 「现行制动力判断方式中未考虑列车管压强分布对列车制动性能的影响，仅依靠试闸时列车的走行距离和降速情况判断列车制动力强弱」；「现行制动力判断方式不足主要表现在：①列车运行至 k20+500 时，在前序操纵中已经施加两次空气制动，由于缓解过程中再充风时间不同造成列车管压强分布在……」 | 指出"现有现场判据"的不足（非其自身不足） | `:236-240`、`:273-276`、`:446-450` |
| 15 | **赵紫宁2022**（空气制动精细建模，模型层）`01_coupler_physics/Zhao2022_AirBrakeRefinedModeling_Optimization_fulltext.txt` | 牵规等效模型不能表征 2 万吨组合编组制动力发挥全过程，需精细化建模 | 「面对 2 万吨组合编组重载列车，牵规简化等效模型已无法正确的表征空气制动力发挥的完整过程。针对目前基于精细化模型进行机理分析的评估方法研究较少的问题，并且为了保证操纵策略优化结果的正确性和有效性，开展空气制动过程精细化建模是很有必要的。」 | 指出"现有模型"的不足（非决策方法不足） | `:260-265`；另见目录 `:195`「3.1 牵规空气制动等效模型局限性分析」 |

### 7.3 我方核读、无自陈原文的（引用时必须标明"核读"）

| # | 文献 | 结论覆盖不到之处 | 证据 |
| :--- | :--- | :--- | :--- |
| 16 | **Lu2025 NMPC**（单列多机车协同，MPC 基线来源）`04_safety_mpc/Cooperative-NMPC…pdf` + 信息卡 | 对象为**单列内多机车**，无列间耦合；216 货车聚合为 8 组 + 2 机车 = 10 质点，非逐车车钩力 | 信息卡 `04_safety_mpc/Lu2025_CooperativeNMPC_MultiLoco.md:36-38`（原文 PDF 6 页本地，作者未写 limitation 段） |
| 17 | **Song2026 MAPPO**（同 7.1 第 1 行） | 车钩力**不进奖励、不进观测**，仅作 3.2.3 评价指标（峰值约 300 kN） | `Song2026_MAPPO_fulltext.txt:356-364`、`:233-243`、`:1376-1379` |

### 7.4 无全文、无法摘"结论处不足"的邻居（禁止据此写"作者自陈"）

| 文献 | 证据等级 | 现状 |
| :--- | :--- | :--- |
| 高济康2025《基于动态规划和深度强化学习的重载列车群组运行优化》（C-LIT-12） | 万方题录 + 摘要 | 摘要称可减小群组最大车钩力；**车钩力进奖励还是仅作评价未知**，无全文 |
| 谌墨2024《基于多智能体强化学习的虚拟编组列车协同控制方法》（C-LIT-13） | 万方详情页 | 关键词计数"车钩力 = 0"；无全文 |
| Wang2025 IEEE ICIRT（单列，车钩力进 reward，C-LIT-07） | 摘要 | 有 −9.64% / −28.77% 数值，无全文 |
| Fang2025 IEEE ISPA（C-LIT-06）、清华学位论文（C-LIT-09）、王建华2023（C-LIT-10）、多列车 DRL 学位论文（C-LIT-11） | 摘要/题录 | 同上 |

### 7.5 与本文件其余各节的接口：对应立论五问 (c) 三条不足

| 立论不足（`RESEARCH_POSITIONING.md` §1.0 Q3） | 本节支撑行 |
| :--- | :--- |
| ① 多列学习线里车钩力要么缺席、要么只是软目标 | 7.1 第 1、3、5 行（缺车钩力 / 现模型无车厢惯性）＋ 7.2 第 12 行、7.3 第 16 行（有硬约束但来自 MPC） |
| ② 有硬约束的方法不会学习（换线需重建模型） | 7.1 第 2 行、7.2 第 12 行自陈（MPC 在线计算规模大 / 长编组需进一步建模）＋ 7.1 第 11 行第三方对 MPC 实时性的批评 |
| ③ 单列车内多智能体 ≠ 多列车组 | 7.1 第 7–10 行（单列 RL 全部）＋ 7.3 第 16 行（单列多机车 NMPC） |

**剩余空格（C-GAP-01）唯一可主张的交集**：多列车组（智能体粒度 = 列车）× 车钩力进入 RL 决策目标 × MARL —— 写"据系统检索未见"，见 `CLAIM_LEDGER.yaml` C-GAP-01 与 [`NEGATIVE_SEARCH_2026-10-20.md`](../logs/verification/NEGATIVE_SEARCH_2026-10-20.md)。

<!-- 该文档整理/压缩于 2026-10-12；§七 并入于 2026-10-29（原独立文件 LITERATURE_GAPS.md 取消，零内容丢失） -->
