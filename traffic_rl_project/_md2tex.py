"""把 ITSC_PAPER_中文对照.md 转成 LaTeX（支持中文 + Noto Sans CJK），用 tectonic 编译。

保持内容与英文一致，不加括号/修饰。处理：标题、粗体、斜体、表格、列表、水平线。
"""
import re
from pathlib import Path

md = Path("/mnt/d/Code/MultiAgent/traffic_rl_project/docs/ITSC_PAPER_中文对照.md").read_text(encoding='utf-8')
lines = md.splitlines()

# LaTeX 头（fontspec + Noto Sans CJK，直接指定字体文件路径）
header = r"""\documentclass[11pt]{article}
\usepackage[margin=2.2cm]{geometry}
\usepackage{fontspec}
\usepackage{xeCJK}
\usepackage{amsmath,amssymb}
\usepackage{longtable}
\usepackage{array}
\usepackage{booktabs}
\setCJKmainfont[Path=/home/chano/miniconda3/envs/traffic_rl/fonts/]{NotoSansCJKsc-VF.ttf}
\setCJKsansfont[Path=/home/chano/miniconda3/envs/traffic_rl/fonts/]{NotoSansCJKsc-VF.ttf}
\setmainfont[Path=/home/chano/miniconda3/envs/traffic_rl/fonts/]{NotoSansCJKsc-VF.ttf}
\title{ITSC 论文中文对照版}
\author{}
\date{\today}
\begin{document}
\maketitle
"""

out = [header]
in_table = False
for ln in lines:
    stripped = ln.strip()
    # 表格行
    if stripped.startswith('|') and stripped.endswith('|'):
        if not in_table:
            out.append(r"\begin{longtable}{*{20}{p{1.6cm}}}")
            in_table = True
        # 分隔行 --- 跳过
        if set(stripped.replace('|','').replace(':','').replace('-','').strip()) == set():
            out.append(r"\midrule")
        else:
            cells = [c.strip() for c in stripped.strip('|').split('|')]
            # 处理表格内的 **粗体**
            cells_tex = []
            for c in cells:
                c = c.replace('**', '')  # 去掉 md 粗体
                c = c.replace('`', '')
                c = c.replace('‰', r'\textperthousand ')
                c = c.replace('→', r'$\rightarrow$ ')
                c = c.replace('≤', r'$\leq$ ')
                c = c.replace('≥', r'$\geq$ ')
                c = c.replace('±', r'$\pm$ ')
                c = c.replace('_', r'\_')
                c = c.replace('%', r'\%')
                c = c.replace('#', r'\#')
                cells_tex.append(c)
            out.append(' & '.join(cells_tex) + r' \\')
        continue
    else:
        if in_table:
            out.append(r"\end{longtable}")
            in_table = False
    # 标题
    if stripped.startswith('### '):
        out.append(r"\subsection*{" + stripped[4:] + "}")
    elif stripped.startswith('## '):
        out.append(r"\section*{" + stripped[3:] + "}")
    elif stripped.startswith('# '):
        out.append(r"\section*{" + stripped[2:] + "}")
    # 水平线
    elif stripped == '---' or stripped == '***':
        out.append(r"\bigskip\hrule\bigskip")
    # 粗体/斜体处理 + 数学符号 + 特殊字符转义
    elif stripped:
        t = stripped
        t = t.replace('**', '')
        t = t.replace('*', '')
        t = t.replace('`', '')  # 去反引号
        t = t.replace('‰', r'\textperthousand ')
        t = t.replace('→', r'$\rightarrow$ ')
        t = t.replace('≤', r'$\leq$ ')
        t = t.replace('≥', r'$\geq$ ')
        t = t.replace('±', r'$\pm$ ')
        t = t.replace('×', r'$\times$ ')
        # LaTeX 特殊字符转义（数学替换已先完成；原文 .md 不含反斜杠，故不转义 \\）
        t = t.replace('{', r'\{').replace('}', r'\}')
        t = t.replace('_', r'\_').replace('%', r'\%')
        t = t.replace('#', r'\#').replace('&', r'\&')
        out.append(t + '\n')
    else:
        out.append('\n')

if in_table:
    out.append(r"\end{longtable}")

out.append(r"\end{document}")
tex = '\n'.join(out)

# 写 LaTeX 文件到 docs（用 ASCII 文件名避免 tectonic 中文路径问题）
tex_path = Path("/mnt/d/Code/MultiAgent/traffic_rl_project/docs/ITSC_PAPER_CN.tex")
tex_path.write_text(tex, encoding='utf-8')
print(f"已生成: {tex_path.name} ({len(tex)} chars)")
