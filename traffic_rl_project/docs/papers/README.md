# 文献库目录（docs/papers/）

> 本页 = **文献库清单**：本地文件 → 题名 / 作者·年份 / 出处·DOI / 用途。
> 与 `docs/REFERENCE_INDEX.md`（**技术/公式 → 论文**，写作速查）互补：本页按「文献」组织，RefIndex 按「技术点」组织。
> 索引入口：本页由 `docs/README.md` 登记。
> **文献讨论成果（逐篇证据 / 指标术语对照 / 防追尾机制分级 / ATP 诚实边界）**：[`LITERATURE_FINDINGS.md`](LITERATURE_FINDINGS.md) —— 写 Related Work、指标表、图表标签前先读它；本页只管"有哪些文献"，不管"讨论出了什么"。

## 目录结构（分主题子目录）

| 子目录 | 主题 | 对应内容 |
| :--- | :--- | :--- |
| `01_coupler_physics/` | ① 车钩构建、物理环境仿真 | 纵向动力学 · 车钩/缓冲器 · 空气制动 · 循环制动 · 长大下坡 |
| `02_rl/` | ② 强化学习 | RL 算法 / 单列车 RL 基线 |
| `03_formation/` | ③ 列车编队 | 多智能体 · 群组协同 · 虚拟耦合编队 |
| `04_safety_mpc/` | ④ 安全层 / MPC | MPC 对比基线 · 安全层 / ETCS |
| `05_energy_other/` | ⑤ 节能 / 其他 | 节能对照 · Related Work |

另有 `arxiv_src/`（3 个 arXiv 源码树，原位保留）。

## 维护规则（新增文献必做）

1. **落地**：把文件放进对应主题子目录 `docs/papers/<子目录>/`，命名 = `作者年份_主题.ext`（如 `Guo2025_MARL_PlatoonConsensus.pdf`）或中文题名；同一文献的 PDF / 信息卡 / fulltext / csv 配套件放同一子目录。
2. **登记**：在本页对应主题表**新增一行**（文件 / 题名 / 作者·年份 / 出处·DOI / 用途）。
3. **三处同步**：若该文献被正文引用，须同时更新 `docs/REFERENCE_INDEX.md`（技术点）与 `docs/refs.bib`（BibTeX）；新增 PDF 信息卡（同名 `.md`）时在本页「文件」列一并列出。
4. **辅助件约定**：同名 `.md` = **该文献数据 SSOT**；`*_fulltext.txt` = 字符检索件；`*.csv` = 提取数据（如 `Zhao2022_fig53_velocity_anchors.csv`）。
5. **不可得文献**：只记入页末「暂无本地文件（待补 / 不可得）」，不为其建占位页。

**当前状态**：本地文件 86 个（PDF / txt / md / html / csv），已按子目录归类如下（「文件」列均为所在子目录内文件名）。

---

## 一、`01_coupler_physics/` — 车钩构建 / 物理环境仿真

