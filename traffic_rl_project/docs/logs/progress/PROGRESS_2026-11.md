***

title: 阶段二执行流水 2026-11
date: 2026-11-12
status: active
owner: Owner + Agent
supersedes: 无（本文件 = docs/PROJECT_PIPELINE.md 2026-11 条目的原样迁出，内容零丢失）

> **角色**：阶段二**执行流水**（append-only：历史 ✅/❌ 条目一律保留，新条目按月追加到文件末尾）。
> 项目**总览 / 现行状态 / 下一步**见 `docs/PROJECT_PIPELINE.md` **§〇**；诊断数据见 `docs/logs/diagnostics/`。
> **来源**：2026-11-12 自 `docs/PROJECT_PIPELINE.md` 按时间物理拆出，正文一字未改。

***

## 阶段二执行流水（2026-11-10 ~ ，2026-11-12 自 PROJECT_PIPELINE 迁入，正文零改动）

### 4.3.5 三段推进计划（2026-11-10 用户裁定，当时执行，已结束）

> ⛔ **已被 ADR-064 + ADR-066 取代（2026-11-11 / 11-12），不再执行，原文保留仅存档**：
> 段 1（60 集）→ 现为 ADR-066 阶段 1 的 **20 集**；段 2（诊断）→ 已并入阶段 1 收尾的三项诊断；
> 段 3（1400 集规模训练）→ **ADR-064 废止「1400 集」硬指标**，训练量档位至今未定（待 §4.3.6 B 的 pilot，且 pilot 已中止）。
> 现行任务只看 §〇。

> 授权边界：**全部本地**。云服务器仅在第三段"正式规模训练"落地时、且用户批复规格与预算后才允许开（见 `docs/rules/SERVER_OPS.md` 铁律 10）；询价/probe/试开实例同属需审批范围。

| 段 | 目标 | 具体动作 | 状态 |
|---|---|---|---|
| **1. 阶段门 60 集** | 补齐第 3 窗，使判据①可判 | 从 40 集末权重续跑至 60 集（ep41–60）；**reward 分量落盘通道已补**（`train_reward_terms_{tag}.csv`，逐集 9 项 + 步数，供判据③；主配置 `reward_term_log: true`） | ⛔ 被 ADR-066 阶段 1（20 集）取代 |
| **2. 若不过 → 只做诊断** | 定位峰值成因，不盲调权重 | 逐窗拆解：峰位断面、ED/AB 交接、缓解相位、EBD 密度；判定奖励里**是否存在真正驱动降峰的梯度**；配合少量本地短程验证 | ⛔ 已并入阶段 1 三项诊断 |
| **3. 规模训练** | ~~1400 集（≈14 天）本地不可行~~ **档位待 ADR-064 pilot 定（1400 已废止）** | 云侧「开机即跑、跑完即关」包**已备好未开通**：预检 8 项（`preflight_payload.sh`）+ 实例 bootstrap/watchdog + 本地回传校验/停机复核/释放（`pull_artifacts.sh` + `run_lifecycle.ps1`），详见 `SERVER_OPS.md` §17。~~本次方案 = 只补 20 集（ep41–60，`c9i.2xlarge` ≈5.1 h ≈8 元）~~ **未批复不建实例、不询价** | ⛔ 集数口径已废止 |

**判据不变**：① 末窗 ≤ 暖机窗 −10% 且无连续 3 窗单调上升；② 降峰但 `ovs_rate` 升 ≥50% 的窗标红不算改善；③ `coupler_peak` 占比降而 `rel_anchor`/`gap_eff` 不塌陷；④ 峰值与 `violations` 必须同向。全文见 `DECISIONS.md` ADR-059 补充块。

### 4.3.6 ADR-064 训练预算诊断与 pilot 待办（2026-11-11 晚追加）

> 背景：用户质疑「1400 集在全剖面口径下是否合理」→ 22 篇文献检索（ADR-064）→ 发现口径错配；随后实测确认「近期确定性峰值从未 <1000 kN」（1163–1333 区间），且规则层 GA 极限 = 1163.69 kN（超线 16%）。

**A. 诊断（进行中，0 元本地）—— 判定"RL 在伤害还是在改善但不够"**

| 行 | 命令要点 | 用途 |
|---|---|---|
| M0 纯规则 | `--mode decompose_m0` | 规则层下限（RL 调制恒 0） |
| M1 全通道 | `--mode decompose_m1 --checkpoint v10seed0_ep13` | 当前架构确定性峰值（21:22 启动） |
| M1-mask-ab | `--mode decompose_m1 --mask_lever ab` | 仅 ED 杠杆 |
| M1-mask-ed | `--mode decompose_m1 --mask_lever ed` | 仅 AB 杠杆 |

判定树：**M1 ≥ M0 ⇒ RL 当前负贡献，应改架构/收权限（加奖励加集数无效）；M1 < M0 但 >1000 ⇒ 权限不足，需扩大动作空间（如 RL 参与缓解时机）；M1 <1000 ⇒ 门槛已过，直接进 H1/H2**。执行器 `tmp_eval_compare.sh`（排队等 ep13 评估结束）。

