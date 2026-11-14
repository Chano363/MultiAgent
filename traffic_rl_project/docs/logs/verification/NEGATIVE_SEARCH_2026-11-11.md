# 负结果台账 · 2026-11-11：多列车编队 × 档位级离散动作 × MARL

> 用途：为 **ADR-065 贡献 ②「档位级 MARL × 多列编队」** 提供"据系统检索未见"的可审计依据（ADR-044 决策 4）。
> 措辞上限：**"据系统检索未见（截至 2026-11-11，通道 S2 / arXiv / Web / 本地全文库）"**；禁用"空白/首创/首次"。

## 一、命题（要判定"是否已有"的三个要素交集）

**要素 A**：多列车编队（智能体粒度 = 列车，或 ≥2 列车的群组协同）
**要素 B**：档位级/离散操纵动作（RL 直接决定空气制动档位，**含"缓解"档**，即拥有循环制动相位决定权）
**要素 C**：MARL（多智能体强化学习，非单智能体 + 事后协调）

判定目标：**A ∧ B ∧ C 是否已有工作占位。**

## 二、检索式与通道

| 通道 | 检索式（代表性） | 命中 | 说明 |
|---|---|---|---|
| Semantic Scholar（MCP `scholar-search`） | `multi-train platoon heavy haul train reinforcement learning braking notch discrete action coupler force cooperative MARL` | 10 条（去重后 7 篇相关） | 见 §三 逐条判定 |
| Semantic Scholar | `heavy haul train reinforcement learning air brake release timing cyclic braking action space decision` | 10 条 | 见 §三 |
| arXiv 通道（同上 MCP 的 arxiv 源） | `hierarchical reinforcement learning train operation upper level task selection lower level control` | 10 条 | **几乎全部是通用 HRL 教程/机器人内容**，无列车档位级 MARL 工作 |
| Web 检索（中文） | `重载列车 深度强化学习 操纵优化 动作空间 牵引 电制动 空气制动 档位 缓解` | 10 条 | 命中 5 篇中文一手工作，见 §三 |
| 本地全文库（`docs/papers/`，32 篇 txt + 28 PDF） | 动作空间/notch/缓解 关键词扫描 | 11 篇有实质内容 | 见 §三 |

**未覆盖通道（必须声明）**：CNKI 主站被滑块验证拦截（ADR-045 已记录，改用万方可检索）；IEEE Xplore 全文闭源（仅摘要级）；ScienceDirect 部分 403。⇒ **中文小语种期刊与非 OA 会议可能有遗漏**。

## 三、逐条判定（要素 A/B/C）

### 具备 B（档位级/离散，含缓解）+ 缺 A（不是多列车编队）

