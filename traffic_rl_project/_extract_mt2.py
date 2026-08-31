"""提取李蔚论文 MT-2 多段线性缓冲器特性曲线数据（各段刚度、过渡点、迟滞参数）。"""
import pypdf, re

path = "docs/papers/重载组合列车纵向力优化的联合制动分析及研究_李蔚.pdf"
r = pypdf.PdfReader(path)
full = " ".join((p.extract_text() or "") for p in r.pages)

print(f"总页数: {len(r.pages)}")
# 定位缓冲器模型部分（多段线性、加载/卸载/过渡、图4）
for kw in ["多段线性", "加载阶段", "卸载阶段", "过渡阶段", "阻抗力", "刚度", "位移", "图 4", "迟滞"]:
    hits = list(re.finditer(re.escape(kw), full))
    print(f"\n### '{kw}' 共 {len(hits)} 处")
    for m in hits[:3]:
        s = max(0, m.start()-150)
        e = min(len(full), m.end()+250)
        seg = full[s:e].replace("\n", " ")
        print(f"  ...{seg}...")
