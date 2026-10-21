# 文档导航地图（唯一索引）

> 本文件是项目**所有文档**的入口。任何查找先来这里；找到 `computer://`/相对链接即可跳转。
> 职责分层、模板、规范见 `docs/rules/README.md`。新建文档先读 `docs/rules/CHECKLIST_NEW_DOC.md`。

## 快速导航

| 想找                   | 去哪                                                                       |
| -------------------- | ------------------------------------------------------------------------ |
| **代码知识库（改码前速查）**     | `docs/knowledge/TRAIN_DYNAMICS_KNOWLEDGE_BASE.md` · `knowledge/TRAIN_ENV_SAFETY_KNOWLEDGE_BASE.md` · `knowledge/RL_TRAINING_EVAL_KNOWLEDGE_BASE.md` · `knowledge/MPC_BASELINE_KNOWLEDGE_BASE.md` |
| 项目总览 / 任务清单 / 下一步    | `docs/PROJECT_PIPELINE.md`                                               |
| 研究定位 / 创新点 / 文献库     | `docs/RESEARCH_POSITIONING.md`                                           |
| **技术/公式 → 论文 引用索引**  | `docs/REFERENCE_INDEX.md`（写作速查）                                    |
| **文献讨论成果（证据/口径/机制）** | `docs/papers/LITERATURE_FINDINGS.md`（指标术语对照 · 防追尾机制分级 · ATP 诚实边界；写 Related Work / 指标表前读） |
| 论文↔项目验证基准（对照）        | `docs/VALIDATION_BASELINE.md`                                            |
| 验证执行日志（V 系列过程记录）     | `docs/logs/verification/`（按月/按 V 拆分）                               |
| 实验/诊断数据记录（按月拆分）     | `docs/logs/diagnostics/`（`DIAGNOSTICS_YYYY-MM.md`）                      |
| 阶段二执行流水（按月拆分）       | `docs/logs/progress/`（`PROGRESS_YYYY-MM.md`，2026-10-12 自 `PROJECT_PIPELINE.md` 拆出，append-only） |
| **新**重大决策记录（ADR）     | `docs/logs/decisions/DECISIONS.md`                                      |
| 踩坑 / 失败教训            | `docs/logs/learnings/LEARNINGS.md`                                      |
| 每日工作日志（timeline）     | `docs/logs/README.md`（→ `.codebuddy/memory/`)                            |
| 论文稿                 | 原 `docs/ITSC_PAPER.md/.tex/.pdf` 已删除（2026-10-19 目标会议更换，见 git 历史）；重写时新建 |
| 复现性说明                | `docs/REPRODUCIBILITY.md`                                                |
| **文献库目录清单（文件→元数据）** | `docs/papers/README.md`（新增文献必登记；含主题分类表 + 待补清单 + 子目录结构） |
| 文献 PDF / 信息卡         | `docs/papers/`（按主题分 5 个子目录：`01_coupler_physics/` 车钩与物理仿真 · `02_rl/` 强化学习 · `03_formation/` 列车编队 · `04_safety_mpc/` 安全层/MPC · `05_energy_other/` 节能/其他；重要文献配同名 `.md` 信息卡 + `_fulltext.txt` 全文检索件，信息卡为该文献数据 SSOT；例 `papers/01_coupler_physics/Zhao2022_AirBrakeRefinedModeling_Optimization.md`） |
| 规范 / 模板 / checklist  | `docs/rules/`                                                            |
| 汇报 / 交流材料（杂项）      | `docs/杂项/`（非研究 SSOT 的临时交流文档，如项目介绍 docx 及其提取版 md）                        |
| 阶段一历史成果              | `traffic_rl_project/history/`（原 `training_results_standardized.md` 已删，git 历史可查）      |

## 文责治理（强规范，写文档前必读）

**SSOT（单一事实源）**
- 每条数据只在产生它的文档出现一次，他处一律用链接引用，**绝不复制粘贴**。
- 新增内容先判断写进哪个角色（判断树见 `rules/README.md` 第四节），不混装、不重复建位。

**追加 / 拆分 / 立论三态**
- **流水**（诊断 / 决策 / 教训 / 日志）：`append-only`，老内容绝不覆盖；新增一律 `### 小节-日期` 追加。
- **立论**（RESEARCH_POSITIONING / 论文 / 规范）：可覆盖式修订，动机存档进 ADR；被推翻的论断原位标 `superseded` 并指向新结果。
- **超阈值拆分**：单文件接近 ~200KB 必须按 `类型/时间` 物理拆分，旧位置留薄 stub（`supersedes` + 索引链接）延续旧链接，并同步登记本文件（导航）。