| 本地文件 | 题名 | 作者 / 年份 | 出处 / DOI | 用途 / 关联 |
| :--- | :--- | :--- | :--- | :--- |
| `于宗泽2025_fulltext.txt`、`重载列车车钩缓冲装置纵向动力学精细化模型_于宗泽.pdf` | 重载列车车钩缓冲装置纵向动力学精细化模型 | 于宗泽, 魏玉光, 于海龙, 方波, 胡楚璇 / 2025 | 中国铁道科学 46(2), DOI 10.3969/j.issn.1001-4632.2025.02.17 | MT-2/QKX100 阻抗特性函数 + 车钩运动子模型（本项目缓冲器模型来源） |
| `重载列车QKX100与MT-2缓冲器动态特性.pdf`、`yanghui2020_qkx_mt2.txt` | 重载列车 QKX100 与 MT-2 缓冲器动态特性 | 杨辉, 原俊荣, 付雅婷, 李中奇 / 2020 | 北京工业大学学报 46(9):1018-1026, DOI 10.11936/bjutxb2018110009 | 缓冲器动态特性对比 |
| `201102010.pdf`、`mawh2011.txt` | 缓冲器阻抗特性对重载列车动力学性能的影响 | 马卫华, 宋荣荣, 揭长安, 罗世辉 / 2011 | 交通运输工程学报 11(2):59-64 | 弹性胶泥 vs 摩擦胶泥缓冲器阻抗 |
| `弹性胶泥缓冲器关键参数对快捷列车纵向冲动的影响_赵旭宝.pdf`、`zhaoxubao2022_qkx100.txt` | 弹性胶泥缓冲器关键参数对快捷列车纵向冲动的影响 | 赵旭宝 等 / 2022 | 振动与冲击 41(5) | 缓冲器关键参数敏感性 |
| `一种用于模拟车辆冲击试验的铁路货车纵向连接模型_杨亮亮.pdf`、`yangliangliang2017_mt2.txt` | 一种用于模拟车辆冲击试验的铁路货车纵向连接模型 | 杨亮亮 等 / 2017 | 中国铁道科学 38(1) | 车辆冲击试验连接模型 |
| `lei2019_gooa.pdf`、`lei2019_fulltext.txt` | Influence of Draft Gear Modeling on Dynamics Simulation for Heavy-Haul Train | Cheng Lei, Jia Liu, Lisheng Dong, Weihua Ma / 2019 | Shock and Vibration 2019: 2547318, DOI 10.1155/2019/2547318 | 查表 vs 楔簧缓冲器模型（MT-2） |
| `Analysis of the nonlinear dynamic behavior of longitudinal systems in heavy-haul trains.pdf`、`Wang2025_longitudinal_nonlinear_fulltext.txt`、`Wang2025_LongitudinalNonlinear_缓冲器非线性.md` | Analysis of the nonlinear dynamic behavior of longitudinal systems in heavy-haul trains | Leiting Wang, Yang Jin, Wangxiang Li, Chenyang Tang / 2025 | Electronic Research Archive（OA）, DOI 10.3934/era.2025027 | 载荷/游隙/缓冲器→分岔混沌 |
| `krishna-et-al-2020-an-integrated-numerical-framework-to-investigate-the-running-safety-of-overlong-freight-trains.pdf`、`Krishna2020_overlong_heterogeneity_fulltext.txt`、`Krishna2020_OverlongHeterogeneity_运行安全.md` | An integrated numerical framework to investigate the running safety of overlong freight trains | V. V. Krishna, D. Jobstfinke, S. Melzi, M. Berg / 2020 | Proc. IMechE Part F, 235(1), DOI 10.1177/0954409720905203（OA） | 货车异构→列内力（E4-H 先例） |
| `车钩间隙对重载列车纵向冲击动力学的影响_杨敏.pdf` | 车钩间隙对重载列车纵向冲击动力学的影响 | 杨敏 / 出处待补 | 中文期刊 | 车钩间隙死区（0.01 m）放大规律（判据锚） |
| `车钩间隙及制动操纵模式对万吨重载列车纵向动力学性能影响分析_杨敏.pdf` | 车钩间隙及制动操纵模式对万吨重载列车纵向动力学性能影响分析 | 杨敏 / 出处待补 | 中文期刊 | 间隙 × 操纵模式联合影响 |
| `2万吨重载列车牵引启动工况的纵向冲动分析_杨忠良.pdf` | 2 万吨重载列车牵引启动工况的纵向冲动分析 | 杨忠良, 孙林平, 马卫华, 罗世辉, 王波 / 2024 | 动力学与控制学报 22(9):81-88, DOI 10.6052/1672-6553-2024-046 | 牵引启动车钩力分布 |
| `重载列车纵向动力学建模研究_丁莉芬.pdf` | 重载列车纵向动力学建模研究 | 丁莉芬 / 2012 | 北京交通大学 学位论文[D] | 纵向动力学建模 |
| `Parameters-design-for-vertical-section-of-a-30-000-ton-heavy-haul-railway-aligment-based.pdf` | Parameters design for vertical section of a 30,000-ton heavy-haul railway alignment based on longitudinal dynamics analysis | Qihan Chu, Can Zou, Yiming Zhang / 待核 | 会议论文（IEEE 格式；venue/年份待核） | 3 万吨纵断面参数设计 |
| `朔黄铁路2万t重载组合列车纵向车钩力分析及应用研究_张二田.pdf`、`张二田2021_朔黄2万t车钩力实测.md`、`张二田2021_朔黄2万t车钩力_fulltext.txt` | 朔黄铁路 2 万 t 重载组合列车纵向车钩力分析及应用研究 | 张二田 / 2021 | 神华科技 19(1):74-78 | ⭐ 唯一实车车钩力实测源（判据 S1-S7） |
| `大秦线2万t重载列车货车车钩力跟踪试验研究_王鼎.pdf`、`王鼎2023_大秦线车钩力跟踪试验.md`、`王鼎2023_大秦线车钩力跟踪试验_fulltext.txt` | 大秦线 2 万 t 重载列车货车车钩力跟踪试验研究 | 王鼎, 苗晓雨, 姜成 / 2023 | 铁道车辆 61(1):102-105, DOI 10.3969/j.issn.1002-7602.2023.01.021 | ⭐ 46 次测力车钩实测（判据 D1-D6，2250 kN） |
| `靳新元2018_朔黄2万t长大下坡车钩受力.md`（无本地 PDF，网络获取全文） | 朔黄铁路 2 万 t 重载组合列车在长大下坡道车钩受力分析与应用 | 靳新元 / 2018 | 神华科技 2018(5):79-83 | ⭐ 2 万 t 分工况评定指标 1500/1000/6°/2250 kN（**ADR-036 主锚**，编组与 `20kt_1plus108_1plus108` 同款） |
| `重载列车制动力判断标准及纵向冲动研究_刘博阳.pdf`、`刘博阳2022_列尾压强与车钩力.md`、`刘博阳2022_制动力判断标准_fulltext.txt` | 重载列车制动力判断标准及纵向冲动研究 | 刘博阳, 魏伟, 豆飞 / 2022 | 大连交通大学学报 43(6):38-44, DOI 10.13291/j.cnki.djdxac.2022.06.007 | 列尾压强→拉钩力（判据 L1-L6） |
| `Fu2019_CouplerConstraint_HeavyHaul.pdf` | 基于钩缓约束的重载列车驾驶过程优化 | Fu / 2019（出处待补） | — | 车钩力 1000/2250 kN 上限（安全层阈值来源） |
| `重载组合列车纵向力优化的联合制动分析及研究_李蔚.pdf` | 重载组合列车纵向力优化的联合制动分析及研究 | 李蔚 / 2023（出处待补） | — | Newmark-β + Picard 来源（数值积分） |
| `重载列车空气制动精细建模与操纵优化.pdf`、`Zhao2022_AirBrakeRefinedModeling_Optimization.pdf`、`.md`、`_fulltext.txt`、`Zhao2022_fig53_velocity_anchors.csv` | 重载列车空气制动精细建模与操纵优化 | 赵紫宁 / 2022 | 西南交通大学 硕士论文[D] | 三段式空气制动精细模型（信息卡 = 数据 SSOT） |
| `不同万吨编组列车空气制动特性对纵向动力学性能影响_周占松.pdf` | 不同万吨编组列车空气制动特性对纵向动力学性能影响 | 周占松 / 2026（出处待补） | — | 编组 × 空气制动特性 |
| `rs-11-2024-0048.pdf` | Research on optimization and evaluation method of heavy-haul train cyclic braking manipulation | Wen He, Chongyi Chang, Lan Li, Yupan Song / 2025 | Railway Sciences（OA）, DOI 10.1108/RS-11-2024-0048 | 高精度 LTD + 遗传算法循环制动优化 |
| `编组方式对3万吨重载列车循环制动工况纵向冲动的影响_樊运新.pdf` | 编组方式对 3 万吨重载列车循环制动工况纵向冲动的影响 | 樊运新 / 2024（出处待补） | — | 编组方式 → 循环制动冲动 |
| `货车连挂方式对万吨重载列车循环制动过程纵向冲动影响分析_王宏宇.pdf` | 货车连挂方式对万吨重载列车循环制动过程纵向冲动影响分析 | 王宏宇 / 出处待补 | — | 连挂方式 → 循环制动冲动 |
| `考虑车钩力约束的重载列车运行优化分层框架与迭代求解方法_魏咪.pdf` | 考虑车钩力约束的重载列车运行优化分层框架与迭代求解方法 | 魏咪 / 2024（出处待补） | — | ⭐ 车钩力约束分层框架（最重要对标） |
| `Zhang2025_20kT_LongitudinalDynamics_Braking.pdf` | 20 kT 制动纵向动力学（§4.3额外尾部充风装置，非普通EOT功能） | Bo Zhang等 / Mathematics 2026, 14, 158（在线2025-12-31；历史文件名保留） | 10.3390/math14010158 | 纵向动力学 / 车钩力 |

