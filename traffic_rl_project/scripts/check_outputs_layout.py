"""outputs/ 产物目录布局校验（机器守卫，不靠人读规范）。

目的：既有防卫（`run_training.py` 的 dirs 校验、`official_entry_guard`、
`training_metadata_guard`）全在"Python 入口内"，只能拦住走入口的写法；
而历史上 92 个散文件是"临时脚本 + shell 重定向"（`python tmp_x.py | tee
outputs/log_x.txt`）产生的，绕过了所有入口。本脚本不看"谁写的"，只看
"落在哪里"，因而对任意写法都有效（规范见 EXECUTION_RULES「产物目录规范」）。

用法（在 traffic_rl_project 根目录）：
    python scripts/check_outputs_layout.py            # 校验；退出码 0 = 合规
    python scripts/check_outputs_layout.py --strict   # 遗留待迁移目录也算错误
退出码：0 = 合规（可能含待迁移 WARN）；1 = 存在违规；2 = outputs/ 不存在。

同类先例：scripts/check_agents_links.py（文档引用卫生）。
"""
import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]   # scripts/ → traffic_rl_project
OUTPUTS = ROOT / "outputs"

# 目标一级分类（EXECUTION_RULES §「产物目录规范」目标树）——只按"产物是什么"分组
CANONICAL_TOP = {
    "checkpoints",      # 模型权重
    "results",          # 结果 JSON/CSV
    "figures",          # 展示/论文图（策展，允许覆盖）
    "logs",             # 训练日志 + tensorboard
    "sim_validation",   # 物理仿真验证
    "smoke",            # 冒烟/调试产物（可删）
    "deprecated",       # 作废资产
}

# 遗留一级目录 → 目标落点（EXECUTION_RULES §4 映射表）。
# P2 全量迁移已于 2026-10-08 完成，故本表清空；此后任何非目标树的一级目录
# 一律判为 ERROR（无需 --strict）。若再次出现迁移期，可临时回填本表。
LEGACY_TOP = {}


def check(strict: bool = False):
    """返回 (errors, warnings)。errors 非空即违规。"""
    errors, warnings = [], []
    if not OUTPUTS.is_dir():
        raise FileNotFoundError(f"outputs/ 不存在: {OUTPUTS}")

    # R1：outputs/ 根级不得出现任何普通文件（历史 92 个散文件的直接病灶）
    for p in sorted(OUTPUTS.iterdir()):
        if p.is_file():
            errors.append(
                f"outputs/ 根级出现散文件: {p.name}"
                f"（须落 <类别>/<实验线>/<run>/，见规范 R1）"
            )

    # 一级目录：目标树之内 / 遗留待迁移 / 未知新增
    for p in sorted(OUTPUTS.iterdir()):
        if not p.is_dir():
            continue
        if p.name in CANONICAL_TOP:
            continue
        if p.name in LEGACY_TOP:
            msg = f"outputs/{p.name}/ 为遗留一级目录，目标落点 {LEGACY_TOP[p.name]}（待迁移）"
            (errors if strict else warnings).append(msg)
        else:
            errors.append(
                f"outputs/{p.name}/ 不是目标树的一级分类（规范 §1：新增一级目录必须登记本规范）"
            )
    return errors, warnings


def main() -> int:
    ap = argparse.ArgumentParser(description="校验 outputs/ 布局是否符合产物目录规范")
    ap.add_argument("--strict", action="store_true",
                    help="把「遗留待迁移目录」也算作错误（P2/P3 迁移完成后使用）")
    args = ap.parse_args()

    try:
        errors, warnings = check(strict=args.strict)
    except FileNotFoundError as e:
        print(f"[错误] {e}")
        return 2

    if errors:
        print("=== outputs_layout: 存在违规 ===")
        for e in errors:
            print(f"  [ERROR] {e}")
    if warnings:
        print("=== outputs_layout: 待迁移（历史遗留，非本次新增） ===")
        for w in warnings:
            print(f"  [WARN] {w}")
    if errors:
        print(f"\n共 {len(errors)} 处违规、{len(warnings)} 处待迁移。"
              f"修正落盘位置后重跑。")
        return 1
    print(f"[OK] outputs/ 布局合规（一级分类 = 目标树；待迁移 {len(warnings)} 项）。")
    return 0


if __name__ == "__main__":
    sys.exit(main())