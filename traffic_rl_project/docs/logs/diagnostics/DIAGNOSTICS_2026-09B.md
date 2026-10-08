***

title: 实验 / 诊断数据记录（2026-09 续，体积拆分承接文件）
date: 2026-09-30
status: active
owner: Owner + Agent
supersedes: partial（自 `docs/logs/diagnostics/DIAGNOSTICS_2026-09.md` 按体积拆分出本文件，零内容丢失）
------------------------------------------------------

# 实验 / 诊断数据记录（2026-09 续 / 承接）

> **拆分说明**：`DIAGNOSTICS_2026-09.md` 已达 189.9KB（接近 200KB 物理拆分阈值），按「日志类按类型/时间分子目录新文件」规则，把 **2026-09-25 起**的条目物理迁入本文件（原文照搬，**零内容丢失**）；原文件对应段落已移除并留指针。
> **记录法则**（原始数据落盘 / 完整命令 / seed+超参 / 分组明细 / 结论可解释 / 失败同样记录）见 [`DIAGNOSTICS_2026-09.md`](DIAGNOSTICS_2026-09.md) 顶部「记录法则」，本文件沿用同一法则。

## 索引

- 迁移入（自 `DIAGNOSTICS_2026-09.md`，原文照搬）：
  - 诊断-2026-09-25-AB需求驱动塑形修复
  - 诊断-2026-09-26-AB激活后滞后峰值击穿安全层（源头门控治本）
  - 诊断-2026-09-28-100ep短训证伪"30ep收敛"（偶发AB爆发持续，末段50ep平均破线）
- 新条目：
  - 诊断-2026-09-30-100ep破线根因（车钩力口径错配 + AB 通道 + 安全层对 AB 无权限）
  - 诊断-2026-09-30-「长训后期 value 发散」复核（观测证据与代码链路；结论：该叙事不成立）
  - 诊断-2026-09-30-metadata 编组不一致溯源（`physics` 块固报 1+0，运行实为 1+1）
  - 诊断-2026-09-30-X1/X4 判别性实验（闸门 on/off 有效性 + 滞后 AB 波机制反事实；产物时间戳 2026-10-01 00:0x–00:26）
- 改造-2026-09-30-X2 训练日志补落盘 `value_loss/entropy/approx_kl/value_norm_*`（独立 `train_loss_{tag}.csv` + TB；单测 `tests/test_logging_metrics.py`）

***

## 条目区

### 诊断-2026-09-25-AB需求驱动塑形修复

- **诊断日期**：2026-09-25
- **主题**：MAPPO 训练 seed0 **退化成"纯 ED 蠕行、全程不用空气制动(AB)"** 的根因定位与修复验证。
- **现象**：完整 53km 独立剖面评估，se0(ep2265 last 权重) 全程 `ab_steps=0`、`peak_coupler` 1248kN(>1000 超限)、`band_rate` 6%、末速 18km/h、reward −1.4e7；**seed1 则健康**（peak 744~815kN / viol 0 / band 99.99% / 末速 64）。decision_interval（1 vs 10）已排除为原因。
- **根因（三机制叠加）**：
  - `ab_cost=0.0`：AB 在奖励上完全中性，还会因触发 comfort/coupler 项被隐式扣分 → 策略学会"不用 AB"。
  - action dead zone `ab_mod∈[-0.5,0.5]`：该区间 RL 对 AB 完全无效，策略保持≈0 最安全。
  - 短窗 1200 步(≈120s/2.6km)：AB 长程收益（防掉速/车钩力）在窗内信噪比≈0。
  - **smoke 实证**：旧权重 `ab_mod` min=−0.088、mean=+0.55，**从未<−0.15** → 策略主动把 ab 杠杆压成"正向抑制"，主动放弃 AB。
- **文献依据**：Zhang2024（Cyclic Air Braking DQN on long downhill，Algorithms 2024, MDPI，DOI 10.3390/a17050190）式22需求驱动塑形：越限 Rc<0 罚 / AB engaged=0 / 释放 Rd>0 奖。成本按本项目量纲缩放，避免重蹈 `-80·ov²` 的 value 震荡（见诊断-2026-09-10）。
- **修复（已落代码）**：
  - `src/environments/train_fleet_env.py` `_calculate_reward_decomposed`（约 L801-818）：`ab_cost` 从 0 改为**需求驱动**——领航列带外或超速且本步 `ab_count<=0` 时 `ab_cost -= 0.5*needs_brake`（`needs_brake` = 带外/超速 0/1）。
  - `src/controllers/multi_loco_controller.py`（约 L247/L251）：AB 触发/抑制阈值 ±0.5 → **±0.15**。
- **smoke 验证（已跑通，证据入档）**：
  | # | 断言 | 输入 | 期望 | 实际 | 结论 |
  |---|---|---|---|---|---|
  | (a) | 塑形确定性 | 领航列 vel=28m/s(超 v_max22.2)，ab_count=0 vs 1 | reward Δ=−0.5 | **Δ=−0.500000**（精确=0.5·needs_brake） | ✓ |
  | (a) | 不误罚带内 | 领航列速度带内 | Δ=0.000000 | **Δ=0.000000** | ✓ |
  | (b) | 阈值触发 | ab_mod=−0.2 | 触发 MIN 档 | 触发 | ✓ |
  | (b) | 阈值不触发 | ab_mod=−0.1 | 不触发 | 不触发 | ✓ |
  - 旧权重 1200 步 rollout：reward +11070.7 / peak 652.4kN / band 100%，但 **ab_steps=0**（策略已放弃 AB，非阈值够不到）。
- **结论与下一步**：塑形给了 AB **反向调制负梯度**、阈值让小值可触达，AB"能参与"具备学习条件；但**证明"真的学到用 AB"还需用新 reward+阈值短训练重训，观察收敛后 ab_mod 是否进入 <-0.15**。── 待重训验证。
- **复现命令 / 产物**：见当日诊断脚本（`outputs/` 带时间戳 JSON）；smoke 断言脚本结果已归档。
- **状态**：根因定位 + 修复落地 + smoke 通过；**重训验证待续**。

### 诊断-2026-09-26-AB激活后滞后峰值击穿安全层（源头门控治本）

- **诊断日期**：2026-09-26
- **主题**：9-25 塑形修复后，短训证明"AB 能学了"，但**安全层兜不住 AB 沿列传播的滞后峰值**（viol 332/1549kN），需治本。
- **现象（9-25 短训 `episodes=30`，reward+塑形+阈值已落）**：
  - AB 确实被激活（此前不当事件从无到有），但 harm 爆发：ep12 viol134/pk1202、ep16 viol238/pk1391、ep22 viol91、ep30 viol332/pk1549/gap_min44m；末段平均 pkCpl **1162kN > 1000**。
- **前端根因（冲突目标）**：`SafetyLayer.protect`（L198-217）与 `_coupler_throttle_scale` 都按 **obs_state['coupler_forces']（上一时刻）** 钳制当前动作——**反应式**。RL 本步新增 AB 源时此刻力未升 → 不钳；AB 波以 ~200m/s 沿约 1km 列车传播约 5s（dt=0.1 约 50 步）**之后**压缩峰值才到达 → 拦不住 → 破 1000kN。**viol 口径核对**：`train_fleet_env` L500 `np.sum(coupler>limit)` 逐车辆累加，与正式评估一致，**非计数 bug，真击穿**。
- **治本修复（已落 `src/controllers/multi_loco_controller.py` L205-214/L245-275）**：
  - `AB_ADD_SOURCE_MAX_RATIO` 0.85 → **0.6**（力比≥0.6 即禁止 RL 新增 AB 源，更早封"高力叠加"）。
  - 新增 `AB_MAX_CONCURRENT_ADD=1`：单步决策内允许新增的 AB 源并发 **≤1**，杜绝多机车同步触发 AB 的压缩波叠加。
- **验证（重跑同 30-ep 短训，`outputs/checkpoints_ab_gate/`，命令同 9-25 加 `--checkpoint_dir outputs/checkpoints_ab_gate/`）**：
  | 指标 | 门控前(ab_smoke) | 门控后(ab_gate) | 结论 |
  |---|---|---|---|
  | 末段平均 pkCpl | 1162 kN（破线） | **980.9 kN** | ✓ <1000 |
  | 末尾 viol (ep30) | 332 | **3**，末段 avg 1.6 | ✓ 收敛 |
  | 末尾常规 ep viol | ep22=91 | 多数 ep=0 | ✓ |
  - **注意**：ep16 viol148/pk1232、ep18 viol60/pk1163 仍偶发爆发（探索期），源头门控只封"高力下新增源 + 并发"，**未封基线循环制动的 AB 兜底 + 已触发 AB 的滞后传播峰值**；末段已收敛到 viol≈0-9。
- **结论与下一步**：治本方向正确（AB 激活 + 车钩力<1000 初步可共存）。**正式长训（1400ep）前建议先补一次更长短训（60-100ep）确认偶发爆发收敛**；若仍在，需评估是否在安全层做"预测式 AB 峰值防护"（按位置+波速提前降 ED/退已触发 AB）。
- **复现命令 / 产物**：`run_training.py --experiment configs/experiments/formation_ed_ab_3train_1plus1.yaml --seed 0 --episodes 30 --checkpoint_dir outputs/checkpoints_ab_gate/`，日志 `outputs/logs/diagnostics/log_ab_gate_train.txt`，权重 `outputs/checkpoints_ab_gate/`。
- **状态**：⚠️ **superseded（见下节 诊断-2026-09-28）**：本节的"末段<1000 / viol≈0"是 **30ep 窗口过短的假象**；100ep 短训证伪（末段 50ep 平均 pkCpl 破线、偶发爆发持续）。源门控治本方向仍成立，但**未收敛**。

