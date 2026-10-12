***

title: 阶段二执行流水 2026-09
date: 2026-10-12
status: active
owner: Owner + Agent
supersedes: 无（本文件 = docs/PROJECT_PIPELINE.md 执行流水的原样迁出，内容零丢失）

> **角色**：阶段二**执行流水**（append-only：历史 ✅/❌ 条目一律保留，新条目按月追加到文件末尾）。
> 项目**总览 / 计划 / 下一步**见 `docs/PROJECT_PIPELINE.md`；诊断数据见 `docs/logs/diagnostics/`。
> **来源**：2026-10-12 自 `docs/PROJECT_PIPELINE.md` 按时间物理拆出，正文一字未改。

***

## 2026-09-02 起（阶段二 continuation）

### \[P] 实现"真正的 ATP"：复现 ETCS 目标距离超速防护曲线（升级 SafetyLayer）

- **状态**：✅ 已完成（4/5 步完成：验证基准→实现→单测对齐→**多列群组集成**；步骤5/5 论文更新待续）

- **归属**：P1 · 对应论文 Methods（安全层）与 Limitations（回应"ATP 是假的"/"有了 ATP 就不会追尾"质疑）

- **动机/背景**：答辩反馈 ① "你的 ATP 是假的"；② "真实铁路里追尾由信号级 ATP 保证，不由你控制器管"。需把 `src/safety_layer.py` 中的**简易限速软修正**升级为**有论文依据的真实 ATP 目标距离超速防护曲线（SBI/EBI）**，并使"追尾由 ATP 保证、我们做车钩力/间距"的叙事成立。

- **主文献**：欧洲铁路局 ERTMS 官方《Introduction to ETCS Braking Curves》（ERA\_ERTMS\_040026 V1.5，2020）→ `docs/papers/04_safety_mpc/ERA_2020_Introduction_to_ETCS_Braking_Curves.pdf`；辅助综述《An overview of the ETCS braking curves》。

- **核心复现模型（从 PDF §3 提炼）**：

  - **EBD（紧急制动减速曲线）**：对每个前方目标点（降速点/EOA/停车/间距约束点），用「保证紧急减速度（随速度步进）+ 坡度分量 A\_gradient」从目标点反推抛物线速度-距离曲线；减速度越低曲线越平。

  - **EBI = EBD + 最不利假设**（制动建立时间内按实测加速度 + 速度误差）得到的监督限位。

  - **五级监督**：I（提示）→ P（许可速度）→ W（警告）→ SBI（服务制动触发，可选）→ EBI（紧急制动触发）。

  - ETCS 实时只算**当前速度对应的单个 P/EB 限位**，非一次性整条曲线。

  - 制动建立时间可对本项目空气制动波速传播延迟建模（对齐 `braking.py`）。

- **完成判据（验收）**：✅ 已达成（2026-09-02，**111 测试通过**）＝ `SafetyLayer` 用 ETCS 曲线替换简易限速逻辑后 106+5 测试通过；限速路段内无超速漏检；长大下坡坡度分量生效；与论文 EBD 数值示例对齐（`test_etcs_braking.py` 28 用例，引用 PDF §5 数值例）。

- **多列群组 ETCS 集成（2026-09-02 完成）**：

  - `train_fleet_env.py`：`enable_etcs=True` 时建**共享 ETCS 制动曲线**（制动建立时间=车列总长/紧急波速 250m/s≈4.9s；建立期内按剖面最陡下坡沿坡加速度最不利；`grade_at` 绑定同一条剖面 → 坡度分量在监督层生效）。每步把**前列尾车位置**注入后列作 ETCS 监督目标（`set_etcs_targets`），实现车载"防追尾"由前瞻式 EBD/EBI 保证。

  - `train_env.py`：新增 `enable_etcs`/`etcs_curve` 配置项传入 SafetyLayer，`_state_snapshot` 注入 `head_position_m`/`etcs_curve`/`etcs_targets`。

  - `safety_layer.py`：反应式限速**恒在**（不再只在 ETCS 未生效时启用）——修复"前列很远时 ETCS 允许速度高、漏掉 80km/h 线速上限"的漏洞；ETCS（前瞻防追尾）+ 反应式（线速兜底）并存。

  - 集成回归：先跑通单测再全量，**111 测试全部通过，无回归**（车钩力/间距指标不受影响）。训练/评估命令留待手动执行验证（用户工作流约束）。

- **方法/计划步骤**：1) 从 PDF §3/§5 提取公式与数值示例 → 写入 `VALIDATION_BASELINE.md` 验证基准（ETCS 节）；2) 实现 `src/train_dynamics/` 或 `src/safety_layer.py` 内 EBD/EBI 曲线计算器 + 监督逻辑（含坡度分量、反应/建立时间）；3) 用论文数值示例做单元测试对齐（Gamma/Lambda 制动参数）；4) 接入现有分层训练/评估，验证车钩力/间距不回归 —— ✅ 已集成多列群组（见上）；5) 更新论文 Methods/Limitations 与文档留痕。

