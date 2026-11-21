"""守卫：队列等待条件必须判"上游已完成"，不能只判"文件出现"（诊断 §19.54）。

背景：2026-11-21 发生过一次同机并发（主指标敏感度探针与全量 pytest 并跑约 3.5 分钟），
根因 = shell 输出重定向在任务**启动瞬间**就创建输出文件 ⇒ 只判 "-f 文件存在" 会提前放行。
⇒ 两个队列启动器的等待条件必须追加**内容判据**。
"""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PM_SENS = ROOT / "scripts" / "cloud" / "launch_adr083_primary_sens.py"
EDAB = ROOT / "scripts" / "cloud" / "launch_edab_gap_recheck.py"
DIAG = ROOT / "docs" / "logs" / "diagnostics" / "DIAGNOSTICS_2026-11.md"


def _text(p):
    return p.read_text(encoding="utf-8")


def test_pm_sens_waits_for_pytest_summary_not_just_file():
    t = _text(PM_SENS)
    # 【2026-11-21 §19.57 更新】判据已加固为"大小写不敏感 + 含 summary 特征"，
    #   并且**删除了 pgrep 进程判据**（它会匹配到上游队列自身的命令行 ⇒ 永久误判）。
    assert "grep -qiE 'short test summary info|passed|failed|error'" in t, \
        "主指标敏感度队列的等待条件必须包含 pytest 收尾判据（大小写不敏感 + summary 特征）"
    assert "-f outputs/logs/adr083_float_probe/full_pytest_after_col_observer.txt ] &&" in t, \
        "必须把文件存在判据与内容判据并列（&&）"
    code_only = "\n".join(ln for ln in t.splitlines() if not ln.strip().startswith("#"))
    assert "pgrep" not in code_only, \
        "等待判据不得使用 pgrep 进程判据（会自匹配上游命令行 ⇒ 永久等待，§19.57）"


def test_edab_waits_for_content_of_all_predecessors():
    t = _text(EDAB)
    assert t.count("grep -q") >= 3, \
        "edab-recheck 的三个前序产物都必须有内容判据（§19.54）"
    assert "grep -q '\\\"ulps\\\"'" in t or "grep -q '\"ulps\"'" in t, \
        "JSON 前序产物须按内容键判定完成，避免读到半写文件"


def test_diag_records_the_concurrency_event():
    t = _text(DIAG)
    assert "§19.54" in t
    seg = t[t.index("§19.54"):]
    for token in ("红线 2", "并发", "kill", "内容判据"):
        assert token in seg, f"§19.54 缺少关键内容：{token}"


def test_diag_states_reusable_queue_rule():
    t = _text(DIAG)
    seg = t[t.index("§19.54"):]
    assert "上游已完成" in seg and "文件出现" in seg
