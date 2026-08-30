"""验证中文字体渲染（生成测试图，肉眼确认无方块）。"""
import sys
from pathlib import Path
sys.path.append(str(Path(__file__).parent.parent.parent))

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from src.utils.plot_style import setup_cjk_font

name = setup_cjk_font(verbose=True)
fig, ax = plt.subplots(figsize=(6, 3))
ax.plot([1, 2, 3], [1, 4, 2], label='车钩力峰值')
ax.set_xlabel('训练回合')
ax.set_ylabel('车钩力 (kN)')
ax.set_title('中文标签渲染测试：循环制动协同')
ax.legend()
fig.tight_layout()
out = Path('outputs/figures/_font_test.png')
out.parent.mkdir(parents=True, exist_ok=True)
fig.savefig(out, dpi=120)
print("已生成:", out, "| 字体:", name)
