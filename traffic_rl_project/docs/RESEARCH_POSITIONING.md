# 面向长大下坡场景基于多智能体强化学习的重载列车群组自动控制方法

> **论文题目**：面向长大下坡场景基于多智能体强化学习的重载列车群组自动控制方法
> **研究对象**：一万吨级 1+0 重载列车群组（单机牵引的万吨列车，群组由多列组成，每列内部有车钩力）
>
> 本文档统一定义本项目（阶段二）的**研究定位、创新点、分层框架、文献清单与可复现技术点**。
> 是撰写报告、设计实验、补充文献时的总入口。

---

## 一、研究定位（Mission）

### 1.1 核心目标

用**多智能体强化学习（MARL）+ CTDE 范式**实现**面向长大下坡场景的重载列车群组自动控制**，研究对象为**一万吨级 1+0 重载列车群组**（每列 = 1 机车 + ~100 节货车，单机牵引，群组由多列组成）。

**场景约束**：长大下坡（如大秦线/朔黄线 -10‰ 连续下坡），需循环制动调速。
**自动控制内涵（2026-08-14 修正）**：**层级一（列间）MARL 训练出的控制器做群组协同决策**（每列输出目标速度/宏观驾驶曲线），**层级二（列内）由底层控制器（规则式/MPC）安全执行**（跟踪目标速度 + 保证车钩力 ≤1000kN）。即"RL 定策 + 底层控制器安全执行"的分层架构，与业界（VCTS/魏咪分层框架/Tang2020）一致，避免纯 RL 直接控 100 车厢的稳定性风险。

核心创新在于**"车钩力 + 多列群组 + 长大下坡"三层协同**——
- 现有长大下坡 RL 工作（Zhang2024 DQN、Liu2021 DDQN、Wang2025 DQN）**均忽略车钩力**
- 本项目在长大下坡循环制动场景下**显式建模车钩力**，并扩展到多列群组协同

### 1.2 核心创新点（与现有工作的差异）

| 维度 | 现有工作 | 本项目创新 |
|:--|:--|:--|
| 长大下坡 RL 控制（Zhang2024 DQN / Liu2021 DDQN / Wang2025 DQN） | 长大下坡循环制动 + RL，但**明确忽略车钩力**（"interaction forces between cars are not taken into account"） | **显式建模车钩力** + 长大下坡循环制动 |
| 虚拟耦合列车（VCTS） | 多列车协同，但**简化掉车钩力**（用安全间距） | **同时建模车钩力** |
| 单列车厢级重载控制 | **有车钩力**，但只做**单列** | **扩展到多列群组** |
| **车钩力 + 多列群组 + 长大下坡** | **几乎空白** | **分层 MARL 框架（本项目）** |

**创新论点**：群组级控制不能忽略每列内部的车钩力约束——
1. **物理真实性**：重载列车内部车钩力是真实安全约束（1000 kN 上限），忽略它可能给出"速度同步但车厢挤压"的危险解；
2. **跨层传播**：一列的纵向冲动可能通过编队级联传播到其他列（单层模型看不到）；
3. **真实需求**：大秦线等重载场景列车往往上百节，车钩力绕不开。

> **最终架构下的车钩力创新点呈现（2026-08-22）**：最终分层架构把"车钩力贯穿约束"下沉到列内**规则循环制动 + 车钩力安全层强制执行**（`enforce_coupler=True`，M1/M3 都守住 864/997kN < 1000kN）。第2层 RL 只做阈值协同（v_max_adj/v_min_adj），不直接承担车钩力约束。消融（M1 vs M2）显示第2层 RL 是否考虑车钩力无差异（结构性结论）——车钩力创新点证据在"规则循环制动 + 安全层强制执行"层面，而非第2层 RL 消融。

### 1.3 分层（Hierarchical）MARL 框架