## 二、`02_rl/` — 强化学习

| 本地文件 | 题名 | 作者 / 年份 | 出处 / DOI | 用途 / 关联 |
| :--- | :--- | :--- | :--- | :--- |
| `Tang2020_DoubleSwitchQ.pdf` | 多机车 RL + 车钩力多目标（Double-Switch Q） | Tang / 2020（出处待补） | — | 多机车 RL 基线 |
| `Zhang2024_DQN_CyclicBraking_Downhill.pdf`、`.txt` | 长大下坡循环空气制动 DQN | Changfan Zhang 等 / 2024 | MDPI Algorithms 17(5):190, DOI 10.3390/a17050190 | RL 循环制动基线（忽略车钩力→创新空间；T_a 充风约束） |
| `information-15-00271.pdf` | Cyclic Air Braking Strategy for Heavy Haul Trains on Long Downhill Sections Based on Q-Learning Algorithm | Changfan Zhang, Shuo Zhou, Jing He, Lin Jia / 2024 | MDPI Information 15(5):271, DOI 10.3390/info15050271 | Q-Learning 循环制动（同组后继工作） |
| `An-Optimization-Method-of-Heavy-Haul-Train-Driving-Strategy-Based-on-Dueling-DQN.pdf` | An Optimization Method of Heavy Haul Train Driving Strategy Based on Dueling DQN | Qida Si, Lu Jiang, Qi Wang, Youbin Su, Zhiming Xiao, Yuxuan Han, Ming Chai / 2025 | 2025 IEEE ICIRT, DOI 10.1109/ICIRT66379.2025.11216735 | Dueling DQN 驾驶策略（长陡下坡） |
| `wang-et-al-2026-hierarchical-reinforcement-learning-for-long-distance-multi-objective-optimization-of-heavy-haul-trains.pdf` | Hierarchical RL for Long-Distance Multi-Objective Optimization of Heavy-Haul Trains via Sequential Task Assignment Across Spatial Segments | Jianhua Wang, Cong Wang, Qingyuan Wang, Yiding Yu, Xiaoyun Feng / 2026 | IET Intelligent Transport Systems, DOI 10.1049/itr2.70254 | 分层 RL + 车钩力（单列车） |
| `Huang2025_EITO_ExpertSystemDRL.pdf` | 专家系统 + DRL 列车运行 | Huang / 2025（出处待补） | — | Related Work |

