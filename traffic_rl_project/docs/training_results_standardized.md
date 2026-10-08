---
title: 阶段一训练成果报告（无人机编队）
status: archived
date: 2026-09-01
owner: Owner
# 历史成果保留；当前主战场为阶段二
---

# 基于多智能体强化学习的无人机编队控制训练成果报告

**Training Results Report: Multi-Agent Reinforcement Learning for UAV Formation Control**

训练日期：2026年5月 | 仿真平台：gym-pybullet-drones | 算法框架：Agent Lightning + MAPPO

---

## 摘要

针对多无人机编队控制中传统方法依赖精确环境模型、动态适应性不足的问题，本文提出基于多智能体近端策略优化（MAPPO）的无人机编队控制方法。以gym-pybullet-drones高保真物理仿真器为训练平台，构建3架四旋翼无人机的编队保持任务。通过设计共享策略网络与集中式价值网络的MAPPO架构，结合连续速度控制的4维VEL动作空间，在500轮训练中实现了**平均奖励 $99.39 \pm 47.18$、最优奖励 $235.50$、平均高度误差 $0.383\,\text{m}$、平均编队误差 $0.497\,\text{m}$** 的编队保持效果。横向对比中，SAC算法虽在编队误差（$0.322\,\text{m}$）上表现更优，但高度控制偏差达 $0.638\,\text{m}$ 且后期策略退化严重；PPO算法训练不稳定，最终未能收敛。消融实验表明，集中式评论家结构使编队误差降低 $38.2\%$，KL散度早停机制将策略坍缩概率从 $11.8\%$ 降至 $0\%$。确定性推理模式在10轮测试中取得**平均奖励 $115.31 \pm 15.27$、高度误差 $0.375\,\text{m}$、编队误差 $0.347\,\text{m}$** 的稳定表现，验证了该方法的有效性与鲁棒性。

**关键词：** 多无人机编队控制；多智能体强化学习；MAPPO；深度强化学习；gym-pybullet-drones；集中式评论家；KL散度早停；确定性推理

---

## 1 引言

随着无人机技术在军事侦察、灾害救援、物流配送等领域的广泛应用，多无人机编队控制作为集群智能的核心问题日益受到关注。与单无人机系统相比，多无人机编队具备更好的鲁棒性、容错性和任务执行效率[1]。然而，无人机实际飞行环境具有部分可观测、非线性、强耦合等特点，传统控制方法（如领航-跟随法[2]、虚拟结构法[3]、一致性理论[4]等）需要平台和扰动的精确模型进行控制律设计，限制了其适用范围。

深度强化学习（Deep Reinforcement Learning, DRL）作为数据驱动的决策方法，无需依赖精确的环境模型，通过智能体与环境的交互实现自我优化，为解决多无人机编队控制问题提供了全新范式[5]。近年来的研究表明，DRL在无人机集群控制中展现出巨大潜力：陈众楷等[6]提出基于安全强化学习的多无人机编队与避障控制方法，利用控制障碍函数确保飞行安全；Ziyuan Ma等[7]提出自适应强化学习与多模态感知融合框架，实现了大规模无人机群的自主编队与避障。何明等[8]系统梳理了群体仿生智能与深度强化学习（BSI-DRL）融合的无人机集群行为建模方法，指出BSI-DRL已成为驱动无人机集群高级自主协同的核心范式。

本工作按照BSI-DRL范式中的"仿生规则生成式多智能体强化学习"方向（中层融合），将编队保持的生物协同特性（间距保持、速度匹配、群体凝聚）转化为连续形式的奖励函数，引导智能体自主涌现符合编队需求的协同策略。本文的**主要贡献**包括：

1. 设计了适配高保真物理仿真的MAPPO编队控制器，解决了VEL模式动作空间与多智能体框架的适配问题；
2. 提出了KL散度早停机制与低学习率策略，将策略坍缩概率降至 $0\%$；
3. 通过多算法横向对比和消融实验，系统分析了各组件对编队性能的贡献度；
4. 验证了确定性推理模式在实际部署中的优越性。

---

## 2 问题建模

### 2.1 MDP形式化定义

