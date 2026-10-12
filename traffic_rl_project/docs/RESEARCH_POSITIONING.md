# 面向长大下坡场景基于多智能体强化学习的重载列车群组自动控制方法

> **研究对象**：一万吨级 1+1 重载列车群组（每列 = 首/尾双机车 + 94 节货车，`consist_preset: 10kt_1plus1`；3 列 = 6 台机车智能体；群组由多列组成，每列内部有车钩力）

> **【本文件定位（2026-10-12 核对）】立论 SSOT**（研究定位 / 创新点 / 对比规范 / 文献立论），属"立论"类可覆盖式修订，动机存档进 ADR。**进度与任务 → `PROJECT_PIPELINE.md`；重大决策 → `logs/decisions/DECISIONS.md`；文献文件清单 → `papers/README.md`；执行规范 → `rules/EXECUTION_RULES.md`**——这些不看本文件。

> **【2026-09-08 主轴共识（用户权威口径，本文件以此为铁律；ADR-013 修订 ADR-012 的"两层叠加"框架）】**
> **论文最终目的 = 编队**（多列重载列车群组长大下坡协同：保持安全列距 + 速度带一致 + 车钩力≤1000kN）；**多智能体强化学习只是实现编队的手段**。
> **仅保留一套 formation-aware RL** = **机车级 ED/AB 分工**（每台机车=智能体，ED 连续 / AB 离散档位），且 RL 以**编队为上下文**（obs 含前列间距/相对速度/前方坡度/群组车钩力，reward 以编队目标为主）——编队目标由这一套 RL 承载。底层由列内规则循环制动 + 车钩力安全层（确定性）执行。
> **废止**"编队层（列车级）RL + 列内层（机车级）RL 两层叠加 = T-MARL"的表述（ADR-012→ADR-013）。
> **重要**：单列车 standalone decompose（`decompose_loco_ed_ab.yaml`, num_trains=1）= **方向性偏差**，不承主线、不得当主结果；RL 必须以**编队上下文**重构。语义代号 SSOT 见 `.trae/documents/MT2多列编队M1与消融实验补齐规划.md` §0.1（M-数字已废止）。

***

## 一、研究定位（Mission）

### 1.1 核心目标

用**多智能体强化学习（MARL）+ CTDE 范式**实现**面向长大下坡场景的重载列车群组自动控制**，研究对象为**一万吨级 1+1 重载列车群组**（每列 = 首/尾双机车 + 94 节货车的多机车分布式动力，3 列 × 2 = 6 台机车智能体，群组由多列组成；"1+0 单机牵引"为 2026-09-02 重构前的旧对象，见 §1.3.1）。

**场景约束**：长大下坡（如大秦线/朔黄线 -10‰ 连续下坡），需循环制动调速。
**自动控制内涵（2026-09-08 ADR-013 修订）**：**最终目标是编队**（多列群组长大下坡协同）；**RL 落位为机车级 ED/AB 分工**（每台机车=智能体，以编队为上下文，承载编队目标），**底层由规则循环制动 + 车钩力安全层确定性执行**（`get_action_cyclic_braking` + `enforce_coupler` ≤1000kN）。即"RL 定策 + 底层控制器安全执行"的分层架构，与业界（VCTS/魏咪分层框架/Tang2020）一致，避免纯 RL 直接控 100 车厢的稳定性风险。

### 1.2 核心创新点（与现有工作的差异）

| 维度                                                      | 现有工作                                                                                     | 本项目创新                  |
| :------------------------------------------------------ | :--------------------------------------------------------------------------------------- | :--------------------- |
| 长大下坡 RL 控制（Zhang2024 DQN / Liu2021 DDQN / Wang2025 DQN） | 长大下坡循环制动 + RL，但**明确忽略车钩力**（"interaction forces between cars are not taken into account"） | **显式建模车钩力** + 长大下坡循环制动 |
| 虚拟耦合列车（VCTS）                                            | 多列车协同，但**简化掉车钩力**（用安全间距）                                                                 | **同时建模车钩力**            |
| 单列车厢级重载控制                                               | **有车钩力**，但只做**单列**                                                                       | **扩展到多列群组**            |
| **车钩力 + 多列群组 + 长大下坡**                                   | **几乎空白**                                                                                 | **分层 MARL 框架（本项目）**    |

> **⚠️ claim 收窄（ADR-030，2026-10-07）**：上表「忽略车钩力」**仅限 Zhang2024 / Liu2021 / Wang2025 这批单列 RL**，勿推广为「文献都忽略」——**Wang2026** 已在单列重载长大下坡 RL 中显式含车钩力（安全限值 1100 kN，进奖励与状态）；**Song2026** 多列虚拟编组 Tube-MPC 显式含车钩力约束（±1500 kN，峰值 330.4 kN）。**真空白 = 「多列群组 × 车钩力 × MARL」的交集**（Wang2026 单列、Song2026 是 MPC 非 MARL）；立论表述 = **「把车钩力凭证从单列挪到多列群组」**，而非「别人不管车钩力」。

> **claim 限定（2026-10-07，ADR-030 收窄）**：上表"忽略车钩力"**仅指所列举的具体工作**（Zhang2024 / Liu2021 / Wang2025 等**单列、车钩力未入模**者），**不可推广为"文献都忽略车钩力"**——
> - **Wang2026**（IET ITS，**单列**重载长大下坡**分层 RL**）**已显式含车钩力**：安全限值 1100 kN，进奖励与状态（本地 `docs/papers/02_rl/Wang2026_hierRL_fulltext.txt`）；
> - **Song2026**（北京交通大学学报，**多列**虚拟编组 **Tube-MPC**）**已含车钩力约束**：±1500 kN，峰值 330.4 kN（本地 `docs/papers/03_formation/Song2026_TubeMPC_VirtualCoupling.pdf`）。
>
> 真正的空白 = **"多列群组 × 车钩力 × MARL"** 的交集（Wang2026 是单列、Song2026 是 MPC 非 MARL）。立论应押 **"把凭证从单列挪到多列群组"**，而非"别人不管车钩力"。

**创新论点**：群组级控制不能忽略每列内部的车钩力约束——

1. **物理真实性**：重载列车内部车钩力是真实安全约束（1000 kN 上限），忽略它可能给出"速度同步但车厢挤压"的危险解；
2. **跨层传播**：一列的纵向冲动可能通过编队级联传播到其他列（单层模型看不到）；
3. **真实需求**：大秦线等重载场景列车往往上百节，车钩力绕不开。

> **车钩力创新点呈现（2026-08-22 / 2026-09-08 修订）**：把"车钩力贯穿约束"下沉到列内**规则循环制动 + 车钩力安全层强制执行**（`enforce_coupler=True`，编队规模下守住 <1000kN）。RL（机车级 ED/AB，formation-aware）不直接承担车钩力约束；车钩力擦除消融（原 M2，已并入安全层消融）显示 RL 是否考虑车钩力无差异（结构性结论）——车钩力创新点证据在"规则循环制动 + 安全层强制执行"层面，而非 RL 层消融。

### 1.3 编队目标 × 单套 formation-aware RL 框架（2026-09-08 ADR-013 修订）

```
┌──────────────────────────────────────────────────────┐
│ 编队目标（最终目的，非 RL）：多列群组长大下坡协同      │
│   保持安全列距 + 速度带一致 + 车钩力 ≤1000kN           │
│           ↓ 由同一套 RL 承载（编队上下文）             │
│ RL 落位（手段，唯一一套）：机车级 ED/AB 分工           │
│   智能体 = 每台机车（编队上下文内重构）               │
│   动作   = [ed_mod, ab_mod]（ED 连续 / AB 离散档位）   │
│   状态   = 本机车 ED/AB 衰减 + 前列间距/相对速度/      │
│            前方坡度 + 组内车钩力                       │
│           ↓ 目标速度/档位                              │
│ 底层执行（确定性）：列内规则循环制动 + 车钩力安全层    │
│   get_action_cyclic_braking + enforce_coupler≤1000kN  │
└──────────────────────────────────────────────────────┘
```

**连接**：RL 输出多机车的 ED/AB 分配（含列内目标速度/档位）→ 底层规则循环制动按编队目标追踪，车钩力安全层强制执行 ≤1000kN。

**战略依据（2026-08-22，保留）**：放弃"RL 直接学单列循环制动"（缓解波长时延6s→PPO信用分配失效+车钩力多体耦合→探索即爆炸，多次失败）。领域标准（Zhang2024/Tang2020）= 离散档位 + 规则循环制动；车钩力由"规则循环制动 + 安全层强制执行"保证。RL 只承担**多机车 ED/AB 分配**，以编队为上下文学习协同，不逐车直接学单列循环制动。

**对比实验（证明编队创新价值，语义代号；重跑后以本套 RL 结果为权威）**：

- **编队协同 vs 无协同（formation-aware vs No-C）**：编队目标是否达成（列距 / 速度带 / 车钩力 / 追尾率）——由本套 formation-aware RL 与"无编队上下文"对照得出。历史 +110042 属 R0 编队层阈值 RL 旧物理，不作为当前主结果引用（ADR-013）。

