# 负结果检索台账（Negative Search Ledger）—— C-GAP-01

> 用途：为 claim `C-GAP-01`（否定命题）提供**可审计**的检索证据。台账缺失时
> `scripts/check_claim_ledger.py` 直接报错——这是刻意的：**"没找到"只有留下检索记录才算证据**。
> 归口：`docs/CLAIM_LEDGER.yaml` → `claims[C-GAP-01].search_ledger`。
> 纪律：本文件 append-only；每次复跑新增日期小节，不改旧行。

## 台账-2026-10-20 英文通道首轮

- **检索通道**：Semantic Scholar（含 DBLP 映射）+ arXiv（scholar-search MCP 统一出口）
- **未覆盖通道（重要）**：CNKI / 万方 / 维普、IEEE Xplore 全库检索、Google Scholar、Web of Science。
  本节结论只覆盖**英文可检索区**，不得表述为全语种检索完成。
- **检索式与结果**：

| # | 检索式 | 年份 | 命中 | 与本 claim 相关的排除理由 |
|---|---|---|---|---|
| S1 | `virtual coupling heavy haul train coupler force multi-agent reinforcement learning` | 2022-2026 | 16 | 仅 Ma2025 ITSC（GO-MADDPG）相关：多列 MARL，但摘要**无车钩力**（safety constraints / tracking interval / collision avoidance）→ 不占"车钩力进 RL 目标"格；其余为不相干 MARL/机器人论文 |
| S2 | `long steep downhill heavy haul train coupler force in-train force reinforcement learning control` | 2022-2026 | 15 | 相关 5 条全部为**单列**：Wang2025 ICIRT（DQN，车钩进目标）、Lu2025 ICIRT（NMPC 多机车）、Zhao2026 CCDC（电空协调 MPC）、Liu2024 VSD（操纵优化）、Wei2025 TTE（AILC）→ 均不占"多列车组"格 |
| S3 | `train platoon cooperative control reinforcement learning in-train force heavy haul freight` | 2023-2026 | 12 | 相关 2 条：Ma2025 ITSC、Fang2025 ISPA（车厢级 APF+DRL，**单列**）→ 不占"多列车组"格 |
| S4 | `multi-train cooperative control heavy haul virtual coupling reinforcement learning coupler force constraint` | 不限 | 13 | 与 S1/S3 命中集合相同，无新增 |

- **结论（本通道）**：未检索到"车钩力进入**多列车组**多智能体 RL 决策目标（状态/奖励/约束）"的工作。
  最近邻三条：Song2026 MAPPO（多列 MARL，车钩力不进目标）、Song2026 Tube-MPC（多列 + ±1500kN 硬约束，非 RL）、Ma2025 ITSC（多列 MARL，车钩力待核）。

## 已知风险敞口（必须在论文措辞中体现）

1. **中文通道未跑** → 中文文献（如宋宗莹一脉、西南交大/北交大团队）只能靠本地 PDF 与既往人工检索留痕，
   而 Song2026 两条恰为中文文献——**主战场就是中文侧**，这是最大敞口。
2. **Ma2025 ITSC 闭源**（DOI `10.1109/ITSC60802.2025.11423646`）→ 其 MIQP 的"safety constraints"是否含车钩力未知，
   一旦含，C-GAP-01 需再次收窄。
3. 检索为**关键词召回**，非引文网络回溯（未做 forward/backward citation chasing）。

## 复跑记录

- 2026-10-20：S1–S4 首轮（英文通道）。claim 状态 = `pending_cn_channel`。

## 台账-2026-10-20 中文通道首轮（网页代理，非结构化 CNKI）

- **通道**：通用网页检索（zh-CN）。**不是** CNKI/万方高级检索——本机未装浏览器自动化 CLI（`agent-browser` / `playwright` 均缺失），结构化检索待安装后补跑。
- **检索式与结果**：

