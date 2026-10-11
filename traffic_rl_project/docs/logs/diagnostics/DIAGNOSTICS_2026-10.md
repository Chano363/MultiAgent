***

title: 实验 / 诊断数据记录（2026-10）
date: 2026-10-01
status: active
owner: Owner + Agent
supersedes: —
------------------------------------------------------

# 实验 / 诊断数据记录（2026-10）

> **记录法则**：沿用 [`DIAGNOSTICS_2026-09.md`](DIAGNOSTICS_2026-09.md) 顶部「记录法则」（原始数据落盘 / 完整命令 / seed+超参 / 分组明细 / 结论可解释 / 失败同样记录）。本文件为 **2026-10 按月新文件**，**append-only**。
> **承接**：X1/X2/X4 判别性实验的**原始数据**在 [`DIAGNOSTICS_2026-09B.md`](DIAGNOSTICS_2026-09B.md)「诊断-2026-09-30-X1/X4」；本文件承接其结论做**根因归因**与**文献解法调研**。

## 索引

- 诊断-2026-10-01-「MARL 不行」根因归因（奖励口径 / AB 通路 / 安全层权限 / 信用分配）
- 调研-2026-10-01-同类问题的文献解法（文献 → 病根 → 解法对照）
- 改造-2026-10-01-文献四改造落地（A 充风门 / D 安全层 AB 权限 / C 车钩力进目标 / B per-agent advantage）
- 诊断-2026-10-01-P0 三行基线（现行断面力口径）与 AB 通道裁定
- 验证-2026-10-01-主训练 YAML 按 ADR-017 对齐（配置解析短训验证）
- 修复-2026-10-01-long_eval 违规计数口径（O(n²) 放大）+ 端到端预检
- 修复-2026-10-01b-`--mode all` 主对比链路三处缺陷（MPC 行缺失 / MPC 状态残留 / solve_statuses 崩溃）
- 启动-2026-10-01-ADR-021 口径 seed0 1400 ep 重训（含"长跑进程持久化"排障）
- 检索-2026-10-01-`ab_min_hold_s` 文献结案（负结果：无运行期最小 AB 保持时长出处）
- 修复-2026-10-01c-评估链路第五处缺陷：`--decision_interval` 默认 1 与训练的 10 **静默失配**
- 更正-2026-10-01-机时估算低估 3.4×（≈3.4 天 → **≈11.7 天/seed**，含推导与 tqdm ETA 陷阱）
- 审计-2026-10-01-主表 checkpoint 选取：`best.pt` **不保证存在**（仅 long_eval 达标才写）+ 主表用 `last`/`best` 待裁决
- 审计-2026-10-01b-主表 MPC 行的**动作桥接量纲错配**（实测：指令 ED 0.75 → 实际打满 1.0；且永不能减闸/牵引）+ 默认 `fair` 未开 `inner_rule_cyclic`
- 修复-2026-10-01d-MPC 桥接量纲错配（M1）**甲方=反解加性关系**修复（用户裁定）+ M3/M4 + 规则层审计（R1/R2/M2）
- 删除-2026-10-01-MPC 基线唯一化为 NMPC（ADR-022）：删 `FairMPCController`/简化 `MPCController` + 旧评估脚本链
- 停训-2026-10-03-adr024 长训严重震荡的根因诊断与修复（ADR-025：AB 否决覆盖 90s 滞后 / ValueNorm 指数遗忘 / KL 判据标准化）

***

## 条目区

### 诊断-2026-10-01-「MARL 不行」根因归因（奖励口径 / AB 通路 / 安全层权限 / 信用分配）

- **诊断日期**：2026-10-01
- **主题 / 触发**：判定"当前 MARL 就是不行"（长剖面破 1000 kN 红线、不敌规则层），要求**停止重跑**、直接用**已有代码 + 已有诊断**给出根因。
- **口径与范围**：本条是**代码级 + 既有资产**的归因分析，**不新跑实验**；每条结论标注证据来源（代码行 / 既有 JSON / 既有诊断条目）。破线口径 = 断面力 `coupler_interface_forces()`（ADR-018 SSOT）。

#### 一、结论（一句话）

不是 MAPPO 范式失效，而是**多条链同时断开**：奖励没把车钩力当目标（量级 ≈3% 且无超限跳变）、AB 通路绕过安全层、闸门管不到真正破线的那条通道、信用分配视界（17 s）远短于 AB→峰值的物理滞后（≈90 s）。**同时必须诚实记录：跨权重"AB 用得多 → 峰值高"的单调相关被数据否证**（见 §五）。

#### 二、断点 1｜奖励口径：车钩力量级 ≈3%，且"超限"无跳变

代码锚 `train_fleet_env.py:_calculate_reward_decomposed`：

- 主项 `speed_band_reward` 带内最高 **+6.0/列**（`:739`）；带外 `−0.2×(norm_dev−1)×100`（`:741`，norm_dev=2 → **−20**）。
- 车钩力项 `coupler_term = −0.2·mean(obs[:,5]) − 0.2·peak_norm`（`:766`），**理论上限 −0.4** ⇒ 单列口径下仅为速度带收益的 **≈6.7%**，多列叠加（gap/rel_anchor 项）后占比更低。
- **无"超限跳变"**：`−80·ov²` 硬惩罚已于 2026-09-10 回滚（`:757-760` 注释），现行 peak 项只是**线性归一化**、上限 −0.4 ⇒ **破线与不破线在 reward 上几乎不可区分**。
- **反向推力**：`:822-824` `needs_brake and ab_count<=0 → ab_cost -= 0.5`（"带外/超速却无 AB → 弱惩罚"）⇒ 奖励**显式倒逼"需减速必须靠 AB"**（借自 Zhang2024 需求驱动塑形，见 `docs/papers/Zhang2024_DQN_CyclicBraking_Downhill.txt:632-655`）。
- ⇒ 学习信号里**保速度带（+6）远强于控车钩力（≤0.4）**；下坡保带的唯一手段是 AB ⇒ 梯度指向"多用 AB"。

#### 三、断点 2｜AB 通路：`ab_sources` 在安全层之前组装，安全层只回写 ED

代码锚 `train_env.py:_step_decomposed`：

- `ab_sources` 由 RL 动作逐机车组装（`:474-491`），**在安全层之前**；
- 安全层 `self.safety.protect(proj_throttle, ...)`（`:509`）只作用于 `proj_throttle`，回写的是 `ed_throttle`（`:522-524`）；
- AB 唯一的安全层干预是把 `ab_command` **升格为 EMERGENCY**（`:517-520`，ETCS EBI 触发）——是"加"不是"减"。
- ⇒ **安全层对 RL 的 AB 源无"减"权限**（ED 有投影，AB 没有）。即 `诊断-2026-09-30-100ep破线根因 ⑤` 的代码级根因，`ab_sources` 直通 `dynamics.step_vehicles_ed_ab`（`:528`）。

#### 四、断点 3 + 4｜闸门有效域窄 + 在生产（确定性驱动）策略上 no-op

代码锚 `multi_loco_controller.py`：

- 常量 `AB_FALLBACK_NOTCH=-0.4`（`:201`）、`AB_ADD_SOURCE_MAX_RATIO=0.6`（`:211`）、`AB_MAX_CONCURRENT_ADD=1`（`:213`）；
- 接线 `:253`（`safety.ab_new_source_veto`）+ `:280-283`（仅当 `cur_coupler_ratio<0.6 且 added<1` 才允许 RL 新增 AB 源）。
- **有效域 = "RL 新增 AB 源"通道 ∩ 策略实际使用的动作子集**；规则基线循环制动（`get_action_cyclic_braking`）触发的 AB 源**不经过闸门**。
- X1 实测（`DIAGNOSTICS_2026-09B.md`）：生产 ckpt 闸门 on/off **轨迹逐位相同**（`final_seed0_v2` 761.0 kN / `final_seed1_v2` 627.1 kN，均 0 破线）⇒ **no-op**；仅采样探索态部分有效（1165.6 vs 1268.9）且**仍破 1000 kN**。决策见 **ADR-020**。

#### 五、断点 5｜信用分配：单标量 advantage 广播 + 视界 17 s ≪ 滞后 90 s

代码锚 `mappo_agent.py`：

- `gamma=0.99` / `gae_lambda=0.95`（`:173-174`）；`compute_gae` 对每步只产出**一个标量**（`:323-337`）；
- `:464-465` `adv_broad = batch_advantages.unsqueeze(-1)` 把该标量**广播到全部 agent** ⇒ 6 台机车共用同一 advantage，**分不清"哪台机车该负责"**（即多智能体信用分配问题）。
- **有效信用视界** = 1/(1−γλ) = 1/(1−0.9405) ≈ **17 决策步 = 17 s**（DI=10）；而 `诊断-2026-09-30-100ep破线根因` 实测 **AB 首现 t=0 → 首破 t=901（≈90 s）**。⇒ 90 s 后的峰值无法反传到触发它的 AB 动作上（权重 ≈ e^{−90/17} ≈ 0.005）。

#### 六、诚实边界｜"AB 步数越多 → 车钩力峰值越高"的单调相关**被否证**

既有 53km 评估（`outputs/results/decompose/eval_decompose_decompose_m1_ms36000_*_53km.json`，均 `physics_version=29569dcaf78a`）：

| 权重 | ab_steps | 断面力峰值 kN | band_rate | 末速 km/h | reward |
| :--- | ---: | ---: | ---: | ---: | ---: |
| `seed0_nep1400/last_ep841` | 3419.4 | **824.6** | 0.971 | 61.2 | +221163 |
| `s0_ep1623` | **10753.0** | **863.5** | 0.997 | 72.0 | +87648 |
| `s1_ep811` | 4285.0 | 1242.3 | 0.916 | 62.9 | −1.94e7 |
| `best_s0` | **13987.0** | 1682.5 | 0.898 | 47.7 | −173606 |
| `best_s1` | 6591.0 | 1250.9 | 0.981 | 63.0 | −2.00e7 |

> ⚠️ 表中 `viol` / `safety_events` 字段**未列且不可用**：其量级异常（1e6~1e10），为旧**每车净力口径 + O(n²) 累加**遗留，须按 ADR-018 断面力口径重算（ADR-020「更正」(c)）。

- **否证**：`s0_ep1623` 的 `ab_steps=10753`（全表最高之一）却 **863.5 kN / band 99.7%**（安全）；而 `best_s1` 的 `ab_steps=6591`（更低）反而 **1250.9 kN（破线）**。⇒ 决定破线的**不是"AB 用得多"，而是"AB 新增源的时空分布"**（同一时刻多源叠加 / 集中在列尾时破线）。
- **受控实验支持该解释**：X4-a「在飞波锁」（禁止在飞波期间新增源）把峰值 1268.9 → **777.1 kN / 0 破线**（与闸门开关无关）；X4-b「撤销已发源」恶化（1268.9 → 1323.5 kN / 103 破线步）。
- ⇒ **不得**把 53km 破线归因于"AB 用量"或"架构本身"；`last` 权重可守线（`ep841` / `ep1623`），破线样本对应 **选错权重 / 训练不足 / 新增源时空分布失控**。

#### 七、归因汇总（每条标注证据）

| # | 断点 | 关键证据 | 后果 |
| :--- | :--- | :--- | :--- |
| 1 | 奖励：车钩力量级 ≈3% 且无超限跳变 | `train_fleet_env.py:739/741/766`；`−80·ov²` 已回滚 `:757-760` | 控压力梯度被保带梯度淹没 |
| 2 | 奖励反向推力：needy 无 AB 罚 | `train_fleet_env.py:822-824` | 倒逼"必须用 AB" |
| 3 | AB 通路绕过安全层 | `train_env.py:474-491` vs `:509/:522-524` | AB 无 ≤1000 kN 兜底 |
| 4 | 闸门有效域窄 + 确定性 no-op | `multi_loco_controller.py:211/213/253/280-283`；X1 | 破线通道无人管辖 |
| 5 | 信用分配：标量 advantage + 视界 17 s ≪ 滞后 90 s | `mappo_agent.py:173-174/323-337/464-465`；诊断 09-30 | 峰值无法反传到肇因动作 |

#### 八、修复方向（候选，需实验裁决；决策见 ADR-021）

1. **给车钩力真正的学习信号**：把"超限"做成非线性项（量纲受控），或按文献改走约束集 / safety filter；使破线与不破线在目标里可区分。
2. **限制 AB 新增源的时空分布**（非一刀切锁死）：错峰 / 单位长度源密度上限 / 有界配额（X4-a 已证机制有效，需找可部署形态）。
3. **AB 加最小充风时间约束**（Zhang2024 把最小充风时间做进动作空间），抑制"缓解—再制动"循环。
4. **修复信用分配**：per-agent advantage（COMA 反事实基线 / PRD-MAPPO）+ 视界覆盖延迟窗口（n-step / λ 对齐）。
5. **补齐训练量 + 正确选权重**（ADR-017）：1400ep × 5 seed，主结果用 `last` 而非"训练 reward 选优的 `best`"。

- **不做（已裁决）**：削减已发 AB 源（X4-b 反证恶化）；在飞波全锁（废 AB 杠杆，ADR-020）。
- **复现命令 / 产物**：本条为代码 + 既有资产归因，无新命令；既有资产出处 = `outputs/results/decompose/eval_decompose_decompose_m1_ms36000_*_53km.json`（**不覆盖**）。
- **状态**：归因完成；修复方向写入 `docs/logs/decisions/DECISIONS.md` **ADR-021**（待实验裁决）。

***

### 调研-2026-10-01-同类问题的文献解法（文献 → 病根 → 解法对照）

- **诊断日期**：2026-10-01
- **动机**：上一条归因出断点后，检索"同类问题别人怎么解"——本地库（`docs/papers/`）+ web。
- **引用纪律**：外部权威标注原文出处；本地文献给文件路径；**未核实到 DOI 的一律不给编号**。

#### 一、车钩力 / 纵向力怎么进学习目标（对应断点 1）

| 做法 | 代表工作（出处） | 与我们断点的对应 |
| :--- | :--- | :--- |
| 进 reward 目标（多目标加权） | Tang2020（本地 `docs/papers/Tang2020_DoubleSwitchQ.pdf`，多机车 + 车钩力建模 + 多目标）；Wang2025 ICIRT DQN（`10.1109/ICIRT66379.2025.11216684`，最大拉力 −9.64% / 最大压力 −28.77%） | 给车钩力**有量级的**目标信号，替换我们 ≈3% 的 shaping |
| 进约束集（分层 / MPC） | 魏咪等（本地 PDF，车钩力约束分层框架）；宋宗莹等 2026 Tube-MPC（本地 PDF，`10.11860/j.issn.1673-0291.20250156`，车钩力峰 330.4 kN ≤22% 限值）；Fu2019（本地 PDF，钩缓约束 + 预测控制） | 与 ADR-014"约束"定位一致，但需**可学习的对偶信号**，否则仍是"无梯度" |
| 运行时 safety filter / CBF | Wabersich & Zeilinger 2021, *A predictive safety filter for learning-based control of constrained nonlinear dynamical systems*, Automatica（arXiv:1812.05506）——**预测式 safety filter** 把约束系统变成"无约束安全系统"；Li, Tong, Giua 2024 CBF-QP（`10.1109/CASE59546.2024.10711420`） | 把 AB 通道纳入 filter 权限范围（补断点 3），且用**预测**而非反应式（破线是 ≈90 s 滞后） |

> **文献自带警示**：safety filter 与被保护策略**各自独立**训练/优化时会产生"冲突甚至振荡行为"（Pfrommer et al. 2022, L4DC, arXiv:2112.13941）——与本项目 X4-b 观察到的"缓解—再制动"恶化**同源**。⇒ 采用 filter 路线时必须处理两者一致性，而非简单加装。

#### 二、AB 的离散 / 时间约束（对应断点 2）

| 做法 | 代表工作（出处） | 对应 |
| :--- | :--- | :--- |
| 把**最小充风时间**做进动作空间 | Zhang2024（本地 `docs/papers/Zhang2024_DQN_CyclicBraking_Downhill.txt:566-577`：环境设计"considering ... constraints of the train pipe's air-refilling time"） | 从**动作定义层**杜绝"缓解—再制动"过快循环（正是闸门管不到的规则层通道） |
| AB 需求驱动塑形（越限罚 / engaged=0 / 释放奖） | Zhang2024（同上，`:632-655` reward 设计） | 我们 `train_fleet_env.py:822-824` 已借用其思想，但**缺"超限"项与"最小间隔"** |

#### 三、信用分配与延迟（对应断点 5）

| 做法 | 代表工作（出处） | 对应 |
| :--- | :--- | :--- |
| per-agent advantage（反事实基线） | COMA, Foerster et al. 2018, AAAI, *Counterfactual Multi-Agent Policy Gradients*（中心化 critic + 反事实基线，替换"广播同一标量"） | 直接解我们 `mappo_agent.py:464-465` 的"6 台机车共用 advantage" |
| 在 MAPPO 上做信用解耦 | Kapoor, Freed, Choset, Schneider 2024, RLJ/RLC, *Assigning Credit with Partial Reward Decoupling in Multi-Agent PPO*（PRD-MAPPO：动态拆小子群） | MAPPO 原生信用分配弱，可直接叠加 |
| 视界覆盖延迟 | GAE（Schulman et al. 2016）有效视界 ~1/(1−γλ)；n-step / λ-return 是拉长视界的标准手段 | 我们 γλ=0.9405 → 17 s，需拉到 ≥ 物理滞后（≈90 s）或改半马尔可夫 / 决策间隔 |

#### 四、结论

- 本问题**不是无人遇过**：车钩力进目标/约束、AB 时间约束、per-agent 信用分配、predictive safety filter 四条都有成熟解法可对位。
- **最贴合本项目的组合**：① AB 最小充风时间进动作空间（Zhang2024，成本最低、不动架构）；② per-agent advantage（COMA / PRD-MAPPO，解断点 5a）；③ 车钩力进目标**或**升级为预测式 safety filter（二选一，解断点 1/3）。
- **必须保留的警示**：filter 与策略解耦会产生振荡（Pfrommer 2022），与 X4-b 现象同源 ⇒ 若走 filter 路线，须做一致性处理。
- **状态**：调研完成；组合方案与优先级见 `docs/logs/decisions/DECISIONS.md` **ADR-021**。

***

### 改造-2026-10-01-文献四改造落地（A 充风门 / D 安全层 AB 权限 / C 车钩力进目标 / B per-agent advantage）

- **日期**：2026-10-01
- **动机**：上一条「调研」已给出四条成熟解法，ADR-021 已定级；本条记录**代码落地 + 机制 on/off 隔离验证**（规格 `.trae/specs/implement-literature-informed-fixes/`）。
- **验收规程**：沿用 **ADR-020 第 4 条** —— ① on/off 隔离对照（量化机制**自身**贡献，而非"开了之后变好"）；② 在**确定性驱动策略**上给结论；③ **声明有效域**。

#### 一、落地清单（文献 → 代码）

| 改造 | 文献依据 | 代码落点 | 参数与出处 |
| :--- | :--- | :--- | :--- |
| **A** AB 最小充风时间 | Zhang2024（本地 `docs/papers/Zhang2024_DQN_CyclicBraking_Downhill.txt:250-255` 与 `:287-295`：**运行约束 (1) Air-refill time**，式 (9) `t_{b,j+1} − t_{r,j} ≥ T_a`——"释放相时长不得短于最小充风时间 `T_a`"） | `src/controllers/multi_loco_controller.py`（`_ab_gate` + 逐机车 `_ab_on/_ab_last_apply_step/_ab_last_release_step` + `ab_refill_veto_count`/`ab_hold_veto_count`） | `ab_min_refill_s=222.0 s`（**有出处**：式 (9) 的 `T_a`；数值取 `VALIDATION_BASELINE.md:201` 张二田 S6 最短充风 222 s，实测范围 175~512 s 见 `:169` 赵紫宁）；`ab_min_hold_s=0.0` **标 `待核实`**——已复查 Zhang2024 全文，其运行约束**只含"释放相 ≥ T_a"，没有"最短制动保持时长"约束**，故该项**无文献出处**，默认不激活（不编造） |
| **D** 安全层对 AB 的禁新增源 | Wabersich & Zeilinger 2021（arXiv:1812.05506，预测式 safety filter）+ ADR-021 决策 3 | `src/environments/train_env.py::_step_decomposed`（`safety.protect()` **之后**）；计数再经 `train_fleet_env.py::_step_decomposed_fleet` **跨列车聚合**入 fleet `info` | 复用既有 `SafetyLayer.ab_new_source_veto`（反应式 `ratio≥0.6` **或** 预测式 `P_pred≥0.9·limit`）；env 侧只做**新源丢弃**（0/1），**不撤销已建立源**。⚠️ 曾实现的 `scale<0.5 ⇒ 新源降一档` 梯度臂**可证不可达**，已于 2026-10-01 移除（证明见下） |
| **C** 车钩力受控超限项进 reward | Tang2020（本地 PDF）/ Wang2025 ICIRT（`10.1109/ICIRT66379.2025.11216684`） | `src/environments/train_fleet_env.py`（`REWARD_SCHEMA` / `COUPLER_OVER_W=6.0` / `COUPLER_OVER_CAP=2.0`；峰值口径改**断面力**） | 超限项 `-6.0·min(peak_norm−1, 2.0)`，上界 **−12.0**（刻意避开已回滚的 `-80·ov²` 量级） |
| **B** per-agent advantage + 信用视界 | COMA（Foerster 2018 AAAI）/ PRD-MAPPO（Kapoor 2024）/ GAE（Schulman 2016） | `src/algorithms/mappo_agent.py`（`critic` 枚举 / N 维价值头 / per-agent GAE / 去广播 / 视界换算）；`src/trainer/registry.py`；`src/metadata.py`；`src/evaluation/evaluate_decompose.py`（`probe_critic_mode`） | 主 YAML：`critic: per_agent`、`gamma=0.999`、`gae_lambda=0.99` ⇒ 视界 `1/(1−γλ)=91.0` 决策步 ×`DI=10`×`dt=0.1 s` = **91.0 s ≥ 90 s** |

#### 二、A 的 on/off 隔离对照（确定性驱动策略，12000 步窗口）

- **为何是 12000 步**：`ab_min_refill_s=222 s` ≈ **2220 原始步**；1200 步（120 s）窗口内该门几乎不触发 ⇒ 无法区分 on/off。12000 步 = 1200 s，含 ≥1 个完整循环制动周期。
- 复现：见本节「四、复现命令」。

| 配置 | reward | 断面力峰值 | 破线(车厢·步) | AB 源·步 | band 率 | 末速 | `ab_refill_veto` | `ab_hold_veto` |
| :--- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| **A_off**（`ab_min_refill_s=0.0`） | −39838 | **926.95 kN** | 0 | **4447** | 99.975% | 78.18 km/h | 0 | 0 |
| **A_on**（`ab_min_refill_s=222.0`） | **+36340** | **914.37 kN** | 0 | **2565** | 99.983% | 64.26 km/h | **6657** | 0 |

- **机制结论**：门**强绑定**（6657 次拒绝新增源）⇒ AB 用量 **−42.3%**（4447→2565）且**峰值略降**（926.95→914.37 kN）、band 不改（99.98%）、**无破线**。
- **有效域**：仅约束 **AB 源的新增/释放时序**（逐机车），不改变 ED 通道、不撤销已建立源；对**不使用 AB 新增源通道**的策略为 no-op。
- ⚠️ 末速 64.26 vs 78.18 km/h：on 组更保守（少用 AB ⇒ 下坡控速更依赖 ED/规则循环制动）。**不据此判优劣**（reward 已含带内与末态项；最终优劣须重训后评）。
- ⚠️ **窗口口径限定（全剖面对照后需加注）**：本表的"峰值略降"（926.95→914.37 kN）**只在首 1200 s 窗口成立**；**全剖面（36000 步 / 53km）上同一对比的峰值符号反转**（改动前 1350 kN → 改动后 1643.49 kN）。引用本表**必须带窗口口径**，详见本文「四、改动前对照」②。

#### 三、D 的 on/off 隔离对照（确定性驱动策略，12000 步窗口）

- **隔离方式**：harness 级把每列子环境的 `SafetyLayer.ab_new_source_veto` 猴补为恒 `False`（**不新增生产开关**，遵循"禁止布尔开关"约定）；`D_on` = 默认行为。
- **为何 12000 步**：1200 步窗口内该策略 `ab_steps=0`（本段不走 AB 新增源通道）⇒ 无法区分 on/off。

