# 文献库目录（docs/papers/）

> 本页 = **文献库清单**：本地文件 → 题名 / 作者·年份 / 出处·DOI / 用途。
> 与 `docs/REFERENCE_INDEX.md`（**技术/公式 → 论文**，写作速查）互补：本页按「文献」组织，RefIndex 按「技术点」组织。
> 索引入口：本页由 `docs/README.md` 登记。

## 维护规则（新增文献必做）

1. **落地**：把文件放进 `docs/papers/`，命名 = `作者年份_主题.ext`（如 `Guo2025_MARL_PlatoonConsensus.pdf`）或中文题名。
2. **登记**：在本页对应主题表**新增一行**（文件 / 题名 / 作者·年份 / 出处·DOI / 用途）。
3. **三处同步**：若该文献被正文引用，须同时更新 `docs/REFERENCE_INDEX.md`（技术点）与 `docs/refs.bib`（BibTeX）；新增 PDF 信息卡（同名 `.md`）时在本页「文件」列一并列出。
4. **辅助件约定**：同名 `.md` = **该文献数据 SSOT**；`*_fulltext.txt` = 字符检索件；`*.csv` = 提取数据（如 `Zhao2022_fig53_velocity_anchors.csv`）。
5. **不可得文献**：只记入页末「暂无本地文件（待补 / 不可得）」，不为其建占位页。

**当前状态**：本地文件 70 个（PDF / txt / md / html / csv），已按主题归类如下。

---

## 一、纵向动力学 / 车钩力 / 缓冲器

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
| `重载列车制动力判断标准及纵向冲动研究_刘博阳.pdf`、`刘博阳2022_列尾压强与车钩力.md`、`刘博阳2022_制动力判断标准_fulltext.txt` | 重载列车制动力判断标准及纵向冲动研究 | 刘博阳, 魏伟, 豆飞 / 2022 | 大连交通大学学报 43(6):38-44, DOI 10.13291/j.cnki.djdxac.2022.06.007 | 列尾压强→拉钩力（判据 L1-L6） |
| `Fu2019_CouplerConstraint_HeavyHaul.pdf` | 基于钩缓约束的重载列车驾驶过程优化 | Fu / 2019（出处待补） | — | 车钩力 1000/2250 kN 上限（安全层阈值来源） |
| `Tang2020_DoubleSwitchQ.pdf` | 多机车 RL + 车钩力多目标（Double-Switch Q） | Tang / 2020（出处待补） | — | 多机车 RL 基线 |
| `重载组合列车纵向力优化的联合制动分析及研究_李蔚.pdf` | 重载组合列车纵向力优化的联合制动分析及研究 | 李蔚 / 2023（出处待补） | — | Newmark-β + Picard 来源（数值积分） |

## 二、空气制动 / 循环制动 / 长大下坡

