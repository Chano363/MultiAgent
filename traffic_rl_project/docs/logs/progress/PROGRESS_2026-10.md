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

<!-- 该文档整理/压缩于 2026-10-12 -->