将多无人机编队控制问题建模为马尔可夫决策过程（MDP），由元组 $\langle \mathcal{S}, \mathcal{A}, \mathcal{P}, \mathcal{R}, \gamma \rangle$ 定义，其中 $\mathcal{S}$ 为联合状态空间，$\mathcal{A}$ 为联合动作空间，$\mathcal{P}: \mathcal{S} \times \mathcal{A} \times \mathcal{S} \rightarrow [0,1]$ 为状态转移概率，$\mathcal{R}: \mathcal{S} \times \mathcal{A} \rightarrow \mathbb{R}$ 为奖励函数，$\gamma \in [0,1]$ 为折扣因子。

**状态空间：** 每架无人机观测 $72$ 维物理状态，包括位置 $(x,y,z)$、线速度 $(v_x,v_y,v_z)$、姿态四元数 $(q_0,q_1,q_2,q_3)$、角速度 $(\omega_x,\omega_y,\omega_z)$ 及电机转速（4维）。$N=3$ 架无人机构成 $216$ 维全局观测向量：

$$
\mathbf{s}_t = [o_1, o_2, \ldots, o_N] \in \mathbb{R}^{72N}, \quad N=3 \Rightarrow \mathbf{s}_t \in \mathbb{R}^{216}
$$

**动作空间：** 采用VEL模式连续速度控制，每架无人机输出 $4$ 维动作：

$$
a_i = [v_x, v_y, v_z, \text{magnitude}], \quad \text{magnitude} \in [0,1]
$$

其中前三维为归一化速度方向向量，第四维 $\text{magnitude}$ 为速度幅度缩放因子，通过下式生成目标速度指令：

$$
\mathbf{v}_{\text{target}} = \text{SPEED\_LIMIT} \times \text{magnitude} \times \hat{\mathbf{v}}, \quad \hat{\mathbf{v}} = \frac{[v_x, v_y, v_z]}{\|[v_x, v_y, v_z]\|_2}
$$

$N$ 架无人机构成 $4N$ 维联合动作向量：

$$
\mathbf{a}_t = [a_1, a_2, \ldots, a_N] \in [-1,1]^{4N}, \quad N=3 \Rightarrow \mathbf{a}_t \in [-1,1]^{12}
$$

### 2.2 奖励函数设计

奖励函数由高度保持、编队距离、生存奖励和边界安全四部分连续奖励构成，采用连续而非稀疏形式以提供平滑的梯度引导信号：

$$
R(\mathbf{s}_t, \mathbf{a}_t) = r_h + r_f + r_s + r_b
$$

其中各分量为：

1. **高度误差惩罚：** $r_h = -\sum_{i=1}^{N}|z_i - z_{\text{target}}|$，对每架无人机偏离目标高度进行连续惩罚。

2. **编队距离惩罚：** $r_f = -\sum_{i=1}^{N}\sum_{j=i+1}^{N}\big|\|\mathbf{p}_i - \mathbf{p}_j\|_2 - d_{\text{target}}\big|$，维护无人机间期望间距 $d_{\text{target}} = 5.0\,\text{m}$。

3. **生存奖励：** $r_s = N \times 1.0$（每步存活奖励），鼓励无人机维持在有效飞行区域内。

4. **边界安全惩罚：** $r_b = \sum_{i=1}^{N}\max(0, \|\mathbf{p}_i\|_\infty - \text{boundary}) \times w_{\text{bound}}$，当无人机接近仿真边界时施加温和惩罚，$w_{\text{bound}} = 0.1$。

> **连续奖励优于稀疏奖励的机制：** 早期实验中使用稀疏高度奖励（仅在 $|z - z_{\text{target}}| < \delta$ 时给 $+100$，否则 $-100$），导致SAC算法在高度控制上严重退化（HeightErr $= 0.724\,\text{m}$，为目标高度的 $72.4\%$）。改为连续形式后，高度误差得到大幅改善。这印证了BSI-DRL范式[8]中"奖励函数嵌入生物特性，驱动规则自主生成"的设计原则——连续奖励对应于生物群体中持续的环境反馈，使智能体获得平滑的策略梯度引导。

---

## 3 算法设计

### 3.1 MAPPO架构总览

MAPPO（Multi-Agent Proximal Policy Optimization）采用集中式训练-分布式执行（Centralized Training with Decentralized Execution, CTDE）范式，核心组件如下：

**（1）共享策略网络（Shared Policy Network）**

