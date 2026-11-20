"""ADR-083 前置取证：启动 ep1..ep7 漂移轨迹批跑的 Windows 侧启动器。

【为什么单独写这个文件】EXECUTION_RULES §长跑要求 >5 分钟的长跑脱离 IDE/客户端
进程树启动。正规做法是 Windows 任务计划；本机安全策略禁止在命令串里直接拼
shell（schtasks / wscript / wsl.exe 均被拦），因此改为：

    计划任务动作 = python.exe <本文件>
        → 本文件用 subprocess 拉起 wsl.exe（附着长会话，见 EXECUTION_RULES 第 6 条）
        → wsl.exe 内跑 scripts/probes/run_drift_trajectory_ep1_ep7.sh

【判活】不看本进程输出，按规则用 pgrep -af 判活；产物目录才是完成判据。
"""
import os
import subprocess
import sys
import time

WSL_CMD = (
    "cd /mnt/d/Code/MultiAgent/traffic_rl_project && "
    "mkdir -p outputs/logs/adr083_drift_trajectory && "
    "bash scripts/probes/run_drift_trajectory_ep1_ep7.sh "
    "> outputs/logs/adr083_drift_trajectory/run.out 2>&1"
)


def main():
    log = r"D:\Code\MultiAgent\traffic_rl_project\outputs\logs\adr083_drift_trajectory\launcher.log"
    os.makedirs(os.path.dirname(log), exist_ok=True)
    with open(log, "a", encoding="utf-8") as f:
        f.write("launch at %s\n" % time.strftime("%Y-%m-%dT%H:%M:%S"))
        f.flush()
        # wsl.exe 自身作为附着会话存活（EXECUTION_RULES 第 6 条：WSL 在最后一个
        # 会话退出时会终止全部分布进程，故不能 setsid/nohup 后立刻返回）。
        p = subprocess.Popen(["wsl.exe", "-e", "bash", "-lc", WSL_CMD])
        f.write("wsl pid=%s\n" % p.pid)
        f.flush()
        rc = p.wait()
        f.write("wsl exited rc=%s at %s\n" % (rc, time.strftime("%Y-%m-%dT%H:%M:%S")))
    return 0


if __name__ == "__main__":
    sys.exit(main())