### 诊断-2026-09-28-100ep短训证伪"30ep收敛"（偶发AB爆发持续，末段50ep平均破线） - 2026-09-28
- **诊断日期**：2026-09-28
- **主题**：把 9-26 的 30-ep 短训延长到 **100 ep**，检验"源头门控后偶发爆发是否收敛"。结论：**未收敛，30ep 的收敛是窗口太短的假象**。
- **复现命令**：`run_training.py --experiment configs/experiments/formation_ed_ab_3train_1plus1.yaml --seed 0 --episodes 100 --checkpoint_dir outputs/checkpoints_ab_gate100/`；日志 `outputs/logs/diagnostics/log_ab_gate100_train.txt`；耗时 7182.4s (119.7min, 76.3 s/ep)。
- **原始数据（逐集解析，非估算）**：
  - 100 ep 中 **40 ep 出现 viol>0**。
  - **末段 ep51-100**：pkCpl **avg 1037.6 kN（>1000，破线）**、max **1586 kN**、**23/50 ep 破线**、viol 合计 **1138**。
  - 大爆发（viol>100 的灾难集）：ep31 (pkCpl 1483 / viol 214)、ep79 (1586 / 191)、ep80 (1469 / 351)、ep93 (1267 / 168)；对应 R = -104493 / -76710 / -145754 / -174175。
  - 脚本尾部打印"末段平均车钩力峰值: 996.0 kN"——**该口径为"末 10 ep"**，恰好落在两次小爆发之间，**不能代表末段整体**（易掩盖）。
- **对照**：9-26 的 30ep 在同口径（末段）得 pkCpl 980.9 / viol≈0 → 延长到 100ep 后末段 50ep 平均反升到 **1037.6**。**说明收敛判断至少需要 ≫30ep 窗口**。
- **机制解读**：源头门控（`AB_ADD_SOURCE_MAX_RATIO=0.6` + `AB_MAX_CONCURRENT_ADD=1`）只封"**RL 新增** AB 源"；未封 ①规则基线循环制动的 AB 兜底（`get_action_cyclic_braking` 在 ED 不足时触发，陡坡段多机车同触）②已触发 AB 沿 ~1.2km 列车 @200m/s 的**滞后压缩峰值**。故"偶发暴力 AB 吸态"仍周期性出现——与项目记忆记录的已知失败模式一致；9-19 的 value 治本（winsorize + value grad clip + KL 收紧）只解决"破线→value 污染放大"，**未消除爆发源头**。
- **诚实边界**：本 100ep 为 **from-scratch 探索期**，瞬态破线不等于终态策略不安全（旧 reward 的 1400ep 终态策略曾 53/35km 全 viol 0）。**但本结果足以否定"30ep 即已收敛"的判断**，且暴露"安全层无法在物理上真正兜住 ≤1000kN"这一契约缺口。
- **下一步（待决策，见下）**：①诊断爆发源（RL 新增 vs 规则基线 AB）；②预测式安全层（按位置+波速提前降 ED/退已触发 AB，使"≤1000kN 硬兜底"名副其实）；③直接 1400ep 全量重训、以终态策略评估为准（接受探索瞬态）。
- **状态**：**未收敛**；需在"补硬兜底 vs 直接重训"间决策。复现产物 `outputs/checkpoints_ab_gate100/`、`outputs/logs/diagnostics/log_ab_gate100_train.txt`。

### 诊断-2026-09-30-100ep破线根因（车钩力口径错配 + AB 通道 + 安全层对 AB 无权限）

- **诊断日期**：2026-09-30
- **主题**：回答"纯规则基线为什么不破 1000kN？你是怎么诊断的、在什么剖面？"——定位 **100ep 短训权重在同一 1200 步窗口内车钩力 pkCpl 破 1000kN** 的根因。
- **诊断对象 / 剖面 / 种子**（全部可复现）：
  - **权重**：`outputs/checkpoints_ab_gate100/mappo_fleet_last_ep100_dec_ad2_cp_seed0_seed0.pt`（`decision_interval=10`，即 1s 策略节奏）。
  - **剖面**：主训练配置 `configs/experiments/formation_ed_ab_3train_1plus1.yaml`（`shuozhou_real_53km`，取**起始 1200 步窗口 = 120s**）。
  - **rollout seed**：2000（`set_seed(2000)`，初速 80 km/h）；编组 3 列 × (1 机车 + 94 货车 + 1 机车) = 6 agent / 96 车/列。
  - **复现方式**：本次诊断脚本为临时脚本（`tmp_diag_exec / metric / metric2 / mech / dt`、`tmp_diag_attr / ab_source`、`tmp_ablate_channel / coact`、`tmp_replay_policy`、`tmp_test_etcs_overlap`），已按项目规则（临时脚本用后即删）在结论入档后删除；**原始输出已全部落盘 `outputs/logs/diagnostics/log_diag_*.txt`（不覆盖，长期保留）**，即为本节全部数据表的证据源。
  - 脚本方法（可重建，共同骨架）：`parse_experiment_yaml(EXP)` + `Registry.build` → `agent.load(CKPT)` → `set_seed(2000)` → `env.reset(seed=2000, options={'speed': 80/3.6})` → 逐步 `env.step`，每步取 `tr.dynamics.coupler_interface_forces()`（断面力口径）/ `_coupler_forces()`（净力口径）并记录 `info['executed_actions']`、每列非 RELEASE 车辆数、AB 源机车号、车头速度；消融场景通过 `mode ∈ {full, no_rl, no_traction, no_ab}` 改造执行动作实现（`no_rl`=喂零动作走规则层、`no_traction`=清零负 ed 通道、`no_ab`=清空 `ab_sources`）；dt 敏感性通过同时改写 `env.dt / tr.dt / tr.dynamics.dt / controller.dt` 并保持 1s 决策节奏实现。
  - 原始输出文件：`outputs/logs/diagnostics/log_diag_exec.txt`、`outputs/logs/diagnostics/log_diag_metric.txt`、`outputs/logs/diagnostics/log_diag_metric2.txt`、`outputs/logs/diagnostics/log_diag_mech.txt`、`outputs/logs/diagnostics/log_diag_dt.txt`。

#### ① 口径错配：训练/评估/违规计数/安全门控全用"每车净力"，而基准是"单钩断面力"

- 两种口径（`src/train_dynamics/train.py`）：
  - `_coupler_forces()`（L331-345）= **每车净力**（相邻钩矢量和 `forces[:-1]+=f; forces[1:]-=f`）——**当前训练/评估/计数用**。
  - `coupler_interface_forces()`（L347-357）= **单钩断面力**（正=压钩力）——代码注释明确"实测数据（张二田 929/1021 kN…）均为单钩断面力口径，**所有对照验证必须用它，避免用车厢净力造成误判**"。

| 口径 | FLEET 峰值 | 峰值步 | 步数 >1000kN | 车厢·步 >1000kN |
|---|---|---|---|---|
| 净力 `_coupler_forces()` | 1238.4 kN | t=1076 | 92 / 1200 | **110** |
| 断面力 `coupler_interface_forces()` | 1238.4 kN | t=1076 | 124 / 1200 | **857** |

- 同一次 rollout：**净力口径少报约 7.8×**（110 vs 857 车厢·步）。
- 逐列净/断比：train0 = 1.00、train2 = 1.00、**train1 = 0.87**（净力 965.6kN@t=1193 vs 断面力 1111.9kN@t=1136）。
- 峰值步（t=1076）断面力剖面：`sec min=-818.3 / max=+765.0 kN`，**异号相邻对 = 7/95** ——净力在拉压交界处把异号相邻钩叠加，正是误判来源。
- 影响的代码点（全部读净力）：
  - `src/environments/train_env.py` L330（`_state_snapshot` → 安全层输入）、L346（`_update_metrics` 违规计数）
  - `src/environments/train_fleet_env.py` L675-679（`_peak_coupler_n` / `_coupler_limit_violations`）
  - `src/controllers/multi_loco_controller.py` L106（`_coupler_throttle_scale`）、L242（`cur_coupler_ratio`）

#### ② 断面力口径四场景消融（决定性）：**AB 通道是破线的必要通道**

| 场景 | 断面力峰值 | 峰值步 | 步数 >1000kN | 逐列峰值 (kN) |
|---|---|---|---|---|
| **full**（策略） | **1238.4 kN** | t=1076 (train2) | **124 / 1200** | [948.1, 1111.9, 1238.4] |
| **no_rl**（纯规则基线） | **767.7 kN** | t=1078 (train2) | **0 / 1200** | [739.2, 751.0, 767.7] |
| **no_traction**（去牵引注入） | **1242.3 kN** | t=1181 (train2) | **110 / 1200** | [991.3, 975.5, 1242.3] |
| **no_ab**（去空气制动） | **870.1 kN** | t=1151 (train1) | **0 / 1200** | [730.1, 870.1, 737.8] |

- **纯规则基线在同一剖面确实不破 1000kN**（断面力 767.7kN，0 步破线）——**用户直觉正确**。
- **去掉 AB ⇒ 安全（870.1kN / 0 步）；保留 AB ⇒ 破线**（full 124/1200、no_traction 110/1200）⇒ **AB 是破线的必要通道**。
- **去掉牵引仍破线（1242.3kN）⇒ 牵引通道不是根因**（此前"带内牵引是根因"的推断被证伪）。

#### ③ 峰值步机制（t=1076，肇事列 train2）