| 本地文件 | 题名 | 作者 / 年份 | 出处 / DOI | 用途 / 关联 |
| :--- | :--- | :--- | :--- | :--- |
| `重载列车空气制动精细建模与操纵优化.pdf`、`Zhao2022_AirBrakeRefinedModeling_Optimization.pdf`、`.md`、`_fulltext.txt`、`Zhao2022_fig53_velocity_anchors.csv` | 重载列车空气制动精细建模与操纵优化 | 赵紫宁 / 2022 | 西南交通大学 硕士论文[D] | 三段式空气制动精细模型（信息卡 = 数据 SSOT） |
| `不同万吨编组列车空气制动特性对纵向动力学性能影响_周占松.pdf` | 不同万吨编组列车空气制动特性对纵向动力学性能影响 | 周占松 / 2026（出处待补） | — | 编组 × 空气制动特性 |
| `Zhang2024_DQN_CyclicBraking_Downhill.pdf`、`.txt` | 长大下坡循环空气制动 DQN | Changfan Zhang 等 / 2024 | MDPI Algorithms 17(5):190, DOI 10.3390/a17050190 | RL 循环制动基线（忽略车钩力→创新空间；T_a 充风约束） |
| `information-15-00271.pdf` | Cyclic Air Braking Strategy for Heavy Haul Trains on Long Downhill Sections Based on Q-Learning Algorithm | Changfan Zhang, Shuo Zhou, Jing He, Lin Jia / 2024 | MDPI Information 15(5):271, DOI 10.3390/info15050271 | Q-Learning 循环制动（同组后继工作） |
| `An-Optimization-Method-of-Heavy-Haul-Train-Driving-Strategy-Based-on-Dueling-DQN.pdf` | An Optimization Method of Heavy Haul Train Driving Strategy Based on Dueling DQN | Qida Si, Lu Jiang, Qi Wang, Youbin Su, Zhiming Xiao, Yuxuan Han, Ming Chai / 2025 | 2025 IEEE ICIRT, DOI 10.1109/ICIRT66379.2025.11216735 | Dueling DQN 驾驶策略（长陡下坡） |
| `rs-11-2024-0048.pdf` | Research on optimization and evaluation method of heavy-haul train cyclic braking manipulation | Wen He, Chongyi Chang, Lan Li, Yupan Song / 2025 | Railway Sciences（OA）, DOI 10.1108/RS-11-2024-0048 | 高精度 LTD + 遗传算法循环制动优化 |
| `编组方式对3万吨重载列车循环制动工况纵向冲动的影响_樊运新.pdf` | 编组方式对 3 万吨重载列车循环制动工况纵向冲动的影响 | 樊运新 / 2024（出处待补） | — | 编组方式 → 循环制动冲动 |
| `货车连挂方式对万吨重载列车循环制动过程纵向冲动影响分析_王宏宇.pdf` | 货车连挂方式对万吨重载列车循环制动过程纵向冲动影响分析 | 王宏宇 / 出处待补 | — | 连挂方式 → 循环制动冲动 |
| `考虑车钩力约束的重载列车运行优化分层框架与迭代求解方法_魏咪.pdf` | 考虑车钩力约束的重载列车运行优化分层框架与迭代求解方法 | 魏咪 / 2024（出处待补） | — | ⭐ 车钩力约束分层框架（最重要对标） |

## 三、多智能体 / 群组协同（MARL）

| 本地文件 | 题名 | 作者 / 年份 | 出处 / DOI | 用途 / 关联 |
| :--- | :--- | :--- | :--- | :--- |
| `Song2026_MAPPO_HeavyHaulGroup.html` | 重载列车群组 + MAPPO（定位最接近） | 宋宗莹 等 / 2026 | 预印本, DOI 10.61951/SciencepaperOnline.202605.0114（**仅摘要页，全文不可得**） | 最接近本项目的群组 MARL |
| `Song2026_TubeMPC_VirtualCoupling.pdf` | 虚拟编组 + 传统空气制动协同（Tube-MPC，fence 压缩） | 宋宗莹 等 / 2026 | 北京交通大学学报 50(2):116-131, DOI 10.11860/j.issn.1673-0291.20250156 | 虚拟耦合 MPC 对照 |
| `wang-et-al-2026-hierarchical-reinforcement-learning-for-long-distance-multi-objective-optimization-of-heavy-haul-trains.pdf` | Hierarchical RL for Long-Distance Multi-Objective Optimization of Heavy-Haul Trains via Sequential Task Assignment Across Spatial Segments | Jianhua Wang, Cong Wang, Qingyuan Wang, Yiding Yu, Xiaoyun Feng / 2026 | IET Intelligent Transport Systems, DOI 10.1049/itr2.70254 | 分层 RL + 车钩力（单列车） |
| `Guo2025_MARL_PlatoonConsensus.pdf`、`.txt` | Enhanced consensus control architecture for autonomous platoon utilizing multi-agent reinforcement learning | Xin Guo 等 / 2025 | Computer-Aided Civil and Infrastructure Engineering, DOI 10.1111/mice.13463 | 车队 MARL 共识控制（间距 −8.3% / 编队长 −19.1%） |
| `Zhang2021_MADRL_TrainPlatoon.pdf`、`.txt` | Multi-Agent Deep Reinforcement Learning Based Consistency Control in Train Platoon Systems | Xinran Zhang, Gaofeng Nie, Wanli Ni, Hui Tian / 2021 | 会议（IEEE；venue 待核） | leader-follower + 人工势场群组一致性 |
| `Multi-Agent Reinforcement Learning Optimization for Virtual Coupled Train Set Problem in CBTC Systems.pdf` | Multi-Agent Reinforcement Learning Optimization for Virtual Coupled Train Set Problem in CBTC Systems | Guanlin Jing, Yifei Zou, Zuyuan Zhang, Jiguo Yu, Dongxiao Yu, Xiuzhen Cheng / 2025 | Tsinghua Science and Technology, DOI 10.26599/TST.2025.9010067 | VCTS + MARL（城轨 CBTC） |
| `electronics-15-01823.pdf` | Predictive Mamba-Enhanced Multi-Agent Reinforcement Learning Control for Virtual Coupling of High-Speed Trains | Han Hu, Qingsheng Feng, Zhun Han, Wangyang Liu, Hong Li / 2026 | MDPI Electronics 15: 1823, DOI 10.3390/electronics15091823 | PM-MASAC 高铁虚拟编组 |
| `Hua2024_MARL_CACC_EnergyEfficiency.pdf`、`.txt` | Communication-Efficient MARL for Platoon Stability and Energy-efficiency Co-optimization in CACC of CAVs | Min Hua 等 / 2024（出处待补） | — | CACC MARL 节能（+5.8%） |
| `Huang2025_EITO_ExpertSystemDRL.pdf` | 专家系统 + DRL 列车运行 | Huang / 2025（出处待补） | — | Related Work |

