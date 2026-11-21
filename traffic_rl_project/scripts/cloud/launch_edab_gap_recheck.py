"""§19.51 追加验证的**排队启动器**（Windows 侧，红线 2：长跑脱离 IDE 进程树；同机串行）。

为什么排队而不是直接跑：
    §19.51.3b 的分层统计是**历史产物的横切统计**，不是受控对照——历史 `ed_ab` 读数来自
    **旧代码**（`git_commit=a589991d…`，2026-11-11/12），第 9 投读数来自**新代码**
    （`git_commit=154c1b8e…`，2026-11-20），期间物理层/控制器层改过
    （ADR-076/077/080/081 全在 `1bb7b02` 祖先链上）⇒ **旧代码下的 42 m 列距
    能否在现版本代码下复现，是未知数** ⇒ 必须实测。

排队顺序（同机串行，红线 2 附则）：
    ① 等放大系数探针产物 `amplification_probe.json` 落盘；
    ② 等 followup 队列收口（其最后一步产物 = `full_pytest_after_col_observer.txt`）；
    ③ 等主指标敏感度探针收口（产物 = `primary_metric_sensitivity.json`）；
    ④ 最后才跑 `run_edab_gap_recheck.py`（**整程 31500 步 ×2 族**，约 40 min）。

⚠️ **为什么排在最后**：本次复跑要花约 40 min 机时，且**不产出任何判据**——
    它只回答"第 11 投的『回 ed_ab schema』干预面还存不存在"这一**可行性问题**。
    而放大探针 / 主指标敏感度探针直接关系到 §19.47–§19.49 的**判据有效性**（更靠前）。
    ⇒ **优先级靠后，但成本为零（纯本地评估，不触红线 1）**。

⚠️ **红线遵守**：
    · **零新增训练、零云端机时** ⇒ 不触红线 1；
    · **同机串行**（等三个前序产物全部落盘）⇒ 不违反红线 2 附则；
    · **只跑整程 31500 步** ⇒ 不违反红线 3（短窗不作判据）；
    · 产物落 `outputs/logs/adr083_gap_primary_metric_sweep/` ⇒ 不违反硬红线 4。
"""
import os
import subprocess
import sys
import time

LOG_DIR = r"D:\Code\MultiAgent\traffic_rl_project\outputs\logs\adr083_gap_primary_metric_sweep"

PREDECESSORS = [
    "outputs/logs/adr083_float_probe/amplification_probe.json",
    "outputs/logs/adr083_float_probe/full_pytest_after_col_observer.txt",
    "outputs/logs/adr083_float_probe/primary_metric_sensitivity.json",
]

WSL_CMD = (
    "source /home/chano/miniconda3/etc/profile.d/conda.sh && "
    "conda activate traffic_rl && "
    "cd /mnt/d/Code/MultiAgent/traffic_rl_project && "
    "mkdir -p outputs/logs/adr083_gap_primary_metric_sweep && "
    "echo '[edab-recheck] waiting for 3 predecessors' && "
    "for i in $(seq 1 1440); do "
    "  ok=1; "
    # ⚠️ 2026-11-21 修正：等"上游已完成"而非"文件存在"——
    # pytest 输出文件在**启动瞬间**就被 shell 重定向创建；JSON 产物在写入过程中
    # 也可能只写了一半 ⇒ 只判存在会让本队列与上游任务**并发**（违反红线 2
    # 「同机多任务串行」）或读到半写文件。⇒ 追加"内容判据"。
    "  [ -f outputs/logs/adr083_float_probe/amplification_probe.json ] || ok=0; "
    "  grep -q '\"ulps\"' outputs/logs/adr083_float_probe/amplification_probe.json 2>/dev/null || ok=0; "
    "  [ -f outputs/logs/adr083_float_probe/full_pytest_after_col_observer.txt ] || ok=0; "
    "  grep -qE 'passed|failed|error' outputs/logs/adr083_float_probe/full_pytest_after_col_observer.txt 2>/dev/null || ok=0; "
    "  [ -f outputs/logs/adr083_float_probe/primary_metric_sensitivity.json ] || ok=0; "
    "  grep -q '\"ulps\"' outputs/logs/adr083_float_probe/primary_metric_sensitivity.json 2>/dev/null || ok=0; "
    "  [ \"$ok\" = \"1\" ] && break; "
    "  sleep 30; "
    "done; "
    "for p in " + " ".join(PREDECESSORS) + "; do "
    "  if [ ! -f \"$p\" ]; then echo '[edab-recheck] ABORT: missing '$p; exit 2; fi; "
    "done; "
    "echo '[edab-recheck] predecessors ready, starting recheck' && "
    "python scripts/probes/run_edab_gap_recheck.py "
    "> outputs/logs/adr083_gap_primary_metric_sweep/edab_recheck_run.log 2>&1; "
    "echo '[edab-recheck] rc='$? && date"
)


def main():
    os.makedirs(LOG_DIR, exist_ok=True)
    log = os.path.join(LOG_DIR, "edab_recheck_launcher.log")
    with open(log, "a", encoding="utf-8") as f:
        f.write("launch at %s\n" % time.strftime("%Y-%m-%dT%H:%M:%S"))
        f.flush()
        p = subprocess.Popen(["wsl.exe", "-e", "bash", "-lc", WSL_CMD])
        f.write("wsl pid=%s\n" % p.pid)
        f.flush()
        rc = p.wait()
        f.write("exited rc=%s at %s\n" % (rc, time.strftime("%Y-%m-%dT%H:%M:%S")))
    return 0


if __name__ == "__main__":
    sys.exit(main())
