# 文档导航地图（唯一索引）

> 本文件是项目**所有文档**的入口。任何查找先来这里；找到 `computer://`/相对链接即可跳转。
> 职责分层、模板、规范见 `docs/rules/README.md`。新建文档先读 `docs/rules/CHECKLIST_NEW_DOC.md`。

## 快速导航

| 想找 | 去哪 |
|---|---|
| 项目总览 / 任务清单 / 下一步 | `docs/PROJECT_PIPELINE.md` |
| 研究定位 / 创新点 / 文献库 | `docs/RESEARCH_POSITIONING.md` |
| 论文↔项目验证基准（对照） | `docs/VALIDATION_BASELINE.md` |
| 验证执行日志（V 系列过程记录） | `docs/records/VERIFICATION_LOGS.md` |
| 实验/诊断数据记录（含已拆入的历史诊断） | `docs/records/DIAGNOSTICS.md` |
| **新**重大决策记录（ADR） | `docs/records/DECISIONS.md` |
| 踩坑 / 失败教训 | `traffic_rl_project/.learnings/LEARNINGS.md` |
| 每日工作日志（timeline） | `docs/logs/README.md`（→ `.codebuddy/memory/`) |
| 论文（唯一权威） | `docs/ITSC_PAPER.md` / `.tex` / `.pdf` |
| 复现性说明 | `docs/REPRODUCIBILITY.md` |
| 文献 PDF / 信息卡 | `docs/papers/`（重要文献配同名 `.md` 信息卡 + `_fulltext.txt` 全文检索件，信息卡为该文献数据 SSOT） |
| 规范 / 模板 / checklist | `docs/rules/` |
| 阶段一历史成果 | 见「归档区」↓ |

## 文责治理

- **SSOT**：每条数据只在产生它的文档出现，他处用链接。新增内容先判断写进哪个角色（见 rules README 第四节判断树）。
- **追加式**：老内容绝不覆盖；新增一律 `### 小节-日期` append。
- **复用模板**：计划 / 失败 / 经验请分别用 `rules/TEMPLATE_*.md`。

## 文档全集（按角色）

### 主文档（active）
| 文档 | 角色 | 状态 |
|---|---|---|
| `PROJECT_PIPELINE.md` | 总览+工作计划 | active |
| `RESEARCH_POSITIONING.md` | 定位+文献库 | active |
| `VALIDATION_BASELINE.md` | 验证基准对照（2026-09-01 已拆 V日志/诊断）| active |
| `records/VERIFICATION_LOGS.md` | V 系列验证执行日志 | active |
| `records/DIAGNOSTICS.md` | 实验/诊断数据（含拆入的历史诊断）| active |
| `records/DECISIONS.md` | 决策记录（ADR-001 起）| active |
| `ITSC_PAPER.md` / `.tex` / `.pdf` | 论文（唯一权威）| active |
| `REPRODUCIBILITY.md` | 复现 | active |

### 治理层（rules）
| 文档 | 用途 |
|---|---|
| `rules/README.md` | 规范总览 + 角色表 + 判断树 |
| `rules/TEMPLATE_WORKPLAN.md` | 追加工作计划的模板 |
| `rules/TEMPLATE_FAILURE.md` | 记录失败/踩坑模板 |
| `rules/TEMPLATE_EXPERIENCE.md` | 沉淀可复用经验模板 |
| `rules/CHECKLIST_NEW_DOC.md` | 新建/修改文档清单 |
| `rules/EXECUTION_RULES.md` | 执行规范（原 PIPELINE 七）|
| `guides/CODE_INDEX.md` | 代码/配置/输出目录索引（原 PIPELINE 五）|
| `records/DIAGNOSTICS.md` | 实验/诊断数据（含拆入历史诊断）|
| `records/VERIFICATION_LOGS.md` | V 系列验证执行日志 |
| `records/DECISIONS.md` | 决策记录（ADR）|
| `logs/README.md` | 工作日志入口（指向 `.codebuddy/memory/`）|

### 归档区（archived，保留不删，标 status: archived）
| 文档 | 说明 |
|---|---|
| `learning_report.md` | 阶段一完整技术报告（历史成果）|
| `training_results_standardized.md` | 阶段一学术成果报告 |
| `ITSC_PAPER_PLAN.md` | 论文写作计划（被 `ITSC_PAPER.*` 承接）|
| `ITSC_PAPER_CN.md` / `ITSC_PAPER_中文对照.md` | 中文版/对照（非投稿权威版本，衍生）|
| `HANDOFF_*.md`、`GROUP_MEETING_TALK_PLAN.md`、`HUMAN_TODO.md` | 阶段性交接/会议/备忘（任务已转移到 `PROJECT_PIPELINE`）|

### 归档区（已有，保持）
| 路径 | 说明 |
|---|---|
| `docs/papers/` | 文献 PDF + 提取数据 |
| `docs/archive/scripts/` | 被冻结的临时脚本（不在根目录）|

> 归档 = 标记 + 导航归类 + git 冻结。路径**不移动**（避免打断链接），仅 front matter 标 `archived`，正文原样保留。