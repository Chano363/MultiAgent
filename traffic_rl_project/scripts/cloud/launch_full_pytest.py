"""全量 pytest 的 Windows 侧启动器（脱离 IDE 进程树，红线 2）。

背景：上轮 `pytest tests/ -q` 用后台 Bash 启动，跑了 37 min 后随会话任务回收
被中断，**结果未落盘**（只有 .pytest_cache 的陈旧 lastfailed，不能当权威结论）。
本启动器让全量测试在独立进程树中跑完，并把输出写到文件。

用法：python scripts/cloud/launch_full_pytest.py <输出文件>
"""
import os
import subprocess
import sys
import time

WSL_CMD = (
    "source /home/chano/miniconda3/etc/profile.d/conda.sh && "
    "conda activate traffic_rl && "
    "cd /mnt/d/Code/MultiAgent/traffic_rl_project && "
    "python -m pytest tests/ -q"
)


def main():
    out = sys.argv[1] if len(sys.argv) > 1 else (
        r"D:\Code\MultiAgent\traffic_rl_project\outputs\logs\full_pytest\pytest_out.txt")
    os.makedirs(os.path.dirname(out), exist_ok=True)
    log = out + ".launcher.log"
    with open(log, "a", encoding="utf-8") as f:
        f.write("launch at %s\n" % time.strftime("%Y-%m-%dT%H:%M:%S"))
        f.flush()
        # wsl.exe 自身作为附着会话存活（EXECUTION_RULES 第 6 条）
        with open(out, "w", encoding="utf-8") as fo:
            p = subprocess.Popen(["wsl.exe", "-e", "bash", "-lc", WSL_CMD], stdout=fo,
                                 stderr=subprocess.STDOUT)
            f.write("wsl pid=%s out=%s\n" % (p.pid, out))
            f.flush()
            rc = p.wait()
            f.write("pytest exited rc=%s at %s\n" % (rc, time.strftime("%Y-%m-%dT%H:%M:%S")))
    return 0


if __name__ == "__main__":
    sys.exit(main())
