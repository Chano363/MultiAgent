"""本地收账 closer（机制级防空转，2026-11-17 三次空转事故后立项）。

设计目标：**不管**云端任务成败、**不管** WorkBuddy 会话是否存活，实例到点必停费。
以 Windows 计划任务（schtasks）注册运行，独立于聊天会话进程树。

触发停机条件（任一满足即触发，不依赖人对"成败"的判读）：
  1. done marker 文件出现在云上（任务正常收尾标记）
  2. exit-pattern 在本次运行的**独立日志**中出现（脚本自记的退出码行）
  3. ssh 连续 3 次不可达（实例可能已被兜底 poweroff——此时须补 API stop 确认 StopCharging）
  4. 硬 deadline 到（--deadline-min；**检测无关**，这是最后一道，永不缺席）

误杀防线（19:12 事故教训：closer grep 共享日志匹配到历史崩溃行，误杀健康评估）：
  - 只读 --log 指定的**本次运行独立日志**，禁止任何形式的共享日志/历史日志匹配；
  - exit-pattern 匹配到的行必须带本次运行的启动标记之后的时间戳才有效（--start-marker 校验）。

用法（通常经 schtasks 注册，勿在 IDE 终端长跑——EXECUTION_RULES §长跑）：
  D:/Anaconda/python.exe scripts/cloud/closer_aliyun_ecs.py \
    --instance i-xxxx --deadline-min 120 \
    --ip 47.120.11.1 \
    --marker /root/proj/outputs/logs/cloud/RUN.DONE \
    --log /root/proj/outputs/logs/cloud/run.log \
    --start-marker RERUN_START --exit-pattern "EXIT_EVAL_EP|EXIT_TRAIN" \
    --pull-glob "/root/proj/outputs/results/**/*pilot*" \
    --pull-dir outputs/results/decompose

停机动作 = instance_state_aliyun_ecs 的 stop 逻辑（StopCharging + 回执复核），产物先 pull 后停。
AK：~/.aliyun_ak.txt（只读，不复制、不落日志）。
"""
import argparse
import json
import os
import shutil
import subprocess
import sys
import time
from datetime import datetime, timedelta

from ak_path import resolve_ak_file

KEY = os.path.expanduser("~/.ssh/cloud_traffic")
DEFAULT_REGION = "cn-heyuan"
SELF_LOG = ""
# 空 ssh 配置：-F 指向真实空文件以绕过用户 config（"NUL" 只有 Windows-OpenSSH 认，Git-ssh 不认）
_EMPTY_CFG = os.path.join(os.path.dirname(os.path.abspath(__file__)), "_empty_ssh_config")


def log(msg):
    line = f"[closer {datetime.now().strftime('%F %T')}] {msg}"
    print(line, flush=True)
    if SELF_LOG:
        with open(SELF_LOG, "a", encoding="utf-8") as f:
            f.write(line + "\n")


def _ssh_exe():
    """计划任务环境 PATH 不全/不可靠：显式解析 ssh.exe（19:19 心跳 rc=124 教训）。"""
    cand = [
        shutil.which("ssh"),
        r"C:\Windows\System32\OpenSSH\ssh.exe",
        r"C:\Program Files\Git\usr\bin\ssh.exe",
    ]
    for c in cand:
        if c and os.path.exists(c):
            return c
    raise FileNotFoundError("找不到 ssh.exe")


def ssh(ip, cmd, timeout=25):
    """返回 (rc, stdout)。rc!=0 视为不可达证据。

    -F NUL  绕过用户 ssh config（计划任务环境下 config 内容可能引发挂起）
    BatchMode=yes  禁一切交互提示，宁可快速失败也不挂起
    """
    argv = [_ssh_exe(), "-i", KEY, "-F", _EMPTY_CFG, "-o", "BatchMode=yes",
            "-o", "ConnectTimeout=10", "-o", "StrictHostKeyChecking=accept-new",
            f"root@{ip}", cmd]
    try:
        p = subprocess.run(argv, capture_output=True, text=True, timeout=timeout)
        return p.returncode, p.stdout
    except subprocess.TimeoutExpired:
        return 124, ""


def trigger_met(args, unreachable_streak):
    """返回 (是否触发, 原因)。

    退出码行语义（19:26 提前停机教训）：多阶段任务逐段写 EXIT_* 行，
    第一条 EXIT 行 ≠ 任务完成——必须凑满 --exit-min-count 条才算全部收尾。
    """
    if unreachable_streak >= 3:
        return True, f"ssh 连续 {unreachable_streak} 次不可达（疑似已 poweroff，须补 API stop 确认停费口径）"
    rc, out = ssh(args.ip,
                  f"ls {args.marker} 2>/dev/null; "
                  f"awk '/{args.start_marker}/{{found=1}} found' {args.log} 2>/dev/null "
                  f"| grep -E '{args.exit_pattern}' | tail -{args.exit_min_count}")
    if rc != 0:
        return False, ""
    lines = [ln for ln in out.strip().splitlines() if ln.strip()]
    if any(args.marker.split("/")[-1] in ln for ln in lines):
        return True, "done marker 出现"
    if len(lines) >= args.exit_min_count:
        return True, f"独立日志退出码行凑满 {args.exit_min_count} 条：{lines}"
    return False, ""