| 配置 | reward | 断面力峰值 | 破线 | AB 源·步 | band 率 | 末速 | `ab_safety_vetoed`（**env 侧真丢弃**） | `veto_fired_calls`（**含控制器调用点**） |
| :--- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| **D_on**（安全层 AB 权限**开**，默认） | +36340 | 914.37 kN | 0 | 2565 | 99.983% | 64.26 km/h | **35** | 1216 |
| **D_off**（猴补为永不否决） | +35638 | 914.37 kN | 0 | 2555 | 99.983% | 64.26 km/h | **0** | 0 |

- **两个计数的口径必须分清（首版留痕曾把它们混为一谈，此处更正）**：
  - `veto_fired_calls`（harness 猴补包一层计数）= **所有返回 True 的调用**，含 `multi_loco_controller.py:305` 那个**2026-09-30 既有**的控制器侧调用点（每原始步 1 次，DI=10 下单窗口 12000 次）。故 1216 主要来自控制器侧，**不是 D 的贡献**。
  - `ab_safety_vetoed`（生产 `info` 键，本规格新增）= env 侧**确实丢弃了非空新源**的步数 = **35/12000 ≈ 0.3%**。`if ab_sources:` 前置 ⇒ veto 返回 True 但本就无新源可丢的调用**不计入**。
- **机制结论（诚实版）**：env 侧否决**确实在触发**（35 次 / off 组 0 次 ⇒ 隔离有效），但**断面力峰值逐位相同**（914.3721888138994 kN），band/末速亦同，仅 AB 源步数（2565 vs 2555）与 reward（差 +702）有微小差异。
  ⇒ 在本策略 / 本窗口上，D 的边际贡献**不在峰值指标**上：A 的充风门（6657 次拒绝）已挡掉绝大多数新增源，D 的 35 次为**重叠拦截**。
  ⇒ **D 的定位 = 安全保证**（把 AB 通道纳入与 ED 对称的 ≤1000 kN 兜底，使 ADR-018「硬兜底」名实相符），**不是性能杠杆**。
- ⚠️ **移除的"梯度投影臂"（可证不可达，纯重构、零行为变化）**：首版曾按 ED 同款投影式实现 `scale<0.5 ⇒ 新源 SERVICE→MIN 降一档`。它**永远不可能执行**：
  1. `ab_new_source_veto()` 的反应式判据是 `p0 ≥ coupler_veto_ratio(0.6) · limit`（`safety_layer.py:69/156`）；
  2. `p0 = max(obs_state['coupler_forces'])`，而 `_state_snapshot()`（`train_env.py:335`）喂的正是 `coupler_interface_forces_per_vehicle()`——**与本块算 `scale` 用的是同一个数组**，且该函数返回 `np.abs(...)` 后取相邻两钩最大幅值，**恒 ≥ 0**（`train.py:374-376`）⇒ `p0 ≡ ratio·limit`；
  3. `scale<0.5 ⟺ ratio>0.9`，而 `ratio>0.9 ⇒ p0 ≥ 0.9·limit ⇒ veto=True`；分支序为 `if veto: … elif scale<0.5: …` ⇒ **降级臂恒被抢先**。
  4. `coupler_veto_ratio` 全仓无覆盖（恒 0.6）⇒ 结论稳定。已删除该臂、其计数键 `ab_safety_downgraded`、以及**靠猴补关掉 veto 才能通过**的那条误导性单测；新增源码级断言禁止其回流（`tests/test_ab_refill_and_safety_authority.py::test_step_decomposed_has_no_revoke_path`）。
  - **含义**：只要 veto 阈值停在 0.6，"AB 渐变投影"就**无法表达**（禁新增是任何梯度降级的超集）。真·梯度 AB 权限必须连同 veto 阈值一起重定 → 归入**完整预测式 safety filter**（长久计划）。
- **有效域**：本步环境收到的**全部新申请 AB 源**（含规则层——env 无法区分来源，故比 ADR-018「仅 RL 新增源」闸门更宽，属有意的兜底强化）；**不含**已建立源（不撤销）。
- ⚠️ **与规格 Scenario 的显式偏差（诚实声明）**：规格 `implement-literature-informed-fixes` 的 Scenario 写「高力下禁新增 → 该新增源被丢弃（**保留规则基线源**）」，而本实现**同时**丢弃规则层本步的新增源。原因：`ab_sources` 在 env 内由控制器输出的 `final` 组装，**env 分不清 RL/规则来源**；要只拦 RL 源，须把控制器的 `baseline` 透传进 `train_env.step`（API 改动）。
  - **为何保留当前（更宽）行为**：① 立论侧「车钩力 ≤1000 kN 是**硬**底线」要求 AB 通道整体受安全层约束（ADR-018「名实相符」），只拦 RL 源在 RL 不用该通道时仍是 **no-op**（LRN-20260930-010）；② **实测无害**：D on/off 峰值**逐位相同**、band/viol 相同，规则基线单独跑仍为 **812.87 kN / viol 0 / band 98.01%**。
  - **适用条件 / 何时须改窄**：若未来出现「安全层在关键时刻挡掉规则层制动 → 超速 → ETCS 紧急」的链条，必须改为**来源感知**（把 `baseline` 透传），即并入**完整预测式 safety filter**（长久计划）；届时须按 ADR-020 重做 on/off。
- ⚠️ **已知边界（诚实声明）**：控制器侧既有的 `_coupler_throttle_scale` 投影在 `peak ≥ 1.0×限值` 时把 `final[:,1]` 缩到 0 ⇒ 该步 `ab_sources` 为空 ⇒ 走 `ab_command=RELEASE`，**可能释放已建立源**。这是 **D 之前就存在**的路径（2026-09-09），本规格**未改动**；D 新增的拦截路径刻意用 `ab_command=None` 避免该副作用。此"不一致"正是 Pfrommer 2022 警示的 filter/策略解耦形态，列为**完整预测式 safety filter**（长久计划）须处理的问题。

#### 四、C 的 reward 解析核对（生产函数 `_calculate_reward_decomposed`）

| `peak_norm` | 总 reward | Δ(vs peak_norm=1.0) | 超限项实测 | 解析期望 `-6·min(pn−1, 2)` |
| ---: | ---: | ---: | ---: | ---: |
| 0.5 | −256.6 | +0.10 | 0 | 0 |
| 1.0 | −256.7 | 0.00 | 0 | 0 |
| 1.5 | −259.8 | −3.10 | **−3.0** | −3.0 |
| 3.0 | −269.1 | −12.40 | **−12.0**（触顶） | −12.0 |
| 5.0 | −269.5 | −12.80 | **−12.0**（限幅） | −12.0 |

- 说明：Δ 与超限项之差 = 原有车钩力整形项 `−0.2·peak_norm`（如 pn=1.5 时 −0.1）。
- **机制结论**：`peak_norm ≤ 1` 恒为 0；跨 1.0 后**线性**、在 `pn ≥ 3` **触顶 −12.0**；量级与速度带项（+6/列）同档，**无 `−80·ov²` 式大系数**。
- **有效域**：仅"**超限**"段落进目标（`ov = peak_norm−1`），**不作均值最小化**（维持 ADR-014 边界）；口径 = 断面力（ADR-018 SSOT）。

#### 五、B 的验证（信用视界对齐 + 端到端 + 评估侧）

- **① 视界换算修正**：`effective_horizon_s` 原为 `steps × decision_interval`（**漏乘 `dt`**）。`decision_interval` 是**原始环境步数**（`train_runner` 内 `for _ in range(cfg.decision_interval)` 调 `env.step`），不是秒 ⇒ 原式把默认 γ/λ 的 16.8 s **误报成 168 s「覆盖」**。已修为 `steps × DI × dt`，并加测试反例（默认 γ/λ 必须判为「不足」）。
- **② 启动打印（实测）**：
  `[信用视界] gamma=0.999 gae_lambda=0.99 | 1/(1-γλ)=91.0 决策步 | 决策间隔 10 原始步 × dt=0.1s = 1.00s/决策步 → 有效视界 91.0s | 对照物理滞后≈90s → 覆盖`
- **③ 端到端冒烟**（`run_training.py` 主 YAML，3 ep / max_steps 60 / batch 16）：per-agent `update()` 正常（loss 0.103 / vloss 0.259 / KL 0.013 / vstd 109.73），权重落盘；`metadata.json` 实测 `critic=per_agent`、`reward_schema=v2-bounded-overlimit-section-force`、`algo_params.gamma=0.999 / gae_lambda=0.99`。
- **④ 评估侧**：`evaluate_decompose.probe_critic_mode()` 读 ckpt 内嵌 `metadata.critic`（旧 ckpt 无该字段 → 按 value 末层 2-D 权重最小首维推断：1=标量头 / >1=per-agent 头）。实测：新 ckpt `metadata.critic='per_agent'`（out_dims 含 6）；旧 ckpt `metadata.critic=None`（out_dims 含 1）⇒ 判定正确。
- ⚠️ **边界**：B **改变训练算法** ⇒ `critic/advantage/GAE` 语义变化，**旧权重在新目标下失去可比性**；同上 C 改 reward 口径 ⇒ **旧 ckpt 全部失效，最终性能结论必须重训**（长久计划，见 `PROJECT_PIPELINE.md`）。

#### 六、复现命令（harness `tmp_task7_verify.py`，用后即删）

```sh
# 环境
source ~/miniconda3/etc/profile.d/conda.sh && conda activate traffic_rl
cd /mnt/d/Code/MultiAgent/traffic_rl_project

# A: on/off 各 12000 步（同一 ckpt / 同 seed / 同剖面，仅 ab_min_refill_s 变）
python tmp_task7_verify.py --scenes a --tag task7_a
# D: on/off 各 12000 步（--scenes d_on / d_off 可单独跑）
python tmp_task7_verify.py --scenes d --tag task7_dc
# C: 奖励分项解析核对（无 rollout）
python tmp_task7_verify.py --scenes c --tag task7_c
```

- 权重：`outputs/checkpoints/formation/final_seed0/mappo_fleet_last_ep1623_dec_ad2_cp_seed0_seed0.pt`
- 剖面：`shuozhou_real_53km`；决策间隔 `DI=10`；确定性 `select_actions(deterministic=True)`
- 结果 JSON：`outputs/results/diagnostics/verify_task7_metrics_task7_a.json` / `..._task7_c.json`

### 诊断-2026-10-01-P0 三行基线（现行断面力口径 + 修好的 viol 计数）与 AB 通道裁定

- **日期**：2026-10-01
- **动机**：ADR-021 决策 1 的 **P0**（零架构改动、不涉重训）：① 在现行**断面力口径（ADR-018 SSOT）+ 修好的 viol 计数**下重算 53km 的 **M0（规则基线）/ M1（`last` 生产权重）**；② 做 **`--mask_lever ab`**（收走 RL 的 AB 新增源通道）对照 ⇒ 判定 **AB 通道对最终性能是净正还是净负**。
- **为何必须重算**：同一权重 `ep1623` 在**旧口径**（`physics_version=29569dcaf78a`）下记为 **863.5 kN / band 99.7% / 末速 72.0 km/h**（ADR-020 更正条），在**现行口径**（`physics_version=1eab36352fd3`）下为 **1643.5 kN / 77 破线步**。差异来源于**口径**（每车净力 → 断面力）与**违规计数修复**，不是权重变化 ⇒ ADR-020 更正条里那些数字**不可与本节混用**。

#### 一、三行基线（全剖面 53km · 36000 步 · `DI=10` · 确定性 · `seed=0` · 单 seed）

| 行 | 配置 | reward | 断面力峰值 | 破线（车厢·步） | AB 源·步 | band 率 | 末速 | ATP 事件 |
| :--- | :--- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| **M0** | 规则基线（RL 调制恒 0） | −288742 | **812.87 kN** | **0** | 3212 | 98.01% | 46.27 km/h | 145750 |
| **M1** | RL 全通道（`last_ep1623`） | −345340 | **1643.49 kN** | **77** | 7656 | 91.58% | 73.67 km/h | 521889 |
| **M1-maskab** | RL **仅 ED**（`--mask_lever ab`） | **−160384** | **1037.50 kN** | **44** | **1105** | **95.85%** | 56.89 km/h | 74906 |

- 三行**同代码**（改动后：A 充风门 on / D 禁新增源 on / C 新 reward / B 新算法均已在主树）、**同 ckpt**、**同剖面**、**同 seed**，唯一变量 = `--mask_lever ab` 或 RL 是否参与。
- `metadata`：三行均 `git_commit=d6ba3540…`、`physics_version=1eab36352fd3`；M1 两行 `reward_schema=v2-bounded-overlimit-section-force`、`critic=centralized_scalar`（**旧 ckpt** ⇒ `probe_critic_mode()` 由权重形状判为标量头，正确）。

#### 二、AB 通道裁定：**净负**（ADR-021 决策 1 ② 的判据）

- **口径**：M1 与 M1-maskab 逐项对比（M1-maskab 的 `ab_mod` 恒 0 ⇒ 其 `ab_steps=1105` 即**纯规则层**循环制动；M1 的 `7656` 含 RL 新增的 ≈**6551** 步）。
- **结果**：收走 RL 的 AB 新增源通道后，**五项指标全部改善**：峰值 **1643.49 → 1037.50 kN（−605.99 kN，−36.9%）**；破线 **77 → 44（−33）**；band 率 **91.58% → 95.85%（+4.27 pt）**；AB 用量 **−85.6%**；reward **−345340 → −160384**。代价 = 末速 73.67 → 56.89 km/h（更保守、更接近规则层 46.27）。
- **裁定**：**在本 ckpt（旧目标 / 旧算法训练）上，RL 的 AB 通道是净负**。RL 新增的那 ≈6551 步 AB 恰是峰值从 1038 抬到 1643 kN 的部分。
- **⚠️ 不得过度外推**（三条边界）：
  1. 这是**旧权重**（在"多用 AB 得速度带奖励"的旧目标 + 标量 advantage 广播的旧算法下训练）。净负**不能证明**"AB 通道本身无价值"，只能证明**旧目标让策略学出了有害的 AB 使用**（与「根因归因」②③ 一致）。
  2. M1-maskab **仍然破线**（1037.50 kN / 44 步）⇒ **仅靠收走 AB 通道不足以守住 ≤1000 kN**；必须叠加 **C（车钩力进目标）+ B（信用分配修复）后重训**（长久计划）。
  3. 单 seed、单权重、确定性 ⇒ 方向性判据，**不作最终性能结论**；最终结论须按 ADR-017 跑 1400 ep × 5 seed 重训后出。
- **与既有机制的关系**：M1-maskab 同时说明 `--mask_lever ab` 在**当前代码**下确为有效消融开关（AB 步 7656→1105 证明通道真被切断），可继续用于后续消融表。

#### 三、复现命令

```sh
source ~/miniconda3/etc/profile.d/conda.sh && conda activate traffic_rl
cd /mnt/d/Code/MultiAgent/traffic_rl_project

CKPT=outputs/checkpoints/formation/final_seed0/mappo_fleet_last_ep1623_dec_ad2_cp_seed0_seed0.pt

# M0 规则基线
python src/evaluation/evaluate_decompose.py --mode decompose_m0 \
  --grade shuozhou_real_53km --max_steps 36000 --n_seed 1 --eval_seed 0 \
  --decision_interval 10 --out_suffix _p0_m0_rule_53km
# M1 全通道
python src/evaluation/evaluate_decompose.py --mode decompose_m1 --checkpoint $CKPT \
  --grade shuozhou_real_53km --max_steps 36000 --n_seed 1 --eval_seed 0 \
  --decision_interval 10 --out_suffix _p0_m1_last_53km
# M1 仅 ED（AB 通道收走）
python src/evaluation/evaluate_decompose.py --mode decompose_m1 --checkpoint $CKPT --mask_lever ab \
  --grade shuozhou_real_53km --max_steps 36000 --n_seed 1 --eval_seed 0 \
  --decision_interval 10 --out_suffix _p0_m1_maskab_53km
```

- 结果 JSON：`outputs/results/decompose/eval_decompose_decompose_{m0,m1}_ms36000_p0_*.json`

#### 四、改动前对照（A 在**全剖面**上的净效应 —— 混合结论）

- **方法**：在**源码冻结副本**（`git worktree`，冻结 SHA `d6ba3540`，即改动前工作树 = **A/B/C/D 全部未落地**）中，用 `tmp_p0_freeze_boot.py`（**显式把副本根插入 `sys.path[0]` 并断言 `src.metadata.__file__` 落在副本内**——只 `cd` 不算冻结，见 LRN-20261001-006）跑同三条命令，后缀 `_pre_*`。harness 与冻结副本均**用后即删**（`git worktree remove --force` + `git worktree prune` 已执行）；复现方法见 LRN-20261001-006 的描述（插 `sys.path[0]` + 断言）。
- 对照 = `_pre_*`（改动前）vs `_p0_*`（改动后）。M1 行上 **B/C 不改 rollout 行为**（B 只改训练侧、C 只改 reward 值），D 在 12000 步上已证近 no-op ⇒ **差值主要由 A 解释**（残余 D 未分离，已在下方边界里声明）。

| 行 | 代码版本 | reward | 断面力峰值 | 破线（车厢·步） | AB 源·步 | band 率 | 末速 |
| :--- | :--- | ---: | ---: | ---: | ---: | ---: | ---: |
| M0 规则（RL 全程 0） | **改动前**（`_pre_m0_rule_53km`） | −288742 | 812.87 kN | 0 | **3212** | 98.01% | 46.27 km/h |
| M0 规则（RL 全程 0） | 改动后（`_p0_m0_rule_53km`） | −288742 | 812.87 kN | 0 | **3212** | 98.01% | 46.27 km/h |
| M1 **仅 ED**（`--mask_lever ab`） | **改动前**（`_pre_m1_maskab_53km`） | +145465 | **1023 kN** | **21** | **1441** | **97.07%** | 46.2 km/h |
| M1 **仅 ED**（`--mask_lever ab`） | 改动后（`_p0_m1_maskab_53km`） | −160384 | **1037.50 kN** | **44** | **1105** | **95.85%** | 56.89 km/h |
| M1 RL 全通道 | **改动前**（`_pre_m1_last_53km`） | −46801 | **1350 kN** | **905** | **16270** | **99.62%** | 60.7 km/h |
| M1 RL 全通道 | 改动后（`_p0_m1_last_53km`） | −345340 | **1643.49 kN** | **77** | **7656** | **91.58%** | 73.67 km/h |

- **① A 的有效域（修正后的准确表述）**：`_ab_gate` 装在**控制器**里，**对"新增 AB 源"一视同仁**（不分规则层 / RL 层）。因此：
  - **在"RL 完全不出手"的纯规则轨迹上（M0 行）⇒ 逐位相同 = A 不触发**。这不是"门只管 RL"，而是**规则层自己的循环制动排程本就满足 222 s 充风窗**（与 `VALIDATION_BASELINE.md:201` 张二田 S6 的实测最短充风一致）；
  - **一旦 RL 从 ED 通道扰动轨迹（M1-maskab：AB 步 1441→1105，−23.3%），A 就会连带拦到"被扰动后的规则层 AB 排程"**；全通道（M1）上更是 −52.9%。
  ⇒ 准确表述：**A 的有效域 = "在 222 s 充风窗内请求新增 AB 源"这一动作，与来源无关；纯规则轨迹恰好不触发，轨迹被 RL 扰动后必然触发**。
  ⇒ 论文叙事应为"A 把**充风纪律**变成硬约束，使 RL 无法为了短期速度收益破坏它"，**不是**"A 只管 RL 通道 / 规则层不受影响"。
- **② A 在全剖面上的净效应是"混合"，三个配置一致指向同一方向**：

  | 配置（改动前 → 改动后） | AB 源·步 | 断面力峰值 | 破线（车厢·步） | band 率 |
  | :--- | :--- | :--- | :--- | :--- |
  | M1 全通道 | 16270 → 7656（**−52.9%**） | 1350 → **1643.49 kN（+21.7%）** | 905 → **77（−91.5%）** | 99.62% → **91.58%（−8.04 pt）** |
  | M1 仅 ED | 1441 → 1105（**−23.3%**） | 1023 → **1037.50 kN（+1.4%）** | 21 → **44（+23）** | 97.07% → **95.85%（−1.22 pt）** |
  | M0 纯规则 | 3212 → 3212（0） | 812.87 → 812.87（0） | 0 → 0 | 98.01% → 98.01% |

  - **一致的符号**：A **总是**压低 AB 用量；**在 RL 参与的两个配置里都使峰值升高、band 变差**（M1 上 +294 kN / −8.04 pt；仅 ED 上 +14.5 kN / −1.22 pt）。
  - **不一致的符号**：破线步数在 M1 上大降（905→77），在仅 ED 上反升（21→44）。
  - **物理解读（诚实版）**：旧权重是"靠 AB 保速度带"训出来的。**A 掐掉 RL 的 AB 新增源后，策略"想用 AB 却用不了"** ⇒ 下坡控速变差（band 掉、末速更高），并在个别时刻出现更高峰值。它换来的好处是**在 M1 上把破线步数从 905 压到 77**（AB 源"时空分布"被约束住，与 ADR-021 断点 5 的否证一致）。
  - ⚠️ **结论：A 不能单独用**——必须与 **C（车钩力进目标）+ B（信用分配修复）** 一起重训；否则只是把"AB 用得多、破线步多"换成"AB 用得少、峰值更高、速度带更差"。已写入 ADR-021「执行闭环」⑤ 与 `PROJECT_PIPELINE.md` 长久计划。
  - ⚠️ **对 12000 步 A on/off 表的限定**：那张表（本文「二、」）结论"峰值略降 926.95→914.37 kN"只在**首 1200 s 窗口**成立；**全剖面（36000 步）上峰值的符号反了**。⇒ 引用时**必须带窗口口径**，不得把 12000 步的"峰值略降"推广到全剖面。
- ⚠️ **未分离的残余**：本对照是"A(+D)"而非"A 单独"（冻结副本不含 D 的 env 侧否决；D 在 12000 步 + M0 行上均表现为 no-op，但全剖面贡献未单独隔离）。
- **隔离性证明（代码级 diff，决定性）**：对**整条评估路径**做 `git diff d6ba3540 -- src/{environments,controllers,train_dynamics,safety_layer.py,evaluation,physics_governance.py}`，**唯一差异**是四改造的落地文件：

  | 文件 | 差异 | 归属 |
  | :--- | ---: | :--- |
  | `src/controllers/multi_loco_controller.py` | +75 | **A** |
  | `src/environments/train_env.py` | +27 | **D** |
  | `src/environments/train_fleet_env.py` | +49 | **C**（+ D 的 fleet 计数聚合） |
  | `src/evaluation/evaluate_decompose.py` | +31 | **B** 的 `probe_critic_mode` + 报告字段（**不改 rollout 动力学**） |

  而 **`src/train_dynamics/*`、`src/safety_layer.py`、`src/physics_governance.py` 差异为 0**；两版 `metadata.physics_version` 亦逐字符相同（`1eab36352fd3`）⇒ **物理完全可比**，上表差异只能来自 A/B/C/D。（`d6ba3540…` 是 `git stash create` 产生的 dangling 提交，即"改四改造之前的会话工作树快照"；冻结副本已 `git worktree remove`，如需复现可按 ADR-021「执行闭环」① 的四处落点反向还原。）
- ⚠️ **`_p0_*` vs `_pre_*` 命名约定（源码冻结副本事故的教训）**：这两组曾**同时**落在冻结副本目录里，一组是**现行口径**（`_p0_*`）、一组是**改动前基线**（`_pre_*`）。判定归属**不能看目录**，只能看该次运行的 `[boot] src.metadata.__file__=` 断言行与 JSON 内 `reward_schema`（新代码才有）；详见 `LEARNINGS.md` LRN-20261001-006。

### 验证-2026-10-01-主训练 YAML 按 ADR-017 对齐（配置解析短训验证）

- **动机**：四改造落地后发现**主训练配置与 ADR-017 硬要求不一致** —— `episodes: 120`（不足达标量）、缺 `n_env` / `warm_start` / `long_eval_*`、注释仍留已 SUPERSEDED 的"53km 全程由多段 1200 步拼接覆盖"、`env_cfg.max_steps: 36000` 注释误标"53km 全程训练"。若不改，主训练线仍落在不足量上，且注释继续误导。
- **改动**（`configs/experiments/formation_ed_ab_3train_1plus1.yaml`）：`episodes: 120 → 1400`（ADR-017 §4）；新增 `n_env: 4` / `parallel_traj_len: 0`（§1 + 诊断-2026-09-10）、`warm_start: true` / `bc_episodes: 3` / `bc_epochs: 30`（诊断-2026-09-15）、`long_eval_interval: 50` / `long_eval_steps: 36000`（§2 + 诊断-2026-09-22）；`max_steps` 与 `curriculum` 注释改为 ADR-017 §1/§2 口径。
- **验证（`--episodes 2` 覆盖短训，exit 0，280.7 s）**：

