"""官方口径 ep1/ep2/ep3/ep5/ep7 快评批次的 Windows 侧启动器（红线 2）。

用法：python launch_adr083_official.py [ep列表, 空格分隔]
"""
import os
import subprocess
import sys
import time

EP_LIST = " ".join(sys.argv[1:]) if len(sys.argv) > 1 else "1 2 3 5 7"

WSL_CMD = (
    "source /home/chano/miniconda3/etc/profile.d/conda.sh && "
    "conda activate traffic_rl && "
    "cd /mnt/d/Code/MultiAgent/traffic_rl_project && "
    "EP_LIST=\"%s\" "
    "bash scripts/probes/run_official_ep1_ep7.sh "
    "> outputs/logs/adr083_official_ep1_ep7_20261121/run.out 2>&1"
) % EP_LIST


def main():
    log = r"D:\Code\MultiAgent\traffic_rl_project\outputs\logs\adr083_official_ep1_ep7_20261121\launcher.log"
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
