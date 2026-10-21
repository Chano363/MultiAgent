"""claim 渲染器：把 CLAIM_LEDGER.yaml 的权威措辞渲染进 SSOT 的受控区块。

为什么不用"禁止手写"的规矩，而用渲染：
    规矩可以被绕过；**被覆盖的区块不会被绕过**——手改的内容下次 --write 即消失。
    这是"杜绝抄写"的机械实现（同 outputs/ 不许覆写历史是同一类约束）。

块语法（只允许出现在 SSOT 文件里）：
    <!-- claim:C-LIT-01 begin -->
    （脚本生成的内容；手改无效）
    <!-- claim:C-LIT-01 end -->

用法（在 traffic_rl_project/ 下）：
    python scripts/render_claims.py --check   # 校验区块 == 台账（默认行为）
    python scripts/render_claims.py --write   # 用台账覆盖区块内容
退出码：0 = 一致；1 = 区块漂移/标记不成对；2 = 环境问题。
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PROJ = ROOT / "traffic_rl_project"
LEDGER = PROJ / "docs" / "CLAIM_LEDGER.yaml"

# 只有 SSOT 可以承载渲染区块（临时工具文档一律不接）
TARGETS = [
    PROJ / "docs" / "RESEARCH_POSITIONING.md",
]

BLOCK_RE = re.compile(
    r"(?P<begin><!--\s*claim:(?P<cid>[A-Za-z0-9\-]+)\s*begin\s*-->)"
    r"(?P<body>.*?)"
    r"(?P<end><!--\s*claim:(?P=cid)\s*end\s*-->)",
    re.S,
)

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")


def read_text(p: Path) -> str:
    return p.read_text(encoding="utf-8", errors="ignore").replace("\x00", "")


def load_claims() -> dict:
    try:
        import yaml  # noqa: PLC0415
    except ImportError:
        print("[ERROR] 需要 PyYAML：pip install pyyaml")
        sys.exit(2)
    if not LEDGER.exists():
        print(f"[ERROR] 台账不存在：{LEDGER}")
        sys.exit(2)
    data = yaml.safe_load(read_text(LEDGER)) or {}
    out = {}
    for c in data.get("claims", []):
        stmt = re.sub(r"\s+", " ", str(c.get("statement", ""))).strip()
        # 折叠 YAML 折行留下的多余空格：中文标点两侧不留空格
        stmt = re.sub(r"\s+([，。；：、？！）」】])", r"\1", stmt)
        stmt = re.sub(r"([（「【，。；：、])\s+", r"\1", stmt)
        out[c["id"]] = stmt
    return out


def render_body(cid: str, stmt: str) -> str:
    return f"\n- **{cid}**：{stmt}\n"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--write", action="store_true", help="用台账覆盖区块内容")
    args = ap.parse_args()

    claims = load_claims()
    drift = 0
    unknown = 0
    blocks = 0

    for path in TARGETS:
        if not path.exists():
            print(f"[ERROR] SSOT 不存在：{path}")
            return 2
        text = read_text(path)
        matches = list(BLOCK_RE.finditer(text))
        # 倒序替换：避免前面的替换改变后面区块的偏移量
        for m in reversed(matches):
            blocks += 1
            cid = m.group("cid")
            if cid not in claims:
                print(f"[ERROR] {path.name} 引用了台账中不存在的 claim：{cid}")
                unknown += 1
                continue
            expected = render_body(cid, claims[cid])
            if m.group("body").strip() == expected.strip():
                continue
            drift += 1
            if args.write:
                text = text[: m.start("body")] + expected + text[m.end("body"):]
                print(f"[FIX] {path.name} 区块 {cid} 已按台账重写")
        if args.write and drift:
            path.write_text(text, encoding="utf-8")

    # 反向检查：台账里的 claim 是否都在 SSOT 中渲染出来（防止"台账加了、正文没落"）
    rendered_ids = set()
    for path in TARGETS:
        if path.exists():
            rendered_ids |= {m.group("cid") for m in BLOCK_RE.finditer(read_text(path))}
    missing = [cid for cid in claims if cid not in rendered_ids]
    if missing:
        print(f"[ERROR] 台账有 {len(missing)} 条 claim 未在 SSOT 渲染：{', '.join(missing)}")
        print("        fix: 在 §1.2 加 <!-- claim:<ID> begin/end --> 标记后跑 --write")

    if unknown or missing:
        return 1
    if drift and not args.write:
        print(f"\n共 {blocks} 个区块，{drift} 个漂移。fix: python scripts/render_claims.py --write")
        return 1
    print(f"[OK] {blocks} 个 claim 区块与台账一致（台账 {len(claims)} 条）。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