| 检查项 | 证据（日志 / `metadata.json`） | 结论 |
| :--- | :--- | :--- |
| curriculum 解析 | `curriculum 边界: [(0, 500), (10, 1000), (20, 1200)]` | ✅ |
| 信用视界对齐 | `[信用视界] gamma=0.999 gae_lambda=0.99 \| 1/(1-γλ)=91.0 决策步 \| ×DI=10 原始步 ×dt=0.1s → 有效视界 91.0s \| 对照物理滞后≈90s → 覆盖` | ✅ |
| BC 热启动分支 | `Fleet BC warm start: 采集 27000 条 (obs, [0,0])，预训练 30 epochs` → `BC loss=2.674` | ✅ |
| `--episodes` 覆盖生效 | `metadata.hyperparameters.episodes = 2`（YAML 为 1400） | ✅ 覆盖链可用 ⇒ YAML 1400 可被正确解析 |
| 并行多环境 | `metadata.hyperparameters.n_env = 4`、`parallel_traj_len = 0` | ✅ |
| 热启动 / 长程评估 | `warm_start=true`、`bc_epochs=30`、`long_eval_interval=50`、`long_eval_steps=36000` | ✅ |
| 四改造参数 | `critic=per_agent`、`reward_schema=v2-bounded-overlimit-section-force`、`ab_min_refill_s=222.0` | ✅ |
| 运行稳定性 | 2 集 `viol 0`；pkCpl 561 → 568 kN；`耗时 280.7s (4.7min)` | ✅ |

- **复现命令**（⚠️ 必须**同时**重定向三个输出目录，见下）：
```
python run_training.py --experiment configs/experiments/formation_ed_ab_3train_1plus1.yaml \
  --seed 0 --episodes 2 --override log_interval=1 \
  --checkpoint_dir outputs/_cfgcheck/seed0 \
  --results_dir outputs/_cfgcheck/seed0/results \
  --override dirs.figures_dir=outputs/_cfgcheck/seed0/figures
```
- ⚠️ **验证纪律教训（LRN-20261001-009）**：首跑**漏了 `--override dirs.figures_dir=…`** ⇒ `figures_dir` 回落到 YAML 默认 `outputs/checkpoints/formation/seed0/figures`，**覆写了 09-25 那次 100-ep 历史训练的学习曲线 PNG**。原始 `train_history_dec_ad2_cp_seed0.csv` 未受影响（results 已重定向），已用**同一** `save_training_artifacts` 绘图路径从该 CSV 重建 PNG（无信息丢失）；`tmp_figfix.py` / `/tmp/_figfix` / `outputs/_cfgcheck/` 已全部删除。**此后所有冒烟/验证跑必须同时重定向 `checkpoint_dir` + `results_dir` + `dirs.figures_dir` 三者。**
- **结论**：主训练 YAML 已达 ADR-017 口径且训练入口可正确解析；本节为"配置层"验证，**不等于**性能验证 —— 性能结论仍须按 ADR-017 跑 `1400 ep × 5 seed` 重训 + 完整剖面评估后才成立（ADR-021「执行闭环」⑥ 强制边界）。

### 修复-2026-10-01-long_eval 违规计数口径（O(n²) 放大）+ 端到端预检

- **发现（为长跑做前置审计时）**：`TrainRunner._long_eval`（2026-09-22 新增的周期性完整剖面选优器）写成
  `viol += int(info['coupler_limit_violations'])`，而 env 的该计数器是 **episode 级单调累计**
  （`train_fleet_env.py:320` reset 清零 / `:519` 逐步累加，step 间不清零）⇒ 等价于**把累计值逐步相加**，
  36000 步可达 **1e8** 量级。同一 bug 在 `evaluate_decompose.py:160-163` **已于 2026-09-25 修过**，`_long_eval` 漏改。
- **危害定级（诚实，不夸大）**：`best_eval` 仅在 `ok=True` 时写入，而 `ok` 要求 `int(viol)==0`；
  计数器从 0 单调不减 ⇒"逐步累加和==0"⇔"全程无违规"⇔"真实总数==0"，**判据语义等价**，
  故已落盘的 `long_eval_best.json` / checkpoint 内嵌 `long_eval_best` 的 `viol` 恒为 0（正确）。
  **真实危害 = 日志误导 + 脆弱性**：未达标评估会打印 `viol 1234567` 类天文数字（会被误读为"机制失效/仿真坏了"），
  且一旦判据放宽，错误数值将直接进元数据。
- **修复**：改为**每步增量累加**（与 `evaluate_decompose.py` 对齐）

  | 项 | 值 |
  | :--- | :--- |
  | 位置 | `src/trainer/train_runner.py::_long_eval` |
  | 改法 | `cur_viol = float(info.get('coupler_limit_violations', 0)); viol += cur_viol - prev_viol; prev_viol = cur_viol` |
  | 单测 | 新增 `tests/test_long_eval_metrics.py`（3 项）：累计序列 `0,0,1,2,3,4` ⇒ 断言 **4**（旧写法 **10**）；零违规仍 `达标=True` 且 best 落盘；源码级断言禁止回流 |

- **端到端预检**（真 `TrainFleetEnv`，`--episodes 2 --override long_eval_interval=1 --override long_eval_steps=400`，
  exit 0，357.3 s，三输出目录均已重定向）：
  - `[long_eval] ep1: reward +3249 | peak 540kN | viol 0 | band 100.0% | 末速 66.8km/h | 达标=True`（ep2 同）
  - `best` 文件 + `results/long_eval_best.json`（`{reward 3248.6, ep 1, peak_kN 540.1, viol 0, final_kmh 66.8}`）正常落盘
  - ⇒ 结论：**周期性选优（每 50 ep）在 1400 ep 长跑中不会静默失选优**；顺带确认单次 36000 步评估机时 ≈ **57 min**（400 步 ≈38 s 外推），与既有 `~55 min` 记录一致。
- **同源残留（已定位、刻意未改）**：另有 3 个 live 脚本为同一写法（`compare_m1_baselines.py:53`、
  `evaluate_fleet_hier_80.py:46`、`compare_m1_init80.py:46`），均属**已废止 hierarchical 方案**（ADR-013）且全仓零引用 ⇒
  不静默改历史复现资产；**若旧表格引用过其 `viol`，必须按 O(n²) 膨胀处理**。详见 `LEARNINGS.md` LRN-20261001-010。
- **复现命令**：
```
python run_training.py --experiment configs/experiments/formation_ed_ab_3train_1plus1.yaml \
  --seed 0 --episodes 2 --override long_eval_interval=1 --override long_eval_steps=400 --override log_interval=1 \
  --checkpoint_dir outputs/_lecheck/ckpt --results_dir outputs/_lecheck/results \
  --override dirs.figures_dir=outputs/_lecheck/figures
```

### 修复-2026-10-01b-`--mode all` 主对比链路三处缺陷（MPC 行缺失 / MPC 状态残留 / solve_statuses 崩溃）

> 承接上节：为 1400 ep 长跑做前置审计时，顺带核对了"重训后要产出的主对比三行"这条路。发现 **`--mode all` 这条被 `REPRODUCIBILITY.md` §十 当作"主对比三行"的命令，实际从未产出过 MPC 行**，且其 MPC 路径存在两个更深的问题。三者互为因果、必须一起修。

#### 一、缺陷清单与证据

| # | 缺陷 | 证据 | 教训编号 |
| :--- | :--- | :--- | :--- |
| ② | `--mode all` **静默只出 2 行**（缺 MPC） | `outputs/results/decompose/eval_decompose_all_ms300_smoke_x1.json` 的 `results` 只有 `decompose_M0_rule` / `decompose_M1_rl` 两个键（`eval_args.enable_mpc=false`） | LRN-20261001-011 |
| ③ | MPC 控制器**逐回合状态未清零** | `_mpc_controller` 仅在 `_mount_mpc` 时 reset；`eval_method` 复用同一条 env 跑 `n_seed` 回合 ⇒ 第 2/3 回合继承 `_gap0_init`(初值 1e9)/`_gap_ref` | LRN-20261001-012 |
| ④ | fair MPC 行**收尾即崩**（`AttributeError: 'FairMPCController' object has no attribute 'solve_statuses'`） | 上节冒烟 `[long_eval]` 之后的 `--mode all` 实跑 traceback（`rollout()` 收尾组装处） | LRN-20261001-013 |

- **④ 的危害最大**：异常发生在**指标组装**、而**结果 JSON 尚未落盘**（落盘在 `main()` 末尾）⇒ 已跑完的 M0/M1 两行（各 36000 步、数十分钟）**一起白跑**；且用 `| tail` 或后台运行时 **exit code 被吞**（本次冒烟报 exit 0），极易误判为成功。
- **为什么三者能同时存在**：②把整条 MPC 路径**静默挡在门外** ⇒ ③④ 的代码**从未被执行、也无测试覆盖**（`grep long_eval/MPC tests/` 无命中）；已有的 MPC 冒烟用的是 `--mpc_type nmpc`（`eval_decompose_mpc_ms60_smoke_nmpc.json`），而 NMPC 恰好**有** `solve_statuses`，绕开了 ④。

#### 二、修复

| # | 文件 | 改动 |
| :--- | :--- | :--- |
| ② | `src/evaluation/evaluate_decompose.py` | 解析参数后**立即**归一 `if args.mode in ('all','mpc'): args.enable_mpc = True`（置于 `build_metadata` **之前**，避免 metadata 记 `enable_mpc=false` 而实跑挂了 MPC 的自相矛盾）；删掉 MPC 块内的条件式兜底 |
| ③ | 同上 | `rollout()` 内、`env.reset()` 之后、`st0` 快照之前加 `_mpc.reset()` ⇒ 每回合清零（`n_seed=1` 与"仅挂载时 reset"等价 ⇒ **旧单 seed MPC 数值不变**） |
| ④ | `src/controllers/fair_mpc_controller.py` | 补 `solve_statuses`（`__init__` + `reset()` 清空 + 每次 `minimize` 后 append），口径与 NMPC 同构——均取**求解器自身收敛标志**：`'optimal' if res.success else f'fail:{res.message}'`；失败时仍沿用 `res.x`（既有行为不变） |
| ④ | `src/evaluation/evaluate_decompose.py` | 收尾改为 `sts = getattr(_mpc,'solve_statuses',None)`，无状态源时**不产出** `mpc_solve_fail` 而非抛异常——附加诊断缺失不得让主结果一起丢 |

#### 三、验证（实跑冒烟，fair + `n_seed 2`，真 env）

命令：
```
python src/evaluation/evaluate_decompose.py --mode all --max_steps 120 --n_seed 2 \
  --checkpoint outputs/checkpoints/formation/final_seed0_v2/mappo_fleet_last_ep1063_dec_ad2_cp_seed0_seed0.pt \
  --decision_interval 10 --out_suffix _mpc_ok_check
```
输出（`outputs/results/decompose/eval_decompose_all_ms120_mpc_ok_check.json`）：
```
decompose-M0 规则基线(RL调制恒0): reward +829 | peakCoupler 505kN | viol 0 | ATP事件 288 | AB步 0   | meanED 0.850 | band率 100.00% | 末速 76.4km/h
decompose-M1 RL(...ep1063..., interval=10): reward +825 | peakCoupler 428kN | viol 0 | ATP事件 288 | AB步 20 | meanED 0.617 | band率 100.00% | 末速 77.0km/h
MPC(Fair) @ shuozhou_real_53km: reward +831 | peakCoupler 501kN | viol 0 | ATP事件 288 | AB步 0 | meanED 1.000 | band率 100.00% | 末速 75.7km/h | MPC求解 1025ms均值/3226ms峰值 | fail 0
------------------------------------------------------------------------------
Δ(D-RL - D-Rule): Δreward -4 | ΔpeakCoupler -77kN | ΔATP事件 +0
Δ(D-RL - MPC):    Δreward -7 | ΔpeakCoupler -73kN | ΔATP事件 +0
已保存: outputs/results/decompose/eval_decompose_all_ms120_mpc_ok_check.json
```
- ✅ **3 行齐全**（此前恒为 2 行）；✅ 三行 Δ 摘要打印（此前 `len(results)>=3` 不成立、整块静默跳过）；✅ `fail 0` 说明 `res.success` 语义可用（非"恒失败"）；✅ JSON 落盘。
- 单元测试 `python -m pytest tests/test_metric_accounting.py -o addopts= -q` ⇒ **9 passed**（覆盖 ①②③④：行为级 + 源码级防回流）。

#### 四、⚠️ 顺带测出的**算力事实**（写论文排期必须知道）

- **MPC 单次求解 1025 ms 均值 / 3226 ms 峰值**（3 列 1+1、`B×block_len` 预测窗、SLSQP maxiter=90）。
- `mpc_act` 的 `act_interval` 默认 **1**（逐步求解）⇒ 完整 53km（36000 步）的 **MPC 行 ≈ 10.3 h/seed**；文档口径的 `--n_seed 3` ⇒ **≈31 h 仅 MPC 一行**。
- ⇒ 这不是"随手一跑"的命令：**`REPRODUCIBILITY.md` §十 的主对比命令必须补成本提示**（已补）。也解释了为什么 MPC 行长期"只有 smoke、没有全剖面结果"。

***

### 启动-2026-10-01-ADR-021 口径 seed0 1400 ep 重训（含"长跑进程持久化"排障）

**背景**：四改造（A/D/C/B）改变训练目标与算法 ⇒ **旧权重失效**，性能结论只能由重训产生（Task 7.4 边界）。此前主 YAML 未按 ADR-017 达标（`episodes: 120`），已于 Task 9 对齐（`1400` / `n_env 4` / `warm_start` / `long_eval 50@36000`），本条目记录**首次长训真正落地**。

**一、启动命令（启动器 `scripts/launchers/launch_retrain_adr021_seed0.sh` 内容等价）**

```
python run_training.py \
  --experiment configs/experiments/formation_ed_ab_3train_1plus1.yaml \
  --seed 0 \
  --checkpoint_dir outputs/checkpoints/formation/adr021_1400ep_seed0 \
  --results_dir    outputs/checkpoints/formation/adr021_1400ep_seed0/results \
  --override dirs.figures_dir=outputs/checkpoints/formation/adr021_1400ep_seed0/figures
```

- 未传 `--episodes` ⇒ 取 YAML 的 **1400**（总目标集数语义，ADR-019）。
- **三个输出目录全部重定向到全新路径** ⇒ 不覆盖 `outputs/checkpoints/formation/{seed0,final_seed0}/` 等任何历史产物（纪律见 LRN-20261001-009）。

**二、排障过程：`nohup`/`setsid` 在 IDE Shell 工具内**无效

| 尝试 | 命令形态 | 结果 |
| --- | --- | --- |
| 1 | `cd && source && conda activate && setsid nohup python … > log 2>&1 < /dev/null &` | 报 `LAUNCHED`，但无 python 进程、**log 文件未创建** |
| 2 | `nohup setsid bash scripts/launchers/launch_retrain_adr021_seed0.sh > log 2>&1 < /dev/null &` | 同样无进程、无 log |
| 探针 | `nohup setsid sleep 90 > /tmp/surv_probe.txt 2>&1 < /dev/null &` → 下次调用 `pgrep -af "sleep 90"; ls /tmp/surv_probe.txt` | **两边皆空（exit 1）** ⇒ 进程不跨调用存活 |
| ✅ 3 | IDE Shell 工具 `run_in_background: true` + `wsl -e bash -lc "… bash <启动器> > log 2>&1"`（**前台等待**） | 成功：`PID 673`、`ps -o etime,time,pcpu` = `01:24 / 00:01:14 / 89.1%`、输出目录已建 |

⇒ 结论：**回收不是靠信号**（`setsid` 新会话 + `nohup` 免疫 SIGHUP 都挡不住），而是工具在调用返回时**整体回收该调用的进程组/作业**。在工具内部做 shell 脱壳属方向性错误。教训：`LEARNINGS.md` **LRN-20261001-014**。

**三、启动实证（下一步独立调用复查，非"启动打印"）**

- 进程：`pgrep -af run_training.py` ⇒ `python run_training.py --experiment configs/experiments/formation_ed_ab_3train_1plus1.yaml --seed 0 …`（PID 673）。
- 资源：`ps -o etime,time,pcpu,pmem` ⇒ 89.1% CPU / 4.4% MEM；`nvidia-smi` ⇒ GPU 0% / 145 MiB（**BC 热启动为 CPU 密集阶段**，GPU 空闲属正常）。
- 产物：`outputs/checkpoints/formation/adr021_1400ep_seed0/` 与 `results/` 已创建。
- 日志 `outputs/logs/diagnostics/log_retrain_adr021_seed0_20261001.txt` 已打出：
  ```
  实验: formation_ed_ab_3train_1plus1 | algorithm=mappo interaction=mappo_fleet | seed=0 episodes=1400 simcase=official
  checkpoint_dir=outputs/checkpoints/formation/adr021_1400ep_seed0 results_dir=…/results
  MAPPO设备: cuda
  [信用视界] gamma=0.999 gae_lambda=0.99 | 1/(1-γλ)=91.0 决策步 | 决策间隔 10 原始步 × dt=0.1s = 1.00s/决策步 → 有效视界 91.0s | 对照物理滞后≈90s → 覆盖
  ```
  ⇒ 配置链路（1400 ep / official 工况 / per-agent 信用视界对齐）**均按 ADR-021 口径生效**。
- ⚠️ **日志为 `>` 重定向 ⇒ 块缓冲**：分钟级看不到新行属正常，**不能以"日志未更新"判死**；判活须用 `pgrep` + `ps -o etime,pcpu`。

**四、⚠️ 机时与持久化边界（写论文排期必须知道）**

- **【2026-10-01 当日实测更正，原估 ≈3.4 天作废】** 启动时按"每集 ≈140 s"外推得 ≈3.4 天/seed；**实跑后由训练自身进度条测得 500 步课时 271 / 276 / 274 / 278 s/集**（`n_env=4` ⇒ ≈0.137 s/env-step），另有 BC 热启动 ≈11 min ⇒ **低估约 3.4×**。按 curriculum（`500:0,1000:10,1200:20`）折算：ep1–10 ≈275 s、ep11–20 ≈550 s、ep21–1400 ≈660 s ⇒ 1400 集 **≈10.6 天**；叠加 28 次 `long_eval`（≈57 min/次）≈1.1 天 ⇒ **实测口径 ≈11.7 天/seed**（官方推导见 `REPRODUCIBILITY.md` §十）。
  - ⚠️ **为什么原估算错**：`140 s/集` 是从一次"短训总墙钟 ÷ 集数"反推的，而短训的 BC 阶段与课时口径都和 1400 集长跑不同 ⇒ **短训总耗时不能除以集数当每集耗时**。
  - ⚠️ **tqdm 的 ETA 也不能直接用**：它按当前（500 步）速率线性外推并打印 `105~108 h`（≈4.5 天），**不随 curriculum 升到 1000/1200 步调整** ⇒ 同样低估约 2.5×。
  - ⚠️ **排期含义**：`1400 ep × 5 seed` 单机串行 ≈ **58 天**，须先裁决"减课时/减集数"还是"并行多机/多卡"。
- 本轮由 IDE 后台作业承载 ⇒ 进程**随 IDE 会话存活**；**数天级无人值守须改用用户自己的 WSL 终端**重跑启动器（命令见 `REPRODUCIBILITY.md` §十：
  `cd /mnt/d/Code/MultiAgent/traffic_rl_project && nohup setsid bash scripts/launchers/launch_retrain_adr021_seed0.sh > outputs/logs/diagnostics/log_retrain_adr021_seed0_20261001.txt 2>&1 < /dev/null &`）。
- 中断恢复（ADR-019）：`--episodes 1400 --resume latest`（`--episodes` = **总目标集数**，非增量），完整命令见 `REPRODUCIBILITY.md` §十。

**五、落地登记**

`REPRODUCIBILITY.md` §十「重训里程碑」段（启动器 / 两种调用场合 / 输出路径 / 恢复命令 / 机时预期）；`PROJECT_PIPELINE.md` 长久计划 1（状态 🟡 seed0 已启动）；`LEARNINGS.md` LRN-20261001-014。

***

### 检索-2026-10-01-`ab_min_hold_s` 文献结案（负结果：无运行期最小 AB 保持时长出处）

**问题**：改造 A 有两个半边 —— ① 最小充风时间（`ab_min_refill_s`，已定 `222.0 s` 并有出处）；② 已建立 AB 源的**最小保持时间**（`ab_min_hold_s`）。②在落地时被标为 **`待核实`**（默认 `0.0`、不激活）。本条目把该开放问题**查证到结案**（项目铁律：**无出处不得编造数值**）。

**检索范围与结论**（三条，均支持"无出处"）

| # | 来源 | 相关条目（原文要点） | 是否可作为「运行期最小 AB 保持时长」 |
| :-: | :-- | :-- | :-- |
| 1 | **Zhang2024**（本项目主依据，DQN 循环制动）`docs/papers/Zhang2024_DQN_CyclicBraking_Downhill.txt:246-277` | §2.2 Running Constraints **仅三条**：(1) 充风时间式 (9) `t_{b,j+1} − t_{r,j} ≥ T_a`；(2) 速度限式 (10)；(3) 电制力比例式 (11) | ❌ **无**"最短制动保持时长"这一约束（逐条复核，非摘要判断） |
| 2 | **《铁路机车操作规则》**（铁运〔2012〕281 号；技术规章编号 **TG/JW104-2012**；国家铁路局公布文本） | (a) "在长大下坡道前方的**列检作业场**需进行持续一定时间的**保压试验**时，应在列车制动机按全部试验方法试验后，自阀减压 **100 kPa 并保压 3 min**，列车不得发生自然缓解。"<br>(b) "**重载货物列车速度在 30 km/h 以下，不应缓解列车制动。**" | ❌ (a) 是**列检站保压试验**（制动系统气密性/自然缓解检查），**不是运行期操纵时长下限**，场景与语义都不对；<br>❌ (b) 是**速度门限**而非时长 —— 且本项目 `v_min = 11.111 m/s = 40 km/h > 30 km/h` ⇒ 在 53km 主剖面上**恒不触发（空约束）** |
| 3 | **赵紫宁 2022** 表 5-3（`docs/papers/Zhao2022_AirBrakeRefinedModeling_Optimization.md:254`） | 4 个制动段**制动时长** 212 / 946 / 1358 / 918 s | ❌ 属**实车实测观测值**，不是"不少于 X"的下界 ⇒ 不能反推为约束 |

**结论与处理**

- `ab_min_hold_s` **保持 `0.0`（不激活）**，标签由开放的 `待核实` 改为**已结案的负结果**：本轮已检 Zhang2024 全文、行业规章《铁路机车操作规则》、赵紫宁 2022 实测表，**均无"运行期最小 AB 保持时长"的可用出处** ⇒ 按铁律**不编造**、接口保留但不启用。
- **留给后人的线索（不塞进本参数）**：上表 (b)「重载列车 v<30 km/h 不应缓解」是一条**真实、可引用**的运行规章；但它在本项目 53km 场景（`v_min=40 km/h`）恒不触发，若要建模须换到更低 `v_min` 的剖面，并作为**独立机制**（"低速度段禁止缓解"）另行设计 + 独立验证，**不得**复用 `ab_min_hold_s` 的时间语义。
- **A 的旁证（非技术源，仅记备查）**：`ab_min_refill_s=222 s` 的量级另有一处独立旁证 —— 大秦线 2.1 万吨列车"分步循环制动法"报道中提到"第 4 次缓解和第 5 次制动期间，用于充压的时间刚好只有 **210 秒**"（工人日报 2023-08-09，**新闻报道，非技术源，不入引用表**），与张二田 S6 实测最短充风 222 s 同量级。

**落地**：`REFERENCE_INDEX.md` 落地映射新增本行（含三条来源与否决理由）；`configs/experiments/formation_ed_ab_3train_1plus1.yaml` 与 `src/controllers/multi_loco_controller.py` 的 `待核实` 注释同步为结案口径；ADR-021 遗留② 状态更新。

***

### 修复-2026-10-01c-评估链路第五处缺陷：`--decision_interval` 默认 1 与训练的 10 **静默失配**

**背景**：本轮在 seed0 长训运行期间做"主表生成器"的第三轮审计（前两轮见「修复-2026-10-01」/「修复-2026-10-01b」）。**缺陷同源**：被 CLI 默认值静默改变的文档语义。

**一、缺陷**

