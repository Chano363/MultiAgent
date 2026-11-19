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
### [P0] HANDOFF-2026-11-18 接手收口（2026-11-18 深夜）

- **检查单复核（原 HANDOFF §六）**：实例 i-f8zcp6vvis4rnztw0p9y = `Stopped + StopCharging` ✅（不烧钱）；本地 schtasks 发现 w4v21 时代**过期残留 closer 任务 2 个**（`w4v21_closer`/`w4v21_full_closer`，一次性触发器 11-17 已过期、目标 tmp 脚本已删），已 `schtasks /delete`，之后无任何 closer 残留 ✅；OOS 云端硬顶 `exec-ce9089bc4f674c789ee4` = **Waiting**（deadline 2026-11-19T04:00:00Z = 北京 12:00；到点对已停机实例执行 StopInstance，无费用影响，保留至自然到期；提前取消用 `oos_hard_deadline.py --disarm`）✅。
- **工具修复（顺手）**：`scripts/cloud/oos_hard_deadline.py --list` 在 ListExecutions 返回 dict 型 `Parameters` 时崩溃（对 dict 切片 KeyError），改 `str(...)[:120]` 后 --list 复现通过。
- **HANDOFF 迁移**：§二 预算口径 → §0.7 资源总盘子已覆盖；§三 训练硬事实 → §0.1/§0.5/§0.8 已覆盖；§四 停费机制 → §0.1 三层闭环 + SERVER_CLOSER_SETUP 已覆盖；§五 日期锚点 → §0.7 已有。**新增落盘**：§0.3「W4 续投方向 A/B/C」行（owner 拍板点 + 继续投的红线 1/G1/closer 前置）、§0.1 任务行「后续」改口径、§0.4 ADR-073 行状态更正为已收口、根 AGENTS.md「产出纪律」条。迁移完成后 HANDOFF_2026-11-18.md 删除（存档 commit 288c583）。
- **遗留上报（本次未动）**：`MPC_HANDOFF_2026-11-14.md` 连同 4 个 MPC 文件的**未提交工作树改动**（params/tube_mpc/evaluate_mpc_tube/tests，**+210/−39**，另含该交接件 §0 段 +21/−6）= MPC 基线线在途工作，归其 owner 收口；仓内因此仍有 1 份 HANDOFF（≤ 上限，合规）。**〔后注 2026-11-19 凌晨：该交接件已代为收口删除，见下一节；4 个 MPC 代码文件仍未 commit。〕**项目根另有 5 个未跟踪 `tmp_*` 残留（vbs/cmd/pt），待清理。
- **检查单发现的操作障碍已当场修复（红线 4 精神）**：双活 closer 的 JSON 配置原落 `outputs/configs/`——**未登记的一级目录**，`check_outputs_layout.py` 判错，且该目录不在 gitignore 内（closer 配置含实例 ID 与公网 IP，有进 git 的风险）。已改 `register_closer_pair.ps1` 落 `outputs/logs/cloud/`（注册一级目录 + gitignored），并把写盘改为**无 BOM UTF-8**（PowerShell 读取不变，python `json.load` 亦可直接吃）；存量唯一文件 `closer_verify_dual_20261118.json` 已迁移、空目录已删；落盘口径已写入 `SERVER_CLOSER_SETUP.md`。三守卫复跑全绿：`check_outputs_layout` exit 0、`check_agents_links` exit 0、`check_claim_ledger` ERROR 0（WARN 23 为存量）。


### [P1] MPC_HANDOFF_2026-11-14 收口删除（2026-11-19 凌晨）

