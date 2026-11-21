"""主指标浮点敏感度探针的 Windows 侧启动器（红线 2：长跑脱离 IDE 进程树；同机串行）。

用法：python scripts/cloud/launch_adr083_primary_sens.py

排队逻辑：
    先等 followup 队列收口（其最后一步的产物 = 全量 pytest 输出文件存在）
    ⇒ 再跑主指标敏感度探针（0 / +1 / **−1** ULP 三档整程，约 60 min）
    ⇒ 保证同机同一时刻只有一个 CPU 密集任务（红线 2 附则：同机多任务串行）。

⚠️ **负档位（−1 ULP）是必跑项，不是可选项**（§19.48 判读规则）：
    单向扰动曲线无法区分"混沌放大"与"系统性偏置"⇒ 必须双向对照。
    ⇒ 启动器**硬编码 `--ulps 0,1,-1`**，不得删减负档位。

⚠️ 口径：产出 `outputs/logs/adr083_float_probe/primary_metric_sensitivity.json`，
    属**机制层敏感度诊断**，不得作为峰值/安全判据引用。
"""
import os
import subprocess
import sys
import time

LOG_DIR = r"D:\Code\MultiAgent\traffic_rl_project\outputs\logs\adr083_float_probe"

WSL_CMD = (
    "source /home/chano/miniconda3/etc/profile.d/conda.sh && "
    "conda activate traffic_rl && "
    "cd /mnt/d/Code/MultiAgent/traffic_rl_project && "
    "mkdir -p outputs/logs/adr083_float_probe && "
    "echo '[pm-sens] waiting for followup queue (full pytest output)' && "
    "for i in $(seq 1 720); do "
    # ⚠️ 2026-11-21 修正：等待条件必须判"上游**已完成**"，不能只判"文件存在"
    # （shell 重定向会在 pytest **启动瞬间**就创建该文件 ⇒ 只判存在会让本队列
    #  与仍在跑的 pytest **并发**，违反红线 2「同机多任务串行」）。
    # ⇒ 追加判据：pytest 输出里必须出现收尾汇总行（passed/failed/error）。
    "  if [ -f outputs/logs/adr083_float_probe/full_pytest_after_col_observer.txt ] && "
    "     grep -qE 'passed|failed|error' outputs/logs/adr083_float_probe/full_pytest_after_col_observer.txt; then break; fi; "
    "  sleep 30; "
    "done; "
    "if ! grep -qE 'passed|failed|error' outputs/logs/adr083_float_probe/full_pytest_after_col_observer.txt 2>/dev/null; then "
    "  echo '[pm-sens] ABORT: followup queue not finished after 6h'; exit 2; fi; "
    "echo '[pm-sens] followup done, starting primary metric sensitivity probe' && "
    "python scripts/probes/probe_primary_metric_sensitivity.py "
    "--checkpoint outputs/checkpoints/formation_10kt_1plus108/"
    "w4nincrgatecaprel_w4full_20261120_cloud/"
    "mappo_fleet_last_ep6_dec_ad1_cp_seed0_seed0.pt "
    "--max_steps 31500 --ulps 0,1,-1 "
    "> outputs/logs/adr083_float_probe/primary_sens_run.log 2>&1; "
    "echo '[pm-sens] probe rc='$? && date"
)


def main():
    os.makedirs(LOG_DIR, exist_ok=True)
    log = os.path.join(LOG_DIR, "primary_sens_launcher.log")
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
