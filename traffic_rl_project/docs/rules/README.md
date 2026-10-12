# 文档规范总览（Docs-as-Code 最佳实践落地）

本目录是本项目**唯一**的文档治理层。所有文档协作依据这里，所有新文档必须先读
`CHECKLIST_NEW_DOC.md`。

---

## 一、本项目文档架构（角色分层）

每类文档有明确职责、Owner、生命周期（SSOT 详见纪律 1）。

| 目录/文档 | 角色 | 生命周期 | 谁追加 |
|---|---|---|---|
| `docs/rules/` | 规范 + 模板（本文档体系就是它） | 修订走 review，只更新不覆盖历史规则记录 | 项目 Owner |
| `docs/README.md` | **导航地图**：所有文档入口，唯一索引 | 增删文档时同步 | 项目 Owner |
| `docs/PROJECT_PIPELINE.md` | 总览 + 工作计划清单（任务追加走 TEMPLATE_WORKPLAN） | append-only，历史✅保留 | Owner + Agent |
| `docs/logs/progress/PROGRESS_YYYY-MM.md` | **阶段二执行流水**（自 PIPELINE 按月迁出的历史执行条目） | append-only，按月新建承接文件 | Owner + Agent |
| `docs/VALIDATION_BASELINE.md` | 论文↔项目**验证基准**（公式/数据对照）；历史诊断已留此处 | append-only | Owner + Agent |
| `docs/logs/diagnostics/DIAGNOSTICS_YYYY-MM.md` | **新的**实验/诊断数据记录（按月拆分，append-only） | append-only | Agent + Owner |
| `docs/logs/decisions/DECISIONS.md` | **新的**重大决策记录（ADR：背景→选项→结论→后果） | append-only，废弃标 superseded | Owner + Agent |
| `docs/logs/learnings/LEARNINGS.md` | 踩坑/失败教训（走 TEMPLATE_FAILURE） | append-only | Agent |
| `.codebuddy/memory/YYYY-MM-DD.md` | 每日工作日志（timeline，见 `docs/logs/README.md`） | 每日一篇，不覆盖 | Agent |
| `docs/papers/` | 文献 PDF + 提取数据（`RESEARCH_POSITIONING.md` 索引） | 新增 | Owner |
| `docs/ITSC_PAPER.md/.tex/.pdf` | 论文（唯一权威版本），其余版本移 archive | 冻结后进 archive | Owner |

## 二、八条最佳实践纪律（大厂对齐）

1. **单一事实源 SSOT**：不重复；要引用用链接。数据只在产生它的文档记录，其他页面链接。
2. **职责分离**：验证 / 诊断 / 决策 / 踩坑 / 日志 / 论文 各归其位，不混装。
3. **Front Matter**：每个文档顶部 YAML 块 `title / date / status / owner / supersedes`。
4. **变更走 review**：重要文档随代码进 git；决策记录只追加，废弃用 `supersedes`，不篡改旧文。
5. **少即多**：单文件超阈值(约 200KB)必须拆分或新建承接文件；旧内容保留，新内容进新文件。
6. **append-only 留痕**：工作/诊断/决策都只追加小节，历史命令/结论是论文溯源基础，绝不覆盖。
7. **导航登记**：新建文档必须登记进 `docs/README.md`，否则等于没建。
8. **临时物即生即清**：临时脚本用后即删或移 `outputs/`，不留在根目录。

## 三、三类核心模板（追加/总结/记录）

| 场景 | 用哪个模板 |
|---|---|
| 追加工作计划到 `PROJECT_PIPELINE.md` | `TEMPLATE_WORKPLAN.md` |
| 已完结的执行条目按月归档到 `logs/progress/` | `TEMPLATE_WORKPLAN.md`（整条原样迁出，标题不变） |
| 记录一次失败/踩坑到 `docs/logs/learnings/LEARNINGS.md` | `TEMPLATE_FAILURE.md` |
| 沉淀一条可复用历史经验（区别于一次性教训） | `TEMPLATE_EXPERIENCE.md` |
| 新建任何文档前 | `CHECKLIST_NEW_DOC.md`（必读） |

## 四、快速判断"这条我要写进哪个文件"

```
我要记录的是？
├─ 一个实验/诊断跑出的数据 + 复现命令          → logs/diagnostics/DIAGNOSTICS_YYYY-MM.md（按月，append）
├─ 我做了个重要技术/方向决策                     → logs/decisions/DECISIONS.md
├─ 我踩坑了、修了、怎么避免复发                  → logs/learnings/LEARNINGS.md
├─ 我新增一个要做的任务/计划                      → PROJECT_PIPELINE.md（TEMPLATE_WORKPLAN）
├─ 一条历史任务的执行记录/结果（PIPELINE 已过长）    → 按月追加到 logs/progress/PROGRESS_YYYY-MM.md（append-only）
├─ 今天的工作流水（做了什么/卡在哪）              → .codebuddy/memory/YYYY-MM-DD.md（每日日志）
├─ 一条能复用的方法论/知识（有出处、有反例）       → TEMPLATE_EXPERIENCE 沉淀
└─ 论文/对外交付物                                → docs/ITSC_PAPER.*（唯一权威）
```

---

> 本文件本身走 best practice：它只是规范，不承载项目数据。

<!-- 该文档整理/压缩于 2026-10-01 -->
