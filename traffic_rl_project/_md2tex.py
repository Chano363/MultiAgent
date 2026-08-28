"""把 ITSC_PAPER_中文对照.md 转成 LaTeX（支持中文 + 公式 + 图 + 表格），用 tectonic 编译。

处理：标题、粗体、斜体、表格、列表、水平线、公式($$ 和 行内 $)、图片、参考文献。
数学内容($...$)不做 LaTeX 特殊字符转义；普通文本转义。
"""
import re
from pathlib import Path

md = Path("/mnt/d/Code/MultiAgent/traffic_rl_project/docs/ITSC_PAPER_中文对照.md").read_text(encoding='utf-8')
lines = md.splitlines()

# LaTeX 头（fontspec + 中文标准字体）
header = r"""\documentclass[11pt]{article}
\usepackage[margin=2.2cm]{geometry}
\usepackage{fontspec}
\usepackage{xeCJK}
\usepackage{amsmath,amssymb}
\usepackage{graphicx}
\usepackage{array}
\usepackage{booktabs}
% 中文论文标准字体：正文宋体(SimSun)、标题黑体(SimHei)、加粗用黑体
\setCJKmainfont[Path=/mnt/c/Windows/Fonts/, BoldFont=simhei.ttf]{simsun.ttc}
\setCJKsansfont[Path=/mnt/c/Windows/Fonts/]{simhei.ttf}
\setmainfont[Path=/mnt/c/Windows/Fonts/, BoldFont=simhei.ttf]{simsun.ttc}
% 标题使用黑体（sans）
\makeatletter
\renewcommand{\section}{\@startsection{section}{1}{\z@}{-3.5ex \@plus -1ex \@minus -.2ex}{2.3ex \@plus .2ex}{\normalfont\large\bfseries\sffamily}}
\renewcommand{\subsection}{\@startsection{subsection}{2}{\z@}{-3.25ex\@plus -1ex \@minus -.2ex}{1.5ex \@plus .2ex}{\normalfont\normalsize\bfseries\sffamily}}
\makeatother
\title{基于循环制动的多智能体强化学习用于长大下坡重载列车群组协同控制（中文对照）}
\author{}
\date{}
\begin{document}
\maketitle
"""


_ESCAPE = {
    '{': r'\{', '}': r'\}',
    '_': r'\_', '%': r'\%',
    '#': r'\#', '&': r'\&',
}
_UNICODE = {
    '‰': r'\textperthousand ',
    '→': r'$\rightarrow$ ',
    '≤': r'$\leq$ ',
    '≥': r'$\geq$ ',
    '±': r'$\pm$ ',
    '×': r'$\times$ ',
    '\u2212': r'$-$ ',
}


def escape_text(t):
    """转义普通文本；跳过 $...$ 数学内容（不转义 _ { } 等）。"""
    out = []
    i = 0
    n = len(t)
    while i < n:
        ch = t[i]
        if ch == '$':
            # 复制整个数学片段（$...$ 或 $$...$$）原样保留
            j = i
            j += 2 if (i + 1 < n and t[i+1] == '$') else 1
            # 找到配对的结束符
            end = i + (2 if (i + 1 < n and t[i+1] == '$') else 1)
            while end < n:
                if t[end] == '$':
                    if end + 1 < n and t[end+1] == '$':
                        end += 2
                    else:
                        end += 1
                    break
                end += 1
            out.append(t[i:end])
            i = end
            continue
        # 先处理 unicode 数学符号（替换为 math 片段）
        if ch in _UNICODE:
            out.append(_UNICODE[ch])
            i += 1
            continue
        # md 标记去掉
        if ch == '*' and i + 1 < n and t[i+1] == '*':
            out.append('')
            i += 2
            continue
        if ch == '`':
            i += 1
            continue
        # 普通转义
        if ch in _ESCAPE:
            out.append(_ESCAPE[ch])
        else:
            out.append(ch)
        i += 1
    return ''.join(out)


out = [header]
in_table = False
table_caption = None
figure_caption = None
in_ref = False