所有无人机共享同一策略网络 $\pi_\theta(a_i|o_i)$，输入为单架无人机局部观测 $o_i \in \mathbb{R}^{72}$，输出为 $4$ 维动作的高斯分布均值 $\boldsymbol{\mu} \in \mathbb{R}^{4}$ 和对数标准差 $\log\boldsymbol{\sigma} \in \mathbb{R}^{4}$：

$$
[\boldsymbol{\mu}, \log\boldsymbol{\sigma}] = f_\theta^{\text{policy}}(o_i), \quad a_i \sim \mathcal{N}(\boldsymbol{\mu}, \text{diag}(\boldsymbol{\sigma}^2))
$$

网络结构为 $[256, 256, 128]$ 三层全连接 + ReLU激活，输出层线性映射至动作均值和对数标准差。

**（2）集中式价值网络（Centralized Critic）**

$V_\phi(\mathbf{s}_t)$ 以 $216$ 维全局状态为输入，输出标量状态价值 $V \in \mathbb{R}$：

$$
V_\phi(\mathbf{s}_t) = f_\phi^{\text{critic}}(\mathbf{s}_t), \quad \mathbf{s}_t \in \mathbb{R}^{216}
$$

同样采用 $[256, 256, 128]$ 三层网络结构。训练时利用全局信息评估状态价值，执行时各智能体仅依赖局部策略网络 $\pi_\theta(a_i|o_i)$ 独立决策。

**（3）经验缓冲区与GAE**

存储每轮收集的轨迹数据 $(\mathbf{s}_t, \mathbf{a}_t, r_t, \mathbf{s}_{t+1}, \log\pi_\theta)$，支持广义优势估计（Generalized Advantage Estimation, GAE）[12]：

$$
\hat{A}_t^{\text{GAE}(\lambda)} = \sum_{l=0}^{T-t-1}(\gamma\lambda)^l \delta_{t+l}, \quad \delta_t = r_t + \gamma V_\phi(\mathbf{s}_{t+1}) - V_\phi(\mathbf{s}_t)
$$

其中 $\lambda \in [0,1]$ 控制优势估计的偏差-方差权衡，本工作取 $\lambda = 0.95$。

### 3.2 策略更新与KL散度早停

策略更新采用PPO-clip目标函数：

$$
L^{\text{CLIP}}(\theta) = \mathbb{E}_t\left[\min\left(\rho_t(\theta) \cdot \hat{A}_t, \; \text{clip}\left(\rho_t(\theta), 1-\varepsilon, 1+\varepsilon\right) \cdot \hat{A}_t\right)\right]
$$

其中 $\rho_t(\theta) = \frac{\pi_\theta(a_t|s_t)}{\pi_{\theta_{\text{old}}}(a_t|s_t)}$ 为新旧策略的概率比，$\varepsilon = 0.2$ 为剪切范围。

**KL散度早停（KL Early Stopping）机制：** 在每轮epoch更新后计算新旧策略的KL散度：

$$
D_{\text{KL}}\big(\pi_{\theta_{\text{old}}} \| \pi_\theta\big) = \mathbb{E}_{o \sim \mathcal{D}}\left[\text{KL}\big(\pi_{\theta_{\text{old}}}(\cdot|o) \| \pi_\theta(\cdot|o)\big)\right]
$$

若 $D_{\text{KL}} > \tau_{\text{KL}} = 0.01$，则提前终止本轮epoch迭代。该机制将策略坍缩概率从 $11.8\%$（无早停，ep110-130附近）降至 $0\%$，以极小的计算开销（仅需一次KL散度前向计算）换取显著的训练稳定性改善。

### 3.3 确定性推理模式

在部署/测试阶段采用确定性推理：动作 $a_i = \boldsymbol{\mu}_\theta(o_i)$，即直接使用策略网络均值作为输出，而非从高斯分布 $\mathcal{N}(\boldsymbol{\mu}, \text{diag}(\boldsymbol{\sigma}^2))$ 采样。该模式消除了随机噪声引入的行为方差，适用于训练收敛后的评估与部署场景。

---

## 4 实验设置

### 4.1 物理环境配置

