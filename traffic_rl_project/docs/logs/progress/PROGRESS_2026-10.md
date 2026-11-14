***

title: 阶段二执行流水 2026-10
date: 2026-10-12
status: active
owner: Owner + Agent
supersedes: 无（本文件 = docs/PROJECT_PIPELINE.md 执行流水的原样迁出，内容零丢失）

> **角色**：阶段二**执行流水**（append-only：历史 ✅/❌ 条目一律保留，新条目按月追加到文件末尾）。
> 项目**总览 / 计划 / 下一步**见 `docs/PROJECT_PIPELINE.md`；诊断数据见 `docs/logs/diagnostics/`。
> **来源**：2026-10-12 自 `docs/PROJECT_PIPELINE.md` 按时间物理拆出，正文一字未改。

***

## 阶段二执行流水（2026-10，截至 10-07）

### [P3]「MARL 破线」根因归因 + 改造方向定级 - 2026-10-01

- **状态**：🟡 归因 ✅ 完成 / 改造 ⏳ 待裁决（**不涉重训**）
- **归属**：P3（免重辨识主线的**安全与训练稳定性**支柱）· 对应论文 Methods（奖励/安全层/信用分配）/ Limitations
- **动机/背景**：判定"当前 MARL 不行"（长剖面破 1000 kN、不敌规则层）。以**代码锚 + 既有资产**归因出断点，并**否证**"AB 用量↔峰值单调相关"。全文见 `docs/logs/diagnostics/DIAGNOSTICS_2026-10.md`「诊断-2026-10-01」+「调研-2026-10-01」；决策全文见 `docs/logs/decisions/DECISIONS.md` **ADR-021**。
- **断点（5 条，均代码锚）**：① 奖励车钩力量级 ≈3% 且无超限跳变（`train_fleet_env.py:739/766`，`:757-760` 已回滚硬惩罚）；② 奖励反向倒逼用 AB（`:822-824`）；③ AB 通路绕过安全层（`train_env.py:474-491` vs `:509/:522-524`）；④ 闸门有效域窄 + 确定性 no-op（`multi_loco_controller.py:211/213/253/280-283`；X1）；⑤ 信用分配：标量 advantage 广播（`mappo_agent.py:464-465`）+ 视界 17 s ≪ 滞后 90 s。
- **否证（诚实留痕）**：`s0_ep1623` `ab_steps=10753` → 863.5 kN / band 99.7%（安全）；`best_s1` `ab_steps=6591` → 1250.9 kN（破线）⇒ 决定破线的是**新增源时空分布**，不是用量。教训 `LEARNINGS.md` LRN-20261001-002。
- **下一步（ADR-021 定级）**：
  - **P0（零架构改动、不涉重训，先做）**：① 现行断面力口径 + 修好的 viol 计数下重算 53km 的 M0（规则）/ M1（`last`）两行；② `--mask_lever ab` 对照（判 AB 通道净正/净负）。
  - **P1**：AB 最小充风时间进动作空间（Zhang2024 做法）。**P2**：per-agent advantage（COMA / PRD-MAPPO）。**P3**：车钩力进目标 **或** 预测式 safety filter（二选一，由 P0/P1 裁决）。
- **产出文件**：
  - 记录：`DIAGNOSTICS_2026-10.md`（新，含根因 + 文献调研）；`DECISIONS.md` ADR-021；`LEARNINGS.md` LRN-20261001-002
  - 立论：`RESEARCH_POSITIONING.md` §1.6「车钩力定位」加"待修订（ADR-021）"标记 —— **已落实修订**（同日稍后改为"已修订并落地"，见下一条目 + ADR-021「执行闭环」⑦④）
  - 迁入：`VALIDATION_BASELINE.md` 附录 A（仿真设计速览）/ 附录 B（Gotchas 速查）——自根 `AGENTS.md` 下沉
  - 既有资产（不改）：`outputs/results/decompose/eval_decompose_decompose_m1_ms36000_*_53km.json`
- **遗留**：全部文档改动**尚未 git 提交**（待用户确认）。

### [P1/P2/P3] 文献四改造落地（A 充风门 / D 安全层AB权限 / C 车钩力进目标 / B per-agent advantage）- 2026-10-01

- **状态**：✅ 代码落地 + 单测全绿；✅ 机制 on/off 隔离验证（ADR-020 规程）；✅ **P0 三行基线 + AB 通道裁定**；🟡 **重训已启动**（2026-10-01，seed0 1400 ep，见「长久计划 1」）；✅ `ab_min_hold_s` 文献结案（负结果，见「检索-2026-10-01」）
- **归属**：P1（A）· P2（B）· P3（C+D）—— 对应 ADR-021 的 P1/P2/P3；规格 `.trae/specs/implement-literature-informed-fixes/`；执行闭环见 ADR-021 末节
- **动机/背景**：ADR-021 定级 + 文献调研四条方向（`docs/logs/diagnostics/DIAGNOSTICS_2026-10.md`「调研-2026-10-01」）；文献→代码映射见 `docs/REFERENCE_INDEX.md`「落地映射」
- **落地（文件 / 落点）**：
  - **A｜AB 最小充风时间**：`src/controllers/multi_loco_controller.py`（`get_action_decomposed` 内 `_ab_gate`；逐机车计时状态 + `ab_refill_veto_count` / `ab_hold_veto_count`）。**文献依据已定位到式**：Zhang2024 运行约束 (1) Air-refill time 的式 (9) `t_{b,j+1} − t_{r,j} ≥ T_a`（`docs/papers/02_rl/Zhang2024_DQN_CyclicBraking_Downhill.txt:250-255` / `:287-295`），本实现与之一致。默认 `ab_min_refill_s=222.0 s`（`T_a` 取 `VALIDATION_BASELINE.md:201` 张二田 S6 最短充风；实测范围 175~512 s 见 `:169`）；`ab_min_hold_s` **Zhang2024 全文无该类约束 ⇒ 默认 0.0**（不编造）—— **2026-10-01 扩检后结案（负结果）**：Zhang2024 全文 /《铁路机车操作规则》（TG/JW104-2012）/ 赵紫宁2022 实测表**均无"运行期最小 AB 保持时长"可用出处**，标签由 `待核实` 改为**已结案**；最近的两条规章（列检站"保压试验 3 min"、"重载列车 v<30km/h 不应缓解"）语义均不对（后者在本场景 `v_min=40km/h` 恒不触发）。见 `DIAGNOSTICS_2026-10.md`「检索-2026-10-01」+ `REFERENCE_INDEX.md` 落地映射。
  - **D｜安全层对 AB 的禁新增源权限**：`src/environments/train_env.py::_step_decomposed`（`protect()` 之后）：复用 `SafetyLayer.ab_new_source_veto`（反应式 `≥0.6·limit` / 预测式 `≥0.9·limit`）**丢弃本步新申请源**；**不撤销已建立源**（X4-b 反证）。诊断键 `info['ab_safety_vetoed']`（经 fleet 层跨列聚合）。**有效域**：本步环境收到的**全部**新申请 AB 源（含规则层，因 env 无法区分来源）——比 ADR-018 闸门更宽，属有意的兜底强化。⚠️ 首版另有"高力时新源降一档（SERVICE→MIN）"的梯度臂，经证明**恒被 0.6 硬否决抢先 ⇒ 不可达**，已连同其计数键一并删除（纯重构、零行为变化；LRN-20261001-007）。
  - **C｜车钩力受控超限项进 reward**：`src/environments/train_fleet_env.py`（`REWARD_SCHEMA='v2-bounded-overlimit-section-force'`；`COUPLER_OVER_W=6.0` / `COUPLER_OVER_CAP=2.0`）。峰值口径改**断面力**（原每车净力少报约 7.8× ⇒ reward 看不见破线）；超限项**有界**（上界 −12），刻意避开已回滚的 `-80·ov²` 量级。
  - **B｜per-agent advantage + 信用视界对齐**：`src/algorithms/mappo_agent.py`（`critic` **枚举** `centralized_scalar`（默认，零回归）/`per_agent`；`CentralizedValueNetwork(output_dim=N)`；`compute_gae` per-agent 各自标准化；`update()` 去广播；`effective_horizon_s` 打印并对照 90 s 滞后）+ `src/metadata.py`（新增 `critic` / `reward_schema`，带兜底不阻断生成）+ `src/evaluation/evaluate_decompose.py::probe_critic_mode`（评估侧按 ckpt 形状自动选价值头）
- **验收（ADR-020 第 4 条规程：on/off 隔离对照 + 确定性驱动策略 + 声明有效域）**：
  - ✅ 新增单测（`tests/test_ab_refill_and_safety_authority.py` / `test_coupler_reward_overlimit.py` / `test_per_agent_critic.py`）
  - ✅ 全量回归 `python -m pytest tests/ -q` ⇒ **222 passed / exit 0**（1039.55 s；`pytest.ini` 的 `-qq` 会抑制末行，记录时用 `-o addopts=` 覆盖取汇总行）
  - ✅ **per_agent 路径端到端冒烟**（`run_training.py` 短训 3ep）：日志 `有效视界 91.0s → 覆盖`；
    checkpoint 内嵌 metadata 实测 `critic=per_agent` / `reward_schema=v2-bounded-overlimit-section-force`
  - ✅ **A on/off**（12000 步）：AB 步 4447→2565（**−42.3%**）、峰值 926.95→914.37 kN、band 不变、**0 破线**、`ab_refill_veto` 6657 次
    - **A 的完整有效域（全剖面对照，修正表述）**：`_ab_gate` 在控制器里、对"新增 AB 源"**不分来源**。**纯规则轨迹**（M0）改动前/后**逐位相同**（规则层排程本就满足 222 s 充风窗）；**RL 从 ED 通道扰动轨迹后**（仅 ED 配置）A 即连带拦到规则层排程（AB 步 1441→1105，−23.3%）⇒ **A 的有效域 = "在 222 s 充风窗内请求新增 AB 源"这一动作，与来源无关**
    - ⚠️ **A 在全剖面上是"混合"效应，不是纯改善**（三配置一致：A 总是压低 AB 用量，但在 RL 参与时**峰值升高、band 变差**）：M1 全通道 AB 16270→7656（−52.9%）、破线 905→77（−91.5%），**但**峰值 **1350→1643.49 kN（+21.7%）**、band **99.62%→91.58%（−8.04 pt）**；仅 ED 配置 AB 1441→1105、峰值 1023→1037.50 kN、band 97.07%→95.85% ⇒ **A 必须与 C+B 一起重训才可能兑现价值**；且 12000 步表的"峰值略降"**只在首 1200 s 成立**（全剖面符号反转，LRN-20261001-008）
  - ✅ **D on/off**（12000 步）：env 侧真丢弃 **35/12000** 步、**峰值逐位相同**（914.3721888138994 kN）⇒ **D = 安全保证（名实相符的 ≤1000 kN 兜底）而非性能杠杆**
  - ✅ **C 解析核对**：peak_norm 0.5/1.0/1.5/3.0/5.0 → 超限项 0/0/−3.0/−12.0/−12.0，与 `−6·min(pn−1,2)` 一致
  - ✅ **P0 三行（53km / 现行断面力口径）**：M0 规则 **812.87 kN / 0 破线**；M1 RL 全通道 **1643.49 kN / 77 破线步 / AB 7656 步**；M1 `--mask_lever ab` **1037.50 kN / 44 破线步 / AB 1105 步**（band 91.58%→95.85%）⇒ **AB 通道裁定（旧权重）= 净负**
- **本轮补齐的完整性缺口（自查反例，见 `LEARNINGS.md`）**：
  1. `effective_horizon_s` **漏乘 dt** 的 10× 偏差（`decision_interval` 是原始步数不是秒）→ 已修 + 测试反例
  2. `value(...).squeeze()` 在 batch=1 时压错维度 → 改显式 `view`
  3. **D 的计数在生产接口不可见**：fleet 层丢弃子环境 info → 已跨列车聚合进 `TrainFleetEnv.info`
  4. **评估链路断裂**：per_agent 权重装不进标量头 → 新增 `evaluate_decompose.probe_critic_mode()`
  5. **主 YAML 启用** `critic: per_agent` + `gamma/gae_lambda=0.999/0.99` + `ab_min_refill_s/hold_s`（⇒ 进 metadata）
  6. **"冻结副本"被 editable 安装击穿**：`git worktree` + `cd` **不等于**冻结 → 需 `tmp_p0_freeze_boot.py`
     显式插入副本根到 `sys.path` 并断言；首轮 P0 三行因此**实为改动后**（标签已更正）（LRN-20261001-006）
  7. **D 的梯度投影臂不可达**（嵌套阈值）→ 已删除该臂 + 计数键 + 误导性单测，加源码级断言防回流（LRN-20261001-007）
  8. **主 YAML 与 ADR-017 硬要求不一致**（2026-10-01 补齐）：`episodes: 120`（不足达标量）、缺 `n_env` / `warm_start` / `long_eval_*`、且注释仍含已 SUPERSEDED 的"53km 全程由多段 1200 步拼接覆盖" ⇒ 已按 ADR-017 对齐（`episodes: 1400` / `n_env: 4` / `parallel_traj_len: 0` / `warm_start: true` / `bc_episodes: 3` / `bc_epochs: 30` / `long_eval_interval: 50` / `long_eval_steps: 36000`），`max_steps` 注释改为"env 截断上限 / 评估口径（训练时域由 curriculum 决定）"（ADR-017 §1/§2/§4）
  - ✅ **对齐验证（`--episodes 2` 覆盖短训，exit 0，280.7s）**：日志 `curriculum 边界: [(0, 500), (10, 1000), (20, 1200)]` + `[信用视界] … 有效视界 91.0s | 对照物理滞后≈90s → 覆盖` + `Fleet BC warm start: 采集 27000 条 … 预训练 30 epochs`（BC 分支被触发）；`metadata.json` 实测 `episodes=2`（CLI 覆盖生效 ⇒ YAML 1400 可被正确解析）/ `n_env=4` / `parallel_traj_len=0` / `warm_start=true` / `bc_epochs=30` / `long_eval_interval=50` / `critic=per_agent` / `reward_schema=v2-bounded-overlimit-section-force` / `ab_min_refill_s=222.0`；两集 `viol 0` / pkCpl 561→568 kN。
  - ⚠️ **验证纪律教训**：该短训**未覆盖 `dirs.figures_dir`**，导致 `outputs/checkpoints/formation/seed0/figures/fig_learning_curve_dec_ad2_cp_seed0.png`（09-25 历史 100-ep 曲线）被 2-ep 版覆盖 —— 已用原始 CSV（未受影响）经同一 `save_training_artifacts` 绘图路径重建。**此后任何短训验证必须同时覆盖 `checkpoint_dir` / `results_dir` / `dirs.figures_dir` 三者**（LRN-20261001-009）。
  9. **`_long_eval` 违规计数 O(n²) 放大**（2026-10-01 为长跑前置审计时发现）：`viol += int(info['coupler_limit_violations'])` 把 episode 级**单调累计**计数器逐步相加 ⇒ 36000 步可达 1e8。同一 bug 在 `evaluate_decompose.py` 已于 09-25 修过、`_long_eval` 漏改。**危害 = 日志误导 + 脆弱性**（`ok` 判据在零违规语义下侥幸等价，落盘元数据未被污染）。已修为每步增量累加 + 新增 `tests/test_metric_accounting.py` + **端到端预检**（真 env、每集触发、exit 0）：`viol 0 / peak 540kN / 达标=True`、best 与 `long_eval_best.json` 正常落盘 ⇒ 1400 ep 长跑不会在 ep50 静默失选优。**同源残留 3 个 live 脚本**（已废止 hierarchical 方案、全仓零引用）刻意未改，避免动历史复现资产；若旧表格引用其 `viol` 须按膨胀处理（LRN-20261001-010）。
  10. **`--mode all` 静默只出 2 行（缺 MPC）**（2026-10-01）：`--enable_mpc` 默认 False 把 MPC 行挡在门外，与 `REPRODUCIBILITY.md` §十「主对比三行」不符，且三行 Δ 摘要（`len(results)>=3`）同步静默跳过 ⇒ 已改为解析后即归一 `all/mpc ⇒ enable_mpc=True`（且在 `build_metadata` 之前，避免 metadata 与实际行为矛盾）。见 LRN-20261001-011。
  11. **MPC 控制器逐回合状态未清零**（2026-10-01）：`_mpc_controller` 只在挂载时 reset 一次，而 `eval_method` 复用同一条 env 跑 `n_seed` 回合 ⇒ `--n_seed 3`（文档口径）的第 2/3 回合继承上一回合的 `_gap0_init`/`_gap_ref`，**回合不独立**。已改为 `rollout()` 内逐回合 reset（`n_seed=1` 等价 ⇒ 旧单 seed MPC 数值不变）。见 LRN-20261001-012。
  12. **fair MPC 行从未跑通：`solve_statuses` 缺失 ⇒ 收尾 AttributeError**（2026-10-01，修 ⑩ 后第一次实跑即暴露）：`rollout` 只 `hasattr` 守卫了 `solve_times` 却直接下标取 `_mpc.solve_statuses`，而 `FairMPCController` 从不记录状态 ⇒ **崩在收尾组装、结果 JSON 尚未落盘 ⇒ M0/M1 两行（各 36000 步）也一起白跑**，且 `| tail`/后台会吞掉 exit code（极易误判为成功）。已补 `FairMPCController.solve_statuses`（口径与 NMPC 对齐：取求解器自身收敛标志 `res.success`）+ 评估侧 `getattr` 降级保护。见 LRN-20261001-013。**该缺陷同时说明"被 CLI 默认值静默挡住的代码路径"从不被执行、也无测试覆盖。**
  13. **`--decision_interval` 默认 1 与训练的 10 静默失配**（2026-10-01，第三轮审计）：`REPRODUCIBILITY.md` §十 的主对比命令**未传**该参数 ⇒ 照文档跑 D-RL 行会以"每原始步重新决策"执行，而策略是在 10 步动作保持（semi-MDP）下训练的 ⇒ **训练/评估失配**；真正跑过的主结果都显式带了 `10`，故藏了一整轮。与缺口⑩（`--mode all` 静默缺 MPC 行）**同一病根 = CLI 默认值静默决定语义**。已改为**自 ckpt 内嵌 metadata 自动读取**（读不到退回训练标准值 10 并打印），解析置于 `build_metadata` 之前；显式传参行为不变。单测 +5（该文件 14 passed）、真 ckpt 实跑三处一致。见 `DIAGNOSTICS_2026-10.md`「修复-2026-10-01c」/ LRN-20261001-015。
- **长久计划（本规格明确不做，另排算力）**：
  1. **重训里程碑**：`critic: per_agent` + γ/λ 对齐（1/(1−γλ) ≥ 90 s）+ 新 reward schema，`1400ep × 5 seed`，完整 53km 剖面评估（ADR-017 铁律）
     - **🟡 seed0 已启动（2026-10-01）**：启动器 `scripts/launchers/launch_retrain_adr021_seed0.sh` ⇒ 全新输出目录 `outputs/checkpoints/formation/adr021_1400ep_seed0/{,results,figures}`（**不覆盖任何历史产物**），日志 `outputs/logs/diagnostics/log_retrain_adr021_seed0_20261001.txt`。判活实证：`pgrep` 到 PID、`ps` 89% CPU、输出目录已建；启动日志已打出 `episodes=1400 / simcase=official / [信用视界] 91.0s → 覆盖`。**机时实测更正 ≈11.7 天/seed**（先前登记"≈3.4 天"**低估 3.4×**，勿再引用）：实测 500 步课时 **271/276/274/278 s/集**（`n_env=4`）+ BC ≈11 min；按 curriculum 折算 1400 集 ≈10.6 天，叠加 28 次 `long_eval` ≈1.1 天。⇒ **`1400 ep × 5 seed` 单机串行 ≈58 天**，**须先定：减课时/减集数，还是并行多机**（详见 `REPRODUCIBILITY.md` §十 推导与 tqdm ETA 低估警示）。恢复命令（ADR-019 `--resume latest`）与"两种调用场合"说明同见 §十。
     - **🔁 已按 ADR-023 重启（2026-10-02）**：ED 调制带宽 `ed_mod_coef` 0.5 → **1.0**（全幅，动作空间语义变更）⇒ 上面那次 run 停于 **ep55/1400（5h22m，viol 0）**，并按新口径重启：启动器 `scripts/launchers/launch_retrain_adr023_seed0.sh`、输出 `outputs/checkpoints/formation/adr023_1400ep_seed0/{,results,figures}`、日志 `outputs/logs/diagnostics/log_retrain_adr023_seed0_20261002.txt`。旧目录 `adr021_1400ep_seed0`（55 集）**原样保留、标注"旧带宽口径、不得引用"**。机时预期不变（≈11.7 天/seed）。见 `DECISIONS.md` ADR-023 + `REPRODUCIBILITY.md` §十。
     - ⚠️ **持久化边界**：本轮经 IDE 的 Shell 工具以 `run_in_background` 承载 ⇒ 进程**随 IDE 会话存活**；若要数天级无人值守，须改用用户自己的 WSL 终端重跑启动器（命令见 `REPRODUCIBILITY.md` §十，教训 `LEARNINGS.md` LRN-20261001-014）。
     - ⚠️ **待裁决（主表口径）**：D-RL 行取 `last_ep1400`（端态、无条件可复现）还是 `best`（long_eval 评估选优）？审计发现 **`best.pt` 不保证存在**（`long_eval` 全不达标则根本不写；`long_eval>0` 时 `_maybe_save_best` 被跳过 ⇒ 唯一来源是达标判据），而 `last_ep{N}`（含 `N=1400`）**保证存在**。既有口径"主结果用完整训练后的 `last`"与 ADR-017 §2 的"long_eval 选优"在 `best` 改由评估指标选出后**不再互斥** ⇒ 须明确。详见 `DIAGNOSTICS_2026-10.md`「审计-2026-10-01-主表 checkpoint 选取」+ `REPRODUCIBILITY.md` §十 存在性对照表。**裁决前不要只跑一行就下结论。**
     - 余下 seed1~4 待排算力（单机 ≈58 天 ⇒ 先定减量或并行）。
  2. **跨线泛化**：53km 训 → 20/35km 域外剖面零微调（Regime A，ADR-016）
  2b. ✅ **MPC 行"动作桥接量纲错配"已裁决并修复**（2026-10-01，甲方=反解加性关系，用户裁定）：`get_action_accel` 产绝对 ED 深度 ∈[0,1] 却被当加性 `ed_mod`（×0.5）消费 ⇒ 指令不兑现（0.75→实际打满 1.0）+ 结构性不能减闸/牵引。**改为**：桥接先复算规则基线（`_rule_baseline_edab`，保存/还原闩锁不污染 env 状态）再反解 `ed_mod = clip((desired_ed − baseline_ed)/0.5, ±1)`，并按 MPC 意图给 `ab_mod`（想停/加速→抑制 +0.4；需求顶满自有权限 `desired_ed ≥ 0.7` →预触发 −0.4）⇒ **MPC 与 D-RL 动作权限完全一致**（同样 ±0.5 ED 调制 / 同样 AB 抑制与预触发阈值 / 同样无牵引通道），唯一差异回到"决策来源"（ADR-016 不失公允）。**同时**：M3 `inner_rule_cyclic` 由硬编码改为显式 `--mpc_inner_rule_cyclic`（默认 False = like-for-like，True 仅复现历史 `mpc_rule`）；M4 `--mpc_type` **默认值与选项随后由 ADR-022 处置**（先"不改默认"，同日改为**单值枚举 `nmpc`**——见下方 2b 的 ✅ 行）。⚠️ **MPC 行历史数值全部作废，须重跑**。见 `DIAGNOSTICS_2026-10.md`「修复-2026-10-01d」。
     - **验证（实跑）**：全量回归 **241 passed / exit 0**；定向 **26 passed**；`check_agents_links.py` `[OK]`。真 env（修复期 fair 口径）`--mode mpc --max_steps 300 --n_seed 1` ⇒ `meanED **0.744**`（修复前 = 1.000，**退出饱和**）、`viol 0`、`band 100%`、`桥接越权请求 0`。结果 JSON 已记录 `metadata.eval_args.mpc_inner_rule_cyclic=false` 与新键 `mpc_bridge_ed_saturated`。
     - ⚠️ **由实测引出的新待裁决项**：MPC 的 `meanED 0.744` ≈ **其自身权限上限 0.75**（`accel_lo=-0.75`，Fair/NMPC 默认同值），而规则/RL 的 ED 可达 **1.0** ⇒ 这是**控制器自身动作边界**造成的制动权限差（**非桥接造成**，桥接已忠实交付）。裁决选项：① 放宽 `accel_lo` 到 −1.0 使权限对齐；② 保持并在论文中明确声明差异来源。
       > 【**已裁决（2026-10-02，ADR-023）：选 ②** —— `accel_lo=-0.75` 保持不改，登记为"已声明差异"（0.75 m/s² 电制动已大于最陡 −10‰ 的重力分量 ≈0.098 m/s²，物理上非瓶颈）；带宽（另一重上限）则按用户裁定全局放宽为 1.0。】
     - **验证（实跑，ADR-022 删除后）**：`pytest tests/ -q` ⇒ **exit 0 全绿**（后台日志 4 行进度点 72+72+72+27 = **243 tests**，无 F/E；末行汇总计数未落盘，不引具体 passed 数）；定向 4 文件 **46 passed**；`check_agents_links.py` ⇒ `[OK] … 23 个已有 ADR`（ADR-022 已登记）。真 env `--mode mpc --mpc_type nmpc --max_steps 300 --n_seed 1` ⇒ `reward +2221 / peak 318kN / viol 0 / ATP 288 / AB步 0 / meanED 0.512 / band 100.00% / 末速 73.3km/h / 求解 74ms 均值·1693ms 峰值 / fail 0`；**NMPC 求解比已删 fair/SLSQP 快 ≈9×**（74 vs 651 ms）⇒ 53km MPC 行 ≈**0.74 h/seed**（原记 651 ms ⇒ 6.5 h/seed 已更正）。
     - ⚠️ **实测新发现（与 `accel_lo` 同族，并入下方待裁决项）**：该行 `桥接越权请求 **455 步·机车**`（300 步 × 3 列 × 2 机车 = 1800 个"机车-步"机会，约占 25%）⇒ **±0.5 的 ED 调制权限带对 NMPC 偏窄**。但该带宽由 `ed_mod ∈ [−1,+1] × ED_MOD_COEF(0.5)` 决定、**D-RL 完全同款** ⇒ 不是"MPC 被单独削弱"，而是"**动作权限带本身够不够**"；它与 `accel_lo=−0.75 ⇒ 期望 ED 上限 0.75 < 规则/RL 可达 1.0`（此项才是 NMPC 独有）共同构成**两重上限**。**放宽任一项须同步评估 D-RL 的同一限制，勿造新不对称。**
       > 【**已裁决（2026-10-02，ADR-023，用户裁定"放宽 ①"）**：带宽**全局**放宽为 `ed_mod_coef = 1.0`（全幅；`ed_mod ∈ [−1,1]` 恰好覆盖可达差 |Δ| ≤ 1.0）⇒ 同窗口 `桥接越权请求 **455 → 0**`（`reward +2221 / peak 318kN / viol 0 / band 100% / meanED 0.500 / 求解 69ms / fail 0`），其余指标几乎不变 ⇒ 印证 455 次是权限带宽所致。`accel_lo=-0.75` **保持不改**并登记为"已声明差异"（0.75 m/s² 电制动 > 最陡 −10‰ 的重力分量 ≈0.098 m/s²）。`evaluate_decompose.ED_MOD_COEF` 改为从控制器默认值**派生**；`metadata` 新增 `ed_mod_coef` 键。**动作空间语义变更 ⇒ 旧带宽 ckpt/评估数值失效**（seed0 已按新口径重启）。见 `DIAGNOSTICS_2026-10.md`「放宽-2026-10-02」+ `DECISIONS.md` ADR-023。】
     - ✅ **基线唯一化（2026-10-01，ADR-022，用户裁定"只留 nmpc，其他的都删除"）**：`FairMPCController` / 简化 `MPCController` / `evaluate_m1_m3_long.py` / `make_m1m3_figures.py` / `make_5train_fig.py` / `eval_phys2_*` / `eval_dqn_multitrain.py` **全部删除**；`evaluate_decompose --mpc_type` 收敛为单值 `nmpc`（移除 `--mpc_simple` 与失效的 `--mpc_enforce_coupler`）。术语统一：`nmpc_controller.py` 的"多体"= **集中质量(lumped)多体**。SSOT `RESEARCH_POSITIONING.md` §1.6 的 `fair_mpc_controller` 指名按 ADR-022 覆盖修订；`AGENTS.md`/`docs/README.md`/`EXECUTION_RULES.md` 同步。**历史 MPC 数值全部作废**，主表须按 Regime A 重跑（显式 `--mpc_type nmpc`）。
  2c. ⏸️ **冻结区（闭包内）遗留缺陷，待停训期清理**：① `multi_loco_controller.get_action_accel` 牵引分支"算了 `throttle` 却未返回"（死赋值，`M2`）——**新桥接已不消费该分支，故不影响主表 MPC 行**，但仍是死代码；② `get_action_cyclic_braking` docstring"中段维持"易被误读为"带内给牵引"，实际是**保持两态闩锁**（`R1`，措辞问题非功能缺陷）。两者均需改 `src/controllers/multi_loco_controller.py` ⇒ **须先停 seed0 长训**。（2026-10-02 的停训窗口**只**用于 ADR-023 的带宽改动 —— 为压小重启风险，M2/R1 仍按本项继续挂起，不夹带在同一窗口。）
  2d. ✅ **规则层"负 ed 牵引通道是死代码"→ 推翻**（2026-10-01 审计）：`coordination_adj` 返回的 `coordination_traction` **确实被消费** —— 在 `train_fleet_env.py:680-683` 于 `get_action_decomposed` **返回之后**直接写入 `final_edab[k,0] = −traction`，绕开该方法内的 `clip(…,0,1)` ⇒ 牵引可达，且该注入纯规则驱动、**对 RL 与 MPC 一视同仁**（不构成权限不对称）。
  3. **完整 predictive safety filter**（Wabersich & Zeilinger 2021 的 MPC 形式）作 D 的升级备选（须连同 `coupler_veto_ratio` 阈值一起重定，才能表达**梯度** AB 权限 + 来源感知 + filter/策略一致性）
  4. **重训后复核 AB 通道去留**：重跑同一 `--mask_lever ab` 对照再裁定（本规格的"净负"只在旧权重上成立，**不据此砍动作维度**）
  5. ~~**改动前全剖面对照**（冻结副本 `d6ba3540` 的 `_pre_*` 三行）~~ **✅ 已完成**（53km 全剖面版 `_pre_*` 三行已产出，见 `DIAGNOSTICS_2026-10.md`「诊断-2026-10-01-P0…」§四；12000 步版为更早的一轮，非本条所指）
