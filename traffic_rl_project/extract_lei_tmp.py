# -*- coding: utf-8 -*-
"""临时：落盘 lei2019 全文供读取。"""
import sys
sys.stdout.reconfigure(encoding="utf-8")
from pypdf import PdfReader
src = r"d:\Code\MultiAgent\traffic_rl_project\docs\papers\lei2019_gooa.pdf"
reader = PdfReader(src)
out = [f"===== PAGE {i+1} =====" for i, p in enumerate(reader.pages)]
# 更好的逐页块结构
blocks = []
for i, p in enumerate(reader.pages):
    blocks.append(f"===== PAGE {i+1} =====\n" + (p.extract_text() or ""))
text = "\n".join(blocks)
dst = r"d:\Code\MultiAgent\traffic_rl_project\docs\papers\lei2019_fulltext.txt"
with open(dst, "w", encoding="utf-8") as f:
    f.write(text)
print("wrote", dst, len(text))