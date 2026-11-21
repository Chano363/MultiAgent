"""ep6 本地复跑（判决性对照 B）的 Windows 侧启动器（红线 2）。"""
import os
import subprocess
import sys
import time

SCRIPT = sys.argv[1] if len(sys.argv) > 1 else "scripts/probes/run_repeat_ep6_check.sh"

WSL_CMD = (
    "source /home/chano/miniconda3/etc/profile.d/conda.sh && "
    "conda activate traffic_rl && "
    "cd /mnt/d/Code/MultiAgent/traffic_rl_project && "
    "bash %s" % SCRIPT
)


def main():
    log = r"D:\Code\MultiAgent\traffic_rl_project\outputs\logs\adr083_repeat_ep6\launcher.log"
    os.makedirs(os.path.dirname(log), exist_ok=True)
    with open(log, "a", encoding="utf-8") as f:
        f.write("launch at %s script=%s\n" % (time.strftime("%Y-%m-%dT%H:%M:%S"), SCRIPT))
        f.flush()
        p = subprocess.Popen(["wsl.exe", "-e", "bash", "-lc", WSL_CMD])
        f.write("wsl pid=%s\n" % p.pid)
        f.flush()
        rc = p.wait()
        f.write("exited rc=%s at %s\n" % (rc, time.strftime("%Y-%m-%dT%H:%M:%S")))
    return 0


if __name__ == "__main__":
    sys.exit(main())