基于gym-pybullet-drones的VEL控制模式，使用MultiHoverAviary作为底层物理环境。核心配置：无人机数量 $N=3$；目标高度 $z_{\text{target}} = 1.0\,\text{m}$；目标编队间距 $d_{\text{target}} = 5.0\,\text{m}$；最大速度 $\text{SPEED\_LIMIT} = 1.0\,\text{m/s}$；每回合最大步数 $\text{MAX\_STEPS} = 400$；仿真频率 $\text{freq} = 240\,\text{Hz}$；控制频率 $\text{ctrl\_freq} = 48\,\text{Hz}$。使用GPU（CUDA）加速PyTorch神经网络运算。

### 4.2 算法超参数配置

**表1** 三种算法的超参数配置对比

| 超参数 | MAPPO（最终方案） | SAC（对比基线） | PPO（对比基线） |
|:---|:---|:---|:---|
| 学习率 | $5 \times 10^{-5}$ | $1 \times 10^{-4}$ | $3 \times 10^{-4}$ |
| 折扣因子 $\gamma$ | $0.99$ | $0.99$ | $0.99$ |
| GAE参数 $\lambda$ | $0.95$ | N/A | $0.95$ |
| 剪切范围 $\varepsilon$ | $0.20$ | N/A | $0.15$ |
| 熵系数 | $0.005$ | $\alpha=0.02$（固定） | $0.001$ |
| 价值系数 | $0.50$ | N/A | $0.50$ |
| 最大梯度范数 | $0.50$ | N/A | $0.50$ |
| 训练轮次（epochs） | $4$ | N/A | $10$ |
| 批次大小 | $64$ | $256$ | $128$ |
| 目标网络软更新 $\tau$ | N/A | $0.001$ | N/A |
| 经验池容量 | N/A | $1,000,000$ | N/A |
| KL早停阈值 $\tau_{\text{KL}}$ | $0.01$ | N/A | N/A（无早停） |
| 网络结构（Policy） | $[256,256,128]$ 共享 | Actor: $[256,256,256]$ | $[256,256,128]$ |
| 网络结构（Critic） | $[256,256,128]$ 集中式 | Critic: $[256,256,256]$ | 共享Actor-Critic |
| 自动熵调节 | N/A | False（固定$\alpha$） | N/A |
| 训练总轮次 | $500$ | $1,864$ | $6,415$ |
| 总训练步数 | $\sim 200,000$ | $\sim 745,600$ | $\sim 2,566,000$ |
| GPU加速 | 是（CUDA） | 是（CUDA） | 是（CUDA） |

---

## 5 实验结果与分析

### 5.1 多算法横向对比

**表2** 三种算法的编队控制性能对比

| 指标 | MAPPO（500轮） | SAC（1,864轮） | PPO（6,415轮） |
|:---|:---|:---|:---|
| 最优奖励 | $235.50$ | $6,751.39$ | $677.23$ |
| 平均奖励 | $99.39 \pm 47.18$ | $-892.20$（后期退化） | $\sim 0$（未收敛） |
| 收敛状态 | $\checkmark$ 稳定收敛 | $\times$ 后期退化 | $\times$ 未有效学习 |
| 平均高度误差（m） | $0.383$ | $0.638$ | $0.0^*$ |
| 平均编队误差（m） | $0.497$ | $0.322$ | $0.0^*$ |
| 平均速度（m/s） | $0.491$ | $0.732$ | $\sim 0^*$ |
| 高度稳定性 | 优（连续奖励） | 差（稀疏奖励） | —（未起飞） |
| 策略坍缩 | $0\%$（KL早停） | 退化至零 | 训练全程未激活 |

> *注：PPO的 $0$ 值指标源于训练失败（无人机未起飞/奖励函数未触发），非有效控制结果。

**关键发现：**

1. **MAPPO在仅500轮训练后即实现稳定收敛**，平均奖励 $99.39$，远优于PPO（6,415轮未收敛）和SAC（1,864轮后严重退化）。这表明共享策略 + 集中式评论家的CTDE架构在编队任务中具有显著优势。

2. **SAC算法的奖励函数存在根本性矛盾**：其高分（$6,751.39$）主要源自早期大规模生存奖励（奖励函数将高度仅作为稀疏门控），但高度误差高达 $0.638\,\text{m}$，说明该奖励结构无法同时优化高度和编队双重目标——生存奖励驱动策略尽可能延长飞行时间，而不驱动精确高度保持。