| 文献 | 动作空间原证据 | 对象 | 缺哪一角 |
|---|---|---|---|
| **Zhang2024** Algorithms 17(5):190（TR-C 2021 同组） | *"The control action is defined as the setting of the **relative electric brake force and air brake notch**"*；`s_k=[P_k,V_k,T_k]` | **单列**（1 机车 + 108/216 货车） | 缺 A、缺 C |
| **Tang2020** Knowledge-Based Systems 190:105173（*Double-Switch-Q*，本地全文） | 多机车**离散 notch**，显式约束 notch **变化率**；目标含 velocity/energy/**coupler force**，原文 *"reduce the coupler forces through the **coordination of traction and braking forces from different locomotives**"* | **单列车内多机车**（多台 HXD3B） | 缺 A（不是多列车编队）、缺 C（单智能体 DSQ 架构） |
| **清华博士论文（C-LIT-09）** IDS + IDQN | 主控机车把**车钩力信息传播**给从控机车，各机车独立 DQN | **单列车内多机车异步控车** | 缺 A |
| **中文 DQN（多质点长大下坡）** | *"动作空间设置为离散的 **8 个制动档位：0 档表示缓解状态**，1~6 档常用制动，7 档紧急"*；观测预取**前方 2 km 平均坡度** | **单列**（SS6B + C80） | 缺 A、缺 C |
| **《基于DQN算法的货运列车长大下坡运行优化算法研究》**（维普） | *"通过与环境交互**搜寻最优循环制动工况转换点**"* | 单列 | 缺 A、缺 C |
| **《基于强化学习的重载列车操纵优化算法研究》** 河南科技 2025, 52(22):34-43 | *"动作空间包括**列车控制力与空气制动决策**"*；状态含**累计制动缓解时间** | 单列 | 缺 A、缺 C |
| **《基于强化学习的重载组合列车长大下坡操纵优化研究》** 机车电传动 2023(6) | 2 万 t **组合列车**；约束含**列车管制动及缓解时间** | 组合列车（单列概念，非多列车编队） | 缺 A、缺 C |
| 专利 CN119807769B（空电联合操纵） | *"对动作向量进行**分解**，得到牵引制动力以及**空气制动状态**"* | 单列 | 缺 A、缺 C |

### 具备 A（多列车/编队）+ 缺 B（无档位级相位决定权）

| 文献 | 动作/结构 | 缺哪一角 |
|---|---|---|
| **Wang2026** IET ITS（分层） | 幅度为 [-1,1]→**21 档离散步长 0.1** + 组合制动一个 0/1 整数变量；**相位由顶层 DP 决定**（不是 RL） | 缺 B（RL 不拥有相位；相位在 DP 手里）+ 场景是单列车沿线路的任务段切换 |
| **谌墨 2024**（北交大硕，C-LIT-13） | CTDE + MADDPG（连续动作），VCTS 协同 | 缺 B（连续动作）+ 缺车钩力 |
| **高济康 2025**（华东交大硕，C-LIT-12） | 群组运行 + EWM-DQN 群组多目标（含车钩力） | 缺 C（单智能体） |
| **Song2026** APF-MAPPO（本地全文） | MAPPO 多列车编队，动作语义见其 §动作空间（连续，未含缓解档） | 缺 B |
| **Jing2025 / Hu2026 / Ma2025 / Hua2024 / Zhang2021**（本地全文） | 均为多列车/编队 MARL，动作连续（速度/加速度/协同调整量） | 缺 B |

### 具备 A ∧ B ∧ C

**0 篇。**

## 四、结论（措辞受限版）

**据系统检索未见（截至 2026-11-11，通道 Semantic Scholar / arXiv / Web / 本地全文库）**，将**档位级离散动作（含缓解档、RL 直接拥有循环制动相位决定权）**用于**多列车编队 MARL** 的工作。

- 最近邻三篇各缺一角：**Tang2020**（档位级 + 车钩力，但单列车内多机车）、**Wang2026**（相位由 DP 而非 RL，且单列车任务段）、**Song2026**（多列 MARL 但连续动作、无缓解档）。
- **不得**表述为"空白""首创""无人做过"；正文只写"据系统检索未见（截至 2026-11-11，通道 …）"。
- 若要升级为更强措辞，需补：CNKI 主站（当前被拦截）、IEEE Xplore 全文（闭源）、日/俄/印铁路期刊通道。

## 五、顺带发现（非本命题，供 MPC 基线参考）

- **Zhu, Yao & Hu, "Physics-informed Koopman Mixed-Integer Model Predictive Control for Heavy Haul Trains"**（ScienceDirect, IFAC 系）：把**连续牵引/电阻制动力**与**离散空气制动**处理为混合整数 Koopman MPC。⇒ 该文可能是比 Song2026 管式 MPC 更贴"离散闸 + 连续 ED"结构的 MPC 基线候选，**建议在 Tube MPC 复现前评估**（ADR-042 主表 MPC 行选型可复议）。

## 六、相关

ADR-065（本台账服务的贡献定位）、ADR-045（三要素交集 C-GAP-01 与中文通道）、ADR-044（台账规范与措辞上限）、`REFERENCE_INDEX.md`（文献映射）。
