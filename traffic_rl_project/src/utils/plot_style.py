"""matplotlib 中文字体配置（论文/汇报插图统一入口）。

WSL 的 conda 环境默认无 CJK 字体（只有 DejaVu），中文标签会渲染成方块
（Glyph missing from font(s) DejaVu Sans）。本项目所有插图（训练曲线、
轨迹对比图等）在绘图前调用 setup_cjk_font()，自动注册系统可用的中文字体：
优先 Windows 字体（WSL 可访问 /mnt/c/Windows/Fonts），其次 Linux Noto CJK。
"""
from pathlib import Path

# 候选字体路径（按优先级）：Windows 雅黑/黑体 → Linux Noto/SimHei
CJK_FONT_CANDIDATES = [
    ('/mnt/c/Windows/Fonts/msyh.ttc', 'Microsoft YaHei'),
    ('/mnt/c/Windows/Fonts/msyhbd.ttc', 'Microsoft YaHei'),
    ('/mnt/c/Windows/Fonts/simhei.ttf', 'SimHei'),
    ('/mnt/c/Windows/Fonts/simsun.ttc', 'SimSun'),
    ('/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc', 'Noto Sans CJK JP'),
    ('/usr/share/fonts/truetype/wqy/wqy-zenhei.ttc', 'WenQuanYi Zen Hei'),
]

_configured = False


def setup_cjk_font(verbose: bool = False):
    """注册并设置 matplotlib 中文字体，返回实际使用的字体名（失败返回 None）。"""
    global _configured
    import matplotlib
    import matplotlib.font_manager as fm

    if not _configured:
        available = {f.name for f in fm.fontManager.ttflist}
        for path, name in CJK_FONT_CANDIDATES:
            if Path(path).exists():
                if name not in available:
                    try:
                        fm.fontManager.addfont(path)
                        available = {f.name for f in fm.fontManager.ttflist}
                    except Exception:
                        continue
                if name in available:
                    matplotlib.rcParams['font.sans-serif'] = [name] + list(
                        matplotlib.rcParams.get('font.sans-serif', []))
                    # 解决负号显示为方块
                    matplotlib.rcParams['axes.unicode_minus'] = False
                    _configured = True
                    if verbose:
                        print(f"[plot_style] 中文字体: {name} ({path})")
                    return name
        _configured = True  # 无 CJK 字体也不再重复尝试
        if verbose:
            print("[plot_style] 未找到中文字体，中文标签可能显示为方块")
        return None
    return matplotlib.rcParams.get('font.sans-serif', [None])[0]
