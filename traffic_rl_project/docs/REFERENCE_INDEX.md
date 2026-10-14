# 引用索引（技术/公式 → 论文）

> 写论文时的引用速查。每项：技术/公式 → 来源论文 → 本地文件（`docs/papers/` 下完整文件名；无本地文件的标注 arXiv/出处）。引用须锚定外部权威，禁止用本项目历史当外部标准。

## 纵向动力学 / 车钩力

| 技术/公式 | 来源 | 文件 |
| :--- | :--- | :--- |
| MT-2 摩擦式迟滞缓冲器（Stribeck 静750/动500 kN，v_er=0.2，饱和2270kN@83mm）【旧解析口径，已被下行容嘉欣2025 查表口径取代，见 ADR-031】 | 于宗泽2025《重载列车车钩缓冲装置纵向动力学精细化模型》 | `于宗泽2025_fulltext.txt` |
| MT-2 货车装载-缓释阻抗曲线 fl/fu 数字化查表（fl(83mm)=2270kN 锚定）+ 速度法 sign(Δv) 选支（加载→fl、卸载→fu、Δv=0→f0）——当前实现口径 | 容嘉欣2025《更大牵引质量重载列车动力学建模与仿真分析》机械 52(7):57-64 图4(b) | `容嘉欣_更大牵引质量_提取文本.md` + `更大牵引质量重载列车动力学建模与仿真分析_容嘉欣(1).pdf` |
| 车钩间隙死区（0.01m）→ 间隙放大车钩力（60km/h 0.01 vs 0.018m 差 52.14kN） | 杨敏《车钩间隙对重载列车纵向冲击动力学的影响》 | `车钩间隙对重载列车纵向冲击动力学的影响_杨敏.pdf` |
| 车钩力正常/紧急上限 1000/2250kN | Fu2019《基于钩缓约束的重载列车驾驶过程优化》 | `Fu2019_CouplerConstraint_HeavyHaul.pdf` |
| 多体纵向耦合运行安全框架（超长列车） | Krishna2020 | `Krishna2020_OverlongHeterogeneity_运行安全.md` |
| 缓冲器非线性纵向动力学 | Wang2025 | `Wang2025_LongitudinalNonlinear_缓冲器非线性.md` |
| 20kT 制动纵向动力学（EOT 拉钩力 780→489kN，-37%） | Zhang2025 | `Zhang2025_20kT_LongitudinalDynamics_Braking.pdf` |

## 制动力 / 空气制动

| 技术/公式 | 来源 | 文件 |
| :--- | :--- | :--- |
| 牵规常用制动系数 β_c(r)（p₁=600kPa：50~110kPa→0.17~0.67，饱和0.75）+ 换算摩擦系数 φ_h(v)=0.322(v+150)/(2v+150) | 牵规 + 赵紫宁2022 | `重载列车空气制动精细建模与操纵优化.pdf` |
| 换算闸瓦压力 K_h=161.5kN/车（标定自赵紫宁表3-5） | 赵紫宁2022 | `重载列车空气制动精细建模与操纵优化.pdf` |
| 空气制动精细建模 + C_β 段间衰减（首段1.379，段间0.705/0.676） | 赵紫宁2022 | `重载列车空气制动精细建模与操纵优化.pdf` |
| 列尾压强梯度 → 制动缸平衡压比；拉钩力 -44.5%/-20.9% | 刘博阳2022 | `刘博阳2022_列尾压强与车钩力.md` |
| 缓解滞后（列尾压强高→后部缓解延迟 17.8~20.9s） | 刘博阳2022 | `刘博阳2022_列尾压强与车钩力.md` |
| 制动缸压力约 10s 升至峰值 | 周占松2026 | `不同万吨编组列车空气制动特性对纵向动力学性能影响_周占松.pdf` |
| 空气制动波速双向传播（常用200/紧急250 m/s；2万吨初制动差~3s、缓解差~10s） | 张二田2021 | `张二田2021_朔黄2万t车钩力实测.md` |
| 缓解两段式排气（波传播期满 + exp(-t/τ=6s)） | 于宗泽2025 / 赵紫宁2022 | `于宗泽2025_fulltext.txt` / `重载列车空气制动精细建模与操纵优化.pdf` |
| **缓解再充风时间 175~512 s**（12 个制动段实测）；**困难区段最短充风 222 s**（5 次循环制动） | 赵紫宁2022 / 张二田2021 | `重载列车空气制动精细建模与操纵优化.pdf`（VALIDATION_BASELINE 判据 B4）/ `张二田2021_朔黄2万t车钩力实测.md`（判据 S6） |

