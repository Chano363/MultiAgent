"""closer 触发器单测（2026-11-18 nincr ep10 实弹缺口补修）。

不连实例、不碰 AK：mock 掉 ssh()，只验证"什么信号该触发停机、什么不该"。
尤其守住两条误杀红线：ssh 不可达永不触发；退出码行数不足永不触发。
"""
import importlib.util
import os
import sys
from argparse import Namespace
from unittest.mock import patch

HERE = os.path.dirname(os.path.abspath(__file__))
SCRIPTS = os.path.join(os.path.dirname(HERE), "scripts", "cloud")
sys.path.insert(0, SCRIPTS)
spec = importlib.util.spec_from_file_location(
    "closer_aliyun_ecs", os.path.join(SCRIPTS, "closer_aliyun_ecs.py"))
closer = importlib.util.module_from_spec(spec)
spec.loader.exec_module(closer)

BASE = "/root/proj/outputs"
ARGS = Namespace(
    ip="127.0.0.1",
    marker=f"{BASE}/results/exit_code.txt",
    abort_glob=[f"{BASE}/results/BREAK_LINE.txt", f"{BASE}/results/DEAD_*.txt"],
    log=f"{BASE}/logs/lifecycle.txt",
    start_marker="RUN_START",
    exit_pattern="train_rc=",
    exit_min_count=1,
)


def hit(out, rc=0):
    with patch.object(closer, "ssh", return_value=(rc, out)):
        return closer.trigger_met(ARGS)


def test_abort_break_line_triggers():
    ok, why = hit("ABORT:/root/proj/outputs/results/BREAK_LINE.txt\n")
    assert ok and "BREAK_LINE" in why


def test_abort_dead_marker_triggers():
    ok, why = hit("ABORT:/root/proj/outputs/results/DEAD_20261118.txt\n")
    assert ok and "DEAD_" in why


def test_abort_wins_over_missing_done():
    ok, why = hit("ABORT:/root/proj/outputs/results/BREAK_LINE.txt\n")
    assert ok and "失败/破线标记" in why


def test_done_marker_triggers():
    ok, why = hit(f"DONE:{ARGS.marker}\n")
    assert ok and "done marker" in why


def test_exit_line_triggers():
    ok, why = hit("EXIT:train_rc=0 end_at=...\n")
    assert ok and "退出码行" in why


def test_insufficient_exit_lines_do_not_trigger():
    args = Namespace(**vars(ARGS))
    args.exit_min_count = 2
    with patch.object(closer, "ssh", return_value=(0, "EXIT:train_rc=0 first\n")):
        ok, why = closer.trigger_met(args)
    assert not ok and not why


def test_unreachable_never_triggers():
    # 00:24 误杀事故红线：rc=124/255 只告警，绝不停机
    ok, why = hit(f"ABORT:{BASE}/results/BREAK_LINE.txt\n", rc=124)
    assert not ok and not why


def test_no_signal_no_trigger():
    ok, why = hit("")
    assert not ok and not why


def test_remote_command_contains_abort_globs():
    """确认 abort-glob 真的进了 ssh 命令（防参数接线遗漏=静默失效）。"""
    seen = {}

    def fake_ssh(ip, cmd, timeout=60):
        seen["cmd"] = cmd
        return 0, ""

    with patch.object(closer, "ssh", side_effect=fake_ssh):
        closer.trigger_met(ARGS)
    assert "DEAD_*" in seen["cmd"] and "BREAK_LINE.txt" in seen["cmd"]
    assert "ABORT:" in seen["cmd"] and "DONE:" in seen["cmd"]