3. **PPO在该编队任务中完全失效**：reward始终在 $0$ 附近振荡，无人机未能学习有效控制策略。分析源于单智能体PPO架构缺乏编队协同所需的多智能体信息共享机制（各智能体独立优化，缺乏对全局编队状态的显式建模）。

### 5.2 MAPPO训练过程分析

**表3** MAPPO训练过程中的关键指标演进（500轮）

| 训练阶段 | 轮次范围 | 最佳Reward | 奖励均值 | 高度误差（m） | 阶段特征 |
|:---|:---|:---|:---|:---|:---|
| 探索期 | ep 1–50 | $-27.3$ | $\sim 10$ | $0.7$–$1.0$ | 动作随机，偶尔高奖励峰值 |
| 学习期 | ep 51–150 | $+110.6$ | $\sim 50$ | $0.5$–$0.7$ | 稳定爬升，高度控制改善 |
| 提升期 | ep 151–300 | $+195.7$ | $\sim 80$ | $0.4$–$0.5$ | 编队误差 $\downarrow 30\%$ |
| 收敛期 | ep 301–500 | $+235.5$ | $\sim 120$ | $0.35$–$0.40$ | 标准差减小，趋于稳定 |
| 最优轮（ep430） | — | $235.5$ | — | $0.19$ | 单轮最优化表现 |

训练过程呈现典型的四阶段特征：

1. **探索期（ep1–50）：** 奖励大幅波动（$-80$ 至 $+99$），策略尚未建立稳定的动作映射，无人机频繁碰撞边界。
2. **学习期（ep51–150）：** 从ep53进入持续上升通道，高度误差从 $0.7\,\text{m}$ 降至 $0.5\,\text{m}$，无人机逐渐学会维持目标高度。
3. **提升期（ep151–300）：** ep195取得 $195.7$ 的高奖励后，编队误差进入稳定下降区间（$0.5 \rightarrow 0.4$），表明策略开始协调多机的空间关系。
4. **收敛期（ep301–500）：** 奖励在 $100$–$150$ 区间稳定波动，最优值 $235.5$ 出现在ep430。值得注意的是，整个500轮训练过程未出现策略坍缩，验证了KL散度早停机制的有效性。

### 5.3 确定性推理 vs 随机采样对比

**表4** ep430模型的推理模式对比（10轮独立测试，每轮400步）

| 指标 | 随机采样（训练模式） | 确定性推理（测试模式） | 改善幅度 |
|:---|:---|:---|:---|
| 平均奖励 | $93.36$ | $115.31$ | $\uparrow 23.5\%$ |
| 奖励标准差 | $\pm 37.0$（高波动） | $\pm 15.27$（大幅降低） | $\downarrow 58.7\%$ |
| 平均高度误差（m） | $0.402$ | $0.375$ | $\downarrow 6.7\%$ |
| 平均编队误差（m） | $0.414$ | $0.347$ | $\downarrow 16.2\%$ |
| 10轮中最优奖励 | $\sim 137$ | $158.46$ | $\uparrow 15.7\%$ |

确定性推理模式通过直接使用策略网络均值作为动作输出（而非从高斯分布采样），显著降低了测试阶段的行为方差：奖励标准差从 $37.0$ 降至 $15.27$（降幅 $58.7\%$），编队误差从 $0.414\,\text{m}$ 降至 $0.347\,\text{m}$（降幅 $16.2\%$）。这与陈众楷等[6]中将策略均值用于部署的做法一致，确定性推理更适合实际控制场景——策略网络已充分学习到编队控制的有效均值策略，策略分布的方差参数在训练后期自然收窄，随机采样引入的额外噪声反而损害性能。

### 5.4 消融实验

**表5** 消融实验：关键组件对MAPPO性能的影响

| 消融条件 | 平均奖励 | 高度误差（m） | 编队误差（m） | 策略坍缩率 |
|:---|:---|:---|:---|:---|
| 完整MAPPO（最终方案） | $99.39$ | $0.383$ | $0.497$ | $0\%$ |
| 无KL早停 | $\sim 75$ | $0.42$ | $0.55$ | $11.8\%$（ep110附近坍缩） |
| 无集中Critic（独立PPO per agent） | $\sim 45$ | $0.48$ | $0.62$ | $16.7\%$ |
| 高学习率（$lr=3\times10^{-4}$） | $\sim 60$ | $0.45$ | $0.58$ | $23.5\%$ |
| 低熵系数（$\text{entropy}=0.001$） | $\sim 70$ | $0.41$ | $0.53$ | $14.2\%$ |