- **规则澄清（owner 追问触发）**：根 `AGENTS.md`「HANDOFF 生命周期」写的是 **仓内最多同时存在一份**——这是上限，不是「必须留一份」。上一轮我删掉自己的 `HANDOFF_2026-11-18.md`（存档 commit `288c583`）后，`MPC_HANDOFF_2026-11-14.md` 恰好成为仓内唯一一份、且带**未提交**的 §0 复核段，按当时口径属合规遗留，故未删。本轮按 owner 意图代为收口：**迁移 → 删除 → 复跑守卫**，现仓内 HANDOFF = **0 份**。
- **迁移去向（全量，不留档不追加）**：实现现状 / 代码地图 / 正式对照行 / 作废产物 / 场景参数卡 / 对照纪律 → `docs/knowledge/MPC_BASELINE_KNOWLEDGE_BASE.md` **§10**（180 → 291 行）；owner 2026-11-14 17:37 拍板（MPC 主对比改 **MT-2 被控对象**、零阻抗判死、「物理关闭车钩力」→「**控制器侧关闭车钩模型**」）→ `docs/logs/decisions/DECISIONS.md` **ADR-042 附段**；现状行与 MPC 行状态 → `PROJECT_PIPELINE.md` §0.1 / §0.5 / L1 横幅；口径更正 → `DIAGNOSTICS_2026-11.md` 口径补记。
- **顺带更正的文档缺陷（一手核实后修）**：① `PROJECT_PIPELINE.md` L38「穿透 **576**」是**误标**——nincr ep10 的 576 是车钩**超限**步（`viol`），其 `rear_end_steps = 0` 即**零穿透**；`cover_quick_eval.py` 读的硬安全门确实是 `rear_end_steps`，**护栏判定本身无误、不是实现 bug**。② MPC KB 顶栏仍写「尚未实现」且 §7 指向已不存在的 `test_nmpc_controller.py`、正文出现两个同名 §6 ⇒ 已改「已实现，现状看 §10」、断链改 `tests/test_tube_mpc_baseline.py`、设计稿编号改 **§6B**。③ 车钩口径旧表述在 5 处文档同步改述（`RESEARCH_POSITIONING.md` L333/L379、`REPRODUCIBILITY.md` L238、`docs/杂项/项目介绍和问题简述.md` 4 处、根 `AGENTS.md` 领域地图）。④ 53.5 / 51.8 km 一律加「非主仓场景里程」限定（= 原文坡段表全长 / 其覆盖里程；主仓 49.6 km 指**评估里程** `route_end_m=49600`）。⑤ 根 `AGENTS.md` L15/L16 缺空行补齐。
- **一手复验**：`tests/test_tube_mpc_baseline.py` **12 项全过**（原交接件 §2 的「11/11」是过期说法）；`tube_v3_mt2_20261114_r2/result.json` 逐字段核对（peak 1384.587 / band 0.96311 / `rear_end_steps` 789 / `min_gap_m` −309.158 / SLSQP 成功率 1.0 / `atp_interventions=null` / `git_commit=b08d2e4`）。
- **可追溯性**：该件只有一次提交 `65db1bf`，基线版原文 `git show 65db1bf:traffic_rl_project/MPC_HANDOFF_2026-11-14.md`；其工作树 §0 复核段（+21/−6）**从未提交**，实质内容已全量落入 MPC KB §10.2–§10.5，故不再另存该段原文（已在 §10 与本文件显式说明，避免后人按 `HEAD` 追溯落空）。
- **未做**：未 commit（MPC 线 4 个代码文件仍有未提交工作树改动 **+210/−39**，归其 owner 收口）；未训练、未开机、未改物理。三守卫复跑结果见当轮回复。

---
### [P1] 投前预设复算：奖励面 + AB 通道（2026-11-19，零训练零机时）