```
┌─────────────────────────────────────────────────┐
│ 第2层：多列群组协同（列车间，Platoon Level）       │
│   智能体 = 每列列车                              │
│   状态   = 各列位置/速度/间距/前方坡度/前列状态    │
│   动作   = 协同阈值偏移 coor_adj ∈ [-1,1]         │
│            （映射为 v_max_adj/v_min_adj，限±5km/h）│
│   奖励   = 速度 + 间距保持 + 追尾惩罚 + 势场       │
│           ↓ 生成每列的"循环制动阈值偏移"           │
│ 第1层：列内规则循环制动（列车内，Coupler Level）   │
│   （非 RL，领域最优，Zhang2024 直接规则化）       │
│   控制   = get_action_cyclic_braking             │
│           （速度>v_max 制动 / <v_min 缓解）        │
│   约束   = 车钩力 ≤ 1000 kN（安全层强制执行）      │
└─────────────────────────────────────────────────┘
```

**两层连接**：第2层 RL 输出协同阈值偏移（v_max_adj/v_min_adj，限 ±5km/h）→ 第1层规则循环制动按调整后阈值制动/缓解，车钩力安全层强制执行 ≤1000kN。

**战略依据（2026-08-22）**：放弃"RL 学单列循环制动"（缓解波长时延6s→PPO信用分配失效+车钩力多体耦合→探索即爆炸，多次失败）。领域标准（Zhang2024/Tang2020）= 重载列车 RL 用离散档位 + 规则循环制动；Zhang2024 用 DQN 学循环制动但忽略车钩力（单质点）。我们建模车钩力，规则循环制动 + 车钩力安全层是正确方向，RL 只做宏观协同（调阈值不直接动 throttle）。

**对比实验（证明创新价值）**：
- **M1（协同）vs M3（δ=0 独立）**：协同增量 +110042（M1 +33494 vs M3 -76548），M1 不追尾 vs M3 追尾392（核心结果）
- **M1 vs M2（忽略车钩力）**：最终架构下无差异（结构性结论，车钩力约束已内置安全层强制执行）

### 1.4 当前进度（2026-08-22 最终架构）

| 子任务 | 状态 |
|:--|:--|
| 单列动力学环境（TrainFormationEnv，含 ATP 安全层、车钩力 1000kN、Davis 阻力修复、车钩间隙死区） | ✅ 已完成 |
| 列内规则循环制动 + 车钩力安全层（`get_action_cyclic_braking` + `enforce_coupler`） | ✅ 已完成（2026-08-22 最终架构，领域最优） |
| 多列编队环境（TrainFleetEnv，每列=智能体，朔黄线真实剖面 + 限速[40,80]） | ✅ 已完成（2026-08-14/17，free_length=12 真实编队尺度） |
| **最终分层架构**（第1层规则循环制动 + 第2层 RL 阈值协同 v_max_adj/v_min_adj） | ✅ 已完成（2026-08-22，`hierarchical_controller.py`） |
| **M1 训练 + 重评估（核心结果）** | ✅ M1(协同) +33494 vs M3(独立) -76548，**协同增量 +110042**；M1 不追尾 vs M3 追尾392；车钩力 864kN 守住 |
| **多种子统计（随机化初态）** | ✅ 10 seed：M1 +34763±1141（稳健）vs M3 -10641±43683；M1 追尾0 vs M3 158.6 |
| **扰动鲁棒性评估** | ⏳ M1 扰动下不占优（诚实负结果）→ 训练加扰动场景重训中（`l2_robust`） |
| **车钩力消融 M1 vs M2** | ✅ 最终架构下无差异（结构性结论，车钩力约束已内置安全层强制执行） |
| 长大下坡变坡剖面建模 | ✅ 已完成（shuozhou_23800 真实剖面） |

> **论文核心结果（可写入）**：面向长大下坡重载列车群组，提出"规则循环制动（微观）+ RL 阈值协同（宏观）+ 车钩力安全层"分层 MARL。在朔黄线真实剖面 + 多列编队场景，协同增量 +110042（M1 不追尾 vs M3 追尾392），车钩力守住 ≤1000kN，多种子统计稳健。

