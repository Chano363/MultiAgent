"""立论级 claim 台账一致性校验（机器守卫，防"知识不传导"）。

目的：把"同一个事实在 N 个文档里说法不一致"从**人肉发现**变成**脚本报错**。
同类先例：scripts/check_agents_links.py（引用一致性）、scripts/check_outputs_layout.py（产物布局）。

校验 4 件事：
  1. 禁用措辞（旧结论已被推翻/精确化）在现行文档中是否残留 —— ERROR（历史日志 docs/logs/** 降为 WARN，append-only 不回改）
  2. 台账内每条 claim 的 evidence 是否"存活"：文件存在 + 行号在范围内 + 锚词仍在该区间（防全文被移动/替换后台账变空头）
  3. 否定命题（空白/未见/无人）是否满足证据门槛：grade 必须为 A、且 search_ledger 文件必须存在
  4. 台账与 SSOT 是否同步：must_contain 的子串必须真的出现在 ssot 文件里

用法（在 traffic_rl_project/ 下）：
    python scripts/check_claim_ledger.py
    python scripts/check_claim_ledger.py --verbose
退出码：0 = 通过（允许 WARN）；非 0 = 存在 ERROR。
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]          # scripts/ → traffic_rl_project → MultiAgent
PROJ = ROOT / "traffic_rl_project"
LEDGER = PROJ / "docs" / "CLAIM_LEDGER.yaml"

# 历史日志 append-only，不要求回改；命中只提示。
# ppt_talk/report_* = 已归档的旧版汇报（ADR-042 明文"历史日志与旧版 PPT 归档不改"）。
HISTORY_GLOBS = ("docs/logs/",)

# 临时工具文档（与 PPT 大纲同质）：允许事实重复、不保证严谨。
# 规则：允许措辞不一致（只 WARN）；不得作证据源；查阅/立论引用时禁止检索；未经 owner 允许禁改。
# 实际取值以 CLAIM_LEDGER.yaml 的 meta.ephemeral_globs / meta.protected_globs 为准。
EPHEMERAL_GLOBS = ("ppt_talk/", "docs/杂项/")
PROTECTED_GLOBS = ("ppt_talk/", "docs/杂项/")

SKIP_DIRS = {"node_modules", ".git", "__pycache__", "outputs", "arxiv_src", ".codebuddy"}

# 已被证伪/已被精确化的旧措辞。命中即报错（历史日志除外）。
FORBIDDEN = [
    {
        "pattern": r"无车钩力建模",
        "claim": "C-LIT-01",
        "why": "Song2026 Tube-MPC 显式含车钩力（模型/代价/±1500kN 约束）",
    },
    {
        "pattern": r"无人在多列车组层面处理车钩力",
        "claim": "C-LIT-01/C-LIT-04",
        "why": "多列车组层面处理车钩力已有 MPC 先例（Song2026 Tube-MPC、CCDC2025 DMPC）",
    },
    {
        "pattern": r"他们缺的正是车钩约束",
        "claim": "C-LIT-01",
        "why": "Song2026 Tube-MPC 的优化器里就写着 ±1500kN 车钩力约束",
    },
    {
        "pattern": r"车钩力不进(?:奖励|目标)/(?:指标|目标)",
        "claim": "C-LIT-02",
        "why": "Song2026 MAPPO 车钩力不进奖励/观测成立，但作为安全指标进 Fig.7",
    },
    {
        "pattern": r"页面全文无[^。\n]{0,8}(?:车钩|coupler)",
        "claim": "C-LIT-02",
        "why": "该判断来自摘要页而非全文，全文 coupler 命中 20 处",
    },
    {
        "pattern": r"不含车钩力[（(]聚焦宏观运行层[）)]",
        "claim": "C-LIT-02",
        "why": "仅「奖励不含」成立；全文动力学与指标均含车钩力",
    },
    {
        "pattern": r"多列群组\s*[×x]\s*机械车钩力硬约束[^\n]{0,14}空白",
        "claim": "C-LIT-01/C-LIT-04",
        "why": "Song2026 Tube-MPC 即多列 + 机械车钩力硬约束（±1500kN）",
    },
    {
        "pattern": r"长大下坡循环制动层级\s*[×x]\s*车钩力硬约束\s*[×x]\s*多列群组",
        "claim": "C-LIT-01",
        "why": "该三元组 Song2026 Tube-MPC 全满足；差异必须落在「多列车组 × RL 决策目标」",
    },
    {
        "pattern": r"多列群组\s*[×x]\s*车钩力\s*[×x]\s*MARL",
        "claim": "C-GAP-01",
        "why": "ADR-033 已精确化为「车钩力进 RL 目标」，且该措辞已被 Song2026 MAPPO 顶破",
    },
    {
        "pattern": r"车钩力 \+ 多列群组 \+ 长大下坡[^\n]{0,20}几乎空白",
        "claim": "C-GAP-01",
        "why": "该三元组非空白（Song2026 Tube-MPC / Wang2026 / CCDC2025）",
    },
]

errors: list[str] = []
warnings: list[str] = []
checks = 0

# Windows 控制台默认 GBK，文档里的 ⚠/× 等字符会让 print 直接崩，强制 UTF-8 输出
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")


def norm(s: str) -> str:
    """去所有空白：中文全文（如 Song2026 的 PDF 抽取）字间带空格，直接比会误判。"""
    return re.sub(r"\s+", "", s)


def read_text(p: Path) -> str:
    try:
        return p.read_text(encoding="utf-8", errors="ignore").replace("\x00", "")
    except OSError:
        return ""


def iter_docs():
    yield ROOT / "AGENTS.md"
    for base in (PROJ / "docs", PROJ / "ppt_talk"):
        if not base.exists():
            continue
        for p in base.rglob("*.md"):
            if any(part in SKIP_DIRS for part in p.parts):
                continue
            yield p


def rel(p: Path) -> str:
    try:
        return str(p.relative_to(PROJ)).replace("\\", "/")
    except ValueError:
        return str(p).replace("\\", "/")


def is_history(relpath: str) -> bool:
    return any(relpath.startswith(g) for g in HISTORY_GLOBS)


def is_ephemeral(relpath: str) -> bool:
    """临时工具文档（PPT 大纲 / 杂项）：允许重复，但不作证据源。"""
    return any(relpath.startswith(g) for g in EPHEMERAL_GLOBS)


def is_protected(relpath: str) -> bool:
    return any(relpath.startswith(g) for g in PROTECTED_GLOBS)


def load_ledger() -> dict:
    try:
        import yaml  # noqa: PLC0415
    except ImportError:
        print("[ERROR] 需要 PyYAML：pip install pyyaml")
        sys.exit(2)
    if not LEDGER.exists():
        print(f"[ERROR] 台账不存在：{LEDGER}")
        sys.exit(2)
    return yaml.safe_load(read_text(LEDGER)) or {}


def check_forbidden(verbose: bool) -> None:
    global checks
    for p in iter_docs():
        if not p.exists():
            continue
        r = rel(p)
        text = read_text(p)
        lines = text.splitlines()
        for rule in FORBIDDEN:
            pat = re.compile(rule["pattern"])
            for i, line in enumerate(lines, 1):
                if not pat.search(line):
                    continue
                msg = f'[{rule["claim"]}] 禁用措辞 /{rule["pattern"]}/ —— {r}:{i} 「{line.strip()[:70]}」 | 原因：{rule["why"]}'
                if is_history(r):
                    warnings.append("（历史日志，append-only 不回改）" + msg)
                elif is_ephemeral(r):
                    warnings.append("（临时工具文档：允许重复、不作证据源）" + msg)
                else:
                    errors.append(msg)
                checks += 1
                if verbose:
                    print(f"  命中 {r}:{i}")


def check_evidence(ledger: dict) -> None:
    global checks
    for c in ledger.get("claims", []):
        cid = c.get("id", "?")
        ev = c.get("evidence") or []
        if not ev:
            # 否定命题的证据形态是"检索台账"，不是本地全文
            if not c.get("external_doi") and not c.get("search_ledger"):
                errors.append(f"[{cid}] 无本地 evidence、无 external_doi、无 search_ledger —— 空头 claim")
            checks += 1
            continue
        for e in ev:
            if is_ephemeral(e["file"]):
                errors.append(
                    f"[{cid}] 证据源不得为临时工具文档（PPT 大纲 / 杂项）：{e['file']} —— 不得作为立论依据"
                )
                continue
            f = PROJ / e["file"]
            if not f.exists():
                errors.append(f"[{cid}] evidence 文件不存在：{e['file']}")
                continue
            lines = read_text(f).splitlines()
            lo, hi = e["lines"][0], e["lines"][1]
            if hi > len(lines):
                errors.append(f"[{cid}] evidence 行号越界：{e['file']}:{lo}-{hi}（实际 {len(lines)} 行）")
                continue
            seg = norm("".join(lines[lo - 1:hi]))
            if norm(e["anchor"]) not in seg:
                errors.append(
                    f"[{cid}] evidence 锚词失效：{e['file']}:{lo}-{hi} 内未出现「{e['anchor']}」"
                    f"（全文可能已被替换/重抽取，需回验台账）"
                )
            checks += 1


def check_negative(ledger: dict) -> None:
    global checks
    for c in ledger.get("claims", []):
        if c.get("polarity") != "negative":
            continue
        cid = c.get("id", "?")
        checks += 1
        if c.get("grade") != "A":
            warnings.append(
                f"[{cid}] 否定命题 grade={c.get('grade')}（非 A/全文级）——"
                f"只能写「据系统检索未见」，禁止写「空白/首创/无人」"
            )
        sl = c.get("search_ledger")
        if sl:
            if not (PROJ / sl).exists():
                errors.append(
                    f"[{cid}] 声明了 search_ledger 但文件不存在：{sl} —— 否定命题缺检索台账，结论不可审计"
                )
        else:
            errors.append(f"[{cid}] 否定命题未挂检索台账（search_ledger）")


def check_ssot_sync(ledger: dict) -> None:
    global checks
    for c in ledger.get("claims", []):
        ssot = c.get("ssot")
        if not ssot:
            continue
        f = PROJ / ssot
        checks += 1
        if is_ephemeral(ssot):
            errors.append(f"[{c.get('id')}] SSOT 不得为临时工具文档：{ssot}")
            continue
        if not f.exists():
            errors.append(f"[{c.get('id')}] ssot 文件不存在：{ssot}")
            continue
        body = norm(read_text(f))
        for s in c.get("must_contain") or []:
            if norm(s) not in body:
                errors.append(f"[{c.get('id')}] 台账与 SSOT 不同步：{ssot} 中找不到「{s}」")


def check_protected(strict: bool) -> None:
    """受保护目录（PPT 大纲 / 杂项）未经 owner 允许不得改动 —— 用 git 脏文件检测。

    仅 --check-protected 时执行：这些目录常有 owner 自己的未提交草稿，
    默认不查以免把 owner 的编辑误报成违规。
    """
    global checks
    import subprocess

    try:
        out = subprocess.run(
            ["git", "-c", "core.quotepath=false", "status", "--porcelain"],
            cwd=ROOT, capture_output=True, text=True, timeout=30,
        ).stdout
    except (OSError, subprocess.SubprocessError):
        warnings.append("--check-protected：git 不可用，跳过受保护目录检测")
        return
    checks += 1
    for line in out.splitlines():
        p = line[3:].strip().strip('"').replace("\\", "/")
        if p.startswith("traffic_rl_project/"):
            p = p[len("traffic_rl_project/"):]
        if not is_protected(p):
            continue
        msg = f"受保护目录有未提交改动：{p}（未经 owner 允许禁止修改；如为 owner 自己的编辑请提交或说明）"
        (errors if strict else warnings).append(msg)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--verbose", action="store_true")
    ap.add_argument("--check-protected", action="store_true",
                    help="检测 ppt_talk/ 与 docs/杂项/ 是否有未提交改动")
    ap.add_argument("--strict", action="store_true",
                    help="与 --check-protected 连用：把受保护目录改动判为 ERROR")
    args = ap.parse_args()

    global EPHEMERAL_GLOBS, PROTECTED_GLOBS
    ledger = load_ledger()
    meta = ledger.get("meta") or {}
    if meta.get("ephemeral_globs"):
        EPHEMERAL_GLOBS = tuple(meta["ephemeral_globs"])
    if meta.get("protected_globs"):
        PROTECTED_GLOBS = tuple(meta["protected_globs"])

    if args.check_protected:
        check_protected(args.strict)
    check_forbidden(args.verbose)
    check_evidence(ledger)
    check_negative(ledger)
    check_ssot_sync(ledger)

    claims = ledger.get("claims", [])
    print(f"=== claim_ledger: {len(claims)} 条 claim，执行 {checks} 项检查 ===")
    if errors:
        print(f"\n--- ERROR ({len(errors)})：立论级表述冲突，必须修正 ---")
        for e in errors:
            print(f"  [E] {e}")
    if warnings:
        print(f"\n--- WARN ({len(warnings)})：不阻塞，但需人工判定 ---")
        for w in warnings:
            print(f"  [W] {w}")
    if errors:
        print("\n修正路径：① 改台账（结论变了）② 或改文档措辞（文档漂移了）。禁止只加补注。")
        return 1
    print(f"\n[OK] claim 台账一致（ERROR 0，WARN {len(warnings)}）。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
