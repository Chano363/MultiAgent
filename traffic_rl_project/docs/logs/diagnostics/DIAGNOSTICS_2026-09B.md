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
- **复现命令 / 产物**：`run_training.py --experiment configs/experiments/formation_ed_ab_3train_1plus1.yaml --seed 0 --episodes 30 --checkpoint_dir outputs/checkpoints_ab_gate/`，日志 `outputs/log_ab_gate_train.txt`，权重 `outputs/checkpoints_ab_gate/`。
- **状态**：⚠️ **superseded（见下节 诊断-2026-09-28）**：本节的"末段<1000 / viol≈0"是 **30ep 窗口过短的假象**；100ep 短训证伪（末段 50ep 平均 pkCpl 破线、偶发爆发持续）。源门控治本方向仍成立，但**未收敛**。

### 诊断-2026-09-28-100ep短训证伪"30ep收敛"（偶发AB爆发持续，末段50ep平均破线） - 2026-09-28
- **诊断日期**：2026-09-28
- **主题**：把 9-26 的 30-ep 短训延长到 **100 ep**，检验"源头门控后偶发爆发是否收敛"。结论：**未收敛，30ep 的收敛是窗口太短的假象**。
- **复现命令**：`run_training.py --experiment configs/experiments/formation_ed_ab_3train_1plus1.yaml --seed 0 --episodes 100 --checkpoint_dir outputs/checkpoints_ab_gate100/`；日志 `outputs/log_ab_gate100_train.txt`；耗时 7182.4s (119.7min, 76.3 s/ep)。
- **原始数据（逐集解析，非估算）**：
  - 100 ep 中 **40 ep 出现 viol>0**。
  - **末段 ep51-100**：pkCpl **avg 1037.6 kN（>1000，破线）**、max **1586 kN**、**23/50 ep 破线**、viol 合计 **1138**。
  - 大爆发（viol>100 的灾难集）：ep31 (pkCpl 1483 / viol 214)、ep79 (1586 / 191)、ep80 (1469 / 351)、ep93 (1267 / 168)；对应 R = -104493 / -76710 / -145754 / -174175。
  - 脚本尾部打印"末段平均车钩力峰值: 996.0 kN"——**该口径为"末 10 ep"**，恰好落在两次小爆发之间，**不能代表末段整体**（易掩盖）。
- **对照**：9-26 的 30ep 在同口径（末段）得 pkCpl 980.9 / viol≈0 → 延长到 100ep 后末段 50ep 平均反升到 **1037.6**。**说明收敛判断至少需要 ≫30ep 窗口**。
- **机制解读**：源头门控（`AB_ADD_SOURCE_MAX_RATIO=0.6` + `AB_MAX_CONCURRENT_ADD=1`）只封"**RL 新增** AB 源"；未封 ①规则基线循环制动的 AB 兜底（`get_action_cyclic_braking` 在 ED 不足时触发，陡坡段多机车同触）②已触发 AB 沿 ~1.2km 列车 @200m/s 的**滞后压缩峰值**。故"偶发暴力 AB 吸态"仍周期性出现——与项目记忆记录的已知失败模式一致；9-19 的 value 治本（winsorize + value grad clip + KL 收紧）只解决"破线→value 污染放大"，**未消除爆发源头**。
- **诚实边界**：本 100ep 为 **from-scratch 探索期**，瞬态破线不等于终态策略不安全（旧 reward 的 1400ep 终态策略曾 53/35km 全 viol 0）。**但本结果足以否定"30ep 即已收敛"的判断**，且暴露"安全层无法在物理上真正兜住 ≤1000kN"这一契约缺口。
- **下一步（待决策，见下）**：①诊断爆发源（RL 新增 vs 规则基线 AB）；②预测式安全层（按位置+波速提前降 ED/退已触发 AB，使"≤1000kN 硬兜底"名副其实）；③直接 1400ep 全量重训、以终态策略评估为准（接受探索瞬态）。
- **状态**：**未收敛**；需在"补硬兜底 vs 直接重训"间决策。复现产物 `outputs/checkpoints_ab_gate100/`、`outputs/log_ab_gate100_train.txt`。

### 诊断-2026-09-30-100ep破线根因（车钩力口径错配 + AB 通道 + 安全层对 AB 无权限）

