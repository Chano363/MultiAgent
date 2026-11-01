# 证据卡：Wei2017《An air brake model for longitudinal train dynamics studies》

> **取得级别：仅摘要（Abstract）**。全文**未取得**（T&F 付费墙 + 无机构通道）。本卡内容**仅来自出版社公开摘要页**，**不代表读过全文**。摘要未给出的参数一律标"未取得"。

## 1. 题录与来源
- 题名：An air brake model for longitudinal train dynamics studies
- 作者：Wei Wei（通讯 weiwei@djtu.edu.cn）、Yang Hu、Qing Wu、Xubao Zhao、Jun Zhang、Yuan Zhang
- 单位：大连交通大学 交通运输工程学院（Wei/Hu/Zhao/Zhang J/Zhang Y）；澳大利亚中央昆士兰大学 铁路工程中心（Qing Wu）
- 期刊：Vehicle System Dynamics（**Vol 55, Issue 4: Special Issue: Longitudinal Train Dynamics**）
- 页码：**517–533**；投稿 2016-07-29，接收 2016-10-19，在线 2016-11-25
- DOI：10.1080/00423114.2016.1254261
- 基金：China Railway Corporation，grant **2015J007-O**
- 来源 URL：https://www.tandfonline.com/doi/abs/10.1080/00423114.2016.1254261
- 引用数据：1,576 views / 84 CrossRef citations

## 2. 关键词（原文）
Heavy haul train；air brake；longitudinal dynamics；air flow；distribution valve；automatic brake valve

## 3. 摘要原文（完整抄录）
> Experience of heavy haul train operation shows that heavy haul train fatigue fracture of coupler and its related components, even the accidents are caused by excessive coupler force. The most economical and effective method to study on train longitudinal impulse by reducing the coupler force is simulation method. The characteristics of train air brake system is an important excitation source for the study of longitudinal impulse. It is very difficult to obtain the braking characteristic by the test method, a better way to get the input parameters of the excitation source in the train longitudinal dynamics is modelling the train air brake system. In this paper, the air brake system model of integrated system of air brake and longitudinal dynamics is introduced. This introduce is focus on the locomotive automatic brake valve and vehicle distribution valve model, and the comparative analysis of the simulation and test results of the braking system is given. It is proved that the model can predict the characteristics of train braking system. This method provides a good solution for the excitation source of longitudinal dynamic analysis system.

## 4. 可核查证据（仅摘要级）

| 项目 | 摘要给出的内容 |
|---|---|
| 建模对象 | **机车自动制动阀（automatic brake valve）** + **车辆分配阀（distribution valve）** 模型 |
| 建模方法 | 空气制动系统模型与纵向动力学**集成系统**；制动特性难以实测，故以建模获取纵向动力学的**激励源输入参数** |
| 验证方式 | 给出了**制动系统仿真结果与试验结果的对比分析（comparative analysis of the simulation and test results）**，并称模型能预测制动系统特性 |
| 关键词提示 | air flow；distribution valve；automatic brake valve |

## 5. 用户点名必查项 —— 摘要是否覆盖？

| 必查项 | 摘要状态 |
|---|---|
| 自动制动阀 / 分配阀 建模细节 | 摘要**仅说明是重点**，具体方程/结构**未取得** |
| 副风缸（auxiliary reservoir）状态建模 | **未取得**（摘要无 auxiliary reservoir 字样） |
| 再充风后再制动的压力建立 | **未取得**（摘要无 recharge / re-brake 字样） |
| 参数能否用于 **120 型阀** | **未取得**（摘要未提 120 型；需全文的阀型章节确认） |
| 编组 / 吨位 / 定压 / 减压量 / 列尾 / 实测验证 | **未取得**（摘要未给具体编组与工况；仅笼统称有仿真-试验对比） |

## 6. 可迁移方法 / 不可迁移参数 / 未取得数据

### 可迁移方法（摘要级）
- **建模思路**：把空气制动系统模型作为纵向动力学的**激励源**，并与纵向动力学**耦合**——与本项目"空气制动 + 纵向动力学"框架一致。
- **阀级建模的对象划分**：区分**机车自动制动阀**与**车辆分配阀**两级，是 120 型阀建模的标准切入方式。
- **以仿真-试验对比验证制动系统模型**的思路（本项目可参照其验证口径）。

### 不可迁移参数
- 摘要未给任何数值参数 → **无可迁移参数**。
- 作者群为大连交大 + 中央昆士兰大学，与本项目编组无关；**不得因作者相同就默认阀型/参数一致**。

### 未取得数据（需全文）
自动制动阀与分配阀的具体方程与边界条件、副风缸充排风状态方程、再充风后再制动的压力建立过程、是否针对 120 型阀、仿真/试验工况（编组、定压、减压量）、误差量化。

## 7. 特别检查项

- **制动缸排气结束 ≠ 副风缸充满**：摘要**未区分**副风缸与制动缸 → 未取得，不能据此卡判定。
- **普通可控列尾排风 ≠ 主动列尾补气**：摘要**无列尾字样** → 未取得。
- 速度法过渡带 e_v、缓冲器过渡参数、tanh 速度宽度、Lei2019 式(7) μ(v)：**不属于本文主题**。

## 8. 关键页截图
**无**（全文未取得）。

## 9. 一句话短结论
Wei2017（VSD 55(4):517-533）是**机车自动制动阀 + 车辆分配阀**两级建模、并与纵向动力学耦合的经典文献，摘要确认其**做过仿真-试验对比**；但摘要**未给副风缸状态、再充风后再制动压力建立、是否针对 120 型阀**，这些正是本项目关心的内容，**必须取得全文后才能核对**，摘要不足以支撑任何参数迁移。