## 循环制动 / 长大下坡（领域基线）

| 技术/公式 | 来源 | 文件 |
| :--- | :--- | :--- |
| 长大下坡循环空气制动 DQN（朔黄23.8km，限速[40,80]km/h，V0=65，忽略车钩力；Eq.22 Rc/Rd 奖励） | Zhang2024 | `Zhang2024_DQN_CyclicBraking_Downhill.pdf` |
| DDQN 循环制动 | Liu2021 | —（无本地，TR-C 2021） |
| DQN 速度控制 + 纵向冲动抑制（拉-9.64%/压-28.77%） | Wang2025（ICIRT） | —（无本地，IEEE ICIRT 2025） |
| 编组方式→循环制动纵向冲动（3万吨，坡度差≤10.5‰） | 樊运新2024 | `编组方式对3万吨重载列车循环制动工况纵向冲动的影响_樊运新.pdf` |
| 朔黄2万t车钩力实测（判据S1-S7） | 张二田2021 | `张二田2021_朔黄2万t车钩力实测.md` |
| 大秦线车钩力跟踪试验（判据D1-D6，2250kN） | 王鼎2023 | `王鼎2023_大秦线车钩力跟踪试验.md` |
| 货车连挂方式→循环制动冲动 | 王宏宇 | `货车连挂方式对万吨重载列车循环制动过程纵向冲动影响分析_王宏宇.pdf` |

## 多智能体 / 群组协同（MARL）

| 技术/公式 | 来源 | 文件 |
| :--- | :--- | :--- |
| MAPPO 算法 + PopArt value 归一化（returns~1e4-1e5 → value_loss~1e8 数值稳定） | Yu2022 / Hessel2019 | —（无本地，NeurIPS 2022 / AAAI 2019） |
| 多机车 RL + 车钩力 + 多目标（Double-Switch Q） | Tang2020 | `Tang2020_DoubleSwitchQ.pdf` |
| 重载列车群组 + MAPPO（定位最接近；**其自述挑战1 = "reward 软约束无法数学保证车钩力等硬物理约束"，作硬保证通道动机锚**；奖励 = 协同跟踪+势场安全+能耗三段，无车钩项；基线 = 标准 MAPPO、无消融、无安全层） | 宋宗莹2026 | `Song2026_MAPPO_HeavyHaulGroup.pdf`（全文 2026-10-13 入库；`.html` 为旧摘要页） |
| 虚拟编组 + 传统空气制动协同（Tube-MPC，fence 压缩） | 宋宗莹2026 | `Song2026_TubeMPC_VirtualCoupling.pdf` |
| 分层 RL + **状态编码**（累计缓解时间 `t_r` / 车钩力 `f_c` 进状态；空间分段顺序分配） | Wang2026_HRL | `Wang2026_hierRL_fulltext.txt` |
| Dueling DQN 驾驶策略（AB 建立/释放延迟进状态；最小充风约束） | Si2025 | `An-Optimization-Method-of-Heavy-Haul-Train-Driving-Strategy-Based-on-Dueling-DQN.pdf` |
| MASAC + **Mamba 状态预测**（长序列依赖 + 策略不稳） | Hu2026 | `electronics-15-01823.pdf` |
| VCTS + MARL（城轨 CBTC） | Jing2025 | `Multi-Agent Reinforcement Learning Optimization for Virtual Coupled Train Set Problem in CBTC Systems.pdf` |
| 虚拟耦合 MARL（train=agent 分解） | Liu2025 | —（无本地，IEEE ITS Magazine 2025） |
| 车队 MARL 共识控制（间距-8.3%/编队长-19.1%） | Guo2025 | `Guo2025_MARL_PlatoonConsensus.pdf` |
| MADRL 群组一致性（leader-follower + 人工势场） | Zhang2021 | `Zhang2021_MADRL_TrainPlatoon.pdf` |
| 车钩力约束分层框架（最重要对标） | 魏咪2024 | `考虑车钩力约束的重载列车运行优化分层框架与迭代求解方法_魏咪.pdf` |
| LLM 奖励设计框架（源码） | Wei2025 | —（无本地，arXiv:2504.19480） |
| 专家知识+RL 列车运行（源码） | Zhou2020 | —（无本地，arXiv:2003.03327） |
| 车队 DRL 通信框架（源码） | Abdelrahman2021 | —（无本地，arXiv:2312.06858） |