def pull_artifacts(args):
    if not args.pull_glob or not args.pull_dir:
        return
    os.makedirs(args.pull_dir, exist_ok=True)
    ssh_path = _ssh_exe()
    scp = os.path.join(os.path.dirname(ssh_path), "scp.exe")
    if not os.path.exists(scp):
        log(f"⚠️ 找不到 scp（{scp}），跳过产物回传")
        return
    argv = [scp, "-i", KEY, "-F", _EMPTY_CFG, "-o", "BatchMode=yes",
            "-o", "ConnectTimeout=10", "-o", "StrictHostKeyChecking=accept-new",
            f"root@{args.ip}:{args.pull_glob}", args.pull_dir]
    try:
        p = subprocess.run(argv, capture_output=True, text=True, timeout=180)
        log(f"产物回传 rc={p.returncode} → {args.pull_dir} {p.stderr.strip()[:200]}")
    except subprocess.TimeoutExpired:
        log("⚠️ 产物回传超时（不影响停机）")


def stop_instance(region, iid):
    """与 instance_state_aliyun_ecs.py --stop 完全同口径：StopCharging + 复核。"""
    from aliyunsdkcore.client import AcsClient
    from aliyunsdkcore.request import CommonRequest

    lines = [ln.strip() for ln in open(resolve_ak_file(), encoding="utf-8-sig").read().splitlines() if ln.strip()]
    client = AcsClient(lines[0], lines[1], region_id=region)

    def call(action, params):
        req = CommonRequest()
        req.set_accept_format("json")
        req.set_domain(f"ecs.{region}.aliyuncs.com")
        req.set_version("2014-05-26")
        req.set_action_name(action)
        req.set_method("POST")
        for k, v in params.items():
            req.add_query_param(k, v)
        return json.loads(client.do_action_with_exception(req))

    call("StopInstance", {"RegionId": region, "InstanceId": iid,
                          "StoppedMode": "StopCharging", "ForceStop": "false"})
    for _ in range(30):
        res = call("DescribeInstances", {"RegionId": region,
                                         "InstanceIds": json.dumps([iid])})
        it = res.get("Instances", {}).get("Instance", [])
        if it and it[0].get("Status") == "Stopped":
            mode = it[0].get("StoppedMode")
            log(f"复核 Status=Stopped StoppedMode={mode} "
                + ("✅ 已停费" if mode == "StopCharging" else "⚠️ 未停费口径！"))
            return mode == "StopCharging"
        time.sleep(5)
    log("❌ 复核超时，请人工到控制台检查")
    return False


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--instance", required=True)
    ap.add_argument("--ip", required=True, help="开机公网 IP（closer 运行期实例应在 Running）")
    ap.add_argument("--deadline-min", type=int, required=True,
                    help="硬 deadline（分钟）；检测无关、到点必停")
    ap.add_argument("--marker", required=True)
    ap.add_argument("--log", required=True, help="本次运行独立日志（禁用共享日志）")
    ap.add_argument("--start-marker", required=True,
                    help="独立日志中本次运行的启动标记行；其之前的内容一律不匹配")
    ap.add_argument("--exit-pattern", required=True)
    ap.add_argument("--exit-min-count", type=int, default=1,
                    help="触发所需退出码行数下限；多阶段任务 = 阶段数（防第一条 EXIT 行即误判完成）")
    ap.add_argument("--pull-glob", default="")
    ap.add_argument("--pull-dir", default="")
    ap.add_argument("--poll-s", type=int, default=300)
    ap.add_argument("--self-log", default="",
                    help="closer 自身心跳日志路径（schtasks 场景 stdout 不可见，必须落盘自证）")
    ap.add_argument("--region", default=DEFAULT_REGION)
    args = ap.parse_args()
    if args.self_log:
        global SELF_LOG
        SELF_LOG = args.self_log
        os.makedirs(os.path.dirname(SELF_LOG) or ".", exist_ok=True)

    deadline = datetime.now() + timedelta(minutes=args.deadline_min)
    log(f"closer 启动：instance={args.instance} deadline={deadline.strftime('%F %T')} "
        f"poll={args.poll_s}s marker={args.marker}")

    unreachable = 0
    while datetime.now() < deadline:
        hit, why = trigger_met(args, unreachable)
        if hit:
            log(f"触发停机：{why}")
            pull_artifacts(args)
            stop_instance(args.region, args.instance)
            log("closer 收账完成，退出")
            return
        rc, _ = ssh(args.ip, "true", timeout=15)
        unreachable = unreachable + 1 if rc != 0 else 0
        log(f"轮询：未见触发信号（rc={rc} 不可达连计={unreachable}）")
        time.sleep(args.poll_s)

    log("触发停机：硬 deadline 到（检测无关兜底）")
    pull_artifacts(args)
    stop_instance(args.region, args.instance)
    log("closer 收账完成，退出")


if __name__ == "__main__":
    main()