**自动扫描禁止项（每次改动自查）**
1. **孤儿文件**：不被任何文档索引、无 git 历史的纯重复副本 → 删（如曾有的 `logs/dianostics_backup.md`，与他人字节相同且零引用）。
2. **失效引用**：指向不存在文档的链接 → 删引用行，不为不存在文件建占位页。
3. **构建垃圾**：LaTeX `*.aux` / `*.log`、临时脚本 → 加 `.gitignore`（`*.aux` / `*.log`），不进仓库。
4. **职责重叠**：与 `README.md`（唯一入口）导航重复的索引文件 → 归档并声明"以 README 为准"。导航信息应并入 README 而非另建索引文件。
5. **备份冗余**：文件已被拆分且 git 已跟踪原始大文件（`git log` 可恢复）时，旧整文件快照可删；git 历史就是最终备份。

**改文档走 review**
- 重要文档随代码进 git，只提交经确认的改动；导航登记在增删文档时同步。
- 复用模板：计划 / 失败 / 经验分别用 `rules/TEMPLATE_*.md`。

## 文档全集（按角色）

### 主文档（active）

| 文档                                | 角色                           | 状态     |
| --------------------------------- | ---------------------------- | ------ |
| `knowledge/TRAIN_DYNAMICS_KNOWLEDGE_BASE.md` | 代码知识库：列车动力学仿真引擎             | active |
| `knowledge/TRAIN_ENV_SAFETY_KNOWLEDGE_BASE.md` | 代码知识库：编队训练环境与安全层           | active |
| `knowledge/RL_TRAINING_EVAL_KNOWLEDGE_BASE.md` | 代码知识库：RL 训练评估框架            | active |
| `knowledge/MPC_BASELINE_KNOWLEDGE_BASE.md`  | 代码知识库：MPC 对比基线（NMPC）        | active |
| `PROJECT_PIPELINE.md`             | 总览+工作计划（执行流水按月拆至 `logs/progress/`）                | active |
| `RESEARCH_POSITIONING.md`         | 定位+文献库                       | active |
| `REFERENCE_INDEX.md`              | 引用索引（技术/公式→论文，写作速查）          | active |
| `papers/LITERATURE_FINDINGS.md`   | 文献讨论成果：逐篇证据 + 指标术语对照 + 防追尾机制分级 + ATP 诚实边界（`RESEARCH_POSITIONING.md` §1.7 的证据层） | active |
| `VALIDATION_BASELINE.md`          | 验证基准对照（2026-09-01 已拆 V日志/诊断） | active |
| `logs/decisions/DECISIONS.md`     | 决策记录（ADR，append-only）                                  | active |
| `logs/progress/PROGRESS_2026-08.md` / `PROGRESS_2026-09.md` / `PROGRESS_2026-10.md` | 阶段二执行流水（按月拆分，append-only；2026-10-12 自 `PROJECT_PIPELINE.md` 迁出，内容零丢失） | active |
| `logs/diagnostics/DIAGNOSTICS_2026-08.md` / `DIAGNOSTICS_2026-09.md` / `DIAGNOSTICS_2026-09B.md` / `DIAGNOSTICS_2026-10.md` | 实验/诊断数据（按月拆分 + 体积拆分，append-only）       | active |
| `logs/verification/VERIFICATION_LOGS_V1.md` / `VERIFICATION_LOGS_V2.md` / `VERIFICATION_LOGS_V4.md` / `VERIFICATION_LOGS_V5.md` / `VERIFICATION_LOGS_V6.md` | V 系列验证执行日志（按 V 拆分，append-only） | active |
| `logs/learnings/LEARNINGS.md`     | 踩坑 / 失败教训（append-only）                               | active |
| （ITSC_PAPER.md/.tex/.pdf 已删除） | 论文稿随目标会议更换移除（2026-10-19），重写时新建 | removed |
| `REPRODUCIBILITY.md`              | 复现                           | active |

### 治理层（rules）

