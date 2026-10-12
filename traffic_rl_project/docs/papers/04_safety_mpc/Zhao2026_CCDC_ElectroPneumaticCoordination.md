***
title: "论文信息卡 — Zhao et al. 2026：电空协调 MPC（IEEE CCDC 2026）"
date: 2026-10-12
status: active
owner: Owner
fulltext: 未获取（IEEE Xplore 抓取失败；OpenAlex is_oa = false，付费）
metadata_source: OpenAlex API 核实（2026-10-12）
------------------------------------------------------------

# Zhao, Wang, Jiang, Sun 2026 — MPC with Electro-Pneumatic Coordination for Impulse Suppression in Heavy-Haul Trains on Long Steep Downhills

> ⚠️ **摘要级：以下内容要点来自摘要/调研流水，未读全文。**
> 元数据经 OpenAlex API 核实；关键结论来源 = `docs/logs/diagnostics/DIAGNOSTICS_2026-10.md`
> 「文献调研-2026-10-12」（该次调研标 ▲ = 全文确认级，本次登记未复核全文）。

## 出处（OpenAlex 核实）

GB/T 7714-2015：Hongyi Zhao, Qingyuan Wang, Haochen Jiang, Pengfei Sun. MPC with electro-pneumatic coordination for impulse suppression in heavy-haul trains on long steep downhills[C]//2026 38th Chinese Control and Decision Conference (CCDC). IEEE, 2026: 6036-6043. DOI: 10.1109/CCDC69976.2026.11559852.

- 作者单位：西南交通大学 电气工程学院（OpenAlex 机构字段核实）。
- IEEE Xplore 文档号：11559852（页面抓取失败）。

## 核心主张（调研级，全文未复核）

1. **电空协调 MPC**：空气制动**不进优化变量**，由速度误差触发循环「**减压-保压-缓解**」——与本项目 NMPC 基线的桥接逻辑同构（流派 3：分层/触发/级联）。
2. 长大下坡冲动抑制：调研记录**车钩力峰值降低 >8%**（来源 = DIAGNOSTICS 调研条目，本次未复核）。
3. 场景 = 长陡下坡重载列车（与本项目同场景的 MPC 侧对照）。

## 对本项目的价值

- 审稿人若质疑「MPC 不直接连续调制 AB、不含 AB 时滞」：可引本文（触发式循环）作为**文献常态**证据；与刘晓宇 2022（时滞内嵌进状态方程，另一可选路线，本地 `Liu2022_ATO_BrakeDelayModel.txt`）互补。
- ⚠️ 引用去重：勿与 DIAGNOSTICS 调研中的「CCDC 2025 虚拟连挂 DMPC」混淆（不同会议不同文）。