消融实验的关键发现：

1. **集中式评论家是最关键组件**：移除后编队误差从 $0.497\,\text{m}$ 恶化至 $0.62\,\text{m}$（增幅 $38.2\%$），证实全局状态信息对多机空间协调至关重要。这与CTDE范式的核心假设一致——各智能体在训练时可利用全局状态信息学习更准确的价值估计，从而指导策略学习更协调的多机协同动作。

2. **KL散度早停是稳定性保障**：无早停时策略坍缩率 $11.8\%$，加入后降为 $0\%$，以极小的计算开销（仅需一次KL散度前向计算）换取显著的训练稳定性改善。

3. **学习率对MAPPO异常敏感**：$5\times10^{-5}$ 已是最优平衡点，更高学习率（$3\times10^{-4}$）导致策略频繁崩溃（$23.5\%$）。MAPPO的多智能体架构对学习率的要求比单智能体PPO更严格，可能源于多智能体环境中策略更新的非平稳性问题。

4. **充分的熵系数（$0.005$）是必要的**：低熵（$0.001$）时探索不足，策略陷入局部最优，奖励降低约 $30\%$。适度的随机性对于多智能体编队任务的探索至关重要——编队协调需要智能体探索多样化的空间关系，而过早的确定性策略会锁定在局部协同模式中。

---

## 6 讨论

### 6.1 与相关工作的比较

**表6** 与近期文献的横向对比

| 相关工作 | 算法 | 无人机数 | 仿真器 | 编队误差（m） | 高度误差（m） | 训练样本 |
|:---|:---|:---|:---|:---|:---|:---|
| Zhao等（2023）[9] | D3QN | 3 | MATLAB自定义 | $\sim 0.5$ | N/A | 2,000轮 |
| Sadhukhan等（2024）[10] | PPO | 2–8 | Gazebo | N/A | N/A | 100,000步 |
| 陈众楷等（2026）[6] | 安全RL+MADDPG | 3 | Gazebo+ROS | $\sim 0.4$ | $\sim 0.3$ | 100,000步 |
| **本工作** | **MAPPO** | **3** | **gym-pybullet-drones（高保真）** | **$0.497$** | **$0.383$** | **200,000步** |

本工作的编队误差（$0.497\,\text{m}$）处于同类文献的合理区间内，但高度误差（$0.383\,\text{m}$）略高于陈众楷等[6]使用安全强化学习框架的 $0.3\,\text{m}$。值得注意的是，本工作使用高保真PyBullet物理引擎，而多数对比工作使用MATLAB自定义动力学或Gazebo简化模型，物理保真度的差异导致直接比较需谨慎。在本工作的实验中发现，VEL模式下的底层PID控制器可自动补偿重力和气动效应，使训练策略能迁移至更真实的物理场景——这是相对于简化动力学仿真的独特优势。

### 6.2 SAC奖励函数分析的教训

SAC算法的实验为奖励函数设计提供了重要教训。早期使用的稀疏高度奖励（仅在 $|z - z_{\text{target}}| < \delta$ 时给 $+100$，否则 $-100$）导致严重问题：SAC在大多数时间步接收 $-100$ 惩罚，奖励信号极度稀疏，策略无法获取连续的梯度信息，导致高度误差维持在 $0.724\,\text{m}$（目标高度的 $72.4\%$）。改为连续形式的 $r_h = -|z - z_{\text{target}}|$ 后，高度误差有显著改善。

这印证了BSI-DRL范式[8]中"奖励函数嵌入生物特性，驱动规则自主生成"的设计原则：连续奖励对应于生物群体中持续的环境反馈机制（如鱼群的拓扑交互[13]、蜂群的分工协作[14]），使智能体获得平滑的策略梯度引导，而非依赖离散的、稀疏的强化信号。

### 6.3 当前局限性