---

## 二、文献清单（Bibliography）

### 2.1 已下载到本地

| 文件 | 文献 | 说明 |
|:--|:--|:--|
| `docs/papers/Tang2020_DoubleSwitchQ.pdf` | Tang, Wang, Liu. *Reinforcement learning approach for optimal control of multiple electric locomotives in a heavy-haul freight train: A Double-Switch-Q-network architecture.* Knowledge-Based Systems, 2020. | 多机车重载列车 RL，**车钩力建模 + 多目标优化**，与本项目最相关 |
| `docs/papers/Fu2019_CouplerConstraint_HeavyHaul.pdf` | 付雅婷, 原俊荣, 李中奇, 杨辉. *基于钩缓约束的重载列车驾驶过程优化.* 自动化学报, 2019, 45(12): 2355-2365. DOI: 10.16383/j.aas.c190223 | 钩缓约束 + 多目标优化 + 预测控制，**开放获取** |
| `docs/papers/Huang2025_EITO_ExpertSystemDRL.pdf` | Huang, Lai, Chen, Lin, Yin. *Enhanced intelligent train operation algorithms for metro train based on expert system and deep reinforcement learning.* PLoS ONE, 2025, 20(5): e0323478. DOI: 10.1371/journal.pone.0323478 | PPO 多目标优化 + 专家系统 + DMTD 惰行，**GOLD 开放获取 CCBY**，与 2003.03327 同作者团队 |
| `docs/papers/Song2026_MAPPO_HeavyHaulGroup.html` | 宋宗莹, 李烁, 王兴中, 杨迎泽. *基于多智能体强化学习的重载列车群组协同控制.* 中国科技论文在线, 2026-05-26. DOI: 10.61951/SciencepaperOnline.202605.0114 | **多列独立列车群组 + MAPPO**，定位最接近（HTML 为元数据存档，全文需登录下载） |
| `docs/papers/Zhang2025_20kT_LongitudinalDynamics_Braking.pdf` | Zhang, Liu, Guo 等. *Research on Longitudinal Dynamics of 20,000-Ton Heavy Haul Trains Considering Braking Characteristics.* Mathematics, 2025, 14(1): 158. DOI: 10.3390/math14010158 | **GOLD/CCBY**，制动特性对纵向冲动的定量数据，可验证你的空气制动波速传播模型 |
| `docs/papers/Heineken2023_OptimalControl_EnergyEfficient.pdf` | Heineken, Richter, Birth-Reichert. *Energy-Efficient Train Driving Based on Optimal Control Theory.* Energies, 2023, 16(18): 6712. DOI: 10.3390/en16186712 | **GOLD/CCBY**，Pontryagin 极大值原理 + 再生制动，节能 37% |
| `docs/papers/Yang2024_ACSd_EnergyEfficientTrain.pdf` | Yang, Miao, Wang. *Driving Strategy Using an Improved Ant Colony System for Energy-Efficient Train.* J. Advanced Transportation, 2024. DOI: 10.1155/2024/5964428 | **GOLD/CCBY**，蚁群 ACSd 最优驾驶策略 ODSD |
| `docs/papers/考虑车钩力约束的重载列车运行优化分层框架与迭代求解方法_魏咪.pdf` | 魏咪, 王青元, 孙鹏飞, 冯晓云 等（西南交大）. *考虑车钩力约束的重载列车运行优化分层框架与迭代求解方法.* 中国知网 | ⭐⭐ **最重要对标**：**车钩力约束 + 分层框架**，与你的分层 MARL 定位几乎同主题 |
| `docs/papers/编组方式对3万吨重载列车循环制动工况纵向冲动的影响_樊运新.pdf` | 樊运新 等. *编组方式对3万吨重载列车循环制动工况纵向冲动的影响.* 电力机车与城轨车辆, 2024. DOI: 10.3969/j.issn.1001-8360.2024.01.006 | 高：编组 + 循环制动 + 纵向冲动物理规律 |
| `docs/papers/车钩间隙对重载列车纵向冲击动力学的影响_杨敏.pdf` | 杨敏 等. *车钩间隙对重载列车纵向冲击动力学的影响.* 中国知网 | 高：车钩间隙 → 最大车钩力（60km/h 时 0.01m 与 0.018m 相差 52.14kN） |
| `docs/papers/Guo2025_MARL_PlatoonConsensus.pdf` | Guo, Peng, Pi, Zhang, Wu, Ma. *Enhanced consensus control architecture for autonomous platoon utilizing MARL.* Comput-Aided Civ & Infra Eng, 2025. DOI: 10.1111/mice.13463 | 高：双向协同优化 + LSTM 时序，间距误差 -8.3%、编队长度 -19.1%，**HYBRID/CCBYNC** |
| `docs/papers/Zhang2024_DQN_CyclicBraking_Downhill.pdf` | Zhang, Zhou, He 等. *Deep Q-Network Algorithm-Based Cyclic Air Braking Strategy for Heavy-Haul Trains.* Algorithms, 2024, 17(5): 190. DOI: 10.3390/a17050190 | ⭐⭐⭐ **直接对标**：**长大下坡循环空气制动 DQN**，朔黄线实测验证，制动距离 -2.1%、平均速度 +7%。**明确忽略车钩力**——你的创新空间。**GOLD/CCBY** |