| 项 | 值 | 证据 |
| :-- | :-- | :-- |
| `evaluate_decompose.py` 的 `--decision_interval` 默认 | **1** | 原 `p.add_argument('--decision_interval', type=int, default=1, …)` |
| 主训练 YAML | **10** | `formation_ed_ab_3train_1plus1.yaml` ⇒ `metadata.json` 的 `hyperparameters.decision_interval = 10` |
| `REPRODUCIBILITY.md` §十 主对比命令 | **未传该参数** | `… --mode all --checkpoint <best.pt> --n_seed 3` |

⇒ 照文档命令跑，D-RL 行会以**每原始步重新决策**执行，而策略是在**10 步动作保持**（semi-MDP）下训练的 ⇒ **训练/评估失配**（违反项目铁律"训练和评估必须用一致的参数"），且与 ADR-021 P0 三行实跑口径（**显式** `--decision_interval 10`）不一致。

**为何藏了一整轮**：真正跑过的主结果都显式带了 `--decision_interval 10`；"照文档命令跑"从未被列为验收步骤。这与 LRN-20261001-011（`--mode all` 因 `store_true=False` 静默缺 MPC 行）**同一病根**。

**二、修复**

1. `--decision_interval` 默认由 `1` 改为 **`None` = 自 ckpt 内嵌 metadata 的 `hyperparameters.decision_interval` 读取**（ckpt 自描述协议，与既有 `probe_critic_mode` 同源）；读不到 ⇒ 退回**训练标准值 `TRAIN_DEFAULT_DECISION_INTERVAL = 10`**并**明确打印**（不静默）。
2. 解析置于 `build_metadata` **之前** ⇒ `metadata.eval_args.decision_interval` 与实际行为一致（同 LRN-011 的纪律）。
3. 显式 `--decision_interval N` 行为**完全不变** ⇒ 不影响任何已显式指定间隔的既有结果。
4. 顺带修正模块 docstring 里**不可用**的示例 `--mode decompose`（不在 `choices` 中，会直接 argparse 报错）⇒ 改为 `--mode decompose_m1`。

**三、验证（3 层）**

- **单测**：`tests/test_metric_accounting.py` 新增 5 项 ⇒ 该文件 **14 passed**（原 9 项 + 新 5 项：显式透传 / 自 ckpt 读取 / 缺失退回 10 / 旧 ckpt 无字段退回 / 源码级防回流）。
- **真实 ckpt 实跑**：`--mode decompose_m1 --checkpoint outputs/checkpoints/formation/final_seed0/mappo_fleet_last_ep1623_dec_ad2_cp_seed0_seed0.pt --max_steps 120 --n_seed 1 --out_suffix _di_fix_check`：
  ```
  [decision-interval] 自 ckpt metadata 读取 decision_interval=10（与训练一致）
  decompose-M1 RL(…ep1623…, interval=10): reward +827 | peakCoupler 494kN | viol 0 | ATP事件 288 | AB步 0 | meanED 0.743 | band率 100.00% | 末速 76.7km/h
  已保存: outputs/results/decompose/eval_decompose_decompose_m1_ms120_di_fix_check.json
  ```
- **三处一致**（产物 `…_ms120_di_fix_check.json`）：行标签 `interval=10`、`metadata.eval_args.decision_interval = 10`、`args.decision_interval = 10`。
- 同产物另记：`metadata.critic = centralized_scalar`、`metadata.reward_schema = v2-bounded-overlimit-section-force` ⇒ 旧 ckpt（标量价值头）在新脚本下仍可正常装载（`probe_critic_mode` 兜底生效）。

**四、边界（未受影响）**

- 本次改动的是**不被训练进程导入**的独立评估入口（全仓 `grep` 确认无模块 import 它）⇒ 不违反「长训在跑期间的行为性代码冻结」（该规范已按"**产物依赖闭包**"精确化，见 `EXECUTION_RULES.md`）。
- 不改变任何**已显式指定** `--decision_interval` 的历史结果；唯一行为变化发生在"未传该参数"这一此前**未被用作主结果**的路径上。

**五、落地**：`LEARNINGS.md` LRN-20261001-015；`REPRODUCIBILITY.md` §十（命令说明"无需再手动加该参数"）；`PROJECT_PIPELINE.md` 缺口⑬；`tests/test_metric_accounting.py`；`docs/rules/EXECUTION_RULES.md`（冻结规范精确化）。

***

### 审计-2026-10-01-主表 checkpoint 选取：`best.pt` **不保证存在** + 主表用 `last`/`best` 待裁决

**背景**：11.7 天级长训跑完后，"主对比三行"要拿哪个 `.pt` 当 D-RL 行？审计 `train_runner.py` 的 checkpoint 写出路径（`:300-302` / `:460-471`），发现两件事：

**一、三类 checkpoint 的"存在性"完全不同（此前文档未写明）**

| 文件（`{cp_tag}` = `dec_ad2_cp`） | 写出条件 | 1400 ep 后是否保证存在 |
| :-- | :-- | :-- |
| `mappo_fleet_last_ep{N}_{cp_tag}_seed{S}.pt` | 每 `log_interval`(=10) ep 一次 **且末集必写**（`save_last` 在 `(ep+1)%log_interval==0 or ep==run_episodes-1` 分支内） | ✅ **保证**（`N=1400`） |
| `mappo_fleet_ep{N}_{cp_tag}_seed{S}.pt` | 每 10 ep（`namer.periodic_path`） | ✅ 存在（多份） |
| `mappo_fleet_best_{cp_tag}_seed{S}.pt` | **仅当**某次 `long_eval`（每 50 ep，共 28 次）满足 `ok = (viol==0 ∧ peak_kN ≤ 1000 ∧ 末速∈[v_min,v_max])` **且** `ep_r > best_eval['reward']` 才写 | ⚠️ **不保证** —— 28 次全不达标 ⇒ **文件不存在** |

- **根因**：`long_eval > 0` 时 `_maybe_save_best` 被**跳过**（`train_runner.py:300-302`，注释写明"long_eval 启用时 best 由完整剖面评估驱动，训练窗口 reward 不再直接写 best"）⇒ `best` 的唯一来源是 `long_eval` 的达标判据。
- **危害**：`REPRODUCIBILITY.md` §十 的主对比命令写的是 `--checkpoint <best.pt 路径>`；若 `best` 从未写出，**命令会直接报"路径不存在"**（或更糟：误以为是训练失败），而实际训练是成功的。此类"文件不存在 ≠ 训练失败"的误判会浪费排查时间，也可能让人错用别的权重。

**二、主表该用 `last` 还是 `best` —— 既有口径与新机制的张力（待裁决）**

- 项目既有口径（用户既定偏好）：「主结果用**完整训练后的 `last`**（1400 ep），不用训练 reward 选出的 `best`」。
- ADR-017 §2 的要求：`long_eval` 每 50 ep 用**完整剖面选优**（即 `best` 是"评估选优"产物）。
- 关键变化：`best` 现在**不再由训练 reward 选出**，而由"完整剖面达标 + 评估 reward 改进"选出 ⇒ 上述两条**不再互斥**，甚至可以说 `best` 更符合"长程不崩"的初衷。
- ⇒ **需明确裁决**（涉主表口径，不由 Agent 单方定）：D-RL 行取 `last_ep1400`（端态、无条件可复现）还是 `best`（评估选优）。**裁决前不要只跑一行就下结论**；两者都跑代价可控（D-RL 单行 53km ≈57 min，远低于 MPC 行的 ≈10.3 h）。

**三、落地**

- `REPRODUCIBILITY.md` §十 新增"存在性对照表 + 跑前 `ls` 确认 + 待裁决项"；
- `PROJECT_PIPELINE.md` 长久计划 1 登记为待裁决；
- 本审计**未改动任何代码**（纯读取 + 文档），不触及长训的代码冻结边界。

***

### 审计-2026-10-01b-主表 MPC 行的**动作桥接量纲错配** + 默认 `fair` 未开 `inner_rule_cyclic`

> **与既有条目的关系（勿当重复）**：`DIAGNOSTICS_2026-09.md:53` 已把"**fair-MPC 是 strawman**（3.2s SLSQP / 无规则内层 / 无终端集 / 短 horizon）"列为 **still-unresolved**，处方是"补 MPC + 同规则循环制动内层基线"。本条是**新的一层缺陷**：即便把规则内层打开，**动作桥接的量纲仍是错的** —— 处方若只按"加规则内层"执行，仍修不好。

**一、动作列语义（两套，互相冲突）**

| 通道 | 生产者 | 语义 | 取值 |
| :-- | :-- | :-- | :-- |
| `MultiLocoController.get_action_accel(train, target_accel)`（**MPC 桥接**） | `src/controllers/multi_loco_controller.py:377-394` | **绝对 ED 深度**：制动态 `ed = min(−a/a_max, 1)`；牵引态 `ed_throttle` 保持 **0** | col0 ∈ **[0,1]**，col1 **恒 0** |
| `MultiLocoController.get_action_decomposed(...)`（**decompose 消费端**） | 同文件 `:272-323` | **加性调制**：`final[i,0] = clip(baseline_ed[i] + ed_mod_coef(0.5)·ed_mod[i], 0, 1)`〔`ed_mod_coef` **已于 2026-10-02 放宽为 1.0**，ADR-023〕；`ed_mod<0` 才是"减闸/加牵引" | ed_mod ∈ [−1,1] |

`mpc_act`（`evaluate_decompose.py:225-237`）把前者**直接当后者**：`U=compute_actions_from_env(env)` → `get_action_accel(tr, U[ti])` → 拼成 `(num_agents,2)` 喂 `env.step`。**Fair 与 NMPC 共用此桥接**（两者 `compute_actions_from_env` 都返回"每列目标加速度"）。

**二、实测证据（探针 `outputs/probe_mpc_bridge.py`，同态同剖面，用后即删）**

```
[mpc_act] 动作形状 = (6, 2)
[mpc_act] col0 (ed_mod 通道) 逐 agent = [0.75 0.75 0.75 0.75 0.75 0.75]
[mpc_act] col1 (ab_mod 通道) 逐 agent = [0. 0. 0. 0. 0. 0.]
[规则基线 env.trains[0]] shape=(2, 2) ed=[1.  0.7] ab=[0. 0.]
```

**三、两个后果**

1. **指令不被兑现（量纲误差 ≈2×，且上限截断）**：MPC 要 `ED=0.75`（中等制动），实际 `final_ed = clip(baseline + 0.5×0.75)` = `clip(1.0+0.375)=1.0` 与 `clip(0.7+0.375)=1.0` ⇒ **两机车 ED 全部打满**。与历史观测**完全一致**：同一 120 步窗口 `MPC(Fair) meanED = 1.000`（饱和）而 `M0 规则 meanED = 0.850`。⇒ MPC 的"目标加速度"**没有被低层兑现**，实际制动力显著强于其意图（与 `fair_mpc_controller.py:11-13` 自述"MPC 直接给每列目标加速度，列内低层负责 throttle 映射"**相矛盾**）。
2. **单向性（结构性）**：桥接 col0 **永不为负** ⇒ MPC **不可能**减闸、也不可能施加牵引 ⇒ 无法主动维持速度带下沿/追回速度。在长大下坡上这会把 MPC 推向"只会更用力刹"的一侧（低40 / 末速偏低风险），而这**恰好偏向有利于本项目方法的方向** —— 正是 strawman 争议的形态。

**四、附带发现：新主表脚本**丢失**了旧脚本里"like-for-like MPC"那条变体**

- **旧脚本把这件事做成了显式二选一**（`evaluate_m1_m3_long.py:62-73`）：
  `inner_rule_cyclic=(controller == 'mpc_rule')` ⇒ 两条独立模式 ——
  **`mpc_dir` = MPC 直接控加速度（无规则内层）** / **`mpc_rule` = MPC + 规则循环制动内层**，
  注释明写后者才是"与 M-MARL **like-for-like**、消解审稿人'fair-MPC 被剥掉工业 ATO 规则内层'质疑"的公平基线。
- **新脚本 `evaluate_decompose.py` 里这个开关消失了**：`:176` 把 `fair` **硬编码**为 `inner_rule_cyclic=False`
  （≡ 旧脚本的 `mpc_dir`，即**弱的那条**）；`:166` 的 `nmpc` 才是 `True`。**没有任何 CLI 入口能跑到 `mpc_rule` 等价物**。
- 而 `REPRODUCIBILITY.md` §十 的主对比命令**未传 `--mpc_type`** ⇒ 默认即 `fair` ⇒ **主表落到的正是"没有规则内层"的那条**。
- 旁证：`fair_mpc_controller.py:74-79` 的注释 + `HANDOFF_2026-09-22.md:32` 都把 `inner_rule_cyclic=True` 记为消解 strawman 的措施。
- ⚠️ **用词精确（勿over-claim）**：该开关的**实际实现**是**限速兜底**（`fair_mpc_controller.py:231-240`：`v ≥ v_max` 压到 SERVICE 制动、`v ≤ v_min` 强制缓解/牵引），**不是**循环制动/AB 层 ——
  AB 兜底由 `get_action_cyclic_braking` 基线提供、**与开关无关**（`mpc_act` 的 col1 恒 0 ⇒ `ab_mod=0` ⇒ 不调制 ⇒ 规则基线的 AB 原样保留）。所以"没开"的后果是**速度带上下限没有兜底**，而不是"没有空气制动"。
- ⇒ 这不是"可能有意为之"，而是**旧脚本明确区分的两条变体，在新主表生成器里只剩弱的那条** —— 属**能力回退**，不是口味差异。

**四之二、同一族还有一处"默认值静默决定协议"：`--mpc_type` 默认 `fair`，而项目已决定换 `nmpc`**

- `evaluate_decompose.py:254`：`--mpc_type` 默认 **`fair`**；`REPRODUCIBILITY.md` §十 主对比命令**未传该参数** ⇒ 主表 MPC 行走 **Fair**。
- 但 `nmpc_controller.py:3-5` 自述其定位 = "**替换粗糙 FairMPCController 的成熟 MPC 对比基线**（导师口径：**不要留粗糙 MPC 当靶子**，目标是 MARL 效果达到与成熟 MPC 相当）"，立项于 **2026-09-17**。
- ⇒ 文档命令**静默落回被明确"要换掉"的那条基线**，与既定方向相反。这与本文件「修复-2026-10-01c」是**同一病根**（CLI 默认值静默决定协议/语义）的第三次复发。
- ⚠️ 本条**归入同一待裁决**：主表 MPC 行到底用 `fair` 还是 `nmpc`（若用 nmpc，文档命令必须显式带 `--mpc_type nmpc`）。

**四之四、为什么"有测试却没抓到"（关键，说明该缺陷不是"没人想过要防"）**

- `tests/test_nmpc_controller.py:113-132` 的 `test_nmpc_magnitude_comparable_to_rule_baseline` **意图完全正确** ——
  断言串是 "NMPC 与 D-Rule 车钩力/ED 深度**同量级（非粗糙靶子）**"，正是本缺陷破坏的那条性质。
- **但它抓不到**：判据是 `abs(nmpc.mean_ed − rule.mean_ed) < 0.6`。实测该差只有 **≈0.15**（规则 0.85 vs NMPC 打满 1.0）
  ⇒ **远在容差内，绿灯通过**。容差 0.6 是按"两者都在物理制动带内"设的，对"ED 被推到饱和"这种**方向性失真**不敏感。
- 且该测试只走 **NMPC（`inner_rule_cyclic=True`）**；**默认 `fair`（`inner_rule_cyclic=False`）这条路径没有任何同类测试**。
- ⇒ **教训（与 LRN-20261001-013 同型）**：**"有测试"≠"测试覆盖了该要求"** —— 容差型断言会掩盖方向性偏差；
  断言"同量级"时应同时断言"**不饱和/不撞界**"（例如 `mean_ed < 0.99` 或"指令 vs 实到"的直接比对）。

**四之三、SSOT 核查（防止把已知项当新发现）**

- MPC 协议 SSOT = `RESEARCH_POSITIONING.md` §1.5 / §1.6 + `DECISIONS.md` ADR-016。已逐条核对：§1.5 讨论的是**跨线是否重喂 `grade_at`**（Regime A/B 公平标定），**未涉及**"目标加速度→throttle 桥接"的量纲问题。
- ⇒ 本条**不是** SSOT 已覆盖的内容，属**新增**；与 `DIAGNOSTICS_2026-09.md:53` 的 strawman 条目亦为两层不同问题（见本节开头的"与既有条目的关系"）。

**五、待裁决 / 待修（涉 MPC 对比规范 = 立论铁律，Agent 不单方改）**

- 修法候选（需你选，各自都有代价）：
  - **(甲) 反解加性关系**：让桥接输出 `ed_mod = clip((desired_total_ed − baseline_ed)/ed_mod_coef, −1, 1)`，并让 MPC 明确给出它要的 **total ED**（而非经 `get_action_accel` 的绝对深度）。最小改动、保留"规则内层 + 优化外层"结构；代价 = 需要定义 accel→total ED 的映射（坡道上非 1:1）。
  - **(乙) 给 MPC 直接权限**：MPC 行绕开加性调制、直接决定 throttle（真正"直接命令加速度"）。语义最干净；代价 = 与 D-RL 的结构差异变大，需在论文里重新论证 like-for-like。
  - **(丙) 只开 `inner_rule_cyclic=True`（一行）**：仅修第四节的默认不一致，**修不了**第三节的量纲错配。
- ⚠️ **任何一改都会改 MPC 行的数值** ⇒ 必须在**出主表之前**裁决；裁决前不要把现有 Fair-MPC 行当最终基线。
- 这三条都不在本次四改造（A/B/C/D）范围内，也不受长训代码冻结影响（评估入口不在训练闭包内）。

**六、落地**：`REPRODUCIBILITY.md` §十（MPC 行加警示指针）；`PROJECT_PIPELINE.md` 长久计划登记；探针脚本 `outputs/probe_mpc_bridge.py` **用后已删**（留痕即上方实测输出）。

### 修复-2026-10-01d-MPC 桥接量纲错配（M1）甲方修复 + M3/M4 + 规则层审计（R1/R2/M2）

> **与上一条的关系**：上条（「审计-2026-10-01b」）是**审计/待裁决**；本条是**裁决后的落地 + 验证**。用户裁定修法 = **(甲) 反解加性关系**。

**一、规则层审计（用户本轮指令"继续做规则层"）**

| 候选缺陷 | 结论 | 证据 |
| :-- | :-- | :-- |
| **R2**：`get_action_decomposed` 把 col0 `clip(…,0,1)` ⇒ 负 ed（牵引）永不可达 ⇒ `coordination_adj` 的 traction 设计是死代码 | ❌ **推翻** | `coordination_traction` **确实被消费**：在 `train_fleet_env.py:680-683` 于 `get_action_decomposed` **返回之后**直接写 `final_edab[k,0] = −traction`，**绕开**了方法内的 `clip(0,1)`。且该注入**纯规则驱动**（只依赖 `ti>0` + `coordination_traction>0` + `not ctrl._cyclic_braking`），**对 RL 与 MPC 一视同仁** ⇒ 不构成权限不对称 |
| **R1**：`get_action_cyclic_braking` docstring 称"超速→制动 / 低速→缓解 / **中段维持**"，但 else 分支 `ed_nominal=0, ab_nominal=0` | ⚠️ **措辞歧义，非功能缺陷** | `_cyclic_braking` 是**两态闩锁**（`vel≥eff_v_max`→True / `vel≤eff_v_min`→False），"中段维持"= **保持闩锁状态**；长大下坡带内惰行符合循环制动惯例。⇒ 低压措辞项 |
| **M2**：`get_action_accel` 牵引分支算了 `throttle` 却**未返回**（`multi_loco_controller.py:391-394`） | ✅ **确认（真死赋值）** | 返回式只含 `ed_throttle` 与全零 AB ⇒ MPC 正加速度指令被**静默丢弃**。**属闭包内文件**（训练产物依赖）⇒ 不在本轮改，登记待停训期清理；且**新桥接已不消费该分支**（见下 §二.3）⇒ 不影响主表 MPC 行 |

**二、M1 修复（甲方：反解加性关系）**

`evaluate_decompose.py`（**不在训练闭包内 ⇒ 可改，无需停训**）：

1. 新增 `_rule_baseline_edab(ctrl, tr, env)`：用权威实现 `get_action_cyclic_braking` 复算基线（避免在评估侧复制规则逻辑而漂移），并**保存/还原 `ctrl._cyclic_braking`** —— 该方法会写闩锁，若不复原则评估侧"预演"会改变 env 的实际制动分支。
2. 新增 `mpc_act` 反解：`desired_ed = clip(−U/max_accel, 0, 1)`；`ed_mod = clip((desired_ed − baseline_ed)/ED_MOD_COEF(0.5), ±1)`；并按 MPC 意图给 `ab_mod` —— 想停/加速（`desired_ed≈0`）→ **抑制** `+0.4`；需求顶满自有权限（`desired_ed ≥ 0.7`）→ **预触发兜底** `−0.4`；其余 `0`。
3. **有意不复用 `get_action_accel`**：它内部已乘 `_coupler_throttle_scale`，而 env 的 `get_action_decomposed` 末尾**会再乘一次** ⇒ 高车钩力时 ED 被**双重缓和**。改为内联同一映射（`−U/max_accel`），把车钩力缓和留给 env 侧统一施加（顺带使 M2 的死分支与主表解耦）。
4. **权限等价性（本轮核心结论）**：修复后 MPC 与 D-RL **动作权限完全一致** —— 同样 ±0.5 ED 调制〔**带宽 2026-10-02 已放宽为 1.0，但仍两侧同款**，ADR-023〕、同样 AB 抑制/预触发阈值、同样**无牵引通道**（牵引由 env 的 `coordination_adj` 规则注入，双方同享）⇒ 唯一差异回到"**决策来源**"（NMPC/Fair-MPC 在线优化 vs MAPPO），符合 ADR-016 不失公允口径。
5. ⚠️ **已知近似（有界、须如实写入论文/文档）**：基线以**未协调**带边（`v_max_adj=v_min_adj=0`）复算，而 env 内部对 follower 会叠加 `coordination_adj` 抬带/压带，其值依赖"前一列已 step 之后的**位置**"，在 `env.step` **之前**无法复现 ⇒ follower 处于带边附近时基线估计有偏差（**≤0.5 ED 深度**）。**不影响安全性**（env 侧 clip + SafetyLayer + ETCS 全程生效），只影响"请求 → 交付"的精度。要精确须改闭包内 env（停训代价）。
6. **AB 预触发阈值可达性（防死分支，同 LRN-20261001-007）**：`MPC_AB_TRIGGER_ED = 0.7 < |accel_lo|/max_accel = 0.75`（Fair 与 NMPC 一致）⇒ 可达；单测以 `inspect.signature` 读取默认值守此不变式，**防后人把阈值调高到 ≥0.75 变成死代码**。

**三、M3 / M4（同族"CLI 默认值静默决定协议"）**

- **M3**：`inner_rule_cyclic` 由两处**硬编码**（`nmpc:True` / `fair:False`）改为统一显式开关 `--mpc_inner_rule_cyclic`（**默认 False**）。语义澄清：decompose 通道里 **env 本来就无条件施加规则基线** ⇒ `False` 才是与 D-RL 的 **like-for-like**（各一层同样的护盾）；`True` = MPC **叠两层**护盾（旧脚本 `mpc_rule` 在**非 decompose** 通道下曾是 like-for-like，在本通道已不对等）。⇒ 原 `nmpc` 分支注释"与 D-RL 同构"**不成立**，一并更正。
- **M4**：`--mpc_type` **默认值保持 `fair` 不动** —— 改默认即"静默改动既有主表数值"，正是 LRN-20261001-011 型缺陷；改为在 help/文档中**明写"主表成熟基线请显式传 `--mpc_type nmpc`"**（fair 仅为历史默认）。
  > ⚠️ **SUPERSEDED（同日，ADR-022）**：用户裁定"**只留 nmpc，其他的都删除**" ⇒ `fair` 与简化 MPC **已整体删除**，`--mpc_type` 收敛为**单值枚举 `nmpc`**。本条的"不改默认、只改文档"结论被"删掉选项"取代（理由：留着一个被明确判为"粗糙靶子"的选项，等于把靶子留在仓库里）。见本文件「删除-2026-10-01」+ `DECISIONS.md` ADR-022。
- （附）`--mpc_simple` 是**从未被使用**的选项：全仓（含全部历史结果 JSON）`mpc_simple` 恒为 `false`，且 `MPCController` **没有** `compute_actions_from_env` ⇒ 一旦启用会在 `mpc_act` 处 AttributeError。**已随 ADR-022 删除**（连同 `MPCController` 与其唯一的另一处用法 `--mpc_enforce_coupler`）。

**四、验证**