- 峰值出现在 **车钩 #94（列尾端）**，`sgn=-1`（**受拉**）1238.4 kN；逐列峰值车钩号 = 0 / 71 / 94（0=机后，94=尾端）。
- 峰值步车头 **v = 29.2 km/h**，剖面坡度打印值 **+5.0‰**。
- **全列长期深空气制动**：t=1036 时 **96/96 辆非 RELEASE（全列在 AB）**，随后不均匀缓解至 t=1096 的 37/96。
- 车钩 #94 在 **t=1041–1096 持续受拉 1109–1238 kN**（dt=0.1 下呈 2 步周期高低跳变 520↔1238）。
- **峰值步肇事列两台机车执行动作 = `[ed=+0.50, ab=+0.00]`（纯电制动，当步无新增 AB 源）** ⇒ 破线是**已积累的 AB 状态 + 不均匀缓解**的后果，**非当步新增源**。
- **AB 源出现 884/1200 步**，首现 t=0、末现 t=1169；**断面力 >1000kN 共 124 步**，首破 t=901、末破 t=1199 ⇒ **AB 首现 → 首破滞后 901 步 = 90.1 s**。

#### ④ dt 敏感性：1238kN 是物理真实，**不是 dt=0.1 数值振铃**

| dt | 策略断面力峰值 | 步数>1000kN | 逐列峰值 (kN) | 规则基线峰值 | 基线步数>1000 |
|---|---|---|---|---|---|
| 0.1 | 1238.4 kN @t=1076 | 124 / 1200 | [948.1, 1111.9, 1238.4] | 767.7 kN @t=1078 | 0 / 1200 |
| 0.05 | **1377.7 kN** @t=2391 | 215 / 2400 | [949.0, 1377.7, 1272.8] | 780.9 kN @t=2196 | 0 / 2400 |

- 判据（脚本注释）：把 dt 减半（决策间隔 20 步保持 1s 策略节奏），同策略剖面——若峰值显著下降则为数值不稳定，若量级不变则物理真实。
- **结果：dt 减半峰值不降反升（1238→1378，+11%），基线基本不变（767.7→780.9）** ⇒ **排除 dt=0.1 数值振铃**，1238–1378 kN 量级为**物理真实**（AB 深制动 + 不均匀缓解造成列尾拉力）。基线两 dt 均 0 步破线 ⇒ **规则基线安全结论稳健**。

#### ⑤ 代码级根因：安全层对 AB **无物理权限**（"≤1000kN 硬兜底"名不副实）

- `SafetyLayer.protect`（`src/safety_layer.py` L205-217）规则2 作用在 **`proj_throttle`**（只编码机车制动深度）；`src/environments/train_env.py` L506-508 显示其钳制**只能下调 `ed_throttle`**（`ed_throttle = min(ed_throttle, max(-proj_throttle, 0))`）。
- `src/environments/train_env.py` L457-475：**`ab_sources` 在 `self.safety.protect`（L493）之前组装**并直接传给 `step_vehicles_ed_ab`（L510-513）⇒ **逐机车 AB 波源完全绕过安全层**。
  - **唯一例外**：安全层若触发 `etcs_ebi`，会把**全局** `ab_command` 提升为 `EMERGENCY`（L496-504）——即安全层对 AB 只有"**加**"的权限（升级全局紧急制动），**没有"减"的权限**（不能回退/降档已触发的 AB 源、不能降低 AB 深度）。
- 唯二 AB 闸门（`_coupler_throttle_scale`、`AB_ADD_SOURCE_MAX_RATIO=0.6`）都读**净力口径**且**反应式**（用上一时刻力），叠加 AB 波 ~5s 传播滞后 ⇒ 真实断面力已 >1000kN 时闸门仍不触发。
- `MultiLocoController._safety`（`src/controllers/multi_loco_controller.py` L63-67）为**死代码，从未被调用**。

#### ⑥ 已证伪 / 被推翻的假设（诚实留痕，不删）

- ❌ **"单通道都安全、需联合触发"**（此前"诊断-6"基于**净力口径**得出，含"no_traction 913kN 安全"）：用**断面力口径**重测，**no_traction 实为 1242.3kN / 110 步破线（不安全）**；"no_traction 913kN 安全"是**净力口径伪影**。⇒ 该结论 **superseded**。
- ❌ **"带内牵引注入是根因"**：no_traction 仍破线 ⇒ 牵引通道无关。
- ❌ **"1238kN 是 dt=0.1 数值振铃"**：dt 减半峰值不降反升 ⇒ 排除。
- ✅ **保留结论**：AB 通道是破线的必要通道（no_ab 安全；纯规则基线本区段不引 AB 故安全）；净/断面口径在拉压交界处差异最大（少报约 7.8×）。

#### ⑦ 诚实边界

- 100ep 为 from-scratch **探索期**，瞬态破线 ≠ 1400ep 终态策略不安全；但"安全层无法在物理上真正兜住 ≤1000kN"这一**契约缺口已实证**。
- 本诊断为 **单权重（seed0）× 单 rollout seed（2000）× 单窗口（1200 步）**；**未做跨 seed 统计**，不做"终态不安全"的泛化断言。
- 口径差异仅在**力方向交界（拉压切换）**处显著；纯压/纯拉段两口径一致（train0/train2 比值 1.00）。
- **"合成动作模式不破线"的对照未复测**：该对照所用临时脚本已不存在，无法核对其车钩力口径。按本诊断，其对策略不破线的两种解释为 (a) 若读净力口径 → 存在 ~7.8× 少报；(b) 该模式未形成"深 AB 持续 + 不均匀缓解"的列尾受拉状态。**均未验证，标为待核**（不据此下结论）。
- **未隔离**"列尾拉力是否由 AB 缓解不同步单一造成"：本节给出的是"深 AB + 不均匀缓解（非 RELEASE 96→37）与 #94 持续受拉同期出现"的**时间共现证据**，非受控隔离实验。

#### ⑧ 下一步（待决策，承接 9-28 的②/③）

1. **口径统一**：安全层门控 / 违规计数 / 评估指标全部改用 `coupler_interface_forces()`（SSOT 口径），消除 7.8× 少报与拉压交界误判。
2. **给安全层对 AB 的实际权限**：按位置 + 波速的**预测式 AB 峰值防护**（提前降 ED / 退已触发 AB），并把"当步新增源"硬闸门改读断面力 ⇒ 使"≤1000kN 硬兜底"名副其实。
3. **抑制 AB 不均匀缓解**（列尾拉力来源）：逐机车错峰缓解。
4. 直接 **1400ep 全量 5-seed 重训**，以**终态策略的完整剖面评估**为准（接受探索瞬态）。

- **状态**：**根因已定位（证据充分）+ 已证伪清单明确**；修复方案待用户决策后再落地。
- **复现产物**：`outputs/logs/diagnostics/log_diag_exec.txt`、`outputs/logs/diagnostics/log_diag_metric.txt`、`outputs/logs/diagnostics/log_diag_metric2.txt`、`outputs/logs/diagnostics/log_diag_mech.txt`、`outputs/logs/diagnostics/log_diag_dt.txt`（带时间戳归档，不覆盖）。

### 诊断-2026-09-30-治本改造回归验证（口径统一 + 安全层 AB 减权限 落地后复测）

- **诊断日期**：2026-09-30
- **主题**：承上一节 ⑧ 的第 ①/② 项（口径统一、给安全层对 AB 的实际权限），**方案落地后在同一 1200 步窗口复测**，验证闸门是否奏效、口径统一是否引入行为变化、速度控制是否受损。
- **改造落地内容**：见 `docs/logs/decisions/DECISIONS.md` **ADR-018**（全部改动尚未 git 提交）。
- **诊断对象 / 剖面 / 种子**（与上一节完全一致，控制变量）：权重 `outputs/checkpoints_ab_gate100/mappo_fleet_last_ep100_dec_ad2_cp_seed0_seed0.pt`（`decision_interval=10`）；剖面 `configs/experiments/formation_ed_ab_3train_1plus1.yaml`（`shuozhou_real_53km` 起始 1200 步）；`set_seed(2000)`，初速 80 km/h；3 列 × (1 机车 + 94 货车 + 1 机车) = 6 agent / 96 车/列。
- **复现方式**：临时脚本 `tmp_diag_regress_0930.py`（结论入档后按项目规则删除，方法同上一节骨架）；原始输出落盘 `outputs/logs/diagnostics/log_diag_regress_20260930.txt` / `.json`（不覆盖）。
- **自检（先跑 no_rl）**：断面力峰值 **767.7 kN @t=1078（train2，车钩#4）、0 步破线**，与上一节记录**分毫不差** ⇒ 复现骨架正确（train1 751.0 亦一致）。

#### ① 四场景复测（断面力口径，1200 步）

| 场景 | 改造后峰值 kN | 改造后步数>1000kN | 改造前峰值 | 改造前步数 | 逐列峰值 (kN) |
|---|---|---|---|---|---|
| full | **783.4** @t=928 | **0 / 1200** | 1238.4 | 124 | [777.6, 780.2, 783.4] |
| no_rl | 767.7 @t=1078 | 0 / 1200 | 767.7 | 0 | [756.8, 751.0, 767.7] |
| no_traction | **955.2** @t=848 | **0 / 1200** | 1242.3 | 110 | [777.6, 767.5, 955.2] |
| no_ab | 769.0 @t=1198 | 0 / 1200 | 870.1 | 0 | [704.2, 697.4, 769.0] |

- **四场景全部 0 步破线**（改造前 full 124 步、no_traction 110 步）⇒「≤1000kN 硬兜底」契约缺口在**本窗口**已闭合。
- `no_rl` 峰值与峰值步**逐字一致**（767.7 @t=1078）⇒ 验证闸门只作用于 **RL 新增的 AB 源**、未扰动规则层（符合设计边界"只禁新增、不撤销已建立源"）。train0 739.2→756.8 系口径统一后 `_coupler_throttle_scale` / 源头门控改读断面力所致（见 ②）。

#### ② 闸门开/关隔离对照（决定性归因）

同一条 full / no_traction 执行序列，**仅切换 `ab_new_source_veto` 是否生效**：