## 三、`03_formation/` — 列车编队

| 本地文件 | 题名 | 作者 / 年份 | 出处 / DOI | 用途 / 关联 |
| :--- | :--- | :--- | :--- | :--- |
| `Song2026_MAPPO_HeavyHaulGroup.pdf` | 重载列车群组 + MAPPO（定位最接近） | 宋宗莹 等 / 2026 | 预印本, DOI 10.61951/SciencepaperOnline.202605.0114（**全文 PDF 20 页已入库 2026-10-13**；同名 `.html` 为原摘要页存档） | 最接近本项目的群组 MARL |
| `Song2026_TubeMPC_VirtualCoupling.pdf` | 虚拟编组 + 传统空气制动协同（Tube-MPC，fence 压缩） | 宋宗莹 等 / 2026 | 北京交通大学学报 50(2):116-131, DOI 10.11860/j.issn.1673-0291.20250156 | 虚拟耦合 MPC 对照 |
| `Guo2025_MARL_PlatoonConsensus.pdf`、`.txt` | Enhanced consensus control architecture for autonomous platoon utilizing multi-agent reinforcement learning | Xin Guo 等 / 2025 | Computer-Aided Civil and Infrastructure Engineering, DOI 10.1111/mice.13463 | 车队 MARL 共识控制（间距 −8.3% / 编队长 −19.1%） |
| `Zhang2021_MADRL_TrainPlatoon.pdf`、`.txt` | Multi-Agent Deep Reinforcement Learning Based Consistency Control in Train Platoon Systems | Xinran Zhang, Gaofeng Nie, Wanli Ni, Hui Tian / 2021 | 会议（IEEE；venue 待核） | leader-follower + 人工势场群组一致性 |
| `Multi-Agent Reinforcement Learning Optimization for Virtual Coupled Train Set Problem in CBTC Systems.pdf` | Multi-Agent Reinforcement Learning Optimization for Virtual Coupled Train Set Problem in CBTC Systems | Guanlin Jing, Yifei Zou, Zuyuan Zhang, Jiguo Yu, Dongxiao Yu, Xiuzhen Cheng / 2025 | Tsinghua Science and Technology, DOI 10.26599/TST.2025.9010067 | VCTS + MARL（城轨 CBTC） |
| `electronics-15-01823.pdf` | Predictive Mamba-Enhanced Multi-Agent Reinforcement Learning Control for Virtual Coupling of High-Speed Trains | Han Hu, Qingsheng Feng, Zhun Han, Wangyang Liu, Hong Li / 2026 | MDPI Electronics 15: 1823, DOI 10.3390/electronics15091823 | PM-MASAC 高铁虚拟编组 |
| `Hua2024_MARL_CACC_EnergyEfficiency.pdf`、`.txt` | Communication-Efficient MARL for Platoon Stability and Energy-efficiency Co-optimization in CACC of CAVs | Min Hua 等 / 2024（出处待补） | — | CACC MARL 节能（+5.8%） |
| `Safe_Optimal_Train_Formation_Control_in_Virtual_Coupling_Using_Control_Barrier_Functions.pdf` | Safe Optimal Train Formation Control in Virtual Coupling Using Control Barrier Functions | Y. Li, Y. Tong, A. Giua / 2024 | 2024 IEEE CASE, DOI 10.1109/CASE59546.2024.10711420 | CBF/CLF + QP 安全控制 |
| `1037_Corrected_FINAL_ITSC_2025.pdf` | Virtual Coupling Train Following Control Using High Order Control Barrier Functions | Yike Li, Yin Tong, Alessandro Giua / 2025 | ITSC 2025（IEEE；DOI 待核） | HOCBF 虚拟耦合跟随控制（RBD 安全） |

