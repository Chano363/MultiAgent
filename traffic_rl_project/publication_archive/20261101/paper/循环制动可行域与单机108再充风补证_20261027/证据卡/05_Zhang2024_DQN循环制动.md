# 证据卡 05｜Zhang et al. 2024《Deep Q-Network Algorithm-Based Cyclic Air Braking Strategy for Heavy-Haul Trains》

## 1. 题录（已核对原文首页）
- 题名：Deep Q-Network Algorithm-Based Cyclic Air Braking Strategy for Heavy-Haul Trains
- 作者：Changfan Zhang, Shuo Zhou, Jing He, Lin Jia（湖南工业大学电气与信息工程学院）
- 期刊：Algorithms, 2024, 17(5), 论文号 190
- DOI：原文未在抽取文本中给出（待知网/期刊页核对，不臆填）
- 本地原文：`F:\TRAEWORK_SPACE\MultiAgent\traffic_rl_project\docs\papers\Zhang2024_DQN_CyclicBraking_Downhill.pdf`
- 文本抽取：`_work\Zhang2024_DQN.txt`（分页段另有 `Zhang2024_p4_6.txt`、`_p9_11.txt`、`_p12_14.txt`）

## 2. 研究对象与工况（原文明确）
| 项目 | 原文内容 | 位置 |
|---|---|---|
| 编组 | 1 HXD1 + 108 辆货车 + 1 HXD1 + 108 辆货车 | §4.1，PDF 第 12/17 页 |
| 总重 | 20,000 t | §4.1 |
| 机车/货车 | HXD1：200 t、35.2 m；C80：100 t、13.2 m | Table 1，PDF 第 12/17 页 |
| 线路 | 朔黄线龙宫—北丹（Longgong–Beidaniu），23,800 m，10～12‰ 连续大下坡，限速 80 km/h | §4.1，Table 2 |
| 初速度 | 65 km/h | §4.2.1 |
| 时间步长 | Δt = 100 s | §4.2.1 |
| 缓解速度下限 | 40 km/h（原文写明"for a 20,000-ton heavy-haul train formation"） | 式(10) 下方 |
| 最高制动速度 | 80 km/h | Table 3 |

## 3. 关键原文
### 3.1 再充风约束（§2.2，式 9）
> "To guarantee sufficient braking force in the next braking cycle, sufficient time should be ensured for refilling the air pipe to its maximum pressure [26]. In other words, the release phase must not be shorter than the minimum air-filling time $T_a$, as stated in the operating guidelines."

$$t_{j+1}^{b}-t_j^{r}\ge T_a \qquad (9)$$

紧接着原文写明：
> "$T_a$ is closely related to the formation of the train and the pressure drop within the train air pipe. For predetermined train parameters, the air-filling time needs to be ascertained."

### 3.2 算法参数（Table 3，PDF 第 12/17 页）
- Minimum air-refilling time $T_{AI}$ = **100 s**
- Minimum braking speed $V_{min}^{r}$ = 40 km/h
- Maximum braking speed $V_{max}^{r}$ = 80 km/h
- Planned operation time T = 1500 s

### 3.3 速度约束（式 10）
$$V_{min}^{r}\le v \le V_{r}$$
（原文该式排版疑有笔误，右端应为上限 $V_{max}^{r}$；本卡按上下文理解为"下限 40、上限 80 km/h"，不改写原文。）

## 4. 与当前模型的关系
**可用于当前模型**
- 这是"$T_a$ 依赖编组与减压量、必须按具体编组预先确定"的明确文字证据，可直接反驳"所有编组都用 222 s"。
- 其下限 40 km/h 是**针对 20,000 t 编组**给出的，说明缓解速度下限本身也是编组相关量，不能照搬。

**仅方法参照**
- 把再充风时间作为硬约束嵌入 DQN 的约束处理方式；状态/动作/奖励设计。
- 100 s 的取值是 2 万吨 1+1 编组的算法超参数，**不是 108 辆单机的实测值**，也不是本项目应采用的 222 s。

**待确认**
- 100 s 的来源：是实测、规范还是调参取值，原文未在表 3 处给出出处；需查其参考文献 [26]。
- 计时起止点：原文只说"refilling the air pipe to its maximum pressure"，未定义是司机缓解指令、列尾收到缓解还是列车管达定压。

**不可迁移**
- 1HXD1+108+1HXD1+108、20,000 t、40 km/h 下限、23.8 km 线路、Δt=100 s 的组合，不可直接用于 1+0、10,988 t、49.6 km、内部细步场景。
- 不得把"有 $T_a$ 约束"理解为"该约束值对所有编组相同"。

## 5. 适用边界
- 适用：朔黄线 2 万吨 1+1 编组、10～12‰ 长下坡、限速 80 km/h、初速 65 km/h。
- 不适用：单机 108 辆；需要秒级内部细步的车钩力计算（本文 Δt=100 s，不用于车钩力峰值验收）。

## 6. 缺失
- $T_a=100$ s 的实测/规范出处与计时起止点。
- DOI 与卷期页码（抽取文本只显示 "Algorithms 2024, 17, 190"）。
- 108 辆单机车工况的任何数据（原文未涉及）。