- **产出**：① `PROJECT_PIPELINE.md` L38 归因更正 + §0.3 新增「投前必报判据」行；② `DECISIONS.md` **ADR-074 附段三**（撤回我的错误结论 + 三项待拍板 P1/P2/P3）；③ `DIAGNOSTICS_2026-11.md` **诊断-2026-11-19-rewardface**（两投分项面复算表 + 探针全表）；④ 探针归档 `outputs/results/diagnostics/nincr_abgate_probe_20261119/`（含 `_margin20` 变体）+ 脚本 `tmp_nincr_abgate_probe.py`（带 metadata / git_commit / physics_version，红线 5 口径；root `tmp_*.py` 被 `.gitignore` 忽略，仅存工作树）；整程对照版 `tmp_nincr_abfull_diag.py` 已就位。
- **我撤回的结论（重要）**：「主线奖励面里 `coupler_peak_term` 结构恒 0 ⇒ `COUPLER_PEAK_W` 是从没拉过的死杠杆」。**错**：主线占面 **17.5%**（−2.096/步），恒 0 只属于 w4v21 投 YAML `coupler_peak_w: 0.0`（ADR-072 决策 3′ 主动消融）；现行 fleet 奖励也无 `n_fp`/`force_mask` 门控。自反证 = v20 把 W 乘 2 就塌缩。⇒ **「首投先救活失声项」动机作废**。
- **一手新事实（零训练探针，4,000 决策步，同 ckpt 同配置）**：AB 派生请求率 **0.90–0.98** vs 实际施加率 **0.040–0.128**；`refill_veto` 3,413–3,594 次/4,000 步、`hold_veto` **0**、每次释放恰锁 **222.0 s**（=2,220 步）⇒ **编队约 90% 时间只有 ED 单源**；策略主动施加 AB 累计约 35 步（3.5 s），探针内唯一一次 `ab=−0.40` 是超速兜底 SERVICE 而非交接动作 ⇒ **「贴顶不惰行」是结构必然读数，不是策略偏好**。
- **瓶颈变量定位实验（两个变体，同 ckpt）**：滞回 0.05→0.20 ⇒ AB 可用率仅 0.075→0.100（无效）；0.05→**0.50**（释放阈值归 0，只有真惰行才释放）⇒ AB 可用率 **0.357/0.444/0.410**、`refill_veto` 3,4xx→1,2xx–2,0xx ⇒ **绑定约束是"释放条件"**（起点 t=3.8 s 一次 n 下探 1.0→0.390 就锁掉其后整段 222 s）。**同一实验的色警示**：该变体窗口 peak 1002→**1199.4 kN**、超限步 `[5,18,963]`（尾列暴增，与 C4 旧故障链同型）⇒ **强行打开 AB ≠ 降峰**，须覆盖主峰的定向复现才判得了（红线 3）。C3 `gap_aware_refill`（ADR-053）历史全程 peak **0% 变化**、`relax_max_s=30` 在净空 946.9 m 下只缩短 5.51 s ⇒ 已排除。
- **P1 文献核查已完成（零成本）**：找到实车规程锚 = 赵紫宁2022「**尽量在缓坡段缓解；缓解时逐渐增大电制力并保持 ≥50 s；缓解后再缓慢调整**」+「缓解点前后各约 600 m 电制力不变」（`Zhao2022…_fulltext.txt:2829-2839/2851-2856`）、Ma2025 约束 (14)(17)(18)-(19)、张二田2021「减少缓解次数」（`:507-508`）。⇒ **一手结论**：派生化把"缓解 AB"与"电制力下探"焊成同一次动作，**与实车规程方向相反** ⇒ 修复应落在**坡度门控释放**，⚠️ 不得用 `ab_min_hold_s`（2026-10-01 负结果仍成立，只把它的**适用边界**在 `docs/papers/LITERATURE_FINDINGS.md` 索引行收窄为"仅否证该秒数参数"）。
- **顺带更正两处口径混写**：`ab_derive_notch_idx=2` = `AB_NOTCH_LEVELS=(0.0,−0.05,−0.20,−0.40)` 的 **−0.20（比例）**，YAML「MIN（70 kPa）」把比例与 kPa 混写；`notch_incr_rate_notches=3.0` 的限幅**每次调用（0.1 s）生效**（单次 |Δn|≤0.1499，一个决策步内可达 1.0）⇒ ADR-074「单决策步 3/20」在 fleet 调用节律下不成立。
- **另一条更该先修的风险（P3）**：`gap_eff` 达成率仅 **3.4%**（+0.207/步 vs 满分 6.0；评估 `gap_err` 457 m > 衰减尺度 150 m ⇒ 接近零分区）⇒ **主表 H1 列距主张可能没有训练梯度**，此风险高于「peak 距 1180 差 37 kN」。
- **未做 / 边界**：未 commit、未训练、未开机、未改物理、未改代码；探针窗口 400 s / 4.3→12.0 km **未触及已知主峰** ⇒ 「AB 不可用是否就是峰 1217 的成因」仍属推断，需覆盖主峰窗口的定向复现才能定案。P1/P2/P3 待 owner 拍板后才落 ADR-075。