| 对照 | 峰值 kN | 步数>1000kN | `coupler_force_limit` 安全层事件 |
|---|---|---|---|
| full（闸门开） | 783.4 | 0 | 0 |
| full_nogate（闸门关，口径已统一） | 1156.7 | 17 | 328 |
| no_traction（闸门开） | 955.2 | 0 | 0 |
| no_traction_nogate（闸门关，口径已统一） | 1155.5 | 35 | 647 |

- **闸门贡献明确**：闸门开 → 峰值 −200~370 kN、破线 17/35 步 → 0 步。
- **口径统一的独立贡献**：`full_nogate`（闸门关但口径已统一）1156.7 kN / 17 步，对比改造前 full 1238.4 kN / 124 步 ⇒ **124→17 步来自口径统一**（门控改读断面力后更早介入，属**行为**变化而非仅计数），**17→0 步来自闸门**。
- 闸门命中步数：full 396、no_rl 425、no_traction 385、no_ab 286（每步每列各调一次，共 3600 次调用）。

#### ③ 速度控制未受损（反而更稳）

| 场景 | 车头 min/mean/max (km/h) | <40 km/h 比例 | 末速 (km/h) |
|---|---|---|---|
| full | 38.5 / 58.0 / 79.4 | 3.4% | 39.2 |
| full_nogate | — | 42.8% | 35.9 |
| no_rl | 40.0 / 60.5 / 79.4 | — | — |

- 闸门开 → 低速比例 **42.8% → 3.4%**、末速 35.9 → 39.2 ⇒ 封"暴力 AB 叠加"反而**改善**速度维持。
- **余量提示**：full / no_traction 末速 39.2 km/h 略低于 `v_min=40`（余量 0.8 km/h），单窗口结果，不作结论。

#### ④ 复现踩坑（新）

- `env.reset()` **未彻底清空列车动力学内部状态**：env 级累计量（`_peak_coupler_n` / `_coupler_limit_violations` / `_overspeed_violations` / `_safety_events`）与 `safety.last_events` 已重置，但动力学对象 / 安全层峰值历史（`_peak_hist`）等**有残留** → 同一 env 实例连跑多场景存在**顺序依赖**（train0 峰值 732.6↔756.8 kN 浮动）。**已改为逐场景重建 env**。教训见 `LEARNINGS.md` LRN-20260930-003。

#### ⑤ 结论与状态

- **闸门奏效、口径统一生效、无新安全问题**（本窗口四场景全 0 破线，速度未受损）。
- 上一节 ⑧ 的第 ①/② 项**已落地并验证**（ADR-018）；第 ③（抑制 AB 不均匀缓解）、第 ④（1400ep 全量 5-seed 重训）**仍待做**。
- **诚实边界**：仍为**单权重（seed0）× 单 rollout seed（2000）× 单窗口（1200 步）**，未做跨 seed / 全剖面统计，**不得据此断言终态策略安全**；100ep 为 from-scratch 探索期权重。
- **复现产物**：`outputs/logs/diagnostics/log_diag_regress_20260930.txt`、`outputs/logs/diagnostics/log_diag_regress_20260930.json`（不覆盖）。

### 诊断-2026-09-30-遗留①受控隔离（eot 缓解双向 vs 单向：列尾受拉无贡献，不改造核心物理）

- **诊断日期**：2026-09-30
- **主题**：上一节 ⑤ 的"列尾受拉 = 深 AB + 不均匀缓解"，其机制**未经受控隔离**（诊断⑦诚实边界）。遗留①候选 = "逐机车错峰缓解 / eot 缓解双向同步"。本轮用**现成 `eot` 开关**（`_reset_air_brake_command(0, eot=...)`，eot=True 时缓解波从队首+尾部双向传播、提升缓解同步性）做受控对比——若 eot 显著降列尾拉力 ⇒ 证实"缓解不同步"是列尾拉力的因果通道 ⇒ 支撑改造；若 eot 无显著影响 ⇒ 不轻动核心物理。
- **诊断对象 / 剖面 / 种子**（与前两节完全一致，控制变量）：权重 `outputs/checkpoints_ab_gate100/mappo_fleet_last_ep100_dec_ad2_cp_seed0_seed0.pt`；剖面 `configs/experiments/formation_ed_ab_3train_1plus1.yaml`；`set_seed(2000)`，初速 80 km/h；1200 步窗口；`decision_interval=10`。
- **复现方式**：临时脚本 `tmp_diag_eot_isolation.py`（方法同骨架）；原始输出 `outputs/logs/diagnostics/log_diag_eot_isolation_20260930_133819.json`。
- **结果（同一 full 权重，仅 eot 变量不同）**：

| eot | 断面力峰值 | 峰值步 | 步数>1000kN | 列尾受拉峰值 | 逐列峰值 (kN) |
|---|---|---|---|---|---|
| False（现状） | **648.2 kN** | t=837 | 0 | **317.2 kN** | [648.2, 551.0, 593.3] |
| True（双向缓解） | **627.4 kN** | t=851 | 0 | **317.2 kN** | [627.4, 551.3, 589.2] |

- **解读**：
  1. **治本(ADR-018)后**同一 full 权重峰值已 **1238.4 → 648.2 kN**（AB 减权限闸门奏效，0 步破线）——"破线根因"在闸门层面已闭合。
  2. **eot 双向缓解对列尾受拉零贡献**（317.2 不变）、对峰值仅 −3%（648→627）——「不同步缓解 → 列尾受拉」在**当前闸门净化的 AB 行为**下**不构成主导通道**。
  3. ⇒ **不支持改造核心缓解物理**（逐机车错峰缓解等）：其增益 ~3% 在 0 破线安全态上不划算，且会引入回归风险。遗留①**决策为"不改造（证据不支持）"**，避免二次重训。
- **诚实边界**：本对比是**受控隔离**（仅 eot 变量），但仍是**单权重 × 单 rollout seed × 单窗口**；列尾受拉峰值的"绝对大小"与坡度全貌相关，未做全剖面。§⑤"深AB+不均匀缓解"与列尾张拉的时间共现仍成立，只是其在**当前闸门行为下已不触发 1000kN 破线**。
- **结论 / 状态**：**遗留①采纳"不改造核心物理"**（证据：eot 无显著贡献）；「免二次重训」成立——可直接进入遗留②（1400ep 全量 5-seed 重训）。
- **复现产物**：`outputs/logs/diagnostics/log_diag_eot_isolation_20260930_133819.json`（不覆盖）。

### 诊断-2026-09-30-续训框架端到端验证

- **诊断日期**：2026-09-30
- **主题**：对 `ADR-019`（统一训练框架续训改造）做**框架行为级端到端验证**——验证"路径写错不再静默重训""`--episodes` = 总目标集数""历史/最优态拼接""`--resume-weights-only`"四条契约。
- **性质声明（诚实边界）**：本节全部为**框架冒烟**，窗口压到 60 步（`--override env_cfg.max_steps=60 --override curriculum=0:60`）以秒级跑完；**不产生任何策略性能结论**（reward/车钩力数值仅作"训练确实在跑"的活性证据），**不得引用为性能数据**。
- **诊断对象 / 种子 / 配置**：`configs/experiments/formation_ed_ab_3train_1plus1.yaml`（`3 列 × (1 机车 + 94 货车 + 1 机车)` = 6 agent，`decision_interval=10`）；`seed=0`；`device=cuda`。
- **复现命令**（`/tmp` 为临时目录；产物已归档到 `outputs/`）：

```sh
# ① 首发 1 ep
python run_training.py --experiment configs/experiments/formation_ed_ab_3train_1plus1.yaml \
  --episodes 1 --override env_cfg.max_steps=60 --override curriculum=0:60 \
  --checkpoint_dir /tmp/rs2/cp --results_dir /tmp/rs2/cp/results \
  --override dirs.figures_dir=/tmp/rs2/fig
# ② 续训到「总目标 3 ep」（应只跑 2 ep）
python run_training.py --experiment configs/experiments/formation_ed_ab_3train_1plus1.yaml \
  --episodes 3 --resume /tmp/rs2/cp/mappo_fleet_best_dec_ad2_cp_seed0.pt \
  --override env_cfg.max_steps=60 --override curriculum=0:60 \
  --checkpoint_dir /tmp/rs2/cp --results_dir /tmp/rs2/cp/results \
  --override dirs.figures_dir=/tmp/rs2/fig
# ③ `--resume latest`（应三信号一致 → 已训 3 ep）
python run_training.py ... --episodes 5 --resume latest ...
# ④ 路径不存在（应 FileNotFoundError，而非静默重训）
python run_training.py ... --episodes 5 --resume /tmp/rs2/cp/NOPE.pt ...
# ⑤ 纯权重迁移续训
python run_training.py ... --episodes 6 --resume /tmp/rs3/cp/mappo_fleet_best_dec_ad2_cp_seed0.pt --resume-weights-only ...
```

- **结果**：

| 场景 | 期望 | 实际 | 结论 |
|---|---|---|---|
| ① 首发 1 ep | 落 `best` + `last_ep1` + history 1 行 | reward +400.5、pkCpl 517kN、viol 0 | ✅ |
| ② `--resume <best> --episodes 3` | 只跑 2 ep、曲线拼成 3 行、best 继承 | 日志"**已训 1 ep，目标总 3 ep，本轮跑 2 ep**"；`[resume] 拼接历史曲线（1 行）`；CSV **3 行连续**（1/2/3）；`best +400.5` 未重置 | ✅ |
| ③ `--resume latest --episodes 5` | 三信号一致 → 已训 3 ep | 信号 `{metadata.done_ep: 3, history_rows: 3, filename: 3}` → "已训 3 ep，本轮跑 2 ep" | ✅ |
| ④ `--resume /NOPE.pt` | 抛错、不重训 | `FileNotFoundError: [resume] 指定的续训 checkpoint 不存在…（旧行为会静默从头重训，现已禁止）` | ✅ |
| ⑤ `--resume-weights-only` | 只加载权重、重置优化器/统计量 | 日志"（weights_only，优化器/统计量已重置）"、"已训 3 ep，目标总 6 ep，本轮跑 3 ep" | ✅ |