### 1.3.1 【2026-09-02 智能体分解立论；2026-09-08 定为唯一 RL 落位】多机车分布式动力 × 电空双制动分工（formation-aware）= 承载编队目标的唯一 RL

> **背景（导师批评）**："3 列 1+0 群组叫多智能体不合适"——1+0 = 每列仅 1 台动力源（单机牵引），
> 把"列车"当智能体本质是"3 条曲线的宏观优化"，与单体优化缺乏本质区分，'多智能体'名不符实。
> 审稿人（含直接对标的宋宗莹2026）同一风险。
>
> **结论**：融合两路学术界成熟的"多智能体"形态重构智能体分解，使"多智能体"锚定在**物理独立动力源**上，名实相符。

| 你的想法                    | 学术依据（已核实）                                                                                    | 本质                                                  |
| :---------------------- | :------------------------------------------------------------------------------------------- | :-------------------------------------------------- |
| **A. 1+0→1+1/多机车分布式动力** | Tang2020（多机车 RL+车钩力）、姚小沛2013（1+1 编组循环制动车钩力）、赵紫宁2022（2万吨 1+1 精细制动）、樊运新2024（编组方式→纵向冲动）         | 多台**物理独立动力源**的牵引/电制动/缓解错峰**分配** = 真多智能体协同           |
| **B. 电制动/空气制动分离**       | Yu2022（北京交大，长大下坡**电空联合制动**协调控制，Actuators 11(6)145）、仿真器 braking.py 已分 ED/AB + 多源 `ab_sources` | 电制动（连续/仅机车/响应快）vs 空气制动（离散档位/波速传播/**车钩力主源**）异构动作空间分工 |

**(融合设计 = 唯一 RL，非叠加层)**：多机车分布式动力作"体"（每台机车=智能体），每台机车同时决策电制动/空气制动分配——机车之间动力/缓解错峰降车钩力，制动器之间电空耦合分配。此 RL 取代旧的"编队层(列车级)阈值 RL"，作为承载编队目标的**唯一**学习层（以编队为上下文；ADR-013）。底层规则循环制动 + 车钩力安全层仍确定性执行。

**可行性已确认（2026-09-02）**：`TrainConsist.vehicles` 按序 + `locomotive_indices` 返回全部机车 +
`LocomotiveParams` 独立定义 → 多机车编组原生支持；ED/AB 已在 `braking.py` 分离、`ab_sources` 支持多源。
改动面集中在 `train_env.py` 编组建构 + 动作空间，不涉动力学积分核心。

**⚠️ 实施边界（2026-09-08 用户拍板）**：本方向 = 承载编队目标的**唯一 RL**，必须以**编队**为上下文实现（多列群组场景 + 每列机车=agent）；**不得**退化为"单独训练单列车"当作主线（该形态已被判为方向性偏差）。行内 `train_env.py`/`train.py`/`coupler.py`/`tractive.py` 为他人改仿真的未提交状态，不冲突不改造。按规划（.trae/documents/MT2多列编队M1与消融实验补齐规划.md）阶段2/3 立项 + 冒烟 + 全量训练（**该训练已启动并迭代多轮，进展勿查本文件，见 `PROJECT_PIPELINE.md`**）。

### 1.4 当前进度

> **【superseded（2026-10-12）】进度 SSOT = `docs/PROJECT_PIPELINE.md`**——原"2026-08-22 最终架构"状态表已过时（其中"机车级 ED/AB 待训练"等状态早已变化），**状态类信息一律以 Pipeline 为准，勿再引用本节旧表**。本节只留不再变化的架构事实：

- ✅ 单列动力学环境（`TrainFormationEnv`：ATP 安全层、车钩力 1000kN、Davis 阻力、车钩间隙死区）
- ✅ 列内规则循环制动 + 车钩力安全层（`get_action_cyclic_braking` + `enforce_coupler`）
- ✅ 多列编队环境（`TrainFleetEnv`：真实剖面 **`shuozhou_real_53km`** 53.2km + 限速 \[40,80]；`shuozhou_23800` 仅保留作 Zhang2024 复现场景）
- ✅ 编组 preset `10kt_1plus1`（3 列 × 首/尾双机车 = 6 agent）
- ⛔ 编队层（列车级）阈值 RL（`hierarchical_controller.py`）—— **2026-09-08 ADR-013 下线**，历史 +110042 属 R0 旧物理、不作主结果
- ▶ **唯一 RL 落位** = 机车级 ED/AB 分工（formation-aware）——训练/评估/消融进展见 `PROJECT_PIPELINE.md`

> **论文核心结果（可写入，重跑后以本套 RL 为权威）**：面向长大下坡重载列车群组，最终目的 = **编队**（多列群组长大下坡保持安全列距 + 速度带一致 + 车钩力≤1000kN）；手段 = **单套 formation-aware MARL**（机车级 ED/AB 分工，每机车=智能体，以编队为上下文）。历史"编队协同增量 +110042"属 R0 编队层阈值 RL 旧物理，不作为当前主结果引用（ADR-013）；编队协同结果改由本套 RL 在 MT-2 物理下重跑确认。

### 1.5 规范性问题（SSOT：主轴 / MPC 对比 / 车钩异构）【2026-09-05 ADR-010】

> 本节是这些思想的**唯一权威出处**（SSOT）。`AGENTS.md`、`docs/README.md` 只给稀疏指针，指向本节与 ADR-010。

**主轴与底线（可降级 vs 不可逾越）**

- **底线（不可逾越）**：多列编队（platoon）+ 队内车钩力 ≤1000kN + 安全列距（不追尾）。任何架构/论文叙事守这两条。

- **锦上添花（可降级、不当主线）**：AB+ED 分工、1+1 分布式动力——真物理杠杆但只是增强。

- 教训（2026-09-05）：单列 1+1 下"ED 够用、多源 AB 低冲动"→ 单杠杆可刷标量分，电空分工"意义不大"（`mask_lever` 消融：ED=车钩力安全、AB=吞吐，AB-only 标量 reward 反超双杠杆）。→ 核心立论放**多列 + 车钩力 + 列距**交汇处。

**MPC 对比只留 Regime A（逐线公平标定）——【2026-09-16 ADR-016 覆盖 ADR-010 的 A/B】**

- MPC 预测模型是通用物理（`a=命令+g·坡度+b0`），坡度只是输入馈给，不是模型本身。

- **唯一保留 Regime A——每线重喂（公平标定）**：每条测试线给正确 `grade_at`（剖面图纸，可在线标定 b0）。用于 main/E1/E3/E4 全部对比；失败只归因"聚合模型+秒级窗+车钩代理"。

- **废止 Regime B（不重辨识）**：不再提供"跨线不给新参数、专演 MPC 失配"的对比。理由（ADR-016）：D-RL 跨线携带 53km 训练所得策略，而 B 的 MPC 却不携带源域标定（`grade_at=None`→前5车平均坡度），对象不对称、有 strawman 非议；且"MPC 不重标定即失配"属换线必做符规标定的领域常识，无需本论文重复证明。立论改押"**免重辨识成本**"：零重标定代价的 MARL ≈ 逐线重标定后的 MPC。

- **D-RL 跨线严格零微调**，文中声明 "MARL no fine-tuning on target line"；**Protocol 逐实验标 A**（无 B，不再 A/B 双标）。

**车钩/列车异构性（E4-H）【2026-09-16 SUPERSEDED：不承担立论，仅代码可选鲁棒性】**

> **状态迁移（2026-09-16，ADR-016 后）**：本节标题原为"泛化卖点 E4-H"，**已从立论移除**。主 claim 只押"免重辨识成本"（ADR-016），车钩异构与其无关，**不作泛化卖点、不进正文主表**。以下历史正文保留供回溯；`--hetero` 代码保留为可选鲁棒性（默认齐次零回归）。

- 每个车钩、每列车物理参数（刚度/间隙/预紧/摩擦/总重/车长）不同 = **实例异构**，不是数学"离散/切换"。

- 当前 `train.py` 用单套共用 `CouplerParams`（齐次）；支撑异构须改逐车钩/逐列车独立参数 + 分布抽样 + held-out 评估（`--hetero`，默认齐次零回归）。

- 对位：MPC 锁单套参数 → 偏差下车钩力越限；MARL 见过分布 → 迁移保持底线。**（以下为 2026-09-05 正式定调）**

**【2026-09-05 定调】车钩异构化不做主推 / 降级为可选鲁棒性（供导师汇报的理由）**

- **结论**：E4-H（逐车钩异构 → 泛化）**不做论文主线**；`--hetero` 代码保留为**可选鲁棒性**项，泛化立论改押 **E4 真实轴**（跨剖面 23→35km / 编组规模 3→5 / 随机初速 55–75）。

- **理由**（可复述给导师）：

  1. **领域非核心需求**：重载纵向动力学学界的"泛化/敏感性"关注的是**运行可控项**（跨线、编组、随机初态、载荷）；"同批次车钩逐钩公差"并非该领域认可的优化对象。
  2. **缺实证方差数据**：逐钩刚度/间隙/摩擦的逐台标定·方差**无公开实测**；文献只给**静态基值**（MT-2：F0 200 / friction 500 / k 1.89e7，Ge2018/于宗泽/李蔚）与"参数偏移强变纵向动力学"的**机理**（Wang2025、马卫华2011），**没有给逐钩变差幅值**。
  3. **硬伤：±15% 带宽无出处**。除非做 `force_scale` 扫掠把带宽变成被测变量，否则写"±15%"必然被审稿人挑战"依据在哪"。
  4. **检索证据**：正式检索（arXiv/Semantic Scholar/Web）**未发现**"同一列车内逐钩**连续**参数各异 + 分布/held-out 泛化"的直接工作；近似的只有 Krishna2020（列内**离散混编** wagon/制动块/buffer，力学层，非控制层）。张力即"无先例=novelty"或"无先例=非领域需求"——对投稿而言后者是**负资产**。
  5. **利剑反向**：审稿人若问"这问题现实吗 → 同批次公差<±5%、效应被变坡掩盖"，反而推翻我们"要凸显 MARL 泛化"的目的。

- **落点**：泛化 claim = E4（跨线/规模/随机初态，领域公认、可复现）；`--hetero` 仅作 robustness 附录备选，不承担主线。

> 配套决策见 `docs/logs/decisions/DECISIONS.md` ADR-010；实验计划见 `.trae/documents/plan_2026-09-05_多列platoon重构与MPC对比异质泛化.md`（临时工作产物，不入 SSOT）。

### 1.6 立论定调：免重辨识 claim（2026-09-09，SSOT，覆盖式修订 ADR-010 已过时部分）

> **本节为当前论文的立论口径（覆盖式修订，不追加历史）**。取代 §1.5 中"泛化方向 23→35km"等已过时假设（该假设写于未获 53km 真实数据时）。若未来 claim 再变，直接覆盖本节当前口径，动机存档见 ADR-014。

**核心 claim（"免重辨识成本"，非"比控制品质"）【2026-09-16 ADR-016 reframe】**

- 同一环境 / 安全层 / **53km 主训练**（`shuozhou_real_53km`；现行配置以 `configs/experiments/formation_ed_ab_3train_1plus1.yaml` 为准）下，**零微调的 D-RL 跨线守住底线**（车钩力≤1000kN、不越 ATP 限速、列距不破界）。
- 对**逐线公平标定的 MPC**（`NMPCController`：列内**集中质量(lumped)多体** + **MT-2 符号化车钩** + 车钩力 ≤1000kN 硬约束 + casadi/**IPOPT** + `inner_rule_cyclic` + 每线重喂 `grade_at` 图纸 + 在线标定 b0，即 Regime A）：D-RL 以**零重辨识成本**达到 MPC 逐线专门重标定后才有的同档性能（实测 MARL 泛化 ≈ 重标定 MPC）。
  > **【ADR-022，2026-10-01】** 对比基线**唯一化**为 `NMPCController`；旧的 `FairMPCController`（聚合列 + 车钩力代理 + SLSQP）与简化 `MPCController` **已删除**（"不要留粗糙 MPC 当靶子"）。本节原指名 `fair_mpc_controller` 的表述按本 ADR 覆盖修订；**Regime A 协议本身不变**。历史 MPC 数值全部作废。
- **不与 MPC 比"谁控制得更准"，只比"免重辨识的成本"**（MARL 跨线零微调 vs MPC 每线重标定+在线求解）。
- **废止"MPC 不重辨识即失配"作为论证**（Regime B 已删）：不证明、不依赖该结论，属换线必做符规标定的领域常识，不占篇幅。

**立论矩阵（2026-09-16，SSOT）——MARL 卖点与安全层边界的权威界定**

> 作用：框死"MARL 到底比 MPC 好在哪、哪些绝不能当卖点"，避免后续又拿安全层当创新点或把 claim 摊薄。铁律：**安全性由规则层+SafetyLayer 兜底，不归功于 MARL、不写进立论**。

- **主 claim（唯一，必做）——免重辨识成本**：功能指标持平即可（不追求反超），差异化仅在"达到同档功能性能的获取成本 = 0（免重辨识）vs MPC 逐线重标定"。指标=速度带达成/间距误差/车钩力≤1000kN 落地率的**同档持平** + 标定成本量化（见上「标定成本量化口径」）。
- **结构性次要优势（2026-09-16 定稿取舍）**——只留**有数据可实证**的两条，作 Appendix/补充证据，不涉安全层；无实证的砍：
  - **规模可扩展性（留，Appendix）**：3→5 列，D-RL 每步网络前向一次 vs MPC 多列耦合 **IPOPT** 求解维度随列数增长；用 3→5 列 + `solve_times` 图实证（横轴列数、纵轴每步求解耗时）。
  - **实时决策延迟（留，Appendix 一句数字）**：网络前向毫秒级 vs 每步在线 **IPOPT**；报 `solve_times` 现成统计即可，**当补充数字，不当主卖点**（决策间隔 1s 下 MPC 也够快，别硬立）。
  - **去中心化/抗单点故障（砍，不写进立论）**：仅定性断言、无"求解器故障 vs 某机车失效"实际对照实验，且去中心化亦含通信/一致性缺陷，审稿易戳空；不占篇幅。
- **明确排除（不写进立论、不当卖点）**：
  - **安全性（守底线/0碰撞/车钩力≤1000kN）**：由安全层+规则层保证，非 MARL 贡献；ATP 触发等只作约束达成记录，不归功于 MARL。
  - **随机化鲁棒性的"安全面"**（0 碰撞资产）：同上，若保留仅可用**功能性能统计方差**（速度带/间距误差）重定义，不以"0 碰撞"为卖点。
  - **混合架构可解释性**：不以"安全由规则兜底"为卖点即无可说之处，默认弃用。

**车钩力定位（约束，修订明义）**

- 车钩力 = 硬安全层（enforce ≤1000kN）+ 观测上下文（状态带车钩力）；**不作均值最小化对象**（2026-10-01 前写作"**不进 reward**"——该绝对表述已按下方条款修订为"允许受控超限项、不作均值最小化"）。
- 这是"约束"语言（导师口径"保持在以内"），"优化目标"定位已废止。
- **⚠️ 已修订并落地（2026-10-01，ADR-021 决策 2「执行闭环」①）**：上述"**绝不进 reward**"的**绝对表述已修订**——现允许**受控的"超限"非线性项**进目标：`coupler_over_term = −6.0 · min(peak_norm − 1, 2.0)`，上界 **−12.0**，仅在 `peak_norm > 1` 时生效（`peak_norm` = **断面力**峰值 / 限值，口径 SSOT = ADR-018）；**`mean` 项权重未动 ⇒ 仍不作均值最小化**，**安全叙事仍不归功于 MARL**（≤1000 kN 由安全层 + 规则层保证）。
  - 动机（诊断，`logs/diagnostics/DIAGNOSTICS_2026-10.md`「诊断-2026-10-01」）：原车钩力 shaping 量级仅 ≈3%（上限 −0.4 vs 速度带 +6/列）**且无超限跳变**（`−80·ov²` 已回滚）⇒ 破线/不破线在目标里不可区分。
  - 落地与量级核对：`logs/diagnostics/DIAGNOSTICS_2026-10.md`「改造-2026-10-01」四、（解析核对 pn=1.5→−3.0 / 3.0→−12.0 / 5.0→−12.0）；metadata 记 `reward_schema=v2-bounded-overlimit-section-force`。
  - **待裁定**：该权重是否保留、以及是否需要放大，**须由 C+B 重训（1400 ep × 5 seed）后的结果决定**（长久计划，见 `docs/logs/progress/PROGRESS_2026-10.md`）。本条其余立论边界不变。

**动作结构（固化为单词结构 Q）**

- `multi_loco_controller.get_action_decomposed`：规则循环制动 + 逐机车 RL 调制 `[ed_mod, ab_mod]`∈[-1,1]；**调制带宽 `ed_mod_coef = 0.5`（半幅）** ⇒ `final_ed = clip(baseline_ed + 0.5·ed_mod, 0, 1)`。⚠️ 口径变更史：ADR-023 曾放宽至 1.0（全幅），完整剖面 A/B 判"对 RL 有害、对 MPC 无收益"后由 **ADR-024 回退 0.5**（现行值；带宽即动作空间语义，换值即换策略含义，见 `DECISIONS.md` ADR-023/024）。MPC 桥接与 D-RL **同款同带宽**，符合 ADR-016 不失公允口径。
- claim 落"协同调制"层；**规则层管单车安全制动、RL 管多车编队协同**。

**主对比（对 MPC）三行同环境/安全层**：D-RL / D-Rule / MPC。

**主指标（对齐"免重辨识成本"）【2026-09-16 ADR-016】**：MARL 跨线**零微调**（文中声明"no fine-tuning on target line"）；MPC 每线重标定并量化**重标定代价**（完成辨识所需步数/数据、`solve_times`）。**底线达成证据**（非"谁控得准"）：车钩力≤1000kN 落地率、ATP 触发次数（替代"追尾"——安全层已杜绝物理追尾，ATP 触发=策略踩线兜底依赖度）、列距/速度带落地率。

**标定成本量化口径（2026-09-16，SSOT，配套 ADR-016）**

> 目标：把"免重辨识成本"变成可量化、可复现的证据。先厘清事实：MPC 的"标定"由两部分构成——**b0 在线标定**（`nmpc_controller` 的速度差分标定，每步免费）与 **`grade_at` 图纸注入**（需目标线完整坡度剖面，这才是换线重标定的成本所在）。量化对象 = **先验注入量**，不是计算耗时。

- **口径 1（主证，必做）——先验注入量清单表**：MPC-C 的标定成本 = 获得目标线坡度图纸所需工程动作，逐项列行业惯例数值（线路实测人天 → 数据处理人天 → 参数辨识人天 → 仿真验证 → 试车审批，引符规/文献依据）；**D-RL 一行 = 0**（零微调、零先验）。表格即"成本差"证据，轻量、不占篇幅。
- **口径 2（视觉证据，篇幅允许再加）——标定预算曲线**：横轴 = 注入目标线信息量（剖面采样点数/覆盖坡段比例），纵轴 = 底线达成率（车钩力≤1000kN / ATP 触发次数）。MPC 全图纸 = 100% 预算点；稀疏图纸（50%/25% 剖面）性能衰减成曲线；**D-RL = 0 预算单点，落在 MPC≈100% 预算的性能上**——"零成本达同档"的可视化。
- **口径 3（现成数据，顺手补）——在线求解代价**：`solve_times` 已逐步记录，统计 MPC 跨线后**求解失败/超时次数、平均耗时**，作部署运行成本的补充证据（非标定成本本体）。
- **口径 4（不做）——辨识收敛时间**：b0 改 RLS/KF 在线辨识虽工程更真实，但要改控制器+加实验，成本高收益低；除非审稿人明确质疑，否则不启用。

**跨线方向（修订 ADR-010 已过时假设）**

- 主训练 53km；**跨线目标 = 域外真实剖面（20/35km；具体剖面与实验安排以 `docs/PROJECT_PIPELINE.md` 为准）**，**不是 23.8**（23.8 仅作已知基线锚，不作跨线泛化证明，因它是已拟合过的合成线、"见过"了）。
- MPC 跨线**逐线注入该线 `grade_at` 图纸 + 在线标定 b0**（Regime A）；**不再提供 no-re-identification 的 Regime B**（ADR-016）。

**放弃项（定稿）**：SAC/QMIX/DQN-fair **不进实验主表**（claim 不依赖 RL 算法选择，仅 Related Work 一句引文献）；ED/AB 隔离、No-ETCS、No-C 不进正文（与既有 ADR-013 删除项一致）。

### 1.7 安全分层与 ATP 诚实边界（SSOT，2026-10-12）

> 作用：把"防追尾到底靠什么、哪些是实现描述哪些是文献贡献、话能说到哪一步"钉死，避免把系统实现包装成文献创新，也避免过度承诺。

**四层分工（本项目的实现描述，非文献分级）**

1. **层0 RL 定策**：formation-aware 机车级 ED/AB 调制（编队为上下文，ADR-013 唯一 RL 落位）。
2. **层1 规则前瞻**：ETCS 目标距离曲线（gap 目标 = 前列尾车），I/P/W/SBI/EBI 五级监督提前减速贴线；列内规则循环制动负责正常工况执行。
3. **层2 ATP 硬介入**：EBI 全列紧急制动，**最高优先级、最后施加、不被车钩力规则释放**（`safety_layer.py` 铁律注释 + `train_env.py` EBI 真落空气制动）。
4. **层3 事后断言**：评估入口 `assert rear_end_steps == 0`（非 0 判该行无效）；训练 rollout gap≤0 判回合无效。

**编队不能只靠 ATP（四条，写论文时的自辩）**

- ATP 是**监督器不是控制器**：只在越线那刻介入，不产生"保持间距/速度带"的正常控制量 ⇒ 没人负责正常工况，编队不成立。
- **一介入就打车钩力底线**：全列紧急制动放大百辆万吨列车的纵向冲动，冲击 1000 kN 硬底线（*推断*；代码规则顺序反证其会打架——ETCS 特意放最后）。
- **论文归因**：安全不归功 MARL（ADR-014/021 铁律）。**ATP 触发次数 = 控制失败次数**，MARL 拿的是"少触发、少超限"，ATP 拿的是"最后一道不失守"。
- **兜底前提可失效**（见下）+ ATP 全兜会吃掉 RL 梯度（安全层吞掉惩罚 ⇒ 学不到）。

**诚实前提（必须进论文，逐字口径）**

- `d_safe` 的目标速度取**前车当前速度**（`train_fleet_env.py` `_atp_safe_gap`：`speed_mps=lead_v`）⇒ 隐含**假设前车不减速**。
- **缺口未修前，只能声称"对前车保持速度/缓减速安全"**；修后（目标速度改 `max(lead_v − a_assumed·t, 0)`，`a_assumed` 用已标定实测紧急减速度 0.38–0.43 m/s²，或最保守取 0）才能声称"**对前车紧急制动安全**"。
- 配套缺口：现只有位置–速度曲线、无 closing-rate（相对速度）监督 → 建议补 1/TTC 阈值触发 service brake。
- **⚠️ 待拍板**：修缺口 + 补 TTC/TET 会改变 ATP 触发次数，历史评估数值不再严格可比 ⇒ 宜在 1400 ep × 5 seed 主训练开跑前一次性切干净口径。

**同类型论文（编队）的防追尾机制对照**

| 论文 | 机制 | 保证强度 |
|---|---|---|
| Li2024（CBF/CLF+QP） | 安全集 + 前向不变性写进 QP | 硬，有数学证明 |
| Song2026（Tube-MPC） | 鲁棒管束 + 严格跟踪/间距约束进优化器 | 硬，有界 |
| Hu2026（MARL 虚拟耦合） | 安全距离进奖励与约束，collision avoidance 作评价 | 软 |
| Guo2025（MARL 编队） | 可变车头时距共识，用 1/TTC、TET、TIT 当安全证据 | 软，指标证据 |

⇒ 我们：层2+层3 比 MARL 同行硬，比 CBF 类少一个数学证明 ⇒ 论文写法 = 工程硬保证（ATP 不可释放 + 零穿透断言）+ TTC/TET 可比指标，**CBF 列 future work**（`safety_layer.py` 已预留接口，不占正文）。

**指标术语对齐（2026-10-12，禁自造词）**

- 文献原词（本地一手）：**spacing error** / **safe distance** / **collision avoidance**（写成*约束*）/ **TTC·TET·TIT** / **time headway**；自造词"**追尾步数**"已从评估与图表删除（根因 = 2026-09 决策只落在被 ADR-022 删除的旧入口，现行入口已补，见 `logs/diagnostics/DIAGNOSTICS_2026-10.md`「指标口径修复-2026-10-12」）。
- 通称"安全违约（列距 < 5 m）"= constraint violation，仅用于历史图表；**主表安全指标 = ATP 触发次数**（`safety_events`）。
- 评估打印标签统一：车钩超限 / ATP 触发次数 / 空气制动步 / 速度带内占比 / 列距误差·最小列距（= spacing error / min spacing）。训练进度行 `pkCpl/viol/band` 为日志缩写，不进主表、不进论文。

***

## 二、文献清单（Bibliography）

### 2.0 文献数据库（Zotero 混合方案）

> **[`docs/refs.bib`](refs.bib)** 是文献结构化数据库（LaTeX 引用消费；Zotero `File→Import` + Better BibTeX 关联本地 PDF）。
> **文件级清单 SSOT = [`papers/README.md`](papers/README.md)**（全量文件→元数据、待补清单都在那）；**本节只保留立论相关条目，不求全、不重复登记**。
> **新增文献务必三处同步**：`refs.bib` + `docs/papers/`（PDF/信息卡）+ [`REFERENCE_INDEX.md`](REFERENCE_INDEX.md)（引用登记，根 `AGENTS.md` 文献库规范）。

### 2.1 已下载到本地

| 文件                                                                                                                                  | 文献                                                                                                                                                                                                                               | 说明                                                                                                                                                                                                                                                             |
| :---------------------------------------------------------------------------------------------------------------------------------- | :------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | :------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `docs/papers/02_rl/Tang2020_DoubleSwitchQ.pdf`                                                                                            | Tang, Wang, Liu. *Reinforcement learning approach for optimal control of multiple electric locomotives in a heavy-haul freight train: A Double-Switch-Q-network architecture.* Knowledge-Based Systems, 2020.                    | 多机车重载列车 RL，**车钩力建模 + 多目标优化**，与本项目最相关                                                                                                                                                                                                                           |
| `docs/papers/01_coupler_physics/Fu2019_CouplerConstraint_HeavyHaul.pdf`                                                                                | 付雅婷, 原俊荣, 李中奇, 杨辉. *基于钩缓约束的重载列车驾驶过程优化.* 自动化学报, 2019, 45(12): 2355-2365. DOI: 10.16383/j.aas.c190223                                                                                                                              | 钩缓约束 + 多目标优化 + 预测控制，**开放获取**                                                                                                                                                                                                                                   |
| `docs/papers/02_rl/Huang2025_EITO_ExpertSystemDRL.pdf`                                                                                    | Huang, Lai, Chen, Lin, Yin. *Enhanced intelligent train operation algorithms for metro train based on expert system and deep reinforcement learning.* PLoS ONE, 2025, 20(5): e0323478. DOI: 10.1371/journal.pone.0323478         | PPO 多目标优化 + 专家系统 + DMTD 惰行，**GOLD 开放获取 CCBY**，与 2003.03327 同作者团队                                                                                                                                                                                               |
| `docs/papers/03_formation/Song2026_MAPPO_HeavyHaulGroup.html`                                                                                    | 宋宗莹, 李烁, 王兴中, 杨迎泽. *基于多智能体强化学习的重载列车群组协同控制.* 中国科技论文在线, 2026-05-26. DOI: 10.61951/SciencepaperOnline.202605.0114                                                                                                                   | **多列独立列车群组 + MAPPO**，定位最接近（HTML 为元数据存档，全文需登录下载）                                                                                                                                                                                                                |
| `docs/papers/03_formation/Song2026_TubeMPC_VirtualCoupling.pdf`                                                                                  | 宋宗莹, 张韦, 王兴中, 张辰东. *基于传统空气制动的重载虚拟编组列车协同控制方法.* 北京交通大学学报, 2026, 50(2): 116-131. DOI: 10.11860/j.issn.1673-0291.20250156                                                                                                            | ⭐ **Tube-MPC + 电/空制动 + 车钩力 + HHVCTS 虚拟编组**（正式期刊版，2026-09-03 手动下载入库）。模型驱动 MPC 最强对照：速度误差 0.44 m/s、间距误差 0.66 m、车钩力峰 330.4 kN（限值 22%）；用 fence 概念压缩多质点计算 → **佐证你论文 Lim 2（在线求解计算负担）**                                                                                |
| `docs/papers/01_coupler_physics/Zhang2025_20kT_LongitudinalDynamics_Braking.pdf`                                                                       | Zhang, Liu, Guo 等. *Research on Longitudinal Dynamics of 20,000-Ton Heavy Haul Trains Considering Braking Characteristics.* Mathematics, 2025, 14(1): 158. DOI: 10.3390/math14010158                                             | **GOLD/CCBY**，制动特性对纵向冲动的定量数据，可验证你的空气制动波速传播模型                                                                                                                                                                                                                   |
| `docs/papers/05_energy_other/Heineken2023_OptimalControl_EnergyEfficient.pdf`                                                                       | Heineken, Richter, Birth-Reichert. *Energy-Efficient Train Driving Based on Optimal Control Theory.* Energies, 2023, 16(18): 6712. DOI: 10.3390/en16186712                                                                       | **GOLD/CCBY**，Pontryagin 极大值原理 + 再生制动，节能 37%                                                                                                                                                                                                                   |
| `docs/papers/05_energy_other/Yang2024_ACSd_EnergyEfficientTrain.pdf`                                                                                | Yang, Miao, Wang. *Driving Strategy Using an Improved Ant Colony System for Energy-Efficient Train.* J. Advanced Transportation, 2024. DOI: 10.1155/2024/5964428                                                                 | **GOLD/CCBY**，蚁群 ACSd 最优驾驶策略 ODSD                                                                                                                                                                                                                              |
| `docs/papers/01_coupler_physics/考虑车钩力约束的重载列车运行优化分层框架与迭代求解方法_魏咪.pdf`                                                                                    | 魏咪, 王青元, 孙鹏飞, 冯晓云 等（西南交大）. *考虑车钩力约束的重载列车运行优化分层框架与迭代求解方法.* 中国知网                                                                                                                                                                   | ⭐⭐ **最重要对标**：**车钩力约束 + 分层框架**，与你的分层 MARL 定位几乎同主题                                                                                                                                                                                                               |
| `docs/papers/01_coupler_physics/编组方式对3万吨重载列车循环制动工况纵向冲动的影响_樊运新.pdf`                                                                                     | 樊运新 等. *编组方式对3万吨重载列车循环制动工况纵向冲动的影响.* 电力机车与城轨车辆, 2024. DOI: 10.3969/j.issn.1001-8360.2024.01.006                                                                                                                                   | 高：编组 + 循环制动 + 纵向冲动物理规律                                                                                                                                                                                                                                         |
| `docs/papers/01_coupler_physics/krishna-et-al-2020-an-integrated-numerical-framework-to-investigate-the-running-safety-of-overlong-freight-trains.pdf` | Krishna, Jobstfinke, Melzi, Berg. *An integrated numerical framework to investigate the running safety of overlong freight trains.* Proc IMechE Part F: J Rail & Rapid Transit, 2020, 235(1). DOI: 10.1177/0954409720905203 (OA) | ⭐ **逐车/逐缓冲器"异构性(heterogeneity)"→ 最大列内力 / 可容忍纵向压钩力**，用"truly random train"(异构分布 min–max 抽取) 评估运行安全；**E4-H 力层先例**（修正"无人做异构"）。2026-09-05 入库，信息卡 `Krishna2020_OverlongHeterogeneity_运行安全.md`                                                                       |
| `docs/papers/01_coupler_physics/Analysis of the nonlinear dynamic behavior of longitudinal systems in heavy-haul trains.pdf`                           | Wang, Jin, Li, Tang. *Analysis of the nonlinear dynamic behavior of longitudinal systems in heavy-haul trains.* Electronic Research Archive, 2025. DOI: 10.3934/era.2025027 (OA)                                                 | 载荷 / **车钩游隙(slack)** / 缓冲器性能 → 纵向系统**分岔/混沌**（耦合 `coupler_gap` 死区 + MT-2 迟滞）；**E4-H"参数偏移强烈改变动力学"依据**；引 Yadav & Vyas 2023(AAR slack→jerk)。2026-09-05 入库，信息卡 `Wang2025_LongitudinalNonlinear_缓冲器非线性.md`                                                           |
| `docs/papers/01_coupler_physics/车钩间隙对重载列车纵向冲击动力学的影响_杨敏.pdf`                                                                                            | 杨敏 等. *车钩间隙对重载列车纵向冲击动力学的影响.* 中国知网                                                                                                                                                                                                | 高：车钩间隙 → 最大车钩力（60km/h 时 0.01m 与 0.018m 相差 52.14kN）                                                                                                                                                                                                             |
| `docs/papers/03_formation/Guo2025_MARL_PlatoonConsensus.pdf`                                                                                     | Guo, Peng, Pi, Zhang, Wu, Ma. *Enhanced consensus control architecture for autonomous platoon utilizing MARL.* Comput-Aided Civ & Infra Eng, 2025. DOI: 10.1111/mice.13463                                                       | 高：双向协同优化 + LSTM 时序，间距误差 -8.3%、编队长度 -19.1%，**HYBRID/CCBYNC**                                                                                                                                                                                                    |
| `docs/papers/02_rl/Zhang2024_DQN_CyclicBraking_Downhill.pdf`                                                                              | Zhang, Zhou, He 等. *Deep Q-Network Algorithm-Based Cyclic Air Braking Strategy for Heavy-Haul Trains.* Algorithms, 2024, 17(5): 190. DOI: 10.3390/a17050190                                                                      | ⭐⭐⭐ **直接对标**：**长大下坡循环空气制动 DQN**，朔黄线实测验证，制动距离 -2.1%、平均速度 +7%。**明确忽略车钩力**——你的创新空间。**GOLD/CCBY**                                                                                                                                                                  |
| `docs/papers/01_coupler_physics/Zhao2022_AirBrakeRefinedModeling_Optimization.pdf`                                                                     | 赵紫宁（导师王青元）. *重载列车空气制动精细建模与操纵优化.* 西南交通大学硕士学位论文, 2022-05.                                                                                                                                                                          | ⭐⭐⭐ **建模 + 优化双料基准**：2 万吨 1+1 编组、**三段式空气制动精细模型**（响应/暂态/稳态）+ 闸瓦压力分布 + 历史制动修正函数；QP 操纵优化使压钩力 -29.49%（叠加操纵规则 -33.74%）。**30 趟车次 / 350 个制动段实车数据**。信息卡 → [`Zhao2022_AirBrakeRefinedModeling_Optimization.md`](papers/01_coupler_physics/Zhao2022_AirBrakeRefinedModeling_Optimization.md) |
| `docs/papers/04_safety_mpc/Cooperative-Nonlinear-Model-Predictive-Control-for-Multiple-Locomotives-of-Heavy-Haul-Train.pdf` | Lu, Zhang, Su. *Cooperative Nonlinear Model Predictive Control for Multiple Locomotives of Heavy Haul Train on Long Steep Downhill Sections.* IEEE ICIRT 2025. DOI: 10.1109/ICIRT66379.2025.11216780 | ⭐⭐ **本项目 MPC 对比基线来源**：多机车协同 NMPC — 多质点模型 + 电/空制动协同 + 车钩力缓代价 + 车钩力/限速/执行器硬约束 + 空气制动波传播延迟（LOCOTROL 非 ECP）。**差异**：原文单列多机车 → 本项目 3 列群组；多质点 → 每列 4 块降阶。信息卡 `Lu2025_CooperativeNMPC_MultiLoco.md` |

**已下载的 arXiv 源码（`docs/papers/arxiv_src/`）**

| 目录                 | 文献                                                                                                                                   | 说明                                                                       |
| :----------------- | :----------------------------------------------------------------------------------------------------------------------------------- | :----------------------------------------------------------------------- |
| `2504.19480/`      | Wei, Yi, Lei, Hong, Du. *An Automated Reinforcement Learning Reward Design Framework with LLM for Cooperative Platoon Coordination.* | **完整源码**（28 文件）：LLM 辅助车队协调奖励设计，可借鉴到分层 MARL 奖励                            |
| `2003.03327/`      | Zhou, Song, Xue, You, Wu. *Smart Train Operation Algorithms based on Expert Knowledge and Reinforcement Learning.* IEEE TSMC.        | **完整源码**：专家知识 + RL 列车运行，含算法与图                                            |
| `2312.06858_full/` | Abdelrahman, Shehata, Basyoni, Morgan. *Scalable Decentralized Cooperative Platoon using Multi-Agent DRL.* IEEE, 2021.               | **完整源码**（109 文件）：**车辆车队 MARL**，前后跟随 "sharing and caring" 通信框架，可迁移到列车群组协同 |

### 2.2 未下载（需订阅/机构权限，已核实元数据）

| 文献                                                                                                                                | 出处                                                   | 相关性                           |
| :-------------------------------------------------------------------------------------------------------------------------------- | :--------------------------------------------------- | :---------------------------- |
| Bulavin & Ignatieva. *Leveraging Deep Reinforcement Learning for Reducing Longitudinal Train Forces in Railway Systems.* 2024.    | LNNS (Springer), DOI: 10.1007/978-3-031-77688-5\_12  | 高：多体 ODE 动力学 + DRL 降纵向力       |
| Fang, Cai, Qiu. *Cooperative Tracking Control Combining with RL for Heavy-Haul Trains.* 2025.                                     | IEEE                                                 | 高：协同跟踪 + RL                   |
| Wu, Spiryagin, Cole, et al. *International benchmarking of longitudinal train dynamics simulators: results.* 2018.                | Vehicle System Dynamics                              | 高：LTD 仿真器基准                   |
| Cole. *Longitudinal train dynamics.* 2017.                                                                                        | Vehicle System Dynamics                              | 高：纵向动力学综述                     |
| *A distributed braking scheme for heavy-haul trains using coupler force...* 2026.                                                 | IEEE/CAA JAS                                         | 高：车钩力约束的分布式制动                 |
| *Dynamic identification of coupler force of heavy haul locomotive.* 2024.                                                         | Engineering Applications of AI                       | 中：车钩力识别                       |
| *Multi-Resolution Deep Learning for Coupler Force Prediction in 20000-Ton Heavy-Haul Trains.* 2025.                               | ResearchGate                                         | 中：车钩力预测 ML                    |
| Lin, Li, Qiu. *A multi-objective optimization approach for the virtual coupling train set driving strategy.* 2025.                | Railway Engineering Science                          | 中：VCTS 单智能体 RL + MPC          |
| *Multi-Agent Reinforcement Learning Optimization for Virtual Coupled Train Set Problem in CBTC Systems.* 2025.                    | Tsinghua Science & Tech                              | 中：VCTS 多智能体                   |
| Aredah, Fadhloun, Rakha. *NeTrainSim: network-level simulator for freight train longitudinal motion and energy.* 2024.            | Railway Engineering Science                          | 中：本项目动力学源头                    |
| Wang, Wang, Sun. *Operation Optimization of Heavy Haul Train Considering Longitudinal Impulse Suppression: a DQN Approach.* 2025. | IEEE ICIRT, DOI: 10.1109/ICIRT66379.2025.11216684    | 高：**重载列车 DQN + 纵向冲动抑制**       |
| 魏咪, 王青元, 孙鹏飞等. *考虑车钩力约束的重载列车运行优化分层框架与迭代求解方法.*                                                                                     | 中国知网                                                 | 高：**车钩力约束 + 分层框架**（与你的分层想法呼应） |
| 樊运新等. *编组方式对3万吨重载列车循环制动工况纵向冲动的影响.* 2024.                                                                                          | 电力机车与城轨车辆, DOI: 10.3969/j.issn.1001-8360.2024.01.006 | 高：编组 + 循环制动 + 纵向冲动            |
| Si, et al. *Convergence-triggered reinforcement adaptive relearning control for virtually-coupled trains.* 2026.                  | Transportation Research Part C                       | 中：虚拟耦合强化自适应再学习                |
| Quaglietta, Wang, Goverde. *A multi-state train-following model for the analysis of virtual coupling railway operations.* 2020.   | J. Rail Transport Planning & Mgmt                    | 中：虚拟耦合列车跟随模型                  |
| Xun, et al. *Cooperative control of high-speed trains for headway regulation.*                                                    | IEEE Trans. Ind. Inform.                             | 中：高速列车协同控制                    |
| Wang, et al. *A reinforcement learning empowered cooperative control approach for IIoT-based virtually coupled train sets.* 2020. | IEEE Trans. Ind. Inform.                             | 中：虚拟耦合 RL 协同                  |
| 上海交大 JVS. *坡道上重载列车纵向冲动研究.* 2013.                                                                                                  | JVS (上海交大)                                           | 中：坡道 + 制动不同步 + 车钩力            |
| Zhou, Sheng, Liu. *基于钩缓特性曲线考虑不确定因素的重载列车驾驶过程优化方法.*                                                                                 | 华东交通大学                                               | 中：车钩特性曲线 + 多质点建模              |

#### 2.2.1 ⭐ 优先获取：车钩力**实测**数据（2026-09-02 登记）

> 动机：本项目所有车钩力结论目前都是模型推断，缺实测锚。以下为已核实的**实测/试验数据**文献。

| 文献                                          | 出处                                                                                      | 数据性质                                                                                             | 状态                                                                                                                                                                    |
| :------------------------------------------ | :-------------------------------------------------------------------------------------- | :----------------------------------------------------------------------------------------------- | :-------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **王鼎, 苗晓雨, 姜成. 大秦线 2 万 t 重载列车货车车钩力跟踪试验研究.** | 铁道车辆, 2023, 61(1): 102-105. DOI: 10.3969/j.issn.1002-7602.2023.01.021（中国铁道科学研究院机车车辆研究所） | ⭐⭐⭐ **46 次跟踪试验实测车钩力**（测力车钩）；大秦线湖东—茶坞；固定测点 106 位 + 非固定测点 8 个位置；**化稍营—涿鹿（−8.2‰）、延庆—茶坞（−9.1‰）循环制动** | ✅ **已下载并已提取**（2026-09-02）：`docs/papers/01_coupler_physics/大秦线2万t重载列车货车车钩力跟踪试验研究_王鼎.pdf`、信息卡 `王鼎2023_大秦线车钩力跟踪试验.md`、验证基准 **V3.5.7**（判据 D1–D6）—— **2250 kN 限值与 safety\_layer 一致；四源量级交叉印证** |
| **王鼎. 重载组合列车制动工况下列车纵向力影响因素分析.**             | 太原铁道科技, 2023(1): 14-17                                                                  | ⭐⭐ 同上批试验，典型相关分析 + 多元回归，给出**循环制动每把闸缓解位置**                                                         | 🟡 **未找到电子版**（内部刊物，知网/维普可能不收录；可试万方/掌桥科研，或发邮件向铁科院王鼎索取）                                                                                                                 |
| 姚小沛. *1+1 编组 2 万 t 列车循环制动车钩力研究.*            | 铁路重载机车研讨会, 中国铁道学会, 2013                                                                 | ⭐⭐ 循环制动车钩力（赵紫宁引\[56]用于一致性对照）                                                                     | 🔴 待获取（会议论文，较难）                                                                                                                                                       |
| **张二田. 朔黄铁路 2 万 t 重载组合列车纵向车钩力分析及应用研究.**     | 神华科技 / 国家能源集团朔黄铁路, 2021, 19(1): 74-78                                                   | ⭐⭐⭐ **朔黄线 2 万 t 动力学试验数据**（纵向车钩力、纵向加速度分布规律）                                                       | ✅ **已在库并已提取**（2026-09-02）：信息卡 `张二田2021_朔黄2万t车钩力实测.md`、验证基准 **V3.5.5**（判据 S1–S7）                                                                                       |
| **刘博阳, 魏伟, 豆飞. 重载列车制动力判断标准及纵向冲动研究.**        | 大连交通大学学报, 2022, 43(6): 38-44. DOI: 10.13291/j.cnki.djdxac.2022.06.007                   | ⭐⭐⭐ **列尾压强→拉钩力 −44.5%/−20.9% 定量规律**；缓解传播时序；TABLDSS 获奖仿真系统                                        | ✅ **已在库并已提取**（2026-09-02）：`重载列车制动力判断标准及纵向冲动研究_刘博阳.pdf`、信息卡 `刘博阳2022_列尾压强与车钩力.md`、验证基准 **V3.5.6**（判据 L1–L6）                                                            |

**其他实测数据渠道（待评估）**：

- **国能朔黄铁路 LKJ 数据集**：北京国际大数据交易所已上架"机车实时状态监测及模块化智能诊断数据集"
  （LKJ + OCS + 动力学设备，2024-10\~2025-09，约 147 亿条记录，7695 字段）。
  ⚠️ 数据产品通常**付费 / 面向机构**，个人获取成本高；可作为**课题组或导师渠道**的长期选项。

- **图数字化**：用 WebPlotDigitizer 从已入库 PDF 的曲线图（如赵紫宁图 5-3、图 5-4）提取数据点，
  成本最低、今天即可做，是"准实测数据"的现实来源。

**⚠️ 必须分清的两类数据**：

- **LKJ 运行数据**（速度 / 公里标 / 管压 / 手柄位）→ **不含车钩力**，只能做"速度曲线锚"；

- **车钩力实测**（测力车钩专题试验）→ 极稀缺，是验证纵向冲动量级的唯一硬锚。
  → 即使拿到 LKJ，车钩力仍须靠模型推断或专题试验数据，这正是"双模型交叉验证"不可省略的原因。

#### 2.2.2 顺藤摸瓜（2026-09-02 提取张二田论文发现的相关文献）

| 文献                                       | 出处                                                                    | 相关性                                                         | 状态             |
| :--------------------------------------- | :-------------------------------------------------------------------- | :---------------------------------------------------------- | :------------- |
| 伏远昱. *大秦线 2.1 万吨列车中部机车与车辆车钩分离问题初探.*      | 铁道机车车辆, 2020, 40(4)                                                   | 高：大秦线实测、中部机车钩缓问题（王鼎引\[1]）                                   | 🔴 待获取         |
| 姚小沛, 王磊, 邵军, 等. *重载组合列车纵向性能的影响因素分析.*     | 铁道机车车辆, 2014, 34(6): 8-12                                             | 高：重载组合列车纵向性能（张二田引\[1]；赵紫宁引\[56]）                            | 🔴 待获取         |
| 马大炜, 王成果, 冀彬. *2 万 t 级重载列车的技术对策及其纵向力研究.* | 铁道机车车辆, 2008, 28(z1)                                                  | 高：2 万 t 纵向力（王鼎引\[2]）                                        | 🔴 待获取（增刊）     |
| 冀彬, 马大炜, 王成果. *大秦线重载列车下坡道安全运行的技术对策研究.*   | 铁道机车车辆, 2008, 28(4): 36-37                                            | 高：大秦线下坡道操纵对策（张二田引\[2]）                                      | 🔴 待获取         |
| 刘博阳, 魏伟, 豆飞. *重载列车制动力判断标准及纵向冲动研究.*       | 大连交通大学学报, 2022, 43(6): 38-44. DOI: 10.13291/j.cnki.djdxac.2022.06.007 | 高：朔黄线列尾压强→最大拉钩力\*\*−44.5% / −20.9%\*\* 定量断言（魏伟团队 + 朔黄机辆分公司） | 🟡 优先下载（北交大知网） |

### 2.3 通过 scholar-search-mcp（Semantic Scholar）新检索到的关键论文

> 已配置 API key，Semantic Scholar 通道稳定。以下论文摘要已提取，含完整 DOI。

| 文献                                                                                                                                                    | 出处 / DOI                                        | 相关性（摘要要点）                                                                                                   |
| :---------------------------------------------------------------------------------------------------------------------------------------------------- | :---------------------------------------------- | :---------------------------------------------------------------------------------------------------------- |
| **Wang, Wang, Sun.** ***Operation Optimization of Heavy Haul Train Considering Longitudinal Impulse Suppression: a DQN Approach.*** **2025.**         | IEEE ICIRT, `10.1109/ICIRT66379.2025.11216684`  | **⭐⭐ 核心对标**：DQN + 简化动力学 + 多参数空气制动等效模型 + 循环制动约束；优化安全/车钩力稳定/速度跟踪；优化制动时机、电制动力协调、车钩力分布。降低最大拉力 9.64%、最大压力 28.77% |
| **Chen, Yang, Jin, Ren.** ***Distributed Global Composite Learning Cooperative Control of Virtually Coupled Heavy Haul Train Formations.*** **2024.** | IEEE TITS, `10.1109/TITS.2024.3360945`          | **⭐⭐ 创新点呼应**：虚拟耦合重载列车编队 + 电空制动算法（改善纵向冲动）+ NN 逼近动力学不确定 + 安全间隔/避碰。正合"群组+车钩力"                                  |
| Ran, et al. *Dynamic identification of longitudinal impulse of heavy-haul locomotive.* 2025.                                                          | Meas. Sci. Technol., `10.1088/1361-6501/addc03` | 高：提出纵向冲动综合指标 CEILI + 多尺度卷积 + 极限学习机识别                                                                        |
| Ma, Bao. *Optimization of Empty Railcar Distribution... DRL.* 2026.                                                                                   | MDPI, `10.3390/futuretransp6030127`             | 中：MDP 建模 + DQN + 经验数据融合                                                                                     |
| Qu, et al. *Comparison of ML algorithms for rapid prediction of operational safety indicators.* 2026.                                                 | `10.1177/1748006X261430836`                     | 中：LSSVM 代理模型预测重载列车安全指标（LTD+MBD 联合仿真）                                                                        |

### 2.4 方向检索补充（通过 MCP，多个研究方向）

**方向 A：分布式制动 / 纵向冲动 / 空气制动建模**

| 文献                                                                                                                                            | 出处 / DOI                                            | 说明                                                                                                                            |
| :-------------------------------------------------------------------------------------------------------------------------------------------- | :-------------------------------------------------- | :---------------------------------------------------------------------------------------------------------------------------- |
| **Zhang, Liu, Guo 等.** ***Research on Longitudinal Dynamics of 20,000-Ton Heavy Haul Trains Considering Braking Characteristics.*** **2025.** | Mathematics, `10.3390/math14010158` (**GOLD/CCBY**) | **⭐⭐ 制动对标数据**：制动缓解不对称、制动管减压（50/70/100kPa → +16.8%/+36.8% 压钩力）、可控尾车延迟 3s 提升同步、尾车充风使最大拉钩力 780→489kN（-37%）。**可直接验证你的空气制动波速传播模型** |
| Ran, Chen, Wang 等. *Digital twin modelling of heavy-haul train for longitudinal impulse simulation.* 2025.                                    | VSD, `10.1080/00423114.2025.2483348`                | 高：数字孪生 + 实测标定预测纵向冲动，含阻力/钩缓/空气制动子系统                                                                                            |
| Liu, Wang 等. *A heavy-haul train longitudinal-vertical coupled dynamics model under emergency braking.* 2024.                                 | VSD, `10.1080/00423114.2024.2353705` (17 引用)        | 高：钩缓非线性迟滞 + 制动延迟/气缸压力 + 紧急制动长下坡                                                                                               |
| Hu, Zhang. *Research and simulation analysis of braking longitudinal impulse of 30,000-ton heavy-duty train.* 2025.                           | `10.1117/12.3060615`                                | 中：编组/初始制动速度/坡度/曲线对纵向冲动影响（1+1+1+1 编组冲动最小）                                                                                      |

**方向 B：虚拟耦合列车（VCTS）编队协同**

| 文献                                                                                                                            | 出处 / DOI                                     | 说明                                                          |
| :---------------------------------------------------------------------------------------------------------------------------- | :------------------------------------------- | :---------------------------------------------------------- |
| **Li, Tong, Giua.** ***Safe Optimal Train Formation Control in Virtual Coupling Using Control Barrier Functions.*** **2024.** | IEEE CASE, `10.1109/CASE59546.2024.10711420` | **⭐⭐ CBF/CLF + QP**：虚拟耦合编队安全最优控制——**正是你要做的"CBF 理论强化安全层"方向** |
| Gong, Wei, Song 等. *DRL-Based Optimization of LQR for Virtual Coupling Train Interval Control.* 2025.                         | IEEE ITSC, `10.1109/ITSC60802.2025.11423016` | 高：DDPG 优化 LQR 参数，间距控制精度提升 68.5%                             |
| Liang, Chai 等. *A Cooperative MPC Approach for Virtual Coupling Train Arrival in Metro.* 2026.                                | IEEE TITS, `10.1109/TITS.2026.3684075`       | 高：DCMPC 分布式协同 MPC + 终端约束，通过能力 +4%                           |
| Wang, Wang, Feng 等. *Cooperative Control of Heterogeneous Virtual Coupling Oriented to Variable Tracking Gap.* 2025.          | `10.23919/CCC64809.2025.11178698`            | 中：变速跟踪间隙异质 VC 协同巡航                                          |
| Che, Lu 等. *Cooperative Control of Subway Train Virtual Coupling with Input Saturation and Quantization.* 2025.               | IEEE ITSC, `10.1109/ITSC60802.2025.11423193` | 中：输入饱和 + 量化 + backstepping + RBF NN                         |

**方向 C：重载列车能耗优化 / 最优驾驶**

| 文献                                                                                                                                            | 出处 / DOI                                                           | 说明                                              |
| :-------------------------------------------------------------------------------------------------------------------------------------------- | :----------------------------------------------------------------- | :---------------------------------------------- |
| **Yang, Miao, Wang.** ***Driving Strategy Using an Improved Ant Colony System for Energy-Efficient Train.*** **2024.**                        | J. Advanced Transportation, `10.1155/2024/5964428` (**GOLD/CCBY**) | 高：ACSd 差分边蚁群 + ODSD 最优驾驶策略决策模型                  |
| **Heineken, Richter, Birth-Reichert.** ***Energy-Efficient Train Driving Based on Optimal Control Theory.*** **2023.**                        | Energies, `10.3390/en16186712` (**GOLD/CCBY**)                     | 高：Pontryagin 极大值原理 + 再生制动，**节能 37%**，含完整驾驶方式切换表 |
| Yildiz, Arikan. *Energy-efficient train operation strategy for human-driven trains... Istanbul Subway.* 2025.                                 | `10.1080/03081060.2025.2457048`                                    | 中：GSA 遗传退火优化加速杆，实车节能 31%                        |
| Zou, Chu 等. *Energy-efficient operation trajectory optimization of heavy-haul trains based on hybrid biological intelligent heuristic.* 2025. | `10.1016/j.jrst.2025.07.003` (HYBRID)                              | 中：混合生物启发式重载列车轨迹优化                               |
| Yang, Xu, Fu. *Research on Multi-objective Optimal Control of Heavy Haul Train Based on Improved GA.* 2022.                                   | IEEE IAI, `10.1109/IAI55780.2022.9976810`                          | 中：FAGA 模糊自适应 GA + 迭代学习控制跟踪目标曲线                  |

**方向 D：多智能体 MARL 列车/车队协同（与你的群组级设计直接对应）**

| 文献                                                                                                                               | 出处 / DOI                                                               | 说明                                                                                       |
| :------------------------------------------------------------------------------------------------------------------------------- | :--------------------------------------------------------------------- | :--------------------------------------------------------------------------------------- |
| **Zhang, Nie, Ni, Tian.** ***Multi-Agent DRL Based Consistency Control in Train Platoon Systems.*** **2021.**                    | IEEE HPCC, `10.1109/HPCC-DSS-SmartCity-DependSys53884.2021.00211`      | **⭐⭐ 群组级设计**：列车编队 leader-follower + 分布式 MADRL + **人工势场先验**，距离/速度一致性 + 抗干扰。与你的"层级一"设计完全对应 |
| **Guo, Peng, Pi, Zhang, Wu, Ma.** ***Enhanced consensus control architecture for autonomous platoon utilizing MARL.*** **2025.** | Comput-Aided Civ & Infra Eng, `10.1111/mice.13463` (**HYBRID/CCBYNC**) | 高：双向协同优化解耦跟踪行为与内部协调 + LSTM 时序建模，间距误差 -8.3%、编队长度 -19.1%                                   |
| Wibisono, Song, Lee. *A Survey of MARL for Cooperative Control in Multi-AUV Systems.* 2025.                                      | IEEE Access, `10.1109/ACCESS.2025.3609457` (**GOLD/CCBY**)             | 中：MARL 综述（VDN/QMIX/MPDDPG/**MAPPO** + CTDE + PettingZoo 环境），含 MAPPO/MADDPG 对比实验          |

> **说明**：方向 A/B/C/D 的 GOLD/HYBRID/CCBY 开放获取论文**浏览器可直连下载，但程序化下载被出版社反爬拦截（403）**，需手动下载。

***

## 三、可从论文直接复现的技术点（Reusable Ideas）

> 标注 **可复现** 的标准：论文给出了可实现的公式/结构/参数，无需额外专有数据。

### 3.1 从 Tang (2020) —— 已下载

| 可复现技术点                      | 说明                                 | 对应本项目              |
| :-------------------------- | :--------------------------------- | :----------------- |
| **多目标奖励函数**                 | 目标 = 速度 + 能耗 + 车钩力；约束 = 机车档位及档位变化率 | 可复用/对比             |
| **Double-Switch-Q-network** | 双开关 Q 网络架构（处理连续机车档位选择）             | 可选做对照算法            |
| **车钩力建模**                   | 纵向动力学中显式建模车钩力                      | 已实现于 `coupler.py`  |
| **机车档位约束**                  | 档位离散 + 变化率限制                       | 已实现于 `tractive.py` |

### 3.2 从 Bulavin & Ignatieva (2024)

| 可复现技术点         | 说明                                | 对应本项目   |
| :------------- | :-------------------------------- | :------ |
| **多体 ODE 动力学** | 列车建模为多体 ODE 系统（与你的 `train.py` 一致） | 已实现     |
| **DRL 降纵向力**   | 以纵向力（车钩力）为优化对象的 DRL 策略            | 奖励已含冲动项 |

### 3.3 从宋宗莹等 (2026) —— MAPPO 群组（已下载元数据）

> 摘要确认：研究**由多列独立重载列车组成的运营编组**的智能协同控制，采用 **MAPPO**。
> 奖励 = **势场安全引导** + **多目标优化**（速度同步、间距保持、能耗）。
> **不含车钩力**（聚焦宏观运行层）→ 这正是本项目"加入车钩力"的差异创新空间。
> 作者单位含国家能源集团/神华（大秦线背景），基金：GJNY-22-7。

| 可复现技术点             | 说明                        | 对应本项目   |
| :----------------- | :------------------------ | :------ |
| **MAPPO + 多列群组协同** | 每列列车为智能体，速度同步 + 间距保持 + 能耗 | 层级一框架   |
| **势场安全引导奖励**       | 用势场把安全约束编码进奖励             | 可借鉴到安全层 |
| **高保真纵向动力学环境**     | 自建纵向动力学作为仿真环境（与你的做法一致）    | 已实现     |

### 3.4 从虚拟耦合类 (Lin 2025, 等)

| 可复现技术点             | 说明                                                              | 对应本项目   |
| :----------------- | :-------------------------------------------------------------- | :------ |
| **安全间距约束**（相对制动距离） | `x_safe = x_min + max((v_prev²/2F_brake - v_i²/2F_brake)·M, 0)` | 层级一约束   |
| **MPC 跟随**         | 跟随列车用 MPC 追踪领航曲线                                                | 可选做基线   |
| **离散动作档位**         | 5 牵引 + 惰行 + 5 制动的离散动作空间                                         | 可对比连续动作 |

### 3.4.1 从赵紫宁 (2022) —— 空气制动精细建模 + QP 操纵优化（已下载）

> 数据表 SSOT → [`docs/papers/01_coupler_physics/Zhao2022_AirBrakeRefinedModeling_Optimization.md`](papers/01_coupler_physics/Zhao2022_AirBrakeRefinedModeling_Optimization.md)
> 验证判据 B1–B6 → [`VALIDATION_BASELINE.md`](VALIDATION_BASELINE.md) [V3.5.4](VALIDATION_BASELINE.md)

| 可复现技术点        | 说明                                                                | 对应本项目                                                   |
| :------------ | :---------------------------------------------------------------- | :------------------------------------------------------ |
| **三段式空气制动模型** | 响应 / 暂态 / 稳态；闸瓦压力分布函数 K\_{z,i}(t)（λ\_z/γ\_z/K\_z）+ 历史修正函数 P\_s(t) | 升级 `train_dynamics/braking.py`：传播延迟 + 充气时长 + **循环制动衰减** |
| **制动波速实测标定**  | 尾车 t\_N=14 s、全长 2 684 m → ≈192 m/s（项目用 200 m/s ✅）；整列建立 58 s       | 直接校验 `braking.py` 波速参数                                  |
| **循环制动性能衰减**  | C\_β 1.379→0.972→0.932（−32%），源于缓解充风不足 + 闸瓦温升                      | 当前未建模 → **可补创新点 / limitation 素材**                       |
| **操纵规则量化**    | 缓坡段缓解、缓解后电制力保持 ≥50 s、分相带闸                                         | 转为 Layer-1 规则循环制动的硬约束                                   |
| **QP 最优控制基线** | 压钩力 −29.49%（+规则 −33.74%）                                          | 论文对比实验的**非 RL 对照组**                                     |
| **遗传算法参数辨识**  | 以速度曲线拟合度为适应度，4 参数 10 bit 编码                                       | 可用于标定本仿真器的制动参数                                          |

**⭐ 立足点金句（作者结论与展望 (2)）**：

> "并未使用纵向动力学模型作为基础解算框架，故无法用车钩力大小作为平稳性优化目标。"
> ——引作本项目分层 MARL 相对 QP/最优控制类方法的动机证据。

### 3.5 可直接用的开源资源（非论文但可复现）

| 资源                                                | 用途                                |
| :------------------------------------------------ | :-------------------------------- |
| **NeTrainSim**（GitHub: VTTI-CSM/NeTrainSim）       | 本项目动力学公式源头（Davis、牵引、Karwatzki 制动） |
| **gym-pybullet-drones**（本地已 fork）                 | 阶段一仿真器，已验证                        |
| **MAPPO 实现**（本项目 `src/algorithms/mappo_agent.py`） | 阶段一已收敛，直接迁移到列车                    |

***



<!-- 该文档整理/压缩于 2026-10-01；覆盖式清理 + 瘦身于 2026-10-12（进度/带宽/研究对象/文献清单口径核对；删 §四 已 superseded、§五 并入 docs/README.md 唯一索引，git 历史可查；维护规矩见 docs/rules/CHECKLIST_NEW_DOC.md「如果改立论文档」） -->