| 文档                             | 用途                              |
| ------------------------------ | ------------------------------- |
| `rules/README.md`              | 规范总览 + 角色表 + 判断树                |
| `rules/TEMPLATE_WORKPLAN.md`   | 追加工作计划的模板                       |
| `rules/TEMPLATE_FAILURE.md`    | 记录失败/踩坑模板                       |
| `rules/TEMPLATE_EXPERIENCE.md` | 沉淀可复用经验模板                       |
| `rules/CHECKLIST_NEW_DOC.md`   | 新建/修改文档清单                       |
| `rules/EXECUTION_RULES.md`     | 执行规范（原 PIPELINE 七）              |
| `logs/decisions/DECISIONS.md`  | 决策记录（ADR）                       |
| `logs/diagnostics/DIAGNOSTICS_2026-08.md` / `DIAGNOSTICS_2026-09.md` / `DIAGNOSTICS_2026-09B.md` / `DIAGNOSTICS_2026-10.md` | 实验/诊断数据（按月 / 体积拆分） |
| `logs/verification/VERIFICATION_LOGS_V1.md` / `VERIFICATION_LOGS_V2.md` / `VERIFICATION_LOGS_V4.md` / `VERIFICATION_LOGS_V5.md` / `VERIFICATION_LOGS_V6.md` | V 系列验证执行日志（按 V 拆分） |
| `logs/learnings/LEARNINGS.md`  | 踩坑 / 失败教训                        |
| `logs/README.md`               | 工作日志入口（指向 `.codebuddy/memory/`） |

### 归档区（archived，保留不删，标 status: archived）

| 文档                                                          | 说明                                     |
| ----------------------------------------------------------- | -------------------------------------- |
| （原 `ITSC_PAPER.tex` / `.pdf`）                            | 论文源稿，已删除（2026-10-19 目标会议更换），见 git 历史 |
> 历史交接/会议备忘（`HANDOFF_*`、`GROUP_MEETING_TALK_PLAN.md`、`HUMAN_TODO.md`，含原"现存唯一交接文档" `HANDOFF_2026-10-17.md`）均已删除，任务全部并入 `PROJECT_PIPELINE.md`；需要时从 git 历史恢复。规则层标定数据看 `outputs/sim_validation/phys_validation/rulecal_*/` 与 `single108_*` 归档。

### 归档区（已有，保持）

| 路径                      | 说明              |
| ----------------------- | --------------- |
| `docs/papers/`          | 文献 PDF + 提取数据   |

> 归档 = 标记 + 导航归类 + git 冻结。路径**不移动**（避免打断链接），仅 front matter 标 `archived`，正文原样保留。

## 核心思想 → 文档映射（思想级索引）

> 想找"某个核心思想/主张在哪"，先看这节；想找"某类文档"，看上面的快速导航。