- **CSV 连续性原始行**（场景②）：`1,400.53,517.3,0.0` / `2,400.53,517.3,0.0` / `3,399.86,510.8,0.0`（`results_dir` 位于 `checkpoint_dir` 之下 ⇒ `_source_results_dir` 命中 `<dir>/results` 布局）。
- **冒烟暴露并修掉的两处真实缺陷**（详见 `LEARNINGS.md` LRN-20260930-005/006）：① `device=cuda` 下 `torch.get_rng_state()` 经 `map_location=cuda` 变 GPU `ByteTensor` → `set_rng_state` 抛 `TypeError`（补 `.cpu()`，CPU 单测测不出）；② logger `ckpt_meta` lambda 用自增前 `global_ep` → `last.pt` 内嵌 `done_ep` 比文件名**少 1** → `--resume latest` 多跑 1 集（改 `global_ep + 1`）。
- **单测**：`tests/test_resume.py` 14 项通过（含 CUDA 条件回归）；全量 `pytest tests/ -q` → **192 passed**（原 172 基线 + 20 新增，0 回归）。
- **状态 / 结论**：ADR-019 四条契约全部成立；「续训 `final_seed{0..4}` best 到 1400ep」现可基于内嵌 `done_ep` 安全执行（建议新输出目录 `final_seed{N}_v2` 防覆盖）。
  - **既有启动脚本语义核对**：`scripts/launchers/launch_final_5seed_v2.sh` 传的是 `--episodes 1400 --override start_ep=<已到 ep>`，在**新语义下恰好正确**（1400 = 总目标；`start_ep` 为最高优先级信号，与 metadata/历史一致，故仅为冗余保险）；在**旧语义下**同一命令会被读成"再跑 1400 集"（→跑满 2392 集）。且其 `results_dir = <ckpt_dir>/results` 命中 `<dir>/results` 布局 ⇒ 源历史曲线可正常拼接。
- **复现产物**：`outputs/logs/diagnostics/log_resume_smoke_20260930.txt`（六份原始日志合并，不覆盖）。

### 诊断-2026-09-30-「长训后期 value 发散」复核：观测证据与代码链路

- **诊断日期**：2026-09-30
- **主题**：复核"长训后期价值函数发散、破线后难以回退"（已写入 PPT 问题页）是否有数据支撑。
- **现象**：5-seed 续训中偶发车钩力破线 episode（pk 1000–1429 kN），项目叙事归因于"长训后期 value 发散"。
- **方法（无新仿真）**：只对既有产物做日志/代码复核 —— 解析 `outputs/logs_final_v2/seed*.log` 与 `outputs/logs_final_parallel/seed*.log`（PowerShell `Select-String`；`*.log` 被 .gitignore 忽略，ripgrep 取不到），读 `final_seed1_v2/results/metadata.json`，审 `src/safety_layer.py` / `src/controllers/multi_loco_controller.py` / `src/environments/train_env.py` / `src/trainer/logger.py`。**未运行 `run_training.py`，未占 GPU。**

**一、训练状态（证据 E1）**

- `pgrep -af run_training.py` 空；`logs_final_v2/seed{0..4}.log` 末次写入 **18:35–18:37**，复核时刻 22:39 → 已停约 4h。GPU `0%, 37MiB`。
- 断点完好：`final_seed{0..4}_v2/` 最新 `last` 分别 ep1067 / 1073 / 588 / 732 / 757。

**二、观测证据：发散叙事与数据不符（证据 E2/E3）**

按 100 集分箱统计 v1 段（`outputs/logs_final_parallel/seed*.log`，`Select-String` 解析 `Ep N/1400` 行）：

| seed | 分箱 | R_avg | pkCpl_max | viol_sum |
|---|---|---|---|---|
| seed0 | 1000–1099 | 11,002 | 938 | 0 |
| seed0 | 1300–1399 | 10,248 | 1041 | 6 |
| seed0 | **1400–1499** | 10,201 | **1195** | **18** |
| seed0 | 1500–1599 | 10,674 | 845 | **0** |
| seed0 | 1600–1699 | 10,692 | 855 | **0** |
| seed1 | 300–399 | 11,068 | 1263 | 51 |
| seed1 | 400–499 | 11,100 | 982 | **0** |
| seed1 | 600–699 | 10,937 | 1119 | 27 |
| seed1 | 800–842 | 11,145 | 938 | 0 |
| seed3 | **100–199** | 9,012 | 1196 | **140** |
| seed3 | 200–599 | 10.1k–11.1k | ≤919 | **0** |
| seed3 | 500–599 | 11,087 | 1266 | 73 |
| seed4 | 100–599 | 11.3k–11.5k | ≤882 | 0 |
| seed4 | 600–672 | 10,463 | 990 | 0 |

**破线 episode 明细**（v1 `logs_final_parallel` + v2 `logs_final_v2`；`viol` = **车厢·步**计数，非步数）：

| 段 | seed | Ep | R | pkCpl | viol(车厢·步) |
|---|---|---|---|---|---|
| v1 | seed0 | 1317 / 1356 / **1492** | +8412 / +10128 / **−14474** | 1041 / 1012 / 1195 | 5 / 1 / 18 |
| v1 | seed1 | 174 / 277 / 381 / 574 / **697** | +9886 / +9755 / +7215 / +10532 / **−16699** | 1187 / 1179 / 1263 / 1181 / 1032 | 11 / 20 / 34 / 18 / 1 |
| v1 | seed2 | 156 / 298 / **311** / 511 | +9112 / −1527 / **−13524** / +9872 | 1024 / 1053 / 1196 / 1202 | 1 / 5 / 22 / 48 |
| v1 | seed3 | 151 / 152 / 184 / **546** | +10437 / +9489 / +8502 / +9286 | 1011 / 1186 / 1196 / 1266 | 1 / 44 / 83 / 73 |
| v1 | seed4 | 541 | +6491 | 1026 | 1 |
| v2 | seed0 | 1006 / 1022 / 1039 / **1051** / 1057 | +10154 / +10132 / +10764 / **+9313** / +10233 | 1041 / 1014 / 1047 / **1140** / 1021 | 2 / 1 / 67 / **295** / 1 |
| v2 | seed1 | 1011 / 1037 / 1043 / **1045** | +11179 / +11415 / +10627 / +10870 | 1001 / 1125 / 1052 / **1429** | 1 / 210 / 1 / **1248** |
| v2 | seed2 | **541** / 548 / **562** / 571 / 582 | +10641 / +10810 / **+163** / +10083 / +10194 | 1264 / 1078 / 1044 / 1087 / 1058 | 8 / 1 / 24 / 1 / 33 |
| v2 | seed3 | 705 | +10520 | 1053 | 1 |
| v2 | seed4 | —（无 pkCpl>1000） | — | ≤998 | 0 |

**判读**：

1. **无单调退化**：seed0 跑到 ep1662，分箱 R_avg 始终 10.2k–11.3k；v2 seed1 全程 R≈+11.4k、`loss≈0`。
2. **破线是孤立事件且自恢复**：seed1 v2 ep1045（pk 1429 / viol 1248）→ ep1046 立刻回到 viol 0；seed1 v1 ep697（R −16699）→ 次 100 集窗口 viol_sum = 0。
3. **破线相位因 seed 而异**：seed3 最差窗口在**早期** ep100–199（viol_sum 140）、无 AB 相关后期破线；seed0 最差在**最晚** ep1400–1499 且其后两窗口归零。**不支持"长训后期统一发散"**。

**三、代码链路（证据 E4–E8 + 推断 I1/I2）**

- E4 `final_seed1_v2/results/metadata.json`：`git_commit=ff745cf`（ADR-018 治本）、`use_coupler_constraint=True`、`decompose=loco_ed_ab`、`resume=...final_seed1/mappo_fleet_best...`、`curriculum=500:0,1000:10,1200:20`、`n_env=4`。
- E5 口径已统一：喂给安全层的车钩力是**每车断面力视图** `coupler_interface_forces_per_vehicle()`（`train_env.py:335`），非净力。
- E6 **安全层对 AB 无权限**（关键）：`SafetyLayer.protect()` 在 decompose 路径确有调用（`train_env.py:509`），但其输出只回写 **ED** 通道（`train_env.py:522-524`）；`ab_sources` 在 `train_env.py:474-490` 组装完成后**原样**传给动力学（`:528`），安全层只能把 `ab_command` **升级**为 EMERGENCY（`:517-520`），**从不削减已发出的 AB 源**。该函数 docstring 写的"再映射回 (ED, AB)"与实现不符（实现只映射回 ED）→ **文档-代码不一致**。
- E7 闸门验证离分布：`outputs/logs/diagnostics/log_diag_regress_20260930.json` 字段 `ckpt=outputs/checkpoints_ab_gate100/mappo_fleet_last_ep100_dec_ad2_cp_seed0_seed0.pt`—— ADR-018「闸门 1238→783 kN、0 步超限」的验证用的是 **100 集短训玩具 checkpoint**，**不是** 5-seed 生产 checkpoint；而生产训练实测仍到 1429 kN。
- E8 **"value 发散"无测量**：`src/trainer/logger.py:116-121` 只写 6 个 scalar（reward / peak_coupler_kN / violations / total_loss / gap_err_mean / gap_min_m），**无 `value_loss` / `value_norm_mean/std` / `entropy` / `approx_kl`**；CSV/JSON 也只有 4 列（episode, reward, peak_coupler_kN, violations）。`mappo_agent.py` 计算并返回了 `value_loss`/`value_norm_*`（`:538-564`），但**没有被落盘**。→ 该结论目前**不可证伪**。