- **诊断日期**：2026-09-30
- **主题**：回答"纯规则基线为什么不破 1000kN？你是怎么诊断的、在什么剖面？"——定位 **100ep 短训权重在同一 1200 步窗口内车钩力 pkCpl 破 1000kN** 的根因。
- **诊断对象 / 剖面 / 种子**（全部可复现）：
  - **权重**：`outputs/checkpoints_ab_gate100/mappo_fleet_last_ep100_dec_ad2_cp_seed0_seed0.pt`（`decision_interval=10`，即 1s 策略节奏）。
  - **剖面**：主训练配置 `configs/experiments/formation_ed_ab_3train_1plus1.yaml`（`shuozhou_real_53km`，取**起始 1200 步窗口 = 120s**）。
  - **rollout seed**：2000（`set_seed(2000)`，初速 80 km/h）；编组 3 列 × (1 机车 + 94 货车 + 1 机车) = 6 agent / 96 车/列。
  - **复现方式**：本次诊断脚本为临时脚本（`tmp_diag_exec / metric / metric2 / mech / dt`、`tmp_diag_attr / ab_source`、`tmp_ablate_channel / coact`、`tmp_replay_policy`、`tmp_test_etcs_overlap`），已按项目规则（临时脚本用后即删）在结论入档后删除；**原始输出已全部落盘 `outputs/log_diag_*.txt`（不覆盖，长期保留）**，即为本节全部数据表的证据源。
  - 脚本方法（可重建，共同骨架）：`parse_experiment_yaml(EXP)` + `Registry.build` → `agent.load(CKPT)` → `set_seed(2000)` → `env.reset(seed=2000, options={'speed': 80/3.6})` → 逐步 `env.step`，每步取 `tr.dynamics.coupler_interface_forces()`（断面力口径）/ `_coupler_forces()`（净力口径）并记录 `info['executed_actions']`、每列非 RELEASE 车辆数、AB 源机车号、车头速度；消融场景通过 `mode ∈ {full, no_rl, no_traction, no_ab}` 改造执行动作实现（`no_rl`=喂零动作走规则层、`no_traction`=清零负 ed 通道、`no_ab`=清空 `ab_sources`）；dt 敏感性通过同时改写 `env.dt / tr.dt / tr.dynamics.dt / controller.dt` 并保持 1s 决策节奏实现。
  - 原始输出文件：`outputs/log_diag_exec.txt`、`outputs/log_diag_metric.txt`、`outputs/log_diag_metric2.txt`、`outputs/log_diag_mech.txt`、`outputs/log_diag_dt.txt`。

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
- **复现产物**：`outputs/log_diag_exec.txt`、`outputs/log_diag_metric.txt`、`outputs/log_diag_metric2.txt`、`outputs/log_diag_mech.txt`、`outputs/log_diag_dt.txt`（带时间戳归档，不覆盖）。

### 诊断-2026-09-30-治本改造回归验证（口径统一 + 安全层 AB 减权限 落地后复测）

- **诊断日期**：2026-09-30
- **主题**：承上一节 ⑧ 的第 ①/② 项（口径统一、给安全层对 AB 的实际权限），**方案落地后在同一 1200 步窗口复测**，验证闸门是否奏效、口径统一是否引入行为变化、速度控制是否受损。
- **改造落地内容**：见 `docs/logs/decisions/DECISIONS.md` **ADR-018**（全部改动尚未 git 提交）。
- **诊断对象 / 剖面 / 种子**（与上一节完全一致，控制变量）：权重 `outputs/checkpoints_ab_gate100/mappo_fleet_last_ep100_dec_ad2_cp_seed0_seed0.pt`（`decision_interval=10`）；剖面 `configs/experiments/formation_ed_ab_3train_1plus1.yaml`（`shuozhou_real_53km` 起始 1200 步）；`set_seed(2000)`，初速 80 km/h；3 列 × (1 机车 + 94 货车 + 1 机车) = 6 agent / 96 车/列。
- **复现方式**：临时脚本 `tmp_diag_regress_0930.py`（结论入档后按项目规则删除，方法同上一节骨架）；原始输出落盘 `outputs/log_diag_regress_20260930.txt` / `.json`（不覆盖）。
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
- **复现产物**：`outputs/log_diag_regress_20260930.txt`、`outputs/log_diag_regress_20260930.json`（不覆盖）。