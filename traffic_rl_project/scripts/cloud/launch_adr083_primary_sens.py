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
    # ⚠️ 2026-11-21 修正（两次）：
    #   (a) 等待条件必须判"上游**已完成**"，不能只判"文件存在"
    #       （shell 重定向会在 pytest **启动瞬间**就创建该文件 ⇒ 只判存在会让本队列
    #        与仍在跑的 pytest **并发**，违反红线 2「同机多任务串行」）。
    #   (b) 判据必须**大小写不敏感**且**不依赖最终计数行**：pytest 的收尾可能只留下
    #       "short test summary info" + 大写 "FAILED"（如上游被中断时计数行缺失），
    #       小写 grep 'failed' 会漏判 ⇒ 队列无限等待。
    #   (c) ⚠️ **不用进程判据**（pgrep -f 会被"命令行里含该字符串"的其它进程
    #       —— 包括上游队列自己的 bash —— 误判为'仍在跑'，导致永久等待；
    #       且字符类写法也救不了，因为上游 bash 命令行里含 `python -m pytest tests/`
    #       这类字面量）⇒ 改用 pytest 的**收尾摘要行**（'short test summary info'
    #       只在 pytest 结束时打印）作为唯一完成判据。
    "  if [ -f outputs/logs/adr083_float_probe/full_pytest_after_col_observer.txt ] && "
    "     grep -qiE 'short test summary info|passed|failed|error' outputs/logs/adr083_float_probe/full_pytest_after_col_observer.txt; then break; fi; "
    "  sleep 30; "
    "done; "
    "if ! grep -qiE 'short test summary info|passed|failed|error' outputs/logs/adr083_float_probe/full_pytest_after_col_observer.txt 2>/dev/null; then "
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
