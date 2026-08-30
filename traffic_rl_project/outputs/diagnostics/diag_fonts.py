import collections
import matplotlib.font_manager as fm

names = [f.name for f in fm.fontManager.ttflist]
cjk = [n for n in collections.Counter(names)
       if any(k in n.lower() for k in ('cjk', 'hei', 'yahei', 'song', 'noto', 'wqy', 'source han'))]
print("CJK 候选字体:", cjk if cjk else "无")
print("字体总数:", len(set(names)))
print("前5个:", list(collections.Counter(names))[:5])