| # | 检索式 | 命中相关 | 排除理由 |
|---|---|---|---|
| Z1 | 重载列车 长大下坡 车钩力 多智能体强化学习 群组 协同控制 | 4 | Song2026 MAPPO（已知，C-LIT-02）；清华学位论文（C-LIT-09，单列多机车）；王建华2023（C-LIT-10，单列组合列车）；IMUT 学位论文（单列循环制动，车钩力仅进仿真环境）→ **无一为多列车组** |
| Z2 | 重载列车 虚拟编组 车钩力 强化学习 多列车 协同 | 3 | 同上三条；其余为 3.5 万吨群组试验新闻稿（非文献） |
| Z3 | 重载列车群组 编队运行 车钩力 多智能体 强化学习 奖励 2026 | 2 | Song2026 MAPPO；CN120178720A 专利（分层多智能体，单列车内车辆级）→ 不占格 |
| Z4 | 多列车 协同 编队 强化学习 车钩力 约束 学位论文 列车群 | 4 | 万方《基于深度强化学习的多列车运行协同优化控制方法》（C-LIT-11，多列车 + DRL 但主题为节能/运行协同，摘要无车钩）；高速列车群 DRL 两篇（客专、无车钩）→ 不占格 |

- **结论（本通道）**：仍未检索到"车钩力进入**多列车组** MARL 决策目标"的工作；C-GAP-01 的格子在本通道保持空。
  **新增邻居 3 篇**（均已入台账）：C-LIT-09（多智能体 RL + 车钩力信息，但智能体粒度 = 单列车内多机车）、C-LIT-10（长大下坡 + RL + 车钩力，单列）、C-LIT-11（多列车 + DRL，无车钩）。
- **边界判定口径（写论文时必须带上）**：本 claim 的"多列车组"指**智能体粒度 = 列车**；单列车内部的机车级 / 车厢级多智能体（C-LIT-06 / C-LIT-09）**不构成占位**，但必须在 related work 主动引用划界，否则审稿人会用"多智能体"口径质疑。

## 台账-2026-10-20 中文结构化通道：万方智搜（可用）

- **通道**：万方智搜 `https://s.wanfangdata.com.cn/paper`（Playwright + Chromium，无头；**通过**，无需验证码）
- **CNKI 状态**：`kns.cnki.net` 被 `captchaType=blockPuzzle` 滑块拦截（探针实测跳 `/verify/home`，页面无检索框）→ **结构化 CNKI 仍未覆盖**。

| # | 检索式 | 命中 | 结论 |
|---|---|---|---|
| W1 | 重载列车 车钩力 强化学习 多列车 | 6 | **C-LIT-12 高济康2025（多列群组 + DQN + 车钩力为优化目标之一）**；C-LIT-10 同组（刘文韬2025 博士、杨航2022、齐嫣然2023、汤辉玥2020=Tang2020 系）；专利 CN120178720A |
| W2 | 车钩力 多智能体 强化学习 | 4 | **C-LIT-13 谌墨2024（多列车组 + MADDPG，车钩力=0 不占格）**；刘文韬2025；杨航2022；齐嫣然2023 |
| W3 | 列车群组 强化学习 车钩力 | — | 与 W1 集合重叠 |
| W4 | 长大下坡 车钩力 强化学习 | — | 单列 RL 簇（刘文韬/杨航/王建华2023） |
| W5 | 虚拟编组 车钩力 强化学习 | 2 | C-LIT-13；C-LIT-12 |

- **结论（本轮修正）**：
  1. 「多列车组 + **RL**（单智能体）+ 车钩力为优化目标」 = **已占位**（C-LIT-12 高济康2025）。此前"车钩力进 RL 目标"半格空白的表述**作废**。
  2. 「多列车组 + **MARL**」 = 已有（C-LIT-13 谌墨2024 / Song2026 MAPPO / Ma2025 ITSC），但均**无车钩力**。
  3. 三要素交集（多列车组 × 车钩力进 RL 目标 × MARL）在本轮全部通道仍**未命中**。