**推断（I1/I2，未做因果实验，标注为待验证）**：

- **I1 破线机制**：AB 波以 ~200 m/s 沿 ~1.4 km 列车（1+1）后传 → 滞后 ≈ 7 s（dt=0.1 → **~70 步**）才在全列生效。源刚发出时**实测力仍低、上升率 ≈ 0**，闸门的两条判据（反应式 `p0 ≥ 0.6·limit`、预测式 `rate·horizon`）**同时静默 → 闸门开口**；随后波前叠加使断面力穿越 1000 kN，而安全层唯一杠杆是 ED → 拦不住。这与 `ab_new_source_veto` docstring 自述的"反应式拦不住滞后峰值"一致，但**预测式在波起始处同样失效**。
- **I2 自激振荡**：车钩力规则在 `coupler_override='release'` 下把 ED 钳为 0（`safety_layer.py:275-277`），长大下坡上释放 ED → 列车加速 → 下一步需再制动 → 新 AB 源 → 新压缩波，形成极限环（破线后经一个波周期自恢复，与 E3 的"孤立+自恢复"形态相符）。

**四、待做的判别性实验（按性价比排序）**

| 编号 | 实验 | 判别的问题 |
|---|---|---|
| X1 | 用**生产 checkpoint**（`final_seed1_v2` 的 `last_ep1043`，即 ep1045 事件前一步）重跑 6 场景回归（gate on/off，1200 步，seed 2000） | 闸门在生产分布上是否仍守住 ≤1000 kN；若 gate-on 仍破线 → E7 的"离分布验证"被证实 |
| X2 | 在 `logger.py` + history CSV 增列 `value_loss` / `value_norm_mean` / `value_norm_std` / `entropy` / `approx_kl` | 让"value 发散"可证伪（当前 E8） |
| X3 | 逐步记录"在飞的 AB 源集合 + 每个源的发出步 + 断面力峰值" | 直接检验 I1 的 ~70 步滞后与"闸门开口时刻" |
| X4 | 反事实：给安全层"在飞波"锁（一波未过尾车前禁再增源）或允许削减已发 AB 源 | 检验 I1/I2 的因果性；若 pk 落回 <1000 kN 则机制确证 |

- **结论（可下的与不可下的）**
  - **可下**：5-seed 训练的**可观测**异常是**孤立、自恢复的车钩力破线 episode**（pk 1000–1429 kN，viol 1–1248 车厢·步），**不是**奖励/损失的单调发散；破线相位因 seed 而异，不支持"长训后期统一发散"。
  - **可下**：安全层对 AB 通道**无权限**（E6）且闸门在波起始处静默（I1），是破线可以被"结构性解释"的两个已确认/高置信点。
  - **不可下**：`value_loss` 是否发散——**未落盘**（E8），须先补 X2 才能断言。PPT 问题页"长训后期价值函数发散"的措辞应改为可观测口径，或补测量后再写。
- **复现命令 / 产物**：本条无新仿真产物（纯既有产物复核）；证据源 = `outputs/logs_final_v2/seed{0..4}.log`、`outputs/logs_final_parallel/seed{0..4}.log`、`outputs/checkpoints_formation/final_seed1_v2/results/metadata.json`。
- **状态**：复核完成，"长训后期 value 发散"**不成立**；破线机制待 X1–X4 判别性实验确认。

---

### 诊断-2026-09-30-metadata 编组不一致溯源（`physics` 块固报 1+0，运行实为 1+1）

- **诊断日期**：2026-09-30
- **主题**：`metadata.json` 里 `env_cfg.consist_preset=10kt_1plus1` 与 `physics.physics.consist_preset=10kt_1plus0` 并存的出处与成因；闭环「诊断-2026-09-30-100ep破线根因」小节标注的待核项。
- **现象**：读 `outputs/checkpoints_formation/final_seed1_v2/results/metadata.json`（`git_commit=ff745cf`，`physics_version=29569dcaf78a`）：`env_cfg.consist_preset=10kt_1plus1`，但嵌套 `physics.physics.consist_preset=10kt_1plus0`；`simulator_model` 串为
  `NeTrainSim-multibody|coupler=MT-2|braking=ED+AB-relief-wave|simcase=official|cyclic_degrade=True|consist=10kt_1plus0|grade=shuozhou_real_53km`，`simulator_model_version` 连带走样。
- **方法（无新仿真）**：全仓 Grep `consist_preset`（`*.py`，78 处命中）+ 读 `src/metadata.py` / `src/physics_governance.py` / `src/physics_config.py` / `src/trainer/train_runner.py` / `src/evaluation/evaluate_decompose.py` + 读取上述 `metadata.json`。**未运行训练/评估**。

**一、出处（同一根因，污染 3 处）**

| # | 位置 | 代码出处 |
|---|---|---|
| 1 | `metadata.json` → 嵌套 `physics.physics.consist_preset` | `src/metadata.py:82` `"physics": world_cfg` |
| 2 | `metadata.json` → `simulator_model` 串中 `consist=10kt_1plus0` | `src/metadata.py:50-62` `g('consist_preset')` 从 `world_cfg['physics']` 取值 |
| 3 | `simulator_model_version`（`sha1(simulator_model)[:12]`） | `src/metadata.py:66-68`，模型指纹连带失真 |

对照：`env_cfg` 块来自实验 YAML 的 `.env_cfg`（`configs/experiments/formation_ed_ab_3train_1plus1.yaml:24` `consist_preset: 10kt_1plus1`）→ **env_cfg 正确**。

**二、根因（三层追）**

1. **表象**：`metadata.json` 中 `env_cfg` 与 `physics` 两处编组互相矛盾。
2. **机制**：official 快照的定位是"固版/哈希/断言基线"（本就不跟随 env_cfg），但 metadata 的 `physics` 块**直接复用了它**（`train_runner.py:77` `world_cfg = official_world_config(PhysicsConfig())` = `physics_governance.py:37` 由 `PhysicsConfig()` **固版默认值**构造）⇒ "基线快照"被当"运行配置"上报。而 `src/physics_config.py:21` 的 `consist_preset` 默认值仍是 `10kt_1plus0`（同文件 `grade_profile` 已于 2026-09-09 改为 `shuozhou_real_53km` ⇒ **更新不完整，只改坡没改编组**）；该字段全仓**零读取者**（消费方一律走 `config.get('consist_preset', ...)`，如 `train_fleet_env.py:90`）⇒ **死字段无人读、过期无人察**。同源缺陷存在于其他入口：`train_fleet.py:135/156/161`、`train_cyclic_braking.py:268/273`、`evaluate_decompose.py:236`、`history/trainers/train_fleet_dqn.py:74`、`history/trainers/train_dqn_cyclic.py:67`。
3. **为什么没早发现**：守卫 `assert_case_allows` 只比对 `_OFFICIAL_LEGAL` 里 3 个调试开关（`physics_governance.py:27-34`），`consist_preset` **不在其中** ⇒ 不一致静默放行；且没有任何测试断言 `metadata.physics` 与本次 `env_cfg` 一致。

**三、影响判定（不是物理缺陷，是元数据缺陷）**

- **非物理缺陷**：`PhysicsConfig.consist_preset` 是死字段（Grep 78 处命中中无一处读取它），运行编组实际来自 YAML。
- **运行确实用了 1+1**：`env_cfg=10kt_1plus1` 与 `decompose=loco_ed_ab` + 6 agent（3 列 × 2 机车，`train_env.py:114-131` `consist_10kt_1plus1`）自洽。
- **是元数据/可复现性缺陷**：`physics` 块 + `simulator_model` + `simulator_model_version` **均误报 1+0**，违反「结果数值以 metadata 为准」——读 metadata 者会误判编组，跨运行比 `simulator_model_version` 会错配。历史影响范围：所有经 `official_world_config(PhysicsConfig())` 落盘 metadata 的运行（含 `final_seed*_v2`）。

**四、修复（已落代码，2026-09-30）**

- `src/physics_governance.py`：新增 `RUN_DERIVED_KEYS = ("consist_preset",)`；`official_world_config(physics, env_cfg=None)` 按该清单用 `dataclasses.replace` 从本次 env_cfg 派生覆盖固版默认值（不传 env_cfg → 行为与旧版完全一致）。其余物理项仍锚定 official 默认（固版基线不随实验漂移）。
- 入口接线（4 处）：`src/trainer/train_runner.py:77-79`（传 `cfg.env_cfg`）、`src/trainer/train_fleet.py:136`、`src/trainer/train_cyclic_braking.py:268`（各传 `{'consist_preset': consist_preset}`，并把三处重复调用收敛为单个 `world_cfg`）、`src/evaluation/evaluate_decompose.py:40-45/243-249`（新增 `run_consist(mode)`，与 `make_env` 共用同一表达式，避免两处手写编组串）。
- **未改**（历史复现线保留原样，避免破坏旧资产）：`evaluate_l1_long.py:93`、`evaluate_l1_rule_baseline.py:81`（其 env 配置本就是 1+0 = 固版默认，无失真）、`history/trainers/*`（归档代码）。

**五、验证**

| # | 断言 | 命令 / 输入 | 期望 | 实际 | 结论 |
|---|---|---|---|---|---|
| (a) | 不传 env_cfg 保持旧行为 | `official_world_config(PhysicsConfig())` | `consist_preset=10kt_1plus0` | `10kt_1plus0` | ✓ |
| (b) | 派生生效 | `official_world_config(PhysicsConfig(), env_cfg={'consist_preset':'10kt_1plus1'})` | 嵌套 physics 报 1+1 | `10kt_1plus1` | ✓ |
| (c) | 其余物理项不漂移 | 同上，比对 `grade_profile`/`coupler_force_limit_n`/`enable_cyclic_degrade` | 与固版默认相等 | 相等 | ✓ |
| (d) | 指纹随编组变化 | `simulator_model_version('official', derived) != snapshot` | 不相等 | 不相等；串内含 `consist=10kt_1plus1` | ✓ |
| (e) | 空值不覆盖 | `env_cfg={'consist_preset': ''}` | 回落固版默认 | `10kt_1plus0` | ✓ |

