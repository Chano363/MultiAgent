"""本地收账 closer（机制级防空转，2026-11-17 三次空转事故后立项）。

设计目标：**不管**云端任务成败、**不管** WorkBuddy 会话是否存活，实例到点必停费。
以 Windows 计划任务（schtasks）注册运行，独立于聊天会话进程树。

触发停机条件（任一满足即触发，不依赖人对"成败"的判读）：
  1. done marker 文件出现在云上（任务正常收尾标记）
  2. exit-pattern 在本次运行的**独立日志**中出现（脚本自记的退出码行）
  3. **失败/破线标记出现（--abort-glob，如 BREAK_LINE.txt / DEAD_*.txt）**——
     2026-11-18 nincr ep10 实弹暴露：快评破线后训练还活着，而 closer 只认正常退出
     与 deadline，失败标记出现时它一直空等=实例继续计费。失败标记 = 立即收账。
  4. 硬 deadline 到（--deadline-min；**检测无关**，这是最后一道，永不缺席）

⚠️ 不可达触发器已废除（2026-11-18 00:24 误杀事故）："ssh 连续 3 次不可达 → 疑似已
poweroff → 补 API stop"把 **ssh 超时 ≠ 机器关机** 两件事划了等号——三次 rc=124 网络
抖动就把健康运行的实例停了。不可达只计数、只留痕，**永不触发停机**；机器真挂了 billing
由 deadline 兜底，误杀概率归零优先于早停几分钟。

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
    失败时 stderr 首行落自志（rc=255/124 排障需要，2026-11-18 w4cover 全程不可达教训）
    """
    argv = [_ssh_exe(), "-i", KEY, "-F", _EMPTY_CFG, "-o", "BatchMode=yes",
            "-o", "ConnectTimeout=10", "-o", "StrictHostKeyChecking=accept-new",
            f"root@{ip}", cmd]
    try:
        p = subprocess.run(argv, capture_output=True, text=True, timeout=timeout)
        if p.returncode != 0 and SELF_LOG:
            err1 = (p.stderr or "").strip().splitlines()[:1]
            log(f"ssh 失败 rc={p.returncode} cmd[:60]={cmd[:60]!r} stderr={err1}")
        return p.returncode, p.stdout
    except subprocess.TimeoutExpired as e:
        if SELF_LOG:
            err1 = ((e.stderr or b"").decode("utf-8", "ignore").strip().splitlines()[:1])
            log(f"ssh 超时({timeout}s) cmd[:60]={cmd[:60]!r} stderr={err1}")
        # 网络抖动（丢包→SYN 重传）下单次超时不代表链路坏：隔 5s 重试一次
        time.sleep(5)
        try:
            p = subprocess.run(argv, capture_output=True, text=True, timeout=timeout)
            if p.returncode != 0 and SELF_LOG:
                err1 = (p.stderr or "").strip().splitlines()[:1]
                log(f"ssh 重试失败 rc={p.returncode} stderr={err1}")
            return p.returncode, p.stdout
        except subprocess.TimeoutExpired:
            return 124, ""