## 安全层 / 虚拟耦合 / MPC

| 技术/公式 | 来源 | 文件 |
| :--- | :--- | :--- |
| ETCS 制动曲线（EBI/SBI 单调表 + searchsorted） | ERA 2020 | `ERA_2020_Introduction_to_ETCS_Braking_Curves.pdf` |
| CBF/CLF + QP 安全控制 | Li2024 | `Safe_Optimal_Train_Formation_Control_in_Virtual_Coupling_Using_Control_Barrier_Functions.pdf` |
| 虚拟耦合综述 | Wu2023 | —（无本地，IEEE TIV 2023） |
| RL 虚拟耦合路线图 | Basile2022 | —（无本地，DAI 2022） |
| 分布式全局复合学习协同控制 | Chen2024 | —（无本地，IEEE TITS 2024） |
| 虚拟耦合 LMPC | Vaquero2025 | —（无本地，CACIE 2025） |
| 改进 MPC 协同控制 | Wang2026（**≠** MARL 表的 `Wang2026_HRL`；本行 = bib `wang2026_cooperative_mpc`） | —（无本地，铁路运输与经济 2026） |
| 单列多体 NMPC 循环制动（Shuozhou） | Yang2025 | —（无本地，IEEE ITSC 2025） |
| **多机车协同 NMPC（长陡下坡）**：多质点模型 + 电/空制动协同 + 车钩力缓代价 + 车钩力/限速/执行器硬约束 + AB 波传播延迟 —— **本项目 MPC 基线来源** | Lu2025 | `Cooperative-Nonlinear-Model-Predictive-Control-for-Multiple-Locomotives-of-Heavy-Haul-Train.pdf` |
| ECP 逐车连续可控假设 + MPC（ECP 假设绕开气动时滞；车钩力作罚项）——ECP-MPC 开山作（**摘要级**） | Zhang & Zhuan 2014（IEEE TCST 22(1):13-22, DOI 10.1109/TCST.2013.2238235） | `Zhang2014_TCST_ECP_MPC.md` |
| 制动模型一阶惯性+纯滞后（**Td=1.0 s, τ=0.4 s**）进状态方程；「制动曲线生成−跟踪」两级；明言 ATO 通常不能直接控制各车厢制动力 | 刘晓宇2022（自动化学报 48(1):171-181） | `Liu2022_ATO_BrakeDelayModel.txt` |
| MILP 速度剖面：空气制动**指令时滞 + 充风时间**显式建模（长大下坡）；刚体模型（无车钩力）；0-1+big-M 线性化 | Yu2023（J. Adv. Transp. 2023:6649871） | `Yu2023_MILP_RefillTime_Downhill.txt`（部分正文：至 §3.3） |
| ECP 车钩力**前馈补偿** + 分布式列队控制（非 MPC；批评 MPC 的 QP 实时性） | Zhang2026（IEEE/CAA JAS 13(4):877-887） | `Zhang2026_JAS_CouplerCompensation.txt`（部分正文：至 §II） |
| 电空协调 MPC：**AB 不进优化变量**、速度误差触发循环「减压-保压-缓解」，车钩力峰降 >8%（**摘要级**） | Zhao2026（IEEE CCDC 2026, DOI 10.1109/CCDC69976.2026.11559852） | `Zhao2026_CCDC_ElectroPneumaticCoordination.md` |
| Shrinking-horizon **输入参数化** MPC（离散模式集化为 NLP） | Farooqi 2018（IFAC-PapersOnLine 51(20):203-208） | `Farooqi2018_ParametrizedMPC.pdf` |
| FSMPC 有限控制集枚举 + **制动级位↔减速度静态映射** + PSO 逐级位辨识时滞 + HMM 预测电空转换（地铁精确停车） | 李蔚2025（铁道科学与工程学报 22(10):4424-4435） | `Li2025_FSMPC_BrakeNotch.txt` |