- 定向单测：`tests/test_metric_accounting.py` **21 passed**（新增 7 项：反解精确性行为级断言 / AB 双通道意图 / 预触发阈值可达性 / 复算不污染闩锁 / 桥接饱和计数 / 源码级防回流 ×2）。其中反解断言是**旧缺陷的回归守卫**：旧实现交付 = `0.5×期望`，会红。
- 补强被绕过的那条测试：`tests/test_nmpc_controller.py` 的 `_nmpc_act` 原自带一份桥接**副本**（与生产并行演化 ⇒ 生产的量纲错配在测试里被副本掩盖）⇒ 改为**直接调用生产 `ev.mpc_act`**；并给 `test_nmpc_magnitude_comparable_to_rule_baseline` **补"不撞上下界"断言**（原 ±0.6 容差被 0.15 的实际差骗过）。
- 全量回归：`pytest tests/ -q` ⇒ **241 passed / exit 0**（含本次评估侧全部改动，无失败）；`python scripts/check_agents_links.py` ⇒ `[OK] … 22 个已有 ADR`。
- **真 env 实跑（公平口径，`--mpc_type fair`，300 步，53km 剖面，seed 0）**：

  ```
  [mpc-bridge] 反解加性调制（ED_MOD_COEF=0.5；AB 抑制/预触发 mod=+0.4/-0.4，预触发阈值 desired_ed≥0.7）
  MPC(Fair) @ shuozhou_real_53km: reward +2272 | peakCoupler 414kN | viol 0 | ATP事件 288 |
    AB步 3 | meanED 0.744 | band率 100.00% | 末速 71.2km/h |
    MPC求解 651ms均值/1744ms峰值 | fail 0 | 桥接越权请求 0 步·机车
  ```

  ⇒ **`meanED` 退出饱和**（修复前同一 MPC 行 = **1.000**，见上一条 §三.1）⇒ 指令按期望交付；`viol 0`、`band 100%`、`越权请求 0` 说明该窗口内 MPC 的请求全在 ±0.5 权限内、完全兑现。结果 JSON 同时记录了 `metadata.eval_args.mpc_inner_rule_cyclic=false`（M3 开关已进元数据）与新键 `mpc_bridge_ed_saturated`。
- ⚠️ **由实测引出的新观察（待裁决，非桥接问题）**：MPC 的 `meanED 0.744` **≈ 其自身权限上限 0.75**（`accel_lo=-0.75` ⇒ 期望 ED 上限 = `|accel_lo|/max_accel` = 0.75），而规则层/RL 的 ED 可达 **1.0**（`get_action_cyclic_braking` 的 `clip(1−stagger,0,1)`，队首机 ED=1.0）⇒ **存在"控制器自身动作边界"造成的制动权限差**（Fair 与 NMPC 的 `accel_lo` 默认都是 −0.75）。这**不是**桥接造成的（桥接已把 MPC 的请求忠实交付），而是 MPC 控制器的参数选择。若要完全对等，须把 `accel_lo` 放宽到 −1.0（或在论文中明确声明该差异及其来源）。**修法涉 MPC 控制器默认参数 ⇒ 与"主表用 fair/nmpc"一并待你裁决。**
- ⚠️ **MPC 行历史数值全部作废**（口径已变），主表须重跑。

**五、直接可读的教训**：`LEARNINGS.md` **LRN-20261001-017**（桥接跨通道搬迁 ⇒ 语义/量纲未随通道改；容差型"同量级"断言对**撞界/饱和**不敏感）。

### 删除-2026-10-01-MPC 基线唯一化为 NMPC（ADR-022）+ 术语统一

- **触发**：用户提问"**nmpc 是什么意思？不要乱其名字**"。核对后发现仓库里**三个 MPC 并存**、命名与锚点互相矛盾（详见 `DECISIONS.md` ADR-022 背景）：`FairMPCController`（聚合列 + 车钩力代理 + SLSQP）被 SSOT §1.6 指名为主表基线**且是 `--mpc_type` 默认值**；`NMPCController` 的立项口径却是"**替换粗糙 FairMPCController**、不要留粗糙 MPC 当靶子"；简化 `MPCController` 从未启用。
- **术语澄清（回答"nmpc 是什么"）**：**NMPC = Nonlinear Model Predictive Control（非线性模型预测控制）**；本项目实现 = `NMPCController`（`src/controllers/nmpc_controller.py`）：列内**集中质量(lumped)多体**（`n_lump=4` 块/列）+ **MT-2 符号化车钩**（预压/刚度/Stribeck/间隙死区/行程饱和）+ 车钩力 ≤1000 kN 硬约束 + 终端代价 + control blocking，求解器 **casadi + IPOPT**。**"多体" ≠ 逐车 ~101 节全耦合多体**（文件头已加术语声明）。
- **用户裁定**："**只留 nmpc，其他的都删除**" → 立 **ADR-022**。
- **删除清单（8 个文件）**：
  | 删除 | 理由 |
  | :-- | :-- |
  | `src/controllers/fair_mpc_controller.py`（`FairMPCController`） | 被明确判为"粗糙靶子"的旧基线；其聚合模型 + 车钩力代理与"同档对冲"口径不符 |
  | `src/controllers/mpc_controller.py`（`MPCController`） | 简化线性 MPC，**全仓从未启用**（`--mpc_simple` 恒 false） |
  | `src/evaluation/evaluate_m1_m3_long.py` | 评估旧入口（M1/M3/M4 语义代号已废止），且 import 上面两个已删类 |
  | `make_m1m3_figures.py` / `make_5train_fig.py` / `eval_phys2_m1_5seed.py` / `eval_phys2_5train.py` / `eval_dqn_multitrain.py` | 依赖 `evaluate_m1_m3_long` 的制图/统计/评估链，随之失效 |
- **代码改动（evaluate_decompose nmpc-only）**：去 `fair`/`mpc_simple` 分支与 import；`--mpc_type` 收敛为**单值枚举 `{'nmpc'}`（默认 `nmpc`）**（保留单值枚举只为既有文档命令按原样可复现，不再是"默认值静默决定协议"）；移除 `--mpc_simple` 与随之失效的 `--mpc_enforce_coupler`；`_mount_mpc` 文档串重写；两处指向 `FairMPCController` 的注释改为控制器无关表述。
- **测试改动**：删 `test_fair_mpc_records_solve_statuses`（源文件已删）；等价断言改为对**唯一**控制器 `NMPCController` 的 `test_nmpc_records_solve_statuses`；`test_mpc_bridge_ab_trigger_reachable` 收敛为只查 NMPC；`test_eval_mode_all_normalizes_enable_mpc` 的源码切片锚点由 `mpc_label` 改为 `results['mpc'] = eval_method(`（原锚点随简化消失）。
- **文档同步**：`RESEARCH_POSITIONING.md` §1.6（`fair_mpc_controller` 指名 → `NMPCController`；"多质点" → "集中质量(lumped)多体"；Appendix 两处 `SLSQP` → `IPOPT`；标定口径的 b0 出处改指 `nmpc_controller`）、`AGENTS.md`、`docs/README.md`（Regime A/B 行同时更正为 A-only）、`REPRODUCIBILITY.md`（§三 加**失效声明**、§四 简化 MPC 与 DQN 评估链标删除、§十 MPC 三节改写 + 主表/跨线命令补 `--mpc_type nmpc`、更正 `--mode decompose` 笔误）、`PROJECT_PIPELINE.md`（4.x 命令块加失效声明 + 长久计划 2b 补 ADR-022）、`rules/EXECUTION_RULES.md`（评估入口改指 `evaluate_decompose`）、`src/trainer/ckpt_policy.py`（**纯注释**）、`src/evaluation/make_phys2_figures.py`（注释）。
- **验证（实跑）**：`pytest tests/ -q` ⇒ **exit 0，全绿**（后台日志仅落 4 行进度点：72+72+72+27 = **243 tests，无 F/E**；末行汇总计数未被 `| tail` 捕获 ⇒ 只能确认"全绿 + exit 0"，不引具体 passed 数）；定向（`test_metric_accounting` + `test_nmpc_controller` + `test_fleet_decompose` + `test_ab_refill_and_safety_authority`）**46 passed**；`check_agents_links.py` ⇒ `[OK] … 23 个已有 ADR`（ADR-022 已登记）；真 env `--mode mpc --mpc_type nmpc --max_steps 300 --n_seed 1`：
  ```
  MPC(NMPC 集中质量多体+MT-2+IPOPT) @ shuozhou_real_53km: reward +2221 | peakCoupler 318kN | viol 0 |
    ATP事件 288 | AB步 0 | meanED 0.512 | band率 100.00% | 末速 73.3km/h |
    MPC求解 74ms均值/1693ms峰值 | fail 0 | 桥接越权请求 455 步·机车
  ```
  ⇒ 标签/枚举/桥接全部按 nmpc-only 生效；**求解成本比已删除的 fair/SLSQP 快约 9×**（74 ms vs 651 ms 均值）⇒ 53km MPC 行从 ≈6.5 h/seed 降到 **≈0.74 h/seed**（`REPRODUCIBILITY.md` §十 已同步更正）。
- ⚠️ **实测新发现（与 `accel_lo` 同族，须一并裁决）**：`桥接越权请求 455 步·机车` = NMPC 的期望 ED 与规则基线之差 > ±0.5 被 clip 截断的次数（fair 行为 0）⇒ **±0.5 的 ED 调制权限带对 NMPC 偏窄**。但该带宽与 D-RL **完全相同**（like-for-like 的设计结果）⇒ 不是"MPC 被单独削弱"，而是"**动作权限带本身**是否够用"。与 "`accel_lo=-0.75` ⇒ 期望 ED 上限 0.75 < 规则/RL 的 1.0" 共同构成**两重上限**；放宽任一项须同步评估 D-RL 的同一限制，勿造出新的不对称。
  > 【**已裁决（2026-10-02）**：按 ADR-023 **全局放宽**为 `ed_mod_coef = 1.0`（全幅）⇒ 同窗口 `桥接越权请求` **455 → 0**；`accel_lo` 保持 −0.75 并登记为已声明差异。见本文件「放宽-2026-10-02」+ `DECISIONS.md` ADR-023。】
- **⚠️ 后果**：**MPC 行历史数值全部作废**（控制器更换 + 桥接口径已修），主表须按 Regime A 重跑。`history/**` 内引用 `evaluate_m1_m3_long` 的旧脚本成为**悬空引用**（历史区，按设计不复现）；`outputs/deprecated/**` 与历史结果 JSON **原样保留**。`requirements.txt` 的 `scipy` 在 `src/` 内已无引用 ⇒ 暂留，避免连带风险。
- **未裁决项（不变）**：① 主表 D-RL 行取 `last_ep1400` 还是 `best`；② `1400ep × 5 seed` 算力（单机 ≈58 天）；③ NMPC `accel_lo=-0.75` ⇒ 期望 ED 上限 0.75 vs 规则/RL 可达 1.0 的**控制器参数级权限差**（是否放宽到 −1.0）。
  > 【**③(b) 已由 ADR-023 裁决（2026-10-02）**：带宽全局放宽为 1.0；③(a) 保持原值并登记为已声明差异。】

### 放宽-2026-10-02-ED 调制带宽 0.5→1.0（ADR-023；用户裁定"放宽 ①"）

- **触发**：ADR-022 验证实测 `桥接越权请求 455 步·机车`（见上一条「删除-2026-10-01」§末）⇒ 用户裁定：「**放宽 ① 吧，这个只是作为一个 baseline，所以细节不重要，你自主决策即可**」。
- **裁决 = 选项 ①（全局放宽带宽，非只放宽 MPC）**：`ed_mod_coef` **0.5 → 1.0**。依据：`ed_mod ∈ [−1,1]` 与可达差 `|Δ| ≤ 1.0`（MPC 期望 ED ∈ [0,0.75] 与规则基线 ∈ [0,1] 之差的上界）**恰好匹配** ⇒ 桥接零截断；且**两个通道权限依旧完全相同**（对称）。否掉"只放宽 MPC 侧"：那会造出 MPC 带宽 > D-RL 带宽的**新不对称**，违反 ADR-016 不失公允口径。
- **改点（3 处，均为非冻结区/停训后执行）**：
  1. `multi_loco_controller.get_action_decomposed` 的 `ed_mod_coef` 默认值 `0.5 → 1.0`。这是**全仓唯一改点位**（无任何调用方显式传该参数；`train_fleet_env.py:673` 只传 `v_max/v_min/adj`）⇒ 训练与评估**同时**生效，不存在"训练按 A、评估按 B"。
  2. `evaluate_decompose.ED_MOD_COEF` 由**硬编码镜像常量**改为 `inspect.signature(MultiLocoController.get_action_decomposed).parameters['ed_mod_coef'].default` **派生** —— 灭掉 LRN-20261001-017 同族"两处并行演化 ⇒ 静默失配"。
  3. `metadata.build_metadata` 新增键 **`ed_mod_coef`**（动作空间语义：换值即换策略含义，同一 ckpt 行为不同）⇒ 历史运行可比对。
- **不改** `accel_lo = -0.75`（ADR-022 未裁决项③(a)）：它是控制器**自身**的制动深度参数，且 0.75 m/s² 电制动已大于最陡 −10‰ 的重力分量（≈0.098 m/s²）⇒ 物理上非瓶颈；ADR-023 把它**登记为已声明差异**（规则层 ED 可达 1.0 vs NMPC 期望 ED ≤ 0.75）。
- **验证（实跑，结果 JSON = `outputs/results/decompose/eval_decompose_mpc_ms300_adr023_coef1_check.json`）**：
  ```
  python src/evaluation/evaluate_decompose.py --mode mpc --mpc_type nmpc --grade shuozhou_real_53km \
    --max_steps 300 --n_seed 1 --out_suffix _adr023_coef1_check
  ```
  ```
  [mpc-bridge] 反解加性调制（ED_MOD_COEF=1.0；AB 抑制/预触发 mod=+0.4/-0.4，预触发阈值 desired_ed≥0.7）
  MPC(NMPC 集中质量多体+MT-2+IPOPT) @ shuozhou_real_53km: reward +2221 | peakCoupler 318kN | viol 0 |
    ATP事件 288 | AB步 0 | meanED 0.500 | band率 100.00% | 末速 73.4km/h |
    MPC求解 69ms均值/1509ms峰值 | fail 0 | 桥接越权请求 0 步·机车
  ```
  ⇒ **`桥接越权请求` 455 → 0**（改前对照见上一条同窗口实跑），其余指标几乎不变（`meanED 0.512→0.500`、`peakCoupler 318kN` 不变、`viol 0` / `band 100%` 不变）⇒ 印证那 455 次是**权限带宽**所致，而非 MPC 决策异常。
- **测试**：定向（`test_metric_accounting` + `test_fleet_decompose` + `test_nmpc_controller`）**39 passed**。改动/新增：`test_decompose_ed_modulation_changes_ed`（±0.5 → ±1.0）、`test_mpc_bridge_inverts_additive_modulation`（ed_mod 期望由写死 `0.8` 改为 `desired / ED_MOD_COEF`）、`test_mpc_bridge_saturation_diag_is_recorded`（真实口径断言**恒 0**，并用 `monkeypatch` 把口径临时收窄到 0.5 证明计数器非死码）、**新增** `test_bridge_ed_band_derives_from_controller_default`（源码级守卫：带宽必须派生、不得手抄字面量）。
- **全量回归 / 引用校验**：`pytest tests/ -q` ⇒ **全绿（无 F/E）**——后台任务 exit 0，日志 4 行进度点 `72+72+72+28 = 244 tests`（= 上一轮 243 + 本次新增 1 项守卫，计数自洽）；末行汇总计数仍未落盘（`>` 重定向块缓冲，同 LRN-20261002-001 现象，**不代表失败**）。`python scripts/check_agents_links.py` ⇒ `[OK] AGENTS.md 引用一致性通过（ADR 编号越界检查 24 个已有 ADR）`（ADR-023 已登记）。
- **动作语义变更的后果**：按旧带宽（0.5）产出的 ckpt / 评估数值对新口径**失效** ⇒ seed0 长训（PID 673，ep55/1400，elapsed 5h22m，viol 0）已**主动停掉并按新口径重启**（新目录 `adr023_1400ep_seed0`）；旧目录 `adr021_1400ep_seed0` 的 55 集产物**原样保留**（不覆盖、不删除），标注"旧带宽口径、不得引用"。`P0 三行基线` / `AB 通道裁定` 同批作废，随 A/B/C/D 重训复核重做。

### 冒烟与基线-2026-10-02-新口径（ADR-023）下的冒烟 + 其余两行 baseline + 可跑消融

- **背景**：ADR-023（ED 调制带宽 0.5→1.0）改变了**动作空间语义** ⇒ 主表须按新口径重跑。用户指令："先冒烟看看效果，然后把别的 baseline 也跑了，消融能跑的也跑跑"（目标：直到 MARL 有好的结果；需要启动长训时暂停）。seed0 1400ep 长训已在跑（`adr023_1400ep_seed0`，PID 658，BC 热启动 `BC loss=2.674` 完成 ⇒ 进入训练循环）。
- **冒烟（两条，均带 `--out_suffix`）**：
  | 行 | 命令要点 | 结果 |
  | :-- | :-- | :-- |
  | MPC | `--mode mpc --mpc_type nmpc --max_steps 300 --n_seed 1` | `reward +2221 / peak 318kN / viol 0 / ATP 288 / AB步 0 / meanED 0.500 / band 100.00% / 末速 73.4km/h / 求解 69ms均值 / fail 0 / **桥接越权请求 0**（改前 455）` ✅ |
  | D-Rule | `--mode decompose_m0 --max_steps 300 --n_seed 3` | `reward +2298 / peak 512kN / viol 0 / ATP 288 / AB步 0 / meanED 0.850 / band 100.00% / 末速 70.5km/h` ✅ |
- **✅ 省算力发现：`--n_seed 3` 对确定性行是 3× 纯冗余（实测）**：`eval_decompose_decompose_m0_ms300_adr023_det_check.json` 的 `per_seed` 三段**逐位完全相同** —— `reward 2298.1141287732603`、`peak_coupler_kN 511.7638857894402`、`mean_ed 0.849999999999996`、`final_speed_kmh 70.45704045184233`。机制：`eval_method` 用**同一条 env** + 同一 `rng` 连跑 `n_seed` 个回合，而规则/MPC 行与 `eval_mode=True` 的 D-RL 行都是**确定性**的（`rng` 只在 `--random_init_speed` 时被消费）⇒ 回合无差异。
  - ⇒ 两行 baseline 本次用 `n_seed=1`（数字与 3 回合一致）；**建议**把主表口径改为"确定性行 `n_seed=1`；仅 `--random_init_speed` 鲁棒性协议用多回合"（ADR-016 协议本身不变；**待用户确认**）。省下的成本：MPC 行 2.2 h→0.74 h、D-Rule 行 ≈2.9 h→≈1 h（`--n_seed 3` 口径下）。
- **baseline（完整 53km / 36000 步，`n_seed=1`，`--eval_seed 0`，2026-10-02 完成）**：

  | 行 | reward | peakCoupler | viol | ATP事件 | AB步 | meanED | band率 | 末速 | 其它 |
  | :-- | :-- | :-- | :-- | :-- | :-- | :-- | :-- | :-- | :-- |
  | **D-Rule**（`_adr023_m0_53km`） | **+92 950** | 1073 kN | 68 | 124 559 | 2176 | 0.251 | **97.28%** | 50.6 km/h | — |
  | **MPC/NMPC**（`_adr023_mpc_53km`） | **−813 642** | 848 kN | 0 | **3 937 431** | 8588 | 0.315 | **61.98%** | 64.8 km/h | 求解 95 ms 均值 / 1693 ms 峰值；**solve fail 1936**；桥接越权请求 **0** |
  - ⇒ **两行都没问题地跑通了**，但读数有两点必须记住：① **`--n_seed` 冗余结论**（见上）成立；② **NMPC 在完整剖面上远弱于规则基线**（reward 差 9×、band 62% vs 97%、ATP 事件 31×、求解失败 1936 次）——其 `abal` 结构上**没有规则循环内层护盾**（`inner_rule_cyclic=False` 才是当前 like-for-like 口径）⇒ 已排 **M3 消融**（`--mpc_inner_rule_cyclic`，同一 53km）判定"是不是缺护盾导致的"，结果见下。
  - ⚠️ 另注：D-Rule 在完整剖面上 `peak 1073 kN / viol 68`（略破 1000 kN）——与 NMPC 的 `viol 0` 并不矛盾：MPC 用 8588 步 AB 硬压车钩力、代价是速度带崩掉（62%）。

- **⚠️ 诊断：新口径（`ed_mod_coef=1.0`）对 RL 行是负面的（A/B 证据，2026-10-02）**
  - **对照条件**：两次长训除 `ed_mod_coef` 外**完全同构**（同 YAML/seed/curriculum/reward/BC/物理；训练进程不导入 `evaluate_decompose`）⇒ 是干净的单变量 A/B：旧 = `adr021_1400ep_seed0`（0.5），新 = `adr023_1400ep_seed0`（1.0）。
  - **同 episode 直接对比（ep51–55，1200 步课时）**：

    | ep | 0.5（旧）：peak / viol | 1.0（新）：peak / viol |
    | :-- | :-- | :-- |
    | 51 | 826 kN / **0** | 1389.6 kN / 490 |
    | 52 | 858.9 kN / **0** | 1188.4 kN / 327 |
    | 53 | 880.9 kN / **0** | 1304.6 kN / 553 |
    | 54 | 842.9 kN / **0** | 1284.5 kN / 694 |
    | 55 | 906.0 kN / **0** | 1340.9 kN / 397 |
  - **后续趋势**：0.5 那次在 ep51 起连续 5 集 `viol 0`（峰值 ≤906 kN）；1.0 这次到 **ep150 仍未稳定**——`peak 1194–1468 kN`、`viol 92 – 3244`，且 episode reward 多次转负（ep121 −19 031、ep124 −22 851、ep126 **−47 781**）。
  - **对照组（同为 1.0 的 MPC 行）**：300 步窗口内 `桥接越权请求 455 → 0` 但 `reward / peak / viol / band / 末速` **几乎不变**（0.512→0.500、318 kN、0、100%、73.3→73.4）⇒ **放宽带宽给 MPC 带来的只是"名义上的接口保真"，没有实质性能收益**（完整剖面亦未见收益）。
  - ⇒ **裁定建议（待用户确认，见 `PROJECT_PIPELINE.md`）**：放宽 ① **得不偿失** —— MPC 侧无实质收益，RL 侧却因"可整幅撤销规则层 ED"而持续破 1000 kN 底线（与"规则层负责单车安全制动、RL 只管协同调制"的设计意图相冲突）。**倾向 ADR-024 覆盖 ADR-023 决策 1（带宽回 0.5）**，保留 ADR-023 的两项结构性改进（常量改为**派生** + metadata 新增 `ed_mod_coef` 键）；若要保住 1.0，则须先给安全层加"高车钩力下禁止 RL 撤销规则层 ED"的否决（工作量更大，即长久计划 #3 的预测式 safety filter）。
  - **留痕**：本节 + `PROJECT_PIPELINE.md`「[P2] …」；训练历史 CSV（两次）`adr021_…/results/train_history_dec_ad2_cp_seed0.csv` 与 `adr023_…/…`。
- **⛔ 消融可跑性裁定（不静默跳过）**：
  - ✅ 可跑（不需 ckpt）：**MPC 双层护盾**（`--mpc_inner_rule_cyclic`）—— MPC 侧唯一的可跑消融，排在两行 baseline 之后。**已跑完（2026-10-02，53km/36000 步，`n_seed=1`）**：

    | 配置 | reward | peak | viol | ATP事件 | AB步 | band | 末速 | 求解 fail |
    | :-- | :-- | :-- | :-- | :-- | :-- | :-- | :-- | :-- |
    | MPC 裸跑（`_adr023_mpc_53km`） | −813 642 | 848 kN | 0 | 3 937 431 | 8588 | 61.98% | 64.8 km/h | 1936 |
    | **MPC + 规则内层**（`_adr023_mpc_innerrule_53km`） | −3 635 838 | 950 kN | 0 | **622 391** | 4651 | **71.04%** | 40.5 km/h | **0** |
    - ⇒ 补规则内层护盾后 `solve fail 1936→0`、ATP 事件降 **6×**、band **+9pp** ⇒ **"NMPC 弱在缺内层规则护盾"这一判断成立**；但代价是**更保守**（末速 40.5 km/h 擦 `v_min=40` 下限、reward 更差）⇒ 即便补齐护盾，NMPC 仍**远弱于 D-Rule**（`+92 950 / band 97.28%`）。
    - 该结论测的是"MPC 是否缺护盾"，与 ckpt/带宽无关 ⇒ **不受 ADR-024 回退影响，结论可留用**（但数值产于 1.0 口径，标注之）。
    - 留痕：`outputs/logs/diagnostics/log_eval_adr023_mpc_innerrule_53km.txt`、`outputs/results/decompose/eval_decompose_mpc_ms36000_adr023_mpc_innerrule_53km.json`。
  - ⛔ **不可跑（须等新口径 ckpt）**：`--mask_lever ed|ab`（ED/AB 杠杆隔离）、D-RL 行本体、任何"需新口径 ckpt"的对照。原因：现有 ckpt 全部产于 `ed_mod_coef=0.5`，在 1.0 口径下**语义失效**（同一 ckpt 的调制幅度翻倍）⇒ 代用即造出训练/评估失配（`EXECUTION_RULES.md` 明令禁止）。