def trigger_met(args):
    """返回 (是否触发, 原因)。

    退出码行语义（19:26 提前停机教训）：多阶段任务逐段写 EXIT_* 行，
    第一条 EXIT 行 ≠ 任务完成——必须凑满 --exit-min-count 条才算全部收尾。
    不可达（unreachable）永不触发停机（00:24 误杀事故）。

    【2026-11-18 失败标记】每条探测输出加 ABORT:/DONE:/EXIT: 前缀再解析：
    避免"basename 子串恰好出现在无关行"造成误判（19:12 误杀同类风险）。
    """
    parts = []
    for pat in args.abort_glob:
        parts.append(f"for f in {pat}; do [ -e \"$f\" ] && echo \"ABORT:$f\"; done")
    parts.append(f"ls {args.marker} 2>/dev/null | sed 's/^/DONE:/'")
    parts.append(
        f"awk '/{args.start_marker}/{{found=1}} found' {args.log} 2>/dev/null "
        f"| grep -E '{args.exit_pattern}' | tail -{args.exit_min_count} "
        f"| sed 's/^/EXIT:/'")
    rc, out = ssh(args.ip, "; ".join(parts), timeout=60)
    if rc != 0:
        return False, ""
    lines = [ln.strip() for ln in out.strip().splitlines() if ln.strip()]
    for ln in lines:
        if ln.startswith("ABORT:"):
            return True, f"失败/破线标记出现：{ln[len('ABORT:'):]}"
    if any(ln.startswith("DONE:") for ln in lines):
        return True, "done marker 出现"
    exits = [ln[len('EXIT:'):] for ln in lines if ln.startswith("EXIT:")]
    if len(exits) >= args.exit_min_count:
        return True, f"独立日志退出码行凑满 {args.exit_min_count} 条：{exits}"
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
    # 网络路径间歇性丢包（2026-11-18 w4cover 实测 rc=124/255 交替）：
    # 产物回传失败 = 停机后产物滞留云盘，必须重试而非一次放弃。
    for attempt in range(1, 4):
        try:
            p = subprocess.run(argv, capture_output=True, text=True, timeout=180)
            log(f"产物回传(第{attempt}/3次) rc={p.returncode} → {args.pull_dir} "
                f"{p.stderr.strip()[:200]}")
            if p.returncode == 0:
                return
        except subprocess.TimeoutExpired:
            log(f"⚠️ 产物回传(第{attempt}/3次)超时")
        time.sleep(10)


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
    ap.add_argument("--abort-glob", action="append", default=[],
                    help="失败/破线标记的文件通配符（云端路径），出现即触发停机；"
                         "可给多个。例：/root/.../BREAK_LINE.txt /root/.../DEAD_*.txt")
    ap.add_argument("--log", required=True, help="本次运行独立日志（禁用共享日志）")
    ap.add_argument("--start-marker", required=True,
                    help="独立日志中本次运行的启动标记行；其之前的内容一律不匹配")
    ap.add_argument("--exit-pattern", required=True)
    ap.add_argument("--exit-min-count", type=int, default=1,
                    help="触发所需退出码行数下限；多阶段任务 = 阶段数（防第一条 EXIT 行即误判完成）")
    ap.add_argument("--pull-glob", default="")
    ap.add_argument("--pull-dir", default="")
    ap.add_argument("--poll-s", type=int, default=300)
    ap.add_argument("--dry-run", action="store_true",
                    help="验证模式：完整走轮询/触发/产物回传链路，但【不调用停机 API】。"
                         "对训练实例做 closer 验证必须带此参数"
                         "（2026-11-18 12:14 事故：带真实参数的 1min deadline 测试"
                         "触发兜底停机，葬送 ep6 训练）")
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
        f"poll={args.poll_s}s marker={args.marker}"
        + (" [dry-run：不会真正停机]" if args.dry_run else ""))

    unreachable = 0
    while datetime.now() < deadline:
        hit, why = trigger_met(args)
        if hit:
            log(f"触发停机：{why}")
            pull_artifacts(args)
            if args.dry_run:
                log("[dry-run] 验证命中触发链路，跳过停机 API，退出")
                return
            stop_instance(args.region, args.instance)
            log("closer 收账完成，退出")
            return
        rc, _ = ssh(args.ip, "true", timeout=30)
        unreachable = unreachable + 1 if rc != 0 else 0
        if unreachable >= 3:
            log(f"⚠️ ssh 连续 {unreachable} 次不可达（仅告警不停机，deadline 兜底）")
        log(f"轮询：未见触发信号（rc={rc} 不可达连计={unreachable}）")
        time.sleep(args.poll_s)

    log("触发停机：硬 deadline 到（检测无关兜底）")
    pull_artifacts(args)
    if args.dry_run:
        log("[dry-run] 验证命中 deadline 兜底链路，跳过停机 API，退出")
        return
    stop_instance(args.region, args.instance)
    log("closer 收账完成，退出")


if __name__ == "__main__":
    main()
