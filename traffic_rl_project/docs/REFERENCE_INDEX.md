# 引用索引（技术/公式 → 论文）

> 写论文时的引用速查。每项：技术/公式 → 来源论文 → 本地文件（`docs/papers/` 下完整文件名；无本地文件的标注 arXiv/出处）。引用须锚定外部权威，禁止用本项目历史当外部标准。

## 纵向动力学 / 车钩力

| 技术/公式 | 来源 | 文件 |
| :--- | :--- | :--- |
| MT-2 摩擦式迟滞缓冲器（Stribeck 静750/动500 kN，v_er=0.2，饱和2270kN@83mm） | 于宗泽2025《重载列车车钩缓冲装置纵向动力学精细化模型》 | `于宗泽2025_fulltext.txt` |
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
| 重载列车群组 + MAPPO（定位最接近） | 宋宗莹2026 | `Song2026_MAPPO_HeavyHaulGroup.html` |
| 虚拟编组 + 传统空气制动协同（Tube-MPC，fence 压缩） | 宋宗莹2026 | `Song2026_TubeMPC_VirtualCoupling.pdf` |
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
| 改进 MPC 协同控制 | Wang2026 | —（无本地，铁路运输与经济 2026） |
| 单列多体 NMPC 循环制动（Shuozhou） | Yang2025 | —（无本地，IEEE ITSC 2025） |

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
| `fan2024` | `编组方式对3万吨重载列车循环制动工况纵向冲动的影响_樊运新.pdf` | 编组→冲动规律 |
| `wu2023` | —（无本地） | 虚拟耦合综述 |
| `basile2022` | —（无本地） | RL 虚拟耦合路线图 |
| `liu2025` | —（无本地） | train-level decomposition |
| `yang2025` | —（无本地） | 单列多体 MPC 基线 |

---

维护：新增引用三处同步（`docs/papers/` + `refs.bib` + 本表）；自研项（winsorization、value grad clip、KL 0.012、5-seed 并行）在论文中声明"ours"，不混入文献。