**已下载的 arXiv 源码（`docs/papers/arxiv_src/`）**

| 目录 | 文献 | 说明 |
|:--|:--|:--|
| `2504.19480/` | Wei, Yi, Lei, Hong, Du. *An Automated Reinforcement Learning Reward Design Framework with LLM for Cooperative Platoon Coordination.* | **完整源码**（28 文件）：LLM 辅助车队协调奖励设计，可借鉴到分层 MARL 奖励 |
| `2003.03327/` | Zhou, Song, Xue, You, Wu. *Smart Train Operation Algorithms based on Expert Knowledge and Reinforcement Learning.* IEEE TSMC. | **完整源码**：专家知识 + RL 列车运行，含算法与图 |
| `2312.06858_full/` | Abdelrahman, Shehata, Basyoni, Morgan. *Scalable Decentralized Cooperative Platoon using Multi-Agent DRL.* IEEE, 2021. | **完整源码**（109 文件）：**车辆车队 MARL**，前后跟随 "sharing and caring" 通信框架，可迁移到列车群组协同 |

### 2.2 未下载（需订阅/机构权限，已核实元数据）

| 文献 | 出处 | 相关性 |
|:--|:--|:--|
| Bulavin & Ignatieva. *Leveraging Deep Reinforcement Learning for Reducing Longitudinal Train Forces in Railway Systems.* 2024. | LNNS (Springer), DOI: 10.1007/978-3-031-77688-5_12 | 高：多体 ODE 动力学 + DRL 降纵向力 |
| Fang, Cai, Qiu. *Cooperative Tracking Control Combining with RL for Heavy-Haul Trains.* 2025. | IEEE | 高：协同跟踪 + RL |
| Wu, Spiryagin, Cole, et al. *International benchmarking of longitudinal train dynamics simulators: results.* 2018. | Vehicle System Dynamics | 高：LTD 仿真器基准 |
| Cole. *Longitudinal train dynamics.* 2017. | Vehicle System Dynamics | 高：纵向动力学综述 |
| *A distributed braking scheme for heavy-haul trains using coupler force...* 2026. | IEEE/CAA JAS | 高：车钩力约束的分布式制动 |
| *Dynamic identification of coupler force of heavy haul locomotive.* 2024. | Engineering Applications of AI | 中：车钩力识别 |
| *Multi-Resolution Deep Learning for Coupler Force Prediction in 20000-Ton Heavy-Haul Trains.* 2025. | ResearchGate | 中：车钩力预测 ML |
| Lin, Li, Qiu. *A multi-objective optimization approach for the virtual coupling train set driving strategy.* 2025. | Railway Engineering Science | 中：VCTS 单智能体 RL + MPC |
| *Multi-Agent Reinforcement Learning Optimization for Virtual Coupled Train Set Problem in CBTC Systems.* 2025. | Tsinghua Science & Tech | 中：VCTS 多智能体 |
| Aredah, Fadhloun, Rakha. *NeTrainSim: network-level simulator for freight train longitudinal motion and energy.* 2024. | Railway Engineering Science | 中：本项目动力学源头 |
| Wang, Wang, Sun. *Operation Optimization of Heavy Haul Train Considering Longitudinal Impulse Suppression: a DQN Approach.* 2025. | IEEE ICIRT, DOI: 10.1109/ICIRT66379.2025.11216684 | 高：**重载列车 DQN + 纵向冲动抑制** |
| 魏咪, 王青元, 孙鹏飞等. *考虑车钩力约束的重载列车运行优化分层框架与迭代求解方法.* | 中国知网 | 高：**车钩力约束 + 分层框架**（与你的分层想法呼应） |
| 樊运新等. *编组方式对3万吨重载列车循环制动工况纵向冲动的影响.* 2024. | 电力机车与城轨车辆, DOI: 10.3969/j.issn.1001-8360.2024.01.006 | 高：编组 + 循环制动 + 纵向冲动 |
| Si, et al. *Convergence-triggered reinforcement adaptive relearning control for virtually-coupled trains.* 2026. | Transportation Research Part C | 中：虚拟耦合强化自适应再学习 |
| Quaglietta, Wang, Goverde. *A multi-state train-following model for the analysis of virtual coupling railway operations.* 2020. | J. Rail Transport Planning & Mgmt | 中：虚拟耦合列车跟随模型 |
| Xun, et al. *Cooperative control of high-speed trains for headway regulation.* | IEEE Trans. Ind. Inform. | 中：高速列车协同控制 |
| Wang, et al. *A reinforcement learning empowered cooperative control approach for IIoT-based virtually coupled train sets.* 2020. | IEEE Trans. Ind. Inform. | 中：虚拟耦合 RL 协同 |
| 上海交大 JVS. *坡道上重载列车纵向冲动研究.* 2013. | JVS (上海交大) | 中：坡道 + 制动不同步 + 车钩力 |
| Zhou, Sheng, Liu. *基于钩缓特性曲线考虑不确定因素的重载列车驾驶过程优化方法.* | 华东交通大学 | 中：车钩特性曲线 + 多质点建模 |

