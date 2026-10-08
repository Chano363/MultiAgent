***
title: "论文信息卡 — Lu2025：多机车协同 NMPC（长陡下坡）"
date: 2026-10-03
status: active
owner: Owner
source_pdf: Cooperative-Nonlinear-Model-Predictive-Control-for-Multiple-Locomotives-of-Heavy-Haul-Train.pdf
------------------------------------------------------------

# Lu, Zhang, Su 2025 — Cooperative Nonlinear Model Predictive Control for Multiple Locomotives of Heavy Haul Train on Long Steep Downhill Sections

> 本地全文：`docs/papers/Cooperative-Nonlinear-Model-Predictive-Control-for-Multiple-Locomotives-of-Heavy-Haul-Train.pdf`（6 页）。
> **用途**：本项目 **MPC 对比基线的来源**（`src/controllers/nmpc_controller.py`）。

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

- **MPC 基线来源**：本项目 `NMPCController` 的框架（多机车 NMPC + 多体/MT-2 车钩 + 车钩力约束 + 电/空协同 + AB 波传播延迟 + 逐线重喂坡度）与该文逐条对应。
- **可引用点**：「忽略车钩力」「忽略空气制动波传播延时（假设 ECP）」是领域通病——支撑本项目**显式建模车钩力 + AB 波速**的动机段。

## 与本项目实现的差异（对外必须讲清，否则「复现」不成立）

1. **对象**：原文是**单列内的多机车**协同；本项目是 **3 列群组**（platoon），列车**之间**的耦合是原文没有的。
2. **粒度**：原文用**多质点模型**；本项目 `NMPCController` 降阶为**每列 4 个集中质量块**（块间 MT-2 串联等效）。⇒ 逐车车钩力不在 MPC 约束内。
3. **代价/约束权重**：本项目另加终端代价、列距 ≥ 20 m 等。

⇒ 准确措辞：**参照 Lu 等的多机车 NMPC 框架实现，并降阶、扩展到多列群组**。