- **产出**：结果 JSON `outputs/results/decompose/eval_decompose_*_adr023_*.json`；日志 `outputs/logs/diagnostics/log_eval_adr023_*.txt`；计划 `PROJECT_PIPELINE.md`「[P2] 新动作口径（ADR-023）下的冒烟 / 其余两行 baseline / 可跑消融」。

### 回退-2026-10-02 · ED 调制带宽 1.0 → 0.5（ADR-024 落地）

- **决策依据**：见上「冒烟与基线-2026-10-02」的 A/B 诊断 + `DECISIONS.md` **ADR-024**。用户裁决原文："**回退 0.5 并重启（推荐）**"。
- **改动（先停训，PID 658 ep205/1400 elapsed 14h20m；闭包内行为性改动铁律）**：
  1. `src/controllers/multi_loco_controller.py` → `get_action_decomposed(ed_mod_coef: 1.0 → 0.5)` + docstring 标注 ADR-024（仍是全仓**唯一改点位**）。
  2. `src/evaluation/evaluate_decompose.py` → `ED_MOD_COEF` 仍为**派生**（自动跟随 0.5）；注释更新 ADR-023→024。
  3. `src/metadata.py` → `_resolve_ed_mod_coef` docstring 指向 ADR-024（派生逻辑不变，键仍为 `ed_mod_coef`）。
  4. 测试：`test_fleet_decompose.py`（`±1.0`→`±0.5`）；`test_metric_accounting.py::test_mpc_bridge_saturation_diag_is_recorded` 按 0.5 口径**重写为二态对照**（U=−0.4 期望 0.4 ≤ 带宽 ⇒ 不越界；U=−0.75 期望 0.75 > 带宽 ⇒ 越界且 AB 预触发）。
- **验证**：定向测试（`test_metric_accounting` / `test_fleet_decompose` / `test_nmpc_controller`）⇒ **39 passed**；`check_agents_links.py` ⇒ `[OK] AGENTS.md 引用一致性通过（ADR 编号越界检查 **25** 个已有 ADR）`；全量 `pytest tests/ -q` ⇒ **原有 244 项全绿（exit 0）**（本次回退仅改默认证 + 注释 + 测试断言，不新增用例）。
- **重启**：启动器 `scripts/launchers/launch_retrain_adr024_seed0.sh` → 新目录 `outputs/checkpoints/formation/adr024_1400ep_seed0`；日志 `outputs/logs/diagnostics/log_retrain_adr024_seed0_20261002.txt`。重启后须核对 `metadata.json` 的 `ed_mod_coef == 0.5`。
- **产物保留（不覆盖不删除）**：`adr021_1400ep_seed0`（0.5 旧结构）、`adr023_1400ep_seed0`（1.0 口径，已回退）；主表两行 baseline 的 `_adr023_*` 结果按"1.0 口径"存档，作 ADR-023 宽带对照证据。
- **待办**：待 `adr024` 新 ckpt 产出后，重跑主表 D-RL 行 + 两行 baseline（0.5 口径）+ ED/AB 杠杆隔离（`--mask_lever ed|ab`）。

<!-- 该文档整理/压缩于 2026-10-01 -->

### 停训-2026-10-03 · adr024 长训严重震荡的根因诊断与修复（ADR-025 落地）

- **触发**：用户裁定"**严重震荡就停了吧，先修复，别继续无意义的训练**"。
- **停训**：WSL PID 885（`run_training.py ... adr024_1400ep_seed0`，elapsed **1 天 6 小时**）→ `kill -INT` 优雅退出，日志末条为 `KeyboardInterrupt`（numpy `_wrapreduction`），最后回合 **ep341**；ckpt `mappo_fleet_ep340_dec_ad2_cp_seed0.pt` 保留。停训后 `ps` 无残留训练进程。
- **诊断数据（日志 `outputs/logs/diagnostics/log_retrain_adr024_seed0_20261002.txt`，682 条回合记录）**：

  | 区间 | 干净回合(viol=0) | 峰值>1200kN | `gap_min`<0 | 平均 `vstd` |
  | :-- | --: | --: | --: | --: |
  | ep 0-49 | 62% | 34% | 6% | 4,118 |
  | ep 50-99 | **22%** | 52% | 10% | **11,515** |
  | ep 150-199 | 60% | 30% | 4% | 10,530 |
  | ep 300-341 | **16%** | **63%** | 17% | 10,315 |

  - 最差回合：pk **1.85 MN**、viol 44,718、`gap_min` **-63 m**、reward **-39,380**（ep194）。
  - **阶跃点**：`value_norm.std` 在 ep50 前后由 ~4118 → ~11515 后**不再回落**，与干净率 62%→22% 同步。
  - 日志中 `KL早停: x > 0.0120` 遍布几乎每个回合。
- **根因（三条，详见 `DECISIONS.md` ADR-025）**：① 激励不对称（速度带 +6.0/步 vs 车钩力项 0.2、超限封顶 -12）；② 坏模式自我强化（极端负回报永久抬高 `ValueNorm` 尺度 → KL 早停常态化 → 退不出坏模式）；③ 动作权限窗口（AB 新增源否决的预测时域用"列长/波速≈6s"，与实测 **90.1s** 力建立滞后混同 ⇒ 拦不住滞后峰值）。
- **修复（ADR-025，三项最小改动）**：`coupler_veto_lag_s=90.0`（否决 horizon 改按滞后；需 ≥max(30s,半时域) 历史才启用预测式）；`ValueNorm(decay=0.98)` 指数遗忘；KL 早停判据 `mean((Δlogp)²)` → 标准 `mean(Δlogp)`。
- **验证**：
  - 全量 `pytest tests/ -q` ⇒ **244 passed（exit 0）**。
  - 否决行为差异（合成峰值 100→500 kN @1000 N/步，当前 500 kN 未达反应式 600 kN 阈）：**旧口径 veto=False / 新口径 veto=True**。
  - 沙盒冒烟（`--episodes 2`，三个输出目录重定向到 `outputs/smoke/_smoke/slice16k/`）：**通过**。配置正常加载（`simcase=official`，无"调试工况禁入训练"断言触发）；BC 热启动 27000 条/30 epochs；2 回合 **viol=0**、pkCpl **641 / 745 kN**（<1000）、`gap_min` **179 / 62 m**（>0）；~77 s/回合（500 步窗口）。KL 判据出现**负值**（-0.018 / -0.030），符合新标准估计的行为预期。
- **沙盒纪律**：该剖面/配置**只作训练方法迭代**，结果**不得进正文主表**（ADR-017 §3：短训长验方向错误）；沙盒**不缩短单集窗口**（否则 90s 滞后峰值不出现），加速仅来自更短的完整剖面评估。
- **留痕**：`DECISIONS.md` ADR-025；配置文件 `configs/experiments/_debug_train_method_slice16k.yaml`；剖面 `src/train_dynamics/grade_profile.py::profile_shuozhou_real_53km_slice16k`。

#### 沙盒结果-2026-10-04 · ADR-025 修复的 80 ep 验证（`shuozhou_real_53km_slice16k`）

- **运行**：`scripts/launchers/launch_debug_slice16k_seed0.sh` → `outputs/checkpoints/formation/_debug_train_method_slice16k/`；日志 `outputs/logs/diagnostics/log_debug_slice16k_adr025_seed0_20261003.txt`；端到端 **228.5 min / 80 ep**。
- **训练窗口（1200 步短窗）逐 10 ep**（干净率 = viol=0 回合占比）：

  | ep | 干净率 | 平均峰值 | 最大峰值 | vstd |
  | :-- | --: | --: | --: | --: |
  | 0-9 | 100% | 644 kN | 745 | 877 |
  | 10-19 | 100% | 790 kN | 915 | 2,440 |
  | 20-29 | 100% | 837 kN | 978 | 3,992 |
  | 30-39 | **70%** | 923 kN | 1,101 | 3,547 |
  | 40-49 | 100% | 761 kN | 897 | 3,189 |
  | 50-59 | 100% | 626 kN | 773 | 3,076 |
  | 60-69 | 100% | 632 kN | 775 | 3,173 |
  | 70-79 | 100% | 630 kN | 807 | 3,450 |

  - **全局：干净率 96.3%（155/161）、峰值>1200kN 0%、`gap_min`<0 0%、最大峰值 1,101 kN、平均 vstd 2,971（稳定，无阶跃爆）。**
  - 对照旧 run（adr024）：干净率 62%→16%、峰值>1200kN 达 63%、`gap_min`<0 达 17%、vstd 阶跃到 11,515 不回落。**"越练越差"与"暴力 AB 爆发"均消失**；ep30-39 的小回落于 ep40 起自动恢复，平均峰值持续下行。
- **完整剖面评估（12000 步 = 15.7km 全程）**：

  | ep | reward | 峰值 | 破线步 | band | 末速 | 达标 |
  | :-- | --: | --: | --: | --: | --: | :-- |
  | 40 | −22 253 | 1221 kN | 997 | 100.0% | 41.0 km/h | ✗ |
  | **80** | **+10 758** | **968 kN** | **0** | 92.6% | 48.7 km/h | **✓** |

  - ⇒ ep40→ep80 峰值 **1221→968 kN**、破线 **997→0**，末速回到带内 ⇒ **完整剖面达标**（`best` ckpt 已按长程评估保存）。
  - ⚠️ **短窗 vs 全程落差仍在**：训练窗口峰值仅 ~900 kN，全程 ep40 却到 1221 kN（记忆中的"短窗评估低估"），故**必须靠长程评估判优**（本 run 的 `long_eval` 每 40 ep）。
- **独立复算（`evaluate_decompose.py`，非训练内 `long_eval`）**：`--mode decompose_m1 --checkpoint .../mappo_fleet_best_dec_ad2_cp_seed0.pt --grade shuozhou_real_53km_slice16k --max_steps 12000 --n_seed 1`：

  | peakCoupler | viol | band | 末速 | 列距误差(均/峰) | 最小列距 | 追尾 | ATP事件 | AB步 | meanED |
  | --: | --: | --: | --: | --: | --: | --: | --: | --: | --: |
  | **880 kN** | **0** | 93.12% | 49.3 km/h | 80.3 / 357.2 m | 19.0 m | 0 | 17 666 | 1 733 | 0.336 |

  - ⇒ 与训练内 `long_eval`（peak 968 / viol 0 / band 92.6% / 末速 48.7）**一致**：车钩力守住 ≤1000 kN、破线 0。**两处独立复算互证。**
  - 结果 JSON：`outputs/results/decompose/eval_decompose_decompose_m1_ms12000_sandbox_best_ep80_slice16k.json`。
- **结论**：ADR-025 三项修复**有效**——先消除震荡/爆发，再在完整剖面上把车钩力压回 ≤1000 kN。
- **未决 / 下一步**：① 沙盒为 15.7km 切片，**不能替代 53km 主口径**（更长累计下坡更难）；须把该 recipe 回迁 `formation_ed_ab_1plus1` 主配置跑 1400 ep 复核；② KL 早停现多在 epoch 1-4 触发（更新偏少），若主口径学习过慢可再调 `target_kl`；③ 沙盒结果是 debug 证据，**不得进正文主表**（ADR-017 §3）。

#### 负间距根因-2026-10-04 · ATP 制动被车钩力缓和放掉（ADR-027 落地）

- **触发**：用户质疑"负间距=追尾？ATP 干什么吃的"、"换 CTCS 会改善吗"。
- **现象（v3 间距奖励沙盒 `_debug_gapv3_slice16k`，80 ep）**：ep21–24 `gap_min` 64/155/147/54 m（v3 见效），但 **ep25 仍 `gap_min −53 m` + 单回合 R **−9,185,419** + vstd **17,105**（阶跃）** ⇒ v3 降低负间距频率、**未根除**，与 ADR-025「坏模式自我强化」同签名。
- **根因（代码级）**：`src/safety_layer.py` `protect()` 原施加顺序 = **ETCS(规则0) → 反应式超速(规则1) → 车钩力缓和(规则2) → 间距(规则3)**。规则 2 在 `coupler_override='release'`（fleet 子环境默认）下把制动**钳回 0**，且它在 ETCS **之后** ⇒ **把 ATP 刚下的制动放掉**。自毁闭环：
  > 后列刹不住逼近前列 → 列间受压车钩破 1000 kN → 车钩力规则 release 放掉 ETCS 电制动（AB 紧急建立 ~10 s）→ 后列在下坡失去即时制动继续下探 ⇒ **间距穿负**。
- **澄清**：CTCS-2/3 与 ETCS 的 ATP 同族（目标距离制动曲线 + SBI/EBI），换制式不换机制；问题在**本实现规则优先级**，不在制式。
- **修复（ADR-027，最小改动）**：施加顺序改为 **A 车钩力缓和 → B 间距防挤压 → C 反应式超速 → D ETCS**（`np.minimum` 最后覆盖 ⇒ ETCS 制动不可被放掉）。规则语义/阈值/`coupler_override` 行为不变。
- **验证（已做）**：
  - 定向回归 `test_safety_atp_brake_not_released_by_coupler_rule`（ETCS EBI + 车钩 1200 kN + release ⇒ 紧急制动保留 `≤ −0.9`）；全量 `tests/` **245 passed**。
  - 独立评估（**旧 v3 ep20 ckpt + 修复后安全层**，`--grade shuozhou_real_53km_slice16k --max_steps 12000 --n_seed 1`）：

    | peakCoupler | viol | band | 末速 | 列距误差(均/峰) | 最小列距 | 追尾 |
    | --: | --: | --: | --: | --: | --: | --: |
    | 901 kN | 0 | 84.98% | 49.9 km/h | 101.1 / 312.8 m | **72.2 m** | **0 步** |

  - JSON：`outputs/results/decompose/eval_decompose_decompose_m1_ms12000_atpfixcheck.json`。
  - ⚠️ 该评估是**同一 ckpt 换安全层**的定向检查（非 v3 训练内 A/B），负间距为**整集最小值的偶发事件**，确定性单跑未必复现 ⇒ **决定性证据须看沙盒重跑** `_debug_gapv3_atpfix_slice16k`（同配置同 seed）逐 ep 的 `gap_min<0` 计数与 vstd 轨迹。
- **沙盒重跑**：`scripts/launchers/launch_debug_gapv3_atpfix_seed0.sh` → `outputs/checkpoints/formation/_debug_gapv3_atpfix_slice16k/`；日志 `outputs/logs/diagnostics/log_debug_gapv3_atpfix_slice16k_seed0_20261004.txt`。判据 = `gap_min<0` 归零、vstd 无阶跃、峰值/band/最小列距三项 ≥ 规则基线。
- **留痕**：`DECISIONS.md` ADR-027；`src/safety_layer.py` `protect()`；`tests/test_safety_layer.py`。

#### 负间距根因-2026-10-04 · 修订：原假设被推翻 + 真实"放大器"（ADR-028）

- **决定性问题**：修复版沙盒 `_debug_gapv3_atpfix_slice16k`（同配置同 seed + 新安全层）跑到 ep45，**ep20/ep25 与修复前逐位一致**：

  | 回合 | 修复前 | 修复后 |
  | --- | --- | --- |
  | ep25 | `R −9185419 \| pkCpl 880kN \| loss 1.743 \| vloss 1.742 \| vstd 17106 \| gap_min −53m` | 逐位相同 |
  | ep20 | `R −2961 \| pkCpl 846kN \| loss 3.421 \| vloss 3.411` | 逐位相同 |

- **推论**：负间距轨迹**从未走到"车钩力规则放掉 ATP 制动"的分支**（否则重排必改变动作）⇒ 上文"自毁闭环"根因**不成立**；安全层规则重排**保留**（ATP 优先级语义更正确、零回归），但**不解决负间距**。
- **真实"放大器"根因（ADR-028）**：`_atp_safe_gap` 在穿透（`actual_gap≤0`）时**恒返 0.0** ⇒ 间距危险项 `over=(d_safe−gap)/max(d_safe,1.0)` 分母塌缩为 **1.0 m**，`over` 退化成"穿透**米数**" ⇒ `−60·over²` 爆炸（−53 m ⇒ **≈−1.7e5/步**）⇒ 单集 `R≈−9.18e6`（与 ~54 步穿透量级吻合）⇒ValueNorm `vstd` 抬到 17k，ep26–45 仅缓降到 ~10.5k。
- **修复（ADR-028，最小改动）**：危险项分母加固定参考尺度 `GAP_DANGER_REF_M=100.0`（`denom = d_safe if d_safe>1.0 else GAP_DANGER_REF_M`）⇒ 穿透时 `over` 无量纲、量级有界（−53 m ⇒ −16.9/步）；非穿透路径行为逐位不变。
- **验证（已做）**：`tests/test_train_fleet_env.py::test_fleet_gap_danger_penalty_bounded_on_penetration`（两对 53 m 穿透 ⇒ `reward>−3000`；修复前 ≈−3.4e5）。
- **仍未决**：负间距**本身**（虚拟穿透）为何发生——需加载 ckpt 复现 ep20/ep25，逐步记录 ETCS 是否介入 / 制动是否被放掉 / 速度-坡度-间距趋势（ADR-027 权限假设已排除）。
- **证据边界**：以上均为**沙盒**（`slice16k`）观测，按 ADR-017 §3 **不进正文主表**；训练内 A/B 结论仍待重跑。

#### 负间距根因-2026-10-04 · 定案：牵引绕过安全层（ADR-029）

- **方法**：定向压测探针 `scripts/tmp_probe_gap.py`（**临时脚本，用后已删**；单列 decompose，**合成更慢前列**匀速前进，初始 gap0=300 m，−12‰ 陡坡，80→54 km/h，3000 步）。先 P1 证伪"ETCS 模型乐观"，再 P2 以三档后列动作对照，定位穿透因子。
- **P1 证伪"模型乐观"**：仿真真实紧急制动停止距离 **769.7 m** vs ETCS 模型 `braking_distance` **977.2 m**（仿真/模型 = **0.788**，模型比现实**保守 ~27%**）⇒ **EBI 并非"触发过晚"**，问题不在模型。
- **P2 决定性对照（唯一变量 = 后列动作）**：

  | 后列动作 | 最小间距（修复前） | 穿透 | 最小间距（修复后） | 穿透 |
  | --- | --: | :--: | --: | :--: |
  | 全牵引 `[-1,0]` | **−65.3 m** | **是** | **+75.4 m** | **否** |
  | 惰行 `[0,0]` | +82.5 m | 否 | +82.5 m | 否 |
  | 全制动 `[1,-1]` | +192.2 m | 否 | +184.4 m | 否 |

  ⇒ **牵引是唯一穿透因子**；全牵引档 EBI 触发 2316/3000 步却持续下探 ⇒ 安全层**压不住牵引**。
- **根因（代码级，`src/environments/train_env.py` `_step_decomposed`）**：原 `proj_throttle` 把**牵引映射为 0**（`-max(act,0)`）⇒ 牵引从不进入 `SafetyLayer`（约定 `>0`=牵引）。规则 A(车钩力缓和)/B(间距防挤压)/D(ETCS EBI) 声称的"抑制/禁止加速"对牵引**全部落空**：EBI 触发仍满牵引，"边牵引边紧急制动"，下坡重力+牵引共同加速 ⇒ 虚耦合穿透。次因：`step_vehicles_ed_ab` 中 `ab_sources` 优先级高于 `ab_command`（`train.py:556-559`）⇒ EBI 紧急升级被动作 AB 源**静默丢弃**。
- **修复（ADR-029，最小改动 3 处）**：① `proj_throttle` 带符号投影（牵引以正号入安全层，使规则可真正取消牵引）；② EBI 触发时清空 `ab_sources`，只发车头 `ab_command=EMERGENCY`；③ 安全层修正结果回写 `throttle`/`ed_throttle`（牵引被压 ≤0 时 `throttle` 同步归零）。
- **验证（已做）**：新回归 `tests/test_fleet_decompose.py::test_etcs_ebi_*` **2 passed**；探针重跑全牵引档 **−65.3 → +75.4 m**（表见上）；全量 `tests/` **248 passed**。
- **刻意不做（延后）**：EBI 迟滞 latch、EBI 强制 ED 打满（现只封顶不加深）——待沙盒重跑判据决定。
- **证据边界**：探针为**单列 decompose + 合成前列**的定向压测，非训练轨迹；AD-029 的**训练级**效果仍须沙盒重跑 `gap_min<0` 计数验证，按 ADR-017 §3 **不进正文主表**。
- **留痕**：`DECISIONS.md` ADR-029；`src/environments/train_env.py` `_step_decomposed`；`tests/test_fleet_decompose.py`。

#### 负间距根因-2026-10-04 · 训练级确认（ADR-029 沙盒 v5）

- **运行**：`scripts/launchers/launch_debug_gapv5_adr029_seed0.sh` → `_debug_gapv5_adr029_slice16k`（与 v3/v4 **同配置同 seed 0**）；日志 `outputs/logs/diagnostics/log_debug_gapv5_adr029_slice16k_seed0_20261004.txt`；**80 ep / 183.8 min**。
- **结果（三项判据）**：
  1. **穿透根除**：全 80 集 **`gap_min<0` = 0 次**（最小 46 m @ep33）。同 seed 对照：**ep20 −7 → +166 m；ep25 −53 → +143 m**。
  2. **vstd 不中毒**：全程 **819→~2,105**，无 1e4+ 阶跃（v3 曾 17,105）。
  3. **性能**：best reward **9,015.77**、末段平均车钩力峰值 **859.9 kN**、ep80 `pkCpl 1045kN / viol 1 / gap_min 105m`。
- **结论**：ADR-029 **在训练级确认根除虚拟穿透**。**遗留（另案）**：车钩力零星破线（ep31 1017kN/viol2、ep80 1045kN/viol1）属车钩力控制精度，与穿透不同轴。
- **证据边界**：沙盒（`slice16k`）方法迭代，按 ADR-017 §3 不进正文主表；主口径 53km/1400ep 复核待另跑。

### 路线覆盖 / "看不全路"-2026-10-06 · 调研与诊断计划

**问题**：53km 主剖面训练，但每集训练窗口 = curriculum ≤1200 步（`curriculum: 500:0,1000:10,1200:20`），dt=0.1 ⇒ 单集仅 120 s ≈ **只走 2–3 km**；且 `reset()` 起点**固定**（`_base_pos`，领航列在原点；`start_offset_m` 方案已于 2026-08-20 移除）⇒ 训练只见前段。评估却跑完整剖面（`long_eval_steps: 36000`）⇒ 后段坡道落在训练状态分布外（OOD）。

**立场（ADR-017，SSOT）**：训练=短窗口、评估=独立完整剖面是**正确范式**，不是缺陷。"训练看全路"= 拉长 on-policy rollout = 历史反复失败之路（自举误差滚雪球）。正确解 = **在分布/信息上覆盖全路**，非拉长窗口。

**历次尝试结果**（详见 `PROJECT_PIPELINE.md`）：
| 尝试 | 结果 |
|---|---|
| 300 步短程训 → 3000 步全程评估 | 泛化失败（seed1 全程追尾 398、车钩力超限）；3 seed 中 1/3 失败，已写入 Limitations |
| curriculum `300-1000-3000` 渐进出步 | 阶段切换正确、缓解短程过拟合；后上限收到 1200（ADR-017） |
| n_env=4 × 恒定 2000 步 × 44ep（无渐进） | **Step1 FAIL**：首 10ep 全面破线（peak 1476–1827kN、viol 494–1474），~12h |
| 上者 + BC warm_start | reward 侧修复（best +14558、8 集 6 正），车钩力仍破线（peak 1079–1650） |
| 长程 9000+ 步 | seed1 灾难（reward 崩、发散） |
| slice16k + curriculum ≤1200 | 稳定（viol=0、pkCpl≤839kN） |

⇒ **"让训练看更长的路"（3000/9000/36000 步）几乎全失败**；活下来的是"短窗口 + 渐进出步"。