### 2.3 通过 scholar-search-mcp（Semantic Scholar）新检索到的关键论文

> 已配置 API key，Semantic Scholar 通道稳定。以下论文摘要已提取，含完整 DOI。

| 文献 | 出处 / DOI | 相关性（摘要要点） |
|:--|:--|:--|
| **Wang, Wang, Sun. *Operation Optimization of Heavy Haul Train Considering Longitudinal Impulse Suppression: a DQN Approach.* 2025.** | IEEE ICIRT, `10.1109/ICIRT66379.2025.11216684` | **⭐⭐ 核心对标**：DQN + 简化动力学 + 多参数空气制动等效模型 + 循环制动约束；优化安全/车钩力稳定/速度跟踪；优化制动时机、电制动力协调、车钩力分布。降低最大拉力 9.64%、最大压力 28.77% |
| **Chen, Yang, Jin, Ren. *Distributed Global Composite Learning Cooperative Control of Virtually Coupled Heavy Haul Train Formations.* 2024.** | IEEE TITS, `10.1109/TITS.2024.3360945` | **⭐⭐ 创新点呼应**：虚拟耦合重载列车编队 + 电空制动算法（改善纵向冲动）+ NN 逼近动力学不确定 + 安全间隔/避碰。正合"群组+车钩力" |
| Ran, et al. *Dynamic identification of longitudinal impulse of heavy-haul locomotive.* 2025. | Meas. Sci. Technol., `10.1088/1361-6501/addc03` | 高：提出纵向冲动综合指标 CEILI + 多尺度卷积 + 极限学习机识别 |
| Ma, Bao. *Optimization of Empty Railcar Distribution... DRL.* 2026. | MDPI, `10.3390/futuretransp6030127` | 中：MDP 建模 + DQN + 经验数据融合 |
| Qu, et al. *Comparison of ML algorithms for rapid prediction of operational safety indicators.* 2026. | `10.1177/1748006X261430836` | 中：LSSVM 代理模型预测重载列车安全指标（LTD+MBD 联合仿真） |