- **产出文件**：`src/safety_layer.py`（或新 `atp.py`）＋ 单元测试 ＋ `VALIDATION_BASELINE.md` ETCS 节 ＋ 诊断记录 (`docs/logs/diagnostics/DIAGNOSTICS_2026-09.md`)

- **关键边界（诚实声明）**：本复现聚焦**车载超速/限速防护曲线**（速度监督），非闭塞/信号层的授权防护（Movement Authority）；"防追尾属 ATP 职权，我们补充车钩力+缩短安全间隔"的叙述据此成立。

***

## P 系列未挂账｜ARIS 跨模型审阅链试点 - 2026-09-02

- **状态**：✅ 已试点（2026-09-02）｜评审结论已反哺论文重构方向

- **归属**：论文评审/方法论支撑（工具链，非训练任务）

- **动机/背景**：论文进入"MARL vs MPC 结构性对比"重构期，需要独立第二模型对抗性审出单模型自审的盲区偏袒。引入 ARIS（`Auto-claude-code-research-in-sleep`，[GitHub](https://github.com/wanshuiyin/Auto-claude-code-research-in-sleep)）。

- **接入方式**：`@` 引用 ARIS 仓库（`D:\Code\MultiAgent\Auto-claude-code-research-in-sleep`），不复制进项目 `.trae/skills/`；调研沿用 `mcp-servers\llm-chat\server.py`。

- **MCP 集成（llm-chat，跨族对抗）**：

  - reviewer=OpenRouter `minimax/minimax-m3:free`，executor=deepseek → `family_relation=different`

  - **TRAE 密钥遮罩坑**：TRAE 注入 stdio env 时把"值像 API key"(`sk-...`) 的变量前缀替换成 `\u2026` → httpx 报 ascii 编码错。**解法**：server.py 新增 `LLM_CRED_FILE`（从本地 key 文件读，env 只传中性路径），[server.py L52-72](file:///D:/Code/MultiAgent/Auto-claude-code-research-in-sleep/mcp-servers/llm-chat/server.py#L52-L72)；key 入 `C:\Users\chano\.trae-cn\memory\llm_chat_key.txt`（git 外）。

- **跨模型评审结论**（minimax 独立审 [ITSC\_PAPER.md](file:///D:/Code/MultiAgent/traffic_rl_project/docs/ITSC_PAPER.md)）：**P1 still-unresolved**——"Model-Free MARL" 标题 vs §IV 规则循环制动内层失配 → 改名 "Hierarchical Hybrid MARL w/ Rule-Based Cyclic-Braking Inner Layer"；**P2 still-unresolved**——fair-MPC（3.2s SLSQP 无规则内层/无终端集）是 strawman → 补 "MPC+同规则内层" 公平基线重跑 5-seed；**P3 partially-fixed**——20km 剖面 + 5 列仅提及 → 升级独立小节补全量指标。

- **留痕**：`docs/logs/diagnostics/DIAGNOSTICS_2026-09.md`（诊断-2026-09-02-ARIS 试点）+ `docs/logs/decisions/DECISIONS.md` ADR-008

- **下一步**：按 P1-P3 改论文 Abstract/Contributions、补 MPC+规则内层 baseline 实验；如需更严格独立，部署私有 ump/challenge 端点（`independence_verified` 目前 unverified）

***

### \[P3.5] 智能体分解重构：多机车分布式动力 × 电空双制动分工 - 2026-09-02

- **状态**：✅ 核心判据完成（2026-09-05，**完整 23.8km 时域全链路验证通过**）：①decompose 规则基线 vs 单机单控 = reward +74%/band +9.5pp/AB -89%；②RL 层（semi-MDP 决策间隔 10 救回）vs 自身规则基线 = reward +2.1%/车钩力 -21%/末速 +11.2km/h/ATP 事件 -97%，全部门控通过、零超限。证据链：单机单控 → decompose 规则 → decompose RL 三层递进全正增量。详见 DIAGNOSTICS 诊断-2026-09-05 三节（冒烟/全量+bug修复/RL层救回）。剩余：多 seed 训练（3 seed 协议）、论文 Methods/Results 改写（ITSC_PAPER 仍为旧架构叙事）

- **归属**：P3 层级一（多列群组）的**列内智能体分解升级** · 对应论文 Methods 问题陈述 / 创新点

- **动机/背景**：导师批评"3 列 1+0 群组叫多智能体不合适"——单机牵引每列仅 1 台动力源，把"列车"当智能体本质是宏观曲线优化，'多智能体' 名不符实（宋宗莹2026 同风险）。重构锚定到**物理独立动力源**（多机车）+ **电空双制动分工**，名实相符。

- **完成判据（验收）**：多机车(≥1+1)+每机车电/空双决策编组环境可跑；短训冒烟证明可控；全量评估给出 vs 单机+单控的**增量收益**（预期错峰缓解降车钩力峰值）。

- **方法/关键命令**：编组建构 ✔ `src/environments/train_env.py` 新增 `10kt_1plus1` 预设（2 机车 index \[0,95]，\~9976t）；动作空间 ✔ `decompose='loco_ed_ab'` 开关（默认 None）→ 每机车 (ED,AB) 动作 `(num_locomotives,2)`；控制器 ✔ `src/controllers/multi_loco_controller.py`（新增）循环制动 ED 优先 + 逐机车 ED 错峰 + 车钩力安全钳；训练（RL 智能体）✔ **2026-09-05 逐机车 RL 短训冒烟完成**——`train_fleet_env.py` 新增 `decompose='loco_ed_ab'` 模式（智能体=每机车、11 维 obs 含 AB 状态、电空分工奖励塑形）+ `train_fleet.py --decompose` 入口 + `MultiLocoController.get_action_decomposed`（规则基线 + RL `[ed_mod,ab_mod]` 调制）+ **ED 可用度物理化**（功率约束 F_ed=P/v vs 坡道需求力，修复原模型下基线 AB 兜底永不可达）。两轮冒烟（朔黄线 80km/h 起步 3000 步）：**可学性确认——车钩力 734→559kN（-24%）两轮复现、viol 0、band 99.97%**（RL 学到"逐机车错峰提前 MIN 档 AB"分配）；综合奖励与 M0 打平（-0.2%，差值≈AB 成本塑形项）→ 全量训练前置：①AB 成本/车钩力权重校准（目标定义，需导师拍板）②训练期探索不稳定对策（随机耦合 coupler 1168kN）。详见 `docs/logs/diagnostics/DIAGNOSTICS_2026-09.md` 诊断-2026-09-05-decompose换架构冒烟

- **配置**：`decompose` 默认 None（向后兼容，148 测试全过零回归，含 `tests/test_fleet_decompose.py` 9 项）

- **结果（2026-09-03 首跑）**：

  - ✅ decompose 可跑：动作空间 (2,2)、双机车 ED 错峰分工可见（act=\[\[1,0],\[0.7,0]]）、车钩力 749kN 守住

  - ✅ 139 测试全通过（`decompose=None` 零回归）

  - 📄 留痕：`docs/logs/diagnostics/DIAGNOSTICS_2026-09.md` 诊断-2026-09-03-多机车电空分工（decompose 首跑）

  - ⏳ 待补：逐机车 RL 短训冒烟证明可控性、全量评估 vs 单机增量收益（错峰缓解降车钩力）

- **关联**：文档立论 `docs/RESEARCH_POSITIONING.md` §1.3.1；决策 `docs/logs/decisions/DECISIONS.md` ADR-009；诊断 `docs/logs/diagnostics/DIAGNOSTICS_2026-09.md`

***

## 仿真器验证 HANDOFF 收尾 - 2026-09-02（论文数据定量复现）

- **状态**：✅ 已完成（2026-09-02，全量 **125 passed**，Windows Anaconda）

- **归属**：P0.75 验证基准的"论文工况定量复现"阶段（原 `docs/HANDOFF_2026-09-02_SimulatorValidation.md`，已删除，git 历史可查）

- **动机/背景**：仿真器已通过物理自洽（第一锚）+ RK4 独立实现（第二锚）验证并修复 3 个动力学 bug（含 Newmark 欠松弛 75% 缩水），剩余"论文工况对论文数字"的定量复现。

- **完成内容**：

  - **P0-1**：修复后论文数值重跑，1 万吨 527/597→**885 kN**（+48\~68%），"车钩力偏低 40%"疑点由 Bug 3 解释；2 万吨满 SERVICE 2405 kN 归因满档减压。

  - **P0-3**：`braking.py` 牵规 β\_c 连续减压量模型（K\_h=161.5 kN/车，向后兼容）；S5 定量化（1 万吨 1513 m / 2 万吨 1627 m 落 \[1050,3302) 带）；L1 解除 skip。

  - **P0-2**：2 万吨 1+1 验证编组 + 赵紫宁表5-3 四制动段锚点误差 **0.0 km/h**（r∈\[52.57,56.70] kPa 落文献常用带）；张二田 S1 尝试：全程峰值 **1677 kN ∈ 四源带 \[1000,1800]**。

  - **P1-4/5/6**：五编组长度效应绿（232>216）、S4 解除 xfail（659 kN）、历史数值断言审计（fleet 区分度测试 100% 动力学校准）。

- **留痕**：`docs/VALIDATION_BASELINE.md` V3.5.8 + `docs/logs/diagnostics/DIAGNOSTICS_2026-09.md`「诊断-2026-09-02-P0-2/3 + P1-4/5/6」+ 工作日志 `.codebuddy/memory/2026-09-02.md`。

- **遗留（用户手动执行，WSL conda）**：M1/M3/MPC 论文表 MARL 评估在 100% 动力学下重跑（相对结论预计不变，绝对值待更新）。

***

## 立论转向：Lim 2 替换为"MPC 在线求解计算复杂度/实时性" - 2026-09-03

- **状态**：✅ 已完成（实验证伪 → 立论文案 + 缩放实验 + 诊断留痕）

- **归属**：论文 ITSC\_PAPER.md（Introduction / Limitations 主轴）；对应 RESEARCH\_POSITIONING 立论

- **动机/背景**："司机经验=涌现协同（错峰）"立论被实验证伪（标准 RL 200 集未独立学出错峰）且无前人工作依托 → 用户决策放弃，转用 MPC 其他结构局限。

- **完成内容**：**实验证伪**——`outputs/exp_emergence_standard_rl.py`（10kt\_1plus1 + decompose='loco\_ed\_ab'，MAPPO 200 集）→ 错峰指数恒 +0.00，未涌现错峰；收敛到同步平稳制动（车钩力 1215→95kN）；规则恒值分工 reward 反而最差（−12287）。**Lim 2 替换**——ITSC\_PAPER.md §I/II/V/VI 把"不能复用驾驶经验"换成"**在线求解计算复杂度（保真×时域×规模）→ 实时不可行**"；Related Work 补 Wu2017（150 车空气制动 6.7× 慢于实时）、Wang2026（卡尔曼 2nN 状态）、Zhang2026（Koopman-NMPC）。**缩放实验**——`outputs/exp_mpc_complexity_scale.py` → 公平 MPC 每步求解 17ms（N=2,B=5）→ 3169ms（N=5,B=40）\~184×，MARL 推理恒定 0.39ms（最小配置即快 44×）。

- **留痕**：`docs/logs/diagnostics/DIAGNOSTICS_2026-09.md` 两条「诊断-2026-09-03-标准RL未涌现错峰」「诊断-2026-09-03-MPC求解复杂度缩放」；数据 `outputs/exp_emergence_standard_rl_results_20260903_182352.json`、`outputs/exp_mpc_complexity_scale_20260903_190913.json`。

- **关联**：`.trae/documents/plan_2026-09-03_立论司机经验涌现协同.md` 已标注废弃（方向推翻）；ADR-009 多机车电空分工方向不受影响（其"错峰"是规则预设，非本立论）。

***

## B 机制（目标速度协同）训练与评估 - 2026-09-04

- **状态**：❌ **失败（负面结果，已留痕）**——完整 23.8km 评估 M1 reward −653k（best）/−843k（ep75），远低于 M3 +235k / MPC-fair +230k；ATP 紧急制动 173 步。

- **归属**：P3 层级一（多列群组）协同机制重设计（A 阈值偏移 → B 目标速度协同）。

- **动机/背景**：A 机制 reward 分解显示 M1 劣势 = 制动频繁（brake −8,760）+ 间距惩罚，B 机制改为 RL 直接选目标巡航速度（target\_speed ±10km/h，规则循环制动围绕目标循环），期望减少无效制动。

- **完成内容**：✅ 实现 `hierarchical_controller.py` get\_action（v\_coop→目标速度→平移循环带），已验证 v\_coop=0→\[50,70]、+1→\[60,80]、−1→\[40,60]；✅ 训练 75 集 curriculum 300-2000-4000-6000-8000，best +66,712；❌ 评估 M1 best reward −653,268 / ep75 −843,465，reward 分解定位灾难源 = **gap\_reward −825,270**（三列 v\_coop 不一致→间距拉开→跟丢惩罚），speed\_band +222k 与 M3 几乎相同（速度控制正常）。

- **根因（回答"为什么文献能做我们做不出来"）**：

  1. 文献（Zhang2024/Liu2021/Wang2025）= 单列车单智能体控速，无列间一致性维度，RL 直接控制动档位（效果即时）→ 容易学；
  2. 我们 = 3 列独立输出 v\_coop 需自发一致 + 车钩力多体耦合 + ATP 安全约束 → 多智能体一致性问题，信号弱（gap\_reward +1/步 vs speed\_band +5/步）→ 探索即不一致 → 间距崩；
  3. 分层框架本身无问题（M3 也是分层且 +235k），问题在"协同层 RL 可学性"与"规则基线已近最优（学无可学）"。

- **留痕**：`docs/logs/diagnostics/DIAGNOSTICS_2026-09.md` 诊断-2026-09-04-B机制目标速度协同（含 reward 分解表）；数据 `outputs/results/train_history_cp_seed0.json`、`outputs/train_logs/eval_vcoop_vcoop_*.log`。

- **待决策（下一步方向）**：①回 A 机制长时域重训至 15000 步（消除 OOD，公平验证协同价值，2-3h GPU）；②修正 B（限 v\_coop 幅度/平滑正则/列间相对速度/拉长训练时域）；③调整论文立论为"稳定场景规则基线已近最优 + 协同增量在扰动/压力边界场景"（利用已有 M1 鲁棒性证据，无需重训）。

## 车钩缓冲器统一回 MT-2（移除机车 QKX100）- 2026-09-07（ADR-011）

- **状态**：✅ 已完成（2026-09-07，相关 55 测试通过）
- **归属**：P0.75 验证基准 / R0 车钩地基改进的**收口简化**。
- **触发**：承接 R0-C 的 QKX100 胶泥缓冲器分区 + 敏感性扫描；用户决策"还是统一用 A"（A = 成熟论文主流"分车型归一对"）。
- **内容**：全列（含机车-货车连挂钩）统一 MT-2 摩擦式缓冲器（Stribeck 750/500 kN、v_er=0.2、2270 kN 饱和），彻底移除机车 QKX100 弹性胶泥实现（消除 5 个无正文拟合常数的标定参数）。
- **落实**：源码 `params.py`/`coupler.py`/`train.py`、测试 `test_coupler_model_refined`/`test_fleet_decompose`/`test_train_dynamics`、绘图 `plot_physical_curves.py`（图 6 改单面板 MT-2）、训练 metadata physics 串均去 QKX100。
- **留痕**：ADR-011（`docs/logs/decisions/DECISIONS.md`）；`VALIDATION_BASELINE.md` R0-C superseded 标注 + 「诊断-2026-09-07」节；`ITSC_PAPER.md/.tex` Limitation (6) 改写 + tectonic 重编译 PDF；`AGENTS.md` 车钩描述与 R0 gotcha 更新；HANDOFF 补 superseded 声明。

---

## P3 免重辨识泛化 claim 完整实验计划 - 2026-09-10（ADR-014）

- **状态**：🆕 新增（实施中）
- **归属**：P3 · 论文 Experiments（主对比三行 + 跨线泛化 + 对照消融）· 立论依据 ADR-014 §1.6
- **动机/背景**：把 ADR-014 的"扛部署"立论落成可发表实验。核心 claim = 同一环境/安全层/**53km 主训练**下，免重辨识 D-RL 跨线守住底线（车钩力≤1000kN、ATP 不限速、列距不破界）；公平 MPC 需重标定/模型失配/耦合区求解失败。不比"谁控制更准"，只比"谁扛得住部署"。
- **主指标口径**：级联失败率 / MPC 求解失败次数 / ATP 触发次数（非追尾，安全层已杜绝）/ 车钩力峰值 / 列距不破界。
- **方法/关键命令**（完整可复现）：

  ```
  # 阶段0 工程奠基：ATP 永久启用移除 enable_etcs 开关 + run_training 统一入口核对
  # 阶段1 主训练 D-RL 53km 全量 5 seed + 双 checkpoint（best/ep120）+ curriculum→36000
  python run_training.py --experiment configs/experiments/formation_ed_ab_3train_1plus1.yaml --seed {0..4}
  # 阶段2 主对比三行 @53km：D-RL / D-Rule / MPC
  python src/evaluation/evaluate_*.py ...
  # 阶段3 跨线泛化（免重辨识）：D-RL 零微调 @20/35km vs 公平 MPC（no-re-identification，protocol A/B）
  # 阶段4 对照/消融：S-Loco / ED-only / AB-only（论文对标行）
  ```

- **配置**：主配置 `formation_ed_ab_3train_1plus1.yaml`（ED/AB 分工、6 agent、53km、36000 步、curriculum）；5 seed；跨线目标剖面 20km/35km 真实；23.8km 仅作已知锚。逐实验 metadata + JSON 时间戳归档（不覆盖旧文件）。
- **结果（完成后补）**
  - ⏳ 实施中：先完成阶段0 工程奠基（ATP 开关移除），再启动主训练。
- **产出文件**：
  - 结果/图表/日志：`outputs/checkpoints/formation/seed{0..4}/`、`outputs/results_*.json`
  - 数据记录：`docs/logs/diagnostics/DIAGNOSTICS_2026-10.md`（如跨月）、`VALIDATION_BASELINE.md` 诊断留痕

### ⚠️ superseded：训练时域口径修正（2026-09-16）

上节"阶段1 主训练 36000 步 / 53km 全程拼接覆盖"表述**不再采用**（它把两个不同维度混为一谈、产生误导）。修正如下（外部论文实证，见 `docs/papers/`）：

1. **训练时域 = 短窗口（on-policy 收敛前提），不是 36000 步全程**。本项目 on-policy MAPPO 单条 rollout 只能短窗口（`curriculum` 上限 1200 步，已验证安全收敛 viol=0 / pkCpl≤839kN）；长时程会重引入 on-policy 自举误差滚雪球不收敛。on-policy 论文交叉验证：Guo2025 用 horizon 1024/512 短窗口训练。
2. **评估时域 = 独立完整剖面，不是"多段 1200 步拼接"**。成熟做法=训练短窗口、评估单独跑完整剖面（Guo2025：combined trip 训练 1024 窗口、NEDC 完整剖面评估 ~3900 步；Zhang2021 全程 ~1200 步）。主训练 53km → 跨线 35km 完整剖面独立评估。`dt` 小不是障碍（Guo2025 dt=0.1 照样完整剖面评估）；Zhang2024 用 Δt=100s 只是刻意压步数。
3. **训练量（总 episodes）与训练时域（单条窗口）是两个独立维度**。本项目总训练量偏少（~120 episodes/seed，Hua2024 用 6×10⁵ 总步、Guo2025 用 1400 episodes），**补足方向=保窗口、增 episodes**，不是拉长窗口。
4. 以上修正不改变 P3 跨线泛化主线（53km 训练 → 20/35km 未见过剖面验证），该方向经 Guo2025/你项目设计验证为正确。改动仅限"训练时域/评估时域/训练量"的表述澄清。

> 本节 superseded 仅指"阶段1 的时域表述"，不否定 ADR-014 的"跨线泛化 claim"本身。

***

## 阶段二·交接后首日执行记录（2026-09-13）

| 任务 | 状态 | 说明 |
| :--- | :--: | :--- |
| 环境迁移：Windows 无 WSL2，新建 conda `traffic_rl`(py3.10+GPU) 跑通 | ✅ | torch2.6.0+cu124，CUDA 可用；gym+gymnasium 并存；详见 DIAGNOSTICS |
| 全量测试 | ✅ | `pytest tests/ -q` → **173 passed**（760.25s） |
| **§8 Step 1 并行验证（n_env=4 × 2000 步 × 44ep）** | ❌ FAIL（ep1-10 判定） | 首个 10ep **全面破线**（peak 恒 1476–1827kN、viol 494–1474/集、best_reward -2391，reward 无正）。且运行时 **~10–16min/ep → 44ep ≈ 12h**（远超预估 40-60min）。数据 `outputs/diag_53km_nenv/seed0/`；详细 `DIAGNOSTICS_2026-09.md`「2026-09-13-交接后Step1」 |
| Step 1 调整 + 后续 Step 2-5 | ⏳ 待主管拍板 | 候选：①加 BC warm_start；②恢复 curriculum 起步/缩短 parallel_traj_len；③n_env→8；同时须解决物理步进瓶颈。Step 1 判 FAIL 后按交接 §8.3「仍破线→回来讨论」暂停，未擅自进 Step 2 |
| **运行时提速评估（2026-09-13/14）** | ✅ | 实测 omp_num_threads=2/4/8 物理吞吐**无差异**（13.87/13.65/13.81 ms/step）→ 物理单线程主导，omp 提速无效。提速唯可靠 = 缩短总步进（curriculum/降 parallel_len）/ 真多进程并行 n_env（需改代码）。**5-seed×120ep 全量主训练本机不现实**（数十h~数天/seed），需决策：多进程并行 / 停于短档(2500步已覆盖53km) / 更强硬件。详见 DIAGNOSTICS「运行时提速评估」 |
| **受控重验①：加 BC warm_start（n_env=4 × 2000 步 × 8ep）** | ⚠️ 部分 PASS / 判 FAIL | BC 修复 reward 侧（8ep 中 6 正、best+14558，上轮全负），**确认"缺安全起步"是 Step1 FAIL 因素之一**；但车钩力仍破线（peak 1079~1650、viol 14~633），未达 §8.3 判据。数据 `outputs/diag_53km_nenv_BCws/seed0/`；详见 DIAGNOSTICS「受控修正重验」 |
| **待办（最该做）①：恢复 curriculum 渐进出步（parallel_traj_len=0）+ BC + n_env=4** | ⏳ 未跑 | 样本：历史单轨"渐进到 2000"BC 版 ep11-21@2000档 viol 全 0；本轮恒 2000 直接开跑 viol>0 → 渐进起步是遗留破线主嫌，待验证。单 ep 成本低（500/1000 起步为 2000 档 1/4~1/2）。若仍破线→定为"并行信噪比 2000 档不足"，再议 n_env→8/截断/off-policy |

***

## 阶段二·主训练长训稳定性（2026-09-19）：MAPPO 终段 value 发散治本 + 验证通过

**背景**：`seed0_nep1400`（1400ep 主训练）在终段 **ep849→856 发散**（loss +0.337→+1.283、reward 崩 -5371），直接威胁长训主结果稳定性。ep841 best 权重本身干净（53km/35km 双剖面 5-seed 全 viol 0、车钩力<876kN、+221163），发散仅发生在**继续长训**阶段。

**根因**（非单点突变）：策略固有"偶发暴力 AB 探破车钩力>1000kN"的深负破线轨迹，在长训终段碰上 value_norm(PopArt) running std 收缩，被放大成不可回退的 value 污染（全程 viol>0 共 22 个、ep428 起贯穿、终段最集中）。

**三项治本杠杆（全部落点 `src/algorithms/mappo_agent.py`，只影响训练不影响推理）**：
1. per-trajectory winsorization（`_winsorize_by_traj`，lo_q=0.02/hi_q=0.98）：按 done 切轨迹，仅把 <2% 分位的深负异常轨迹整体均摊抬升，正常轨迹不动 → 掐断"污染入口"。
2. value 网络独立 `clip_grad_norm_(max_grad_norm*0.5)`（在整体 clip 之前）→ 掐断"放大端"。
3. KL 早停 `target_kl*1.5→*1.2`（0.015→0.012）→ 提前拦截"累积端"。

**30ep 续训验证（从 ep841 干净权重，n_env=4、恒 1200 步档，107.7min）**：
- violations **30ep 全 0**；total_loss **-0.010~+0.001** 小值稳定；peak_coupler **686~875kN**（<1000kN）；reward **9956~11369** 无崩塌。
- **原发散区 ep849-856 零复发**（ep849 loss=-0.002、ep856[-1.283] -0.010）；KL 早停提前到 epoch 3-4/10（原终段 7-10）。
- 数据 `outputs/checkpoints/formation/seed0_valid_lean/results/train_history_dec_ad2_cp_seed0.csv`；模型 `.../mappo_fleet_best_dec_ad2_cp_seed0.pt`。

**判断**：治本杠杆 **SUCCESS**。留痕 → `docs/logs/diagnostics/DIAGNOSTICS_2026-09.md`「诊断-2026-09-19-MAPPO长训终段value发散治本（winsorize + value grad clip + KL早停收紧）」。

**下一步（主线）**：铺 **5-seed（seed0-4）全量 episodes=1400 长训**（新逻辑自带治本杠杆）→ 核对长期稳定 → best-checkpoint 协议产出主结果 → 主对比评估。若 5-seed 长训仍发散，回读诊断按杠杆强度/超参迭代。

**（2026-09-20 更新）5-seed 1400ep 长训已启动，且改并行编排**：诊断出原串行脚本慢的根因=`n_env=4` 是纯串行 for 循环 + 单进程顺序跑 seed0→4，整训练只占 1 核（load~1.0/12 核）。已改 `scripts/launchers/launch_final_5seed_parallel.sh`（每 seed 独立进程各占 1 核，`wait` 聚合；物理保真零改动）。代价=内存带宽竞争使单 ep 150s→268s，净提速 ~2.8×：墙钟 ~12 天→~104h（~4.3 天）。后台 job `job-5d1ee3c78c7441b194f099519f14dbae`，逐 seed 日志 `outputs/logs/final_parallel/seed{N}.log`，留痕见 DIAGNOSTICS-2026-09-20。

***

### [P3] 车钩力口径统一 + 安全层对 AB 的"减"权限（治本落地） - 2026-09-30

- **状态**：✅ 完成（改造 + 单测 + 同窗口四场景回归验证）
- **归属**：P3（免重辨识泛化主线的**安全兜底契约**修复）· 对应论文 Methods（安全层）/ Limitations（"车钩力 ≤1000kN 硬兜底"）
- **动机/背景**：`诊断-2026-09-30-100ep破线根因` 定位两个**代码级根因**——① 指标口径混用（"每车净力" vs 基准"单钩断面力"，少报 ~7.8×，拉压交界误判）；② 安全层对 AB **无物理权限**（`ab_sources` 绕过安全层；两 AB 闸门反应式且读净力，叠加 AB 波 ~5s 滞后 ⇒"≤1000kN 硬兜底"名不副实）。决策全文见 `docs/logs/decisions/DECISIONS.md` **ADR-018**。
- **完成判据（验收）**：
  - ✅ = 同一 1200 步窗口（`set_seed(2000)`、初速 80 km/h）四场景**断面力口径全部 0 步破线**（full 1238.4→**783.4 kN**、no_traction 1242.3→**955.2 kN**、no_rl 767.7 不变、no_ab 870.1→769.0）
  - ✅ = 单测 `pytest tests/ -q --ignore=tests/test_mappo_train.py` → **172 passed**（exit 0）
  - ❌ 失败项：无
- **方法/关键命令**：回归脚本为临时脚本 `tmp_diag_regress_0930.py`（结论入档后按项目规则已删）；`env.reset()` 有状态残留 → 逐场景重建 env
- **配置**：权重 `outputs/checkpoints/ab_gate100/mappo_fleet_last_ep100_dec_ad2_cp_seed0_seed0.pt`（`decision_interval=10`）；剖面 `configs/experiments/formation_ed_ab_3train_1plus1.yaml`（起始 1200 步）
- **结果（已完成）**：
  - 四场景复测：full **783.4 kN / 0 步**、no_rl 767.7 / 0（**逐字不变**，确认闸门不扰动规则层）、no_traction **955.2 / 0**、no_ab 769.0 / 0
  - **闸门开/关隔离对照**：full_nogate 1156.7 kN / 17 步 → full 783.4 / 0；**口径统一贡献 124→17 步**（门控改读断面力后更早介入，属行为变化）、**闸门贡献 17→0 步**
  - 速度未受损（<40 km/h 比例 **42.8%→3.4%**，末速 35.9→39.2 km/h）
  - **诚实边界**：单权重（seed0）× 单 rollout seed（2000）× 单窗口（1200 步），**不得据此断言终态策略安全**
- **产出文件**：
  - 结果/日志：`computer://d:\Code\MultiAgent\traffic_rl_project\outputs\log_diag_regress_20260930.txt`、`.json`
  - 数据记录：`docs/logs/diagnostics/DIAGNOSTICS_2026-09B.md`「诊断-2026-09-30-治本改造回归验证」；教训 `LEARNINGS.md` LRN-20260930-001/002（转 resolved）/003（`env.reset` 残留）
- **遗留（承接上一节 ⑧）**：① 抑制 AB 不均匀缓解（列尾拉力来源）；② **1400ep 全量 5-seed 重训** + 完整剖面评估；③ 全部代码改动**尚未 git 提交**（待用户确认）

### 续（2026-09-30）：遗留①②结论与 5-seed 重训推进

- **git 提交**：治本改造 ADR-018 全部改动已提交 `ff745cf`（51 文件）。工作树干净。
- **遗留① 定论（不改造核心物理）**：受控隔离诊断（临时脚本 `tmp_diag_eot_isolation.py`，同 full 权重/seed2000/1200 步/断面力口径）——
  - eot=False（现状）峰值 **648.2 kN**、0 步破线、列尾受拉 317.2 kN
  - eot=True（缓解双向同步）峰值 627.4 kN、0 步破线、**列尾受拉 317.2 kN 不变**
  - ⇒ 治本(ADR-018)后同权重峰值 1238→648 kN（闸门奏效、0 破线）；eot 双向缓解对列尾受拉**零贡献** ⇒「不同步缓解→列尾受拉」在当前闸门净化行为下**不构成主导通道**，**不支持改造核心缓解物理**（避免回归 + 免二次重训）。详细见 `DIAGNOSTICS_2026-09B.md`「诊断-2026-09-30-遗留①受控隔离」；产物 `outputs/logs/diagnostics/log_diag_eot_isolation_20260930_133819.json`。
- **遗留② 现状核对**：5-seed 长训**早已停止**（09-22 log 截止）且未完成——`final_seed{0..4}` best 存在、续训到 ep 992/992/521/661/671（/1400）。原 launch resume 源已 MISS；`final_seed{N}` 作续训起点（09-26 AB 并发限制，结构与 ADR-018 兼容）。GPU 空闲。
- **待启动**：续训 `final_seed{0..4}` best 到 1400ep（用 ADR-018 代码，新输出目录 `final_seed{N}_v2` 防覆盖）。

### [P3] 训练框架续训（resume）改造 - 2026-09-30

- **状态**：✅ 完成（代码 + 单测 + 端到端冒烟验证）
- **归属**：P3（工程基建，**上一条"待启动"续训任务的前置**）· 对应论文 Methods（训练可复现性）/ REPRODUCIBILITY
- **动机/背景**：统一训练框架旧 `--resume` 为"半成品"，三个硬伤：① 路径写错/文件不存在 → **静默从头重训**（不报错、白跑数小时；上一条"原 launch resume 源已 MISS"即其现实复现）；② `--episodes` 语义为"再跑 N 集"，须人工算剩余（诊断记录曾致 seed2 超跑到 ep70）；③ 进度/历史/最优态不恢复（logger 与 artifacts **全量覆写** ⇒ 学习曲线只剩续训段；`best` 只读新 `results_dir`）。决策全文见 `docs/logs/decisions/DECISIONS.md` **ADR-019**。
- **完成判据（验收）**：
  - ✅ = 路径不存在 → `FileNotFoundError`（不再静默重训）
  - ✅ = `--episodes` = **总目标集数**，日志显式打印"已训 N ep，目标总 M ep，本轮跑 K ep"
  - ✅ = 续训后 history/CSV 连续、`best` 继承（换目录不丢）
  - ✅ = `--resume-weights-only` 只加载权重（优化器/value_norm/RNG 重置，供旧物理 → ADR-018 迁移）
  - ✅ = 单测 `tests/test_resume.py` **14 passed**；全量 `pytest tests/ -q` → **192 passed**（原 172 + 20 新增，0 回归）
  - ❌ 失败项：无
- **方法/关键命令**：见 `DIAGNOSTICS_2026-09B.md`「诊断-2026-09-30-续训框架端到端验证」（五场景，60 步窗口冒烟）
- **结果（已完成）**：五场景全通过（①首发 1ep → ②`--resume --episodes 3` 只跑 2ep + CSV 3 行连续 + best 继承 → ③`latest` 三信号一致 → ④错路径抛错 → ⑤`--resume-weights-only` 正常）；冒烟中修掉两处真实缺陷（CUDA 下 RNG `ByteTensor`、`last.pt` `done_ep` off-by-one）
- **产出文件**：
  - 原始日志：`outputs/logs/diagnostics/log_resume_smoke_20260930.txt`（不覆盖）
  - 代码：`src/trainer/resume.py`（新）+ `train_runner.py` / `logger.py` / `config_schema.py` / `base_agent.py` / `mappo_agent.py` / `run_training.py` + `tests/test_resume.py`（新）
  - 记录：`DIAGNOSTICS_2026-09B.md`「诊断-2026-09-30-续训框架端到端验证」；教训 `LEARNINGS.md` LRN-20260930-004（静默重训）/005（CUDA RNG）/006（off-by-one）
- **遗留**：① legacy 训练入口（`train_fleet.py` / `train_cyclic_braking.py`）不享受本改造；② 本次改动**尚未 git 提交**（待用户确认）；③ 承接上一条：现在可以安全启动 `final_seed{0..4}` 续训到 1400ep

<!-- 该文档整理/压缩于 2026-10-12 -->
