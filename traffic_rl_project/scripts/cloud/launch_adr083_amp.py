"""放大系数探针的 Windows 侧启动器（红线 2：长跑脱离 IDE 进程树）。

用法：python scripts/cloud/launch_adr083_amp.py
"""
import os
import subprocess
import sys
import time

WSL_CMD = (
    "source /home/chano/miniconda3/etc/profile.d/conda.sh && "
    "conda activate traffic_rl && "
    "cd /mnt/d/Code/MultiAgent/traffic_rl_project && "
    "mkdir -p outputs/logs/adr083_float_probe && "
    "python scripts/probes/probe_amplification.py "
    "--checkpoint outputs/checkpoints/formation_10kt_1plus108/"
    "w4nincrgatecaprel_w4full_20261120_cloud/"
    "mappo_fleet_last_ep6_dec_ad1_cp_seed0_seed0.pt "
    "--max_steps 31500 --ulps 0,1,10,100 "
    "> outputs/logs/adr083_float_probe/amplification_run.log 2>&1"
)


def main():
    log = (r"D:\Code\MultiAgent\traffic_rl_project\outputs\logs\adr083_float_probe"
           r"\amplification_launcher.log")
    os.makedirs(os.path.dirname(log), exist_ok=True)
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