## 节能 / 其他（Related Work）

| 技术/公式 | 来源 | 文件 |
| :--- | :--- | :--- |
| 最优控制节能（Pontryagin，37%） | Heineken2023 | `Heineken2023_OptimalControl_EnergyEfficient.pdf` |
| 蚁群算法节能 | Yang2024 | `Yang2024_ACSd_EnergyEfficientTrain.pdf` |
| 专家系统+DRL 列车运行 | Huang2025 | `Huang2025_EITO_ExpertSystemDRL.pdf` |
| CACC MARL 节能 | Hua2024 | `Hua2024_MARL_CACC_EnergyEfficiency.pdf` |

## 数值积分（Methods）

| 公式/技术 | 来源 | 文件 |
| :--- | :--- | :--- |
| Davis 阻力 R=(1.5+18/axleW+0.03·mph)·W+0.0018·C·A·V²+20·W·grade（空气项独立于车重） | NeTrainSim + 牵规 | —（无本地，NeTrainSim 源码；代码 `src/train_dynamics/resistance.py`） |
| Newmark-β（β=1/4, γ=1/2）+ Picard 迭代（欠松弛 α=0.5 防发散，收敛取未松弛解） | 李蔚2023 / He2025 / 常崇义 | `重载组合列车纵向力优化的联合制动分析及研究_李蔚.pdf`（He2025/常崇义无本地） |
| 物理子步 ≤0.01s（缓冲器冲击 50-100ms 分辨率） | 项目设计 | —（代码 `src/train_dynamics/train.py`） |
| RK4 长时程交叉基准 | 项目对照 | —（代码 `src/train_dynamics/rigid_multi_particle.py`） |

## 论文正文引用映射（ITSC_PAPER.tex bibitem → 完整文件名）

| bibitem | 文件 | 用途 |
| :--- | :--- | :--- |
| `fu2019` | `Fu2019_CouplerConstraint_HeavyHaul.pdf` | 车钩力上限 1000/2250kN（安全层） |
| `tang2020` | `Tang2020_DoubleSwitchQ.pdf` | 多机车 RL+车钩力基线 |
| `zhao2022` | `重载列车空气制动精细建模与操纵优化.pdf` | 空气制动精细模型 |
| `zhang2024` | `Zhang2024_DQN_CyclicBraking_Downhill.pdf` | RL 循环制动基线（忽略车钩力→创新空间） |
| `liu2021` | —（无本地） | RL 循环制动基线 |
| `wang2025` | —（无本地） | RL 循环制动基线 |
| `zhang2t2021` | `张二田2021_朔黄2万t车钩力实测.md` | 车钩力实测验证锚 |
| `yangmin` | `车钩间隙对重载列车纵向冲击动力学的影响_杨敏.pdf` | 间隙规律验证锚 |
| `lu2025_cooperative_nmpc` | `Cooperative-Nonlinear-Model-Predictive-Control-for-Multiple-Locomotives-of-Heavy-Haul-Train.pdf` | **MPC 基线来源**（多机车协同 NMPC） |
| `fan2024` | `编组方式对3万吨重载列车循环制动工况纵向冲动的影响_樊运新.pdf` | 编组→冲动规律 |
| `wu2023` | —（无本地） | 虚拟耦合综述 |
| `basile2022` | —（无本地） | RL 虚拟耦合路线图 |
| `liu2025` | —（无本地） | train-level decomposition |
| `yang2025` | —（无本地） | 单列多体 MPC 基线 |

## 最新决策（ADR）的文献依据

> 从最新 ADR 提炼的**由文献支撑**的部分（ADR-017 训练/评估时域；ADR-021 MARL 破线修复方向）。ADR 正文 = `docs/logs/decisions/DECISIONS.md`；原始调研条目 = `docs/logs/diagnostics/DIAGNOSTICS_2026-10.md`「调研-2026-10-01」。纪律：**未核实到 DOI 的一律不给编号**（只给 venue/年份）。

### ADR-021 MARL 破线修复方向（2026-10-01）