- **产出文件**：
  - 代码：上列 6 文件 + 3 个测试文件 + `configs/experiments/formation_ed_ab_3train_1plus1.yaml`（ADR-017 对齐）
  - 规格：`.trae/specs/implement-literature-informed-fixes/{spec,tasks,checklist}.md`
  - 记录：`DIAGNOSTICS_2026-10.md`（「改造-2026-10-01-文献四改造落地」+「诊断-2026-10-01-P0 三行基线与 AB 通道裁定」+「验证-2026-10-01-主训练 YAML 按 ADR-017 对齐」）；`DECISIONS.md` ADR-021 末节「执行闭环」+ ADR-017「执行闭环」；`LEARNINGS.md` LRN-20261001-003~009；`REPRODUCIBILITY.md` §十（主训练口径）；`REFERENCE_INDEX.md`「落地映射」
- **遗留**：全部代码 + 文档改动**尚未 git 提交**（待用户确认）

### [P2] 新动作口径（ADR-023）下的冒烟 / 其余两行 baseline / 可跑消融 — 2026-10-02

- **状态**：✅ 完成（本口径可跑部分；RL 侧消融因 ckpt 语义失效被阻塞，已随 ADR-024 回退后重排）
- **归属**：P2 · 论文 Experiments（主表其余两行 + 消融）
- **动机/背景**：ADR-023 把 ED 调制带宽放宽为全幅（`ed_mod_coef=1.0`）⇒ **动作空间语义变更**，主表须按新口径重跑。用户指令："**先冒烟看看效果，然后把别的 baseline 也跑了，消融能跑的也跑跑**"（目标 = 直到 MARL 有好的结果；**需要启动长训时暂停**）。seed0 1400ep 长训已在跑（`adr023_1400ep_seed0`，PID 658，BC 热启动已完成）。
- **完成判据（验收）**：① 新口径评估链路冒烟通过（无越权截断 / 无 solve fail）；② **不依赖 D-RL ckpt** 的两行 baseline 在**完整 53km** 上产出可引用结果 JSON；③ 能跑的消融产出结果；④ 被阻塞的消融必须**写明阻塞原因**（不静默跳过）。
- **方法/关键命令**（均带 `--out_suffix` 防同名覆盖 → LRN-20261002-001）：
  - 冒烟：`--mode mpc --mpc_type nmpc --max_steps 300 --n_seed 1 --out_suffix _adr023_coef1_check`
  - 冒烟 + 回合独立性核查：`--mode decompose_m0 --max_steps 300 --n_seed 3 --out_suffix _adr023_det_check`
  - baseline 行：`--mode decompose_m0 --grade shuozhou_real_53km --max_steps 36000 --n_seed 1 --eval_seed 0 --out_suffix _adr023_m0_53km`
  - baseline 行：`--mode mpc --mpc_type nmpc --grade shuozhou_real_53km --max_steps 36000 --n_seed 1 --eval_seed 0 --out_suffix _adr023_mpc_53km`
  - 消融（MPC 双层护盾）：`--mode mpc --mpc_type nmpc --mpc_inner_rule_cyclic …`（待主行跑完再排，避免同控制器并发争用）
- **配置**：`--grade shuozhou_real_53km` / `--num_trains 3`（3 列×1+1 = 6 机车）/ `--eval_seed 0` / `--init_speed_kmh 80` / `--decision_interval` 自 ckpt metadata；协议 = **ADR-016 Regime A**。
- **结果（随跑补）**
  - ✅ 冒烟（MPC，300 步）：`桥接越权请求 455 → 0`，其余指标几乎不变（`reward +2221 / peak 318kN / viol 0 / band 100% / meanED 0.500 / fail 0`）。
  - ✅ **省算力发现（`--n_seed` 冗余，实测）**：确定性行（D-Rule / MPC）在 `n_seed=3` 下三个回合的指标**逐位完全相同**（`reward 2298.1141287732603`、`peak 511.7638857894402`、`mean_ed 0.849999999999996` 三段全等，证据 = `eval_decompose_decompose_m0_ms300_adr023_det_check.json` 的 `per_seed`）⇒ 主表口径的 `--n_seed 3` 对确定性行是 **3× 纯冗余成本**。本次两行 baseline 用 `n_seed=1`（数字与 3 回合相同）；建议主表口径据此改为"确定性行 `n_seed=1`，仅 `--random_init_speed` 鲁棒性行才需多回合"（**待用户确认**）。
  - ✅ **两行 baseline（53km 全剖面，`n_seed=1`，2026-10-02 完成）**：**D-Rule** `reward +92 950 / peak 1073kN / viol 68 / band 97.28% / 末速 50.6km/h`；**MPC/NMPC** `reward −813 642 / peak 848kN / viol 0 / band 61.98% / 末速 64.8km/h / 求解 95ms均值·fail 1936 / 越权 0`。
  - ✅ **M3 消融（MPC + 规则内层护盾，53km）**：`solve fail 1936→0`、ATP 事件 3.94M→622k、`band 61.98%→71.04%`，但 `末速 40.5km/h`（擦下限 v_min=40）、reward 更差 ⇒ **"NMPC 弱在缺内层护盾"成立**，但补齐后仍远弱于 D-Rule；结论与带宽无关，ADR-024 回退后仍可留用。
  - ⚠️ **A/B 诊断（本轮关键，已据此裁定 ADR-024）**：`ed_mod_coef=1.0` 对 RL **负面** —— 完整剖面 A/B 显示 ep51–55 新口径 `viol 327–694`（旧 0.5 口径全 `0`），1.0 长训 4 次长程评估仅 1 次达标（ep200 末速崩至 30.3km/h）；MPC 侧却无收益 ⇒ 详见 `DIAGNOSTICS_2026-10.md`「冒烟与基线-2026-10-02」。
- **⛔ 阻塞项（必须明写，不静默跳过）**：RL 侧消融（`--mask_lever ed|ab`）、D-RL 行本体、以及任何"需新口径 ckpt"的对照，**均须等长训产出 ckpt**（旧 ckpt 产于 0.5 带宽，语义已失效 ⇒ 不可代用）；ADR-024 回退后改为等 `adr024` ckpt。
- **产出文件**：
  - 结果 JSON / 日志：`outputs/results/decompose/eval_decompose_*_adr023_*.json`、`outputs/logs/diagnostics/log_eval_adr023_*.txt`
  - 数据记录：`docs/logs/diagnostics/DIAGNOSTICS_2026-10.md`「冒烟与基线-2026-10-02」

### [P2] ADR-024 回退 ED 调制带宽 1.0 → 0.5 并重启 seed0 长训 — 2026-10-02

- **状态**：✅ 完成（代码 / 测试 / 留痕 / 重启）
- **归属**：P2 · 论文 Experiments（动作空间口径）
- **动机/背景**：ADR-023 放宽带宽后，完整剖面 A/B 实证"**对 MPC 无收益、对 RL 有害**"（1.0 允许策略整幅撤销规则层 ED ⇒ 持续破 1000 kN）。用户裁决原文："**回退 0.5 并重启（推荐）**"。
- **完成判据（验收）**：① `ed_mod_coef` 回 0.5 且派生常量 / metadata 自动跟随（无手抄点）；② 定向 + 全量测试通过；③ ADR-024 + 诊断留痕；④ 用**新目录**重启长训并核对 metadata。
- **方法/关键命令**：停 `adr023_1400ep_seed0`（PID 658）→ `bash scripts/launchers/launch_retrain_adr024_seed0.sh`（新目录 `outputs/checkpoints/formation/adr024_1400ep_seed0`，日志 `outputs/logs/diagnostics/log_retrain_adr024_seed0_20261002.txt`）
- **配置**：同主 YAML（53km / 3 列 1+1 / 1400ep / n_env 4）；唯一变更 = `ed_mod_coef` 默认值 0.5。
- **结果（完成后补）**
  - ✅ 代码：`MultiLocoController.get_action_decomposed(ed_mod_coef=0.5)`（全仓唯一改点位）；`evaluate_decompose.ED_MOD_COEF` 与 `metadata.ed_mod_coef` 均**派生**自动跟随。
  - ✅ 测试：定向 **39 passed**；全量 `pytest tests/ -q` ⇒ **244 项全绿（exit 0）**；`check_agents_links.py` ⇒ `[OK] … **25** 个已有 ADR`。
  - ✅ 长训已按 0.5 口径重启（新目录）；`adr021_*` / `adr023_*` 产物**原样保留**（不覆盖不删除）。
- **遗留/待办**：待 `adr024` 新 ckpt 产出后重跑 D-RL 行 + 两行 baseline（0.5 口径）+ ED/AB 杠杆隔离（`--mask_lever ed|ab`）。
- **产出文件**：`scripts/launchers/launch_retrain_adr024_seed0.sh`；`docs/logs/decisions/DECISIONS.md` **ADR-024**；`DIAGNOSTICS_2026-10.md`「回退-2026-10-02」。

### [P2] 路线覆盖修复：训练起点随机化（消除固定起点 OOD）- 2026-10-07

- **状态**：🔄 进行中（L2 已验证有效；seed0 重训进行中）
- **归属**：P2 · 论文 Methods（训练分布覆盖）；**重训前置**（不修则重训白跑）
- **动机/背景**：L1 诊断发现**固定起点 + ≤1200 步短窗口**使训练完全落在 −1.5‰ 缓坡段，**从未经历 −12‰ 陡下坡（论文核心场景）**；完整剖面评估 83.9% 的步落在训练未见坡度区间 ⇒ 训练场景与研究对象错位。修复方向 = **起点随机化**（短窗口长度不变，训练分布覆盖全路）。
- **完成判据（验收）**：① L2 沙盒 A/B 证明随机化有效（long_eval 达标次数 ON ≥ OFF 且去掉长程灾难）；② 接入主配置后 **seed0 单跑完整 53 km long_eval 达标**（`viol=0 ∧ peak≤1000 kN ∧ 末速∈[40,80]`）；③ 无回归（测试绿）⇒ 再铺 5 seed。
- **方法/关键命令**：
  - L2 沙盒 A/B：`bash scripts/launchers/launch_debug_routecov_ab_parallel.sh`（OFF=固定起点 / ON=起点随机化，唯一差异 `env_cfg.start_randomization`；各 80 ep）；对照器 `python scripts/tmp_analyze_routecov_ab.py`。
  - seed0 重训：`python run_training.py --experiment configs/experiments/formation_ed_ab_3train_1plus1.yaml --seed 0 --checkpoint_dir outputs/checkpoints/formation/routecov_1400ep_seed0 --results_dir outputs/checkpoints/formation/routecov_1400ep_seed0/results --override dirs.figures_dir=outputs/checkpoints/formation/routecov_1400ep_seed0/figures`
- **配置**：主 YAML 新增 `env_cfg.start_randomization.enabled: true`（seed 缺省 = 继承本次运行 `--seed`，5 seed 各自独立随机化且可复现，见 `train_runner.py`）；其余同 ADR-017 达标配方（1400 ep / n_env 4 / BC 热启动 / long_eval 50）。
- **结果（部分，完成后补）**
  - ✅ **L2 终局**：long_eval 达标 **ON 2/2 vs OFF 0/2**；OFF ep80 长程灾难（1815 kN / viol 7788 / 末速 17.4）→ ON 同点达标（832 kN / viol 0 / 末速 51.8）。
  - ✅ **分布层**：评估 OOD 83.9% → **4.1%**（visited 口径规范化为"领航列领航机车 grade bin"，与评估采样单元一致）。
  - 🔄 seed0 重训进行中（`routecov_1400ep_seed0`）；**实测速率 ≈3.8 min/ep（22:18→01:32 跑 51 ep）⇒ 全量 ≈4–5 天**（含 long_eval 每次 ~55 min × 28 次）；`conda run` 缓冲 stdout ⇒ 中途看 `results/` CSV 与 `long_eval_best.json`。
- **遗留/待办**：seed0 long_eval 达标后铺 seed 1–4；顺手修掉 `save_training_artifacts` 与 logger 的 CSV 双写者（已修，统一框架跳过 4 列覆写）。
- **产出文件**：`docs/logs/diagnostics/DIAGNOSTICS_2026-10.md`「路线覆盖 / L1 / L1-b 更正 / L2 终局」；`configs/experiments/formation_ed_ab_3train_1plus1.yaml`；`src/trainer/train_runner.py`（seed 注入）；`outputs/checkpoints/formation/routecov_1400ep_seed0/`。

### [P2] 训练提速：n_env 进程级并行 rollout - 2026-10-07

- **状态**：✅ 代码完成、验证，**已用于生产重铺 5 seed**（显式 CLI `--override n_env_parallel=true`；YAML 默认仍关）
- **归属**：P2 · 执行效率（不改立论/物理/奖励）
- **动机/背景**：单 run 实测 ≈3.8 min/ep ⇒ 全量 1400 ep ≈4–5 天/seed，5 seed 串行 ≈3 周。诊断出根因：GPU 利用率 0%、12 核只有 1 核忙——`train_runner.py` 的 `for ei in range(n_env)` 是**串行**循环，`n_env=4` 只增样本量、不缩短墙钟（单核物理仿真 ≈47.5 ms/env-step）。
- **方法**：新增 `src/trainer/parallel_rollout.py`——把 n_env 条轨迹分发到 n_env 个常驻进程并行；每条轨迹用**确定性种子** `_traj_seed(seed, ep, ei)`；worker 用 CPU、`torch.set_num_threads(1)`；**轨迹 ei 固定绑定第 ei 个进程**（`Pool.map` 自由调度会因 env 跨回合残留状态导致不可复现，见 LRN-20261007-001）；transitions 回传父进程**按序重放** `store_transition`，父进程仍只 `update()` 一次。
- **开关**：`n_env_parallel: true`（`ExperimentConfig`，默认 `False` ⇒ 零回归）；仅 `interaction='mappo_fleet'` + `obs='env'` + `reward!='cyclic'` + 非异构时生效。
- **验证**（`--episodes 2`，重定向三目录到 `outputs/smoke/_smoke/`）：
  - ✅ **可复现**：同 seed 连跑 2 次，`train_history` CSV 逐位相同（对照：串行连跑 2 次也逐位相同）。
  - ✅ **提速**：同 horizon 冒烟，串行 ≈77 s/ep → 并行 ≈33 s/ep（含每集父进程 update）；进程启动/建 env 为一次性开销。稳态预期 ≈3–3.5×（4 条轨迹并行 + 串行 update 段）。
  - ⚠️ **数值不与串行逐位相同**（每轨迹独立 RNG 流；两者各自可复现），跨版本对比不可混用。
- **遗留/待办**：① 长程（1400 ep）实测倍率与内存占用待补；② 首个 long_eval 达标后据此更新 `REPRODUCIBILITY.md` 主训练命令（把 `--override n_env_parallel=true` 写进配方）。
- **产出文件**：`src/trainer/parallel_rollout.py`（新）；`src/trainer/train_runner.py`（接线）；`src/trainer/config_schema.py`（`n_env_parallel`）；`docs/logs/learnings/LEARNINGS.md` LRN-20261007-001。
- **2026-10-07 生产落地（B+C）**：
  - **端到端预检**（`--episodes 2 --override n_env_parallel=true --override warm_start=false --override long_eval_interval=1 --override long_eval_steps=400`，三目录重定向 `outputs/smoke/_smoke/parpre_*`）：exit 0，**108.1 s**；日志 `[并行 rollout] 进程级并行已启用：n_env=4`；ep1/ep2 long_eval 均 `达标=True`（peak 578 kN / viol 0 / 末速 40.0 km/h），`long_eval_best.json` 正常落盘 ⇒ **并行 × long_eval 集成无误**（此前冒烟只测过裸 rollout，未跑 long_eval）。预检产物已清理。
  - **生产启动**：停掉两个串行 job（`pilot_routecov_150ep_seed0` @ep25、`routecov_1400ep_seed0` @ep80），改并行重铺 —— `routecov_1400ep_seed0_par` / `routecov_1400ep_seed1_par`（seed0/seed1 两 job 并发，各 `n_env=4` worker ≈5 核，合计 ≈10/12 核）；seed2–4 待有名额再铺。
  - **必须新目录**：复用旧目录会被 `_restore_best` 读到串行 best ⇒ 污染；故并行 run 一律用 `_par` 后缀新目录。
  - **口径**：并行与串行数值不逐位相同 ⇒ 5 seed 全部走并行；串行 `routecov_1400ep_seed0`（ep80 处）作废，目录保留仅供溯源。
  - **机时更正（实测）**：串行 run 的周期性 checkpoint 墙钟间隔 ⇒ horizon 1200 稳态 **≈165–190 s/ep**、long_eval ≈33 min/次 ⇒ 串行全量 **≈3.5 天/seed**（远低于 `REPRODUCIBILITY.md` 的 11.7 天估计，已在该文档加更正）；并行预期 ≈1.5 天/seed 量级，待首段实测校准。

### [P2] 「训练效果不好」根因定案：训练地平线 120 s < AB 充风 222 s - 2026-10-07

- **状态**：🔴 根因已定（一手全量复查），**修复待实验裁决**（改地平线后对照重训）
- **归属**：P2 · 训练口径（触及 ADR-017 §1 训练时域）
- **结论（一句话）**：主 blocker = **单条训练回合物理时域 1200 步 = 120 s 短于 `ab_min_refill_s = 222 s`** ⇒ 循环制动"充风→二次制动"的车钩力峰值在单回合内不可能出现 ⇒ RL 拿不到梯度；该峰值只在全 53 km 评估暴露（1161 kN > 1000）。次病 = **探索噪声失控**（ED 通道 `log_std` 实测涨到钳位上限 2.0，σ=7.39 ≫ 动作半幅）。
- **一手证据**：ep50/ep240 训练窗 peak 864/716 kN（viol 0）vs 同 ckpt 全剖面 1155/1161 kN（viol 432/463）；5 个 ckpt `long_eval_best` 全 `-inf`（全程达标从未发生）；训练窗 `best_reward` 冻结在 ep23=10603.56；σ_ED 0.234(ep20)→7.389(ep240，=上限)。全文见 `docs/logs/diagnostics/DIAGNOSTICS_2026-10.md`「诊断-2026-10-07」。
- **附带修正**：① `evaluate_decompose` 离线 `target_speed=20.0` 与训练 16.67 失配（2026-10-07 已修并复测：FIXED 口径 ep240 peak 1149.3 kN 仍 >1000 ⇒ 结论不变。⚠️ `metadata.physics.target_speed_mps` 恒为默认 20.0，**不可**用于判口径）；② `mappo_agent.py:617` `num_updates` 用 floor 而实际迭代 ceil ⇒ 上报 entropy/loss 被放大（实测 5.78 vs CSV 8.31）。
- **口径提醒**：全剖面质量其实**在改善**（ep50 `gap_min=−386` 真追尾 → ep240 `gap_min=+33` 无追尾），**训练窗 reward 下降 ≠ 部署质量下降**。
- **跨配置确认（2026-10-07 补）**：破线峰值 ≈1149–1168 kN 在旧 `adr023`／新 `routecov`、par／serial、ep50/ep80/ep150/ep240 **六份全剖面 JSON 上恒定复现，且恒 >1000 kN**（含 FIXED 口径 ep240=1149.3）⇒ 非 routecov 回归、非轮数不够、非并行实现缺陷、非 harness 假象，属**配置无关的结构性**现象（与"时域 120 s < 222 s"论证互印证）。详见 `DIAGNOSTICS_2026-10.md` §七。
- **峰值定位 + 切片裁决（2026-10-07 补，两个一次性探针）**：① 全剖面破线从 **km25.43 持续到终点**，占 **52% 步数**，km26–49 平台 **1146.4 kN**、峰值 **1149.3 kN@km51.3** ⇒ **非偶发尖峰**；而 `slice16k`（21.06–37.02 km）**已覆盖破线区一段**却评估 <1000 ⇒ 破线不取决于单段坡度。② km25 **全新起点**跑 3000 步 = **911.8 kN / 0 超限**（同里程全程 = 1043–1146 kN）⇒ 破线**主要依赖从 km0 起沿程累积的状态**。⇒ **靠后切片不能替代全剖面**（丢致病初始条件）；且训练按 ADR-017 只跑短窗、**不跑满 53 km**，**换剖面长度省不下训练时间**，省时旋钮是 `long_eval_interval` 与总 episode 数。详见 `DIAGNOSTICS_2026-10.md` §九。
- **待办**：① **先查明硬安全层 `enforce_coupler` 为何未把全剖面峰值钉在 ≤1000 kN**（RL 臂实测 1149–1168 kN，而 `use_coupler_constraint` 默认 True ⇒ 安全层名义上启用却未兜住；此点直接决定"峰值该不该由 RL 学"的定位，**推断待验证**）；② 改地平线至 **≥2500–3000 步（≥ AB 充风 222 s）**对照重训（切片不可替代）；`entropy_coef` 退火 / `log_std` 上限收窄；修 `num_updates` 计量；下游省时只动 `long_eval_interval` / 总 episode。

## 阶段二执行流水（2026-10-08 ~ 10-20，2026-11-12 自 PROJECT_PIPELINE 迁入，正文零改动）

> 接本文件前段（2026-10-01 ~ 10-07）。原为 `PROJECT_PIPELINE.md`「执行流水已按月归档」之后的正文，整块物理迁出。

### [P1] 实验计划定稿（obs12 之后）：安全层诊断 → 受控基线 → obs12 对照 → 文献候选迭代 → 终局主训练 - 2026-10-08