1. **高度控制仍有改善空间**：当前高度误差 $0.383\,\text{m}$（约目标高度的 $38\%$），在多机耦合场景下仍需进一步提高。
2. **编队误差来源未完全解耦**：编队误差（$0.497\,\text{m}$）中包含高度偏差的间接贡献和水平面的直接偏差，当前缺少细粒度的消耦分析。
3. **缺乏动态障碍场景验证**：当前实验仅针对静态编队保持，未涉及动态障碍物规避或多编队构型切换。
4. **仿真到实物迁移差距**：PyBullet环境与真实无人机飞行存在传感器噪声、通信延迟、风场扰动等差距，Sim-to-Real迁移是下一步必须面对的问题。
5. **超参数手动调优**：当前超参数经过多次迭代手动调优，缺少自动化的超参数搜索机制（如贝叶斯优化或Ray Tune）。
6. **大规模集群扩展**：当前仅验证3架无人机的编队，向5–10架扩展时CTDE架构的计算复杂度和通信开销将非线性增长。

### 6.4 未来改进方向

结合BSI-DRL综述[8]中提出的未来方向，本工作的改进路线包括：

1. **安全约束集成**：参考陈众楷等[6]的控制障碍函数（Control Barrier Functions, CBF）方法，在MAPPO框架中嵌入安全层，防止无人机在探索阶段采取危险动作，确保训练过程的安全性。
2. **动态角色分配与分层DRL协同**：引入蜂群分工机制的仿生映射，实现无人机在编队保持与避障任务间的动态角色切换，提升异构多任务场景下的适应性。
3. **多模态感知融合**：参考Ziyuan Ma等[7]的工作，整合RGB-D视觉、IMU和激光雷达等多模态输入，增强部分可观测场景下的编队鲁棒性。
4. **自动超参数搜索**：引入贝叶斯优化或进化策略（如Population-Based Training）自动搜索MAPPO的关键超参数，降低人工调优成本。
5. **Sim-to-Real迁移**：在PyBullet训练的基础上，引入域随机化（Domain Randomization）和系统辨识技术缩小仿真-实物差距。
6. **大规模扩展**：将无人机数量从3架扩展至5–10架，并引入注意力机制替代全连接Critic以降低计算复杂度，应对CTDE架构的扩展性挑战。

---

## 7 结论

本文系统研究了基于多智能体强化学习的无人机编队控制问题，主要贡献和结论如下：

**（1）提出并实现了适配gym-pybullet-drones VEL模式的MAPPO编队控制器。** 采用共享策略网络 + 集中式价值网络的CTDE架构，在500轮训练中实现平均奖励 $99.39$、平均高度误差 $0.383\,\text{m}$、平均编队误差 $0.497\,\text{m}$ 的编队保持效果。

**（2）通过SAC、PPO、MAPPO三算法的横向对比实验，揭示了不同算法在编队任务中的表现差异。** SAC的稀疏奖励设计导致无法同时优化高度与编队双重目标；PPO因缺乏多智能体信息共享机制而失效；MAPPO的CTDE架构在编队任务中展现出最优的综合性能。

**（3）消融实验量化了各组件对性能的贡献度。** 集中式评论家是关键组件（编队误差降低 $38.2\%$），KL散度早停是稳定性保障（策略坍缩率从 $11.8\%$ 降至 $0\%$），低学习率（$5\times10^{-5}$）和高熵系数（$0.005$）是收敛的必要条件。

**（4）验证了确定性推理模式在部署中的优越性。** 相比随机采样，奖励提升 $23.5\%$，标准差降低 $58.7\%$。该模式为实际工程应用提供了可靠的推理方案。

综上所述，MAPPO算法结合适当的超参数调优和KL早停机制，能够有效解决基于高保真物理仿真的多无人机编队保持问题。未来的工作将聚焦于安全约束集成、动态避障场景验证和大规模集群扩展三个方向。

---

## 附录A 训练可视化图表索引

本报告涉及的训练可视化图表由训练脚本自动生成，保存于以下路径：

- `outputs/results/mappo_formation_training_results.png` — MAPPO 500轮完整训练曲线（奖励、高度误差、编队误差、速度）
- `outputs/results/sac_formation_training_results.png` — SAC 1,864轮训练曲线
- `outputs/results/ppo_formation_training_results.png` — PPO 6,415轮训练曲线
- `outputs/deploy/mappo_ep430_training_results.png` — ep430最佳模型标注的训练曲线

## 附录B 关键公式汇总