- 测试：新增 `tests/test_physics_governance.py`（6 项）；`python -m pytest tests/test_physics_governance.py -q` → **6 passed**。
- 全量回归：`python -m pytest tests/ -q` → **198 passed（exit 0）**（新增的 6 项含在其中）。产物 `outputs/logs/diagnostics/log_pytest_20260930_metadata_fix.txt`。
  - 口径说明：`pytest.ini` 已含 `addopts = -q`，CLI 再传 `-q` 合成 `-qq`，故日志**只打进度点、末行「N passed」汇总被抑制**；本条计数由日志点数（198）+ 后台任务退出码（0）共同判定，非估算。
- 入口编译：4 个接线脚本 `python -m py_compile` 通过（输出 `COMPILE_OK`）。
- 未做：**重跑训练/评估以重写既有 `metadata.json`** —— 既有 `final_seed*_v2` 的 `consist=` 字段与 `physics_version` 仍为旧值（失真），引用时须按 `env_cfg` 口径解读，或在下次续训落盘时自动修正。

**六、复现命令 / 产物**

- 证据读取（PowerShell，读 metadata；`*.json` 不受 .gitignore 影响）：
  `Select-String -Path outputs\checkpoints_formation\final_seed1_v2\results\metadata.json -Pattern 'consist'`
- 全仓读取点枚举：Grep `consist_preset` over `traffic_rl_project/**.py`（78 处命中，零处读 `PhysicsConfig.consist_preset`）。
- 测试：`python -m pytest tests/test_physics_governance.py -q`（6 passed）。
- 本条无新仿真数据产物（纯代码溯源 + 单测）。

**七、状态**

- 溯源完成 + 修复落地 + 单测（6/6）与全量回归（198 passed / exit 0）通过；代码尚未 git 提交。
- 待办：**重跑/续训后核对新 `metadata.json` 的 `physics.physics.consist_preset` 是否等于 `env_cfg` 值**（一次实测确认），并把该项加入下次续训的验证清单。
- **同族残留风险（未处理）**：`grade_profile` 与 `consist_preset` 同属"运行派生"字段，当前只在入口手写传入 `consist_preset`；若后续实验改用其他剖面（如跨线 `long_downhill_20km/35km`），同样需要把它登记进 `RUN_DERIVED_KEYS` 并在入口传参，否则会重演同类误报。见 `LEARNINGS.md` LRN-20260930-008。

***

### 诊断-2026-09-30-X1/X4 判别性实验（闸门 on/off 有效性 + 滞后 AB 波机制反事实）

- **诊断日期**：2026-09-30（跨零点运行，产物时间戳 `2026-10-01 00:0x–00:26`）
- **主题**：回答三件事——X1「ADR-018 的 AB 新增源闸门是否**只在玩具 ckpt 上有效**」；X4-a「把"新增 AB 源"锁死（**在飞波锁**）能否把峰值压回 ≤1000 kN」；X4-b「允许**削减已发 AB 源**能否把峰值压回 ≤1000 kN」。X2（日志补落盘）见 `### 改造-2026-09-30-X2`。
- **现象 / 触发**：ADR-018 的闸门（`AB_ADD_SOURCE_MAX_RATIO=0.6` + `AB_MAX_CONCURRENT_ADD=1` + `SafetyLayer.ab_new_source_veto`）此前只在 **100ep 玩具 ckpt** 上验证过；生产 ckpt（`final_seed*_v2/last_ep1043`）从未做闸门隔离对照，且其 metadata 的 `consist` 字段又是错的（见上一条），存在"闸门只在玩具权重上看起来有效"的可能。
- **方法（harness 与口径）**：
  - 临时脚本 `tmp_diag_x1x4.py`（**用后已删**，见"临时脚本"栏）；`TrainFleetEnv`（3 列 × 1+1 = 6 机车智能体，`decompose=loco_ed_ab`，`shuozhou_real_53km`，1200 步 = 120s 窗口，初速 80km/h，`decision_interval=10`，`seed=2000`）。
  - **口径**：峰值/破线步/逐列峰值全部取 **断面力** `coupler_interface_forces()`（SSOT，与 ADR-018 一致）。
  - 场景 = {闸门 on/off} × {机制变体}：`inflight`=在飞波锁（任一 AB 波在传播（`_air_brake_pending` 未达 或 `_air_brake_releasing`）即禁新增源）；`revoke`=峰值 ≥0.9·limit 时对当前 AB 源机车 `_reset_air_brake_command()`（撤销已发出的压缩波）。
  - **harness 一致性锚**：纯规则基线 `no_rl`（本 harness）**768.1 kN / 0 破线**，历史 `log_diag_regress_20260930.json` 为 **767.7 / 0**（Δ0.4 kN = 浮点归约顺序差）⇒ 两套 harness 等价。
- **原始数据（落盘，未覆盖）**：`outputs/logs/diagnostics/log_diag_x1x4_{prod_seed0v2,prod_seed1v2,toy100_x1,toy100_norl,stoch,toy100_stoch_full,toy100_stoch_x4}_*.{txt,json}`。

#### 一、X1：闸门 on/off（断面力峰值 kN / 破线步 / 车厢·步）

| ckpt | rollout | 闸门 | 峰值 kN | 步>1000 | 车厢·步 | 闸门命中步 | 末速 km/h |
|---|---|---|---|---|---|---|---|
| `final_seed0_v2/last_ep1043` | 确定性 | on | **761.0** | 0 | 0 | 361 | 45.1 |
| 同上 | 确定性 | off | **761.0** | 0 | 0 | 0 | 45.1 |
| `final_seed1_v2/last_ep1043` | 确定性 | on | **627.1** | 0 | 0 | 60 | 56.4 |
| 同上 | 确定性 | off | **627.1** | 0 | 0 | 0 | 56.4 |
| `checkpoints_ab_gate100/last_ep100` | 确定性 | on | 639.5 | 0 | 0 | 189 | 40.9 |
| 同上 | 确定性 | off | 628.1 | 0 | 0 | 0 | 41.4 |
| 同上 | **采样** | on | **1165.6** | **22** | 28 | 755 | 31.8 |
| 同上 | **采样** | off | **1268.9** | **29** | 199 | 0 | 37.9 |

- **生产 ckpt：闸门 on/off 轨迹逐位相同（761.0 / 627.1，均 0 破线）⇒ 闸门是 no-op**。原因：闸门只约束 **RL 新增 AB 源**这条通道，而这两条策略在窗口内根本不从该通道取动作（`veto` 命中 361/60 步却零影响，说明命中的那些步 RL 本就没申请新增源）。
- **玩具 ckpt：确定性下闸门同样近似 no-op（639.5 vs 628.1，甚至略升）**；只有在**采样探索态**下闸门才显出效果（1165.6 vs 1268.9，−103 kN / −7 破线步）——**但不足以守住 1000 kN**。
- ⇒ **对 X1 的回答**：闸门效力与"ckpt 是不是玩具"无关，而与"**该策略是否使用 AB 新增源通道**"有关；在**驱动（确定性）策略**上它无效，只在**采样探索态**下部分有效且效力不足。**"闸门有效"不能作为已达标结论**（ADR-018 中真正生效的是断面力口径统一，不是这道闸门）。

#### 二、X4-a：在飞波锁（把"新增 AB 源"锁到近乎全锁）

| 变体 | 基线 | 峰值 kN | 步>1000 | 车厢·步 | 闸门命中步 | 末速 km/h |
|---|---|---|---|---|---|---|
| `inflight_lock_nogate` | 无闸门 | **777.1** | **0** | 0 | 1199/1200 | 46.2 |
| `inflight_lock` | 闸门开 | **777.1** | **0** | 0 | 1199/1200 | 46.2 |
| 对照 `no_rl`（纯规则） | — | 768.1 | 0 | 0 | — | 41.2 |
| 基线 `full_nogate` | 无闸门 | 1268.9 | 29 | 199 | 0 | 37.9 |
| 基线 `full` | 闸门开 | 1165.6 | 22 | 28 | 755 | 31.8 |

- **机制确证**：把"新增 AB 源"锁死后峰值 **1268.9 → 777.1 kN（−39%）、破线步 29 → 0**，且结果与闸门开关**完全无关**（两者同为 777.1）⇒ "**RL 新增 AB 源 → 压缩波叠加 → 滞后峰值破线**"这条因果链成立。
- **代价（必须一并记录）**：锁在 **1199/1200 步**都命中，等于**彻底废掉 AB 杠杆**，行为退化到规则基线水平（对照 `no_rl` = 768.1）⇒ 它是"疗效确证"但**不是可部署解**（RL 失去 AB 决策权，与 ADR-013「机车级 ED/AB 分工」相冲突）。

#### 三、X4-b：允许削减已发 AB 源（反事实被否定）

| 变体 | 基线 | 峰值 kN | 步>1000 | 车厢·步 | 撤销次数 | 末速 km/h |
|---|---|---|---|---|---|---|
| `revoke_nogate` | 无闸门 | **1323.5** | **103** | 1580 | 334 | 35.3 |
| `revoke` | 闸门开 | **1636.8** | 79 | 1286 | 188 | 31.7 |
| 基线（无撤销） | — | 1268.9 / 1165.6 | 29 / 22 | 199 / 28 | 0 | 37.9 / 31.8 |