| 核心思想 / 主张                                                           | 主要出处                                                                                                  |
| ------------------------------------------------------------------- | ----------------------------------------------------------------------------------------------------- |
| **主轴与底线**：多列 platoon + 队内车钩力≤1000kN 不可逾越；AB+ED 分工、1+1 是锦上添花         | 仓库根 `AGENTS.md`「规范性问题」；`RESEARCH_POSITIONING.md`                                                      |
| **研究定位 / 创新点**：重载列车群组 × 车钩力 × 长大下坡分层 MARL                           | `RESEARCH_POSITIONING.md`                                                  |
| **架构分层**：规则层（循环制动+电空分工+安全层）作内层，MARL 作外层调制                           | `RESEARCH_POSITIONING.md` §1.3；代码 `src/controllers/multi_loco_controller.py`                                      |
| **智能体分解重构（ADR-009）**：每机车=智能体 / 每列车=智能体 vs 多列                        | `logs/decisions/DECISIONS.md` ADR-009/009.1                                                             |
| **MPC 对比口径**（ADR-037，废止 ADR-016 Regime A 协议）：不按坡换 MPC 模型；同一仿真器/环境/坡度数据/调参力度，坡度为 MPC 固有输入，**不设逐线重喂/重标定协议** | 仓库根 `AGENTS.md`「规范性问题」；`logs/decisions/DECISIONS.md` ADR-037                                                               |
| **MPC 基线唯一 = NMPC**（ADR-022，2026-10-01）：旧 `FairMPCController`/简化 MPC **已删除**；术语"多体"=**集中质量(lumped)多体** | 代码 `src/controllers/nmpc_controller.py`；`DECISIONS.md` ADR-022；`RESEARCH_POSITIONING.md` §1.6 |
| **车钩/列车异构性**（E4-H，**已 SUPERSEDED，不承担立论**）：实例异构 ≠ 离散，逐参数抽样 + held-out                  | `RESEARCH_POSITIONING.md` §1.5（车钩异构节）；`--hetero` 代码为可选鲁棒性                                                          |
| **「MARL 不行」根因与改造方向**（2026-10-01）：奖励口径 / AB 通路 / 安全层权限 / 信用分配                          | `logs/diagnostics/DIAGNOSTICS_2026-10.md`；`logs/decisions/DECISIONS.md` ADR-021                          |
| **文献四改造落地 + P0 三行 / AB 通道裁定**（2026-10-01）：A 充风门 / D 安全层 AB 禁新增 / C 车钩力超限项 / B per-agent | `logs/diagnostics/DIAGNOSTICS_2026-10.md`（「改造…」「P0…」两节）；`DECISIONS.md` ADR-021「执行闭环」；`REFERENCE_INDEX.md` 落地映射；规格 `.trae/specs/implement-literature-informed-fixes/` |
| **主训练 YAML 按 ADR-017 对齐**（2026-10-01）：1400 ep / n_env 4 / BC 热启动 / long_eval 50；`--episodes N` 快速迭代 | `configs/experiments/formation_ed_ab_3train_1plus1.yaml`；`REPRODUCIBILITY.md` §十；`DECISIONS.md` ADR-017「执行闭环」；`DIAGNOSTICS_2026-10.md`「验证-2026-10-01…」 |
| **评估链路四处口径缺陷修复**（2026-10-01）：`_long_eval` viol O(n²) / `--mode all` 缺 MPC 行 / MPC 状态残留 / `solve_statuses` 崩溃 | `DIAGNOSTICS_2026-10.md`「修复-2026-10-01…」两节；`LEARNINGS.md` LRN-20261001-010~013；`tests/test_metric_accounting.py`；`REPRODUCIBILITY.md` §十（MPC 成本提示） |
| **重训启动 / 长跑运维**（2026-10-01 seed0）：启动器、输出目录、`--resume latest` 恢复、机时**实测 ≈11.7 天/seed**（原估 3.4 天作废）、**进程持久化边界** | `scripts/launchers/launch_retrain_adr021_seed0.sh`；`REPRODUCIBILITY.md` §十「重训里程碑」；`DIAGNOSTICS_2026-10.md`「启动-2026-10-01…」；`LEARNINGS.md` LRN-20261001-014 / -016 |
| **ADR-024 动作带宽回退**（2026-10-02）：`ed_mod_coef` 1.0→0.5（放宽对 MPC 无收益、对 RL 有害）；五项 baseline/消融结果 | `DECISIONS.md` ADR-023 / ADR-024；`DIAGNOSTICS_2026-10.md`「放宽 / 冒烟与基线 / 回退-2026-10-02」；`scripts/launchers/launch_retrain_adr024_seed0.sh` |
| **路线覆盖修复：训练起点随机化**（2026-10-07）：固定起点使训练只见 −1.5‰（评估 OOD 83.9%）；L2 A/B 证明随机化有效（long_eval 达标 0/2→2/2，OOD→4.1%）；已接入主配置并启动 seed0 重训 | `DIAGNOSTICS_2026-10.md`「路线覆盖 / L1 / L1-b 更正 / L2 终局」；`docs/logs/progress/PROGRESS_2026-10.md`「路线覆盖修复」；`configs/experiments/formation_ed_ab_3train_1plus1.yaml` |
| **验证基准 / 复现**：论文↔仿真数据对照 + 实验诊断 + 复现命令                               | `VALIDATION_BASELINE.md`；`logs/verification/`；`logs/diagnostics/`；`REPRODUCIBILITY.md` |
| **文献库 / 立论来源**：PDF + 信息卡 + 数据基准                                     | `RESEARCH_POSITIONING.md` 文献库；`docs/papers/`                                                          |
| **指标术语 / 防追尾机制 / ATP 边界 的文献依据**（写 Related Work、指标表、图表标签前）            | `docs/papers/LITERATURE_FINDINGS.md`（结论口径仍以 `RESEARCH_POSITIONING.md` §1.5/§1.6/§1.7 为准）                        |
| **立论事实的唯一措辞权威**（引文献事实、写"空白/未见"前必读）                                     | `CLAIM_LEDGER.yaml`（台账）+ `RESEARCH_POSITIONING.md` §1.2 渲染区块；守卫 `scripts/check_claim_ledger.py` / `scripts/render_claims.py` |
| **否定命题（空白/未见）的检索证据**                                                             | `logs/verification/NEGATIVE_SEARCH_YYYY-MM-DD.md`（检索式/通道/命中/排除理由；缺此文件不得写"空白"） |
| **踩坑 / 经验**：引擎 gotcha、教训（学无可学/超长时域/止回）                              | `logs/learnings/LEARNINGS.md`（唯一 SSOT；原 `AGENTS.md` Gotchas 已迁入此处与 `VALIDATION_BASELINE.md`）                                                      |
| **工作留痕 / 决策**：新诊断、新 ADR                                             | `logs/diagnostics/`、`logs/decisions/DECISIONS.md`                                                        |