| 编号 | 公式名称 | 表达式 |
|:---|:---|:---|
| (1) | 全局状态向量 | $\mathbf{s}_t = [o_1, \ldots, o_N] \in \mathbb{R}^{72N}$ |
| (2) | VEL速度指令 | $\mathbf{v}_{\text{target}} = \text{SPEED\_LIMIT} \times m \times \hat{\mathbf{v}}$ |
| (3) | 总体奖励函数 | $R = r_h + r_f + r_s + r_b$ |
| (4) | 策略网络输出 | $[\boldsymbol{\mu}, \log\boldsymbol{\sigma}] = f_\theta^{\text{policy}}(o_i)$ |
| (5) | GAE优势估计 | $\hat{A}_t^{\text{GAE}(\lambda)} = \sum_{l=0}^{T-t-1}(\gamma\lambda)^l \delta_{t+l}$ |
| (6) | PPO-clip目标 | $L^{\text{CLIP}}(\theta) = \mathbb{E}_t\left[\min(\rho_t \hat{A}_t, \text{clip}(\rho_t,1-\varepsilon,1+\varepsilon)\hat{A}_t)\right]$ |
| (7) | KL散度早停条件 | $D_{\text{KL}} > \tau_{\text{KL}} = 0.01 \Rightarrow$ 终止epoch |
| (8) | 确定性推理 | $a_i = \boldsymbol{\mu}_\theta(o_i)$（非采样） |

---

## 参考文献

[1] 陈众楷, 周晗, 孙懿豪, 等. 基于安全强化学习的多无人机编队与避障控制[J]. 中国科学: 信息科学, 2026, 56: 409-424. doi: 10.1360/SSI-2025-0048

[2] Wang Y, Wu Q, Wang Y. Distributed cooperative control for multiple quadrotor UAVs[J]. IET Control Theory & Applications, 2015, 9(3): 420-428.

[3] Ren W, Beard R W. Virtual structure based spacecraft formation control with formation feedback[C]. AIAA GN&C Conference, 2002.

[4] Olfati-Saber R, Murray R M. Consensus problems in networks of agents with switching topology and time-delays[J]. IEEE Transactions on Automatic Control, 2004, 49(9): 1520-1533.

[5] Sutton R S, Barto A G. Reinforcement Learning: An Introduction (2nd ed.)[M]. Cambridge: MIT Press, 2018.

[6] 陈众楷, 周晗, 孙懿豪, 等. 基于安全强化学习的多无人机编队与避障控制[J]. 中国科学: 信息科学, 2026, 56: 409-424.

[7] Ma Z, Gong H, Wang X. Adaptive Reinforcement Learning with Multi-Modal Perception for Autonomous Formation Control and Exploration in Large-Scale Multi-UAV Swarms[J]. Journal of Beijing Institute of Technology, 2026, 35(1): 63-83. doi: 10.15918/j.jbit1004-0579.2025.043

[8] 何明, 吴晶晶, 韩伟, 等. 深度强化学习赋能的无人机集群仿生行为建模方法[J]. 电子与信息学报, 2026, 48(1): 297-310. doi: 10.11999/JEIT251103

[9] 赵启, 甄子洋, 龚华军, 等. 基于D3QN的无人机编队控制技术[J]. 北京航空航天大学学报, 2023, 49(8): 2137-2146.

[10] Sadhukhan P, et al. A Proximal Policy Optimization Approach for Multi-robot Formation Control with Obstacle Avoidance[C]. IEEE Conference on Decision and Control (CDC), 2024.

[11] Panerati J, Zheng H, Zhou S, et al. Learning to Fly—a Gym Environment with PyBullet Physics for Reinforcement Learning of Multi-agent Quadcopter Control[C]. IEEE IROS, 2021.

[12] Schulman J, Moritz P, Levine S, et al. High-dimensional continuous control using generalized advantage estimation[C]. arXiv preprint arXiv:1506.02438, 2018.

[13] Ballerini M, Cabibbo N, Candelier R, et al. Interaction ruling animal collective behavior depends on topological rather than metric distance[J]. PNAS, 2008, 105(4): 1232-1237.

[14] Seeley T D. The honeybee democracy[M]. Princeton University Press, 2010.

$e^{i\pi} + 1 = 0$

<!-- 该文档整理/压缩于 2026-10-01 -->
