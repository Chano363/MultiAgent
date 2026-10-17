***
title: "论文信息卡 — Lu2025：多机车协同 NMPC（长陡下坡）"
date: 2026-10-03
status: active
owner: Owner
source_pdf: Cooperative-Nonlinear-Model-Predictive-Control-for-Multiple-Locomotives-of-Heavy-Haul-Train.pdf
------------------------------------------------------------

# Lu, Zhang, Su 2025 — Cooperative Nonlinear Model Predictive Control for Multiple Locomotives of Heavy Haul Train on Long Steep Downhill Sections

> 本地全文：`docs/papers/04_safety_mpc/Cooperative-Nonlinear-Model-Predictive-Control-for-Multiple-Locomotives-of-Heavy-Haul-Train.pdf`（6 页）。
> **当前用途（2026-10-17原文复核）**：NMPC已退出主表，本卡作为related work和旧实现沿革。当前定位以`docs/RESEARCH_POSITIONING.md`及ADR-037为准；不能把下文历史实现描述当作忠实复现声明。

## 出处

GB/T 7714-2015：Ran Lu, Miao Zhang, Shuai Su. Cooperative nonlinear model predictive control for multiple locomotives of heavy haul train on long steep downhill sections[C]//2025 IEEE International Conference on Intelligent Rail Transportation (ICIRT). IEEE, 2025. DOI: 10.1109/ICIRT66379.2025.11216780.

作者单位：北京交通大学 先进轨道交通自主运行全国重点实验室 / 中国铁道科学研究院。

## 核心主张

1. **对象**：单列重载列车上的**多台机车**（分布式动力），运行于**长陡下坡**（LSDS，>12‰、>20 km）。
2. **模型**：重载列车**多质点纵向动力学**，整合电制动力、空气制动力、车钩力、运行阻力。
3. **控制**：NMPC，多目标代价 = 速度跟踪精度 + **车钩力缓和** + 能耗 + 稳定性。
4. **约束**：显式处理**限速**、**车钩安全限**、执行器约束。
5. **协同**：多机车分散决策，**电制动力与循环空气制动序列协同**。
6. **关键差异主张**：现有研究多假设 ECP（瞬时响应）；中国用 **LOCOTROL**，制动信号经管内空气波传递 → **存在不可忽略的延时**。本文**显式把空气制动波传播延时写进非线性动力学**。

## 对本项目的价值

- **MPC 基线来源**：本项目 `NMPCController` 的框架（多机车 NMPC + 多体/MT-2 车钩 + 车钩力约束 + 电/空协同 + AB 波传播延迟 + 经 `grade_at` 读坡度）仅属于同类方法参考，不能称与原文逐条一致；具体差异见下文原文复核。
- **可引用点**：传统空气制动传播延迟与单列分布动力协调困难。不能推广成领域普遍忽略车钩/延迟；前人不足须按`RESEARCH_POSITIONING.md`逐篇核对。

## 与本项目实现的差异（对外必须讲清，否则「复现」不成立）

1. **对象**：原文是**单列内的多机车**协同；本项目是 **3 列群组**（platoon），列车**之间**的耦合是原文没有的。
2. **粒度**：原文预测将216货车分为8组、加两机车构成**10个质点**；本项目 `NMPCController` 降阶为**每列 4 个集中质量块**（块间 MT-2 串联等效）。⇒ 逐车车钩力不在 MPC 约束内。
3. **代价/约束权重**：原文已经包含终端代价和终端约束集（式11–15），不能把终端代价列为原文缺失；本项目另有列距 ≥ 20 m 等扩展，其具体实现须独立审计。

⇒ 准确措辞：**参照 Lu 等的多机车 NMPC 框架实现，并降阶、扩展到多列群组**。


## 2026-10-17 原文方法与参数复核

- 已读取本地PDF第1–5页并渲染核对第3–5页（印刷112–114），不是仅依据本卡摘要。
- §II.B/§III：速度参考和空气制动时机预先确定，优化的是连续ED动作序列；不能用本论文给本项目新空气准入门或固定动作选优背书为忠实NMPC。
- 式(11)–(15)：终端代价/终端约束，ED幅值和增量约束、车钩/相对位移/逐车速度约束。少量固定动作两秒/四秒选优没有相同的可行性/稳定性保证。
- 表I及仿真：HXD1为200t/26m、C80为100t/12m，线性弹簧-阻尼车钩；预测聚合10点，Np=Nc=6、Ts=0.5s（3秒），同时优化6个连续输入向量。不能将其车钩参数或权重搬进188t机车/MT-2模型。
- 原文约180s充风、1600kN结果阈值均未迁移；本项目仍222s及1500/2250kN。也没有把本轮0.5/s试验斜率写成论文/实车常数。
- 复核及试验报告：D:/Codex/Documents/Train/controller_takeover_20261017/预测制动协调试验与原文复核_20261017.md。关键限制是动作序列、未来可行接续与预测模型误差，不能仅凭论文3秒窗口认定本项目改成3秒即可通过。