**文献/社区方法**（"短窗口训、长线路泛化"，本次检索）：
| 方法 | 代表 | 作用 | 成本 |
|---|---|---|---|
| 起点/初态随机化（diverse resets） | OmniReset 2026（明指"重访同一窄区域致性能饱和"，可替代课程）；Schäfer 2025 | 短窗口不变、**训练分布覆盖全路** | 低 |
| 路线/难度课程 | CORAL 2026（逐步加长路线，单城→7 未见城 68–98%）；R2R-SAC 2026 | 渐进扩覆盖 | 中 |
| 域随机化 | Yu 2024 Robotica | 鲁棒泛化 | 低 |
| 记忆策略（LSTM/GRU） | **Guo2025 LSTM-MAPPO（本项目文献库）** | 把"看不全"当 POMDP 用记忆补 | 中高 |
| 前瞻观测（坡度/限速预览） | 与 ATP/ETCS 同构 | 直接给"前方的路"，无需经历 | 低–中 |

**当前缺口**：本项目策略 = MLP、固定起点、obs 无前瞻坡度 ⇒ 三类覆盖（经验/信息/记忆）皆缺。最对症 + 最省 = **起点随机化 + 前瞻观测**；LSTM 为重备选。

**诊断计划（分层）**：
- **L1（本次，分钟级，零训练）**：量化固定起点短窗口 vs 完整剖面评估的**路线/坡度覆盖差**（OOD 步占比），判断值不值得改。
- **L2（小时级）**：`slice16k` 沙盒 A/B（起点随机化 on/off，80ep ≈3h），`long_eval` 完整剖面比 峰值/viol/band/末速。
- **L3（仅 L2 不足时）**：前瞻观测 / LSTM。
- 纪律：均属沙盒，按 ADR-017 §3 不进正文主表。

#### L1 结果（2026-10-06，已做，决定性）

脚本（主剖面 `shuozhou_real_53km`，3 列，规则基线零动作；该一次性预检脚本已随结论清理）：
- 主剖面：长 **53,206 m**，坡度 **16 个 bin（−12.0 ~ −1.2‰）**。
- **训练窗口**（固定起点，1200 步）：位置跨度 **5,873 m = 全程 11.0%**；队首坡度 **仅 1 个 bin（−1.5‰）**；速度 61.6–65.0 km/h。
- **完整剖面评估**（36,000 步）：位置 **0→56,562 m**；队首坡度 **15 个 bin（−11.5 ~ −1.0‰）**；速度 41.2–81.4 km/h。
- **OOD：评估步 83.9% / 全线路 94.2% 的坡度落在训练从未访问的区间**。

⇒ **定案**：固定起点 + 1200 步窗口让训练**完全落在 −1.5‰ 缓坡段，从未经历 −12‰ 陡下坡（论文核心场景）**；训练场景与研究对象**错位**。这是"泛化优化"之上的**立论级问题**，且卡在重训之前（不修则重训白跑）。

**修复方向（本次执行）**：起点随机化（短窗口不变，训练分布覆盖全路）。L2 = `slice16k` 沙盒 A/B（on/off）验证。

#### L1-b 更正（2026-10-06）——随机起点后的"残余 OOD 65%"是口径污染，真实值 ≈4–5%

- **背景**：L1 预检的运行日志里，随机起点模式曾报"评估步 OOD **65.0%** / 全线路 OOD 21.0%"，一度被当作"残余覆盖缺口"。复核后判定该数字**不成立**。
- **污染来源（两条，均已代码级确认）**：
  1. **eval 参照不同源**：L1 脚本的"完整剖面评估"复用了同一个 env；随机模式下 `reset()` 会**再随机起点**（`train_fleet_env.py:391-394`：`_start_rand is not None and not eval_mode`）⇒ 两模式的 eval 轨迹本就不是同一条（固定 `−3785→55554`；随机 `25782→85044`）。后者起点在 25.8 km、终点 85 km ⇒ **约 54% 的步落在剖面之外**。
  2. **越界步 grade 被 clamp 成未访问 bin**：终点后 `grade_at` 返回末段 **−11.4‰**（`grade_profile.py:299`）→ bin **−11.5**，而当时训练支持集下界仅 **−11.0‰** ⇒ **所有越界步被判 OOD**。两条叠加 = 65%。
- **正确口径实测**（`scripts/tmp_ood_attribution.py`，用 `eval_mode=True` 恒定基准起点重跑）：
  | 口径 | 固定起点（L1 原值） | 随机起点（正确重算） |
  |---|---|---|
  | 训练访问坡度 bin 数 | 1（−1.5‰） | **11**（−12.0 ~ −1.5‰） |
  | 评估步 OOD（全轨迹） | 83.9% | **4.7%** |
  | 评估步 OOD（仅剖面内） | — | **5.0%** |
  | 全线路 OOD（每 100 m） | 94.2% | **4.1%** |
  - 正确 eval 轨迹：loco `2→55554 m`，剖面外步占比仅 **4.8%**。
  - **未覆盖坡段仅 5 个短变坡 bin**：−8.5‰(0.8%)、−5.5‰(0.4%)、−2.5‰(0.4%)、−2.0‰(0.4%)、−1.0‰(2.3%)，合计里程 **4.3%**。
- **度量敏感点（诚实标注）**：visited 集定义不唯一——L1 用"3 列车 `grade[0]` 的 **max**（最缓和）"，本脚本用"**领航列** `grade[0]`"。下坡时领航列最陡，故本脚本的 11 bin ⊃ 更陡区间；这解释了 21%→4.1% 的一部分差异。**建议**：把该诊断的 visited 定义**规范化**（如"全部机车 grade 的并集"）后再引用，避免口径漂移。
- **口径规范化（定稿 2026-10-07）**：visited 集**统一取「领航列（train 0）领航机车 `grade[0]` 的坡度 bin」**，训练侧对全部 rollout 步取并集、评估侧按同口径计 OOD。理由 = **必须与评估指标的采样单元一致**（评估 OOD 也是取 train0 领航机车坡度），换任何别的采样单元（如 3 列车 max、全机车并集）都会引入 not-comparable 的偏差。**据此 L1 的"8 bin / 21%"口径作废**（max-over-trains ≠ 评估采样单元）；**引用一律用本口径的 11 bin / 4.1%**。
- **结论**：**起点随机化在分布层基本消除路线 OOD**（评估步 4–5%，且残余只是零星短过渡坡段）；固定起点才是问题根源（eval OOD 83.9% 为真实值）。
- **证据边界**：零训练的诊断（规则基线零动作），按 ADR-017 §3 不进正文主表；最终以 L2 真训练 A/B 为准。

### 车钩力"零星破线"-2026-10-06 · 根因调查（另案）

- **触发**：ADR-029 训练级确认的遗留项（v5 沙盒 ep31 1017 kN/viol 2、ep80 1045 kN/viol 1），需判"是确定性策略缺陷还是探索瞬态"。
- **数据来源**：`_debug_gapv5_adr029_slice16k/results/train_history_dec_ad2_cp_seed0.csv`（逐集 `peak_coupler_kN`/`violations`）。
- **训练窗破线分布**：80 集中 **12 集破线、共 164 车厢·步**；**ep31–55 占 161/164（98%）**（峰：ep37 1136 kN/80、ep47 1050 kN/34、ep55 1105 kN/30）；**ep57 后仅 3 次单步微超**（ep62 1111 kN/1、ep73 1053 kN/1、ep80 1045 kN/1，≤11%）。**与 `vstd` 无关**：vstd 在 ep27–80 全程高位（≈1800–2100），破线却只在 ep31–55 后基本消失 ⇒ 非 value 发散所致。
- **关键判别（代码级）**：训练 rollout 走 `select_actions(flat)`（**随机采样**，`src/trainer/interaction.py:83`），long_eval/全部评估走 `deterministic=True`（`src/trainer/train_runner.py:440`）⇒ **训练窗 `viol` 是探索态指标**，含随机动作噪声；部署态 = 确定性策略。
- **确定性长程对照**：
  - 主剖面 53 km（`adr023_1400ep_seed0/results/long_eval_best.json`）：**ep150 peak 956 kN / viol 0 / 末速 68.0 km/h（达标）** ⇒ 确定性策略在**完整 53 km** 上可守线（注：同 run 的**训练窗** ep150 仍见 peak 1194–1468 kN/viol 92–3244，正是探索态 vs 确定性态之差）。
  - v5 沙盒 `slice16k` 的 long_eval：**ep40 peak 914 kN / viol 0**（末速 84.7 km/h 出带 ⇒ 不达标）；**ep80 peak 1815 kN / viol 7788 / band 37.6% / 末速 17.4 km/h（灾难）**。
- **结论（诚实版）**：
  1. 训练窗"零星破线"**主要为随机探索瞬态**，非确定性策略的稳定缺陷（主剖面 ep150 达标 + 训练/评估动作模式差异共同支持）。
  2. **但长程稳定性依权重而定**：v5 ep80 短窗看似正常（`pkCpl 1045 kN/viol 1`）却长程灾难 ⇒ 再次印证"**短窗 reward 最优 ≠ 长程安全**"（诊断-2026-09-22），选权重必须看 long_eval。
  3. 机制方向沿用 ADR-021 断点：**AB 新增源的时空叠加**（同刻多源 / 集中列尾）+ 安全层对 RL 的 AB 源**无"减"权限**（只增不减）。
- **未验证（hypothesis，勿当结论）**：v5 ep80 长程崩是否与 ADR-029"EBI 触发清空 `ab_sources`"引发的连续紧急制动级联有关（band 37.6% + 末速 17.4 km/h 提示安全层重度介入）——需带 instrument 的 eval 复核（记录 per-coupler 时程 + EBI 事件计数）。
- **证据边界**：均为沙盒（`slice16k`）与既有 JSON/CSV 的归因，未新跑仿真；按 ADR-017 §3 **不进正文主表**。

### L2 路线覆盖 A/B 终局-2026-10-06 · 起点随机化有效（真训练对照）

- **实验**：`slice16k` 沙盒，两臂唯一差异 = `env_cfg.start_randomization: {enabled: true, seed: 0}`（OFF=固定起点 / ON=起点随机化），其余逐行一致；`seed 0`，80 ep；分析器 `scripts/tmp_analyze_routecov_ab.py`。
- **long_eval（完整剖面·确定性策略）**：

  | 臂 | ep | reward | peak_kN | viol | band | 末速 | 达标 |
  |---|---|---|---|---|---|---|---|
  | OFF | 40 | +57245 | 914 | 0 | 74.4% | 84.7 | n |
  | OFF | 80 | **−158308** | **1815** | **7788** | 37.6% | 17.4 | n |
  | ON | 40 | +67065 | 795 | 0 | 86.1% | 53.6 | **Y** |
  | ON | 80 | +56399 | 832 | 0 | 86.2% | 51.8 | **Y** |

- **判据（ON 相对 OFF）**：**long_eval 达标次数 ON 2/2 vs OFF 0/2**（决定性）；OFF ep80 出现长程灾难（1815 kN / viol 7788 / 末速 17.4），ON 同点仍达标（832 kN / viol 0 / 末速 51.8）。
- **训练态（per-episode CSV）**：reward ON 占优（best +9889 vs +9016，末 10 集均值 +7216 vs +6073）；破线集数 ON 19 > OFF 12、maxPeak ON 1755 > OFF 1151、总 viol ON 23136 > OFF 164。**这是探索态指标**（训练走随机采样，`interaction.py:83`），随机起点把训练分布摊到全路，探索期撞到更陡坡段的破线增多属**分布覆盖的副产品**，与部署态安全性无关（long_eval 已证）。
- **`gap_min` 未取到**：两臂 CSV 前段为 4 列行、后段 8 列（`artifacts.save_history` 与 `logger.log_episode` 双写者），分析器仅收 8 列行 ⇒ 显示 n/a，待修 CSV 写者后补。
- **结论**：**起点随机化有效**（分布层：评估 OOD 83.9%→4.7%；策略层：long_eval 0/2→2/2 达标且修掉 ep80 长程灾难）⇒ **接入主配置 `formation_ed_ab_3train_1plus1.yaml` 再重训**。
- **证据边界**：沙盒 80 ep、单 seed，按 ADR-017 §3 **不进正文主表**；最终以接入主配置后的完整多 seed 重训为准。

### 诊断-2026-10-07-「训练效果不好」根因（routecov 主配置 seed0 全量复查）

- **被测对象**：`outputs/checkpoints/formation/routecov_1400ep_seed0_par`（主 YAML + 起点随机化 ON + `n_env_parallel` + reward `v4-atp-aligned-gap`），ckpt ep50/ep100/ep150/ep200/ep240；训练态 CSV 两表；离线全剖面（53km / 36000 步 / DI=10 / 确定性 / seed0）评估 JSON。
- **判据（一律一手）**：ckpt 内嵌 `metadata`、`train_history_*.csv`、`train_loss_*.csv`、`results/decompose/eval_decompose_*.json`，以及**直接前向 ckpt 权重实测 log_std/σ**（探针 `tmp_probe_ckpt.py`，用后即删）。

#### 一、结论（一句话）

**主 blocker = 训练地平线（1200 步 = 120 s）短于 AB 最小充风时间（`ab_min_refill_s = 222 s`）**：循环制动"充风→二次制动"的车钩力峰值在**单条训练回合的物理时域内根本不可能出现**，故 RL 拿不到针对它的梯度；该峰值只在完整 53 km 评估里暴露（1161 kN > 1000），属**结构性不可学**。**次病 = 探索噪声失控**（ED 通道 `log_std` 涨到钳位上限 2.0，σ=7.39 ≫ 动作半幅 1.0），使中后期 on-policy 数据被噪声淹没、训练窗 reward 自 ep23 起再未刷新。

#### 二、断点 1｜危险事件不在训练回合的物理时域内（**主干，决定性**）

- 训练地平线由 `curriculum: 500:0,1000:10,1200:20` 决定（`_parse_curriculum`→`_resolve_horizon`），**ep≥20 后恒为 1200 步**；`dt=0.1` ⇒ **单回合物理时域 = 120 s**。
- AB 最小充风时间 **`ab_min_refill_s = 222.0 s`**（`train_fleet_env.py:179`；出处张二田 S6，`VALIDATION_BASELINE:201`）。**120 s < 222 s ⇒ 一个训练回合内连"一次完整充风"都完成不了，二次制动的车钩力峰值必在回合外。**
- 一手数值对照（同 ckpt）：

  | ckpt | 训练窗 peak（CSV） | 训练窗 viol | 全 53km peak（评估 JSON） | 全 53km viol |
  |---|---|---|---|---|
  | ep50 | 864.0 kN | 0 | **1154.9 kN** | **432** |
  | ep240 | 716.6 kN | 0 | **1161.1 kN** | **463** |

  ⇒ **训练窗内"干净"（≤864 kN / viol 0），全剖面却稳定破线（≈1155–1161 kN）**：越限量（>1000 kN）**整体落在训练窗之外**。策略在窗内学到的"不变量"与全剖面的失稳点不是同一件事。
- 佐证（已在库、同结论）：`train_runner.py:456-457` 的 2026-09-22 注记「训练窗口 1200 步≈2.4km 的 reward 最优 ≠ 完整剖面评估最优；短视激进权重长程崩」。
- **达标从未达成（一手）**：ep50/100/150/200/240 五个 ckpt 的 `metadata.long_eval_best` 全为 `{'reward': -inf, 'ep': 0}` ⇒ 全程 53 km 达标判据（`viol==0 ∧ peak≤1000kN ∧ 末速带内`，`train_runner.py:504`）**一次都没满足**。
- **诚实边界**：训练窗 CSV 中确有零星 >1000 kN 集（ep76=1364、ep91=1449、ep93=1522），集中在 ep54–94 / ep171–184 且伴随巨大 viol —— 那是"短时标/初始暂态"型破线，**不是** 222 s 时标的循环制动峰；ep240 这两类都被压到窗内不出现，全剖面却仍破线 ⇒ 与"长时标峰不可学"一致（此段为**推断**，已与一手数值相容）。

#### 三、断点 2｜探索噪声失控（ED 通道 σ → 钳位上限；次病，实测）

- 直接对 ckpt 权重前向实测（`reset` 后同一 obs），逐集趋势：

  | ep | σ_ED | σ_AB | 实测 entropy（nats） |
  |---|---|---|---|
  | 20 | 0.234 | 0.426 | 0.557 |
  | 50 | 0.248 | 0.463 | 0.691 |
  | 100 | 0.341 | 0.676 | 1.349 |
  | 150 | 0.762 | 2.402 | 3.423 |
  | 200 | 5.643 | 2.219 | 5.314 |
  | 240 | **7.389（=钳位上限 ln_std=2.0）** | 2.561 | 5.780（理论上限 6.84） |

  ⇒ ED 通道 `log_std` **单调涨到 clamp 上限 2.0**，σ=7.39 而动作域仅 [-1,1]（**动作标准差 = 动作半幅的 7.4 倍**，约 89% 采样被裁到 ±1）⇒ 训练 rollout 的 ED 指令 ≈ 随机 ±1。
- 机制（代码事实）：`mappo_agent.py:133` 只把 `log_std` 钳到 `[-4, 2]`；`entropy_coef=0.005` **恒定、无退火**（YAML 注释明写系 0.002→0.005 故意调高"提熵促探索"）；且熵按**无界高斯** `N(mean,σ)` 计算（`mappo_agent.py:521`），而动作在 `select_actions` 里被 `clamp(-1,1)`（`:307`）⇒ σ 一旦饱和，再增大仍"免费"涨熵，唯一上界就是那个 clamp。
- 与训练结果一致：训练窗 `best_reward` **冻结在 ep23 的 10603.56**，此后 220 集再未刷新；窗内 reward 从 ep20–50 的 ~9000 降到 ep200–245 的 ~2000（多次为负）。
- **seed 相关（不是必然律）**：`routecov_seed1_par` 熵稳定（ep20–200 在 0.35–0.90）、`seed2` 部分上涨（ep200=6.43）、`seed0` 失控 ⇒ 属"不稳定发散"而非配置必炸。

#### 四、次要与计量问题

1. **训练-评估不同参（harness，已于 2026-10-07 修）**：`evaluate_decompose.make_env` 原硬编码 `target_speed: 20.0`，而训练 `env_cfg` **不含该键** ⇒ 训练实走 env 默认 `(v_min+v_max)/2 = 16.67 m/s`。该键同时定 obs 速度误差参考与动态目标列距（183.3 m vs 200 m）。修后待重测（离线结果在本项修复前产出，属共变量差异）。
2. **`num_updates` 计数 bug（计量）**：`mappo_agent.py:617` 用 `epochs * floor(len/batch)`，而内层实际迭代是 `ceil`（`range(0,len,batch)`）⇒ 上报 `entropy/value_loss/policy_loss` 被 `ceil/floor` 放大。实测 ep240 entropy=5.78，CSV 记 8.31（≈1.44×）。诊断时**以实测为准**，CSV 熵曲线只看趋势。
3. **全剖面 reward 并非随训练变差（反直觉、须更正口径）**：ep50 全剖面 reward −376758（`gap_min=−386`，**真追尾 1382 步**）→ ep240 +161325（`gap_min=+33`，无明显追尾，末速 75.2 km/h、band 91.9%）。即**全剖面质量在改善**（修掉了追尾），**训练窗 reward 下降 ≠ 部署质量下降**（长程评估才是部署口径）。两个"变差/变好"是不同口径，勿混。

#### 五、修复方向（候选，需实验裁决，不在本条目定案）

- **主干**：让训练回合覆盖 ≥ `ab_min_refill_s` 的物理时域（或把循环制动"充风→二次制动"整周期纳入回合/以分段起点对齐到循环制动段），否则车钩力安全约束**不可能**被 RL 学出来。
- **次病**：`entropy_coef` 退火（或对 `log_std` 上界收到与动作域匹配，如 σ_max≲0.5），杜绝"饱和后仍免费涨熵"；同时修 `num_updates` 计量。

#### 六、证据边界

- 上述数值全部来自 `routecov_1400ep_seed0_par` **单 run / 单 seed**（该 run 于 ep245 前后停训），按 ADR-017 §3 **不进正文主表**；"训练窗时域 < 充风时间 ⇒ 不可学"的机制结论对配置成立（`120 s < 222 s` 为常量事实），但"是否唯一主因"需以**改地平线后的对照重训**裁决（待办）。
- 离线评估 JSON 产出于 `target_speed` 修复**之前**；结论中的"全剖面破线 ≈1155–1161 kN"在该批数值上成立。FIXED 口径（`target_speed=16.67`，与训练同参）ep240 复评已补齐 = **1149.3 kN / viol 270**（见 §七）⇒ 结论不变。

#### 七、补证｜破线峰值跨配置/跨并发/跨进度恒定（配置无关性）

全剖面（53km/36000 步/DI=10/确定性/seed0）六份一手 JSON 对照：

| ckpt | 全剖面 peak kN | viol | reward | 末速 km/h | band |
|---|---|---|---|---|---|
| `adr023_1400ep_seed0` ep50（**旧配置**，routecov 之前） | 1157.6 | 187 | +186722 | 81.2 | 91.4% |
| `routecov_1400ep_seed0_par` ep50 | 1154.9 | 432 | −376758 | 41.3 | 91.7% |
| `routecov_1400ep_seed0`（**串行**）ep50 | 1167.8 | 444 | +116847 | 77.4 | 96.9% |
| `routecov_1400ep_seed0`（**串行**）ep80 | 1162.9 | 218 | +196687 | 74.6 | 99.0% |
| `routecov_1400ep_seed0_par` ep150 | 1162.0 | 109 | +145549 | 77.1 | 95.4% |
| `routecov_1400ep_seed0_par` ep240（**FIXED 口径**，`target_speed` 与训练同参 16.67） | 1149.3 | 270 | +143140 | 69.1 | 87.7% |

- **破线峰值 ≈1149–1168 kN 跨配置（旧 `adr023` / 新 `routecov`）、跨并发实现（par / serial）、跨训练进度（ep50/ep80/ep150/ep240）、跨 harness 口径（20.0 / 16.67）恒定复现，且恒 >1000 kN** ⇒ 车钩力破线**不是 routecov 引入的回归、不是"训练轮数不够"、不是并行 rollout 实现缺陷、也不是 harness 口径造成的假象**，而是配置无关的**结构性**现象 —— 与"训练窗时域 120 s < 充风 222 s ⇒ 二次制动峰值不可学"（§二）相互印证。
- par vs serial 同 ckpt(ep50)：reward 差约 5×10⁵（**并行 rollout 确实影响策略质量**），但**峰值同档（1154.9 vs 1167.8）** ⇒ 峰值与并发实现无关，佐证其为物理/时域结构决定，而非实现细节。
- **harness 口径判据（更正）**：可判口径的是 `eval_args` 是否含 `target_speed` 键 —— 前五份均**无**该键（修复前脚本），ep240 FIXED 份为 `target_speed: null`（修复后脚本）。⚠️ `metadata.physics.target_speed_mps` 恒为 **20.0**（`evaluate_decompose` 调 `build_metadata` 时传的是**默认 `PhysicsConfig()`**，非本 run 实际值）⇒ **该字段不可用于判口径**（潜在元数据保真缺陷，勿据此下结论）。`target_speed` 修复已实测生效（探针 `tmp_verify_ts.py`，用后即删：无 `--target_speed` ⇒ `env.target_speed=16.666…`，与训练同参；显式 `--target_speed 20.0` ⇒ 20.0）。

#### 八、为什么"短训"没有暴露这个问题（补记 2026-10-07）

- **短训跑在 16 km 切片上**：沙盒/短训路况 = **`shuozhou_real_53km_slice16k`（= 母剖面 21.06–37.02 km，约 16 km）**；其自身 docstring 自称"**保留 -12‰ 陡坡 + -1.5‰ 缓坡交替、保留变坡/循环制动难点**" ⇒ **不能断言"危险段不在切片内"**（先前推断，**已更正**）。切片上长评/短评 peak 880–901 kN、viol 0 属实，但**究竟是切片漏掉了触发 >1000 kN 的里程，还是时域/起点没触及，尚未证实** —— 必须先**在完整 53 km 上定位峰值出现的里程**才能判定（见 §九）。
- **一手"假绿"证据**：① 沙盒 long_eval（routecov ON）ep40/80 = **795 / 832 kN、viol 0、达标 Y**；② 短程离线复评 `ms12000`（切片）= **880 / 901 kN、viol 0**。三者全绿 ⇒ 无红灯。
- **训练窗指标本就不可作判据**：训练 rollout 走**随机采样**（探索态，`interaction.py:83`），训练窗 `viol` 是噪声指标；且 `120 s < 222 s` ⇒ 二次制动峰值**结构性不在窗内**。短窗最优 ≠ 长程安全（诊断-2026-09-22 / 10-06 已反复印证）。
- **唯一能看见的全 53 km 口径，信号曾丢失**：主 run `long_eval`（完整 53 km / 确定性）5 个 ckpt `long_eval_best` 全 `-inf`（从未达标），但**失败当时未留痕**（`_append_long_eval_history` 于 2026-10-07 才加）+ 日志丢失 ⇒ 未成红灯；仅离线全剖面评估才把 1149–1168 kN 摆出来。
- **诚实边界（勿过度归因）**：旧 `adr023` 曾在 ep150 的 long_eval 于**完整 53 km** 达标（**956 kN / viol 0**）⇒ **"峰值绝对不可学"不成立为定律**；它说明的是"**短窗给不出针对该峰值的梯度**"。新 `routecov` 配置从未达标，另叠加了**熵失控**（§三）。两条机制不互斥，勿把"新配置到不了旧配置水平"全记在时域头上。