## 四、`04_safety_mpc/` — 安全层 / MPC

| 本地文件 | 题名 | 作者 / 年份 | 出处 / DOI | 用途 / 关联 |
| :--- | :--- | :--- | :--- | :--- |
| `Cooperative-Nonlinear-Model-Predictive-Control-for-Multiple-Locomotives-of-Heavy-Haul-Train.pdf`、`Lu2025_CooperativeNMPC_MultiLoco.md` | Cooperative Nonlinear MPC for Multiple Locomotives of Heavy Haul Train on Long Steep Downhill Sections | Ran Lu, Miao Zhang, Shuai Su / 2025 | 2025 IEEE ICIRT, DOI 10.1109/ICIRT66379.2025.11216780 | ⭐ **本项目 MPC 基线来源**（`NMPCController`） |
| `Zhang2014_TCST_ECP_MPC.md`（信息卡，无本地全文） | Optimal Operation of Heavy-Haul Trains Equipped With ECP Brake Systems Using MPC Methodology | Lijun Zhang, Xiangtao Zhuan / 2014 | IEEE Trans. Control Systems Technology 22(1):13-22, DOI 10.1109/TCST.2013.2238235 | ECP-MPC 开山作；ECP 假设绕开气动时滞（摘要级，元数据 Crossref 核实） |
| `Liu2022_ATO_BrakeDelayModel.txt` | 高速列车精确停车的鲁棒自触发预测控制 | 刘晓宇, 荀径, 高士根, 阴佳腾 / 2022 | 自动化学报 48(1):171-181, DOI 10.16383/j.aas.c200039 | 制动曲线生成-跟踪两级；制动模型一阶惯性+纯滞后 Td=1.0s/τ=0.4s 进状态方程（全文） |
| `Yu2023_MILP_RefillTime_Downhill.txt`（部分正文，至 §3.3） | Mixed Integer Linear Programming Based Speed Profile Optimization for Heavy-Haul Trains | Huazhen Yu, Yihui Wang, Andrea D'Ariano, Anzheng Lai, Youneng Huang / 2023 | Journal of Advanced Transportation 2023:6649871, DOI 10.1155/2023/6649871（OA） | MILP 显式建模空气制动指令时滞+充风时间（长大下坡）；刚体模型无车钩力 |
| `Zhang2026_JAS_CouplerCompensation.txt`（部分正文，至 §II） | A Distributed Braking Scheme for Heavy-Haul Trains Using Coupler Force Compensation | Jilie Zhang, Zhiyong Chen, Ge Guo / 2026 | IEEE/CAA J. Autom. Sinica 13(4):877-887, DOI 10.1109/JAS.2025.125870（OA） | ECP 车钩力前馈补偿+分布式列队（非 MPC）；批评 MPC QP 实时性 |
| `Zhao2026_CCDC_ElectroPneumaticCoordination.md`（信息卡，无本地全文） | MPC with Electro-Pneumatic Coordination for Impulse Suppression in Heavy-Haul Trains on Long Steep Downhills | Hongyi Zhao, Qingyuan Wang, Haochen Jiang, Pengfei Sun / 2026 | 2026 38th IEEE CCDC:6036-6043, DOI 10.1109/CCDC69976.2026.11559852 | 电空协调：AB 不进优化变量、速度误差触发循环「减压-保压-缓解」，车钩力峰降>8%（摘要级，元数据 OpenAlex 核实） |
| `Farooqi2018_ParametrizedMPC.pdf` | Efficient Train Operation via Shrinking Horizon Parametrized Predictive Control | Hafsa Farooqi, Lorenzo Fagiano, Patrizio Colaneri / 2018 | IFAC-PapersOnLine 51(20):203-208, DOI 10.1016/j.ifacol.2018.11.014 | 输入参数化把离散模式集化为 NLP（discrete MPC 对照） |
| `Li2025_FSMPC_BrakeNotch.txt` | 基于FSMPC的列车精准停车阶段动态优化研究 | 李蔚, 曹悦, 娄永梅, 黄苏苏, 何怡霏 / 2025 | 铁道科学与工程学报 22(10):4424-4435, DOI 10.19713/j.cnki.43-1423/u.T20250035 | FSMPC 有限集枚举+制动级位↔减速度静态映射+HMM 预测电空转换（全文） |
| `Safe_Reinforcement_Learning_Control_of_High-Speed_Maglev_Train_Levitation_System_Considering_Aerodynamic_Lift_Force.pdf` | Safe RL Control of High-Speed Maglev Train Levitation System Considering Aerodynamic Lift Force | 作者待核 / 2025 | CIYCEE 2025（会议稿；DOI 待核） | HOCBF + 扰动观测器安全层（RL+安全层结构参考） |
| `ERA_2020_Introduction_to_ETCS_Braking_Curves.pdf` | Introduction to ETCS Braking Curves | ERA / 2020 | 欧盟铁路局（ERA） | ETCS 制动曲线（EBI/SBI 单调表） |

