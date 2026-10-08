---
title: "论文信息卡 — Wang2025：重载列车纵向系统的非线性动态（载荷/车钩游隙/缓冲器→分岔混沌）"
date: 2026-09-05
status: active
owner: Owner
source_pdf: Analysis of the nonlinear dynamic behavior of longitudinal systems in heavy-haul trains.pdf
fulltext: Wang2025_longitudinal_nonlinear_fulltext.txt
---

# Wang et al. 2025 — Analysis of the nonlinear dynamic behavior of longitudinal systems in heavy-haul trains

> 全文字符检索件：`Wang2025_longitudinal_nonlinear_fulltext.txt`（18 页，36.2k 字符）。
> **用途**：为"车钩游隙(slack)/缓冲器阻抗特性/载荷 的变化会**强烈改变**重载列车纵向动力学（甚至分岔/混沌）"提供权威依据 → 坐实 E4-H"逐车钩参数离散为何有物理意义"。

## 出处
GB/T 7714-2015：Leiting Wang, Yang Jin, Wangxiang Li, Chenyang Tang. Analysis of the nonlinear dynamic behavior of longitudinal systems in heavy-haul trains[J]. Electronic Research Archive, 2025. DOI: 10.3934/era.2025027（Open Access）。

## 核心主张（对本项目有用）
1. 重载列车纵向系统的主要不确定性来源 = **载荷(payload)、车钩游隙/间隙(coupler slack)、缓冲器性能/阻抗特性(buffer device performance)**；这些变化可能使系统**分岔→混沌**。
2. 缓冲器本质是**非线性阻抗 + 迟滞(hysteresis，摩擦型)**；车钩有**连接游隙(slack)**，与干摩擦/碰撞伴生——这两者正是本项目 `coupler_gap`(死区) + MT-2 摩擦迟滞模型的物理映射。
3. 以 2-DOF 纵向模型 + R-K4 + 分岔图/相图/Poincaré 映射分析，得到周期倍化分岔→拟周期→混沌。
4. 引用了 **Yadav & Vyas 2023（AAR 自动车钩 slack → 纵向动力学与 jerk，Vehicle System Dynamics, DOI 10.1080/00423114.2022.2107546）**——补充了"车钩游隙定量影响纵向动力学/冲动"的另一先例。

## 对本项目 E4-H 的直接价值
- **参数变化不是"微小扰"**：载荷/游隙/缓冲器特性在参数域里能驱动纵向系统发生**分岔/混沌** → 说明逐车钩参数离散会使列内力分布出现**本质性、非线性**的重新分配（呼应 T1 图"异构→逐钩力重分布"图）。
- 为 `--hetero` 扰动的 **物理显著性**提供依据：不是拍脑袋的 ±15%，而是"这类参数的偏移会强烈改变纵向动力学"的对应文献支撑。
- 引出的 Yadav&Vyas 2023 可作 **coupler slack→force** 的补充先例（备查/可再下载）。

## 落地建议
- 论文 Related Work / E4-H 动机：引用 Wang2025（+Yadav&Vyas2023）说明"车钩游隙/缓冲器参数偏移会非线性地改变纵向动力学"，从而论证"逐车钩异构分布 + 控制层鲁棒/外推"的必要性。
- 与 Krishna2020（异构→列内力）互为：一个"力学/运行安全层异构"、一个"非线性动力学敏感层"。

> 待办：如需要可人工精读其缓冲器阻抗/游隙的具体取值与分岔图，回填更细参数档位（当前卡已含其引用链 Yadav2023）。

<!-- 该文档整理/压缩于 2026-10-01 -->