| 做法 / 结论 | 来源 | 文件 |
| :--- | :--- | :--- |
| AB 最小充风时间进动作空间（"air-refilling time" 约束，治"缓解—再制动"过快循环） | Zhang2024 | `Zhang2024_DQN_CyclicBraking_Downhill.txt:566-577` |
| AB 需求驱动塑形（越限罚 / engaged=0 / 释放奖；本项目 `train_fleet_env.py:822-824` 借其思想） | Zhang2024 | `Zhang2024_DQN_CyclicBraking_Downhill.txt:632-655` |
| 车钩力进 reward 目标（多目标加权） | Tang2020 / Wang2025（ICIRT） | `Tang2020_DoubleSwitchQ.pdf` / —（无本地，DOI `10.1109/ICIRT66379.2025.11216684`） |
| 车钩力进约束集（分层 / MPC；须有可学习的对偶信号，否则无梯度） | 魏咪2024 / 宋宗莹2026（Tube-MPC，车钩力峰 330.4 kN）/ Fu2019 | `考虑车钩力约束的重载列车运行优化分层框架与迭代求解方法_魏咪.pdf` / `Song2026_TubeMPC_VirtualCoupling.pdf`（DOI `10.11860/j.issn.1673-0291.20250156`）/ `Fu2019_CouplerConstraint_HeavyHaul.pdf` |
| 预测式 safety filter（把约束系统变成"无约束安全系统"；补 AB 通道"减"权限） | Wabersich & Zeilinger 2021（Automatica） | —（无本地，arXiv:1812.05506） |
| CBF/CLF + QP 安全控制 | Li, Tong, Giua 2024（IEEE CASE） | `Safe_Optimal_Train_Formation_Control_in_Virtual_Coupling_Using_Control_Barrier_Functions.pdf`（DOI `10.1109/CASE59546.2024.10711420`） |
| **警示**：safety filter 与被保护策略解耦优化 → 冲突/振荡（与本项目 X4-b "缓解—再制动"恶化同源） | Pfrommer et al. 2022（L4DC） | —（无本地，arXiv:2112.13941） |
| per-agent advantage（反事实基线，替换"标量 advantage 广播到全部 agent"） | COMA, Foerster et al. 2018（AAAI） | —（无本地，AAAI 2018） |
| MAPPO 信用解耦（动态拆小子群，可叠加于原生 MAPPO） | PRD-MAPPO, Kapoor et al. 2024（RLJ/RLC） | —（无本地） |
| 有效信用视界 ~1/(1−γλ)；n-step / λ-return 是拉长视界的标准手段 | GAE, Schulman et al. 2016 | —（无本地，ICLR 2016） |

**落地映射（2026-10-01，文献 → 代码；规格 `.trae/specs/implement-literature-informed-fixes/`）**