## 五、`05_energy_other/` — 节能 / 其他（Related Work）

| 本地文件 | 题名 | 作者 / 年份 | 出处 / DOI | 用途 / 关联 |
| :--- | :--- | :--- | :--- | :--- |
| `Heineken2023_OptimalControl_EnergyEfficient.pdf` | 最优控制节能（Pontryagin） | Heineken / 2023（出处待补） | — | 节能对照 |
| `Yang2024_ACSd_EnergyEfficientTrain.pdf` | 蚁群算法节能 | Yang / 2024（出处待补） | — | 节能对照 |

---

## 暂无本地文件（待补 / 不可得）

> 只在 `REFERENCE_INDEX.md` 出现、本库尚无本地副本。下载后请上移一行到对应主题表并补全元数据。

| 文献 | 出处 | 备注 |
| :--- | :--- | :--- |
| Liu2021 DDQN 循环制动 | TR-C 2021 | RL 循环制动基线 |
| Wang2025 DQN 速度控制 + 纵向冲动抑制 | IEEE ICIRT 2025, DOI 10.1109/ICIRT66379.2025.11216684 | RL 循环制动基线 |
| Yu 等 2023 重载虚拟编组 | MDPI Sustainability 15(18):13425, DOI 10.3390/su151813425 | OA，可下载 |
| Liu & Xu 2024 虚拟编组 | MDPI Sensors 24(13):4231, DOI 10.3390/s24134231 | OA，可下载 |
| 何晖等 2023 | 中国铁道科学 44(6):196-205（无 DOI） | 付费墙，不可得 |
| 魏文军等 2026 长大下坡虚拟编组分层控制 | 铁道科学与工程学报 23(4):1612-1624（共13页，DOI 待查） | 待补；与本项目同场景（长大下坡+虚拟编组+分层），需对标：非 RL（LQ+迭代 MPC），空气制动力当总扰动、无车钩力 |
| 马骏峰等 2025 | 铁道科学与工程学报 22(10):4388-4397, DOI 10.19713/j.cnki.43-1423/u.T20242047 | 待补 |
| Yu2022 / Hessel2019（MAPPO + PopArt） | NeurIPS 2022 / AAAI 2019 | 算法依据 |
| Liu2025 虚拟耦合 MARL | IEEE ITS Magazine 2025 | train=agent 分解 |
| Wu2023 虚拟耦合综述 | IEEE TIV 2023 | 综述 |
| Basile2022 RL 虚拟耦合路线图 | DAI 2022 | 路线图 |
| Chen2024 分布式全局复合学习 | IEEE TITS 2024 | 协同控制 |
| Vaquero2025 虚拟耦合 LMPC | CACIE 2025 | MPC 对照 |
| Wang2026 改进 MPC 协同控制 | 铁路运输与经济 2026 | MPC 对照 |
| Yang2025 单列多体 NMPC 循环制动 | IEEE ITSC 2025（Shuozhou） | MPC 对照 |
| Wei2025 LLM 奖励设计 | arXiv:2504.19480 | 源码 |
| Zhou2020 专家知识 + RL | arXiv:2003.03327 | 源码 |
| Abdelrahman2021 车队 DRL 通信 | arXiv:2312.06858 | 源码 |
| Yadav & Vyas 2023 车钩游隙 | Vehicle System Dynamics, DOI 10.1080/00423114.2022.2107546 | 游隙→纵向动力学 |
| Wabersich & Zeilinger 2021 预测式 safety filter | Automatica, arXiv:1812.05506 | 安全层依据 |
| Pfrommer et al. 2022 safety filter 冲突 | L4DC, arXiv:2112.13941 | 安全层警示 |
| COMA（per-agent advantage） | AAAI 2018 | 信用分配 |
| PRD-MAPPO 信用解耦 | RLJ/RLC 2024 | 信用分配 |
| GAE 有效信用视界 | ICLR 2016 | 视界依据 |
| NeTrainSim（Davis 阻力） | 源码 | 阻力模型 |
| He2025 / 常崇义（Newmark-β） | — | 数值积分 |