- **否定**：撤销已发 AB 源**不降反升**（1268.9 → 1323.5 kN，破线步 29 → 103）；闸门开时更差（1165.6 → 1636.8）。撤销 334/188 次说明该动作确实反复执行。
- **物理解释（与本项目既有结论一致）**：撤销 AB 源 → 该源进入**缓解排气** → 后续闸门/策略又可能再触发 → 形成"**缓解—再制动**"循环；而"缓解不同步 / 缓解后再制动"正是本项目反复实证的车钩力峰值主因（`_reset_air_brake_command` 的注释与 09-30 遗留① 隔离结论同源）。⇒ 「削减已发 AB 源」**不是解法**，应放弃该方向。

#### 四、复现性校准（重要，影响历史数值引用）

- 本 harness 在**确定性** rollout 下**无法复现**历史 `log_diag_regress_20260930` 的 `full 783.4` / `full_nogate 1156.7`；同 ckpt **采样** rollout（同 seed=2000）得 `1165.6` / `1268.9`——**同量级、不同值**。
- 两个独立旁证支持"历史 regress 是采样探索态"：① `no_rl` 两 harness 一致（768.1 vs 767.7，规则基线无采样差异）；② 确定性下本 harness 与**同日 post-commit** 的 `log_diag_eot_isolation`（现状 648.2 / eot 627.4）同族（本 harness 628.1–639.5）。⇒ 差异只出现在**受策略影响的场景**，来源即"动作是否按分布采样"。
- **引用纪律**：`log_diag_regress_20260930` 的 `full/full_nogate/no_traction*` 绝对值**属采样探索态、且依赖采样流，不可逐位复现**，与确定性评估不可并列；引用时须标注 rollout 模式与采样流不可复现。`no_rl`/`no_ab` 等**不依赖策略**的场景不受影响。

- **结论 / 下一步**：
  1. **不得**把 ADR-018 的 AB 闸门当作"已在生产策略上验证有效"——它在确定性驱动策略上是 no-op，在采样探索态效力不足（仍未守住 1000 kN）。
  2. 「在飞波锁」确证机制但会废掉 AB 杠杆 → 不作解决方案；「削减已发 AB 源」反事实**否定**（恶化）。
  3. 真正可守住 ≤1000 kN 的路径需另找：候选方向 = ①**约束 AB 源的时空分布**（如按列内位置错峰、限制单位长度内的源密度）而非一刀切锁死；②把"新增源"改为**RL 与规则基线共同决定的有界配额**；③在**断面力口径**下对 AB 相关动作做**双层投影**（ED 已投影，AB 未投影）。需另立实验裁决。
  4. 生产 ckpt 的闸门 no-op 结论**限于本 1200 步窗口**（起始 120s/2.6km），不作全域声明。
- **⚠️ 更正（2026-10-01 同日后补）："53km 全剖面 D-RL vs D-Rule 在现行物理下不存在"的表述作废。** 全仓复查得：D-RL **@53km** 的既有评估在 `outputs/results_decompose/` 有多份（`decompose_m1_*_53km`：`ep841`(5 seed) / `ep1623` / `ep1521` / `best_s0` / `best_s1` / `ep2265`，均 `physics_version=29569dcaf78a`），方向与"缺证据"相反——**`last` 权重守得住红线且不输规则层**（`ep841` 824.6 kN / band 97.1% / 末速 61.2 km/h / reward +221k；`ep1623` 863.5 / 99.7% / 72.0；`ep1521` 928.7 / 99.4% / 64.1；对照规则层 827.5 / 98.4% / 50.5 / −145k）；**破线者皆为"选错权重/训练不足"**（`best` 1682.5/1250.9、`ep120` 1162.1、`ep2265`(seed0 退化 `ab_steps=0`) 1248.0）。仍未重算的只有：**现行断面力口径 + 修好的 viol 计数**下的 M0 / M1(last) 两行，以及 **`--mask_lever ab` 对照**。详见 `DECISIONS.md` ADR-020「更正」行。
- **复现命令 / 产物**（WSL，`conda activate traffic_rl`，仓库根 `traffic_rl_project/`）：
  - `python tmp_diag_x1x4.py --ckpt outputs/checkpoints_formation/final_seed0_v2/mappo_fleet_last_ep1043_dec_ad2_cp_seed0_seed0.pt --tag prod_seed0v2 --scenes full,full_nogate,inflight_lock,revoke`
  - `python tmp_diag_x1x4.py --ckpt outputs/checkpoints_formation/final_seed1_v2/mappo_fleet_last_ep1043_dec_ad2_cp_seed1_seed1.pt --tag prod_seed1v2 --scenes full,full_nogate,inflight_lock,revoke`
  - `python tmp_diag_x1x4.py --ckpt outputs/checkpoints_ab_gate100/mappo_fleet_last_ep100_dec_ad2_cp_seed0_seed0.pt --tag toy100_x1 --scenes full,full_nogate`
  - `python tmp_diag_x1x4.py --ckpt outputs/checkpoints_ab_gate100/mappo_fleet_last_ep100_dec_ad2_cp_seed0_seed0.pt --tag toy100_norl --scenes no_rl,no_rl_nogate`
  - `python tmp_diag_x1x4.py --ckpt outputs/checkpoints_ab_gate100/mappo_fleet_last_ep100_dec_ad2_cp_seed0_seed0.pt --tag toy100_stoch --scenes full_nogate --stochastic`
  - `python tmp_diag_x1x4.py --ckpt outputs/checkpoints_ab_gate100/mappo_fleet_last_ep100_dec_ad2_cp_seed0_seed0.pt --tag toy100_stoch_full --scenes full --stochastic`
  - `python tmp_diag_x1x4.py --ckpt outputs/checkpoints_ab_gate100/mappo_fleet_last_ep100_dec_ad2_cp_seed0_seed0.pt --tag toy100_stoch_x4 --scenes full_nogate,inflight_lock_nogate,revoke_nogate,inflight_lock,revoke --stochastic`
  - 产物（JSON 内含全部逐列明细）：`outputs/logs/diagnostics/log_diag_x1x4_prod_seed0v2_20261001_000346.json`、`..._prod_seed1v2_20260930_235953.json`、`..._toy100_x1_20261001_001608.json`、`..._toy100_norl_20261001_002139.json`、`..._toy100_stoch_20261001_001349.json`、`..._toy100_stoch_full_20261001_001823.json`、`..._toy100_stoch_x4_20261001_002629.json`（各配同名 `.txt` 摘要）。
  - 检查脚本 `tmp_inspect_regress.py` / `tmp_inspect_ckpt.py` 同为临时脚本，**用后已删**。
- **状态**：X1/X4 完成并落盘；临时脚本已删；结论要求**修订 ADR-018 的效力表述**（闸门在确定性策略上 no-op）——待用户确认后写入 `DECISIONS.md`（本条目不擅自改 ADR）。

***

### 改造-2026-09-30-X2 训练日志补落盘优化器诊断量（使"value 发散"可证伪）

- **背景 / 触发**：诊断「训练后期 value 发散」时发现**无数据可判**——`TrainingLogger` 只落 `total_loss`，而 `MAPPOAgent.update()` 明明算了 `value_loss / policy_loss / entropy / grad_norm` 却**全被丢弃**；`approx_kl`（早停判定量）与 `value_norm_mean/std`（PopArt 尺度）**根本没有出现在返回 dict 里**。⇒ 该叙事既不能证真也不能证伪（承接同日「value 发散复核」条目：结论是叙事不成立，但当时缺硬证据）。
- **改造（已落代码）**：
  1. `src/algorithms/mappo_agent.py`：`update()` 返回 dict 新增 `approx_kl` / `value_norm_mean` / `value_norm_std`（在 epoch 循环前初始化 `approx_kl`，防 `epochs=0`/早停未触发时未定义）；新增 `_zero_stats()` 静态方法，统一 4 处"跳过更新"早退路径的字段（原先只回 `{'total_loss': 0.0}`，字段缺失会让下游 CSV 缺列）。
  2. `src/trainer/logger.py`：新增**独立** `train_loss_{tag}.csv`（表头 `episode, value_loss, policy_loss, entropy, approx_kl, grad_norm, value_norm_mean, value_norm_std, total_loss`）+ 同名 TB scalars + 终端行追加 `vloss / KL / vstd`。**刻意不给 `train_history_{tag}.csv` 加列**：既有 CSV 是旧 8 列 schema，加列会让续训 append 的行列数不一致（ADR-019 要求续训不截断既有 CSV）。
  3. `src/trainer/train_runner.py`：逐集把 `metrics` 的 7 个字段传入 `log_episode`。
- **验证**：新增 `tests/test_logging_metrics.py`（4 项：`update()` 返回含新字段且有限 / `_zero_stats` 字段完备 / 逐集写 loss CSV 且表头与行数正确 / 续训 append 不截断）；`python -m pytest tests/test_logging_metrics.py tests/test_mappo_train.py -q` → **10 passed**；**全量回归** `python -m pytest tests/ -q` → **202 passed（exit 0）**（198 旧 + 4 新；产物 `outputs/logs/diagnostics/log_pytest_20261001_x2.txt`；同 `pytest.ini` 的 `-qq` 效应，末行汇总被抑制，计数由点数 202 + 退出码 0 判定）。
- **未做 / 边界**：本条只**铺好取证通道**，不含"发散"结论；**下一次续训**起才会有 `train_loss_*.csv` 数据。TB 标量需重开 TensorBoard 才可见。
- **复现命令 / 产物**：`python -m pytest tests/test_logging_metrics.py -q`；产物 = 训练时自动生成的 `results/train_loss_{tag}.csv`（尚无，待续训）。
- **状态**：已落代码 + 单测通过；代码尚未 git 提交。

<!-- 该文档整理/压缩于 2026-10-01 -->