| 方向 | 落地文件 / 落点 | 备注 |
| :--- | :--- | :--- |
| AB 最小充风时间 | `src/controllers/multi_loco_controller.py`（`get_action_decomposed` 内 `_ab_gate`） | 依据 Zhang2024 运行约束 (1) 的**式 (9)** `t_{b,j+1} − t_{r,j} ≥ T_a`（`docs/papers/02_rl/Zhang2024_DQN_CyclicBraking_Downhill.txt:250-255` / `:287-295`）；`ab_min_refill_s=222.0`（`T_a` 取张二田 S6 最短充风） |
| AB **最小保持时长**（`ab_min_hold_s`）—— **检索后判定"无出处、不激活"（负结果，2026-10-01 结案）** | `src/controllers/multi_loco_controller.py`（同一 `_ab_gate` 的保持半边，默认 `0.0`） | ① **Zhang2024 全文**仅三条运行约束（充风时间式 (9) / 速度限式 (10) / 电制力比例式 (11)），**无**"最短制动保持时长"（已逐条复核 `Zhang2024…txt:246-277`）；② **《铁路机车操作规则》**（铁运〔2012〕281 号，技术规章编号 TG/JW104-2012，国家铁路局公布文本）中最接近的两条均**不构成运行期最小保持时长**：(a)"在长大下坡道前方的列检作业场…自阀减压 100 kPa 并保压 3 min，列车不得发生自然缓解"—— 属**列检站保压试验**，非运行约束；(b)"重载货物列车速度在 30 km/h 以下，不应缓解列车制动"—— 是**速度门限**而非时长，且本项目 `v_min=40 km/h > 30 km/h` ⇒ **在该场景恒不触发（空约束）**；③ 赵紫宁 2022 表 5-3 的制动时长 212/946/1358/918 s 是**实测观测值**，不是下界。⇒ 结论：**不设默认值、接口保留但不激活**；若日后引入"低速段禁止缓解"（上条 (b)），须作为**独立机制**另行验证，勿塞进本参数（口径见 `DIAGNOSTICS_2026-10.md`「检索-2026-10-01…」）。来源仅给文号/编号（无 DOI，不编号） |
| 车钩力受控超限项 | `src/environments/train_fleet_env.py`（`_calculate_reward_decomposed` + `REWARD_SCHEMA`） | 峰值口径改**断面力**；超限项有界（`COUPLER_OVER_W=6.0` / `COUPLER_OVER_CAP=2.0`），刻意避开已回滚的 `-80·ov²` 量级 |
| 安全层对 AB 的禁新增源 | `src/environments/train_env.py`（`_step_decomposed`，`protect()` 之后） | 复用 `SafetyLayer.ab_new_source_veto()`（反应式 `≥0.6·limit` / 预测式 `≥0.9·limit`）；**不撤销**已建立源（X4-b 反证）。⚠️ 首版另有"降一档"梯度臂，**恒被 0.6 硬否决抢先 ⇒ 可证不可达**，已删除（LRN-20261001-007） |
| per-agent advantage + 视界对齐 | `src/algorithms/mappo_agent.py`（`critic` 枚举 / `compute_gae` / `update` / `effective_horizon_s`）；`src/evaluation/evaluate_decompose.py`（`probe_critic_mode`） | 枚举 `centralized_scalar`（默认，零回归）\| `per_agent`；视界 `1/(1−γλ)` 打印并进 metadata（**换算须 ×`decision_interval`×`dt`**）；评估侧按 ckpt 内嵌 `metadata.critic` 重建价值头 |

### ADR-017 训练 / 评估时域（2026-09-16）

| 结论（文献交叉验证） | 来源 | 文件 |
| :--- | :--- | :--- |
| on-policy 单条 rollout 只能短窗口（horizon 1024/512；~1200）；总训练量 1400 episodes 量级 | Guo2025 / Zhang2021 / Hua2024 | `Guo2025_MARL_PlatoonConsensus.pdf` / `Zhang2021_MADRL_TrainPlatoon.pdf` / `Hua2024_MARL_CACC_EnergyEfficiency.pdf` |
| off-policy（DQN）单条可全长：Δt=100s、单集 15 步跑完 23.8km，总训 10 万 episodes | Zhang2024 | `Zhang2024_DQN_CyclicBraking_Downhill.pdf` |
| 训练=短窗口 + 评估=独立完整剖面（combined trip 训 1024 窗 → NEDC 完整剖面 ~3900 步评估） | Guo2025 | `Guo2025_MARL_PlatoonConsensus.pdf` |

### ADR-026 编队间距（ATP 对齐两段式）（2026-10-04）

| 结论 / 公式（文献原文） | 来源（原文出处） | 文件 |
| :--- | :--- | :--- |
| 安全距离随速度**动态变化**（变时距 VTH 范式）：`d_safe(t)=v₀(t)·T₀ + (v₀(t))²/a_max + d_s`；另给上界 `d_max=10+v₀+0.0825·v₀²` | Guo2025 | `Guo2025_MARL_PlatoonConsensus.txt:333-340`（式5）+ 式4 误差趋零 `:294-316` |
| 目标间距设点 + **硬约束** `0 ≤ x_{n-1,n} ≤ d_max`；奖励照势场设计，含**"达成给固定大 +R／碰撞·越界·倒退给 −R"的悬崖式奖惩**，并区分 safe/edge 状态 | Zhang2021 | `Zhang2021_MADRL_TrainPlatoon.txt:299-317`（式2 控制器）、`:341-367`（式4/5 目标与约束）、`:506-534`（reward 设计） |
| 间距奖励**两段式**：平滑跟踪项 `w₁(dᵢ−d*)²` + **仅在逼近停车距离时生效的防撞项** `w₄(2d_s−dᵢ)²` | Hua2024 | `Hua2024_MARL_CACC_EnergyEfficiency.txt:300-305`（式2） |