### 2026-10-18 待全文的定向检索条目

以下仅取得出版社题录/摘要，不计入本地PDF库存，参数不得据此迁移。用途为单机万吨充风速度余量与制动性能核查，非新增算法创新主张。

- 林轩等2017：HXD2牵引货运列车长大下坡区间周期性制动研究，DOI10.3969/j.issn.0258-2724.2017.05.004；HXD2+100辆C80，全文待获取。
- 肖致明等2023：考虑制动性能差异的重载列车模式化操纵方法，DOI10.13890/j.issn.1000-128X.2023.01.004；北大牛—原平南，编组/公式待全文。

技术适用范围见REFERENCE_INDEX同日条目，BibTeX见docs/refs.bib。MIS检索指令保存在D:/Codex/Documents/Train/controller_takeover_20261017/TraeWork_MIS再制动专项检索指令_20261018.md。


### 新增中文全文实物与关键章节复核-2026-10-18

此前待全文条目为当时库存状态。现已取得林轩中文10页、董克毓4页、黄宇澄119页、肖博懿95页、李彬卓100页，权威原件位于D:/Codex/Documents/Train/paper/万吨108节_再制动压力建立专项/20261018/原文PDF/；来源SHA与带PDF页码文本见同目录原文复核_补充全文_20261018/source_manifest.json。重点核对而非逐页精读：林轩PDF3式(9)充风时间及PDF4缓解速度上界（130秒为本文取值）；黄宇澄PDF34—35/42—43的最低缓解速度、最小缓解时间、转换点条件；董文三机116辆、580kPa判据的68—76秒不用于单机108辆。李文基础模型双机50辆C70E，肖文主对象两万吨，均只筛读适用范围、不迁移数值。题录见docs/refs.bib。

209.5秒为候选缓解到超速窗口，非充风完成时间；当前模型未显式实现完整副风缸再充气动态，不能用制动缸系数反推580kPa时间。修复先查允许缓解速度上下界及充风/下次压力建立余量，保留222秒和1000kN。原文页图与详细解释见D:/Codex/Documents/Train/controller_takeover_20261017/新增全文复核与缓解可行性修复依据_20261018.md。


### 缓解预测误差与数值收敛定向检索-2026-10-18