### 2.4 方向检索补充（通过 MCP，多个研究方向）

**方向 A：分布式制动 / 纵向冲动 / 空气制动建模**

| 文献 | 出处 / DOI | 说明 |
|:--|:--|:--|
| **Zhang, Liu, Guo 等. *Research on Longitudinal Dynamics of 20,000-Ton Heavy Haul Trains Considering Braking Characteristics.* 2025.** | Mathematics, `10.3390/math14010158` (**GOLD/CCBY**) | **⭐⭐ 制动对标数据**：制动缓解不对称、制动管减压（50/70/100kPa → +16.8%/+36.8% 压钩力）、可控尾车延迟 3s 提升同步、尾车充风使最大拉钩力 780→489kN（-37%）。**可直接验证你的空气制动波速传播模型** |
| Ran, Chen, Wang 等. *Digital twin modelling of heavy-haul train for longitudinal impulse simulation.* 2025. | VSD, `10.1080/00423114.2025.2483348` | 高：数字孪生 + 实测标定预测纵向冲动，含阻力/钩缓/空气制动子系统 |
| Liu, Wang 等. *A heavy-haul train longitudinal-vertical coupled dynamics model under emergency braking.* 2024. | VSD, `10.1080/00423114.2024.2353705` (17 引用) | 高：钩缓非线性迟滞 + 制动延迟/气缸压力 + 紧急制动长下坡 |
| Hu, Zhang. *Research and simulation analysis of braking longitudinal impulse of 30,000-ton heavy-duty train.* 2025. | `10.1117/12.3060615` | 中：编组/初始制动速度/坡度/曲线对纵向冲动影响（1+1+1+1 编组冲动最小） |

**方向 B：虚拟耦合列车（VCTS）编队协同**

| 文献 | 出处 / DOI | 说明 |
|:--|:--|:--|
| **Li, Tong, Giua. *Safe Optimal Train Formation Control in Virtual Coupling Using Control Barrier Functions.* 2024.** | IEEE CASE, `10.1109/CASE59546.2024.10711420` | **⭐⭐ CBF/CLF + QP**：虚拟耦合编队安全最优控制——**正是你要做的"CBF 理论强化安全层"方向** |
| Gong, Wei, Song 等. *DRL-Based Optimization of LQR for Virtual Coupling Train Interval Control.* 2025. | IEEE ITSC, `10.1109/ITSC60802.2025.11423016` | 高：DDPG 优化 LQR 参数，间距控制精度提升 68.5% |
| Liang, Chai 等. *A Cooperative MPC Approach for Virtual Coupling Train Arrival in Metro.* 2026. | IEEE TITS, `10.1109/TITS.2026.3684075` | 高：DCMPC 分布式协同 MPC + 终端约束，通过能力 +4% |
| Wang, Wang, Feng 等. *Cooperative Control of Heterogeneous Virtual Coupling Oriented to Variable Tracking Gap.* 2025. | `10.23919/CCC64809.2025.11178698` | 中：变速跟踪间隙异质 VC 协同巡航 |
| Che, Lu 等. *Cooperative Control of Subway Train Virtual Coupling with Input Saturation and Quantization.* 2025. | IEEE ITSC, `10.1109/ITSC60802.2025.11423193` | 中：输入饱和 + 量化 + backstepping + RBF NN |