## 四、安全层 / 虚拟耦合 / MPC

| 本地文件 | 题名 | 作者 / 年份 | 出处 / DOI | 用途 / 关联 |
| :--- | :--- | :--- | :--- | :--- |
| `Cooperative-Nonlinear-Model-Predictive-Control-for-Multiple-Locomotives-of-Heavy-Haul-Train.pdf`、`Lu2025_CooperativeNMPC_MultiLoco.md` | Cooperative Nonlinear MPC for Multiple Locomotives of Heavy Haul Train on Long Steep Downhill Sections | Ran Lu, Miao Zhang, Shuai Su / 2025 | 2025 IEEE ICIRT, DOI 10.1109/ICIRT66379.2025.11216780 | ⭐ **本项目 MPC 基线来源**（`NMPCController`） |
| `Safe_Optimal_Train_Formation_Control_in_Virtual_Coupling_Using_Control_Barrier_Functions.pdf` | Safe Optimal Train Formation Control in Virtual Coupling Using Control Barrier Functions | Y. Li, Y. Tong, A. Giua / 2024 | 2024 IEEE CASE, DOI 10.1109/CASE59546.2024.10711420 | CBF/CLF + QP 安全控制 |
| `1037_Corrected_FINAL_ITSC_2025.pdf` | Virtual Coupling Train Following Control Using High Order Control Barrier Functions | Yike Li, Yin Tong, Alessandro Giua / 2025 | ITSC 2025（IEEE；DOI 待核） | HOCBF 虚拟耦合跟随控制（RBD 安全） |
| `Safe_Reinforcement_Learning_Control_of_High-Speed_Maglev_Train_Levitation_System_Considering_Aerodynamic_Lift_Force.pdf` | Safe RL Control of High-Speed Maglev Train Levitation System Considering Aerodynamic Lift Force | 作者待核 / 2025 | CIYCEE 2025（会议稿；DOI 待核） | HOCBF + 扰动观测器安全层（RL+安全层结构参考） |
| `ERA_2020_Introduction_to_ETCS_Braking_Curves.pdf` | Introduction to ETCS Braking Curves | ERA / 2020 | 欧盟铁路局（ERA） | ETCS 制动曲线（EBI/SBI 单调表） |

## 五、节能 / 其他（Related Work）

| 本地文件 | 题名 | 作者 / 年份 | 出处 / DOI | 用途 / 关联 |
| :--- | :--- | :--- | :--- | :--- |
| `Heineken2023_OptimalControl_EnergyEfficient.pdf` | 最优控制节能（Pontryagin） | Heineken / 2023（出处待补） | — | 节能对照 |
| `Yang2024_ACSd_EnergyEfficientTrain.pdf` | 蚁群算法节能 | Yang / 2024（出处待补） | — | 节能对照 |
| `Zhang2025_20kT_LongitudinalDynamics_Braking.pdf` | 20 kT 制动纵向动力学（EOT 拉钩力 780→489 kN，−37%） | Zhang / 2025（出处待补） | — | 纵向动力学 / 车钩力 |

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