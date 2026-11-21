"""探针后续**串行**队列的 Windows 侧启动器（红线 2：长跑脱离 IDE 进程树；同机多任务串行）。

队列（严格串行，同一时刻只跑一个）：
    ① 等放大系数整程探针收口（`amplification_probe.json` 落盘）；
    ② **torch 策略前向 ISA 路径敏感性探针**（§19.46，补 §19.43 未覆盖的最后一层：
       §19.43 只排除了 **numba 车钩力内核**的 JIT 目标 ISA，未覆盖**策略网络**）；
    ③ 全量 pytest 复核（本轮 env/trainer/artifacts 改动未破坏既有测试）。

为什么串行而不是并行：
    红线 2 附则要求同机多任务串行；放大系数探针与整程 pytest 都是 CPU 密集，
    并行会拖慢并可能干扰计时观察。⇒ 三者严格排队。

用法：python scripts/cloud/launch_adr083_followup.py
"""
import os
import subprocess
import sys
import time

LOG_DIR = (r"D:\Code\MultiAgent\traffic_rl_project\outputs\logs\adr083_float_probe")

WSL_CMD = (
    "source /home/chano/miniconda3/etc/profile.d/conda.sh && "
    "conda activate traffic_rl && "
    "cd /mnt/d/Code/MultiAgent/traffic_rl_project && "
    "mkdir -p outputs/logs/adr083_float_probe && "
    "echo '[followup] waiting for amplification_probe.json' && "
    "for i in $(seq 1 360); do "
    "  if [ -f outputs/logs/adr083_float_probe/amplification_probe.json ]; then break; fi; "
    "  sleep 30; "
    "done; "
    "if [ ! -f outputs/logs/adr083_float_probe/amplification_probe.json ]; then "
    "  echo '[followup] ABORT: probe json missing after 3h'; exit 2; fi; "
    "echo '[followup] probe json present, starting torch ISA path probe' && "
    "python scripts/probes/probe_torch_isa_path.py "
    "--checkpoint outputs/checkpoints/formation_10kt_1plus108/"
    "w4nincrgatecaprel_w4full_20261120_cloud/"
    "mappo_fleet_last_ep6_dec_ad1_cp_seed0_seed0.pt "
    "> outputs/logs/adr083_float_probe/torch_isa_path_run.log 2>&1; "
    "echo '[followup] isa probe rc='$? && "
    "echo '[followup] starting full pytest' && "
    "python -m pytest tests/ -q "
    "> outputs/logs/adr083_float_probe/full_pytest_after_col_observer.txt 2>&1; "
    "echo '[followup] pytest rc='$? && date"
)


def main():
    os.makedirs(LOG_DIR, exist_ok=True)
    log = os.path.join(LOG_DIR, "followup_launcher.log")
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