Zhou/Shi/Hecht，Vehicle System Dynamics60(7):2436—2450，2022（在线2021），DOI10.1080/00423114.2021.1901943：已通过佛罗伦萨大学作者仓储网页读取16页含封面的预印本，讨论不同摩擦迟滞过渡与积分收敛；直接下载受站点验证拦截，未存本地PDF。不能把文中0.1/0.2ms或1ms直接规定为本项目步长，更不能据此断言当前模型错误。[作者仓储](https://flore.unifi.it/retrieve/b71cbe68-acf7-4b44-87f4-fdb45a5f1c56/Comparison%20of%20friction%20draft%20gear%20models%20for%20simulation%20in%20longitudinal%20train%20dynamics_V2025.pdf)。

下一步需原文的方法线索：郭炎冰等《一种用于重载列车纵向动力学仿真的变步长积分算法》，铁道车辆2023,61(3):147—152，题录已由肖博懿PDF92—93参考文献50核实；Wu等国际LTD基准结果，DOI10.1080/00423114.2017.1377840，全文待取。题录见refs.bib；现有lei2019_gooa.pdf不重复下载。MIS检索任务D:/Codex/Documents/Train/controller_takeover_20261017/TraeWork_缓解预测与数值收敛定向检索_20261018.md。用途为验证与误差评估，不是算法创新或当前车钩模型改动依据。
### 2026-10-19 既有全文再核对：恒持的是电制动力

马志强等2023《重载列车平稳运行的空电联合制动匹配控制》，DOI10.13890/j.issn.1000-128X.2023.02.103；用户D盘原PDF与提取文本已存在，不重复下载。PDF4式7/§3.3及PDF5二万吨背景再核实；“缓解后恒持ED50秒”不自动支持本轮30秒或25%力目标。来源与口径见 REFERENCE_INDEX.md 同日条目，bib为ma2023_braking_matching。局部改进仍须动态和全线验收。

### 2026-10-19 新增全文：缓解恒持力与充风时间定义

于岩/魏伟2023 DOI10.13711/j.cnki.cn32-1836/u.2023.04.001，原PDF3已看图，二万吨双机加列尾；支撑坡段筛选加动态验证及缓解后ED不变，不搬公里标/18—50秒峰值时窗。孙中央/王长明2009《铁道机车车辆》29(1):4—7，PDF1式1与PDF2增速验算已核，双机5000吨/约60辆，不搬充风秒数或30km/h缓解速度。郭炎冰等2023 DOI10.3969/j.issn.1002-7602.2023.03.026已获全文，PDF5已看图，108辆C70E平道全制动及特定算法步长对照，不代表当前模型已验证或必须改用其步长。以上取代旧“郭文全文待取”的当前状态；bib为yu2023_daqin_release_location/sun2009_long_downhill_safety/guo2023_variable_step_ltd。原PDF均在D:/Codex/Documents/Train/paper；带页码提取、关键页图和SHA清单在D:/Codex/Documents/Train/paper/新增全文复核_20261019。8份全文已提取不等于全部逐页读完；当前重点复核上述控制/数值章节，陈清扫描文关键数字有识别缺失，未采用其参数。保持力的25%/50%/75%比例均为本地诊断，原文没有规定这些比例。

2026-10-19新增本地全文复核：常崇义等2026（DOI10.19818/j.cnki.1671-1637.2026.197，PDF9—10平衡迭代）与熊芯等2025（DOI10.16385/j.cnki.issn.1004-4523.202506045，PDF6式11）。Bib键chang2026_ltd_progress/xiong2025_realtime_ltd。来源和方法适用边界见D:/Codex/Documents/Train/controller_takeover_20261017/新增论文与联合容差收敛复核_20261019.md；三份PDF及哈希文本在D盘paper/数值积分收敛专项/原文复核_20261019。未复制车型参数，不将摘要或检索建议当已读全文。

2026-10-19文献状态：Zhou2022（DOI10.1080/00423114.2021.1901943）已再次通过大学官方仓储网页读16页预印本相关正文，非只有摘要；本地PDF下载仍受站点验证拦截，未用MIS。原文切换/效率讨论不等于本项目tanh模型错误或其步长可直接移植。原刊入口https://www.tandfonline.com/doi/full/10.1080/00423114.2021.1901943 ，仓储https://flore.unifi.it/handle/2158/1258138 。待补的2006平衡迭代、1990预测校正全文与具体提取项见D盘最新TraeWork_MIS力时程精度与计算效率专项_20261019.md。
