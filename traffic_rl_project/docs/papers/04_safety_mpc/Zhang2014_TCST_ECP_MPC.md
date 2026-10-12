***
title: "论文信息卡 — Zhang & Zhuan 2014：ECP 重载列车 MPC 最优操纵（IEEE TCST）"
date: 2026-10-12
status: active
owner: Owner
fulltext: 未获取（IEEE Xplore 付费墙，页面抓取失败）
metadata_source: Crossref API 核实（2026-10-12）
------------------------------------------------------------

# Zhang & Zhuan 2014 — Optimal Operation of Heavy-Haul Trains Equipped With Electronically Controlled Pneumatic Brake Systems Using Model Predictive Control Methodology

> ⚠️ **摘要级：以下内容要点来自摘要/调研流水，未读全文。**
> 元数据经 Crossref API 核实；内容要点来源 = `docs/logs/diagnostics/DIAGNOSTICS_2026-10.md`
> 「文献调研-2026-10-12」（该次调研标 ▲ = 全文确认级，本次登记未复核全文）。

## 出处（Crossref 核实）

GB/T 7714-2015：Lijun Zhang, Xiangtao Zhuan. Optimal operation of heavy-haul trains equipped with electronically controlled pneumatic brake systems using model predictive control methodology[J]. IEEE Transactions on Control Systems Technology, 2014, 22(1): 13-22. DOI: 10.1109/TCST.2013.2238235.

- IEEE Xplore 文档号：6450066（页面抓取失败，未核实到摘要全文）。
- 注：调研任务中的简称"Optimal Operation of Heavy Hold Trains Equipped with ECP Brakes Using MPC"非正式题名；正式题名以 Crossref 为准。

## 核心主张（摘要/调研级，全文未核实）

1. **ECP-MPC 开山作**：重载列车装备 ECP（电控空气制动）系统，假设**逐车连续可控**——ECP 假设**绕开了气动时滞**问题。
2. MPC 最优操纵：车钩力等作罚项/约束的滚动优化（细节未核实）。
3. 文献流派定位：属「ECP 连续力近似」流派（同阵营后继 = Zhang/Chen/Guo 2026 IEEE/CAA JAS，本地部分全文 `Zhang2026_JAS_CouplerCompensation.txt`）。

## 对本项目的价值

- related work 声明与 ECP 流派的差异：本项目用**传统空气制动**（非 ECP），气动时滞真实存在，由规则层循环制动兜底（呼应 ADR-013「RL 定策 + 底层确定性执行」）。
- 「现有工作多假设 ECP（瞬时响应）」的引用出处之一（与本地 `Lu2025_CooperativeNMPC_MultiLoco.md` 信息卡的差异主张呼应）。