<!-- 该文档整理/压缩于 2026-10-01 -->

### 底层控制器实验交接档案（2026-10-14）

- [归档说明与重画命令](../outputs/sim_validation/phys_validation/controller_repair_20261014/README.md)：37个完成运行、原始轨迹/结果元数据/源码快照、冻结候选和原报告；非正式已验收控制器。
- [文件清单与SHA256](../outputs/sim_validation/phys_validation/controller_repair_20261014/publication_manifest.json)；图片位于 ../outputs/sim_validation/figures/controller_repair_20261014/。历史D盘路径保留出处，读取时使用仓库相对路径。

- **当前双人职责与接口核对（2026-10-14）**：见 [PROJECT_PIPELINE末尾当前清单](PROJECT_PIPELINE.md#p0-当前双人职责接口与联合验收核对---2026-10-14)。历史两层RL/NMPC/53km任务不作为现行安排；共享owner与编组版本同步尚未完成。

- 2026-10-18 缓解幅值与保持退出诊断（未达标）：[D盘完整报告](D:/Codex/Documents/Train/controller_takeover_20261017/万吨108节缓解幅值与保持退出复核_20261018.md)；状态与后续见 PROJECT_PIPELINE.md 同日条目。

- 2026-10-18 再制动准入与压力建立诊断（未达标）：[D盘完整报告](D:/Codex/Documents/Train/controller_takeover_20261017/万吨108节再制动准入与压力建立复核_20261018.md)；状态与后续见 PROJECT_PIPELINE.md 同日条目。

- 2026-10-18 阶段ED延长与充风速度余量（整体未达标）：[D盘报告](D:/Codex/Documents/Train/controller_takeover_20261017/万吨108节阶段ED与充风速度余量复核_20261018.md)、[TraeWork MIS定向检索指令](D:/Codex/Documents/Train/controller_takeover_20261017/TraeWork_MIS再制动专项检索指令_20261018.md)。

- 2026-10-18 新增全文与缓解可行性：[D盘核对报告](D:/Codex/Documents/Train/controller_takeover_20261017/新增全文复核与缓解可行性修复依据_20261018.md)，含林轩/黄宇澄关键公式、董文编组判据及旧汇总解释更正。
- 2026-10-18 原生缓解预测（下一周期候选受限，未验收）：[D盘复核报告](D:/Codex/Documents/Train/controller_takeover_20261017/万吨108节原生缓解预测与可行性瓶颈复核_20261018.md)、[TraeWork定向检索指令](D:/Codex/Documents/Train/controller_takeover_20261017/TraeWork_缓解预测与数值收敛定向检索_20261018.md)。52项回归通过；完整实跑中止，12段完成预测单独留存，不作全线证据。

- 2026-10-19 缓解速度细筛与ED保持对照：[D盘报告](D:/Codex/Documents/Train/controller_takeover_20261017/缓解细化与空电保持时间对照_20261019.md)、[最新MIS原文核对指令](D:/Codex/Documents/Train/controller_takeover_20261017/TraeWork_108节缓解恒持力与充风可行域_20261019.md)。两候选1050秒通过及局部重复/相邻时机检查；延长至车头18.36km速度下界失败，42个连续原生决策点未通过，无全线三列验收。

- 2026-10-19 恒力目标与数值收敛瓶颈（当前）：[D盘最终报告](D:/Codex/Documents/Train/controller_takeover_20261017/新增文献与50秒恒力目标修复_20261019.md)、[数值积分定向检索指令](D:/Codex/Documents/Train/controller_takeover_20261017/TraeWork_非线性积分收敛专项检索_20261019.md)。局部改善未转化为全线通过；关键窗口1475/1599步未满足迭代准则，细步力峰仍未收敛，先核查数值可靠性。62项回归通过；未训练、未晋升默认。

2026-10-19后续：已读新增相关原文并做联合容差/步长诊断，1e-9容差最细两级片段峰633.055883/633.040330kN，迭代均达准则；包络逐时差仍15.79kN，非完整闭环或全线验收。65项回归通过，生产物理未改，未训练/未推送。报告：[D盘详细复核](D:/Codex/Documents/Train/controller_takeover_20261017/新增论文与联合容差收敛复核_20261019.md)。下一步验证失败步回退/力残差与完整闭环，禁止把633kN当整线效果。

2026-10-19最新平衡迭代候选：独立加速度Picard同时检查局部位移与末状态力平衡，β/γ及物理力律未改；气动子步事务回滚与解析解等71项回归通过。固定输入细化峰633.065/633.043kN，全断面时程最大差15.823kN，仍非严密误差界。同765.5秒完整原生状态，248.5秒零RL局部气动机械反馈窗口通过：内部峰572.462kN、最高70.248/最低均速40.288km/h，397600接受细步，力残差均≤10N。原求解235.5秒峰1004.883kN失败，旧2355×6记录精确复现；新方案前20秒与独立短试验精确一致。该窗口继承旧积分历史，预测跳过递归guard但保留原准入与ATP，未作全线/冷起点/三列验收，生产默认未改，未训练，新增工作未推送。数据single108_balanced_{mechanics,tight_mechanics,coupled,coupled_fullwindow}_20261019_round14；D盘报告：D:/Codex/Documents/Train/controller_takeover_20261017/平衡迭代与气动闭环候选复核_20261019.md。下一步冷起点及气动/机械联合细化验证，不能将572kN标为全线规则修复效果。

- 2026-10-19最新冷起点：745.2秒、车头12.725km、内部峰719.817kN、单车47.411—76.139km/h，完整状态已存，尚非49.6km全线通过。74项相关回归通过；力时程精度/效率仍需核查。[D盘详细报告](D:/Codex/Documents/Train/controller_takeover_20261017/冷起点验证与力时程收敛瓶颈_20261019.md)、[TraeWork MIS检索指令](D:/Codex/Documents/Train/controller_takeover_20261017/TraeWork_MIS力时程精度与计算效率专项_20261019.md)。

- 2026-10-19本轮发布资料：[中文循环制动图](../outputs/sim_validation/figures/cyclic_braking_108_20261019/cyclic_cold745_zh.png)、[D盘49份工作文档及配套资料ZIP](../outputs/sim_validation/phys_validation/controller_reports_publication_20261019_round16/controller_reports_publication_20261019_round16.zip)。ZIP含逐文件SHA256。图仅覆盖745.2秒冷起点前缀，不是全线验收；可用src/evaluation/plot_cyclic_archive.py复画，无需重跑仿真。

### 2026-10-20 单列控制修复与局部验证归档

- 单列1机车+108货车（10988吨）、49.6公里固定起点：第33轮完整状态连续运行至尾车通过终点；最高车辆速度78.51493 km/h，最低全列平均速度43.05631 km/h，含前1000秒起步阶段的内部车钩峰值约719.82284 kN。零RL、实验数值求解；生产默认未晋升，不代表三列或随机起点验收。
- 第36轮2180—2580秒局部候选：深制动请求0次，最低车辆42.62470 km/h，内部车钩峰674.21224 kN。第37轮细化缓解重试后最低车辆44.13940 km/h、内部峰651.09197 kN，但深制动请求恢复为1次，未达到全部接续条件，未启动第38轮剩余路段验证。保留第33轮为已通过单列基线。
- 原始数据、完整重启状态、冻结源码与哈希位于 `outputs/sim_validation/phys_validation/single108_*`；不要将轨迹数组视为可恢复全部气动和控制器历史的检查点。
- [D盘工作报告仓库副本](reports/controller_takeover_20261017/)；[中文循环制动图及配套资料](../outputs/sim_validation/figures/controller_repair_20261020/)。保留历史报告，各轮结论以对应result.json和local_comparison.json为准。
- 后续流程：问题前完整状态→同工况局部对比→有明确改善后再线路验收；阶段验收出图，样式调整复用原数据。
