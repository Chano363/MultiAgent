# 引用索引（技术/公式 → 论文）

> 写论文时的引用速查。每项：技术/公式 → 来源论文 → 本地文件（`docs/papers/` 下完整文件名；无本地文件的标注 arXiv/出处）。引用须锚定外部权威，禁止用本项目历史当外部标准。

## 纵向动力学 / 车钩力

| 技术/公式 | 来源 | 文件 |
| :--- | :--- | :--- |
| MT-2 摩擦式迟滞缓冲器（Stribeck 静750/动500 kN，v_er=0.2，饱和2270kN@83mm）【旧解析口径，已被下行容嘉欣2025 查表口径取代，见 ADR-031】 | 于宗泽2025《重载列车车钩缓冲装置纵向动力学精细化模型》 | `于宗泽2025_fulltext.txt` |
| MT-2 货车装载-缓释阻抗曲线 fl/fu 数字化查表（fl(83mm)=2270kN 锚定）+ 速度法 sign(Δv) 选支（加载→fl、卸载→fu、Δv=0→f0）——当前实现口径 | 容嘉欣2025《更大牵引质量重载列车动力学建模与仿真分析》机械 52(7):57-64 图4(b) | `容嘉欣_更大牵引质量_提取文本.md` + `更大牵引质量重载列车动力学建模与仿真分析_容嘉欣(1).pdf` |
| 车钩间隙死区（0.01m）→ 间隙放大车钩力（60km/h 0.01 vs 0.018m 差 52.14kN） | 杨敏《车钩间隙对重载列车纵向冲击动力学的影响》 | `车钩间隙对重载列车纵向冲击动力学的影响_杨敏.pdf` |
| 车钩力正常/紧急上限 1000/2250kN | Fu2019《基于钩缓约束的重载列车驾驶过程优化》 | `Fu2019_CouplerConstraint_HeavyHaul.pdf` |
| **2 万 t 分工况评定指标（ADR-036 主锚）**：常用/全制动 ≤1500kN、正常运行 ≤1000kN、从控机车偏转角 ≤6°、安全性评定 ≤2250kN；缓解同步性（50kPa 时差 9s / 全制动 30-60s / 紧急 165-280s）；实车峰 1429 压/1748 拉（特例） | 靳新元2018《朔黄铁路2万t重载组合列车在长大下坡道车钩受力分析与应用》神华科技 2018(5):79-83 | `01_coupler_physics/靳新元2018_朔黄2万t长大下坡车钩受力.md`（网络获取全文，无本地 PDF） |
| 多体纵向耦合运行安全框架（超长列车） | Krishna2020 | `Krishna2020_OverlongHeterogeneity_运行安全.md` |
| 缓冲器非线性纵向动力学 | Wang2025 | `Wang2025_LongitudinalNonlinear_缓冲器非线性.md` |
| 20kT 制动纵向动力学（额外尾部充风装置拉钩力 780→489kN，-37%；非普通可控列尾功能，§4.3） | Zhang2025 | `Zhang2025_20kT_LongitudinalDynamics_Braking.pdf` |

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
| 制动波速区间：紧急 **270~280**、常用 **225~255**、缓解 **180~200** m/s | Chen2021（Chen Chunyang et al., *Transportation Safety and Environment*） | —（无本地，doi:10.1093/tse/tdaa019 §2.3） |
| 定压 500/600 kPa：紧急 **266/273**、常用 **198/223** m/s（51 辆）；常用波速沿长度提高、紧急基本一致 | 冯征2016（西南交通大学硕士论文《重载货车空气制动系统建模及仿真》） | —（无本地，CNKI 学位论文） |
| 紧急波前后等速、常用波向前快于向后；两组合列车最大制动时差 −50%、尾部加机车 −75% | 魏伟2007《两万吨组合列车制动特性》，交通运输工程学报 7(6):12-16 | —（无本地） |
| 主管 13.24→17.24 m：尾车减压时间 **+30.75%**、制动缸升压 48.65→58.60 s（编组越长越慢） | 魏伟/杜念博2011，交通运输工程学报 11(5):49-54 | —（无本地，doi:10.19818/j.cnki.1671-1637.2011.05.008） |
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
| 朔黄运营操纵口径（表3 制动/缓解位置：循环减压一律 50 kPa、触发 58–65 km/h、缓解 50–60 km/h、循环期 ED 持 300–400 kN、缓解前抬再生力 ≈900 kN 并保持 50 s、长波制动 14–19 km；表4 主坡度 −10.1/−10.8‰）——规则层标定参数来源，**运营规程数据（operating practice）**，作 literature-anchored rule baseline 依据，非同行评审文献、不称行业标准 | 朔黄铁路运营资料（非同行文献，未编号） | `reference/simulation/data_line/朔黄铁路_完整线路信息表_表3表4补充版.xlsx` |

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
| 重载列车群组 + MARL（GO-MADDPG + MIQP；**单质点模型、全文无车钩力** = 「多列车组 × MARL，缺车钩力」全文级占位；C-LIT-05） | Ma2025（IEEE ITSC 2025） | `Ma2025_MADDPG_HeavyHaulGroup.pdf`、`_fulltext.txt` |
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
| **VC 安全间距范式 = 制动距离内运行**（Shift2Rail TD2.8 冲突控制）——【ADR-061 间距锚】本项目 1.1×EBD 间距比其更保守 | Muniandi 2020, IET ITS 14(6):611-619, DOI 10.1049/iet-its.2019.0694（一手全文核实） | —（无本地） |
| **VC headway 设计族 = 常数最小间距 + 速度比例动态分量；重载 distance headway 困难（误差 716 m/36%）、time headway 更优**——【ADR-061 间距锚】本项目 1.1×EBD 属"制动距离比例"族 | Wu Qing/Ge/Zhu/Cole/Spiryagin 2024, ASME JDSMC 146(4):041008, DOI 10.1115/1.4065401（Crossref 题录核实） | —（无本地） |
| **3.5 万吨重载群组国家实测：重车追踪 1091 m / 空车 943 m @ 60 km/h**——【ADR-061 间距锚】本环境初始净空 885 m 同量级（非循环外部锚） | 包神铁路 2025-12-08 试验（科技日报 + 央视网独立报道；非同行文献，未编号） | —（新闻报道，无本地） |
| RL 虚拟耦合路线图 | Basile2022 | —（无本地，DAI 2022） |
| 分布式全局复合学习协同控制 | Chen2024 | —（无本地，IEEE TITS 2024） |
| 虚拟耦合 LMPC | Vaquero2025 | —（无本地，CACIE 2025） |
| 改进 MPC 协同控制 | Wang2026（**≠** MARL 表的 `Wang2026_HRL`；本行 = bib `wang2026_cooperative_mpc`） | —（无本地，铁路运输与经济 2026） |
| 单列多体 NMPC 循环制动（Shuozhou） | Yang2025 | —（无本地，IEEE ITSC 2025） |
| **多机车协同 NMPC（长陡下坡）**：多质点模型 + 电/空制动协同 + 车钩力缓代价 + 车钩力/限速/执行器硬约束 + AB 波传播延迟 —— **本项目 MPC 基线来源** | Lu2025 | `Cooperative-Nonlinear-Model-Predictive-Control-for-Multiple-Locomotives-of-Heavy-Haul-Train.pdf` |
| **多列虚拟耦合重载 DMPC**：5 列 × 2 万 t（2×HXD2 + 214 C80B、2.7 km、大秦线）；n 质点 + n−1 车钩弹簧-阻尼（d=0）；**in-train force 同时进代价项与硬约束 \|f_in\| ≤ 2000 kN**；fence 法把邻车并刚体降阶（C-LIT-04） | Wang/Zhan/Zhang（IEEE CCDC 2025） | `Wang2025_CCDC_DMPC_VC_HeavyHaul.pdf`、`_fulltext.txt` |
| ECP 逐车连续可控假设 + MPC（ECP 假设绕开气动时滞；车钩力作罚项）——ECP-MPC 开山作（**摘要级**） | Zhang & Zhuan 2014（IEEE TCST 22(1):13-22, DOI 10.1109/TCST.2013.2238235） | `Zhang2014_TCST_ECP_MPC.md` |
| 制动模型一阶惯性+纯滞后（**Td=1.0 s, τ=0.4 s**）进状态方程；「制动曲线生成−跟踪」两级；明言 ATO 通常不能直接控制各车厢制动力 | 刘晓宇2022（自动化学报 48(1):171-181） | `Liu2022_ATO_BrakeDelayModel.txt` |
| MILP 速度剖面：空气制动**指令时滞 + 充风时间**显式建模（长大下坡）；刚体模型（无车钩力）；0-1+big-M 线性化 | Yu2023（J. Adv. Transp. 2023:6649871） | `Yu2023_MILP_RefillTime_Downhill.txt`（部分正文：至 §3.3） |
| ECP 车钩力**前馈补偿** + 分布式列队控制（非 MPC；批评 MPC 的 QP 实时性） | Zhang2026（IEEE/CAA JAS 13(4):877-887） | `Zhang2026_JAS_CouplerCompensation.txt`（部分正文：至 §II） |
| 电空协调 MPC：**AB 不进优化变量**、速度误差触发循环「减压-保压-缓解」，车钩力峰降 >8%（**摘要级**） | Zhao2026（IEEE CCDC 2026, DOI 10.1109/CCDC69976.2026.11559852） | `Zhao2026_CCDC_ElectroPneumaticCoordination.md` |
| Shrinking-horizon **输入参数化** MPC（离散模式集化为 NLP） | Farooqi 2018（IFAC-PapersOnLine 51(20):203-208） | `Farooqi2018_ParametrizedMPC.pdf` |
| FSMPC 有限控制集枚举 + **制动级位↔减速度静态映射** + PSO 逐级位辨识时滞 + HMM 预测电空转换（地铁精确停车） | 李蔚2025（铁道科学与工程学报 22(10):4424-4435） | `Li2025_FSMPC_BrakeNotch.txt` |
| **虚拟编组协同巡航的目标速度 = 75 km/h（= 线路限速本身）**；6 列单元列车 50 km 内收敛；速度域 40–120 km/h 时运能 +18%~28% ——【参考速度锚】 | 基于多智能体的重载列车虚拟编组协同巡航控制（在线，未编号） | —（无本地，[国家科技期刊平台](https://opaj.napstic.cn/periodicalArticle/0120240100316778)） |
| **VC consensus 参考速度序列 40→70（cruise velocity）→50→30→50→70** ——【参考速度锚】巡航 70 = 限速 −5 | W 2025, Int. J. Control, doi:10.1080/00207179.2025.2564448 | —（无本地） |
| **MAPPO 重载组 vref(t) 五阶段：19.5 m/s（70.2 km/h）高速巡航 / 11.1 m/s（40）低速巡航** ——【参考速度锚】目标是时变剖面而非标量 | 宋宗莹2026 MAPPO（本地全文） | `03_formation/Song2026_MAPPO_fulltext.txt:684-702` |

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

## 论文正文引用映射（原 ITSC_PAPER.tex bibitem → 完整文件名；论文稿已于 2026-10-19 删除，映射保留备重写引用）

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

### ADR-036 2 万吨车钩力指标档位化（2026-10-14）

| 做法 / 结论 | 来源 | 文件 |
| :--- | :--- | :--- |
| 2 万 t 分工况评定指标：常用/全制动 ≤1500kN、正常运行 ≤1000kN、偏转角 ≤6°、安全评定 ≤2250kN（**档位主锚**） | 靳新元2018《朔黄铁路2万t重载组合列车在长大下坡道车钩受力分析与应用》神华科技 2018(5)（无 DOI，不编号） | `docs/papers/01_coupler_physics/靳新元2018_朔黄2万t长大下坡车钩受力.md` |
| 实车反证"1000 全工况硬顶"：长大下坡 11/19 超 1000、峰值均值 1021/最大 1429（<1500）；≤−7‰ 全程 <1000 | 张二田2021（同线同编组实测） | `01_coupler_physics/张二田2021_朔黄2万t车钩力实测.md` |
| 2250 kN 安全限值 46 趟实车判据 | 王鼎2023 大秦线 | `01_coupler_physics/王鼎2023_大秦线车钩力跟踪试验.md` |
| 1000/2250（正常/紧急）两档互证 | Fu2019 | `01_coupler_physics/Fu2019_CouplerConstraint_HeavyHaul.pdf` |
| **不进指标论证链**：Song2026 ±1000kN（弹簧-阻尼钩缓/全周期场景/编组不同源，只作"以 1000 为目标"先例背书） | Song2026 MAPPO | `03_formation/Song2026_MAPPO_fulltext.txt` |

### ADR-021 MARL 破线修复方向（2026-10-01）

| 做法 / 结论 | 来源 | 文件 |
| :--- | :--- | :--- |
| AB 最小充风时间进动作空间（"air-refilling time" 约束，治"缓解—再制动"过快循环） | Zhang2024 | `Zhang2024_DQN_CyclicBraking_Downhill.txt:566-577` |
| AB 需求驱动塑形（越限罚 / engaged=0 / 释放奖；本项目 `train_fleet_env.py:822-824` 借其思想） | Zhang2024 | `Zhang2024_DQN_CyclicBraking_Downhill.txt:632-655` |
| 车钩力进 reward 目标（多目标加权） | Tang2020 / Wang2025（ICIRT） | `Tang2020_DoubleSwitchQ.pdf` / —（无本地，DOI `10.1109/ICIRT66379.2025.11216684`） |
| reward 槽位骨架：带内平顶正奖 / 带外罚 / AB 参与 0 / 缓解正奖（本项目 v6 借其形） | Zhang2024 | `Zhang2024_DQN_CyclicBraking_Downhill.txt:632-657`（式22） |
| 车钩力峰值比进 reward（有界饱和形；**本项目取形并修正其单调方向**——原文 `−exp(−f/F)` 方向反常） | Wang2026 | `Wang2026_hierRL_fulltext.txt:784-794`（式17） |
| 充风时长约束进 reward（`Rb` 第二分支，本项目 obs[11] 充风就绪度同源） | Wang2026 | `Wang2026_hierRL_fulltext.txt:770-783`（式16） |
| 编队奖励保持 3–5 项目标 + 约束下沉动作空间/安全层（奖励复杂度上界依据，ADR-043） | Song2026 / Hua2024 / Guo2025 | `Song2026_MAPPO_fulltext.txt` / `Hua2024_MARL_CACC_EnergyEfficiency.txt` / `Guo2025_MARL_PlatoonConsensus.txt` |
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
| 奖励槽位对齐文献（v6，13 项→6 槽位） | `src/environments/train_fleet_env.py`（`REWARD_SCHEMA='v6-literature-slots'`） | 速度带形取 Zhang2024 式22；车钩峰值比取 Wang2026 式17（修正单调方向）；AB 需求锚补强为 Wang2026 式16 `Rb`；删车钩均值项（改为峰值口径）。见 ADR-043 |
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

- ed_prelimit：自研规则执行试验，只复用既有AB_SUPPRESS_MARGIN_MPS=0.5m/s构建近上限ED渐进窗口，不是论文规定的提前量，不将10/50秒保持移植为常数。默认关闭，空气/循环阈值及ATP权限不变。真实两万吨60s对照、冻结源和局限见external_archive/controller_extended_20261014/两万吨底层控制器复核.md；不作为论文整线主表证据。

### 赵紫宁2022参数迁移复核-2026-10-17

上述C_beta段间归一化条目仅说明当前实现来源，不构成普适衰减规律的实测证明。原文第20页式3-4至3-10将C_beta与历史操纵修正P_s(t)区分；第50—51页表5-3至5-5参数来自特定连续三段实车工况辨识。当前braking.py按制动段号取1/.705/.676并在第三段饱和是项目简化假设，其在50kPa短循环、朔黄49.6km下的迁移仍待标定核对。不得省略工况直接宣称原文验证了本实现。见本月诊断“接手后Y2触发语义恢复与制动力依据复核”。

### 空电匹配与缓解后电制动连续性原文复核-2026-10-17

- 马志强、王竣渝、魏咪、王青元：《重载列车平稳运行的空电联合制动匹配控制》，《机车电传动》2023(4):71—76，DOI 10.13890/j.issn.1000-128X.2023.02.103。本地原文提取external_archive/paper/底层控制瓶颈专项调研/原文复核_20261014/重载列车平稳运行的空电联合制动匹配控制.txt，式(8)为各车力平衡；§3.3明确空电联合制动时用ED调整速度、开始缓解时恒持ED50s。原文未要求50s后立即归零。当前候选保留50s，再调用既有_grade_feedforward_actions提供净需求ED；文献支撑操纵原则，候选仍需当前模型动态验收。
- 魏伟、张益铭：《2万吨重载组合列车操纵优化研究》，《铁道机车车辆》2021,41(4)，DOI 10.3969/j.issn.1008-7842.2021.04.06。原文编组为HXD1+108C80+HXD1+108C80+可控列尾，案例K20+400—K34+881，并非本项目49.6km全线；69/65km/h、50kPa、340kN等属该实车序列，未移植为本项目控制参数。原文强调空气减压显示/实际值可能存在差异，不能用名义50kPa直接证明模型实际制动力正确。


### 周期制动速度余量与制动性能差异检索入口-2026-10-18

- 林轩等2017《HXD2牵引货运列车长大下坡区间周期性制动研究》，西南交通大学学报52(5):859—868，DOI10.3969/j.issn.0258-2724.2017.05.004，[出版社](https://xnjdxb.swjtu.edu.cn/cn/article/doi/10.3969/j.issn.0258-2724.2017.05.004)。仅摘要核实HXD2+100辆C80、50kPa、再充风约束及周期切换研究；用于确定下一步检索问题，不是108辆参数/车钩验收依据。全文待获取。
- 肖致明等2023《考虑制动性能差异的重载列车模式化操纵方法》，机车电传动(1):24—32，DOI10.13890/j.issn.1000-128X.2023.01.004，[出版社](https://edl.csrzic.com/zh/article/doi/10.13890/j.issn.1000-128X.2023.01.004/)。仅摘要核实50kPa等效效率与北大牛—原平南操作边界研究；全文、编组和公式待核实，不能将该区间等同本项目49.6km。两篇题录登记refs.bib和papers/README，未取得本地PDF，不冒充全文已读。


### 新增中文全文实物与关键章节复核-2026-10-18

此前待全文条目为当时库存状态。现已取得林轩中文10页、董克毓4页、黄宇澄119页、肖博懿95页、李彬卓100页，权威原件位于external_archive/paper/万吨108节_再制动压力建立专项/20261018/原文PDF/；来源SHA与带PDF页码文本见同目录原文复核_补充全文_20261018/source_manifest.json。重点核对而非逐页精读：林轩PDF3式(9)充风时间及PDF4缓解速度上界（130秒为本文取值）；黄宇澄PDF34—35/42—43的最低缓解速度、最小缓解时间、转换点条件；董文三机116辆、580kPa判据的68—76秒不用于单机108辆。李文基础模型双机50辆C70E，肖文主对象两万吨，均只筛读适用范围、不迁移数值。题录见docs/refs.bib。

209.5秒为候选缓解到超速窗口，非充风完成时间；当前模型未显式实现完整副风缸再充气动态，不能用制动缸系数反推580kPa时间。修复先查允许缓解速度上下界及充风/下次压力建立余量，保留222秒和1000kN。原文页图与详细解释见traffic_rl_project/docs/reports/controller_takeover_20261017/新增全文复核与缓解可行性修复依据_20261018.md。


### 缓解预测误差与数值收敛定向检索-2026-10-18

Zhou/Shi/Hecht，Vehicle System Dynamics60(7):2436—2450，2022（在线2021），DOI10.1080/00423114.2021.1901943：已通过佛罗伦萨大学作者仓储网页读取16页含封面的预印本，讨论不同摩擦迟滞过渡与积分收敛；直接下载受站点验证拦截，未存本地PDF。不能把文中0.1/0.2ms或1ms直接规定为本项目步长，更不能据此断言当前模型错误。[作者仓储](https://flore.unifi.it/retrieve/b71cbe68-acf7-4b44-87f4-fdb45a5f1c56/Comparison%20of%20friction%20draft%20gear%20models%20for%20simulation%20in%20longitudinal%20train%20dynamics_V2025.pdf)。

下一步需原文的方法线索：郭炎冰等《一种用于重载列车纵向动力学仿真的变步长积分算法》，铁道车辆2023,61(3):147—152，题录已由肖博懿PDF92—93参考文献50核实；Wu等国际LTD基准结果，DOI10.1080/00423114.2017.1377840，全文待取。题录见refs.bib；现有lei2019_gooa.pdf不重复下载。MIS检索任务traffic_rl_project/docs/reports/controller_takeover_20261017/TraeWork_缓解预测与数值收敛定向检索_20261018.md。用途为验证与误差评估，不是算法创新或当前车钩模型改动依据。
### 2026-10-19 缓解保持与可行性原文再核对

马志强等2023（DOI10.13890/j.issn.1000-128X.2023.02.103），本地PDF `external_archive/paper/重载列车平稳运行的空电联合制动匹配控制.pdf`；提取文本 `external_archive/paper/万吨108节_空电协调专项/提取文本/重载列车平稳运行的空电联合制动匹配控制.txt`。PDF3式4为力/力变化约束，PDF4式7给定空气制动力下恒速可行条件，§3.3明确缓解后恒持**电制动力50秒**；PDF5结论背景为二万吨。原文没有给出本候选“25%力目标”或“30秒保持”；30秒只是同状态诊断的规则偏离，未获单机108辆适用性依据。静态全ED仍加速不等于证明整个222秒周期无解；后续需联合检查空气制动动态与ED力值/变化约束，不能只调缓解速度。bib补登记 `ma2023_braking_matching`。

### 2026-10-19 新增全文：缓解恒持力与充风时间定义

于岩/魏伟2023 DOI10.13711/j.cnki.cn32-1836/u.2023.04.001，原PDF3已看图，二万吨双机加列尾；支撑坡段筛选加动态验证及缓解后ED不变，不搬公里标/18—50秒峰值时窗。孙中央/王长明2009《铁道机车车辆》29(1):4—7，PDF1式1与PDF2增速验算已核，双机5000吨/约60辆，不搬充风秒数或30km/h缓解速度。郭炎冰等2023 DOI10.3969/j.issn.1002-7602.2023.03.026已获全文，PDF5已看图，108辆C70E平道全制动及特定算法步长对照，不代表当前模型已验证或必须改用其步长。以上取代旧“郭文全文待取”的当前状态；bib为yu2023_daqin_release_location/sun2009_long_downhill_safety/guo2023_variable_step_ltd。原PDF均在external_archive/paper；带页码提取、关键页图和SHA清单在external_archive/paper/新增全文复核_20261019。8份全文已提取不等于全部逐页读完；当前重点复核上述控制/数值章节，陈清扫描文关键数字有识别缺失，未采用其参数。保持力的25%/50%/75%比例均为本地诊断，原文没有规定这些比例。

2026-10-19新增本地全文复核：常崇义等2026（DOI10.19818/j.cnki.1671-1637.2026.197，PDF9—10平衡迭代）与熊芯等2025（DOI10.16385/j.cnki.issn.1004-4523.202506045，PDF6式11）。Bib键chang2026_ltd_progress/xiong2025_realtime_ltd。来源和方法适用边界见traffic_rl_project/docs/reports/controller_takeover_20261017/新增论文与联合容差收敛复核_20261019.md；三份PDF及哈希文本在D盘paper/数值积分收敛专项/原文复核_20261019。未复制车型参数，不将摘要或检索建议当已读全文。

2026-10-19文献状态：Zhou2022（DOI10.1080/00423114.2021.1901943）已再次通过大学官方仓储网页读16页预印本相关正文，非只有摘要；本地PDF下载仍受站点验证拦截，未用MIS。原文切换/效率讨论不等于本项目tanh模型错误或其步长可直接移植。原刊入口https://www.tandfonline.com/doi/full/10.1080/00423114.2021.1901943 ，仓储https://flore.unifi.it/handle/2158/1258138 。待补的2006平衡迭代、1990预测校正全文与具体提取项见D盘最新TraeWork_MIS力时程精度与计算效率专项_20261019.md。

### 2026-10-31 缓解恒持力与循环相位：原文再核对

Ma2023（上文已登记）本地提取文本§3.3再次核对：缓解开始后恒定电制动力50秒。He2025（bib键he2025_cyclic_ga、DOI10.1108/RS-11-2024-0048）已通过出版社官方完整HTML重读§4.1—4.3及图7、表2：将一个循环分成三个常值电制动力区段，缓解前后一段保持不变，并联合选择缓解点与电制动力；不是只读摘要。方法线索用于审查当前诊断方案，未直接改正式控制器。

适用边界：He文为HXD1+C80×105+HXD1+C80×105+EOT的两万吨组合列车，与本项目三列独立1+108不同；13%等数值不迁移。Ma文50秒不构成单机108辆通用定标。独立试验round149在缓解残余气制动力阶段连续减载ED，不满足当前恒持语义，且预筛平均列距和速度差均变差，明确否决、未做正式/原生控制策略采纳。round148的49.5km/h仅近似预筛出现安全接管，不宣称真实多体已失败。

750秒真实多体局部验收及后续预筛证据见traffic_rl_project/docs/reports/controller_takeover_20261017/领航49缓解_后续联合核验_20261031.md；下一轮单机恒持力/三列相位针对性补证指令见同目录TraeWork_缓解恒持力与三列相位协调_20261031.md。官方原文：https://www.emerald.com/rs/article/4/2/231/1241699/Research-on-optimization-and-evaluation-method-of 。未声称使用MIS登录。

### 2026-10-31 本地全文与公式符号独立复核补记

He2025完整18页PDF已确认位于docs/papers/01_coupler_physics/rs-11-2024-0048.pdf，D盘本轮副本SHA089A0B77BCEA8F993C6CD2671308F6FDEAD905A20F15EFA745E1A6DF5948D2C3；此前“无本地/只读网页”的条目为当时库存或阅读状态，不再代表当前全文状态。原页核对PDF8/表1为两机各108辆、21000t的验证工况，PDF12/表2为各105辆、20000t优化工况，不混用。

Ma2023 PDF2式(1)、PDF3式(4)、PDF4式(7)及§3.3已看原页；报告中页码和匹配力符号已在独立说明纠正。代码按自身G为下坡正方向的约定使用E_req=G-R-B：负值代表零ED仍减速，超过ED能力代表满ED仍加速；瞬时解不等于50秒/222秒周期可行。另一文献461kN曲线不得直接覆盖当前原生模型。完整说明和原页图在external_archive/paper/缓解恒持力与三列相位协调_20261031/独立核对/独立复核与修订说明_20261031.md。已做只读受力分类round156，未更换正式机车物理、规则默认或宣称三列相位问题已解决。

### 2026-11-01 动态限速接口与跨充风可行性：诊断边界

继承原生线路/动力学，独立诊断修复了当前SBI低于固定76km/h升级门的接口问题，并按现有模型服务波、剩余建压和ED过渡时间做趋势预览；不将其写成文献标定参数或硬安全证明。80秒原生局部通过（峰值895.452kN、0接管）后，后续62.1秒第三列在充风剩余140.9秒、ED已满时仍触SBI：所需ED约903.51kN>可用547.24kN。说明尚需在缓解前做完整充风窗口的联合可行性规划，不能短时通过就宣布规则层修完。领航车头已超出地图，模型延长段与真实线路结论分开。

公开核实的待全文目标：DOI10.1080/00423114.2024.2393354（VSD63(1):121—139，卷期2025/在线2024），以及DOI10.3390/electronics15204606（Electronics2026,15(20):4606）。尚未取到全文，不作为本次控制器算法或参数的既有原文依据；现有Wang2026参考文献的第一篇作者表与出版社页面不一致，题录以DOI原刊核对。详细证据traffic_rl_project/docs/reports/controller_takeover_20261017/动态跟驰限速升级修复_20261101.md；精确检索任务同目录TraeWork_动态跟驰限速与气动响应提前量_20261101.md。未宣称使用MIS或完成全程/训练验收。

## ADR-064 训练设置证据组（2026-11-11 在线检索；**无本地全文**，条目仅作口径证据，不作物理标定依据）

> 用途：回答"训练 episode 怎么定义 / 决策间隔多大 / 集数多少 / 状态是否含绝对位置"。
> 纪律：本组文献**不下载到本地**（用户 2026-11-11 指示），引用时给 DOI/arXiv ID；标 ★ 者为读到全文或详细设置，其余为摘要/元数据级。

### A. 同领域（列车 / 重载）训练设置

| 结论 / 技术点 | 来源 | 出处（无本地文件） |
| :--- | :--- | :--- |
| ★ 一集=整条线路到终点；`s_k=[P_k,V_k,T_k]`（含位置+累计时间）；**Δt=100 s**；Table「Maximum training episode M=100 000」，正文实验展示 10 000 集；收敛判据=累计奖励平台+波动收窄 | Zhang2024（DQN 循环制动；本项目本地另有 Algorithms 17(5):190 全文，同组工作） | TR-C 2021, doi:10.1016/j.trc.2021.103226（本地已有 Algorithms 版 `02_rl/Zhang2024_DQN_CyclicBraking_Downhill.txt`） |
| ★ 环境交互 **1e6 次 / 1e5 集 ⇒ 每集仅 ≈10 步** | Zhang2024 Q-learning（同组） | `02_rl/Zhang2024_QLearning_fulltext.txt`（本地全文） |
| ★ 一集=**固定 700 s 窗**；**ΔT=10 s**；Maximum training episode **2.5×10⁵**；状态含 `X_k`（位置矩阵） | Si2025 Dueling DQN | Information 2024, 15(5):271（本地 `02_rl/Si2025_DuelingDQN_fulltext.txt`） |
| ★ 分层 RL，一集=一个 task segment；10/20/50 km 对应收敛 2500/3200/**>5000 不收敛**；"**决策步长故意设大以限制每集决策数**，物理积分在子步做"；状态含 `x, t_b, t_r, f_c` | Wang2026 | IET ITS 2026, doi:10.1049/itr2.70254（本地全文） |
| ★ **MAPPO**，一集=12 列车跑完整条线路（12 站 11 区间）；**10 000 集**；训练≈4.8 h；状态含时空量；训练与测试同一固定场景 | Tang2026 | Sci Rep 2026, 16:19300, doi:10.1038/s41598-026-50132-x |
| ★ 一集=一次站间运行（≈101 s）；**决策间隔 0.02 s ⇒ ≈5 050 步/集**；**约 80 集收敛**；状态含（位置，速度，剩余时间） | Huang2025（PPO，地铁 ATO） | PLoS ONE 2025, 20(5):e0323478, doi:10.1371/journal.pone.0323478 |
| ★ `Experience horizon 1024 / 512`、`Clip 0.2`、`Entropy loss 0.01`（**ADR-017「1400 集」的原始出处**） | Guo2025 | 本地 `03_formation/Guo2025_MARL_PlatoonConsensus.txt` |
| APF-MAPPO 训练 **2000 集**收敛（0–500 探索 / 500–1200 上升 / 1200+ 稳定） | Song2026 | 本地 `03_formation/Song2026_MAPPO_fulltext.txt` |
| 每集 **T=20 步**、K=10 策略更新步、L=78–80 迭代 | Jing2025 VCTS | 本地 `03_formation/Jing2025_VCTS_fulltext.txt` |
| "Hundreds of steps make up one training episode"；E=200 集；状态 `(δ_{n-1,n}, ν_{n-1,n})` **相对间距/相对速度，不含绝对位置** | Zhang2021 MADRL | 本地 `03_formation/Zhang2021_MADRL_TrainPlatoon.txt` |
| 状态 `[v, v_diff, v_h, d, u]` **全相对量，不含绝对位置** | Hua2024 MARL-CACC | 本地 `03_formation/Hua2024_MARL_CACC_EnergyEfficiency.txt` |
| 训练分三阶段（边界 ep350 / ep600） | Hu2026 PMMASAC | 本地 `03_formation/Hu2026_PMMASAC_fulltext.txt` |
| 重载 RL 声称克服"仅限特定工况/缺前瞻" | rHHT（IEEE 2026, doc 11642769） | DOI 待核（仅元数据级） |
| PER-DDQN 重载自动驾驶 | Xie et al. 2025, ICNSC 2025:261-266 | DOI 待核 |
| DQN 重载纵向冲动抑制（长大下坡循环制动） | IEEE 2025, doc 11216684 | DOI 待核 |
| 重载港口站双智能体 Actor-Critic（调度+资源） | MDPI Systems 2025, 13(9):762 | DOI 待核 |

### B. 方法论（决策间隔 / episode 长度）

| 结论 / 技术点 | 来源 | 出处 |
| :--- | :--- | :--- |
| ★★ **Frame-skip d 与 γ 必须联合调整**（Acrobot/Sarsa(λ)/8 000 集）：γ=0.9 时 d=1 −123.1 → **d=2 −346.6（恶化 2.8×）**；γ=0.999 时 d=1 −95.8、**d=3 −72.7（最优）**、d=5 −81.4。"惯性代价" `Δ_M ≤ 4R_max`，并给 `‖V*−V*_{M_d}‖_∞ ≤ Δ_M(1−γ^{d−1})/((1−γ)(1−γ^d))`；d>1 不影响渐近一致性 | Kalyanakrishnan et al. 2021 | arXiv:2102.03718（CC BY 4.0） |
| ★ 折扣随控制间隔换算：`γ=exp(−τ·dt)`，`τ=−log(γ_base)/dt_base`（基准 dt=0.05 s、γ=0.98）；SAC/FiGAR-SAC/DAC-PPO **性能随交互频率升高明显下降**；30 seeds | Karimi et al. 2022（IROS, CTCO） | arXiv:2212.04407 |
| ★ 控制时长改为可学变量后交互 **200→24（−88%）**、有界 `K=5` 次完成摆起；标准 SAC 高频性能显著下降，TaCoS 对 t_min 稳健 | Treven et al. 2024（NeurIPS, TaCoS） | arXiv:2406.01163 |
| PPO 长 rollout 必须截断，且截断内部靠前步偏差显著更大（Partial GAE） | Jin et al. 2025 | IEEE ToG, doi:10.1109/TG.2024.3408298 |
| 慢决策频率的难点=序列内每个 primitive action 都要有学习信号；提出 FAS 指标 | Patel & Siegelmann 2025（ICLR） | arXiv:2410.08979 |
| **Episode 长度自适应（先短后长、熵驱动）**；机理=同数据量下短集切出更多轨迹、探索多样、避免 dead-end 空转 | Yoo et al. 2025（AELA） | arXiv:2505.19637 |
| 长视界 PPO 的 temporal credit assignment 不稳定 → 序列级 bandit + 单标量 baseline | SPPO 2026 | arXiv:2604.08865 |
| 固定控制频率是刚性约束；最优频率任务相关 | Wang & Beltrame 2024 | arXiv:2407.00290 |
| 动作重复帧的再利用（pseudo-actions） | Hashimoto & Tsuruoka 2021 | arXiv:2105.03041 |
| 大规模并行 on-policy 的 reset 策略与 horizon 显著影响训练 | Staggered Environment Resets | OpenReview（作者待核） |
| 卡车编队 MARL 协调（大规模路网） | Wei et al. 2024 | arXiv:2412.01075 |
| DDPG 虚拟连挂异质高铁；LMPC 虚拟连挂 | Basile et al. 2024 / arXiv:2507.02383 | doi:10.1016/j.engappai.2024.108120 |
| VCTS 多智能体协同运行策略 | Liu et al. 2024 | IEEE ITSM 17(4) |
| MARL 虚拟连挂 CBTC 三场景 | Jing et al. 2025 | Tsinghua Sci Tech, doi:10.26599/TST.2025.9010067 |
| 多步前瞻 DRL 列车调整（节能） | Zhang et al. 2025 | Eng Appl AI, doi:10.1016/j.engappai.2025.110181 |
| 安全 DRL 列车协同节能（再生制动约束） | Applied Intelligence 2025 | doi:10.1007/s10489-025-06542-x |

## 车钩力阈值与实车基准组（2026-11-12 检索；**均无本地文件**，供 ADR-066 口径纪律与 VALIDATION_BASELINE 附录 C 引用）

> 用途：确认「1000 kN 属于哪一档工况」「实车能做到多少」「朔黄人工优化达成水平」「文献 RL 用什么口径」。
> 纪律：只在 `VALIDATION_BASELINE.md` 附录 C 记数据；本表只记**来源与出处**。

| 结论 / 技术点 | 来源 | 出处 |
| :--- | :--- | :--- |
| ★ **阈值分级原文**：正常运行 ≤1000（建议性）、常用全制动 ≤1500（建议性）、从控机车 ≤2000、C70 货车 ≤2250（安全限） | C70A 单元万吨列车试验研究 | `zzcbjt.com/index.php/lbd-2-12-21687`（中卓出版，无本地文件） |
| ★ **实车 >1000 占比**：2014/232 辆 34 次中 **73.5%**（>1500 占 20.6%，最大 2142）；2015/216 辆 19 次中 **58%**（最大压 1429、拉 1358） | 铁科院 2 万吨动态试验（经铁道职培转述） | `mlzp.cc/forum.php?mod=viewthread&tid=47901`；交叉：`chinacaj.net/SBMT/201805/408617.pdf`（朔黄 2 万 t 长大下坡车钩受力分析） |
| ★★ **朔黄优化后达成**：平均最大车钩力 1021 → **806 kN**；超 1000 占比 42.1% → **10.7%**；11 版操纵提升卡、攻克 20 项难题 | 朔黄铁路官网（安全开行八周年，2024-03） | `shtl.shenhuagroup.com.cn/shshtl/1382684311310/202403/d2c0545147ab466fbf1b3abecef89373.shtml` |
| ★ **制动次数 19 → 12 次**；「提前低速减速」改「后期精准高速制动」 | 河北新闻网（崔帅文，2026-06） | `hebei.hebnews.cn/2026-06/16/content_9525108.htm` |
| 充风时间**精确到秒**、空气制动压力**卡控到 1 kPa**；130 km 下坡 12 次循环 | 河北新闻网（2024-02） | `m.hebnews.cn/jt/2024-02/21/content_9141282.htm` |
| 4.0 智能操纵策略：**平均车钩力稳定在 1000 kN 以内**；主动停车缓风率 59% → 21% | 中国能源新闻网（2026-08） | `cpnn.com.cn/qiye/fadianPD2023/202608/t20260806_1906692.html` |
| 4 万吨无线同步操控仿真：常用全制动最大压钩 **1390.3 kN**（近 1500 阈值）、紧急制动 **1473 kN**（<2250） | 中国高校科技期刊集群服务平台 | `cjournal.hep.com.cn/1001-4632/CN/10.3969/j.issn.1001-4632.2026.04.13` |
| **文献 RL 口径**：Wang2026 *"the **maximum** tensile and compressive coupler forces are both constrained within 1100 kN, with **average** values of 72.82 and −105.91 kN"*；表 4 并列 Average(40.43/−90.32) 与 Maximum(315.67/−301.96) | Wang2026 IET ITS | 本地全文 `docs/papers/02_rl/Wang2026_hierRL_fulltext.txt` L1204-1207、表 4 |
| 王建华等 2023：RL 优化「有效减小纵向冲动与最大车钩力」，**未给数值** | 机车电传动 2023(6):139-146 | doi:10.13890/j.issn.1000-128X.2023.06.017 |

### 追加组（2026-11-12 二轮检索；阈值性质 + 循环次数杠杆，供 `LITERATURE_FINDINGS.md` §八 引用）

> 纪律同上：本表只记**来源与出处**，数据解释在 §八。`[W]` = 在线原文/摘要，可复核 URL，**无本地全文**，不得写成本地逐行引用。

| 结论 / 技术点 | 来源 | 出处 | 级 |
| :--- | :--- | :--- | :--- |
| ★ **建议性指标原文四条**：正常运行 ≤1000、常用全制动 ≤1500、从控机车偏转角 ≤6°、安全性评定 ≤2250 | 《朔黄铁路 2 万 t 重载组合列车在长大下坡道车钩受力分析与应用》，中国煤炭 | `chinacaj.net/SBMT/201805/408617.pdf` | W |
| ★★ **「目前尚无相应的国家标准或铁道部标准」**，铁科院建议：紧急制动 ≤2250、正常运行（除紧急制动外）≤1000、纵向加速度 ≤1 g | 西南交大硕士论文《起伏坡道对两万吨重载列车制动工况影响分析》 | `renrendoc.com/p-31581722.html` §2.5 | W |
| 1000（正常运行）/2250（紧急制动）；安全评价模型 `F_NUM=Σβi`（超限计数，γ∈0.75~1）、`F̄_MAX`（多次运行最大拉钩力均值）、加权 `f_s` | Fu2019《基于钩缓约束的重载列车驾驶过程优化》自动化学报 | `aas.net.cn/cn/article/pdf/preview/10.16383/j.aas.c190223.pdf`；本地 PDF `01_coupler_physics/Fu2019_CouplerConstraint_HeavyHaul.pdf` | W+本地 |
| 2250 出自 *Standard on Strength Design and Accreditation Test of Railway Vehicles (1996)*；40 kt 在 13‰ 变坡差下最大压钩 **2091 kN**；同步控制延时每 +1 s 约 +200 kN | Chang2023, Railway Sciences 2(4):495-513 | doi:10.1108/RS-09-2023-0028 | W |
| ★ **「车钩力峰值主要出现在制动缓解与拉压转换阶段，纵向力可达 1100~1300 kN」**；7 条典型长大下坡线型 | 《重载列车循环制动工况动态车钩力作用下的车钩强度校核分析》机械设计与研究 2026(4):378-385（国能朔黄 + 华东交大） | `mqikan.cqvip.com/article/ArticleDetail?id=7204413716` | W |
| ★ 循环 **5→4 次：压钩 1161.5→849.7 kN（−27%）、拉钩 1483.0→1436.6 kN（基本不变）**；凸形变坡常用制动最大拉钩 **1933.4 / 2106.9 kN 超 1500**，调整制动位置或仅用电制动可回归 | 郭刚2026《无线同步操控下 4 万 t 重载组合列车纵向动力学仿真研究》中国铁道科学 47(4):171-182 | doi:10.3969/j.issn.1001-4632.2026.04.13（表 9/表 10） | W |
| 四把闸 → 两把闸：最大拉钩 **−32.1%**、压钩 **−11.4%**（TABLDSS 仿真） | 《2 万吨重载组合列车操纵优化研究》铁道机车车辆 | `tdjc.cbpt.cnki.net`（篇名检索） | W |
| 循环约 6 → 4 次：压钩 2057.3→1682.4、拉钩 2067.5→1295.7 kN | 专利 CN109969220B（双空气制动管循环制动方法） | `patents.google.com/patent/CN109969220B/zh` | W |
| 空电联合的循环次数与最大车钩力均小于纯空气制动；缓解性能随编组 / 坡度 / **缓解速度**增加而变差 | 《应用空电联合制动的重载列车缓解性能》重庆理工大学学报 2017 | `search.napstic.cn`（010cqgxyxb201710014） | W |
