# -*- coding: utf-8 -*-
"""临时脚本：把 于宗泽2025 精细化模型 PDF 全文抽成文本，供检索拟合常数。用后即删。"""
import sys
sys.stdout.reconfigure(encoding="utf-8")
from pypdf import PdfReader

src = r"d:\Code\MultiAgent\traffic_rl_project\docs\papers\重载列车车钩缓冲装置纵向动力学精细化模型_于宗泽.pdf"
reader = PdfReader(src)
out = []
for i, page in enumerate(reader.pages):
    out.append(f"===== PAGE {i+1} / {len(reader.pages)} =====")
    out.append(page.extract_text() or "")
text = "\n".join(out)
dst = r"d:\Code\MultiAgent\traffic_rl_project\docs\papers\于宗泽2025_fulltext.txt"
with open(dst, "w", encoding="utf-8") as f:
    f.write(text)
print(f"PAGES: {len(reader.pages)} -> wrote {dst} ({len(text)} chars)")