- **落地映射**：`src/environments/train_fleet_env.py`（`_atp_safe_gap()` + `GAP_EFF_MARGIN/W/SCALE_M` + `GAP_DANGER_W` + `GAP_DANGER_REF_M`，`REWARD_SCHEMA='v4-atp-aligned-gap'`）。决策见 `DECISIONS.md` **ADR-026**（`GAP_DANGER_REF_M`/schema 升 v4 见 **ADR-028**）。
- **对齐关系**：① 安全距离**动态化** ← Guo2025 式5；② **设点 + 越界悬崖（不封顶）** ← Zhang2021 reward 设计；③ **跟踪项 + 独立防撞项两段式** ← Hua2024 式2。
- **差异（声明为 ours）**：`d_safe` **取 ATP 同源 ETCS 制动距离**（`EtcsBrakingCurve.braking_distance`，含制动建立期 + 坡度）而**非**文献 VTH 解析式——因本项目"不触发 ATP"的判据就是该曲线；`d_eff=1.1·d_safe` 裕量、`GAP_EFF_W=3.0`/`GAP_DANGER_W=60.0`/`GAP_EFF_SCALE_M=150` 具体权重与效率项线性衰减形状均为**自研调参**，无文献出处。
- 注：Guo2025 / Zhang2021 / Hua2024 三篇已在 `docs/papers/`（PDF+txt），且已在上文 ADR-017 段登记，不重复加 `refs.bib`。

---

维护：新增引用三处同步（`docs/papers/` + `refs.bib` + 本表）；自研项（winsorization、value grad clip、KL 0.012、5-seed 并行）在论文中声明"ours"，不混入文献。

## ETCS 执行接口复核补充（2026-10-13）

| 技术/公式或实现边界 | 一手来源 | 本地落点 |
| :--- | :--- | :--- |
| ETCS 监督速度/位置并发出制动介入，实际制动系统负责执行；介入映射不能丢失最终安全制动 | ERA_ERTMS_040026 v1.5 §3.1.1–3.1.2；[官方说明](https://www.era.europa.eu/domains/european-rail-traffic-management-system/braking-curves)及[官方原文](https://www.era.europa.eu/system/files/2022-11/Introduction%20to%20ETCS%20braking%20curves.pdf) | `papers/04_safety_mpc/ERA_2020_Introduction_to_ETCS_Braking_Curves.pdf`；`src/environments/train_env.py::_step_decomposed` 执行既有安全层投影。ED=1/0.75 是本项目投影映射，不是 ERA 指定的车辆常数；非完整 ETCS 认证实现。 |

- 2026-10-13 执行补充：本项目 `etcs_permitted` 对应常用制动，接口现将其传给既有空气 SERVICE 档，避免仅加强 ED、空气仍缓解；请求紧急档不降级。SERVICE 档及源优先级映射是项目实现选择，ERA 说明支持监督/执行分工，不规定本列车必须采用这一电空分配；不新增车辆常数或认证结论。

## 电制动前馈试验边界（2026-10-13）

- 自研推导：令 ED 总制动力抵消 `max(Σ(F_grade − F_Davis + F_air_signed), 0)`，能力不足则饱和；使用现有动力学当前坡度、Davis、已生效空气力及 ED 力映射求逆，不移植论文车辆参数、不读取未来轨迹。落点 `MultiLocoController::_grade_feedforward_actions`，默认关闭、独立诊断。
- 动力学来源沿用 `train_dynamics/train.py`、`resistance.py`、`braking.py` 与既有 `VALIDATION_BASELINE.md`；G=9.8066 沿用动力学，24 次二分是数值精度。下限连续投入复用既有控制裕量 0.5 m/s，属工程控制选择，非论文限定值；性能只认真实归档复核，不将静态力平衡等同于动态稳定性证明。

### 近上限普通电制动渐进投入（2026-10-14）

- ed_prelimit：自研规则执行试验，只复用既有AB_SUPPRESS_MARGIN_MPS=0.5m/s构建近上限ED渐进窗口，不是论文规定的提前量，不将10/50秒保持移植为常数。默认关闭，空气/循环阈值及ATP权限不变。真实两万吨60s对照、冻结源和局限见D:/Codex/Documents/Train/controller_extended_20261014/两万吨底层控制器复核.md；不作为论文整线主表证据。