for ln in lines:
    stripped = ln.strip()

    # ---- 公式块（整行 $$...$$）----
    if stripped.startswith('$$') and stripped.endswith('$$'):
        if in_table:
            out.append(r"\bottomrule")
            out.append(r"\end{tabular}}")
            out.append(r"\end{table}")
            in_table = False
        body = stripped[2:-2].strip()
        out.append(r"\begin{equation}")
        out.append(body)
        out.append(r"\end{equation}")
        continue

    # ---- 行内公式独占一行（$...$ 但不含 $$）----
    if stripped.startswith('$') and stripped.endswith('$') and not stripped.startswith('$$'):
        if in_table:
            out.append(r"\bottomrule")
            out.append(r"\end{tabular}}")
            out.append(r"\end{table}")
            in_table = False
        out.append(stripped)
        continue

    # ---- 图片行 ----
    img_m = re.match(r'!\[([^\]]*)\]\(([^)]+)\)', stripped)
    if img_m:
        if in_table:
            out.append(r"\bottomrule")
            out.append(r"\end{tabular}}")
            out.append(r"\end{table}")
            in_table = False
        cap = figure_caption or table_caption or img_m.group(1)
        out.append(r"\begin{figure}[htbp]")
        out.append(r"\centering")
        out.append(r"\includegraphics[width=0.7\textwidth]{" + img_m.group(2) + r"}")
        out.append(r"\caption{" + escape_text(cap) + r"}")
        out.append(r"\label{fig:" + str(len([l for l in out if l.startswith(r'\label{fig')])) + r"}")
        out.append(r"\end{figure}")
        figure_caption = None
        table_caption = None
        continue

    # ---- 表格行 ----
    if stripped.startswith('|') and stripped.endswith('|'):
        if not in_table:
            n_cols = stripped.count('|') - 1
            col_spec = 'l' + 'r' * (n_cols - 1) if n_cols > 1 else 'l'
            out.append(r"\begin{table}[htbp]")
            out.append(r"\centering")
            if table_caption:
                out.append(r"\caption{" + escape_text(table_caption) + r"}")
            out.append(r"\resizebox{\textwidth}{!}{%")
            out.append(r"\begin{tabular}{" + col_spec + r"}")
            out.append(r"\toprule")
            in_table = True
            table_caption = None
        # 分隔行
        if set(stripped.replace('|', '').replace(':', '').replace('-', '').strip()) == set():
            out.append(r"\midrule")
            continue
        else:
            cells = [c.strip() for c in stripped.strip('|').split('|')]
            cells_tex = [escape_text(c) for c in cells]
            out.append(' & '.join(cells_tex) + r' \\')
        continue
    else:
        if in_table:
            out.append(r"\bottomrule")
            out.append(r"\end{tabular}}")
            out.append(r"\end{table}")
            in_table = False

    # ---- 参考文献列表 ----
    ref_m = re.match(r'^\[(\d+)\]\s+(.+)$', stripped)
    if ref_m:
        if not in_ref:
            out.append(r"\begin{thebibliography}{99}")
            in_ref = True
        out.append(r"\bibitem{r" + ref_m.group(1) + r"} " + escape_text(ref_m.group(2)))
        continue
    else:
        # 空行在参考文献块内仅跳过，不结束
        if in_ref and stripped == '':
            continue
        if in_ref:
            out.append(r"\end{thebibliography}")
            in_ref = False

    # ---- 表标题（**表 X：...**，可带说明）----
    cap_m = re.match(r'^\*\*(表\s*[A-Z0-9IVX]+[：:][^*]*)\*\*\s*(.*)$', stripped)
    if cap_m and not in_table:
        cap_body = cap_m.group(1) + (cap_m.group(2) or '')
        table_caption = cap_body.strip()
        continue
    # ---- 图标题（**图 X：...**，可带说明，说明并入图注）----
    fig_m = re.match(r'^\*\*(图\s*\d+[：:][^*]*)\*\*\s*(.*)$', stripped)
    if fig_m:
        cap_body = fig_m.group(1) + (fig_m.group(2) or '')
        figure_caption = cap_body.strip()
        continue

    # ---- 标题 ----
    def strip_title(s):
        s = re.sub(r'\s*[（(][A-Za-z][A-Za-z0-9\s\-,./]*[)）]\s*$', '', s)
        return s.strip()

    if stripped.startswith('### '):
        out.append(r"\subsection*{" + strip_title(stripped[4:]) + "}")
    elif stripped.startswith('## '):
        out.append(r"\section*{" + strip_title(stripped[3:]) + "}")
    elif stripped.startswith('# '):
        out.append(r"\section*{" + strip_title(stripped[2:]) + "}")
    # 水平线
    elif stripped == '---' or stripped == '***':
        out.append(r"\bigskip\hrule\bigskip")
    # 列表项
    elif re.match(r'^[-*]\s+', stripped):
        out.append(r"\begin{itemize}")
        out.append(r"\item " + escape_text(re.sub(r'^[-*]\s+', '', stripped)))
        out.append(r"\end{itemize}")
    elif re.match(r'^\d+\.\s+', stripped):
        out.append(r"\begin{enumerate}")
        out.append(r"\item " + escape_text(re.sub(r'^\d+\.\s+', '', stripped)))
        out.append(r"\end{enumerate}")
    # 普通段落
    elif stripped:
        out.append(escape_text(stripped) + '\n')
    else:
        out.append('\n')

if in_table:
    out.append(r"\bottomrule")
    out.append(r"\end{tabular}}")
    out.append(r"\end{table}")
if in_ref:
    out.append(r"\end{thebibliography}")

out.append(r"\end{document}")
tex = '\n'.join(out)

tex_path = Path("/mnt/d/Code/MultiAgent/traffic_rl_project/docs/ITSC_PAPER_CN.tex")
tex_path.write_text(tex, encoding='utf-8')
print(f"已生成: {tex_path.name} ({len(tex)} chars)")