**方向 C：重载列车能耗优化 / 最优驾驶**

| 文献 | 出处 / DOI | 说明 |
|:--|:--|:--|
| **Yang, Miao, Wang. *Driving Strategy Using an Improved Ant Colony System for Energy-Efficient Train.* 2024.** | J. Advanced Transportation, `10.1155/2024/5964428` (**GOLD/CCBY**) | 高：ACSd 差分边蚁群 + ODSD 最优驾驶策略决策模型 |
| **Heineken, Richter, Birth-Reichert. *Energy-Efficient Train Driving Based on Optimal Control Theory.* 2023.** | Energies, `10.3390/en16186712` (**GOLD/CCBY**) | 高：Pontryagin 极大值原理 + 再生制动，**节能 37%**，含完整驾驶方式切换表 |
| Yildiz, Arikan. *Energy-efficient train operation strategy for human-driven trains... Istanbul Subway.* 2025. | `10.1080/03081060.2025.2457048` | 中：GSA 遗传退火优化加速杆，实车节能 31% |
| Zou, Chu 等. *Energy-efficient operation trajectory optimization of heavy-haul trains based on hybrid biological intelligent heuristic.* 2025. | `10.1016/j.jrst.2025.07.003` (HYBRID) | 中：混合生物启发式重载列车轨迹优化 |
| Yang, Xu, Fu. *Research on Multi-objective Optimal Control of Heavy Haul Train Based on Improved GA.* 2022. | IEEE IAI, `10.1109/IAI55780.2022.9976810` | 中：FAGA 模糊自适应 GA + 迭代学习控制跟踪目标曲线 |

**方向 D：多智能体 MARL 列车/车队协同（与你的群组级设计直接对应）**

