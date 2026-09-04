r"""把 ITSC_PAPER_中文对照.md 转成 LaTeX（支持中文 + 公式 + 图 + 表格），用 tectonic 编译。

修复（v2）：
- 累积列表项（同一环境的 \item 连续输出，不重复 \begin/\end）
- 块引用 > 用 quote 环境
- 单星号斜体 *xxx* → \textit{xxx}
- 表格列规格 l（不强制 resizebox）
- caption 去掉"表 I/图 N："前缀，让 LaTeX 自动编号
- 公式剥离手写 \qquad \text{(N)}，用 equation 自动编号
- 负号不额外空格
- 中文段首缩进 2em
- 标题区只输出一次（去 \maketitle）

数学内容($...$)不做 LaTeX 特殊字符转义；普通文本转义。
"""
import re
from pathlib import Path

import os, sys
# 兼容 WSL 和 Windows 两种调用
def _resolve(path):
    p = Path(path)
    if p.exists():
        return p
    # 尝试 WSL 风格 /mnt/d/...
    alt = Path("/mnt/d/" + path.replace("D:\\", "").replace("D:/", "").replace("\\", "/"))
    if alt.exists():
        return alt
    raise FileNotFoundError(path)

_md_path = "D:\\Code\\MultiAgent\\traffic_rl_project\\docs\\ITSC_PAPER_中文对照.md"
md = _resolve(_md_path).read_text(encoding='utf-8')
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
\usepackage{indentfirst}
\usepackage{caption}
% 中文段首缩进 2em
\setlength{\parindent}{2em}
% 中文论文标准字体：正文宋体(SimSun)、标题黑体(SimHei)、加粗用黑体
\setCJKmainfont[Path=/mnt/c/Windows/Fonts/, BoldFont=simhei.ttf]{simsun.ttc}
\setCJKsansfont[Path=/mnt/c/Windows/Fonts/]{simhei.ttf}
\setmainfont[Path=/mnt/c/Windows/Fonts/, BoldFont=simhei.ttf]{simsun.ttc}
% 标题使用黑体（sans）
\makeatletter
\renewcommand{\section}{\@startsection{section}{1}{\z@}{-3.5ex \@plus -1ex \@minus -.2ex}{2.3ex \@plus .2ex}{\normalfont\large\bfseries\sffamily}}
\renewcommand{\subsection}{\@startsection{subsection}{2}{\z@}{-3.25ex\@plus -1ex \@minus -.2ex}{1.5ex \@plus .2ex}{\normalfont\normalsize\bfseries\sffamily}}
\makeatother
% caption 格式
\captionsetup{font=small,labelsep=colon}
% 表编号用罗马数字（与正文"表 I/II/III…"一致；图号保持阿拉伯数字）
\renewcommand{\thetable}{\Roman{table}}
\begin{document}
"""

_ESCAPE = {
    '{': r'\{', '}': r'\}',
    '_': r'\_', '%': r'\%',
    '#': r'\#', '&': r'\&',
}
_UNICODE = {
    '‰': r'\textperthousand',
    '→': r'$\rightarrow$',
    '≤': r'$\leq$',
    '≥': r'$\geq$',
    '±': r'$\pm$',
    '×': r'$\times$',
    '\u2212': r'$-$',
}
# 数学片段（$...$ 或 $$...$$），转义时需原样跳过
_MATH_SPAN = re.compile(r'\$\$?[^$]*?\$\$?')


def _escape_plain(s):
    """转义一段纯文本：LaTeX 特殊字符 + Unicode 符号 + 比较符。

    供 escape_text 主循环与 \\textbf / \\textit 内部复用，避免加粗/斜体
    片段里的 ± → ≤ ≥ < > 等漏转义（< > 在 OT1 下会渲染成 ¡ ¿）。
    内含的 $...$ 数学片段原样保留，不被转义。
    """
    out, last = [], 0
    for m in _MATH_SPAN.finditer(s):
        out.append(_escape_chars(s[last:m.start()]))
        out.append(m.group(0))
        last = m.end()
    out.append(_escape_chars(s[last:]))
    return ''.join(out)


def _escape_chars(s):
    """逐字符转义纯文本（无数学内容）。"""
    out = []
    for c in s:
        # < > 在文本模式（OT1）会渲染成 ¡ ¿，必须放进数学模式
        if c == '<':
            out.append('$<$')
        elif c == '>':
            out.append('$>$')
        elif c in _UNICODE:
            out.append(_UNICODE[c])
        elif c in _ESCAPE:
            out.append(_ESCAPE[c])
        else:
            out.append(c)
    return ''.join(out)


def escape_text(t):
    """转义普通文本；跳过 $...$ 数学内容（不转义 _ { } 等）；单星号斜体。"""
    out = []
    i = 0
    n = len(t)
    while i < n:
        ch = t[i]
        if ch == '$':
            # 复制整个数学片段（$...$ 或 $$...$$）原样保留
            j = i
            j += 2 if (i + 1 < n and t[i+1] == '$') else 1
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
        # 单星号斜体 *xxx*  →  \textit{xxx}  （不在 $...$ 内）
        if ch == '*' and not (i + 1 < n and t[i+1] == '*') and not (i > 0 and t[i-1] == '*'):
            # 找下一个 *
            k = i + 1
            while k < n and t[k] != '*':
                k += 1
            if k < n:
                inner = t[i+1:k]
                out.append(r'\textit{' + _escape_plain(inner) + '}')
                i = k + 1
                continue
        # 双星号加粗 **xxx**  →  \textbf{xxx}
        if ch == '*' and i + 1 < n and t[i+1] == '*':
            k = i + 2
            while k + 1 < n and not (t[k] == '*' and t[k+1] == '*'):
                k += 1
            if k + 1 < n:
                inner = t[i+2:k]
                out.append(r'\textbf{' + _escape_plain(inner) + '}')
                i = k + 2
                continue
        if ch == '`':
            i += 1
            continue
        # < > 在文本模式（OT1）会渲染成 ¡ ¿，必须放进数学模式
        if ch == '<':
            out.append('$<$')
            i += 1
            continue
        if ch == '>':
            out.append('$>$')
            i += 1
            continue
        if ch in _UNICODE:
            out.append(_UNICODE[ch])
            i += 1
            continue
        if ch in _ESCAPE:
            out.append(_ESCAPE[ch])
        else:
            out.append(ch)
        i += 1
    return ''.join(out)


def strip_caption_prefix(s):
    """去掉 caption 里的 '表 I：' / '图 1：' 前缀（让 LaTeX 自动加 '表 1:' 编号）。"""
    return re.sub(r'^(表|图)\s*[A-Za-z0-9IVX]+\s*[：:]\s*', '', s).strip()


_CITE_PAT = re.compile(r'(?<![\w。．])\[(\d{1,2})\](?![\w])')
# 需要占更大版心的宽图（文件名含这些关键字）
_WIDE_FIGS = ("combo",)


def add_cites(s):
    """把正文文献引用 [N] 转成 \\cite{rN}；保护 $...$ 数学内容不被误替换。

    仅匹配 1-2 位纯数字的 [N]，避开 [40,80]、[-1,1] 这类区间/数学写法。
    """
    out, last = [], 0
    for m in _MATH_SPAN.finditer(s):
        out.append(_CITE_PAT.sub(r'\\cite{r\1}', s[last:m.start()]))
        out.append(m.group(0))
        last = m.end()
    out.append(_CITE_PAT.sub(r'\\cite{r\1}', s[last:]))
    return ''.join(out)


_THOUSANDS = re.compile(r'(?<![\w.,])(\d{1,3}(?:,\d{3})+)(?![\w,])')


def protect_thousands(s):
    r"""千分位逗号加 {} 保护：+67,597 → +67{,}597（避免逗号后额外间距）。

    只匹配严格的 \d,\d{3} 千分位，不误伤 [40,80]、[0.0, 7.1] 这类区间。
    """
    return _THOUSANDS.sub(lambda m: m.group(1).replace(',', '{,}'), s)


def esc(s, cite=True):
    """escape_text + 引用转换 + 千分位保护（参考文献条目 cite=False）。"""
    t = escape_text(s)
    t = add_cites(t) if cite else t
    return protect_thousands(t)


out = [header]
in_table = False
table_caption = None
figure_caption = None
in_ref = False
in_quote = False
# 列表状态：None / 'enum' / 'item'
list_state = None


def close_list():
    global list_state
    if list_state == 'enum':
        out.append(r"\end{enumerate}")
    elif list_state == 'item':
        out.append(r"\end{itemize}")
    list_state = None


def close_quote():
    global in_quote
    if in_quote:
        out.append(r"\end{quote}")
        in_quote = False


for ln in lines:
    stripped = ln.strip()

    # 块引用 > xxx
    if stripped.startswith('>'):
        close_list()
        if not in_quote:
            out.append(r"\begin{quote}")
            in_quote = True
        body = re.sub(r'^>\s?', '', stripped)
        out.append(esc(body) + '\n')
        continue
    else:
        if in_quote:
            close_quote()

    # 公式块（整行 $$...$$）
    if stripped.startswith('$$') and stripped.endswith('$$') and len(stripped) > 4:
        close_list()
        body = stripped[2:-2].strip()
        # 去掉手写编号 \qquad \text{(N)} （让 equation 自动编号）
        body = re.sub(r'\\qquad\s*\\text\{\((\d+)\)\}\s*$', '', body).strip()
        out.append(r"\begin{equation}")
        out.append(body)
        out.append(r"\end{equation}")
        continue

    # 行内公式独占一行（$...$ 但不含 $$）
    if stripped.startswith('$') and stripped.endswith('$') and not stripped.startswith('$$') and len(stripped) > 2:
        close_list()
        out.append(stripped)
        continue

    # 图片行
    img_m = re.match(r'!\[([^\]]*)\]\(([^)]+)\)', stripped)
    if img_m:
        close_list()
        if in_table:
            out.append(r"\bottomrule")
            out.append(r"\end{tabular}")
            out.append(r"\end{table}")
            in_table = False
        cap_raw = figure_caption or table_caption or img_m.group(1)
        cap = strip_caption_prefix(cap_raw)
        # 图编号 1-based（正文用"图 1/2/3…"）
        n_fig = sum(1 for l in out if l.startswith(r'\begin{figure}')) + 1
        # 宽图（三联子图等）占更大版心，保证子图可读
        fig_w = "0.95" if any(k in img_m.group(2) for k in _WIDE_FIGS) else "0.78"
        out.append(r"\begin{figure}[htbp]")
        out.append(r"\centering")
        out.append(r"\includegraphics[width=" + fig_w + r"\textwidth]{" + img_m.group(2) + r"}")
        out.append(r"\caption{" + esc(cap) + r"}")
        out.append(r"\label{fig:" + str(n_fig) + r"}")
        out.append(r"\end{figure}")
        figure_caption = None
        table_caption = None
        continue

    # 表格行
    if stripped.startswith('|') and stripped.endswith('|'):
        close_list()
        if not in_table:
            n_cols = stripped.count('|') - 1
            col_spec = 'l' * n_cols if n_cols > 0 else 'l'
            out.append(r"\begin{table}[htbp]")
            out.append(r"\centering")
            if table_caption:
                cap = strip_caption_prefix(table_caption)
                out.append(r"\caption{" + esc(cap) + r"}")
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
            cells_tex = [esc(c) for c in cells]
            out.append(' & '.join(cells_tex) + r' \\')
        continue
    else:
        if in_table:
            out.append(r"\bottomrule")
            out.append(r"\end{tabular}")
            out.append(r"\end{table}")
            in_table = False

    # 参考文献列表
    ref_m = re.match(r'^\[(\d+)\]\s+(.+)$', stripped)
    if ref_m:
        close_list()
        if not in_ref:
            out.append(r"\begin{thebibliography}{99}")
            in_ref = True
        # 条目里的 *xxx* 已是 markdown 斜体，转 LaTeX
        out.append(r"\bibitem{r" + ref_m.group(1) + r"} " + escape_text(ref_m.group(2)))
        continue
    else:
        if in_ref and stripped == '':
            continue
        if in_ref:
            out.append(r"\end{thebibliography}")
            in_ref = False

    # 表标题（**表 X：...**）
    cap_m = re.match(r'^\*\*(表\s*[A-Z0-9IVX]+[：:][^*]*)\*\*\s*(.*)$', stripped)
    if cap_m and not in_table:
        close_list()
        cap_body = cap_m.group(1) + (cap_m.group(2) or '')
        table_caption = cap_body.strip()
        continue
    # 图标题（**图 X：...**）
    fig_m = re.match(r'^\*\*(图\s*\d+[：:][^*]*)\*\*\s*(.*)$', stripped)
    if fig_m:
        close_list()
        cap_body = fig_m.group(1) + (fig_m.group(2) or '')
        figure_caption = cap_body.strip()
        continue

    # 标题
    def strip_title(s):
        s = re.sub(r'\s*[（(][A-Za-z][A-Za-z0-9\s\-,./]*[)）]\s*$', '', s)
        return s.strip()

    if stripped.startswith('### '):
        close_list()
        out.append(r"\subsection*{" + strip_title(stripped[4:]) + "}")
    elif stripped.startswith('## '):
        close_list()
        out.append(r"\section*{" + strip_title(stripped[3:]) + "}")
    elif stripped.startswith('# '):
        close_list()
        out.append(r"\section*{" + strip_title(stripped[2:]) + "}")
    # 水平线
    elif stripped == '---' or stripped == '***':
        close_list()
        out.append(r"\bigskip\hrule\bigskip")
    # 列表项（累积）
    elif re.match(r'^[-*]\s+', stripped):
        if list_state != 'item':
            close_list()
            out.append(r"\begin{itemize}")
            list_state = 'item'
        out.append(r"\item " + esc(re.sub(r'^[-*]\s+', '', stripped)))
    elif re.match(r'^\d+\.\s+', stripped):
        if list_state != 'enum':
            close_list()
            out.append(r"\begin{enumerate}")
            list_state = 'enum'
        out.append(r"\item " + esc(re.sub(r'^\d+\.\s+', '', stripped)))
    # 普通段落
    elif stripped:
        close_list()
        out.append(esc(stripped) + '\n')
    else:
        # 空行：保留为空行（不立刻关闭列表项，让跨空行的连续列表项累积）
        out.append('')

# 收尾
close_list()
close_quote()
if in_table:
    out.append(r"\bottomrule")
    out.append(r"\end{tabular}")
    out.append(r"\end{table}")
if in_ref:
    out.append(r"\end{thebibliography}")

out.append(r"\end{document}")
tex = '\n'.join(out)

_tex_path = "D:\\Code\\MultiAgent\\traffic_rl_project\\docs\\ITSC_PAPER_CN.tex"
tex_path = _resolve(_tex_path)
tex_path.write_text(tex, encoding='utf-8')
print(f"已生成: {tex_path.name} ({len(tex)} chars)")