- **状态**：计划已定（依据 = ADR-030 三原则 + 「Pilot 裁决-2026-10-08」），**自 Step 0 起执行**
- **前置口径**：obs12（AB 充风计时进观测，`obs_dim 11→12`）**代码已落地 + 32 测试 + 冒烟通过**，未做受控对照；pilot A/B2/C 裁决与口径修正见 `docs/logs/diagnostics/DIAGNOSTICS_2026-10.md`「Pilot 裁决-2026-10-08」。
- **Step 0 安全层诊断（先行，零训练成本）**：查明 `enforce_coupler` 名义启用（`use_coupler_constraint=True`）为何兜不住全剖面峰值（恒 1112–1168 kN，pilot C 亦 1112）。两假设：**A** 钳动作钳不住已发展的车钩力（力是状态量 ⇒ 立论"硬安全层 ≤1000"叙事需重表述）；**B** decompose 路径未真启用/有 bug。裁决追加至本文档。
- **Step 1 受控基线规格（ADR-030 ②）**：冻结 commit；**3 训练 seed**；统一症状指标 = 全剖面 viol/peak/band/gap_min/追尾 + 训练侧 value_loss/KL/log_std。基线组二选一（**待拍板**）：**路线甲** = pilot C 配置为基线（250 s 窗 + `log_std_max=0` + lr 2e-5 + ValueNorm decay），变量组仅加 obs12（归因最干净）；**路线乙** = 严守 ADR-017 短窗 1200 步，变量组仅加 obs12（合 ADR-030 原文，但 120 s 窗内考不到破线，症状差异可能测不出）。
- **Step 2 跑基线组（3 seed，全 episode 预算）**：拿正常波动带宽（补 ADR-030 指出的"无可信基线"缺口）。
- **Step 3 obs12 对照（唯一变量）**：对比 Step 2 带宽，超出种子噪声才算改善；无差异则归档转下一候选。
- **Step 4 文献候选逐个迭代（ADR-030 清单，一次一个变量）**：② Hu2026 Mamba 序列模块 → ④ 课程式奖励权重 + 优先经验回放 → ③ Wang2026 分层/空间分段（改动最大，最后）。
- **Step 5 终局**：最优配置 × 5 seed × 1400 ep（主 YAML）→ 论文主表 vs NMPC（ADR-037 对比口径：同环境/同坡度数据/同档调参力度，无逐线重喂标定协议，`--mpc_type nmpc`）。MPC 线已基本就位（MPC+规则层全剖面 967 kN / viol 0，图 `nmpc_innerrule_vs_bare_53km.png`）。
- **并行零碎**：`num_updates` 计量修复（`mappo_agent.py:617` floor/ceil，纯上报口径）；MPC 公平基线程度（tasks.md #1，独立讨论）。
- **执行留痕**：各步裁决 append 至本文档；诊断细节入 `DIAGNOSTICS_2026-10.md`。
- **Step 0 裁决（2026-10-08 当日完成）**：假设 B（接线 bug）**排除**——三层防护真实生效（感知缩放 / RL 新增源预测闸门 / 充风门，断面力口径统一）。假设 A **成立（主导）**：感知式钳制看当前力，拦不住 AB 波传播 ~5s 滞后峰值，已建立源不撤销（文档已认，`multi_loco_controller.py` L312-315/L340-348/L366-370）。**伴生缝隙（新发现）**：规则基线自身 AB 兜底（`ed_avail<0.99 → -0.75 档`，L227-229）**不过预测闸门/并发限制** ⇒ ED 耗尽段规则层自己持续追加 AB 源，其滞后峰值即破线主嫌（与峰值跨配置恒定、pilot C RL 收敛后仍 1112 吻合；MPC+规则层行 967 达标反衬）。⇒ "peak 该不该由 RL 学"有了答案候选：**可能根本是规则基线结构性产物**。**新增 Step 0.5（建议先于 Step 1 规格冻结）**：单种子快验（pilot C 配置 + 预测闸门/并发限制覆盖规则基线新增源），裁决缝隙是否即峰值来源。详见 `DIAGNOSTICS_2026-10.md`「安全层诊断-2026-10-08」。
- **Step 0.5 前置证据更新（2026-10-08 傍晚）**：MPC 行轨迹分析**反驳「AB 兜底主嫌」**（AB 期间峰仅 693 kN、>800 kN 全在 AB=0；MPC 行 967 是末步边界回弹而非全程峰值）——safegate 快验照跑（裁决效力不变），预期下调；**簇间一致性差（gap_err 105 vs 29.5 m）升至 RL 症状榜首**。详见 DIAGNOSTICS「MPC vs RL 破线差异分析-2026-10-08」。另：
um_updates 计量修复已落地（真实优化器步数计数，治 KL 早停稀释，71 测试绿）；任务 2（RESEARCH_POSITIONING §1.2 限定）**阻塞**——docs/RESEARCH_POSITIONING.md 等 5 文档在工作区呈已删未提交状态，待用户裁决恢复。
- **状态修正（2026-10-08 晚）**：docs/ 5 文档删除系用户误删，**已恢复**（git checkout，diff 核实无半成品改动残留）；任务 2（RESEARCH_POSITIONING §1.2 claim 收窄段）**已完成**，ADR-030 待办销项。
- **Step 1 受控基线规格（路线甲，已拍板）**——冻结前置 = safegate 快验裁决（跑完即冻结）：
  - **代码冻结**：当前改动集（① 基线 AB 源补闸门 ② num_updates 真实步数计数）。safegate 通过 → 纳入；不通过且有害 → revert ①再冻结（基线代码不得含未验证改动）。
  - **受控档位（3×30 ep，小时级）**：基线组 B = pilot C 配置（--override curriculum=2500:0 --override algo_params.log_std_max=0 + --episodes 30），变量组 V = B + --override env_cfg.use_obs12=true（**以代码实参名为准，启动前核对**）。3 训练 seed {0,1,2}。产物 outputs/checkpoints/formation/ctrl_base_seed{n} / ctrl_obs12_seed{n}；各跑全剖面评估 --n_seed 3。
  - **裁决规则**：V 相对 B 的改善须超出 3-seed 组间带宽（各指标 min–max 跨度）才算数；无差异 → 归档转 ADR-030 候选②（Mamba 序列模块）。
  - **扩档**：胜者配置才进 Step 5 终局（5 seed × 1400 ep）；受控档不做全量训练，控成本。
- **Step 0.5 裁决（2026-10-09）**：**通过**——peak 1112→990.3 kN（2/3 seed <1000）、viol 144→1.67、band 98.05%、gap_min 80.4 m、追尾 0。闸门补齐 + num_updates 修复**纳入基线代码**，冻结。机制修正与细节见 DIAGNOSTICS「Step 0.5 快验裁决-2026-10-09」。
- **下一步（即刻）**：Step 1 受控组启动——基线组 B（3 seed × 30 ep，pilot C 配置 + 闸门代码）与变量组 V（+obs12，键名启动前核对代码），串行 nohup 链；产物 ctrl_base_seed{n} / ctrl_obs12_seed{n}。

### 双人分工与合并方案（2026-10-12，我=单车车钩力侧 / 队友=编队侧）

> 目的：两人并行不互相踩、合并时能对得上。立论/安全分层口径见 `RESEARCH_POSITIONING.md` §1.7（**唯一出处**，本节只讲分工与合并操作）。

**一、分工边界（按模块划，不按指标划——指标是共用的，模块才有 owner）**

| 侧 | 负责模块（改动前先看对方是否在改） | 交付物 |
|---|---|---|
| **我（单车车钩力控制）** | `src/train_dynamics/{coupler,braking,train}.py`（MT-2、缓释曲线、断面力）、`src/safety_layer.py`（enforce_coupler + ATP 规则顺序）、`src/multi_loco_controller.py`（AB 预测闸门/并发限制/充风门）、reward 车钩项（`coupler_over_term`） | 车钩力≤1000kN 落地率、peak/viol 指标、安全层诊断（Step 0/0.5 系列） |
| **队友（编队）** | `src/environments/train_fleet_env.py` 的编队上下文（`_dynamic_gap`/gap 目标/编队 obs）、formation vs No-C 消融、跨线零微调实验、列数扩展（3→5 列） | 列距/速度带指标、编队消融表、跨线主表行 |

**共享冲突热点（必须先约定单点 owner，避免两边同时改）**：`src/environments/train_env.py`（EBI 落地 + `safety_events` 计数）、`src/evaluation/evaluate_decompose.py`（主表出口）、`configs/experiments/*.yaml`、reward 组合处。**默认 owner = 改动发起方，改前在本文档加一行登记**（谁、哪个文件、动什么）。

**二、配合方式（4 条硬规矩）**

1. **物理同源铁律**：训练 / 评估 / 对比基线必须共用同一物理模型。**谁改物理，谁跑全量 `pytest tests/ -q` + 冒烟**（`--episodes 2` 且三输出目录全重定向），改动前后各留一份 `metadata.json`。
2. **接口先冻结再动手**：`obs_dim`、action 结构、**主表指标 JSON 键**（`reward / peak_coupler_kN / viol / safety_events / band_rate / ab_steps / mean_ed / gap_err_* / gap_min_m / mpc_*`）——键名要改，双方先同意 + Grep 全仓改齐，禁止单方改名。
3. **决策各自留痕、互不覆盖**：各自裁决 append 到本文档（加日期小节）；立论变更走 ADR；诊断细节入 `DIAGNOSTICS_2026-10.md`。日志 append-only，历史结论被推翻只标 `superseded`。
4. **术语统一**：指标中文标签按 `RESEARCH_POSITIONING.md` §1.7「指标术语对齐」执行（**禁自造词**，如"追尾步数"）；合并时发现旧词按该节改。

**三、怎么合并（顺序执行）**

1. **合并点 = 主训练冻结 commit**：两侧在同一 commit 上跑 `pytest tests/ -q` 全绿 + `check_agents_links.py` + `check_outputs_layout.py`，才启动 1400 ep × 5 seed 终局训练。**分叉期间各自跑的数不进主表**。
2. **主表单一出口**：由 `evaluate_decompose.py` 一处产出（我维护），队友只供数据不另开评估入口；表列顺序/单位口径由出口统一。
3. **合并前对齐 5 项**：① 同一物理与安全层（"一边改物理、一边做对比"= 无效实验）② 断面力口径（ADR-018）+ 1000 kN + 单位（m/s vs km/h）③ 时域三维度不混（ADR-017：rollout 窗 / 评估剖面 / 总训练量）④ seed 集与随机化初态设置 ⑤ ATP 触发次数、`assert rear_end_steps == 0` 守卫两侧一致。
4. **产物不打架**：`outputs/` 按类型分组 + 运行目录 `语义前缀_时间戳`，**三输出目录必须同时重定向**（checkpoint/results/figures），否则覆写历史（LRN-20261001-009）。
5. **合并后跑一次全量回归**：pytest + 冒烟 + 出一张主表核对列名与 §1.7 一致，再进论文。

**四、注意的地方（踩过的坑）**

- **别在对方跑训练时改共享文件**（`train_env.py`/YAML）——训练读的是启动时代码，中途改会静默不一致。
- **别把对方的口径当"待定"重提**：已定的以 ADR + `RESEARCH_POSITIONING` 为准；要推翻先拿证据。
- **别各自跑评估后直接拼表**：不同 commit / 不同物理的数值不可比（本项目已有"两侧物理同源"铁律）。
- **ATP 缺口 1（前车最坏假设）+ TTC/TET 是否在主训练前切口径，待拍板**（见 §1.7）——定了以后两侧都用新口径，别一半新一半旧。
- **已处置（2026-10-12）**：`outputs/results_mpc_baseline/` 未登记一级目录（`test_outputs_layout` 既有失败）已按 `rules/EXECUTION_RULES.md` 迁至 `outputs/deprecated/results_mpc_baseline/`（该批 MPC 数值属 ADR-022 作废范围，归档保留），全仓路径同步，`test_outputs_layout` 恢复通过。


## 迁入：底层控制器实验交接档案与 2026-10-18~10-20 流水（原 docs/README.md 尾部，2026-11-12 迁出）

> 原为 `docs/README.md` 尾部「底层控制器实验交接档案」整节。**条目中「PROJECT_PIPELINE.md 同日条目」现指本文件**。
> README 只保留导航指针，不再承载带日期的执行记录。

### 底层控制器实验交接档案（2026-10-14）

- [归档说明与重画命令](../outputs/sim_validation/phys_validation/controller_repair_20261014/README.md)：37个完成运行、原始轨迹/结果元数据/源码快照、冻结候选和原报告；非正式已验收控制器。
- [文件清单与SHA256](../outputs/sim_validation/phys_validation/controller_repair_20261014/publication_manifest.json)；图片位于 ../outputs/sim_validation/figures/controller_repair_20261014/。历史D盘路径保留出处，读取时使用仓库相对路径。

