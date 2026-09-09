# 冻结脚本归档（docs/archive/scripts/）

> 这些脚本原是根目录临时物，已从根目录移到这里冻结，**原文保留、不删**（确保信息不丢失）。
> 按最佳实践，本项目根目录只放规范化代码（src/）与文档入口，临时脚本不进根目录。

| 脚本 | 用途（原） |
|---|---|
| `tmp_del_page14.py` | PPT 页 14 临时处理 |
| `tmp_fill.py` | PPT 数据回填临时脚本 |
| `tmp_grep.py` | 临时文本检索 |
| `_extract_mt2.py` | MT-2 车钩参数提取 |
| ~~`_md2tex.py`~~ | ~~Markdown→LaTeX 转换~~（2026-09-08 删除：仅用于旧中文对照 `ITSC_PAPER_中文对照.md`→`ITSC_PAPER_CN.tex`，源与产物均已清理） |

> 若后续确认某脚本需长期保留复现，迁到 `src/evaluation/` 或 `tools/` 并注明用途；否则保持冻结。