#### 九、峰值里程定位 + "切片能否替代全剖面"判别（2026-10-07，两个一次性探针）

两个临时探针（`tmp_peak_loc.py` / `tmp_peak_loc2.py`，**用后即删**），统一口径：ckpt = `routecov_1400ep_seed0_par` ep240；全 53 km（`shuozhou_real_53km`）/ 36000 步 / DI=10 / 确定性 / seed0 / `target_speed` 与训练同参；`init_speed_kmh=80`。

**探针1｜峰值出现的里程（回答 §八 遗留问题）**

- 全程：`km 0.00 → 54.83`，`peakmax = 1149.3 kN`；**破线步数 18689 / 36000（52%）**。
- **破线里程 = km25.43 → 54.83（进入后一直破到终点）**，非偶发尖峰。
- 1 km 分箱峰值：km25–26 = **1043 kN**（进入即破）；km26–49 = **平台 1146.4 kN**；km50+ = **1149.3 kN**。
- top-10 峰值全在 **km51.30–51.31**（step 33512–33521）= 1149.3 kN。
- ⇒ **`slice16k`（21.06–37.02 km）在里程上已覆盖破线区 25.4–37 km 的一段**，却在其上评估 <1000 kN ⇒ 破线**不取决于单段坡度**（先前"切片漏掉危险段"的推断**再次被否**）。

**探针2｜"沿程累积" vs "坡度稳态"判别（决定切片方案是否成立）**

- 做法：同 ckpt，`reset` 后把整队沿剖面平移 **+25000 m（= km25）**，状态全新（模拟"切片内起点"），再跑 3000 步。
- 结果：`start_km=25.00 → end_km=29.57`，`peakmax = **911.8 kN**`，**`n_over_1000 = 0 / 3000`**；每 500 步峰值 `162 → 539 → 706 → 778 → 778 → 912`。
- 对照探针1 同里程（km25–29.57）= **1043–1146 kN**。
- ⇒ **同一位置，全新起点比从 km0 起跑低约 200 kN（912 vs 1146）且不破线** ⇒ 破线**主要依赖从 km0 起沿程累积的状态**（速度 / 循环制动相位 / 充风状态等），而非该里程段的坡度稳态。

**裁决：靠后切片不能替代全剖面**

- 全新起点的切片**不复现** 53 km 上的破线 ⇒ 用切片训练/验证**会丢掉致病的初始条件**，不能作为"复现并修好该问题"的环境。
- **诚实边界**：探针2 新起点峰值**仍在上升**（末段 912 kN 未收敛）且只跑 4.6 km ⇒ **未排除**"新起点再跑 ~10 km 仍会破线"。故此处只作"**强烈提示依赖沿程累积**"，**不作"切片永远安全"的绝对断言**；要定论须跑新起点 ≥15 km（约 1 万步）的扩展实验。

**省时的正确杠杆（不是切片）**

- 训练耗时主要由 **每步物理 × 单窗步数 × episode 数** 决定。按 ADR-017，训练**只跑短窗**（curriculum ≤1200 步 ≈ 2.4 km），**根本不跑满 53 km** ⇒ **换剖面长度省不下训练时间**。
- 真正省时的旋钮 = **`long_eval` 频率**（`long_eval_interval`，50 → 100/200）与**总 episode 数**；而**单窗时域只能加长（≥ AB 充风 222 s ≈ 2500 步），不能缩短** —— 切片给不了这个。

### 文献对齐-2026-10-07 —— 新论文逐篇差异与可借鉴项（一手，供 ADR-030 落定）

**背景**：用户质疑"文献里都没提及、我的改进都没依据文献"。故把本轮新入库的 9 篇论文（fulltext 于 2026-10-07 20:47 提取）逐篇核对，只为回答"同一失效模式（长时制动滞后 vs 长窗口溃散）文献怎么解"，**不作二手转述**。全部结论只来自 `docs/papers/*_fulltext.txt` 实际文本。

**一、逐篇差异（明写事实）**

| 论文（本地 fulltext） | 对象/场景 | 是否建模车钩力 | 是否多列群组 | 算法 |
| :--- | :--- | :--- | :--- | :--- |
| `Wang2026_hierRL_fulltext.txt` | 2 万吨**单列**，长大下坡 | **是**（安全限值 1100 kN；进奖励 R_f + 状态 f_c/t_r，L715/723/631；物理上限 ±2500 kN L1050） | 否 | 分层 RL（空间分段顺序分配） |
| `Song2026_TubeMPC_fulltext.txt` | **多列**虚拟编组，长大下坡 | **是**（约束 ±1500 kN L1405；峰值 330.4 kN=22% L31/L81；车钩力补偿器 L1085） | **是** | Tube-MPC（非 RL） |
| `Si2025_DuelingDQN_fulltext.txt` | 单列 | **物理含**（多质点 F_c，L190；AB 建立/释放延迟 f_delay，L204） | 否 | Dueling DQN（最小充风时间约束） |
| `Zhang2024_QLearning_fulltext.txt` | 单列 | **否**（全文仅参考文献出现 coupler） | 否 | Q-Learning（单机车 agent；动作=AB 二值+ED 比例；最小充风约束） |
| `He2025_CyclicGA_fulltext.txt` | 13 km、−9‰~−12‰ | 是（车钩力降 21–23.9%，L11-24） | 否 | 遗传算法 + 高精度 LTD（循环制动寻优） |
| `Hu2026_PMMASAC_fulltext.txt` | 高铁虚拟编组 | **否**（无长编组车钩问题） | **是** | MASAC + Mamba 状态预测（长序列依赖，L142-155） |
| `Jing2025_VCTS_fulltext.txt` | 城轨 CBTC 虚拟编组 | **否** | **是** | MARL（VCTS） |
| `Li2024_CBF_fulltext.txt` / `Li2025_HOCBF_fulltext.txt` | 虚拟耦合跟随 | 用"相对制动距离"表安全 | **是** | CBF / HOCBF + QP 安全层（含通信延迟） |

**二、可借鉴的 MPC 改进项（一手出处）**
1. 车钩力**显式**进多目标代价与约束函数（Song2026 L25-26/L1402-1405）：速度跟踪 + 车钩力抑制 + 能效 + 稳定性统一协调。
2. **Tube/补偿器**抗空气制动时滞不确定性（Song2026 L31/L1085）——正对我们 AB 充风 222 s 时滞。
3. 循环制动 **GA 寻优**（He2025）→ 可作额外对照或循环制动时刻表来源。

**三、可借鉴的 MARL 改进项（一手出处）**
1. **把制动历史/计时编码进状态**（Wang2026 状态含 `t_r` 累计缓解时间 + `f_c` 最大车钩力 L631；Si2025 状态含 AB 阶段 L312-356；Zhang2024 约束最小充风 L187-214）→ **长时滞后做成可观测量，而非拉长 credit horizon**。（本 ADR-030 已落地：`obs[11]`）
2. **序列/预测模块替代长窗口**（Hu2026 的 Mamba 状态预测块，明确针对"长序列依赖 + 策略不稳"L117-158）。
3. **分层 / 空间分段**（Wang2026）→ 把长时域拆成可学的短子任务。
4. **课程式奖励权重 + 优先经验回放**（Hu2026 L467-495）→ 抑制溃散。

**四、裁决（对"文献没提及"的诚实回答）**
- **错的一半**：不能说"文献都忽略车钩力"——**Wang2026（2026，单列重载长大下坡 RL）已显式含车钩力**，**Song2026（多列虚拟编组 Tube-MPC）也含车钩力约束**。`RESEARCH_POSITIONING.md` §1.2 须补这两条限定（待办见 ADR-030）。
- **真空白的一半**：**"多列群组 × 车钩力 × MARL"** 交集仍近乎空白（Wang2026 单列、Song2026 是 MPC 非 MARL）→ 立论应改押"**把凭证从单列挪到多列群组**"。
- **对我们症状的启示**：我们一直用"拉长窗口"攻 AB 长滞后，而文献的通行解是**状态编码 / 序列模型 / 分层**——方向本就该换（→ ADR-030）。

### Pilot 裁决-2026-10-08（窗口三分支 A/B2/C，受控基线的前置证据）

- **背景**：2026-10-07 19:03 启动的三分支 pilot（当日交接文档，阅后即删），2026-10-08 复核全剖面评估产物并裁决。三组均为 commit `ff745cf`、3 列 1+1、decompose_m1、53km 剖面 × **随机起点**（start_randomization enabled）、BC 热启动、n_env 4、lr 2e-5、**仅 1 个训练 seed（seed0）**；评估统一 = 全剖面 36000 步（dt 0.1 ⇒ 3600 s）× **3 个评估种子**（`n_seed:3`）。
- **训练配置（metadata 一手）**：
  - **A**：40 ep，窗 500→3000 raw 步爬坡（ep15 起 3000 步 = 300 s），DI=10，`log_std_max` 未设（沿用旧钳位 2.0，σ 上限 ≈7.39，即 PIPELINE 实测失控的那组）。
  - **B2**：30 ep，窗 ≤1200 raw 步 = 120 s（结构性 <222 s 充风），DI=25（决策更粗，混变量）。
  - **C**：30 ep，窗恒 2500 raw 步 = **250 s ≥ 222 s**（`curriculum "2500:0"`），DI=10，**`log_std_max=0`（σ≤1）** + ValueNorm decay。
- **全剖面裁决（3 评估种子均值）**：

  | 组 | viol | peak (kN) | band | gap_min (m) | 追尾步 | 结论 |
  |---|---|---|---|---|---|---|
  | A | 497,997 | 1277 | 56.8% | 2.6 | 131 | **崩**（1 seed 全崩末速 17.4 km/h、1 seed 追尾 394 步）|
  | B2 | 597 | 1157 | 67.5% | −118.8 | 9187 | **不达标**（seed0 崩：追尾 26804 步、末速 0）|
  | **C** | **144** | **1112** | **95.7%** | **+47.6** | **0** | **训住但 peak 仍 >1000** |

  C 训练侧健康：value_loss 0.43→0.002~0.009 收敛、KL 全程 <0.05（`train_loss_dec_ad2_cp_seed0.csv`）。
- **口径修正（诚实记录）**：① 评估 JSON 的 `n_seed:3` = **同一 checkpoint 的 3 个评估种子，不是 3 个训练种子**——三组 pilot 证据等级均为**单种子信号**，"3 seed 无崩"表述作废；② C 训练在 53km 剖面上是**随机起点 × 250 s 截窗**，非全程 53km；③ A 与 C 之间差**两个变量**（窗 300→250 s、log_std 钳 2.0→0），pilot 分支对比 ≠ 单变量消融。
- **结论**：① "长窗必崩"不成立——直接死因是**探索失控**，钳住 `log_std` 后 250 s 长窗可训（C viol 较 A 降 **3455 倍**）；② 窗 ≥222 s 是训练窗内考到充风循环的结构性必要条件（与「诊断-2026-10-07」互印证；B2 的 120 s 窗实测 2/3 seed 仍崩于长程协调）；③ peak 1112 kN 恒 >1000 ⇒ PIPELINE 待办①（**安全层 `enforce_coupler` 未把全剖面峰值钉在 ≤1000**）优先级上调——它直接决定"峰值该不该由 RL 学"。
- **产物**：评估 `outputs/results/decompose/eval_decompose_decompose_m1_ms36000_pilot_win{A,B2,C}_last.json`；C 训练 `outputs/checkpoints/formation/pilot_winC_seed0/`（ckpt/results/figures/tensorboard 全）。
- **下一步**：受控基线规格待立（ADR-030 ②：**3 训练 seed** + 统一症状指标）；基线组选择（ADR-017 短窗+obs12 vs pilot C 派生）待拍板。

### 安全层诊断-2026-10-08（Step 0：`enforce_coupler` 为何兜不住全剖面峰值）

- **问题**（PIPELINE 待办①）：`use_coupler_constraint=True` 名义启用，全剖面 peak 恒 1112–1168 kN > 1000（六份 JSON 跨配置复现，pilot C 亦 1112）。
- **decompose 模式防护链全貌**（一手代码，`src/controllers/multi_loco_controller.py`）：
  1. **感知式缩放** `_coupler_throttle_scale`（L131-143）：当前**断面力**峰值（ADR-018 口径，L136/L308）ratio>0.8 → 线性缩 ED/AB 至 0（L361-363 应用于 RL 调制后动作；基线内部 L230 同）；
  2. **RL 新增 AB 源预测闸门** `ab_new_source_veto`（safety_layer.py L143-186，按位置/波速外推峰值提前封源）+ 阈值 0.6 + 单步并发 ≤1（L317-319 / L349-354）——**只拦 RL 新增源**；
  3. **充风门** `_ab_gate`（222s，L364-370，只管频次）。
- **裁决**：
  - **假设 B（接线 bug）排除**：三层防护在 decompose 路径真实生效，断面力口径统一，无静默失效分支。
  - **假设 A 成立（主导，且为文档已认的物理极限）**：注释明写"感知式钳制看的是当前力，拦不住 AB 波传播 ~5s 后的滞后峰值（1km 列 @200m/s）"（L312-315，诊断-2026-09-30 根因②）；**已建立的 AB 源不撤销**（L366-370"已 on 的源不受影响"）——力是动力学状态量，指令层只能管未来新增源。
  - **伴生缝隙（新发现，准-B）**：**规则基线自身的 AB 兜底（`ed_avail<0.99 → -0.75 档`，L227-229）不过预测闸门、不过并发限制**，只受感知 scale（ratio<1.0 时**仍发新源**，如 -0.75×scale<0 照样映射档位）+ 充风门。⇒ 长大下坡 ED 功率耗尽段（ed_avail<0.99 恒成立），**规则层自己持续追加 AB 源**，其波传播滞后峰值即破线主嫌。
- **旁证**：① 峰值跨配置恒定、RL 收敛后仍 1112 ⇒ 结构性产物而非 RL 学坏；② **MPC+规则层行 967 kN 达标**（同规则层）反衬——该行未破线可能因 MPC 目标速度更保守 / ED 用量不同使 ed_avail≥0.99 未触发 AB 兜底（待查）；③ km26–49 的 1146 kN 平台（52% 步数）与"ED 耗尽段 AB 兜底常开 + scale=0 后已建制动波继续传播/缓解延迟"吻合。
- **修复候选（不动手，走单变量流程）**：**Step 0.5 单种子快验**——pilot C 配置 + 预测闸门/并发限制**同样覆盖规则基线新增 AB 源**（约一处条件改动），30 ep 小时级，裁决"缝隙是否即峰值来源"。通过 → 纳入受控基线规格（"硬安全层"叙事成立）；不通过 → 峰值另有来源续诊。
- **叙事影响**：若 Step 0.5 通过，"硬安全层 ≤1000 kN"表述可保；若不通过，需降级为"硬源闸门 + 感知钳制（限源不限波）"并在 RESEARCH_POSITIONING 相应修订。
### MPC vs RL 破线差异分析-2026-10-08（Step 0 后续：旁证②重审）

- **数据**：MPC 行轨迹 npz（traj_mpc_nmpc_innerrule_53km_20261008_110834）+ pilot_winC 评估 JSON；RL 行无轨迹 npz（仅 summary）。
- **关键事实**：① MPC 行 peak 966.8 kN 出现在 **t=3599.2s（episode 末步）、km55.9（名义 53km 终点之后）、AB=0、三车间速差 13 km/h** 的末段回弹（train3 断面）；km26-49 段内最大仅 904 kN。② AB 施加期间断面力最高 **693 kN**；>800 kN 的 26 步**全部**发生在 AB=0 时。③ 58 个 AB 事件中仅 1 个三机同步（1→2 中位延迟 11.8s）——同步 AB 波基本不存在。
- **跨行反相关**：MPC 行 AB 用最多（10115 步）viol=0；纯规则行 AB 最少（2176）破线 1073；RL 行居中（8307 / 144）。
- **裁决：旁证②重审——「规则层 AB 兜底是破线主嫌」假设被 MPC 行数据反驳（初步，待 safegate 快验直接裁决）**：AB 兜底期间的波传播峰值不构成 >800 kN 主源。破线更可能由**无 AB 时的 ED 调制 + 簇间一致性差**驱动（RL gap_err 105 m / gap_min 47.6 m vs MPC 29.5 / 88.4；safety_events 436k vs 14.9k ≈ 29×）。⚠️ MPC 967 属末步边界区峰值，「MPC 行达标」表述需加边界限定（更长 episode 未必守住 1000）。
- **影响与下一步**：① safegate 快验照跑（裁决效力不变：直接测「闸门补齐」是否改 peak），但预期需下调；② RL 行 viol 定位需轨迹 dump（下次评估补 save_traj 参数）；③ **簇间一致性（编队目标本身）升至 RL 侧症状榜首**——与 obs12 互补不冲突（obs12 管 AB 时序感知，簇间相干管编队）。
- 分析脚本（临时，已删）：tmp_analysis/{analyze_mpc_traj,followup_mpc,check_band,peek_structure}.py
### Step 0.5 快验裁决-2026-10-09：闸门补齐生效，peak 1112→990 达标

- **配置**：pilot C 同配置（30 ep / 窗 2500 / log_std 钳 0 / 随机起点）+ 规则基线 AB 新源补闸门（力阈值 0.6 + 预测 veto + 单步并发 ≤1 + 超速紧急豁免）。训练 154.5 min（机器未睡眠则 ~5.8 min/ep）。昨夜首次启动死于系统睡眠（Ep1 后无声消失，无 traceback），残骸归档 _dead20261008。
- **全剖面 3 评估种子**（eval_decompose_decompose_m1_ms36000_pilot_safegate_last.json，已语义归档；默认名曾覆写风险已纠正）：

| 指标 | pilot C（无闸门） | safegate（有闸门） | 裁决 |
|---|---|---|---|
| peak (kN) | 1112.1 | **990.3**（997.7/1015.3/957.9） | **-122，2/3 seed <1000**；seed1 超 1.5% |
| viol 步 | 144 | **1.67**（0/5/0） | -98.8% |
| band 率 | 95.7% | 98.05%（96.8/99.2/98.2） | 未塌反升 +2.3pp |
| gap_min (m) | 47.6 | 80.4（96.4/67.4/77.5） | +33m |
| 追尾 | 0 | 0（3/3） | ✓ |
| AB 步 / meanED | 8307 / 0.192 | 5270 / 0.276 | AB 少 36%、ED 足 +44% |
| ATP 事件 | 436k | 414k–798k | 同量级 |

- **机制统一（修正上午推断）**：AB 稳态施加期间力不高（MPC 行 ≤693 kN），**旧规则层在 ED 耗尽段频繁新增 AB 源，新源的瞬态（波传播 ~5s 滞后叠加既有状态）才是峰值主源**；闸门管住新增源后，制动需求由更多 ED 承接（meanED +44%）→ 峰值 -122 kN。上午「破线由无 AB 时 ED 调制+簇间速差驱动」的推断作废；簇间一致性差（gap_err ~100 m vs MPC 29.5）仍是真实现象，但非本次峰值机制。
- **结论**：① Step 0.5 通过，闸门改动 + num_updates 计数修复**纳入基线代码**（受控基线冻结）；② 「硬安全层 ≤1000」叙事成立但措辞应为「压住」而非「硬钳制」（seed1 1015 轻微超限）；③ 训练窗内末段仍见 1359 kN/viol 2659（随机起点难段），与全剖面达标不矛盾——裁决口径 = 全剖面评估。

### 诊断-2026-10-11-外部反馈两问：速度抖振归因 + MT-2 装载缓释曲线失真量化

> 触发：外部反馈 ①「控制策略速度变化太频繁波动太大，违背常理」；②「车钩做得太理想，装载缓释曲线是错的」。两问均回一手代码 + 实测轨迹量化，未改任何现有 src 物理/控制代码。

**问① 速度抖振归因（轨迹实测，同源对照）**
- 新增轨迹归档：`outputs/results/decompose/traj_m1_rl_53km_20261011_005647/`（D-RL）与 `traj_m0_rule_53km_head_20261011_005810/`（D-Rule@HEAD，补跑原因见下）。
- ⚠️ checkpoint 口径：`adr023 best` 为 obs=11 旧口径，与当前 ADR-030 obs=12 不兼容（size mismatch）→ 用当前代码唯一可加载且 Step 0.5 达标的 `pilot_safegate_seed0/...ep30...pt`（10-09 全剖面 peak 998 / viol 0 / band 96.8%）。
- ⚠️ 旧 m0 轨迹（10-03，ff745cf）早于 ADR-027/029 等，与 m1 不同源 ⇒ 重跑当前 HEAD 的 m0 作对照；两份 m0 指标方向一致。
- 指标（领航列，三列均值见括号）：

| 指标 | m0@HEAD | m1 RL | 判读 |
|---|---|---|---|
| ED 符号翻转 次/min | 0.33 | **2.20** | RL 调制 6.6×，高频碎抖主源 |
| 速度方向反转 次/min | 1.33 (4.11) | 2.28 (4.28) | 领航列 1.7× |
| 进出 40–80 带 次数 | 17 (45) | **38 (51)** | 2.2× |
| 穿越 60 中值 次/10min | 2.00 (4.33) | 1.17 (2.83) | RL 反而少 42%（低频大摆=规则滞回） |
| 加速度 RMS / P95 (m/s²) | 0.069 / 0.108 | 0.069 / 0.098 | 总能量持平，P95 不升 |
| 尾随列带内驻留 | 92.7% | 82.2% | 尾列低速脱带，慢变问题 |
- **结论（实测→推断）**：反馈的"频繁波动"= RL 1s 决策在设定点附近的**高频小幅碎抖**（ED 翻转 6.6×、进出带 2.2×，实测）；"大幅慢摆"由**规则滞回带本身**主导（跨中值往返 RL 反而少，推断）。加速度总能量不因 RL 上升 ⇒ 问题在**频谱分布**而非幅值。全链路无动作速率限制（grep `action_rate|prev_action|rate_limit` 零命中，实测）。
- 待办（未执行）：Δ动作惩罚 / 执行端限速 / 决策降频 三选一需 ADR + 重训；旧 ckpt 与改动后环境不同源。

**问② MT-2 装载缓释曲线失真（量化实锤）**
- 新增脚本 `src/evaluation/plot_mt2_load_release.py`（`--source auto` 复画 / `new` 重算）；图 `outputs/sim_validation/figures/mt2_coupler/mt2_load_release_comparison.png`；数据 `outputs/sim_validation/phys_validation/mt2_load_release_cmp_20261011_002226/`。
- 对照 = 当前 `coupler.py` 标量模型 vs 于宗泽2025 式(1)(2) 字面实现（同 F0/k/μd·FN=500/μs·FN=750/ver=0.2，准静态 0.01 m/s 加载至 83mm 后释放）。
- **加载末段（|v|=0.01 m/s）摩擦分量：现模型 145.6 kN vs 参考 737.5 kN，缺 591.9 kN**（`dir_sm=tanh(dv/0.05)` 把 Stribeck 幅值压到 19.7%）；总阻抗 1914.3 vs 2506.2 kN。
- **迟滞环面积 23193 vs 122425 kN·mm，参考为现模型 5.3 倍**——"太理想"的量化定义：低速段摩擦与耗能严重不足。
- 形状口径修正（诚实边界）：匀速协议下"末端尖峰 vs 回落"**未复现**（最后 5mm 两模型均因刚度 +94.5 kN）；按式(1) 字面 sgn(0)=0，v=0 瞬间两模型均回落（-145.6 / -737.5 kN）。故准确表述 = **加载末段阻抗系统性偏低 592 kN + 环耗能仅 1/5**，而非尖峰方向反了。
- 现有 VALIDATION 锚点局限：迟滞环"逐点一致"是 closed-form 自洽，2270kN@83mm 只校端点，**无实测曲线形状对标**。
- 治理（未执行）：改摩擦结构/参数属物理变更 → ADR + metadata physics 串 + 测试回归；改后旧 ckpt 须在新物理下重评才同源。