- **待核（升格前必须做）**：C-LIT-12 全文——车钩力是进 DQN 奖励项（`r_t` 组成）还是仅作事后评价；若是奖励项，本 claim 继续收窄为"MARL 维度"，措辞改为"首个把车钩力引入**多列车组多智能体** RL 目标"。

## 敞口更新（2026-10-20）

- 已覆盖：英文 S2 + arXiv（S1–S4）、中文网页代理（Z1–Z4）。
- **未覆盖**：CNKI / 万方**高级检索**（结构化、可按主题词 + 来源类别过滤）、Web of Science、Google Scholar、引文网络回溯（forward/backward）。
- 因此 claim 状态 = `pending_cn_structured`，措辞仍锁在"据系统检索未见（英文 + 中文网页通道）"。

## 台账-2026-10-20 全文核验补记（非检索通道，用于把邻居从题录级升为全文级）

> 本节不是新检索通道，而是**证据等级升级**：把已命中邻居从「题录/摘要级」核到「全文级」，
> 消除 C-GAP-01 的"待核"敞口。两篇全文由用户自出版社下载，入库
> `docs/papers/03_formation/`（PDF + `*_fulltext.txt`，双栏按词坐标重抽）。

### N1｜C-LIT-04 Wang/Zhan/Zhang（IEEE CCDC 2025，DOI 10.1109/CCDC65474.2025.11091006）

- **全文核实**：5 列虚拟耦合，每列 2 万 t（2×HXD2 + 214 C80B、长 2.7 km），大秦线 653 km 场景；
  模型 = n 质点 + n−1 车钩**弹簧-阻尼**（工程上取阻尼 `d=0`）；fence 法把邻车并为刚体降阶。
- **纠正摘要级误判（重要）**：车钩力**不只**进代价项——(10e)/(12e) 即硬约束 `|f_in| ≤ f_max = 2000 kN`，
  原文自述 "both are the hard constraints"。此前 C-LIT-04 记"非硬约束"，
  `DIAGNOSTICS_2026-10.md:1429`/`:1434` 同节自我否证，**一律以本节为准**。
- **对 claim 的影响**：「多列 × 车钩力硬约束」在 MPC 侧有**两个独立先例**
  （Song2026 Tube-MPC ±1500 kN、本篇 ±2000 kN）→ 该格不是空白；但两者都**不是 RL**，
  C-GAP-01 三要素仍缺"MARL"。

### N2｜C-LIT-05 Ma/Zhou/Song/Wu/Dong（IEEE ITSC 2025，DOI 10.1109/ITSC60802.2025.11423646）

- **全文核实**：3 列重载群组、列车长 1567 m、v_max 80 km/h、朔黄神池南—龙宫真实数据；
  MIQP 生成参考速度 + GO-MADDPG（HER 目标导向 + 协同避撞 + 动作掩码）。
- 车辆模型 = **单质点**（`a = (μt·Ft − μd·Fd − μc·Fc − R)/M`）；状态 9 维无车钩力；
  奖励 = −(w1Z1+w2Z2+w3Z3) + 越限罚 Θ；约束仅牵引/制动上限、空电互斥、最小追踪间隔（RBD）、限速、TSR；
  **结果指标无车钩力**（目标值/运行时分/能耗/空气制动时长/速度偏差/距离偏差）。
- **结论**：原"闭源、车钩力是否入模待核"**解除**——该篇坐实「多列车组 × MARL，缺车钩力」，
  是 C-GAP-01 反例侧的**英文全文级**证据（此前同格只有中文题录级 C-LIT-13）。

### 敞口更新（同上）

- 仍**未覆盖**：CNKI 结构化检索（滑块拦截）、万方高级检索、Web of Science、Google Scholar、引文网络回溯。
- C-GAP-01 三要素交集结论**不变**；本轮两篇核验只**加强**了"最近邻各缺一角"的排除理由。