**B. pilot 待做（已中止，勿忘）**

- **内容**：`decision_interval=100`（10 s）+ 每集 700 s（`curriculum "7000:0"`）+ `γ=0.990/λ=0.899`（视界 90.9 s）+ 60 集，两组（rand 起点 4300–6300 / fix 4300）。配置文件 **已就绪**：`configs/experiments/_pilot_di100_700s_{rand,fix}.yaml`。
- **状态**：**中止待做**（2026-11-11 21:25）。云端 c9i.2xlarge 跑 rand 组 4 集后主动止损（实例 StopCharging 复核 + 释放，约 6 元）；本地排队 watcher 亦已停。
- **为何中止**：① 主 claim（ADR-042）是编队指标而非峰值，pilot 的低优先级下降；② 峰值下限疑由**规则层锁定**（GA 极限 1163.69），若诊断显示 M1 ≥ M0，则"加更新次数/加证据"不解决问题，pilot 无意义。
- **已有资产**（勿丢）：云端 4 集产物回传于 `outputs/results/formation_10kt_1plus108/pilot_di100_cloud_20261111_211320_pulled/`。**意外观察（仅 4 集探索态，不下结论）**：短集+粗间隔的 `gap_err_mean` 32–44 m、`gap_min_m` 140–141 m（≈d_eff 138.5），**优于** v10 全长训练的 45–59 m / 116–120 m —— 若后续 H1 需要，这条线索值得复测。
- **恢复方式**：`tmp_run_pilot_adr064.sh` 已随本轮清理删除，**需按上述配置重建**（原脚本模式：排队闸门 + 两组串行 + `--resume bc_warmstart.pt --resume-weights-only`）。
- **触发条件**：仅在诊断结论为「RL 有效但权限/预算不足」时启动；若为「RL 伤害」，pilot 不启动，转架构修改。

### [P0] 阶段 1：修 S2-v2 档位保持语义 + 绝对档位第 3 轮验证 - 2026-11-12

- **状态**：🔄 进行中（ADR-066 阶段 1；主路线已冻结，不得跳步）
- **归属**：P0 · Experiments（车钩力门槛兑现）
- **动机/背景**：S2-v2（绝对档位 + 90 s 档位保持）第 1 集即崩溃 —— peak **2351 kN**、`gap_min 19.2 m`、`speed 23.1 km/h`、`route_end_hits 0`。根因：档位保持把「施加 → 缓解」也纳入约束，叠加 222 s 充风门控后退化为**单次长时间重制动**（而非循环制动）。
- **完成判据**：
  - ✅ = 确定性全剖面 `peak_coupler` **< 1280 kN**（M1 residual 基线，同口径）→ 进阶段 2
  - ⚠️ = 1280–1340（持平）→ 判"绝对档位无净收益"，回退 M1，进阶段 3
  - ❌ = > 1340 或再次崩溃 → 判"该路线终止"，回退 M1，进阶段 3
  - **训练窗 peak 不作判据**（探索态，见 DIAGNOSTICS 2026-11-11 条）
- **方法/关键命令**：
  ```
  python run_training.py --experiment configs/experiments/_probe_loco_notch_v2_20ep.yaml \
    --seed 0 --episodes 61 --resume <s2_notch ep41> --resume-weights-only \
    --checkpoint_dir outputs/checkpoints/formation_10kt_1plus108/<RUN_ID>/seed0 \
    --results_dir   outputs/results/formation_10kt_1plus108/<RUN_ID>/seed0 \
    --override dirs.figures_dir=outputs/figures/formation_10kt_1plus108/<RUN_ID>/seed0
  ```
  验证命令：`python src/evaluation/evaluate_decompose.py --experiment <同上 yaml> --checkpoint <ep_last> --mode decompose_m1 --grade shuozhou_ningwuxi_beidaniu_49km --max_steps 31500 --n_seed 1`
- **配置**：`decision_interval=10`（1 s）、`entropy_coef=0.05`、`log_std_min=-2.3`、`ed_zero_point=0.77`、`ab_notch_hold_s=90`、`decompose=loco_notch`
- **唯一代码改动**：`multi_loco_controller.get_action_notch` 的保持条件加 `ab < 0 and self._ab_notch_state[k] < 0`（只约束施加态改档）
- **结果（完成后补）**：待补
- **产出文件**：
  - 结果/日志：`outputs/results/formation_10kt_1plus108/<RUN_ID>/`、`outputs/logs/formation_10kt_1plus108/<RUN_ID>_seed0.log`
  - 数据记录：`docs/logs/diagnostics/DIAGNOSTICS_2026-11.md`「阶段 1 判定」条目
- **不许做**：本阶段内不得改奖励结构、不得改 obs、不得新建控制器/env（属阶段 3 及以后）

### [P1] 阈值口径可辩护与双口径对标（2026-11-12 立案，用户批准）

