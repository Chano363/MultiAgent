"""§19.51 追加验证工具的守卫：`run_edab_gap_recheck.py` 与其排队启动器。

守卫对象（**形式与纪律，不判内容对错**）：
    ① 脚本存在且**只跑整程**（红线 3：短窗不得当峰值/列距判据）；
    ② 脚本**内置短窗作废门槛**（`max_steps < 31500` ⇒ 判决必须作废），
       防止有人拿冒烟读数当判据；
    ③ 判读规则**前置写死**（两个分支：仍 ≤150 m ⇒ 干预面成立 / 已退化 ⇒ 历史读数失效）；
    ④ 启动器**等三个前序产物**才启动 ⇒ 同机串行（红线 2 附则）；
    ⑤ 启动器**零新增训练、零云端**（不触红线 1）；
    ⑥ 产物路径在 `outputs/logs/...` 下（硬红线 4：禁落 `outputs/` 根级）；
    ⑦ 脚本**只跑评估**（调用 `evaluate_decompose.py`，不得调训练入口）。
"""
from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "probes" / "run_edab_gap_recheck.py"
LAUNCHER = ROOT / "scripts" / "cloud" / "launch_edab_gap_recheck.py"
DIAG = ROOT / "docs" / "logs" / "diagnostics" / "DIAGNOSTICS_2026-11.md"


def _src(p: Path) -> str:
    assert p.exists(), f"缺文件：{p}"
    return p.read_text(encoding="utf-8")


def test_scripts_exist():
    assert SCRIPT.exists(), "缺 run_edab_gap_recheck.py"
    assert LAUNCHER.exists(), "缺 launch_edab_gap_recheck.py"


def test_script_has_short_window_invalidation_gate():
    """短窗必须**自动作废判决**（红线 3）。"""
    s = _src(SCRIPT)
    assert "max_steps < 31500" in s, "缺短窗作废门槛"
    assert "只作链路活性校验" in s, "短窗门槛必须写明只作活性校验"
    assert "本判决作废" in s, "短窗门槛必须显式作废判决"


def test_script_judgement_rules_written_before():
    """两个判读分支必须都在脚本里前置写死。"""
    s = _src(SCRIPT)
    assert "干预面成立" in s, "缺『干预面成立』分支"
    assert "历史读数已失效" in s, "缺『历史读数已失效』分支"
    assert "不构成对第 11 投方向的拍板" in s, "必须声明不构成拍板"


def test_script_only_runs_evaluation():
    """只跑评估 ⇒ 不得调用训练入口。"""
    s = _src(SCRIPT)
    assert "evaluate_decompose.py" in s, "必须走官方评估入口"
    for forbidden in ("run_training.py", "train_fleet", "subprocess.Popen([sys.executable, \"run_training"):
        assert forbidden not in s, f"脚本不得触碰训练入口：{forbidden}"


def test_launcher_waits_for_three_predecessors():
    """启动器必须等三个前序产物 ⇒ 同机串行。"""
    s = _src(LAUNCHER)
    for p in ("amplification_probe.json",
              "full_pytest_after_col_observer.txt",
              "primary_metric_sensitivity.json"):
        assert p in s, f"启动器未等待前序产物 {p}"
    assert "ABORT" in s, "启动器缺前序缺失时的 ABORT 分支"


def test_launcher_no_cloud_no_training():
    """零新增训练、零云端 ⇒ 不触红线 1。"""
    s = _src(LAUNCHER)
    assert "run_training" not in s, "启动器不得触发训练"
    for cloud in ("aliyun", "ecs.c9i", "InstanceId", "DescribeInstances"):
        assert cloud not in s, f"启动器不得触碰云端：{cloud}"


def test_output_dir_not_root_level():
    """产物目录必须在 outputs/logs/ 下（硬红线 4）。"""
    s = _src(SCRIPT)
    assert "outputs/logs/adr083_gap_primary_metric_sweep" in s
    assert not re.search(r'["\']outputs/["\']', s), "不得把产物写进 outputs/ 根级"


def test_diag_documents_the_recheck():
    """诊断文档必须登记这次追加验证（否则工具成了无主产物）。"""
    d = _src(DIAG)
    assert "19.51.3c" in d, "诊断未登记 §19.51.3c 追加验证"
    assert "run_edab_gap_recheck.py" in d, "诊断须点名工具脚本"
    assert "MultiAgent_ADR083_edabrecheck" in d, "诊断须点名计划任务"
    assert "判读规则（前置写死）" in d, "诊断须记录前置写死的判读规则"