| 文献 | 出处 / DOI | 说明 |
|:--|:--|:--|
| **Zhang, Nie, Ni, Tian. *Multi-Agent DRL Based Consistency Control in Train Platoon Systems.* 2021.** | IEEE HPCC, `10.1109/HPCC-DSS-SmartCity-DependSys53884.2021.00211` | **⭐⭐ 群组级设计**：列车编队 leader-follower + 分布式 MADRL + **人工势场先验**，距离/速度一致性 + 抗干扰。与你的"层级一"设计完全对应 |
| **Guo, Peng, Pi, Zhang, Wu, Ma. *Enhanced consensus control architecture for autonomous platoon utilizing MARL.* 2025.** | Comput-Aided Civ & Infra Eng, `10.1111/mice.13463` (**HYBRID/CCBYNC**) | 高：双向协同优化解耦跟踪行为与内部协调 + LSTM 时序建模，间距误差 -8.3%、编队长度 -19.1% |
| Wibisono, Song, Lee. *A Survey of MARL for Cooperative Control in Multi-AUV Systems.* 2025. | IEEE Access, `10.1109/ACCESS.2025.3609457` (**GOLD/CCBY**) | 中：MARL 综述（VDN/QMIX/MPDDPG/**MAPPO** + CTDE + PettingZoo 环境），含 MAPPO/MADDPG 对比实验 |

> **说明**：方向 A/B/C/D 的 GOLD/HYBRID/CCBY 开放获取论文**浏览器可直连下载，但程序化下载被出版社反爬拦截（403）**，需手动下载。完整手动下载网址见 `docs/PAPER_DOWNLOAD_LINKS.md`。

---

## 三、可从论文直接复现的技术点（Reusable Ideas）

> 标注 **可复现** 的标准：论文给出了可实现的公式/结构/参数，无需额外专有数据。

### 3.1 从 Tang (2020) —— 已下载

| 可复现技术点 | 说明 | 对应本项目 |
|:--|:--|:--|
| **多目标奖励函数** | 目标 = 速度 + 能耗 + 车钩力；约束 = 机车档位及档位变化率 | 可复用/对比 |
| **Double-Switch-Q-network** | 双开关 Q 网络架构（处理连续机车档位选择） | 可选做对照算法 |
| **车钩力建模** | 纵向动力学中显式建模车钩力 | 已实现于 `coupler.py` |
| **机车档位约束** | 档位离散 + 变化率限制 | 已实现于 `tractive.py` |

### 3.2 从 Bulavin & Ignatieva (2024)

| 可复现技术点 | 说明 | 对应本项目 |
|:--|:--|:--|
| **多体 ODE 动力学** | 列车建模为多体 ODE 系统（与你的 `train.py` 一致） | 已实现 |
| **DRL 降纵向力** | 以纵向力（车钩力）为优化对象的 DRL 策略 | 奖励已含冲动项 |

### 3.3 从宋宗莹等 (2026) —— MAPPO 群组（已下载元数据）

> 摘要确认：研究**由多列独立重载列车组成的运营编组**的智能协同控制，采用 **MAPPO**。
> 奖励 = **势场安全引导** + **多目标优化**（速度同步、间距保持、能耗）。
> **不含车钩力**（聚焦宏观运行层）→ 这正是本项目"加入车钩力"的差异创新空间。
> 作者单位含国家能源集团/神华（大秦线背景），基金：GJNY-22-7。

| 可复现技术点 | 说明 | 对应本项目 |
|:--|:--|:--|
| **MAPPO + 多列群组协同** | 每列列车为智能体，速度同步 + 间距保持 + 能耗 | 层级一框架 |
| **势场安全引导奖励** | 用势场把安全约束编码进奖励 | 可借鉴到安全层 |
| **高保真纵向动力学环境** | 自建纵向动力学作为仿真环境（与你的做法一致） | 已实现 |

### 3.4 从虚拟耦合类 (Lin 2025, 等)

| 可复现技术点 | 说明 | 对应本项目 |
|:--|:--|:--|
| **安全间距约束**（相对制动距离） | `x_safe = x_min + max((v_prev²/2F_brake - v_i²/2F_brake)·M, 0)` | 层级一约束 |
| **MPC 跟随** | 跟随列车用 MPC 追踪领航曲线 | 可选做基线 |
| **离散动作档位** | 5 牵引 + 惰行 + 5 制动的离散动作空间 | 可对比连续动作 |

### 3.5 可直接用的开源资源（非论文但可复现）

| 资源 | 用途 |
|:--|:--|
| **NeTrainSim**（GitHub: VTTI-CSM/NeTrainSim） | 本项目动力学公式源头（Davis、牵引、Karwatzki 制动） |
| **gym-pybullet-drones**（本地已 fork） | 阶段一仿真器，已验证 |
| **MAPPO 实现**（本项目 `src/algorithms/mappo_agent.py`） | 阶段一已收敛，直接迁移到列车 |

---

## 四、下一步行动（建议顺序）

1. **层级二 MAPPO 迁移**：把 `mappo_agent.py` 适配到 `train_env.py`（P1 核心）
2. **基线训练**：`lr=5e-5, entropy=0.005` 起步，验证环境奖励合理性
3. **奖励消融**：速度同步 vs 间距 vs 冲动权重（参考阶段一 L1>L2 经验）
4. **层级一设计**：多列群组环境（安全间距约束，复用现有 `TrainFormationEnv` 作为每列内部动力学）
5. **对比实验**：考虑 vs 忽略车钩力的群组控制
6. **报告**：系统对比无人机 vs 列车、单列车厢级 vs 多列群组级

---

## 五、文档索引

| 文档 | 定位 |
|:--|:--|
| **本文档** | 研究定位 + 创新点 + 文献清单 + 复现要点 |
| `PROJECT_PIPELINE.md` | 全项目 Pipeline 总览 + 进度 |
| `papers/` | 已下载论文（当前仅 Tang 2020） |