- **状态**：🔄 进行中（S1/S2/S3 ✅；**S4 待补**；S5 已判读为降级；S6 挂起）
- **归属**：P0 · Docs + Evaluation（不改变 ADR-066 阶段序，不抢占阶段 1 的算力）
- **动机**：用户要求「确认我们的写法是照前人走的，不是标新立异」。2026-11-12 15 条在线检索后确认三件事：① 1000/1500 是**铁科院建议值**，无国标无部标（2250 才有 TB/T 1335-1996 依据）；② 分档报「达成值」在领域内是常规（郭刚2026 自报最大拉钩 1933.4/2106.9 kN **超 1500** 并给补救路径）；③ 但**三档的具体分界（1000/1200）文献无逐字对应**，属本项目表述。
- **目标**：
  - G1 口径可辩护：每个数值都能指出「建议值 / 国标 / 本项目推断」三者之一，且分级显式。
  - G2 指标可比：补齐「逐循环峰值均值 / 超 1000 占比 / 循环制动次数」三个量，杜绝 1280（maximum）与 806（mean of maxima）混比。
  - G3 方向有依据：阶段 3 的每个动作都有文献支撑，没有的标 I 级或不做。
- **步骤**：

| 步 | 内容 | 产出 | 状态 |
|---|---|---|---|
| **S1** | 登记本轮检索（`REFERENCE_INDEX` §阈值组 + `LITERATURE_FINDINGS` 新增 §八、§一 增 **W 级**） | 两个文档条目 | ✅ 2026-11-12 17:55 |
| **S2** | 诊断脚本补三个量（循环次数 / 逐循环峰值均值 / 超 1000 占比），用已有 smoke2 时程先跑通口径 | `tmp_stage1_diag.py` 新增 `D4_cycle_metrics` | ✅ 2026-11-12 18:05（离线验证通过） |
| **S3** | 训练收尾 → 评估 31500 步 → 三项诊断（已排队，PID 1276） | `RESULT` 行 + `telemetry.npz` | ✅ 2026-11-12 20:55（训练 exit 0 / 评估 exit 0 / 诊断 exit 0，peak **1271.1 kN**） |
| **S4** | 双口径对标判读：主指标 maximum 对现场峰值 1100–1300；补充栏对朔黄 806/10.7%；分行分列 | `DIAGNOSTICS_2026-11.md` 新条目 | ✅ 2026-11-12 21:40（`DIAGNOSTICS_2026-11.md`「诊断-2026-11-12-S4」）：栏 A maximum **1271.1** 落 1100–1300；栏 B 合并均值 **1007.8**（+25.0% vs 806）、超 1000 占比 **62.5%**（+51.8 pp vs 10.7%）；逐列 train0 739.5/0% 已达标，差距全在 train1/train2 |
| **S5** | 规则层门限扫描（4 组 `cyclic_brake_trigger_kmh` × `cyclic_release_kmh`），验证次数↓→峰值↓ 能否迁移 | 扫描结果表 | ✅ **已判读 = 降级**：S3 实测 `D1.apply_count` = **8 次/列** ≤ 13 ⇒「减少循环次数」无空间，**不扫门限**（原定 1.5–2 h 机时省下）。依据 `papers/verification/50_编队协同.md` V14 |
| **S6** | 阶段 3 修订提案（按 ADR-066 决策二三门槛，需用户确认） | 提案文本 | ⬜ 挂 §〇 0.3 |

- **资源**：S1/S2/S4/S6 零算力；S5 本地单核 1.5–2 h；**全程 0 元、不开云实例**。
- **时间**：S1 17:50–18:40 / S2 18:40–19:10 / S3 自动 ≈20:25 起 / S4 当晚 / S5 明日（硬上限 2 h）/ S6 明日晚。
- **风险与处置**：
  | 风险 | 处置 |
  |---|---|
  | 文献场景不可迁移（4 万吨 / 大秦 13‰ vs 本项目 1 万吨三列 / 35 km 合成剖面） | S5 先本地零成本验证；不成立即放弃该杠杆，不写进论文 |
  | 1280（峰值）与 806（均值）混比 | S2/S4 强制双口径同行同列输出 |
  | 缓解速度方向文献矛盾（He2025 提高至 40 km/h 改善 vs 重理工2017「随缓解速度增加而变差」） | 不采信单一数值，只写「存在区间依赖」，列待验证 |
  | 次数↓ 会加大单次制动力、可能破坏速度带 | S5 同步记录速度带内占比，不达标即否决 |
  | 距 12-25 仅 43 天 | S5 硬上限 2 h，超时降级为「只引郭刚2026，不本地验证」 |
  | 三档再次被后人当成「文献通行」 | §〇 0.5 与本条均显式标 I 级 + 禁令 |
- **不许做**：不改主配置 yaml 主值；不为凑指标换口径（ADR-066 决策三②）；不动阶段 1 正在跑的进程；S5 必须串行排队，不得与训练/评估并发。
