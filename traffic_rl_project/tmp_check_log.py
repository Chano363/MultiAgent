"""临时脚本：检查长训日志文件状态。用后即删。"""
import os
p = "outputs/results/baseline_10kt_300ep.log"
if os.path.exists(p):
    print("文件存在，大小:", os.path.getsize(p))
    with open(p, encoding='utf-8', errors='replace') as f:
        lines = f.readlines()
    print("总行数:", len(lines))
    print("=== 末尾 25 行 ===")
    print("".join(lines[-25:]))
else:
    print("日志文件不存在")