### [P1] 主表现状对照 + 跨入口口径分家（2026-11-19 上午，零成本只读归档）

- **主表四行现状（同 `evaluate_decompose` 口径的整程确定性评估，一手归档）**：规则基线 M0（`w3_untuned`）**peak 1294.2 / band 100.0% / gap_err 24.5 m**；Tube MPC r2 **1384.6 / 96.31% / gap_err 140.1 m**（参照不同源，见下）；历史最好 RL 行（w4v4）**1331.9 / 99.8% / 50.3 m**；**nincr 首投 ep10 1217.3 / 85.0% / 457.1 m**。⇒ **RL 在"列距保持"上从未赢过规则基线**（50.3 vs 24.5，首投更差 18 倍）⇒ H1「优于两基线」目前是**反向证据**，不是"还没测到"。
- **两处跨入口口径分家（已落正本，避免主表踩雷）**：① **计数单位 10× 陷阱**——RL 入口每步 = 0.1 s 原始步、MPC 入口每步 = 1.0 s 控制步 ⇒ `viol`/`rear_end_steps`/`ab_steps` 绝对数不可直接比（MPC 789 穿透 = 789 s；nincr 576 超限 = 57.6 s），比值型指标不受影响；② **列距参照不同源**——MPC `gap_err = gap_head − 固定 D_DES(1424.7)`（`:295`）vs RL/规则 `gap − 1.1·d_safe`（动态，`train_fleet_env.py:1509`）⇒ 70 km/h 附近重合、偏离即分叉 ⇒ **不得直接并排 140.1 / 24.5 / 457.1**。更正落点：MPC KB §10.4 三条 ⚠️；PIPELINE §0.5 判据③ + L38；DIAGNOSTICS 口径补记 ⑤。
- **整程 AB 对照（进行中，零费用、不开机、不训练）**：`tmp_nincr_abfull_diag.py` 由 schtasks 任务 `NINCR_ABFULL` 独立进程树启动（红线 2），两变体 = 原滞回 `0.05` 对照 + `0.50`（释放阈值归 0），整程 31,500 迭代、逐拍记 peak/viol/rear_end/band/AB 可用率/**列距 gap 与 d_safe 双参照**；产物 `outputs/results/diagnostics/nincr_abfull_20261119_m{05,50}/{result.json,trajectory.npz,intervals.json,metadata.json}`，**缺 `result.json` 即判中断不得引用**；判活用 `pgrep -f tmp_nincr_abfull_diag`。目的 = 判"打开 AB 到底降不降峰"，并顺带用同一份轨迹给出**两种参照系下的列距**（H1 口径统一的零成本解法）。
- **冒烟副产品**：滞回 0.50 在起步段已示 peak 1199.4 kN、超限 `[0,1,896]`、meanED 0.118 而 AB 施加率 0.99 ⇒ **该变体实为"AB 锁死不释放"**（与实车规程"缓坡段才缓解"相反）⇒ 整程结果出来后大概率判死"只调阈值"这条 P2′。
- **仍未做**：未 commit（12 个文档改动待你一句话）；未改 `src/` 任何代码；未开机；MPC 线 4 个在途文件未碰。脚本已按仓库惯例归位 root `tmp_*.py`（被 `.gitignore:25` 忽略 ⇒ 只存工作树，文档引用处已注明）。

---