- **当前双人职责与接口核对（2026-10-14）**：见 [本文件该条](#p0-当前双人职责接口与联合验收核对---2026-10-14)。历史两层RL/NMPC/53km任务不作为现行安排；共享owner与编组版本同步尚未完成。

- 2026-10-18 缓解幅值与保持退出诊断（未达标）：[D盘完整报告](reports/controller_takeover_20261017/万吨108节缓解幅值与保持退出复核_20261018.md)；状态与后续见 PROJECT_PIPELINE.md 同日条目。

- 2026-10-18 再制动准入与压力建立诊断（未达标）：[D盘完整报告](reports/controller_takeover_20261017/万吨108节再制动准入与压力建立复核_20261018.md)；状态与后续见 PROJECT_PIPELINE.md 同日条目。

- 2026-10-18 阶段ED延长与充风速度余量（整体未达标）：[D盘报告](reports/controller_takeover_20261017/万吨108节阶段ED与充风速度余量复核_20261018.md)、[TraeWork MIS定向检索指令](reports/controller_takeover_20261017/TraeWork_MIS再制动专项检索指令_20261018.md)。

- 2026-10-18 新增全文与缓解可行性：[D盘核对报告](reports/controller_takeover_20261017/新增全文复核与缓解可行性修复依据_20261018.md)，含林轩/黄宇澄关键公式、董文编组判据及旧汇总解释更正。
- 2026-10-18 原生缓解预测（下一周期候选受限，未验收）：[D盘复核报告](reports/controller_takeover_20261017/万吨108节原生缓解预测与可行性瓶颈复核_20261018.md)、[TraeWork定向检索指令](reports/controller_takeover_20261017/TraeWork_缓解预测与数值收敛定向检索_20261018.md)。52项回归通过；完整实跑中止，12段完成预测单独留存，不作全线证据。

- 2026-10-19 缓解速度细筛与ED保持对照：[D盘报告](reports/controller_takeover_20261017/缓解细化与空电保持时间对照_20261019.md)、[最新MIS原文核对指令](reports/controller_takeover_20261017/TraeWork_108节缓解恒持力与充风可行域_20261019.md)。两候选1050秒通过及局部重复/相邻时机检查；延长至车头18.36km速度下界失败，42个连续原生决策点未通过，无全线三列验收。

- 2026-10-19 恒力目标与数值收敛瓶颈（当前）：[D盘最终报告](reports/controller_takeover_20261017/新增文献与50秒恒力目标修复_20261019.md)、[数值积分定向检索指令](reports/controller_takeover_20261017/TraeWork_非线性积分收敛专项检索_20261019.md)。局部改善未转化为全线通过；关键窗口1475/1599步未满足迭代准则，细步力峰仍未收敛，先核查数值可靠性。62项回归通过；未训练、未晋升默认。

2026-10-19后续：已读新增相关原文并做联合容差/步长诊断，1e-9容差最细两级片段峰633.055883/633.040330kN，迭代均达准则；包络逐时差仍15.79kN，非完整闭环或全线验收。65项回归通过，生产物理未改，未训练/未推送。报告：[D盘详细复核](reports/controller_takeover_20261017/新增论文与联合容差收敛复核_20261019.md)。下一步验证失败步回退/力残差与完整闭环，禁止把633kN当整线效果。

2026-10-19最新平衡迭代候选：独立加速度Picard同时检查局部位移与末状态力平衡，β/γ及物理力律未改；气动子步事务回滚与解析解等71项回归通过。固定输入细化峰633.065/633.043kN，全断面时程最大差15.823kN，仍非严密误差界。同765.5秒完整原生状态，248.5秒零RL局部气动机械反馈窗口通过：内部峰572.462kN、最高70.248/最低均速40.288km/h，397600接受细步，力残差均≤10N。原求解235.5秒峰1004.883kN失败，旧2355×6记录精确复现；新方案前20秒与独立短试验精确一致。该窗口继承旧积分历史，预测跳过递归guard但保留原准入与ATP，未作全线/冷起点/三列验收，生产默认未改，未训练，新增工作未推送。数据single108_balanced_{mechanics,tight_mechanics,coupled,coupled_fullwindow}_20261019_round14；D盘报告：reports/controller_takeover_20261017/平衡迭代与气动闭环候选复核_20261019.md。下一步冷起点及气动/机械联合细化验证，不能将572kN标为全线规则修复效果。

- 2026-10-19最新冷起点：745.2秒、车头12.725km、内部峰719.817kN、单车47.411—76.139km/h，完整状态已存，尚非49.6km全线通过。74项相关回归通过；力时程精度/效率仍需核查。[D盘详细报告](reports/controller_takeover_20261017/冷起点验证与力时程收敛瓶颈_20261019.md)、[TraeWork MIS检索指令](reports/controller_takeover_20261017/TraeWork_MIS力时程精度与计算效率专项_20261019.md)。

- 2026-10-19本轮发布资料：[中文循环制动图](../outputs/sim_validation/figures/cyclic_braking_108_20261019/cyclic_cold745_zh.png)、[D盘49份工作文档及配套资料ZIP](../outputs/sim_validation/phys_validation/controller_reports_publication_20261019_round16/controller_reports_publication_20261019_round16.zip)。ZIP含逐文件SHA256。图仅覆盖745.2秒冷起点前缀，不是全线验收；可用src/evaluation/plot_cyclic_archive.py复画，无需重跑仿真。

### 2026-10-20 单列控制修复与局部验证归档

- 单列1机车+108货车（10988吨）、49.6公里固定起点：第33轮完整状态连续运行至尾车通过终点；最高车辆速度78.51493 km/h，最低全列平均速度43.05631 km/h，含前1000秒起步阶段的内部车钩峰值约719.82284 kN。零RL、实验数值求解；生产默认未晋升，不代表三列或随机起点验收。
- 第36轮2180—2580秒局部候选：深制动请求0次，最低车辆42.62470 km/h，内部车钩峰674.21224 kN。第37轮细化缓解重试后最低车辆44.13940 km/h、内部峰651.09197 kN，但深制动请求恢复为1次，未达到全部接续条件，未启动第38轮剩余路段验证。保留第33轮为已通过单列基线。
- 原始数据、完整重启状态、冻结源码与哈希位于 `outputs/sim_validation/phys_validation/single108_*`；不要将轨迹数组视为可恢复全部气动和控制器历史的检查点。
- [工作报告仓库副本](reports/controller_takeover_20261017/)；[归档总索引](../publication_archive/20261101/INDEX.md)（95 份报告 + 11 个数据目录 + `paper/` 原文，覆盖第 24 轮起至 20261101）；[中文循环制动图及配套资料](../outputs/sim_validation/figures/controller_repair_20261020/)。保留历史报告，各轮结论以对应result.json和local_comparison.json为准。
- 后续流程：问题前完整状态→同工况局部对比→有明确改善后再线路验收；阶段验收出图，样式调整复用原数据。

<!-- 该文档整理/压缩于 2026-10-12 -->

### [P0] xmc 底层控制器平稳性诊断与修复 - 2026-10-12

- **状态**：进行中；用户授权 xmc 负责底层控制器，队友负责车钩物理模型。
- **范围/owner**：xmc 修改 `src/controllers/multi_loco_controller.py`，增加控制器专项测试与独立诊断入口；物理模型、奖励、观测/动作结构、主表 JSON 键保持冻结。共享环境/安全层若需修改，先补登记。
- **完成判据**：相同真实仿真工况下比较速度、加速度变化、AB 档位切换与断面力；保持 ATP 优先、充风门和新增 AB 闸门；改善平稳性不得以提高超速或断面力风险换取。1000 kN 为整体闭环目标，本任务不宣称确定性底层单独保证全工况达标。
- **基线**：`4ba79e2`；先采集主训练 decompose 链路的零 RL 调制单列/多列曲线，再逐项修复。
- **诊断入口**：`python src/evaluation/diagnose_low_level_control.py --output <D盘新目录> --steps 900`。这是控制器诊断，不另设论文主表出口；报告/原始轨迹按用户要求保存 D 盘。
- **结果**：完成后追加，记录环境差异及适用范围。

#### 本轮交付 - 2026-10-12

- 已完成主训练 `TrainFleetEnv → MultiLocoController → TrainFormationEnv → SafetyLayer → TrainDynamics` 链路诊断；修复 AB 连续缩放跨档、ED 重复投影、回合 AB 状态残留，并增加 ED 单向恢复限速（工程调参，可设 0 禁用；安全减弱即时、速度上限旁路）。
- 物理、奖励、动作/观测形状、主表出口未修改；新增专项回归与保存/复用真实轨迹的诊断入口。已完成相关回归和实际更新的短训练集成验证。
- 结果权威入口：`external_archive/controller_fix_20261012/底层控制器修复报告.md`；数值来源为同目录的各工况 `result.json` / `trajectory.npz`，并保留原始失败诊断与中间方案，不覆盖。
- **边界**：恒坡单列/三列测试有改善，不作为完整线路或训练后策略的最终安全证明；车钩力裕量仍小。当前为本地修改，后续需在双方统一冻结版本上完成长程评估，分叉数据不进主表。

#### 整线复核补充 - 2026-10-13

- **状态：未验收**。三列零 RL 调制完整剖面对照显示，恢复速率 1/s 候选的 jerk RMS 下降约 41%，但超速列车步 2549→3329、断面力超限计数 5505→6930；恒坡结论仅限原工况，不能外推整线达标。
- 禁用新增 ED 恢复限速、保留其余修复的坡度变化窗口已完成：超限计数 131→31，jerk 峰值 1.02008→0.79838 m/s³，超速列车步均为 159；完整剖面对照仍在运行，暂不更改默认恢复参数。
- 复核报告与新对照轨迹：`external_archive/controller_extended_20261013/底层控制器整线复核.md`。旧整线原始数据保留，元数据更正另存 `result_metadata_corrected.json`；复用归档保留原控制器运行参数并拒绝变更恢复速率。专项控制器 5 项和归档契约 1 项通过。

#### 默认参数回退与复核 - 2026-10-13

- 已根据完整剖面安全回退证据将 `ed_recovery_rate_per_s` 默认设为 0；正值仅作为显式实验选项。保留此前三项控制器修复。整线禁用恢复限速对照使用启动时源码和显式 0 参数，运行途中未替换其控制器。
- 最终相关回归 101 项通过；两回合 60 步短训练正常产生学习更新，峰值约 862/858 kN、超限计数 0/0；仅作为短程集成验证。源码快照、差异与参数追溯保存在 D 盘复核目录。
- 确认 `_get_obs_decomposed()` 会调用有状态的规则控制接口，从而在只读取观测时改变制动状态；已用真实环境复现，但尚未证明这是整线震荡根因，本轮暂未改共享环境。
- 已补读本地 Zhang2024 Q-learning 原文 §2.2 与 He2025 循环制动优化原文 §6；不得将忽略车钩力的模型当作车钩安全证明，也不直接移植两万吨工况的优化数值。继续以同物理、同初态的完整剖面对照决定验收。
- 补查旧整线原始轨迹发现最小列距：旧版 -7.52 m、恢复速率 1/s 候选 -63.75 m，负列距步数 198/1437；该候选亦未满足安全列距判据。诊断摘要补充 `min_gap_m` 与 `negative_gap_steps`（仅独立诊断出口，未修改主表键）。禁用恢复限速整线结果尚未生成，不提前宣称风险消除。

#### 电制动基线保护单因素排查与回退 - 2026-10-13

- 禁用恢复限速的完整剖面已完成：jerk RMS 0.073923（较原版下降约 19%）、超速列车步 2134（下降约 16%）、最小列距 70.705 m、负列距步数 0；但断面力峰值 1360.324 kN、超限计数 8865（原版 5505），仍未验收。
- 相同初态前 360 s 单因素对照：原版超限计数 170、单次 ED 投影候选 1008、恢复原 ED 基线保护后 170；恢复后前 360 s 的速度、断面力和超限统计逐行等于原版。不能仅凭代码出现两次保护就判定重复缩放是 bug。
- **当前默认**：`ed_baseline_projection=legacy`、`ed_recovery_rate_per_s=0`。此前将单次投影作为默认修复的方案 **superseded**；单次投影与正恢复速率仅保留为显式实验选项。离散 AB 与回合状态重置仍保留。物理、共享环境、安全层、奖励及接口形状未修改。
- 当前默认相关回归 102 项通过；恢复原保护的新整线对照运行于 `external_archive/controller_extended_20261013/legacy_projection_full53`，未宣称达标。详情和源码追溯见 D 盘同目录复核报告。
- 当前默认两回合 60 步短训练正常完成实际梯度更新，峰值约 819/796 kN、超限计数 0/0；产物保存在 D 盘 `smoke_legacy`，仅作为集成验证。

#### 线路限速与整列超速判断修复 - 2026-10-13

- xmc 在既有控制器 owner 范围内修复：协调偏置不得抬高绝对线路制动上限；任一车辆超速均触发制动，并约束 AB 抑制与可选 ED 恢复限速旁路。原 ED 基线保护、充风门、ATP 与物理模型保持不变，未修改共享环境。
- 对归档旧源码和当前源码进行同初态、同物理的 23500 m/65 km/h/三列/180 s 对照：jerk RMS 0.103113→0.099235；断面力峰值 1153.516→1090.563 kN；超限计数 126→52；超速列车步 159→134；最小列距 141.871→136.977 m，均无负列距，但仍有超限、超速。
- 起步 360 s 对照：超速列车步 61→57，但超限计数 170→174、jerk RMS 略增；必须保留这一回退，不用有利窗口替代完整剖面验收。
- 当前相关回归 106 项通过，两回合 60 步短训练正常产生更新、峰值约 819/796 kN、超限 0/0。新增归档源码回放契约验证，未修改主表出口。
- **未验收**：旧速度判断版本的 `legacy_projection_full53` 与修复版的 `vehicle_speed_guard_full53` 独立进行整线对照，源代码在进程中按启动版本冻结；原始数据和复核报告统一保存 D 盘。单列车钩阈值仍为整体闭环目标，本轮不宣称底层单独保证全工况达标。

#### 整线回退定位与切换阈值修复 - 2026-10-13

- 两版整线已结束，尚未验收：jerk RMS 0.093077→0.095358，超限计数 7643→9348，超速列车步 3576→3670；最大车辆速度 83.384→82.202 km/h、最小列距 7.781→18.025 m。不能把降低速度峰值误当成降低超速累计暴露或完整平稳性改善。
- xmc 在控制器范围内修复重合的制动/缓解阈值及车尾近上限时提前缓解。采用既有 0.5 m/s 控制裕量保留间隔，不添加空气制动保持时长，不修改物理、共享环境或主配置。
- 相关回归 75 项通过。普通 40 km/65 km/h/180 s 初态的成对窗口完全一致，不能作为改善证明；正在额外列距 200 m、80 km/h 的追赶初态下进行针对性成对验证。原始轨迹、参数与失败结论均按 D 盘复核报告留痕。
- **共享文件 owner 登记（改前）**：xmc 负责 `src/environments/train_fleet_env.py::_get_obs_decomposed` 的控制器状态读取副作用修复，仅保留读取前的循环制动状态；不修改编队目标、奖励、观测维度或安全层。依据是读取观测可改写 `_cyclic_braking` 的真实环境复现，且会影响本轮切换状态保持。

#### 切换状态与观测读取修复验证 - 2026-10-13

- 改前登记范围内已修复 `_get_obs_decomposed` 的循环制动状态读取副作用；实际控制步骤更新状态，观测预览恢复读取前状态。观测/动作维度、奖励、物理及安全层未修改。
- 当前相关回归 110 项通过；短训练两回合各 60 步完成实际更新，峰值约 819/796 kN，超限 0/0，仅作为集成验证。
- 40 km/80 km/h/额外列距 200 m/180 s 追赶对照：jerk RMS 0.123768→0.104157，断面力峰值 1172.453→1145.711 kN，超限计数 441→224，超速列车步 715→348，最小列距 89.154→89.707 m，均无负列距。仍有超速与超限，未验收。只读观测修复在该窗口不改变轨迹，改善由切换阈值修复产生。
- 整线当前组合复核运行于 D 盘 `controller_extended_20261013/hysteresis_readonly_full53`；所有车尾通过真实剖面终点为完成标准，未结束前不宣称整线达标。诊断归档增加共享环境源码/哈希与数值线程设置追溯，旧归档不伪造该信息。详情见 D 盘既有整线复核报告。

#### 跟随速度上限接口换算（改前登记）- 2026-10-13

- owner：xmc，限定 `src/environments/train_fleet_env.py::_step_decomposed_fleet` 中跟随速度上限到控制器偏移量的单位换算；保留既有 LEAD_TAIL_OFFSET_MPS、编队目标、奖励、安全层及物理模型。
- 真实环境契约已失败复现：前列约 40 km/h 时，传入控制器的绝对上限约 80 km/h，超过既定前列速度加 5 m/s（约 58 km/h）。原因是将绝对上限与相对偏移量直接取 min。
- 既有 hysteresis_readonly_full53 进程已经加载并冻结改前环境，本轮换算修复不替换该进程对象；新候选另行保存实际环境源码与哈希，须对照验证后判断是否采用。

#### 跟随速度上限换算复核 - 2026-10-13

- 已修正相对偏移/绝对速度混用，真实环境契约由失败转通过；控制相关回归 111 项通过，扩展归档契约 3 项通过；短训练两回合正常学习更新，峰值约 819/796 kN，超限 0/0。
- 同速追赶窗口无变化；40 km/40-65-65 km/h/60 s 针对性对照，超限计数 259→138、最小列距 219.370→271.952 m，但 jerk RMS 0.032363→0.071215，仍未验收。仅接口语义修复已验证，不能说平稳性任务完成。
- hys 只读版整线（hysteresis_readonly_full53）与当前换算版（cap_offset_full53）各自冻结进程中的源码运行，均保存 D 盘；新诊断支持真实归档适配器回放和逐列初速度，保留同物理与源码哈希。详见 D 盘既有整线复核报告。

#### ATP 电制动执行映射（改前登记）- 2026-10-13

- owner：xmc，限定 `src/environments/train_env.py::_step_decomposed` 中安全层投影到机车电制动输入的映射，不修改 SafetyLayer 优先级、ETCS 曲线、AB 物理、奖励或车钩模型。
- 真实执行轨迹显示 EBI 期间电制动会从 1/0.7 降为 0；新增真实 ETCS + 真实动力学测试在请求 ED=0 及请求牵引两种情况下均复现：空气紧急制动已发送，但机车 ED 仍为 0。现有 min 映射仅允许减权，丢失 ATP 升级。
- 修复目标：仅 ATP 实际触发的机车执行安全层最终制动深度，其他情形保留原 ED 减权；保留取消牵引和空气紧急制动优先级。完整线路旧进程已冻结改前对象，后续候选独立归档，须验证冲击和速度风险，不预判达标。

#### ETCS 电制动执行映射复核 - 2026-10-13

- 已复现并修复 ETCS 最终制动投影未升级物理 ED 的接口缺口；最终范围限定 ETCS EBI/常用介入，普通车钩保护保持减权。初始简单超速映射候选回退，原空气缓解测试初态及断言保留。
- 最终相关回归 116 项通过；独立诊断记录真实执行器输入，记录前后同工况 rows 完全一致。新增 train_env 源码哈希追溯，旧档缺失保持未知。
- 最终混合初态 60 s 对照未验收：jerk RMS 0.071215→0.076027，峰值断面力 1131.128→1338.464 kN，超限 138→886，无超速与负列距。恢复 ETCS 执行语义不是平稳性达标证明；不得通过减弱紧急制动掩盖风险。
- etcs_ed_full53 正在独立运行；旧 hys/换算版整线继续按启动对象冻结运行。2/s 恢复限速候选仅在旧执行接口短窗口改善，尚未用于当前默认；5/s 候选因超限增加不采用。
- 已核对 ERA 官方制动曲线说明；其支持监督/实际制动职责区分，不提供本项目 ED 深度常量。详情及全部中间失败数据保存在 D 盘既有复核报告，当前任务仍进行中。

#### 规则决策提前读取 ETCS 上限（改前登记）- 2026-10-13

- owner：xmc，限定 train_fleet_env.py::_step_decomposed_fleet 中将本步前车 ETCS 目标刷新提前到控制器调用前，以及 MultiLocoController 的可选 ETCS 提前上限实验；不修改 ETCS 曲线、安全层、物理模型、奖励或主配置。
- 真实环境契约失败复现：两列跟随控制器均看不到本步前列位置/速度监督目标。现有混合速度窗口第一步已 EBI，不能将紧急初态直接作为正常控速验收。
- 提前控速仅显式实验开启（默认关闭），使用既有曲线的 SBI 上限，不发明提前制动距离或时间；改善须验证同物理、同初态和原始轨迹，旧整线进程不替换源码。

- 本轮复核：6 个相关测试文件 99 项通过；40 km 起三列同速 65 km/h、额外列距 200 m、120 s 的默认/提前方案结果一致，峰值 1210.721 kN、最高车厢速度 81.334 km/h，未达到目标，提前选项继续默认关闭。原始轨迹、源码及结果位于 external_archive/controller_extended_20261013/etcs_anticipate_before_safe65 和 etcs_anticipate_after_safe65。旧整线会话已无法读取且未见结果文件，不计作已完成验证。

#### 电制动恢复突变复核（改前登记）- 2026-10-13

- owner：xmc，仅控制器诊断与其恢复限速选项；不改车钩、物理、安全层、主训练配置。实际执行轨迹显示最大速度变化率突变伴随电制动 0/满档切换；其中车钩保护后的恢复亦存在 0.25→1 的跳变。
- 在当前 ETCS 执行修复版本重测恢复率 2/s；旧版本的改善不得移植为本版结论。使用与上一轮相同 40 km、65 km/h、3 列、额外列距 200 m、120 s 初态，默认保持关闭，只有速度平稳性和安全指标共同改善才考虑采纳。

- 复核结果：同速 jerk RMS 0.068999→0.066942，但最大 jerk 0.632600→0.756669、超限 377→403、超速 706→732，拒绝默认启用。混合 40/65/65、60 s 超限 886→698、峰值 1338.464→1315.835 kN，仍超限，仅局部改善。新增实际 ED 跳变统计，22 项相关测试通过；详情追加在 D 盘底层控制器整线复核报告及 ed_recovery_current_comparison.json，不宣称整线达标。

#### 仅车钩保护恢复平滑（改前登记）- 2026-10-13

- owner：xmc，修改 MultiLocoController 恢复限速作用域及独立诊断契约；增加 coupler 作用域选项，只有车钩保护削减过电制动时启动恢复限制，正常循环新施加不限制，撤销和超速/ATP 不延迟。默认恢复率仍为 0，主配置不动。
- 同物理同初态比较同速 120 s 和混合 60 s；参数 2/s 是工程试验，不当论文车辆常数；不满足安全及平稳性综合指标不得启用默认。

- 验收：新增 coupler 恢复作用域、缓解/重置与超速响应契约；6 文件 101 项回归通过，补充超速契约后的控制器文件 22 项通过。两工况实际轨迹与 all 恢复作用域数组完全相同，未改善同速超限 403/超速 732，恢复率默认仍 0；不宣布完成。D 盘保存 ed_coupler_recovery2_safe65、ed_coupler_recovery2_mixed 原始轨迹及源码，比较文件 coupler_recovery_scope_comparison.json，图 coupler_recovery_mixed_comparison.png；下一步定位车钩保护与限速制动反复切换。

#### 线路限速投影执行复核（改前登记）- 2026-10-13

- owner：xmc，仅环境执行接口与真实执行契约。检查发现 ETCS 会执行加强制动，但规则 C 的 overspeed 仍被请求/保护深度取 min 丢弃；本轮按每辆实际 overspeed 事件索引恢复该机车安全投影，不将货车事件泛化为全列机车事件，不改安全层顺序或物理。
- 首先验证局部超速时只恢复对应机车，随后运行原有空气缓解及控制相关回归；测试冲突和物理恶化必须留痕，不能降低验收阈值掩盖问题。

- 结果：局部 overspeed 恢复对应机车 ED 投影并取消牵引，ETCS 权限不变。原 81 km/h 空气缓解测试 f_end=322.267 kN 失败，因同时请求限速电制动而非纯空气缓解场景；初速改为限速内 78 km/h，保留 v_end>20 m/s、f_end<300 kN、空气档位全部释放断言，另以真实执行契约验证超速制动。6 文件 104 项回归全部通过。
- 120 s 同速真实线路对照：jerk RMS 0.068999→0.066742，超限 377→304、超速 706→593，但车钩峰值 1210.721→1254.583 kN、最大 jerk 0.632600→0.740245，整体未达标。数据位于 external_archive/controller_extended_20261013/line_atp_local_safe65，比较图及 JSON 同目录上级，报告追加原失败与副作用；保留执行正确性修复，不宣称整线/训练完成。

#### ETCS 常用空气制动执行补齐（改前登记）- 2026-10-13

- owner：xmc，仅 train_env::_step_decomposed 与真实执行契约；4 个实际执行测试复现 SBI 介入时空气指令仍 RELEASE。峰值附近第二列已进入 EBI。修复常用介入的空气 SERVICE 执行，移除较弱动作源遮蔽单源命令的问题，保留请求/监督紧急档最高权限。不改物理、ETCS 曲线、奖励、主配置或平滑默认。
- 同速 120 s 对照 line_atp_local_safe65，混合 60 s 作为紧急压力窗口；既有安全常数不新标定，性能与正确性分别验收。

- 复核：12 种真实执行组合与 6 文件 112 项回归通过；SBI 现执行 SERVICE 空气档，弱源不遮蔽，请求 EMERGENCY 不降级。统一入口 2×60 步短训练实际学习更新正常、超限 0/0，仅证明兼容。
- 同速峰值 1254.583→1198.645 kN、jerk RMS 0.066742→0.066337，但超限 304→538、超速 593→623、EBI 388→444，整体未达标。混合峰值 1338.464→1233.107 kN、超限 886→597，但最小列距 247.095→210.828 m、EBI 230→456、最大 jerk 恶化；不宣称总体安全改善。D 盘归档 sbi_air_safe65、sbi_air_mixed、smoke_sbi_air，报告保留负面结果；后续查介入/退出切换与制动力分布。

#### 常用安全制动同步源配置执行（改前登记）- 2026-10-13

- owner：xmc，仅 decompose 的 SBI 执行接口和真实执行契约。轨迹统计表明常用介入次数有限，不能先归因于高频启停；代码检查确认已有 sync_loco_brake=True 在普通路径采用所有机车发波，而 decompose 的 SBI 未使用该配置。常用安全制动按已有同步配置生成 SERVICE 源，False 保持车头路径；ATP 介入不被普通新源闸门降级。EBI 仍保持 ADR-029 车头紧急路径，不改物理或新增延时常数。
- 先做同步开关/请求紧急优先级契约，再比较同速 120 s、混合 60 s 原始轨迹，数据存 D 盘。不以配置一致性代替性能验收。

- 同步试验拒绝：同速超限 538→476、峰值不变；混合超限 597→803（恶化约 34.5%）、峰值不变。已撤回同步源变更，train_env 源码与改前 D 盘快照逐字符一致；124 项回归通过。普通模式同步配置不能直接套用于 decompose 安全源；不将本项判为已证实的修复根因。试验原始档案 sbi_sync_safe65、sbi_sync_mixed 保留。

#### 速度带内净坡力电制动前馈（改前登记）- 2026-10-13

- owner：xmc，仅 MultiLocoController 显式试验选项及独立诊断契约。当前未进入循环制动时 ED 恒 0，先净下坡加速至上限后再强制制动。试验在速度带内利用现有真实动力学的坡力、Davis 阻力、已生效空气力与 ED 力映射，求抵消净加速的最小电制动；保留机车分配、安全投影、限速触发、低速释放和空气门控。无新车辆参数，默认关闭；数值求逆精度仅算法精度。
- 验证计算不推进或修改物理状态、可用 ED 饱和边界、低速/平坡不无故制动及归档真实性，再做同速和混合窗口。控制器模型依赖声明为自研实现，不把性能验证当论文规定。

- 首轮前馈在下限出现 0/满投入导致 jerk RMS 恶化，已用现有 0.5 m/s 控制裕量连续投入，不新增物理常数。连续版同速 120 s：峰值 921.473 kN、超限 0、线路超速 0、jerk RMS 0.057290；混合压力窗口 jerk RMS 0.108560 仍高于基线 0.066898，试验默认关闭。继续单独验证与恢复率 2/s 的组合；注册训练接口 env_cfg.ed_grade_feedforward 仅显式试验开启，主 YAML 不改。

- 最终回归 129 项通过；显式开启前馈的统一入口 2×60 步短训练正常更新，峰值 826.670/809.867 kN、超限 0/0，仅证明集成兼容。恢复 2/s 组合在同速窗口增加 SBI/EBI 介入、列距变小，混合 RMS 仍劣于基线，不默认采用。
- 第二坡段 23500 m 起同速 120 s：前馈关/开峰值 1164.773→1000.928 kN、超限 120→1、超速 698→0，但 jerk RMS 0.050639→0.059807 恶化，平均速度下降。那 1 次仍严格计作超限，不放宽阈值；未达全面验收，默认保持关闭。D 盘底层控制器整线复核报告记录全部同步/前馈失败、中间版、两坡段与压力窗口，下一步处理高频保护切换、速度参考/效率和整线稳定性。

#### 前馈保护恢复状态丢失修复（改前登记）- 2026-10-13

- owner：xmc，仅 MultiLocoController 的 coupler 恢复作用域与真实契约。复现：未进入循环制动、前馈被车钩保护两次投影清零时，被误认为没有制动请求，恢复状态丢失，下一步从 0 跳至 1/0.7，绕过配置的恢复率 2/s。增加仅此零保护/前馈有效的请求判定，保留正常缓解、下限连续投入和 ATP 权限；默认恢复率/前馈开关不改。
- 修复前真实测试失败；用同初态混合速度窗口、相同显式试验配置比较。不得用契约通过宣称性能完成。

- 复核：修复后 6 文件 130 项通过；补充平坡惰行边界后控制器文件 49 项通过。实际混合窗口前后 rows/请求/实际 ED/实际空气指令数组完全一致，峰值 1233.107 kN、超限 371、jerk RMS 0.089524，仍未达标，未触发此次边界，不宣称性能改善。D 盘归档 ff_coupler_memory_before/after 及比较 JSON，报告说明本项不直接解释默认循环制动图的高频波动，默认开关与主配置不改。

#### 前馈机车分配对照（改前登记）- 2026-10-13

- owner：xmc，仅冻结诊断控制器样本，不改默认控制器。原前馈沿用首/尾 1/0.7 深度权重，尝试仅前馈采用相同深度权重，由原动力学逆映射重新求总需求；常规循环制动、ATP、车钩模型不改。相同深度并不等于不同功率机车力相等，不宣称最优分配。
- D 盘冻结源码明确默认前馈开启，metadata 记录实际 runtime/哈希；23500 m 起同速 120 s、混合 40 km 起 60 s 先验证，数据负面则不合入。

- 等深度试验：第二坡段峰值 1000.928→905.876 kN、超限 1→0，但混合超限 398→471、jerk RMS 0.108560→0.118310，拒绝作为默认分配。试验源码与原始数据保留在 D 盘 equal_ff_*，未修改默认权重。

#### 实际电制动执行反馈（改前登记）- 2026-10-13

- owner：xmc，train_env 的新增只读 info 实际 ED 深度、fleet 执行后的反馈及 controller 恢复历史。原恢复记忆存请求，ATP/保护可能改写后实际不同；恢复限速应以最近实际执行为参考。默认恢复率 0 时行为不变，奖励/观测/动作形状不改，旧冻结控制器无反馈方法不改写其历史。
- 真实单列 EBI 介入下零请求→实际 ED=1 的契约先复现，再以显式前馈+恢复2/s 的混合同初态验证，不能以逻辑通过代替动态验收。

- 结果：原契约失败、修复后6文件132项通过；反馈与真实动力学输入的逐项契约补验通过（控制器文件50项）。前馈+恢复2/s混合对照最大 jerk 0.913745→0.881694，但超限371→376、峰值同1233.107 kN，未达性能验收。默认前馈/恢复关闭的复测与旧 sbi_air_mixed 四组原始数组完全一致，不改默认轨迹。D盘保存 actual_ed_feedback_before/after/default_check、比较JSON及报告；奖励/观测/动作形状、主YAML和物理均不改，未提交推送。

#### 编队降低上限后的后部速度守卫（改前登记）- 2026-10-13

- owner：xmc，仅底层控制器及真实环境契约。检查编队降低 v_max 后后部速度达到编队上限但车头未达到时的触发/恢复限速边界；保留 ETCS 车头位置监督语义，不将车头 ETCS 曲线直接套给尾车，不改物理或主配置。先复现再修复，边界正确性不代表整线平稳性达标。

- 结果：真实 1+1 环境下车头65/尾72 km/h、编队上限70 km/h的契约改前失败，修复后通过；后部按编队上限触发循环制动、禁止弱化空气兜底及绕过恢复延迟。ETCS车头位置上限仍仅作用车头判断。控制器/编队/归档三文件回归全部通过，git diff --check通过。首次归档测试因沙箱临时目录创建失败，改D盘独立临时目录复测通过；尚未运行新整线性能验收，不宣称速度均匀或车钩力达标。

#### 编队后部守卫动态对照 - 2026-10-13

- owner：xmc，旧53km线40km起、40/65/65 km/h、额外列距200m、600步60s，改前仅回退上轮三处守卫表达式的冻结源码，与当前同物理对照。rows/实际ED/实际空气及速度位置完全相同，请求commands及cyclic状态不同：安全层最终覆盖差异。峰值1233.106566 kN、超限597、jerk RMS0.066897747、最小列距210.828226m、线路超速0，仍未达标。相邻两步实际ED变化≥0.5的列-步23次，其中14次相邻SBI事件（不等于已证实因果）；下一步查安全层介入/退出与普通保护请求的衔接，不弱化ATP。原始档案 external_archive/controller_extended_20261013/formation_guard_before_mixed 和 formation_guard_after_mixed。

#### develop合并及两万吨适配核查 - 2026-10-13

- owner：xmc。xmc-dev已快进合并origin/develop至50896db，原控制器修改通过stash恢复，无冲突，备份保留。新版主线路49.6km，主配置仍10kt_1plus1；用户提出转两万吨，具体研究编组待确认，不擅改主YAML或车辆物理。两种20kt预设实际均1+108+1+108（机车index0/109），validation预设注释有1+1歧义，非首尾布局；数值质量须运行核查，不能直接认注释。仅更新独立归档测试的已移除旧线路名，不改历史数据。

#### 两万吨中部分布动力诊断适配（改前登记）- 2026-10-13

- owner：xmc。用户确定1+108+1+108，使用20kt_1plus108_1plus108，实际21976t/218辆/机车index0和109。先增加独立诊断编组选择及元数据防误标契约，主YAML与物理不改；后续基于49.6km线路重新建立制动能力/传播/平稳性基线，旧一万吨结论不沿用。

- 首阶段结果：诊断新增--consist-preset，复用档案时拒绝更换编组标记，5项归档契约通过。三列21976t中部分布动力、新49.6km线路16km起65km/h、额外列距200m，60步6s链路运行正常，峰值370.001kN、超限0、超速0；未触发电空制动，不能当作制动平稳性验收。数据middle20kt_route_smoke_01，下一步运行覆盖实际制动及缓解的窗口。

#### 两万吨制动与电制动能力核查 - 2026-10-14

- owner：xmc。新49.6km线16km起、三列两万吨中部分布动力、80km/h、额外列距200m，1200步独立基线正在运行，源码已由进程载入，后续候选不替换此档。真实-12‰常坡80km/h静态核查：规则ED可用比0.334091，既有1/0.7实际指令的引擎ED/总坡力比0.241297；原估算不含0.85效率且不含后机0.7分配，分母仍按最陡坡保守估算，不以这个差值独立证明动态根因。两万吨规则门控需后续同物理对照，先保留基线。

- 改前契约：两万吨-4‰80km/h下，旧ED估算1.002274（认为可单独控速），按实际1/0.7分配的真实能力比0.724143；测试失败。修复仅能力查询，保留最陡坡需求的保守分母、空气充风/新增源门控及ATP权限，无新物理常数。

- 验证：新增真实能力契约先失败后通过；控制器、编队、充风/保持与安全权限三文件回归通过。四项旧充风测试原先FakeDynamics缺真实ED力接口，已迁移到正式两万吨模型，未在产品代码添加假模型兼容。120s旧估算基线峰值2777.319kN/超速351列步，30s改后与基线前30s rows完全一致（峰1369.417kN、超限5517、jerk RMS0.037552），本窗口原先已要求空气制动，未触发能力误判边界，不宣称动态改善。源/轨迹位于D盘controller_extended_20261014，下一步应验证4‰等误判边界及退出衔接。

#### 两万吨缓坡能力门控动态复核 - 2026-10-14

- owner：xmc。正式两万吨单列、-4‰、初80km/h、600步60s，冻结旧估算与引擎估算对照：峰值1126.808→1174.296kN、超限252→1063、jerk RMS0.035151→0.055925、平均速度77.819→64.583km/h；超速130→67列步。拒绝默认采用，新查询保留ed_physics_availability显式试验（默认False），诊断开关/runtime元数据及复用校验登记；主配置不改。此前精确估算修复须标为实验而非默认性能改善。
- 新版两万吨120s基线SBI相关大ED跳变：介入62次均增大、退出62次均减小、持续介入0次；无SBI相邻34次（有1次列步同时包含机车增减）。计数阈值每步ED深度绝对变化>=0.5，非力变化。下一步优先退出交接，但须保留车钩减权即时性和ATP加强权限，不直接移植10/50秒保持常数。

#### SBI退出电制动交接冻结试验（改前登记）- 2026-10-14

- owner：xmc。仅D盘冻结候选，不改默认控制器。按真实执行ED反馈，在前步SBI时建立交接状态；仅非低速且车钩减权scale=1时试验撤出2/s，scale<1立即退出试验状态并保留减权，ATP在环境末端仍立即接管。2/s是工程试验非文献参数，无10/50秒保持。与当前默认同两万吨49.6km路线16km起80km/h30s比较，负面不合入。

#### 退出交接结果补读与提前控速验证 - 2026-10-14

- owner：xmc。重新核查发现middle20kt_sbi_exit_trial_01已生成完整300步归档，前次会话失联不能等同结果不存在。正式metadata/hash核查与基线前300步rows完全一致，超限5517、峰1369.417kN、jerk RMS0.037552，候选无改善，不合入。修正此前未完成状态，保留历史。
- 下一步仅显式前馈：三列两万吨、新线路16km起65km/h、额外列距200m，600步60s零RL，当前默认与ed_grade_feedforward对照；用真实净坡力电制动抵消加速，能力估算试验保持关闭，不提前空气制动、不改ATP/车钩。验证能否避免进入反复安全接管；失败拒绝默认。

- 60s同工况完成：默认/前馈峰值916.763/1410.457kN，车钩超限0/2735，jerk RMS0.014529/0.058516，平均速度72.993/71.674km/h，超速列步113/39，最小列距365.139/350.822m。前馈虽减少超速/监督事件，但加重车钩和波动，拒绝默认启用，默认代码保持不变。源、元数据、原始NPZ归档middle20kt_early_ed_before_01/after_01。本轮退出候选补验：实际1847kN车钩力立即清除交接状态且ED减权0；逻辑正确仍无动态收益。后续须先捕获有符号逐断面车钩力与两机车实际制动力，定位局部作用，不能只调全列制动深度。

#### 两万吨局部制动力/断面诊断（改前登记）- 2026-10-14

- owner：xmc，仅独立diagnose脚本留痕。增加每断面有符号力、每机车步末ED力、每车步末空气力及位置/速度；步末力为现状态模型查询非步内冲量。旧档缺字段保留未知，不重写历史。与既有早制动候选同初态重跑，检查新增查询不改变rows。定位首机/中机附近断面及保护切换，不改默认控制器/物理/阈值。

#### 局部断面与活动空气源升级缺口定位 - 2026-10-14

- 新增独立诊断字段：signed逐断面力、步末两机车ED力、每车空气力及位置速度，5项归档测试通过。同600步前馈重跑rows/实际ED/实际空气与旧档完全一致，证明记录未改变本窗口动力学。
- 峰值：48.4s第二列、第112断面（中机index109后方），正向断面力1410.457kN，EBI，ED两机1/1，步末ED力390.381/389.326kN；前半列空气力9.747kN、后半列0。40s空气输入EMERGENCY而stored head SERVICE，仅1辆active。
- 实物理最小复现：TrainFormationEnv正式两万吨70km/h，原生step_vehicles_ed_ab先SERVICE、后EMERGENCY，头部档仍SERVICE。train.py::_advance_control_once只在源inactive时_apply，后者也仅inactive建波，因此活动源升级缺口。首次TrainFormationEnv EBI复现因未设曲线未触发EBI，不作为证据；原生指令序列已单独复现，轨迹现象一致。物理部分归队友，不做释放再紧急的控制绕行，不改模型。后续应协作修活动源升级后重评控制器，不能将当前执行缺口归因于MAPPO或平滑参数。

#### 活动空气源升档修复（改前登记）- 2026-10-14

- owner：xmc；用户在明确报告物理执行缺口后要求继续修复，本轮限定空气档位执行，不触碰队友车钩/车辆参数。活动源允许更强档位升级；新增独立升档波以保留旧常用波到达，强波按既有波速传播；重复指令不重置升档计时、弱波不得覆盖强档，缓解与重置清队列。先真实回归复现，不保证峰值因修复降低。

- 活动源升档实现：独立升级pending/delay保留先前弱波，rank防弱档覆盖强档，单/多源路径均允许更强命令，缓解/重置清队列；无车钩/车辆/波速常数变更。改前三项真实升级契约失败，现6项专项通过；6个运行/传播/控制/物理回归文件通过，5项归档回归通过、导航/差异校验通过。首次版本两项运行失败来自同档多源更早到达被截断，已修保留原同档更早波逻辑，原断言全部保留并通过。
- 12s默认初80无EBI，仅运行检查，rows与旧前120步一致。真实60s前馈压力工况：请求EMERGENCY但车头SERVICE列步84→0；峰值1410.457→2026.039kN，超限2735→7344，jerk RMS0.058516→0.066185，超速39→12，监督事件7035→2174，平均速度71.674→71.600km/h。执行正确性已验证，动态未达标；保留修复不恢复漏执行，前馈仍默认关闭。新峰50.9s第二列123断面，两机空气EMERGENCY，SBI阶段。诊断新增train_dynamics源码快照/hash，复用旧档保持未知不误标新物理。后续优先正确空气执行下的制动力分配，不宣称整体改善，未提交推送。

#### 中部分布动力分段净力分配试验（改前登记）- 2026-10-14

- owner：xmc，仅D盘冻结控制器；候选按每台机车至下一机车/尾部的车辆段实际净坡力分配ED，由现有引擎逐机车反算。自研分配假设，非论文参数，段间车钩仍实际耦合，无硬保证；循环基线/ATP/保护/空气源不变，前馈显式开启，与正确升档物理下旧前馈600步65km/h工况比较。旧一万吨首尾布局不应用此段划分。负面不合入。

- 分段候选基础契约：真实两万吨4/6‰分段65km/h，逐段净力残差<1N、不同需求分配不同ED、pos/vel未推进；首次2/4‰检查后段净需求为负，正确ED0，不应断言两段都需制动。正式60s分配候选峰2261.762kN、超限10124、jerk RMS0.075403、超速16；旧前馈同新物理峰2026.039/超限7344/jerk0.066185/超速12，候选综合恶化拒绝合入，冻结源码/元数据在D盘section_ed_*。两者train_dynamics hash完全相同。
- 补齐正确升档物理下默认600步基线middle20kt_correct_default_01：峰916.763kN、超限0、jerk0.014529、超速113、最小列距365.139m、均速72.993km/h。旧一档默认同窗口rows可逐项核查；当前实际默认优于两种前馈试验，前馈/精确能力/恢复限速都不默认启用。不是默认越来越差，但默认仍有超速，60s不代表整线验收。后续优先在默认基线上独立试验接近上限时的制动触发时机，而非叠加前馈；另查压力工况安全制动分配。

#### 默认规则触发裕量对照（改前登记）- 2026-10-14

- owner：xmc，仅D盘冻结候选。当前默认同工况60s峰916.763kN/超限0但超速113列步；仅循环启动判据提前既有AB_SUPPRESS_MARGIN_MPS=0.5m/s，释放下限/制动力分配/ATP/车钩保护及前馈关闭不变。裕量为工程试验，非论文参数。正确升档物理下三列两万吨49.6km线16km起65km/h、额外列距200m600步对照，负面不合入。

- 提前完整循环候选60s：峰1199.616kN/超限241/jerk0.017333/超速73，默认917/0/0.014529/113，安全/平稳性劣化拒绝合入。继续单变量缩小：不改循环/空气触发，接近原上限的既有0.5m/s窗口内仅渐进加入ED，按既有1/0.7分配及原两次保护，不改变ATP/低速/主配置。比较是否避免提前AB造成的冲击；不预判根因。

- ED-only渐进候选短窗共同改善：峰872.589kN、超限0、jerk0.008692、最大jerk0.092037、超速101、均速72.941km/h、最小列距367.452m。相对默认峰下降4.82%、jerk RMS下降40.18%，仍有超速，不验收整线。整理为ed_prelimit显式实验选项默认False（fleet/env_cfg及诊断开关与runtime/ref复用防误标），不改主YAML。新选项只在原速度边界的既有0.5m/s内渐进ED，AB触发/规则latch/ATP/保护保持；登记后再改生产接口。

- 整理完成：ed_prelimit默认False，配置接口和独立诊断开关均可显式启用。新增真实头/尾近上限、禁止提前AB、车钩减权和runtime/复用防误标契约；5个回归文件全部通过，8个边界速度生产选项输出与冻结候选逐项完全相同，导航和diff校验通过。仅60s局部收益，仍超速101，不改主YAML/默认，不宣称长窗口/整线/训练达标。未提交推送。

#### ed_prelimit长窗及第二工况复核 - 2026-10-14

- owner：xmc，本轮冻结行为代码，仅诊断。A：原16km起65km/h三列两万吨延长1200步120s；B：40km起79km/h（近上限）三列两万吨600步60s；两组均额外列距200m、同49.6km路线/物理、零RL，默认与ed_prelimit显式对照。检查后半段/不同坡段、初速效果，负面不默认，不拿60s改进宣称整线。

- 完整反证：A120s默认/候选峰3003.655/1274.697kN、jerk0.044720/0.013392，但最高车厢81.920/88.205km/h、超速404/1864列步，拒绝启用。B60s默认/候选峰1813.197/1994.805kN、超限9040/11440、jerk0.064580/0.084261、超速363/433，亦恶化。此前60s改善结论仅原短窗有效，不能推广；ed_prelimit维持默认False，代码注释标记长窗失败，主配置不改。
- A候选120s：实际空气active列步0，请求AB机车步3722，物理空气输入HOLD1861列步/RELEASE1739列步；默认空气active列步1889。60/80/100/120s原始采样确认全部三列空气未建立、控制规则持续要求AB、超速规则持续生效。当前车钩新源veto与线路超速实际空气执行存在优先级冲突；ETCS有SBI/EBI空气映射，普通线路overspeed仅ED映射，后续优先真实契约复现和隔离验证，不直接放宽车钩阈值或解除保护。不宣称硬保证或整线达标。

#### 线路超速空气执行优先级契约（改前登记）- 2026-10-14

- owner：xmc，限定train_env执行接口。SafetyLayer已有优先级A车钩→B间距→C线路超速→D ETCS；C按车辆投影制动但decompose未转为实际空气制动，新增源veto导致空气始终0。先真实高钩力79/81km/h请求组合复现；C实际事件时映射车头SERVICE空气命令，保留请求/ETCS EMERGENCY最高，不泛化货车超速为全机车ED覆盖；未超速新源veto保留，波速/模型/阈值不改。先契约/回归，再同120s工况对照，不宣称车钩必达标。

- 契约：显式80km/h线路限速下，4种AB请求×79/81km/h，高车钩力真实case改前超速4项空气全RELEASE，改后8项通过，低速veto保留。首次测试未设单列限速（默认较高）未触发overspeed，不计复现证据。修复C/SBI均映射车头SERVICE、强请求/已命令EMERGENCY不被重复事件降级，ETCS最高、ED局部索引映射保留。
- 6文件回归通过；旧纯缓解测试在陡坡触发新ATP空气导致不全释放，改成固定-2‰缓坡隔离纯缓解，原v_end>20与f_end<300及全释放断言保留并通过，未降低阈值。
- 动态：原prelimit120s隔离冲突case最高88.205→82.969km/h、超速1864→485，峰1274.697→3083.192kN、超限3410→62834、jerk0.013392→0.056684，空气建立但冲击恶化，仍未达标，prelimit继续关闭。第二工况实际默认：峰1813.197→2603.844、超限9040→42300、jerk0.064580→0.078614、超速363→395，未获总体改善。执行正确性和控制性能分开，保留优先级修复不恢复漏执行，主YAML/车钩/阈值不改；后续优先两万吨制动能力与安全曲线、传播/分配，未提交推送。

#### 安全曲线超出速度表回退缺口（改前登记）- 2026-10-14

- owner：xmc，限定etcs_braking.nominal_decel的profile越界回退。当前40/60/80kmh表0.426/0.401/0.382，>80后返回constructor默认1.6，超速时高估能力。先边界/制动距离单调契约，改为表末段延续，保留无profile的固定曲线语义，不改系数或物理。单独审计显示两万吨饱和EMERG+ED平坡首段80约0.377m/s²、第三段约0.253，而曲线0.382；build_up10.536只含传播，另有10s升压。审计是模型状态能力查询，非动态标定，不直接写新系数，后续另验。

- 审计口径更正：首轮把Davis正幅值当成有符号力相加，所记0.377/0.253不是正确平坡总减速度，作废。重新按原生方程：brake-only=-(ED+AB)/mass、flat-total=brake-only+R/mass。两万吨80km/h首段0.416157/0.455260，第三段0.292093/0.331196；曲线固定0.382在后续段仍偏强。饱和状态审计非轨迹，不改物理参数；建立时间传播10.536s+现模型紧急升压10s另须核查。
- 越界两项契约改前失败：80.001km/h名义减速度1.6不符表末0.382，单档81km/h制动距离650.727m而等价固定档应664.103m；修复后4文件回归通过，无profile固定曲线保留。距离跨界单调测试原来已通过，不宣称原来距离反单调。归档增加ETCS源码hash/snapshot，旧档缺失保持未知。

- 同工况60s默认越界修复对照：峰2603.844→2544.246kN、超限42300→42239、jerk0.078614→0.080293（略恶化）、超速395→395、最高82.316→82.316、均速73.527→73.536。越界正确性通过，但整体性能未改善/未达标；不把约2.3%峰值下降宣传为验收。新归档etcs_profile_bounds_after_01含ETCS完整源与hash，旧档ETCS哈希缺失不补写历史；train/env/fleet控制源可核对同一版，唯一行为改动为末档回退。后续两万吨能力衰减与建立时间需正式标定/独立对照，不能只替换数字。

#### 两万吨保守能力曲线冻结试验（改前登记）- 2026-10-14

- owner：xmc，仅D盘冻结fleet副本：深拷贝当前正式动力学进行饱和紧急/全ED能力查询，按既有最差循环衰减段取brake-only减速度，40/60/80/90/机车最大速度端点；不计阻力作保守量，不改物理系数。建立时间用既有传播+升压，常用建立时间独立传播+常用升压。模型一致性试验，非实车安全标定，默认/主配置不动。检查新曲线初态是否已落入监督区，不能把不安全初态强压结果当正常巡航。先冻结对照，再决定下一轮；可能涉及目标间距/模型约束可行性瓶颈。

#### 缓解中重新制动执行契约（改前登记）- 2026-10-14

- owner: xmc。原生两万吨模型已复现 SERVICE→RELEASE→SERVICE 源车辆继续排风；本轮仅修复制动指令执行，不改车钩参数。重施同档应恢复升压、保持当时有效压力，远端等待有限波速到达；先失败契约再回归，并以相同40km/79kmh工况比较。能力曲线冻结试验未采纳，默认曲线不变。

#### 中部分布动力等总量电制动分配试验（改前登记）- 2026-10-14

- owner: xmc，冻结控制器副本试验，不改默认。当前两台机车基础请求1.0/0.7，同总量改为0.85/0.85，检验中部108车对称编组是否仍宜沿用首强后弱。保留AB、1000kN和ATP权限，物理完全同源；依据实际力分配和同工况量化比较，而非把对称分配称为已证最优。

#### 正常控制承接SBI速度上限试验（改前登记）- 2026-10-14

- owner: xmc。上一轮冲击峰在53.5秒、中部机车后断面109，ATP EBI迫使两机车全电/紧急空制动，普通循环状态却为False；现有anticipate_etcs实验开关承接服务监督上限并维持循环，验证能否避免反复交权。保持安全层权限及全部模型参数，默认开关不动，同40km/79kmh对照。

#### 重叠缓解波压力跳变（改前登记）- 2026-10-14

- owner: xmc。原生20kt复现：尾部有效压力0.688566，前部重施SERVICE后再次RELEASE，尾部跳回0.8并重置缓解延迟。下一轮保持已进入缓解车辆的既有排风/波前，仍撤销未到达的重施波。真实小步0.1s测试失败后修复；等待当前冻结运行结束再修改物理执行。

#### ATP接管保留中部分布动力（改前登记）- 2026-10-14

- owner: xmc。ADR-029当前通过清空弱AB源保证紧急生效，但全列请求退回车头单源。冻结fleet内嵌train环境副本，安全事件把两台机车的源统一升级为最终SERVICE/EMERGENCY（双向有限传播），不让弱源遮蔽强指令，不改默认与波速。诊断档案保存实际内嵌train源，避免来源指纹误标。验证1000kN、速度平顺、超速及权限回归后再决定。

#### 本轮控制修复收束：监督接管与模型一致性瓶颈 - 2026-10-14

- owner: xmc，仍xmc-dev，无提交/推送。保留同档重施与重叠缓解压力连续性两项执行修复；7个相关动力学/控制测试文件及6项归档测试通过（非全仓测试）。B60秒最终默认jerk RMS0.047796但峰4839.110kN；A120秒峰4616.871kN。冻结双源ATP试验同物理峰4524.827kN、超速381（默认477），jerk0.056542恶化，未启用正式默认。未完成整线，不声称达标。
- 瓶颈：峰值时EBI覆盖普通控制、强制全ED与紧急AB，平滑与车钩减权无法同获权限；当前20kt监督名义能力/建立时间与执行模型尚未校准一致。需动力学负责人共同确认循环段能力、双源传播/升压、群组工况，继续设计提前协调接管。相关train.py修改待联合审查，训练/对比须共享同一模型。D盘完整证据：external_archive/controller_extended_20261014/两万吨底层控制器复核.md；冻结策略、两侧元数据、实际源码和轨迹均已保留。

#### 并行文献原文复核 - 2026-10-14

- owner: xmc。完成本地5篇重点章节＋仓库赵紫宁2022论文及张二田2021实测论文原始PDF参数复核，共7份；未改控制策略/未新增仿真/未向队友发消息。原文表5-4含分车充气时长12/44秒，表5-5三段系数有特定初速/制动持续/缓解历史；222秒是实测最短，不是统一许可门限。10秒（缓解后）、10秒（最大拉钩力后调整）、50秒（优化约束）计时含义不同。下一轮先核对各车位压力/档位减压/循环计数与恢复、监督建立过程，再做单变量控制实验。
- D盘原文、页码图片、SHA256及差异清单：external_archive/paper/底层控制瓶颈专项调研/原文复核与模型差异清单_20261014.md。已核验缺失文献题录/官方入口，受限或下载失败全文明确标注未取得，不作为参数证据。

#### HOLD错误累计空气制动循环（改前登记）- 2026-10-14

- owner: xmc。_advance_control_once将ab_command=None保持指令写成_brake_was_active=False，后续SERVICE/EMERGENCY累计新的制动段，尽管没有发RELEASE。先原生20kt SERVICE→HOLD→SERVICE/EMERGENCY失败契约，再仅修正None保持原有段状态；显式RELEASE仍分段，不重定义完整循环或恢复机制，不改Cβ。与overlap_release_after_01相同工况60s比较，来源哈希注明执行物理不同。

#### 监督建立时间单变量冻结试验（改前登记）- 2026-10-14

- owner: xmc。本轮保留原名义减速度曲线，仅以当前执行模型参数构造传播＋该档位升压的保守全量建立时间：紧急L/250+10，常用L/200+18。属于模型一致性假设的冻结fleet对照，非实车标定/严格安全保证，不改正式默认；与HOLD修复后同模型同控制器B60s对比，运行etcs_runtime记录实际20.536/31.17秒。原文支持分开刻画传播与升压，但不直接规定该求和包络；不复制12/44/58秒论文拟合值。

#### HOLD修复本轮结论 - 2026-10-14

- owner: xmc。HOLD不再结束制动段，SERVICE保持/EMERGENCY升级不额外衰减；显式RELEASE仍分段。7个相关动力学/控制文件及6个归档契约通过。B60s改前改后600行轨迹完全一致，不能归功于性能改善。建立时间单变量冻结试验20.536/31.17秒对照峰4839.110→5622.137kN、jerk0.047796→0.080938，拒绝默认采用，名义减速度profile及物理保持不变。仍是监督能力/建立过程/接管协调联合校准瓶颈。来源external_archive/controller_extended_20261014/hold_and_build_time_comparison_01.json及两万吨底层控制器复核.md。无提交推送，车钩参数及文献时间常数不动。

#### 压力建立与安全退出平滑复核（改前登记）- 2026-10-14

- owner: xmc。新增诊断仅记录原生_brake_pressure、缓解倍率、有效压力系数及releasing状态，不将归一化系数标为kPa；固定正式物理B60秒，并与hold_segment_after_01核对轨迹一致。冻结控制器试验仅在ATP接管后的普通退出阶段限制ED下降，1/s为自研试验值；当前车钩减权/ATP最终保护不延迟、不改AB/安全阈值/车钩参数。先原生权限契约，后同工况性能及压力定位，失败候选不启默认。

#### 分车压力定位与退出平滑本轮结论 - 2026-10-14

- owner: xmc。只读新增压力/缓解倍率/有效压力系数和releasing归档，6项归档契约通过；B600行与旧HOLD修复基线完全一致。冻结普通ATP退出ED下降1/s，正式fleet权限契约四项通过，峰4839.110kN/超速477不变，jerk0.047796→0.047728（约0.14%），不采默认。首次契约初始化模式/共享曲线缺失导致失败，已纠正且失败不当证据。
- 峰52.4s/第2列/断面125，EBI强制全ED/紧急AB；前半列有效压力系数1，尾车0.72659。三列段号1/5/24，第2列4次、第3列23次重施前仍有车辆active；不能按已充分充风长循环解释。第三段后衰减饱和，24不是24次累乘。当前瓶颈需要物理负责人核对短时重施/恢复、段号与Cβ适用性、两源/列尾分车建立和监督曲线。控制候选仅D盘冻结，不动正式默认或车钩。无提交推送。证据external_archive/controller_pressure_20261014/分车压力与安全退出复核_20261014.md及pressure_and_exit_comparison_01.json。

#### SBI普通退出空气保持滞回（改前登记）- 2026-10-14

- owner: xmc。压力基线第3列35.6/35.7s RELEASE→35.8s SBI SERVICE，之后0.3–0.4s反复，CF保护持续存在。冻结控制器仅保持已active且未releasing的头部源，SBI退出裕量复用AB_SUPPRESS_MARGIN_MPS=0.5m/s（试验值，非论文规定），低于当前SBI减裕量/目标消失/源不再活动时立即取消保持。不新增中部源、不重施已缓解源、不改ED/CF减权/EBI最终覆盖/充风参数。与pressure_baseline_01同B60s比较，不达综合预期不启正式默认。

#### Episode空气制动残留（改前登记）- 2026-10-14

- owner: xmc。滞回源失活边界检查发现fleet.reset后旧source仍active；原set_initial/set_initial_speed清压力/段号/部分pending，但未清active/notch/releasing/传播延迟/缓解倍率。原生20kt旧EMERGENCY→reset→SERVICE可能继续旧紧急档，先失败契约；等待滞回运行结束再统一清空气状态，保持所有物理参数不变。包括两类initial方法及正式群组reset，重复episode对照fresh。

#### SBI退出滞回与episode空气重置本轮结果 - 2026-10-14

- owner: xmc。冻结退出滞回B60s峰4839.110→4912.045kN、jerk0.047796→0.049540，超速477→470，整体不采默认。边界检查发现reset残留active/notch/releasing等空气状态，三项原生契约失败后统一重置；18项空气测试通过，含重用fleet与fresh fleet的10步SERVICE轨迹一致。7个相关动力学/控制文件及6归档测试通过。滞回运行在重置修复前结束，两模型版本严格区分。保留重置正确性修复，不改物理参数或车钩；仍未达综合预期，无提交推送。external_archive/controller_pressure_20261014/退出滞回与回合重置修复_20261014.md及sbi_hysteresis_comparison_01.json。

#### 编队追赶抬高缓解线的冻结对照（改前登记）- 2026-10-14

- owner: xmc。先以回合空气重置修复后的正式代码复跑B60秒基线。新候选只在D盘冻结fleet副本：已有循环制动且空气源仍active、未releasing时，不由追赶逻辑将缓解线抬到前列速度附近，保留原40km/h底线及所有ATP/车钩/充风权限。检查追赶与空气制动反复交权，非物理参数标定；同工况比较，未获综合改善不采正式默认。无车钩修改、无提交推送。

- 语义核对更正：候选只取消额外chase_v抬高，保留coordination_adj原有gap偏置（最高3m/s），并非一律恢复40km/h。原生两万吨边界：无空气循环时偏置9.1323m/s、已有循环空气时3m/s；两项实际控制链契约通过。前两次零偏置/小于2假设断言错误，已纠正，不作为失败复现或性能证据。

- 本轮结果：回合重置后的正式B60s与旧pressure基线600行rows完全一致。冻结chase条件候选峰4839.110→1878.223kN、超限60510→12500、段号1/5/24→1/1/1；但jerk RMS0.047796→0.048860，均速73.927→66.866km/h、终点列距310/366→465/397m。仍超1000kN且最高82.316km/h，不采正式默认。四相关控制/空气测试文件及两冻结原生边界通过，diffcheck通过；非整线/全仓验收。证据external_archive/controller_pressure_20261014/编队追赶与循环制动交权对照_20261014.md及两侧result.json。瓶颈：减少重施以持续空制动换取较低冲击，却拖慢跟随列，需循环阶段与编队目标协调，而非简单保持或抬高缓解线。无提交推送。

#### 线路表与制动阶段对接（改前登记）- 2026-10-14

- owner: xmc，限定D盘冻结fleet候选，不改主配置/车钩。核对xlsx主表K40条件缓解与表3 K42汇总差异，保留40–42候选窗，不能位置强放闸。按主表公里标限速构造带源文件SHA256/行号的只读数据，当前位置和前方降低限速目标接入安全链；候选只在已有循环且空气active未releasing时取消额外chase缓解线抬高，保留普通偏置与ATP。50kPa/350kN/50秒未获模型映射确认不硬编码。先原生边界，后同新限速工况基线与候选对照；旧80km/h结果不混比。

- 线路对接本轮结论：D盘冻结限速候选原生契约通过（当前位置75、前方70、gap保留、不积累）。新初速65km/h、40km起点B60秒对照峰2359.654→2447.213kN、超限25692→25994、超速546不变，阶段候选请求切换10→6但整体失败，不采默认。限速对接当前只在冻结decompose入口，完整四阶段控制尚未完成。新缺口：表中普通减压50kPa，规则SERVICE实际140kPa；已有全列reduction覆盖每步更新且可能影响紧急，不能全程固定50削弱ATP。下一轮先普通减压接口/分车档位与压力语义联合核对，暂不改队友物理。证据external_archive/controller_pressure_20261014/线路限速与制动阶段对接复核_20261014.md及route_baseline_03/route_phase_after_03来源档案，无提交推送。

#### xmc-dev阶段性提交与推送登记 - 2026-10-14

- 用户明确要求推送此前完成工作。提交包含已保留控制/空气执行正确性修复、ETCS越界回退、诊断与绘图入口、相关原生契约及文献/进度记录；未启用失败候选，不改主YAML、车钩参数或1000kN阈值。D盘仿真原始档与冻结候选不纳入正式代码，路径见本流水。
- 提交前check_agents_links、check_outputs_layout、diffcheck通过；两万吨原生训练入口2回合×20步冒烟成功、模型/metadata落external_archive/push_validation_20261014。warm_start关闭、未达batch size故无梯度更新，非训练收敛/整线验收。
- 全量pytest首次C盘tmp_path权限失败，不算功能回归证据；已停止旧进程并使用D盘独立basetemp重跑，目前仍在运行，未宣称全量通过。远程origin/xmc-dev无新增提交；origin/ckb-dev有新工作，本次不自动合入，后续按owner共同审查物理执行修复。性能仍存在超速/车钩超限，50/140kPa映射缺口尚未解决。

#### D盘实验档案补传 - 2026-10-14

- 用户要求补推原始数据和冻结副本。extended/pressure两组37个完成诊断运行，共306个原有文件约311.35MiB，逐文件SHA256核对一致；空目录/无result+trajectory的测试壳不上传。正式代码不导入归档，不启用未采用策略。入口outputs/sim_validation/phys_validation/controller_repair_20261014/README.md；publication_manifest.json登记仓库相对路径、原路径和校验值；图独立放figures/controller_repair_20261014。旧元数据原样保留、不重标模型，文档索引已登记。原D盘数据仍保留。本批不含更早日期档案、论文PDF或训练检查点。

#### 单列规则层运营口径标定 A–I 轮（MARL 前置）- 2026-10-15/16

- owner: 单列车钩力任务线（编队归队友）。计划 .trae/documents/rule-layer-operating-calibration-plan.md（P0–P3），验收 ADR-036 制动工况档（峰 ≤1350 kN / 均速 ≥60 / viol≈0 / 不贴 40/80）。P1 落地：CYCLIC 50 kPa 档 + 表3 独立速度门 + ED 缓解协同（全默认关，编队线零回归，13 单测绿）+ ADR-036 门限配置级落地（YAML 显式 1.5e6/2.25e6，训练经 registry→TrainFleetEnv 同源生效，metadata 实证）。P2 迭代 A–H 详见 DIAGNOSTICS_2026-10.md「规则层标定轮 A–H」（G 当前最优 2203/1738/66.0；H 未达标 2247/2039，主钳制源定位到安全层规则 A release 钳零）。2026-10-16 实现 I 组：coupler_override 配置接线（train_env/fleet 双透传，默认 release 零回归，2 接线单测 + 46 相关测试绿）。同日完成：开训命令冒烟实测通过（2ep/exit 0，metadata env_cfg 含 1500000/2250000/全新开关，BC warm start + curriculum 正常）、REFERENCE_INDEX 记表3 数据源（operating practice 措辞）、全仓旧配置名 single_train_coupler_20kt 修正。2026-10-16 晚：I 组评估完成**负结果**（2247/2039/66.0 ≡ H 逐位相同——规则 A 命中全为货车区间、min_brake 无物可咬，推翻"release 是主钳制源"假设）；同根因定位 = decompose 主流程 `final[:,0] *= scale` 把 H 组保住的 300 kN floor **二次清零**（ratio≥1→scale=0→前部无 ED 只剩 AB → t6750 主团簇 2247 kN），实现 **J 组修复**（L591 后兜底 `max(+floor)`，默认关零回归，3 新单测 + 45 相关测试绿 + 全量 pytest 361 项绿 + 链接/产物布局校验过）。J 评估完成**负结果**（2530/1984/65.9，峰值反超：floor 生效但压缩期拖慢前部、方向与 E 组同构）；归档深挖更底层根因 = **最陡段 CYCLIC 制动力不足 → 车速缓爬 80 → ATP 规则 C 事后把全列改 SERVICE 单源猛刹（头车 t6635 v=80.03 跨线时触发）→ 头波撞中后部成主团簇**（argmax 断面力 11→19→48→126 传播实证）。实现 **K 组预升级**：新旋钮 `cyclic_ab_upgrade_kmh`（默认 None 零回归）——循环制动中 `max_vel ≥ 门` 时规则层先把 CYCLIC 兜底预升 SERVICE（错峰双源、受充风/veto 门约束），先于 ATP 事后猛刹；controller+fleet 双接线、3 新单测、相关 110 测试绿；K 评估（=J 口径 + 门 76）归档 `rulecal_20261016/K_preupgrade76` 完成**负结果**（1931/58.8/1283，peak 较 J 改善 2530→1931 但均速破 60、viol 暴涨、speed_min 38.3 破 40 下限）：预升级确实生效（ruleC=0 且 v≥76 时规则层自发 SERVICE 374 步，J 同条件 0 次），但仅覆盖 CYCLIC 已 latch 窗口（release 态爬速至 80 仍被规则 C 抢先三次），且 SERVICE(140 kPa) 过刹把头车压到 36.6-40.5（<40 共 1570 步）——E/J 同构"过刹换低速"第三次复现。判读与 L 组方向（release 态预升级 + 降档中间强度 + 低速进验收）已写 DIAGNOSTICS_2026-10「K 组结果与判读」。同日实现 **L 组修复**：预升级条件由 `ab_nominal == CYCLIC_AB_SENTINEL` 扩为 `in (0.0, SENTINEL)`（补 ED-only 空窗），新增单测 `test_cyclic_ab_upgrade_ed_only_window`、控制器文件 22 项绿、全量 pytest exit 0；L 评估归档 `rulecal_20261016/L_edwindow76` 完成**负结果**（2840.5/61.3/7986/speed_min 39.5，四线三项未达标；K 对照 1931/58.8/1283/38.3）——修复生效（SERVICE 物理步 783312→1782253、规则 C 段 6→13）但 K 方向②被放大：过刹振荡更频（|F|>1350 步 548→1769、overspeed 483→1234），峰值 t=2672s @39.9 km/h 缓解拉扯团簇。**结论：方向①须与方向②联合**，M 组首试升级档降为 MIN(70 kPa) 中间档（候选②缓解门 45→55 视结果决定）；判读已写 DIAGNOSTICS_2026-10「L 组结果与判读」。同日实现 **M 组**：新旋钮 `cyclic_ab_upgrade_notch`（默认 service = L 行为零回归，非法值 ValueError）——预升级档降为 MIN(70 kPa, β 0.20) 中间档（升压仍先于 ATP、过刹大减），controller+fleet 双接线、2 新单测、标定文件 24 项绿；M 评估（= L 口径 + notch=min）归档 `rulecal_20261016/M_min_upgrade` 完成**负结果**（2464/59.9/5011/speed_min 38.8，四线未达标）——但方向②正确：相对 L 六项核心指标全改善（viol −37%、overspeed 1234→763、|F|>1350 1769→1022、峰值 2840→2464、head<40 304→184），AB 分布实证 MIN 档 25854 步接管升级、cyclic 回升至 2443239；代价 = 均速 61.3→59.9 微跌破 60，另暴露起步段 t=14-26s 2464 kN 团簇（全列 release 态的陡坡起步压缩波，非 AB 过刹）。K/L/M 三组失败模式互补：K 峰值最低但均速差、L 均速过线但过刹爆炸、M 居中两头不靠。**N 组设计 = M + 缓解门 45→55**（表3 出处，早释放避免压入 40 以下 + 缩短循环抬均速）；同日 **N 组评估**（= M + `cyclic_release_kmh=55`，无新代码）归档 `rulecal_20261016/N_release55` 完成**负结果但两条线首过**（3030.7/64.7/12312/speed_min 48.4、head<40 步=0）：mean 与 min 双 PASS、峰值与 viol 爆掉；根因探针 = 末段高能态 rule A 车钩规则介入正反馈（t=2728s ruleCoupler 116 步）+ 起步 min 档团簇 2464。同日 **O 组评估**（= L 口径 service 升级 + 缓解门 55）归档 `rulecal_20261016/O_release55_service` 完成**负结果且比 N 更差**（3056.5/68.1/14892/min 49.8，|F|>1350 步 2451 最差；ruleC 120782→253936 翻倍——service 升级档 × release55 高能态叠加 rule C 正反馈）。四组超线四分位对比确认 **K 仍峰值/超线步/起步最优**（548 步、起步 0 超线、四分位 [97,320,98,33]），仅差均速 1.2/低速 1.7，K 峰值在 release45 低速深坑（缓解门可覆盖）。同日 **P 组评估**（= K 口径 + 缓解门 45→50）归档 `rulecal_20261016/P_release50_service` 完成**负结果但三条线首次同时过**（2496/63.9/7002/min 44.6、head<40=0）——均速+低速+40 下限三线首过，仅峰值与 viol 未达标，当前全轮最佳组合；峰值根因 = 缓解时刻 service 波拖尾 + rule A 介入（t=2626s head 48.3→45.4 急减速）。**Q 组启动 = P + 缓解抬再生力 300→900**（回表3 原始口径，直对 P 峰值根因），归档 `rulecal_20261016/Q_boost900`（运行中）。同日 **Q 组评估完成判读**（2405.8/63.3/3790/min 42.2、head<40=0）——**三线继续同过、viol 腰斩（7002→3790）、ruleA 近半**，峰值仅 −90 kN；探针定案峰值 t=2616s = **单向缓解波 25-30 s 传播期速度反转压钩 -2406 kN**（头先缓解被 ED 按住 46.8、尾仍全制动 41.7 → 尾反弹 48.3 上撞断面 116），非 boost 强度问题。**R 组设计 = Q + `eot=true` 双向缓解波**（`train.py` 已实现、fleet 补透传 `train_fleet_env.py` 默认 False 零回归 + `test_eot_wired_through_fleet` 单测绿，Zhang2025 EOT 锚 780→489 kN），归档 `rulecal_20261016/R_eot`（运行中）。判读已写 DIAGNOSTICS「Q 组结果与判读」。同日 **R 组评估完成判读**（= Q + `eot=true`，1822.9/63.96/946/min 44.3、head<40=0）——**全轮最大跃升**：峰值 −24%、viol −75%、超线步 1450→974、ruleA 600→312；决定性证据 = **压钩格 F<-1350 = 0**（Q 3705 格），速度反转被双向缓解波彻底消除，剩余峰值全部转移至 v=78-80 高速制动段（top8 中 7 段 cb=True，pk 1525-1823）。**S 组设计 = R + 升级档 service→min 中间档**（直对高速段制动波强度），归档 `rulecal_20261016/S_min_upgrade`（运行中）；全量 pytest exit 0（eot 透传零回归）。判读已写 DIAGNOSTICS「R 组结果与判读」。同日 **S 组评估完成判读**（= R + 升级档 min，2562.2/64.37/5061/min 44.7、head<40=0）——**负结果且比 R 差**：峰值 +40%、viol +435%，起步段 t=14-28s 首爆 2562（min 档弱波头 + cb 更多，M 组中间档教训复现）。R 剩余峰值探针定案：>1500 步 85% 在 ruleA、ruleC/超速仅 29/0-2、top8 全 cb=True @ v=78-80 → **根因 = 高速段 service 预升级波头强度**。**T 组设计 = R + 升级门 76→79**（主体循环段回落 cyclic 弱波头），归档 `rulecal_20261016/T_gate79`（运行中）。判读已写 DIAGNOSTICS「S 组结果与判读」。同日 **T 组评估完成判读**（= R + 升级门 76→79，2374.4/62.51/2235/44.4、head<40=0）——**负结果**：峰值 +30%、viol +136%（门上移制动力不足 → 速度缓爬，新峰值 t=2394 @ v=73 + 尾部低速回潮 167 步）。**升级机制四象限（档 service/min × 门 76/79）扫完：gate76+service（R=1823）为局部最优，该维度无空间**。**U 组设计 = R + `coupler_override=direction` 方向感知**（拉钩→release 泄力、压钩→min 保留保护；依据 = R 超线 85% 在 ruleA 且压钩格=0，现行 min_brake 对拉钩反效果），归档 `rulecal_20261016/U_dir_release`（实现中）。判读已写 DIAGNOSTICS「T 组结果与判读」。同日实现 **U 组方向感知**（带符号断面力视图 + 双透传 + 规则 A 拉钩→release/压钩→min 分流，4 新单测、全量 pytest exit 0）并完成评估判读（= R + `coupler_override=direction`，2153.5/64.00/3323/44.3、head<40=0）——**负结果且比 R 差**：峰值 +18%、viol +251%、ruleA 312→469（release 钳零制动力突失 → 再制动循环正反馈，与 H 组教训同构），**"拉钩→泄力"假设被推翻，ruleA 干预方式维度（min_brake/release 两头）扫完**。**V 组设计 = R + `coupler_veto_margin` 0.9→0.75 收紧预测式 AB 源 veto**（事前禁止新波源，直对高速段 service 波头叠加，与已扫升级档/门/override 三维度正交；待查 train_env 透传链），归档 `rulecal_20261016/V_veto75`（实现中）。判读已写 DIAGNOSTICS「U 组结果与判读」。同日实现 **V 组 veto 三参数透传**（train_env `**_veto` 注入 + fleet `veto_cfg` + `test_veto_margin_wired_through_fleet`，57 项相关测试绿、全量 pytest exit 0），并行启动 **W 组 = R + veto_ratio 0.45**（反应路对照）。V/W 评估完成判读：**V 负结果且逐位等于 R**（透传验证生效但反应式门 0.6/900kN 永远先触发，预测式 margin 从未参与决策 → 死代码路径，margin 无空间）；**W 负结果且更差**（2511.5/63.73/4486，ratio 0.45 过激 → 该制未制时序混乱，超线格翻倍）→ **veto 双路均无空间**。R 峰值微观定案（probe 单步）：**6.5 s 内头尾速度反转 +4 km/h（尾先 81.4 冲、头 ED 即时减速）→ 断面 133 拉爆 1823**；根因 = **头/中机车 ED 即时（-365×2）与尾车 AB 波 6.5 s 延迟的固有时差矛盾**（EOT 只修缓解波）。**X 组设计 = ED-AB 波到达协同**（升级窗 ED 头中阶梯降权 `ed_upgrade_ramp_s/scale` 默认 0/1 零回归，尾波到齐后恢复满值），归档 `rulecal_20261016/X_edramp`。判读已写 DIAGNOSTICS「V/W 组结果与判读」。X 评估完成（标定 30 测试绿、全量 pytest exit 0）判读：**1777.5/63.89/1481/44.4（head<40=0），peak -45 微改善但 viol +57% 反弹**——ramp_scale=0.4 过狠致 ruleA 312→456（该制未制，与 W veto 0.45 同教训）；峰值形态不变 = top6 全是 v≈78-80 + cb=True + service 升级施加波（升级边沿窗治标，循环每周期重触发）。**Y 组并行两路设计**：Y1 = R + `coupler_veto_ratio` 0.6→0.8（ruleA 反应门 900→1000 kN 晚钳制，直对超线步 85% 在 ruleA 介入期；原拟升级门 76→79 与 T 组重复已撤）、Y2 = R + ramp 轻化 scale 0.7/窗 6.0（修 viol 反弹），归档 `Y1_gate08`/`Y2_ramp07`（并行运行中）。判读已写 DIAGNOSTICS「X 组结果与判读」。Y1/Y2 评估完成判读：**Y1 负结果逐位=R**（veto_ratio 上调零效果 → ruleA 晚钳制假设作废，veto 维度 V/W/Y1 三路全关）；**Y2 = 关键正向**（1815.6/63.44/**339**/44.2，viol -64%、ruleA 171、超线格 2936 四项全轮最佳，ramp 0.7 剂量确认）。峰值未吃到红利的机理 = **ramp 窗只在升级门边沿触发一次、门不退出不重武装**，高速段六个峰值施加波全在窗外跑满 ED。**Z 组设计 = ramp 改施加沿重武装**（`_cyclic_braking` False→True 边沿即重启动窗，每次施加波覆盖 ED 降权，参数沿用 Y2 的 6.0/0.7），归档 `rulecal_20261016/Z_apply_edge`（实现中）。判读已写 DIAGNOSTICS「Y1/Y2 组结果与判读」。Z 评估完成（全量 pytest exit 0）判读：**负结果**（1932.9/63.96/1234/44.2，均与 R 逐位同 → 施加沿窗只盖轻循环入场、对 service 重波无覆盖且入场降权多冲 117 kN）→ **ramp 触发时机两路扫定：保门沿（Y2）、弃施加沿（Z）**。Y2 service 占比探针定案：**超线 743 步中 581（78%）落 service 施加段、v≥76 全在 cb 内**，缺口定量 = Y2 峰值段 9s > ramp 窗 6.0s < 波到齐 7.5s（拖尾峰在窗外）；旧记录排雷 S/T/U 均负（升级档/门位/ruleA 三维度死）。**AA/AB 并行启动**：AA = Y2 + ramp 窗 6.0→8.0（盖满波传播期，`AA_ramp80`）、AB = Y2 + scale 0.7→0.6（强度轴中间档，`AB_scale60`），归档均已运行。判读已写 DIAGNOSTICS「Z 组结果与判读」。AA/AB 评估完成判读：**AA 负**（1964.6/757，窗 8.0 峰末仍在窗末拖尾出、超线步不变 → "窗盖不满"非主因）、**AB 负最差**（2615.6/2951，scale 0.6 该制未制第三次教训）→ **ramp 二维（窗×强度）四象限扫定：6.0/0.7=Y2 局部最优，该轴关闭**。断面探针定案**剩余峰值根因 = 同步双源制动波在中机车(109)后方 110-151 断面对撞**（三段区域均值 1302-1388 vs 其余 658-930，峰值时头源+中源同时 service）。**AC 组启动 = Y2 + `sync_loco_brake=false`**（单源零代码对照，`AC_single_source` 运行中）；**AD 组（中源延时）已实现**：`TrainDynamics(mid_source_delay_s)` 默认 0.0 零回归 + 子步真实时钟倒计时 + 缓解/episode 清队 + 已激活防重复入队 + train_env/fleet 双透传 + 5 新单测（含 fleet 接线），制动传播 7 项绿，候选 4.0s，归档 `AD_middelay40`（回归绿后已启动）。AC=负结果（1932.9/1234 vs Y2 1815.6/339，去双源 viol +264%，断面仍集中 110-151 同区）→ **双源对撞假设推翻、双源保留**，判据移交 AD（中源延时 4.0s 错峰，运行中）；AE 候选 = 升档门下调（76→74 更早 service 兜底，S/T 负向趋势指向"更早更强 service"），与 AD 并行归档 `AE_gate74`。AD/AE 判读完成均**负结果**：AD 2249.6/3387（中源延时造成中机车后方无制动空窗，ruleA 暴涨 10 倍；AC 单源+AD 延时双负 → **双源 0 延时局部最优、中源时序轴关闭**）、AE 2023.7/1889（门 74 更早 service 被否证；门 74/76/79 三点扫定 **76 甜点、门位轴关闭**）。全局最佳仍 Y2（1815.6/63.44/339/44.2，2 PASS）。**AF/AG 并行启动 = Y2 口径表3 速度门轴（未扫）**：AF 触发门 65→60（`AF_trigger60`，超线步速中位 78.8 直接靶点）、AG 缓解门 50→55（`AG_release55`）。判读已写 DIAGNOSTICS「AC 组」「AD/AE 组 结果与判读」。ADR-037 与开训交付待达标（P3）。无提交推送。

### [P0] 当前双人职责、接口与联合验收核对 - 2026-10-14

- **状态**：文档/代码核对完成；执行清单已整理。分工来源为用户聊天截图和2026-10-12分工节；共享接口的最终单点owner尚需双方确认，不代表队友已确认新接口或新参数。
- **归属**：P0；Methods与联合验证。后续新增执行记录在本节之后追加。
- **审计依据**：本地xmc-dev a3640af；origin/develop 50896db；origin/ckb-dev f75fb72。读取远程计划与ADR-035，仅fetch，没有合并队友代码。当前xmc-dev主YAML仍10kt_1plus1；队友ckb-dev已改20kt_1plus108_1plus108。两万吨诊断一直显式覆盖编组，不能据此认定两侧主训练配置已同步。

**结论及历史阅读边界**

- 双人按模块并行、单列先调试再尽早联合，合理。分工不等于两套独立RL同时操纵同一机车。正式架构仍遵循RESEARCH_POSITIONING §1.3/§1.7与ADR-013：唯一formation-aware机车级ED/AB调制 + 确定性规则/安全执行；调车钩指通过ED/AB改变纵向力，不是输出车钩力数值或修改物理参数获得成绩。
- 本文旧4.2.5–4.2.8附近“两层RL/第1层checkpoint→第2层训练”条目仅历史，已被ADR-013覆盖。旧2026-10-08计划中NMPC主表、53km口径分别受ADR-034及49.6km剖面更新覆盖，不作为下一步任务。不得删除失败历史或把早期达标数当当前两万吨验收。
- 本地研究定位顶部仍含万吨历史口径，远程ckb-dev ADR-035已更新研究对象；应先由队友将正式编组更新合入develop，再以共享合并版本冻结主训练。审计不会单方面更改立论或直接合并ckb-dev。
- 2026-10-12分工表的控制器路径src/multi_loco_controller.py已不正确，实际为src/controllers/multi_loco_controller.py。decompose实际obs_dim=12；3列、每列2机车共6 agents；动作shape=(6,2)，每机车ED/AB调制，非逐车厢或列车级第二套RL。旧总览11维/每列一个agent不作为接口规格。

**职责清单（用姓名标识代替“我/队友”）**

|负责人|工作范围|边界与交付|
|---|---|---|
|xmc（编队侧）|train_fleet_env.py编队上下文、动态列距、相对速度、速度协调、formation/独立上下文对照|交付列距误差、速度一致性、速度带和ATP介入指标；保留每列车钩指标，不另训练一个直接覆盖机车动作的编队RL|
|ckb（列内/物理侧）|train_dynamics的车钩/制动模型、单列机车分配、车钩约束与相关奖励设计|交付模型参数依据、单列原生契约、断面力peak/viol；单列训练是诊断/热启动候选，不能直接代替多列联合结果|
|共享热点：发起方登记，双方确认单点owner|train_env.py执行映射、multi_loco_controller.py规则/门控、safety_layer.py、experiment YAML、组合reward、evaluate_decompose.py|xmc此前已保留的空气执行修复需ckb联合审查；不因模块名或既有改动记录自动赋予后续全部修改权限。主评估出口仍evaluate_decompose.py|

**共同前置问题与建议分工（尚非双方已确认的新owner协议）**

|问题|建议主责|协作/完成判据|
|---|---|---|
|普通50kPa与SERVICE140kPa|ckb核对力/压力模型；xmc核对控制链实参传递|先明确机车/货车、分车传播、保持/缓解和连续减压接口。普通指令不可用全列50kPa覆盖削弱ATP SERVICE/EMERGENCY；原生升级、保持、reset契约通过|
|分段限速与公里标|xmc整理位置适配；共享安全接口需ckb审查|K15.9重基0，总49.6km；当前车辆区间限速与前方减速目标、gap目标同时保留，单位正确。当前实现仅D盘冻结decompose候选，未正式全入口落地|
|K40/K42缓解文字差异|共同查原始操纵图/表|表格只给参考窗口，不到公里标就强制放闸；50秒ED保持、33km/h缓解条件不得直接当通用参数。未核实的条件标未知|
|安全接管与监督能力|ckb核对模型能力、建立/衰减；xmc核对目标和执行反馈|ETCS最终权限保留，普通车钩减权不解除EBI；名义曲线不能凭饱和静态查询称动态标定。前车急制动假设仍是已有待定缺口，不宣称已解决|
|版本与主配置同步|ckb将ADR-035更新交付develop；xmc随后合并共同审查|同commit、同物理源码哈希、同编组/线路/阈值，确认后再启动正式训练|

**接口冻结（以代码实参为准，不复制过时概念）**

- 研究编组20kt_1plus108_1plus108，218辆、机车索引[0,109]，实际21976t/列；多列无机械钩挂，车钩指标在列内计算。
- decompose=loco_ed_ab，obs_dim12、num_agents6、动作6×2；一个策略的不同输入/奖励模块可以分开开发，最终联合训练/评估。任何维数、动作语义或主表JSON键改动须双方共同更新接口/metadata与全仓调用者。
- 动作层次区分：RL调制→规则请求→安全处理→实际ED/空气输入→压力/速度/断面力。executed_actions在当前fleet info是控制请求，不能替代实际执行数据；actual_loco_ed及诊断ab_command_to_physics用于核对安全后输入。
- 主表数据出口evaluate_decompose.py；diagnose_low_level_control.py仅故障诊断，不输出论文主表验收。请求切换、stored notch、制动段号不等于完整缓解并充风的循环次数。

**执行步骤清单**

1. P0共同对齐：上述编组/限速/减压/接管接口登记与原生契约；共享版本到位前可读代码、做局部诊断，不启动终局训练。
2. P0列内基线（ckb）：同模型做单列正常制动/缓解/再充风、升级、跨episode验证，提交参数来源与实际动作/压力轨迹。单列达标不能推出多列达标。
3. P1编队模块（xmc，可并行）：先维护同策略的前列位置/速度、间距误差与编队上下文接口；补正常/前列减速/限速变化的原生测试，验证没有追赶与制动反向交权。此阶段不单方面改动作维数或物理。
4. P1尽早联合：同共同版本3列固定规则/零RL调制跑通，分离列内问题与群组交权；再联合训练同一formation-aware策略。单列权重若热启动需明确网络维度/上下文/训练分布，不直接拼接两个checkpoint。
5. P1验证协同：formation与独立上下文同算法/物理/安全/参数，按既有ADR设置种子和实验规模；同时报告列距、速度、车钩与效率，不只看reward。
6. P2正式验收：短窗口只验证链路，49.6km整线单独评估；全量测试、共享metadata及完整主表检查通过后，才能按主计划进入终局训练/论文结论。

**联合完成判据**

- 正确性：全量测试 + 2回合原生冒烟 + AGENTS引用/outputs布局检查；当前全量测试仍在D盘重跑，尚未报告最终通过。
- 同源性：两侧同提交、实际源码哈希、编组、线路/起点、初速/间距、seed、动作与安全参数；不同物理档案不得拼表。
- 安全：整线断面力peak≤1000kN、viol=0，真实列距始终>0、物理穿透计数0；超速依实际分段限速统计，不用统一80km/h遮蔽70/75区间。达不到即未验收，不因安全层名义启用称硬保证已实现。
- 控制质量：速度一致性与列距误差相对同工况基线改善，同时检查jerk、旅行时间、速度带内占比和ATP介入；不能以长期拖慢跟随列/扩大列距换取单项车钩峰下降。各指标阈值/主张按既有ADR执行，未约定的编队误差容差不虚构。
- 证据：原始轨迹、结果、完整metadata与源码快照归档；失败候选保留“未采用”。入口outputs/sim_validation/phys_validation/controller_repair_20261014/README.md。

**下一项xmc实际任务**：先与ckb统一普通减压/强制动接口，再把已核对的分段限速和编队上下文接入正式共享控制路径，并做单列/三列同工况对照。当前不能继续把未校准的全常用制动与表中50kPa操纵策略混用。此处是执行顺序修正，不推翻单套RL或既有研究立论。

### [P0] xmc编队信息链检查 - 2026-10-15

- 用户确认可固定既有制动模型先推进编队。本轮限定train_fleet_env.py只读诊断接口及原生测试，不改obs/action维数、奖励、物理或50/140kPa。先补三列位置信息/间距/前列头尾速度/闭合速度的只读快照与step info，核对观测和安全目标。develop仍50896db，队友两万吨更新仍在ckb-dev，不擅自合并对方分支。上一轮全量测试会话已失效、最终结果不可核实，状态改为未确认，不能继续称仍在运行或已通过。

- 编队信息检查结果：新增get_formation_context只读快照及decompose step info['formation_context']，含头尾位置/速度、真实间距与误差、车头相对速度及前列尾车闭合速度，leader无前列字段用None；不进12维actor观测、不改奖励或动作。六项原生两万吨契约及fleet_decompose/low_level_command_continuity相关回归通过（3文件，非全仓）。external_archive/formation_context_20261015保存a3640af改前与当前5步三列同物理诊断，两侧所有NPZ数组完全一致，只验证接口不改变行为，非性能验收。
- 已确认可观测性缺口：仅把前列65→50km/h、位置/后列速度不变时，后列两agent当前12维观测完全相同；底层规则/ETCS目标可读取前列速度（本轮契约确认）。actor没有显式相对速度、不能据文档假定已接入，不据此断言RL无法学习。下一步需共同约定可选编队观测字段/schema与检查点兼容策略，再做保持同算法/物理的受控信息增量试验；本轮不擅自改obs_dim。用户已澄清50kPa映射不阻塞编队接口开发，仅阻塞对真实操纵/整线安全达标的最终评价。

### [P1] 可选相对速度观测扩展 - 2026-10-15

- 用户授权执行编队观测扩展及兼容性检查。xmc限定fleet观测、MAPPO输入维数校验、训练/评估schema透传和测试；新增formation_relative_speed_obs默认False，保留12维，开启14维追加车头相对速度和前列尾车闭合速度（m/s，leader为0）。不改物理/奖励/动作；旧权重不自动补零迁移。先原生观测/检查点契约，再两回合短冒烟；不能将接口就绪称为性能改善。

- 本轮结果：默认12维、开启14维（追加head_relative_speed_mps与tail_closing_speed_mps，leader0），固定同动作时前12维/轨迹/reward不变。检查点保存model_signature并拒绝维数不符（含weights_only与旧无签名权重）；训练元数据保存observation_schema，评估按检查点恢复开关及编组，显式冲突拒绝。主YAML/物理/奖励/动作未改。四文件特征/协议/编队回归、两文件续训/控制回归通过（CUDA专用跳过）；规范检查通过，非全仓。两万吨3列两回合×20步、小batch冒烟完成真实2次更新，保存14维模型实测重新加载推理obs6×14/动作6×2；只证明链路，不宣称效果改善。external_archive/formation_obs14_20261015/可选编队观测与模型兼容性复核.md及compatibility_result.json含来源哈希/工作区补丁。未提交推送；下一步共享版本后12/14维同物理同预算受控训练对照。

### [P1] 12/14维编队观测受控短训练 - 2026-10-15

- 用户授权继续。协议：固定当前物理/奖励/动作，3列21976t，49.6km剖面，seed0/1/2；各组10回合×100步，decision_interval10、n_env1、初速65、按相同seed起点随机化；BC1回合/1epoch，注意现有BC入口固定最多1500步，不把它误写100步。batch8、PPO epochs2、无整线选优，仅短训练稳定性检查。变量为formation_relative_speed_obs默认False/True（网络输入12/14也随之改变，无法保持参数数目完全相同）。同算法同预算，3对seed结果不当论文显著性。运行依赖代码冻结，数据/日志/完整命令/源码哈希保存D盘独立目录，后续只追加文档。

- 12/14维短训练结果：6个模型全成功、各10回合，最终checkpoint评价；正常10秒种子均值列距MAE1.249→0.534m、速度离散度0.0829→0.0613km/h、各模型峰值均值898.027→565.255kN，但14维仍有种子1096.632kN超限，未全面优于规则。额外200m列距及前60/后65kmh压力30秒：MAE190.292→192.767m（3种子均恶化）、速度离散度2.655→2.006km/h、峰值均值1391.835→1452.353kN、ATP列时步292.667→138.333，取舍明显，14维继续可选/不改默认。6模型及两类评价全完成，运行闭包哈希未变；训练配置逐对仅开关和目录差异。原始轨迹、模型、metadata、命令、快照及报告external_archive/formation_obs_ablation_20261015/编队观测短训练对照复核.md。此为10秒RL窗口小预算，不宣称收益显著、整线或循环安全达标；uniform80协议不代表分段限速复现。下一步成对训练初态覆盖速度/列距偏差与延迟过程，再受控比较，不改物理/奖励。

### [P1] 可选编队初态采样与安全状态核对 - 2026-10-15

- 用户授权继续；xmc限定fleet reset与trainer种子透传、原生测试。新增formation_start_randomization默认关闭，训练态可显式采样各列速度偏差与各车对列距偏差，独立RNG保证12/14组同种子同序列；eval_mode关闭随机化。范围必须显式说明是自研训练采样、不是实测运营扰动，不改主配置或研究主张。拒绝重叠/负速/超配置上限范围；记录初态SBI/EBI条件，不把正列距等同安全初态。本轮先接口/分布诊断，不直接再次长训。

- 初态采样结果：默认关闭，eval不随机化；可选require_clear_sbi有界拒绝采样且不改安全阈值。未筛选100组的200个跟随列状态中88超过SBI、82超过EBI；筛选100组成对12/14初态完全一致，200接受状态均未超过当前SBI/EBI，424候选拒绝324组（其中304亦超EBI，计数重叠）。这是条件分布，不是均匀运营分布或安全能力标定。官方2回合×20步冒烟完成，初态记录尝试3/7次，seed5正确继承；五文件相关回归、引用/布局检查通过，非全仓。报告external_archive/formation_initialization_clear_20261015/编队初态采样与监督筛选复核.md，含原始数据/模型/源码哈希；未提交推送。下一步固定物理与成对初态，确定覆盖制动响应的训练窗口再对照，不将链路通过称性能改善。

### [P1] 120秒编队窗口配对试跑 - 2026-10-15

- 用户授权继续；保持物理/奖励/安全/主YAML不变，独立D盘配置，12/14维seed0各2回合×1200步，DI10、batch8、epochs2、n_env1、无BC（只测扩展窗口与采样链路，不与旧含BC试验归因比较），训练启用相同初态采样及clear-SBI筛选；120秒为既有ADR-017上限，不拉长到222秒。固定评价独立复用相同起点和工况；属于小预算可行性检查，不是正式效果或整线验收。运行期间冻结源码依赖闭包，原始记录保存external_archive/formation_window120_20261015。

- 120秒试跑已完成：两组各2回合及6项固定30秒评价全退出0，两回合初态完全一致、80个依赖哈希未变。未达到预期，不采用：正常规则列距MAE0.118m/峰371kN，12维5.390m/1898kN、14维5.395m/1898kN；压力规则1193kN、12维1453kN、14维1846kN，均存在不同程度超限。无BC、预算仅2回合，不与旧含BC试验作窗口/观测因果归因。下一步先检查冷启动动作相对规则零调制的偏差，再同BC/同预算对照；暂不扩大长训或改安全阈值。完整报告external_archive/formation_window120_20261015/120秒窗口配对试跑复核.md。未提交推送。

### [P1] 冷启动动作与BC初速度传参诊断 - 2026-10-15

- 用户授权继续。范围：先只读核对随机策略均值/方差与实际AB阈值；已发现decompose BC默认从env_cfg读取速度且回落80，训练主循环则读取顶层init_speed_kmh（本次65），叠加初态±5导致BC初始化越界。限定修复trainer中BC初速缺省回落至cfg.init_speed_kmh，保留显式env_cfg值兼容；补原生调用测试，不改物理/动作阈值/策略初始化或主YAML。

- 冷启动100组成对初态推理诊断：12维mean|a|0.476、平均std1.129，14维0.487/std1.602；高斯AB<-0.15概率均值49.2%/52.5%，两回合后49.5%/56.2%，只是请求侧概率、非实际新增源比例。原生BC传参测试及初态回归通过。下一项仅14维执行1回合BC/30epoch+1回合20步RL，记录BC前后同100初态输出，确认热启动是否有效；统一TrainRunner metadata路径，D盘独立产物，不作12/14性能归因。

- 原BC实现1回合1500步/30epoch诊断完成（9000条机车观测）：同100初态mean|a|0.487→0.418、std1.602→1.018，AB新增请求侧概率52.5%→56.8%，不代表实际执行率；BC初速65已生效。发现函数lr=0.001未使用，实际复用RL optimizer的0.00002。扩展限定修复fleet_spec BC独立policy Adam并使用lr，不更改RL学习率/优化器状态；原生契约后同配置复核，非效果验收。

- 热启动修复复核完成：同14维/seed0/1500步9000观测/30epoch，拟合前探针完全一致；BC后mean|a|原0.418→修复0.0525、平均std1.018→0.1396，随机AB新增请求侧概率56.8%→11.8%（非实际执行率）。独立BC optimizer遵从lr且不污染RL学习率/矩估计，原生初速/学习率、采样、检查点/续训回归通过（CPU不适用跳过），规范检查通过。20步链路成功但DI10仅2样本<batch8未更新，不称PPO训练成功。源码冻结核验通过，报告external_archive/bc_effect_fixed_20261015/热启动初速与学习率修复复核.md。控制效果仍待同BC/足够预算120秒配对复测；未提交推送。

### [P1] 修复BC后的120秒成对训练复测 - 2026-10-15

- 用户授权继续。固定当前物理/奖励/安全/主YAML，12/14维seed0各BC1回合1500步/30epoch后RL2回合×1200步；DI10、batch8、epochs2、n_env1，初态采样与clear-SBI相同。选最终ep2模型，正常及压力各30秒固定评价并与规则对照；旧冷启动仅作整套热启动设置对照，不归因于单个BC修复或观测维数。非整线验收/统计结论，运行源码冻结。启动器external_archive/run_formation_window120_bc_20261015.py，数据external_archive/formation_window120_bc_20261015；两模型并行预计约10-20分钟，以实际日志为准。

- 本轮评价追踪补正（独立D盘脚本，不改训练闭包）：旧actual_air仅记录step_vehicles_ed_ab的单源位置参数，存在ab_sources时不是完整空气指令，不能据旧标签推断没有SERVICE或统计完整循环。新档案另存稀疏actual_air_source_commands（车辆源索引，-1无本步指令/0缓解/1MIN/2SERVICE/3EMERGENCY）及raw rl_modulations，既有请求/实际ED/压力/断面力保留；评价脚本哈希进metadata。旧数值指标不因此改写，旧空气记录解释边界追加于此。

- 修复BC的配对复测完成：两模型各2次有效PPO更新，2训练+6评价全退出0，两回合初态逐项一致、80依赖哈希未变。正常30秒规则371kN/MAE0.118m，12维371kN/0.118m、14维234kN/1.295m，均0超限，相较旧冷启动正常1898kN有改善但14维列距仍差于规则。压力30秒规则1193kN、12维1205kN、14维1237kN，均未达标；14维速度离散度2.152优于规则2.317km/h、ATP218少于260，但MAE191.550劣于189.790m。120秒训练本身峰值12维3185/3389、14维2867/3339kN，不得用正常30秒掩盖。暂停扩大训练预算，下一步冻结模型做同初态零RL/ED-only/AB-only/full请求→多源执行→压力→力时序归因。报告external_archive/formation_window120_bc_20261015/修复热启动后的120秒配对训练复测.md。未整线/联合验收，未提交推送。

### [P1] 固定14维权重的制动通道隔离 - 2026-10-15

- 用户授权继续；不再训练、不改物理/安全/主YAML，固定热启动复测最终ep2的14维模型和压力初态（前60/后65kmh、起点16000、额外列距200m）。四个30秒原生诊断：zero/ed_only/ab_only/full，只在策略输出后将隔离通道置0，零调制保留全部规则与ATP。四组全新同源记录，核对初态一致、full重放与旧档一致；保存规则基线、请求、实际多源/ED、压力、ETCS事件和断面力时序。external_archive/formation_channel_isolation_20261015，结果仅诊断，非主表算法消融或安全层关闭消融。

- 四组重跑完成且full与旧档全部NPZ字段逐项一致。零调制/AB-only物理轨迹完全一致，峰1204.594kN、首次超限22.5s；ED-only/full完全一致，峰1237.480kN、首次19.8s。此窗口AB调制未造成执行差异，新增变化来自ED及其引发的闭环接管时序，不据此断言空气物理无问题。基础零调制也失败。补一个冻结候选：已有controller.anticipate_etcs=True（当前fleet主入口未接入该开关），仅D盘脚本设置该属性，让规则参考当前SBI上限；与零/完整策略各同工况对照，阈值/安全权限/物理不改，不直接落主代码。首轮诊断脚本字段索引错误已留痕并分目录重跑。

- 2026-10-16复核完成：四组重跑+两项冻结SBI候选全退出0，初始上下文一致，full与旧档共同数组完全复现，源码/模型哈希未变。zero/AB-only峰1204.6kN/665超限、22.5s首次；ED-only/full峰1237.5kN/1090、19.8s首次，成对物理轨迹完全一致。zero SBI0.2s/EBI27.5s，full SBI0.8s/EBI24.8s，力超限先于首次EBI；本窗口增量来自ED闭环变化，不能推广AB无用或物理正确。提前参考SBI候选zero峰1327.7/5000超限、full1259.1/3000，虽ATP减少但更差，不采用、不落主入口。新zero与旧rule有v_max精度配置区别（22.222与80/3.6），不混用基线。首轮记录脚本错误留痕，正式项目行为代码本轮未改；下一步逐时核对基础追赶/常用接管/源保持缓解/压力传播，保留EBI与阈值。报告external_archive/formation_channel_isolation_20261015/通道隔离与SBI预控候选复核.md。未提交推送。

### [P1] 常用接管缓解抖动与保持候选 - 2026-10-16

- 用户授权继续。先复用前轮zero/full原始数据定位：第2列SERVICE→RELEASE反复隔0.1-0.3s，压力长期集中前部。独立D盘候选保留SBI/EBI阈值和物理：接管后保持实际空气级别，待车头速度明确低于当前SBI减既有AB_SUPPRESS_MARGIN_MPS=0.5m/s才允许普通缓解；保持期间禁止正牵引，紧急升级优先、不被普通请求降级。此0.5为已有控制余量复用的诊断候选，非新实车参数。仅zero/full各30秒先验，不直接改共享train_env或物理。数据external_archive/service_hold_diagnostic_20261016。

- 保持候选完成：zero_hold峰1709.7kN/5857超限、full_hold1782.7/5260，虽然ATP13/24明显减少，仍更差，不采用。追加同物理接口诊断：仅在常用接管时通过已有ab_sources从机车索引0/109发SERVICE，原140kPa档位不变、EBI仍原车头EMERGENCY最高优先；配合前述保持条件，zero/full各30秒。属于单列分配共享热点的冻结候选，需联合审查后才可落地，不改队友物理或主入口。

- 多源+保持候选完成：zero峰1310.0kN/full1725.2kN，仍未优于各自原基线，不采用。为分离源分配与保持两因素，再补原缓解逻辑下仅将常用接管分配到现有机车源0/109的zero/full各30秒；形成原/保持/多源/多源+保持对照，EBI与显式EMERGENCY请求不被替换。

- 2026-10-16完成：原zero/full车头SERVICE↔RELEASE次数68/67和63/62（多次0.1s，非循环数）。保持zero/full峰1709.7/1782.7kN；多源+保持1310.0/1725.2；仅多源1197.8/1218.3，原1204.6/1237.5。六候选新跑全退出0、八条初态一致、源码/模型哈希未变；所有EBI事件列时步核对实际EMERGENCY。候选均未1000kN达标，不落地主代码。瓶颈转为基础规则/接管的动态建立与安全曲线能力一致性，下一步单列固定动作响应及源位置/压力建立/释放核对；不扩训或改队友物理。报告external_archive/service_hold_diagnostic_20261016/常用接管抖动与源分配候选复核.md。未提交推送。

### 接手全部任务：合并与控制修复前置核对 - 2026-10-17

- 用户接手全部任务。xmc-dev 从 a3640af 快进合入 origin/develop 34f08ae；合并前本地 tracked/untracked 工作已保存在 stash `xmc-before-develop-merge-20261017`，恢复后保留该备份。进度冲突保留双方历史，评估编组冲突保留检查点 metadata 显式编组校验并采用两万吨默认编组。未推送。旧双人分工条目仅作历史。
- 针对制动传播、循环标定、BC初速度、编队上下文、观测schema和初态随机化共63项测试：首轮59通过、4项因D盘测试父目录缺失无法启动；创建父目录后相关两文件9项全通过，覆盖全部4项。diff检查通过，无未解决冲突；不代表全量测试或整线验收。测试临时目录 external_archive/merge_validation_20261017。
- 下一项：底层控制修复。优先解决Y2归档门沿ramp与当前Z施加沿ramp的复现语义差异，未改变控制行为、物理参数或安全阈值，尚未开始AF/AG或大规模训练。

### 底层控制修复：恢复Y2与跨回合清理-2026-10-17

- 已恢复Y2门沿渐变并修复reset状态残留，81项针对性测试通过；全量测试和Y2完整剖面复现运行中，未声称达标。读赵紫宁/Wang2026/张二田原文并做同源静态制动力预算；当前需核对循环次数衰减简化在本工况的依据，详见本月诊断同名小节与D盘报告。暂不扩大训练，不改车钩/衰减/阈值。

### 单因素对照纠偏与重新验证-2026-10-17

- AA至AE冻结源码均为Z施加沿版，不能作为Y2参数轴关闭证据；详见本月诊断“归档源码审计”。新增只读归档审计工具及4项回归通过。Y2完整复现和真正门沿8秒窗候选正在同模型下运行，等待结果后再决策AF/AG，期间不改行为代码。

### 修复拉压方向接口倒置-2026-10-17

- 真实两车变形证实raw断面力正压负拉，direction接口原按相反含义解释；已仅修复per_vehicle_signed映射并通过5项新增联动回归。旧“剩余纯拉钩/U方向策略无空间”结论待重审，详见本月诊断；min_brake两条冻结整线对照继续，不能当新方向策略效果。

### 时钟修复优先于继续调参-2026-10-17

- Y2已整线逐元素复现，真实门沿8秒窗负结果不采用。发现观测及MPC预演额外消耗ED保持/渐变计时，已改为独立副本，50秒保持不再变成约25秒。4项新增原生时钟契约与MPC预演回归通过，广泛401通过/1跳过；详见本月诊断。停止未完成的换算长评估，先跑观测时钟修复500秒新基线，之后再重标定，不直接沿用历史6/50秒配置的效果。
- 更新：新时钟500秒已完成，峰1462.18kN、均速58.18km/h，仍未达1350目标；10秒渐变候选40秒反而升至1500.12kN，不采用。电制动足够时不升级SERVICE的冻结候选同40秒峰降至1221.16kN、jerk RMS降约34.2%，仅短窗有效，生产控制器未采用。500秒扩展因D盘自动写入权限审核两次超时未启动，恢复权限后继续原协议；详见本月诊断“新时钟基线与电制动足够时升级门候选”。
- 执行通道更新：文档保存D盘的用户要求不扩大至所有机器实验数据。候选500秒同工况验证已正常启动，原始轨迹、源码快照及结果元数据遵循仓库产物规范保存至outputs/sim_validation/phys_validation/ed_sufficient_prefix5000_20261017_1544（F盘项目内）；不新建F盘报告文档。此前“未启动/等待D盘权限”状态由此条覆盖；等待完整数据后再判定，生产控制器仍未采用候选。
- 候选决策更新：简单ed_avail门控500秒负结果（峰1553.92kN/34断面时刻超限）不采用。第二个“整列净需求”升级筛选仅改强档升级门，500秒峰1234.06kN、jerk RMS较同窗基线降约15.3%、最低列均速49.74km/h、无超速或>1500计数；已启动带1350kN诊断早停的整线目标门验证，尚未验收。两候选均未放入生产控制器，详见本月诊断最新净需求条目。
- 最新：净需求升级候选在567.9s触1350目标早停，此前552s开始超速，未通过整线。时间线定位392.2s（缓解50s保持结束）ED约900kN直接归零，后续充风等待期控速不足。现验证“净需求升级+保持结束后既有力平衡ED前馈”，50s保持/222s充风/空气档位/安全阈值均不改；该冻结候选已越过前述失败点并通过车头约23km处，整线仍在运行，不宣称验收。论文依据及运行目录见本月诊断与REFERENCE_INDEX新增马志强等2023原文复核。
- 复现入口补修：冻结控制器重新实例化现保留其支持的配置开关，避免ED前馈等选项被默认值静默覆盖。原生3步冒烟确认源码defaultFalse而配置True时实际runtimeTrue；比较工具补查controller_runtime，归档回归6项通过。当前在跑候选启动时runtime已按冻结源码defaultTrue+配置True对齐，未受后来入口修补影响，diagnostic_source.py保存启动版本。
- **固定起点单列P2完成**：net_demand_release_ff_route_gate_20261017_1606完整29547步，峰1321.486≤1350kN、均速60.3917≥60km/h、最低列均速45.2546≥40、viol=0、运行中超速步0，尾部46966.016m达既定终止点。整列净需求升级筛选已落入正式控制器，单列标定YAML显式采用通过配方。新旧Y2整体对比及效率代价见HANDOFF §9与repair_comparison.json；不作为单参数收益或MARL收益。
- **当前暂停扩大训练的技术瓶颈**：原生训练随机reset会生成“坡中、满限速、空气制动尚未建立”的初态；20km精确限速冷启动已实测0.1s超速、13.3s触目标线。满两机车ED初始仍有0.03450m/s²净加速，需先处理可行初速度/完整历史状态初始化，再接线三列并联合验收；不改安全阈值、不删除初始超速统计。formation YAML未同步单列配方，未开启长训。用户现承担全部任务，旧分工仅留历史。
- 最后复测：诊断归档/可比性/观测时钟/净需求与保持接续23项通过（controller_final_contracts_20261017_1653/results.xml）。入口对显式配置的FF/prelimit正确继承，对未显式配置的其他实验参数仍保留冻结源码默认值；不把“全部继承当前默认值”当成归档复现。广泛回归的最终统计另记本月诊断。

### 随机冷初态修复-2026-10-17

- 完成已有三篇原文的初速/空气建立/缓解接续核对，无新MIS检索。20km起点70/65/60km/h各200s均无超速，峰1276.603/1327.692/1312.571kN；70km/h另10km/40km各120s均通过。完整状态接续与逐车匹配位置速度的冷重置也各120s通过，不支持热启动一定更优。原始轨迹/源码/metadata在outputs/sim_validation/phys_validation/initialization_*20261017_review。
- 单列标定配置启用显式训练cold_start_max_speed_kmh=70，仅随机化训练reset生效并记录请求/实际速度，固定起点评估仍80km/h。31项相关回归通过；既有1321.486kN整线结果仍有效，但不是本轮新初态整线成绩。详见HANDOFF_2026-10-17.md §10和D盘随机初态复核报告。
- 待办改为坡段边界/种子覆盖→三列参数对接及联合验收→新分布重采BC和短训；未开长训，不声称全随机起点已获安全保证。

### 随机初态边界复验与实际瓶颈-2026-10-17

- 70km/h预登记6边界+3种子120s测试7/9通过；25.0135/26.6335km失败。继续同轨迹至1500诊断早停，分别70.9s/1507.894kN、12.4s/1539.288kN，各1个>1500断面时刻计数，无超速。1350早停前逐元素一致；不是调整控制器安全阈值。
- 继续降速、ED恢复斜率、静态两半列分配、从上游真实运行形成状态后接续，均未消除两个目标反例；候选不采用。静态分配额外长前缀已取消并标无有效结果。
- 修复显式reset seed的路线采样复现；增加真实到达指定位置的预运行诊断，预算不足拒绝。33项相关回归通过。固定起点1321.486kN结果范围不变，三列仅30s接入检查且仍有128安全事件，未联合验收/开训。
- 当前瓶颈改为连续变坡动态制动协调；保留70冷启动上限但不称随机初态验收完成。详细证据见HANDOFF_2026-10-17.md §11、D盘随机初态边界复验报告和initialization_boundary_matrix_20261017_1723/matrix_summary.json。

### 预测协调试验与原文复核-2026-10-17

- 速度预看新增空气门、与静态分配组合、原生2s动作选优、4s平滑选优及按前段需求延后头源，均未解决25/26.6km目标反例，未替换生产控制器。原生2s版动作跳变更大，不采用；4s平滑只降低冲击，仍超目标。
- 局部正结果仅20km/70kmh同200s：均速63.122→68.181，峰约1277、无超速，jerk略升；不作为全局修复或MARL收益。
- 新增原生动作敏感性诊断及可复用预测事件留痕，隔离预测/真实状态，53项软件回归通过。原文Lu2025连续ED序列/终端/增量约束与10点模型已核对，信息卡旧误述修正；未抄车型/阈值，NMPC未恢复主表。
- 当前瓶颈更明确为未来可行的连续动作序列，而非单步动作或统一初速；详细见HANDOFF_2026-10-17.md §12和D盘预测制动协调报告，两个固定反例保留作后续验收。

### 分段电制动序列及接续验证-2026-10-17

- 生产控制器未替换、未训练或推送。新增原生诊断--sequence-grid/--ed-ramp-per-s；两个起点各81组、两段各3s，0/0.5/1双机车请求，0.5/s为工程试验斜率而非实车参数。
- 25.0135km/70kmh预看母候选运行35s完整状态：最佳[0,1]→[0.5,0.5]，6s峰1193.873kN，62/81组≤1350、78/81≤1500。26.6335km运行8s状态：最佳[1,0]→[0.5,0]，峰1421.825，0/81≤1350、11/81≤1500。有限网格不是连续优化，不能据此声称物理无解。
- 转缓坡最佳序列35—41s后平滑接回原规则，45.3s达到1353.168kN目标早停；保持第二段动作则完整120s峰1343.201、均速72.334kmh、最高车辆74.035，无超速/1500超限。前41s两运行逐元素一致。该定时诊断不能部署，且距离1350仅约6.8kN，尚无扰动和整线保证。
- 再入坡最佳序列续持仍14.7s/1504.820kN验收线早停，1个超限断面时刻，无超速；不是完整120s真峰。两个反例仍未联合闭合，不能称底层修复完成。
- 原生预测与真实执行6s窗峰值序列逐元素一致（0N差）、请求一致；相同第一段的9个后继分支前3s逐元素一致，指令斜率和空气保持检查通过。实际安全/气路未改；母控制器为空气预看冻结候选，不能冒充生产性能。
- 原始归档outputs/sim_validation/phys_validation/ed_sequence_{flat,reentry}_20261017_review及ed_sequence_flat_{continuation,hold}_20261017_review、ed_sequence_reentry_hold_20261017_review，含官方metadata/源码快照/原始NPZ/审计JSON。报告traffic_rl_project/docs/reports/controller_takeover_20261017/分段制动序列及接续验证_20261017.md。
- 下一步：从定时分配提炼状态触发和退出/接续条件；再入坡研究更早介入及连续多段动作和未来可行性。未新读/新搜论文，未声称本轮有限网格为Lu2025 NMPC复现；未重跑上轮53项测试，使用原生仿真和逐元素一致性验证本轮诊断。

### 状态触发制动分配与相邻起点复验-2026-10-17

- 未替换生产控制器/启动训练/提交推送。冻结候选v3按两半列坡度差与正压缩位置触发（前0.7/后0.6倍1500、坡度差0.004），相对脉冲3秒、ED请求0.5/s及状态退出；全部是工程假设，非实车/文献参数。母控制器仍为空气预看冻结候选，不能冒充生产版本。
- 两原始反例同一v3完整120s：25.0135km峰1343.201kN，26.6335km峰1490.043kN，均无超速/1500超限。前者35.1s触发、109s状态退出；后者6.1s触发、24.1s退出。再入坡尚未达到1350余量目标。
- 冻结源码哈希、预登记四个±100m相邻起点后全部执行，未据结果再调v3：24.9135km在43.4s/1516.238kN、25.1135km40.7s/1512.967、26.5335km13.9s/1524.825均1500早停；26.7335km完整120s/1499.893。四个未调参相邻工况仅1个守1500，且余量约0.107kN。原始局部成功不能推广；早停值不是完整窗口真峰，未做整线/三列验收。
- 原始失败首启是grade_profile字段名错误，在首步物理推进前失败；run_status明确无有效数值，独立v2修正_grade_profile后重跑。v2转缓坡32.9s介入、44.8s/1350.717余量早停，未声称越1500。v3提高前段触发后通过原点，但相邻位置仍失败。
- 原始归档state_section_ed_{flat,reentry}_v3_20261017_review及四个state_section_*100_v3_20261017_review；state_section_holdouts_plan_20261017_review保存plan/matrix_summary/consistency_audit。六案例规范化源码哈希一致、预登记原始文件哈希一致；原再入坡v2/v3轨迹/请求逐元素相同，转缓坡干预前350步与母候选一致。未重跑旧53项测试，不计作本轮通过数。
- 重读Zhang2026_JAS_CouplerCompensation.txt原文摘要/§II式(1)—(4)，其ECP逐车独立制动前提不适用于本项目两机车常规气路；本地仅部分正文，不称全篇复现或导入控制公式。现阶段应固定反例、加入逐钩变化/邻车速差/加载历史的动态预测与连续接续验证，不再为单个位置调阈值。未新搜论文/登录MIS。
- 完整报告traffic_rl_project/docs/reports/controller_takeover_20261017/状态触发分配与相邻起点验证_20261017.md。没有相邻工况母候选完整配对，因此不主张候选相对生产整体变好/变差；明确结论是候选稳健性验收失败。

### 因果车钩趋势预警审计-2026-10-17

- 新增src/evaluation/audit_coupler_warning.py与tests/test_coupler_warning_audit.py，只读8份既有原生轨迹，未重新仿真、改生产控制器/物理/训练配置或推送；本轮无新的车钩力改善成绩。
- 对1350/1500kN、1/2/3秒时域，比较当前力、0.5秒变化率、加载方向邻车速度门、再加1秒因果均值滤波。相邻速度与符号门不冒充动态模型，所有滤波/时域只是信号处理试验设定。
- 1500kN/2秒：已验收固定起点整线轨迹的原趋势+速度门误报率99.84%，滤波后66.67%；安全120秒原转缓坡/原再入坡滤波误报71.40%/49.28%。三个失败相邻起点虽覆盖20个已知未来正样本，但滤波精确率仅6.29%/6.08%/15.27%；不能把大量持续报警下的2秒提前量当有效突破。该简易预警未接入控制器。
- v1仅完整未来窗；v2保留不完整未来中已观察到超限的已知正样本、排除未知负尾部；v3新增滤波，最终以v3为准。三个目录独立留存不覆盖。最终4项边界测试通过（末帧越线、未知尾部、因果输入、双符号加载方向）。8份原始NPZ与冻结源哈希、时间步均匀性已核对，原始档案只读。
- 原始归档outputs/sim_validation/phys_validation/coupler_causal_warning_audit_v3_20261017_review含完整metadata、逐案例来源、所有设置结果、summary/integrity_audit。报告traffic_rl_project/docs/reports/controller_takeover_20261017/车钩趋势预警有效性核对_20261017.md。
- 当前待办转为验证可预测不同ED动作响应的动态模型及连续接续；不再将线性趋势线当安全边界或为单点反复调门。误报不能证明物理错误、所有预测无效或控制无解；本轮未新搜/新读论文、未导入外部参数。

### 动作响应预测核对-2026-10-17

已验证动作插值与逐车状态插值的精度限制，均未推广。24.9135km定时诊断完整120s峰1266.293kN；26.5335km仍14.3s/1511.695早停。原生数据和误差审计见docs/HANDOFF_2026-10-17.md末节；完整报告traffic_rl_project/docs/reports/controller_takeover_20261017/制动动作响应预测与续跑验证_20261017.md。生产版本不变，后续须保留非线性耦合并验证窗口终点接续；局部定时试验不是通用修复。

### 长窗口接续与按需ED-2026-10-17

原生41条分支定位提前介入价值。按需ED冻结候选在三个相邻再入坡120s峰1404.506/1298.402/1263.969kN，无超速/1500超限；转缓坡76.1s/1511.059仍失败。未替换生产/接训练，详见docs/HANDOFF_2026-10-17.md末节及traffic_rl_project/docs/reports/controller_takeover_20261017/长窗口接续与按需电制动验证_20261017.md；索引three_stage_native_plan_20261017_review/round_summary.json。

### 2026-10-17 万吨1+108底层规则首轮验证：未通过1000kN，已定位AB准入冲突

- 7组原生部分线路试验已归档，工况10988t/列、49.6km线路、80km/h初速、1000kN验收。单列原配置180s峰1009.426kN，继承旧修复规则180s峰977.921kN；原生ED反算候选600s峰1047.694kN、车辆最高80.685km/h（未通过）。三列120s峰991.745kN仅为短测，尾列在负里程延伸段，不代表编队全程通过。
- 候选反算及0.5/s恢复限制、实际ED能力门控等均未解决超限。失败改动保留opt-in（ed_native_force_conversion），默认false；旧双机车行为保留，主配置不推广失败候选。
- 350–469.6s车钩力692.531–937.996kN，持续超过新AB源0.6倍门限（600kN），无法及时新增AB。1000kN指标保持，不关闭保护、不凭空缩短222s充风。后续需有依据的提前AB时序与ED匹配。
- 已核对本地Zhang2024/张二田和期刊官网胡杨2017、马志强2023。222s来自两万吨实测，1+0充风函数未核准。电脑操作工具因无法可靠识别Edge网址而终止，未用MIS取得新全文。
- 详细报告：traffic_rl_project/docs/reports/controller_takeover_20261017/万吨108节底层控制首轮验证与瓶颈_20261017.md。原始索引：outputs/sim_validation/phys_validation/single_10kt108_native_ed_20261017_review/comparison_round.json。当前停在明确控制瓶颈，未启动长训、未提交推送。

### 2026-10-18 万吨108节首次超限分解：局部方向有效，闭环切换仍失败

- 原生重建170s，位置/速度/断面力与昨日冻结归档误差0；保持AB的20s ED分支：撤ED894.940kN、保持939.436kN、满ED1213.616kN。开环敏感性不可当作闭环通过。
- 净需求限ED候选133.1s出现拉伸1030.583kN；加0.5/s主动减弱限制后133.6s仍拉伸1010.163kN。均按1000kN早停，未完成计划250s。与原179.9s压缩峰值形成不同冲击，失败候选不推广。
- 生产规则/物理模型/AB准入/充风及安全门限未改。仅诊断工具支持单机车及序列维度，14项相关测试与渐变候选4项原生接口契约通过。
- 收窄瓶颈：整列净力与压力建立状态不足以选择ED切换时机；后续先验证保留气动/积分历史的短时拉压预测，再评估AB固定600kN准入门。不能通过解除保护或任意缩短充风解决。
- 报告traffic_rl_project/docs/reports/controller_takeover_20261017/万吨108节首次超限核查与闭环对照_20261018.md；原始索引outputs/sim_validation/phys_validation/single108_first_force_probes_20261018_review/。未提交推送。

### 2026-10-18 双相位动作筛选与有界ED：600秒车钩/限速通过，循环未验收

- 原生完整125/170s状态下，0.5与0.4目标动作均通过局部20s拉压筛选；撤ED在125s会拉伸超限而170s局部通过，说明动作不可跨状态直接推广。
- 两个有界净需求冻结候选均完成600秒，峰值954.755kN、车钩超限0、超速0；均速分别55.479/57.350km/h。原600秒失败候选峰1047.694kN，均速62.643且有超速，不是合格安全基线。
- 重要限制：两新候选没有AB缓解请求，未展示完整循环；只覆盖约9–10km，非49.6km全程或三列。工程ED下限及0.5/s均非论文车型参数，不推广默认控制，不直接训练。
- 详细结果与待办：traffic_rl_project/docs/reports/controller_takeover_20261017/万吨108节双相位筛选与有界ED闭环验证_20261018.md。原始汇总outputs/sim_validation/phys_validation/single108_two_phase_probes_20261018_review/closed_loop_comparison.json。后续在候选自己的运行历史验证分阶段ED，兼顾效率、拉压与AB循环；222s充风及1000kN门限不变。

### 2026-10-18 首次缓解衔接改善，再制动准入仍阻塞

隔离候选ED下限0.55在249.1s缓解但260.1s超限1007.081kN；追加缓解窗口ED恢复限速后，249.1—299.1s峰值983.266kN，无超速，四项接口检查通过。但完整重跑484.3s首次超速，493.9s车钩1009.542kN停止，尚未通过。222s充风及1000kN指标保留，生产控制器未改。下一步用候选自身完整历史审计充风结束后的AB准入/提前制动，勿直接删除600kN门槛。新文档见traffic_rl_project/docs/reports/controller_takeover_20261017/万吨108节缓解修复与再制动瓶颈_20261018.md；数据见outputs/sim_validation/phys_validation/single108_release_recovery_trial_20261018_review。只为单列零RL局部试验，不代表全线路/三列或正式训练通过。

### 2026-10-18 再制动门槛核实与充风平滑候选淘汰

前轮候选471.1—484.2s充风已就绪的132步均处循环状态，legacy ED可用度0.3936—0.4013，决策前车钩均>600kN，普通AB持续封源；只读核算见single108_release_recovery_trial_20261018_review/reapplication_gate_audit.json。将ED恢复限速延续整个AB关闭阶段的隔离候选虽通过6项接口契约，但469.3s已超速（距缓解220.2s，小于222s充风），480.6s峰值1012.379kN停止，淘汰，不推广。下一步需联合解决缓解充风速度可行性与普通再制动准入，勿直接删600kN门槛或缩短充风。报告traffic_rl_project/docs/reports/controller_takeover_20261017/万吨108节再制动门槛审计与充风平滑反证_20261018.md；本轮产物single108_refill_recovery_{source,trial}_20261018_review。生产控制器及1000kN指标不变。

### 2026-10-18 再制动同状态反事实与列尾设备语义更正

完整重放471.1s，与前轮位置/速度/断面力/压力/缓解比例/激活标志六项误差0。ED目标0.55的100s配对试验：无AB请求首次超速+10.1s、峰1080.396kN；复制环境仅放行新增50kPa请求的分支首次超速+12.3s、峰1107.447kN。两分支均有原生ATP，超速后可能升级，不能把后续峰值归因于50kPa本身；仅为开环反事实，不是安全验收，说明删除600kN门不足以解决该动作组合。50kPa分支首次超速时压力系数最小0.289/平均0.451，需联合充风和下次压力建立的速度余量规划。诊断工具显式旁路开关仅用于复制分支，19项相关测试通过。

原文核对：Zhang2025文件对应Mathematics2026,14,158（DOI10.3390/math14010158），§4.3为额外尾部充风装置，不等同普通可控列尾；雷美琳PDF31明确普通可控列尾不主动充风。更正train.py注释、VALIDATION_BASELINE、REFERENCE_INDEX、papers/README设备解释与出处，动力学行为/EOT开关不变。eot=True历史结果须声明附加尾部充风假设，不能当作普通列尾万吨108辆结果。报告traffic_rl_project/docs/reports/controller_takeover_20261017/万吨108节再制动反事实与列尾设备核对_20261018.md；原始输出single108_readmission_shadow_20261018_review，含完整元数据。1000kN及222s未改，未推广控制器、未训练、未推送。

### 2026-10-18 阶段控制与70km/h冷启动：前段改善，缓解仍未验收

旧80边界影子试验：0.55/0.70固定请求均失败；阶段增强0.05/s峰1178.687kN，0.005/s降至1037.856kN（260s无超速，3步超限），0.004/s延长400s峰1038.718kN、最高79.533km/h。均未通过，ED1.00矩阵分支会话结束未形成结果。不得把影子新增AB放行当作正式保护策略通过。

当前1+108两配置v_max由截断22.222修正为准确80/3.6；安全层达到上限即制动的比较符/容差不改。单修精度不会取消准确80起步的SERVICE；初期将首段全部归因舍入的判断已纠正。回归验证79.9996不因截断误判、80和80.001仍接管。旧22.222/80缓存不得混用于新配置或70冷启动。

新70冷启动闭环：默认84s峰1014.548kN，且没有AB；ED恢复0.5/s、scope=coupler使共同前84s峰972.370kN，jerk RMS 0.049342→0.025540，首次超限后移到173.7s（1014.348kN）。缓解前实际力作为保持目标候选176s峰1005.045kN；保持目标单次最终减权候选179.8s峰1016.908kN。所有候选未采用。目标588.157kN经保护后实际曾降至约1.8kN，名义恒力不等于实际恒力。下步针对154.8s缓解前后的受力相位、实际ED力及气动释放做预测协调，不能靠继续微调固定系数或放松1000kN。

诊断工具增加分段ED/AB、逐段斜率、实际物理命令及目标采集、可信本地完整原生检查点（非fleet/RL重启）；校验源码依赖/配置/运行版本/时间/SHA，禁止任意外部pickle。7项状态往返误差0，分支前50s逐项一致。相关104测试与规范检查通过。报告traffic_rl_project/docs/reports/controller_takeover_20261017/万吨108节阶段控制与70冷启动复核_20261018.md；round_summary.json位于outputs/sim_validation/phys_validation/single108_cold70_forcehold_once_trial_20261018_review。1000kN、222s、EOT既有附加尾部充风假设保留，未训练、未推广算法、未推送本轮产物。

### 2026-10-18 缓解幅值与保持退出：局部改善，再制动仍未通过

154.8s同状态六项误差0，30s原生影子ED请求0/0.25/0.5/0.75/1峰值分别982.540/848.415/929.657/1129.779/1179.812kN，非完整控制器验收。低幅值恒力候选取缓解前实际ED力25%，50s保持窗峰818.216kN；204.8s退出ED单步+0.719，208.9s峰1001.797kN停止。再对缓解后空气关闭阶段限制普通ED上升0.05/s，204.8—230s峰959.912kN，通过旧退出冲击点；但402.0s首次单车超速，413.1s峰1011.667kN停止，最高单车80.647km/h，仍未达标。两候选缓解前1547步七项轨迹/动作与参考完全一致；共同154.8—173.7s峰1014.348→818.216kN，不能以不同停止时长的全段RMS评价整体改善。

376.8—401.9s充风就绪252步均循环、无负AB请求，决策后峰值最低727.864kN；下一轮须逐步采集决策前门控输入，核对新增源准入与压力建立的速度余量，不删600kN门、不缩222s、不抬1000kN。马志强2023§3.3复核支持缓解恒力50s，25%及0.05/s是本地工程筛选参数，非论文车辆数据。EOT附加尾充风假设保留。37项相关测试及引用/布局检查通过。候选未晋升、未训练、未推送。

原始数据：outputs/sim_validation/phys_validation/single108_cold70_release_probe_20261018_round2、single108_cold70_release_forcequarter_{source,trial}_20261018_round2、single108_cold70_release_quarter_slew_{source,trial}_20261018_round2。报告：traffic_rl_project/docs/reports/controller_takeover_20261017/万吨108节缓解幅值与保持退出复核_20261018.md。

### 2026-10-18 再制动准入与压力建立：准入恢复，仍有压缩超限

参考70冷启动376.8—401.9s的252次决策前断面力727.864—903.112kN，全部超过600kN新增源准入门；用连续轨迹前一步原生断面力核实，不伪造压力/预测历史。诊断入口新增只读决策前峰值、否决、下一步充风时钟与AB开关记录，46项相关测试通过（Windows临时目录权限错误后在允许权限下重跑完成）。

提前20秒将ED请求暂限0.25的冻结候选，与前轮截至356.7s七项轨迹/动作完全一致；376.8s在222秒就绪、峰260.851kN/预测否决False时实际准入，但速度78.415km/h触发既有升级，投入SERVICE而非50kPa。396.5s峰1000.934kN压缩超限、最高单车79.698km/h、无超速。继续将0.05/s ED恢复限速延续压力建立期，与前候选截至375.8s七项完全一致，376.8s准入、385s即压缩1001.180kN，最高单车79.803km/h、无超速；不能认定更好。失败时109车已激活但压力均值0.279，属于建立过程。全局命令RELEASE与非空AB源并存时，源档位优先，不能误称未投入空气制动。

瓶颈已由准入推迟转为SERVICE压力建立与ED/列内速度差匹配。下一步须在候选自身完整原生状态上分阶段预测，兼查50km/h缓解—222秒充风—76km/h预升级的速度余量；不是直接降低600kN门、缩充风或抬1000kN。两候选未通过、不晋升默认；生产控制器未改、未训练、未推送。单列零RL、EOT额外尾充风假设保留，无整线/三列结论。20秒、0.25、0.05/s为本地工程试验值，非论文参数。

数据目录single108_cold70_readmission_{prepare,slew}_{source,trial}_20261018_round3；报告traffic_rl_project/docs/reports/controller_takeover_20261017/万吨108节再制动准入与压力建立复核_20261018.md。

### 2026-10-18 阶段ED延长验证：600秒局部通过，下一充风周期失败

376.8s完整原生状态六项与上一闭环误差0。SERVICE30s保持ED请求0/0.25/0.5/0.75/1的峰406.765/749.455/1019.828/972.618/1106.350kN；0.24/0.26峰766.473/791.120。0.75与相邻浮点数0.7500000000000001峰972.618/1007.722，同输入重复逐项一致，说明近门限结果敏感，不能选择偶然通过点；未经收敛研究不宣称模型错误。诊断普通分支补齐实际物理动作采集，无保护旁路。

冻结候选在首轮缓解后AB开启阶段限制普通ED请求至0.25，暂降低旧300kN运营下限、保留全部安全/充风门。与前轮截至375.8s七项完全一致；同376.8—396.5s窗口峰1000.934→790.084kN。前600s峰975.993kN、最高单车79.782km/h、无超速，仅局部通过。445.2s缓解后，654.7s已超速，普通充风仅209.5s，距222s差12.5s；664.8s峰1001.009kN停止，最高单车80.692、超速102列车步。全段最低均速47.750，不能称恒速或原速度带全程通过。新瓶颈为下一缓解充风的速度余量，不是直接放开600kN门；也未证明任何控制器都无法实现50/222组合。

公开检索核实林轩2017 HXD2周期制动（DOI10.3969/j.issn.0258-2724.2017.05.004，摘要100辆C80/50kPa/充风约束）、肖致明2023制动性能差异（DOI10.13890/j.issn.1000-128X.2023.01.004，摘要北大牛—原平南等效效率），两者全文待获取，已三处登记，不移植参数。TraeWork MIS实际检索指令在traffic_rl_project/docs/reports/controller_takeover_20261017/TraeWork_MIS再制动专项检索指令_20261018.md；本轮报告同目录万吨108节阶段ED与充风速度余量复核_20261018.md。46项回归通过，生产控制器/物理未改，未晋升、未训练、未推送。数据single108_service_build_{probe,robust_plan,robust_probe}_20261018_round4与single108_service_phase_cap_{source,trial}_20261018_round4。单列零RL/EOT额外尾部充风假设保留，无整线三列结论。

### 2026-10-18 新增全文核对与缓解前可行性方向

新增五份PDF已核实/提取，重点核对林轩中文PDF3式9、PDF4缓解速度上界，黄宇澄PDF34—35/42—43最低缓解速度与充风/转换点约束，董文三机116辆580kPa再充气判据。旧汇总未取得全文状态已过时；209.5秒是候选到超速窗口，不是充风完成时间，不能直接推断去掉尾充风后窗口变短。李文双机50辆C70E/初充气、肖文两万吨参数均不迁移。下一步构建缓解前可行性验证，评估缓解速度上下界及下一压力建立余量，而非只降50km/h或缩222s。现有全文足够方法验证；108辆同装置充风标定仍缺。来源三处登记、页图和报告在D盘，本轮未改生产控制/物理、未重跑。报告traffic_rl_project/docs/reports/controller_takeover_20261017/新增全文复核与缓解可行性修复依据_20261018.md。

### 2026-10-18 原生缓解预测：局部改善，下一周期候选受限

新增 `src/evaluation/release_feasibility.py` 与副本隔离/单列速度带一致性测试，52项回归通过。v3修正副本时域及动态领车速度带；首个预测2096点四项与历史实跑完全一致，旧偏差不归因于物理。42.661km/h缓解预测248.5s通过，峰936.830kN、最高79.864/最低平均40.422km/h；下一周期42.718仍超速，40.874则跌破现有下界。仅已筛选候选失败，不证明全局无可行解。瓶颈处停止，完整实跑未归档，12段预测NPZ和SHA已保存；不晋升、不训练、不推送。单列1+108/零RL/EOT额外尾充风，1000kN/222s/原速度边界不变；尚无全线三列验收。

数据 `single108_release_feasibility_{source,trial}_20261018_round5_v3`；D盘报告 `traffic_rl_project/docs/reports/controller_takeover_20261017/万吨108节原生缓解预测与可行性瓶颈复核_20261018.md`。后续先核对缓解可行区间、压力过程与ED接续及匹配编组充风依据；指令同目录 `TraeWork_缓解预测与数值收敛定向检索_20261018.md`。数值收敛为独立敏感性验证，不能替已知预测实现错误背书。

### 2026-10-19 缓解细化与ED保持：1050秒局部通过，延长验证中

补停止文件/下界失败归档、完整原生状态导出与单列接续；56项回归通过。0.3km/h细筛发现42.396候选，纠正“已筛选点失败”不能推为全域无解。相同7655步前缀后，50秒保持/30秒保持均实跑1050s，整体峰975.993kN、无超速；共同窗口峰935.673/955.528kN、最高单车79.929/79.051km/h。30秒为本地工程干预，不是实车参数，尚非通用规则；全段jerk略增，不能称全面更优。同状态30秒重复全等，自然延后0.2/0.4s局部248.5s预测均通过；不是不同冷初速验证。预测/实跑四段2485点全等。原生接续向49600m或首个失败推进，未有全线/三列结论；1000kN/222s及物理不变，不晋升、不训练、不推送。

数据 `single108_release_{fine,hold30}_trial_20261018_round6`、`single108_release_local_robustness_20261019_round6`；延长 `single108_release_hold30_continuation_20261019_round7`。报告 `traffic_rl_project/docs/reports/controller_takeover_20261017/缓解细化与空电保持时间对照_20261019.md`，含状态出处、完整指标及边界。

### 2026-10-19 延长与原生逐点筛查最终结果：未验收

round7与既有实跑重叠2845步六项全等；1082.6s/车头18.357km因均速39.971km/h低于原下界停止。round8把10785—10826的42个连续0.1s缓解时刻逐点预测：7点速度上界、35点下界失败；两轮3171步七项实跑记录全等。含前缀整体峰975.993kN、最高79.864km/h，但非整线通过；仅当前策略及该窄区间无通过点，不推为所有策略无解。Ma2023原文PDF4§3.3明确恒持电制动力50s，30s/25%力目标非原文参数；后续转向空气时变力—ED恒持力值匹配与108辆充风依据，停止只微调缓解速度。本轮按瓶颈停止，不晋升、不训练、不推送。原始数据round7/`single108_release_nativegrid_continuation_20261019_round8`，报告同上；新MIS指令同D目录 `TraeWork_108节缓解恒持力与充风可行域_20261019.md`。

2026-10-19最新：恒力候选尚未全线通过；确认关键窗口Newmark迭代/步长收敛瓶颈，暂停规则参数筛选。62项相关回归通过，零RL，未改生产物理/未晋升/未推送。详细数据与D盘报告、定向检索指令见HANDOFF_2026-10-17.md末尾“恒力目标与数值收敛瓶颈”。

2026-10-19续：平衡迭代诊断候选完成248.5秒局部气动联动，内部力峰572.462kN，最低均速40.288km/h，71项回归通过；非整线或三列验收。详见HANDOFF末尾及D盘《平衡迭代与气动闭环候选复核_20261019.md》。生产默认未改，新增未推送；下一步冷起点/联合步长核查。

2026-10-19续：冷起点745.2秒/车头12.725km，内部峰719.817kN，无超速/接管，完整实验求解器状态已保存；非全线验收。74项回归通过。现瓶颈为再制动力时程精度与计算效率，提示词及结果见HANDOFF末尾/D盘报告。新增未推送，生产默认未改。

<!-- 该文档整理/压缩于 2026-10-12 -->
