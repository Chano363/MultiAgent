# 新建 / 修改文档 Checklist（Docs-as-Code 落地）

> 任何文档工作（新建、大改、归档）**先过此表**。做完才能交付。

## 通用（Front Matter）
- [ ] 文档顶部 YAML 块含：`title` / `date` / `status`(`draft|active|archived`) / `owner` / `supersedes`
- [ ] 语言风格统一（表格、层级、图标一致），遵循项目文档风格
- [ ] 属于哪类已经明确（对照 `docs/rules/README.md` 的角色表），**没混装进别的文档**

## 如果新建
- [ ] 有独立职责，不是已有文档的重复（SSOT 检查）
- [ ] 已登记进 `docs/README.md` 导航（否则等于没建）
- [ ] Owner 已指定
- [ ] 引用的其他文档用链接（`[标题](相对路径)`），不复制内容

## 如果追加内容（append）
- [ ] 用对应模板：计划→`TEMPLATE_WORKPLAN`；失败→`TEMPLATE_FAILURE`；经验→`TEMPLATE_EXPERIENCE`；诊断→`DIAGNOSTICS`
- [ ] 只追加，历史小节未动 ✅ 保留
- [ ] 含复现要素：命令 / seed / 关键超参 / 产出文件链接

## 如果是实验 / 诊断
- [ ] 原始数据落盘 `outputs/`（带时间戳，不覆盖旧文件）
- [ ] 命令 + seed + 配置已记录，保证论文数据可复现
- [ ] 分组明细（逐列/逐工况）已记，非只有平均值

## 如果归档
- [ ] front matter `status: archived` + 标注被谁 `superseded`
- [ ] 归档前内容已冻结备份（git 有记录）
- [ ] `docs/README.md` 导航已把它移到"归档区"

## 收尾
- [ ] `docs/README.md` 导航同步更新
- [ ] `AGENTS.md` 的文档清单章节同步（若引用被改）
- [ ] 旧临时副本（如 tmp_*.py）已删或移 `outputs/`

<!-- 该文档整理/压缩于 2026-10-01 -->
