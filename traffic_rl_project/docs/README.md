# 文档导航地图（唯一索引）

> 本文件是项目**所有文档**的入口。任何查找先来这里；找到 `computer://`/相对链接即可跳转。
> 职责分层、模板、规范见 `docs/rules/README.md`。新建文档先读 `docs/rules/CHECKLIST_NEW_DOC.md`。

## 快速导航

| 想找                   | 去哪                                                                       |
| -------------------- | ------------------------------------------------------------------------ |
| 项目总览 / 任务清单 / 下一步    | `docs/PROJECT_PIPELINE.md`                                               |
| 研究定位 / 创新点 / 文献库     | `docs/RESEARCH_POSITIONING.md`                                           |
| **技术/公式 → 论文 引用索引**  | `docs/REFERENCE_INDEX.md`（写作速查）                                    |
| 论文↔项目验证基准（对照）        | `docs/VALIDATION_BASELINE.md`                                            |
| 验证执行日志（V 系列过程记录）     | `docs/logs/verification/`（按月/按 V 拆分）                               |
| 实验/诊断数据记录（按月拆分）     | `docs/logs/diagnostics/`（`DIAGNOSTICS_YYYY-MM.md`）                      |
| **新**重大决策记录（ADR）     | `docs/logs/decisions/DECISIONS.md`                                      |
| 踩坑 / 失败教训            | `docs/logs/learnings/LEARNINGS.md`                                      |
| 每日工作日志（timeline）     | `docs/logs/README.md`（→ `.codebuddy/memory/`)                            |
| 论文（唯一权威）             | `docs/ITSC_PAPER.md` / `.tex` / `.pdf`                                   |
| 复现性说明                | `docs/REPRODUCIBILITY.md`                                                |
| 文献 PDF / 信息卡         | `docs/papers/`（重要文献配同名 `.md` 信息卡 + `_fulltext.txt` 全文检索件，信息卡为该文献数据 SSOT） |
| 规范 / 模板 / checklist  | `docs/rules/`                                                            |
| 阶段一历史成果              | 见「归档区」↓                                                                  |

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
| `PROJECT_PIPELINE.md`             | 总览+工作计划                      | active |
| `RESEARCH_POSITIONING.md`         | 定位+文献库                       | active |
| `REFERENCE_INDEX.md`              | 引用索引（技术/公式→论文，写作速查）          | active |
| `VALIDATION_BASELINE.md`          | 验证基准对照（2026-09-01 已拆 V日志/诊断） | active |
| `logs/decisions/DECISIONS.md`     | 决策记录（ADR，append-only）                                  | active |
| `logs/diagnostics/DIAGNOSTICS_YYYY-MM.md` | 实验/诊断数据（按月拆分，append-only）                    | active |
| `logs/verification/VERIFICATION_LOGS_V*.md` | V 系列验证执行日志（按 V 拆分，append-only）         | active |
| `logs/learnings/LEARNINGS.md`     | 踩坑 / 失败教训（append-only）                               | active |
| `ITSC_PAPER.md` / `.tex` / `.pdf` | 论文（唯一权威）                     | active |
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
| `logs/diagnostics/`            | 实验/诊断数据（按月拆分）                  |
| `logs/verification/`           | V 系列验证执行日志（按 V 拆分）             |
| `logs/learnings/LEARNINGS.md`  | 踩坑 / 失败教训                        |
| `logs/README.md`               | 工作日志入口（指向 `.codebuddy/memory/`） |

### 归档区（archived，保留不删，标 status: archived）

| 文档                                                          | 说明                                     |
| ----------------------------------------------------------- | -------------------------------------- |
| `learning_report.md`                                        | 阶段一完整技术报告（历史成果）                        |
| `training_results_standardized.md`                          | 阶段一学术成果报告                              |
| `ITSC_PAPER.tex` / `.pdf`                                | 论文源稿 / 编译 PDF（唯一权威投稿版本）           |
| `HANDOFF_*.md`、`GROUP_MEETING_TALK_PLAN.md` | 阶段性交接/会议/备忘（任务已转移到 `PROJECT_PIPELINE`；`HUMAN_TODO.md` 已删） |
> **最新交接**：`logs/HANDOFF_2026-09-10.md`（面向零基础新成员 + agent，含加速导航 / 踩坑史 / 当前卡点与下一步精确指令；supersede `logs/HANDOFF_2026-09-09.md`） |

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
| **研究定位 / 创新点**：重载列车群组 × 车钩力 × 长大下坡分层 MARL                           | `RESEARCH_POSITIONING.md`；论文 `ITSC_PAPER.md` Intro                                                    |
| **架构分层**：规则层（循环制动+电空分工+安全层）作内层，MARL 作外层调制                           | `RESEARCH_POSITIONING.md`；`AGENTS.md`「阶段二列车仿真设计」                                                      |
| **智能体分解重构（ADR-009）**：每机车=智能体 / 每列车=智能体 vs 多列                        | `logs/decisions/DECISIONS.md` ADR-009/009.1                                                             |
| **MPC 对比规范 Regime A/B**：不按坡换 MPC 模型；A=公平重喂、B=no-re-id 演不泛化，逐实验标 A/B | 仓库根 `AGENTS.md`「规范性问题」；论文 Protocol（待展开）                                                               |
| **MPC 模型口径**：聚合列 + 车钩代理 + 坡度先验锁线                                    | 仓库根 `AGENTS.md`（`FairMPCController`）                                                          |
| **车钩/列车异构性**（泛化卖点 E4-H）：实例异构 ≠ 离散，逐参数抽样 + held-out                  | 仓库根 `AGENTS.md`；`计划/实验` 见 `.trae/documents/`                                                          |
| **验证基准 / 复现**：论文↔仿真数据对照 + 实验诊断 + 复现命令                               | `VALIDATION_BASELINE.md`；`logs/verification/`；`logs/diagnostics/`；`REPRODUCIBILITY.md` |
| **文献库 / 立论来源**：PDF + 信息卡 + 数据基准                                     | `RESEARCH_POSITIONING.md` 文献库；`docs/papers/`                                                          |
| **踩坑 / 经验**：引擎 gotcha、教训（学无可学/超长时域/止回）                              | `AGENTS.md` Gotchas；`logs/learnings/LEARNINGS.md`                                                      |
| **工作留痕 / 决策**：新诊断、新 ADR                                             | `logs/diagnostics/`、`logs/decisions/DECISIONS.md`                                                        |

