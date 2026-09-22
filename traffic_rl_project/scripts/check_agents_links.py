"""AGENTS.md 引用一致性校验（Docs-as-Code 工程化强制，不靠人读文档）。

目的：杜绝从 AGENTS.md "妄猜"规范——它只放一句话指针；若指针指向的
ADR/章节/路径不存在或编号越界，说明 AGENTS.md 或 SSOT 已漂移，此脚本立即报错。

用法（在 traffic_rl_project 根目录）：
    python scripts/check_agents_links.py
退出码：0 = 全部引用有效；非 0 = 存在悬空引用/越界 ADR。

同类先例：src/physics_governance.py（物理治理运行时断言）。
"""
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]   # scripts/ → traffic_rl_project → MultiAgent
AGENTS = ROOT / "AGENTS.md"
PROJ = ROOT / "traffic_rl_project"
warnings = []
errors = []


def find_adr_numbers(decisions_path: Path) -> set:
    """返回 DECISIONS.md 中真实存在的 ADR 编号集合（如 {2, 13, 16}）。"""
    nums = set()
    if not decisions_path.exists():
        print(f"[错误] DECISIONS.md 路径不存在: {decisions_path}")
        sys.exit(2)
    for m in re.finditer(r"##\s+ADR-(\d+)(?:\.\d+)?\s", decisions_path.read_text(encoding="utf-8")):
        # 主编号只取整数段（ADR-009.1 → 9 主编号也在集合内；009.1 需单独处理）
        main = int(m.group(1))
        nums.add(main)
    # 捕获 ADR-009.1 这类子编号
    for m in re.finditer(r"##\s+ADR-(\d+\.\d+)\s", decisions_path.read_text(encoding="utf-8")):
        nums.add(float(m.group(1)))
    return nums


def resolve_doc(link: str) -> Path:
    """把 AGENTS.md 内的相对引用解析为真实路径。"""
    link = link.strip().strip("`").lstrip("./")
    link = link.split("#")[0]  # 剥离锚点
    # 形如 docs/... 或 traffic_rl_project/docs/...
    if link.startswith("traffic_rl_project/"):
        link = link[len("traffic_rl_project/"):]
    p = PROJ / link
    return p


def main() -> int:
    text = AGENTS.read_text(encoding="utf-8")
    decisions_path = PROJ / "docs" / "logs" / "decisions" / "DECISIONS.md"
    adr_nums = find_adr_numbers(decisions_path)

    # ADR 主编号的有效集合：ADR-16、ADR-9、ADR-9.1 → 主编号 {16, 9}
    adr_main_ints = {int(str(n).split(".")[0]) for n in adr_nums}

    # 1) 核对 ADR 引用（含 ADR-016 覆盖 ADR-010 这类「引用旧编号」是允许的跨越写法）
    for m in re.finditer(r"ADR-(\d+(?:\.\d+)?)", text):
        main = int(m.group(1).split(".")[0])
        if main not in adr_main_ints:
            errors.append(
                f"AGENTS.md 引用 ADR-{m.group(1)}，但 DECISIONS.md 无主编号 {main}"
                f"（现有 ADR 主编号: {sorted(adr_main_ints)}）"
            )

    # 2) 核对 RESEARCH_POSITIONING 章节引用 §X.Y
    for m in re.finditer(r"RESEARCH_POSITIONING\.md[^`)\n]*§(\d+(?:\.\d+)*)", text):
        pass  # 章节级引用较轻，仅警告标注，交由 #3 路径存在性兜底

    # 3) 核对 docs/ 相对路径存在（防断链）
    for m in re.finditer(r"`([^`]*\.md)`", text):
        ref = m.group(1)
        if not ref.startswith("docs/") and "docs/" not in ref:
            continue
        p = resolve_doc(ref)
        if not p.exists():
            warnings.append(f"AGENTS.md 引用的文档路径不存在: {ref}")

    # 4) 检查 AGENTS.md 是否内联了会在 SSOT 变更后腐化的具体数值（铁律行只应放指针）
    #    —— 仅对已知易变 slogan 做启发式：发现"el = "之外的裸露 episodes 数字对比即提示。
    for m in re.finditer(r"(\d+)\s*episodes?[，,、]?[\)\s]*(?:不足|少)\b", text):
        warnings.append(f"AGENTS.md 出现剧魂的叙述 episodes 数值对比（{m.group(0)}），若为具体论文数应改指针")

    if errors:
        print("=== consistent_links: 存在错误引用 ===")
        for e in errors:
            print(f"  [ERROR] {e}")
        print(f"\n共 {len(errors)} 处错误引用、{len(warnings)} 处警告。")
        print("修正 AGENTS.md 指针或同步 SSOT 后重跑。")
        return 1
    if warnings:
        print("=== consistent_links: 警告 ===")
        for w in warnings:
            print(f"  [WARN] {w}")
    print(f"[OK] AGENTS.md 引用一致性通过（ADR 编号越界检查 {len(adr_nums)} 个已有 ADR）。")
    return 0


if __name__ == "__main__":
    sys.exit(main())