"""账单守卫（billing guard）：纯 API，零 ssh 依赖。

设计动机（2026-11-18 owner 指令）："我还是不相信你的机制，不要让我白花钱了"。
今晚反复出问题的是 ssh 通道（schtasks 环境下探针 rc=124）；本守卫只用阿里云 API
DescribeInstances / StopInstance，不碰 ssh，schtasks 环境下可靠。

逻辑（每次被计划任务唤起时执行，秒级完成）：
  1. API 查实例状态；
  2. Stopped → 记一行"已停费"，退出；
  3. Running 且已过 --stop-after 绝对时限 → API 强停（StopCharging）+ 复核回执；
  4. Running 且未到时限 → 记一行状态心跳，退出。

被 schtasks 每 10 分钟唤起一次（/ET 到点后自动停排）。日志落盘自证心跳。
"""
import argparse
import json
import os
import sys
import time
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from ak_path import resolve_ak_file  # noqa: E402


def log(path, msg):
    line = f"[guard {datetime.now().strftime('%F %T')}] {msg}"
    print(line, flush=True)
    if path:
        os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
        with open(path, "a", encoding="utf-8") as f:
            f.write(line + "\n")


def client_for(region):
    from aliyunsdkcore.client import AcsClient
    lines = [ln.strip() for ln in open(resolve_ak_file(), encoding="utf-8-sig").read().splitlines() if ln.strip()]
    return AcsClient(lines[0], lines[1], region_id=region)


def call(client, region, action, params):
    from aliyunsdkcore.request import CommonRequest
    req = CommonRequest()
    req.set_accept_format("json")
    req.set_domain(f"ecs.{region}.aliyuncs.com")
    req.set_version("2014-05-26")
    req.set_action_name(action)
    req.set_method("POST")
    for k, v in params.items():
        req.add_query_param(k, v)
    return json.loads(client.do_action_with_exception(req))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--instance", required=True)
    ap.add_argument("--region", default="cn-heyuan")
    ap.add_argument("--stop-after", required=True,
                    help="绝对时限（%%Y-%%m-%%dT%%H:%%M，ISO 格式用 T 分隔——schtasks /TR 会吃掉引号，带空格会被拆参）")
    ap.add_argument("--self-log", required=True)
    args = ap.parse_args()

    deadline = datetime.fromisoformat(args.stop_after.strip().replace(" ", "T"))
    c = client_for(args.region)
    res = call(c, args.region, "DescribeInstances",
               {"RegionId": args.region, "InstanceIds": json.dumps([args.instance])})
    it = res.get("Instances", {}).get("Instance", [])
    if not it:
        log(args.self_log, f"⚠️ 实例 {args.instance} 未查到（可能已释放），人工核查")
        return
    status = it[0].get("Status")
    mode = it[0].get("StoppedMode")
    if status != "Running":
        log(args.self_log, f"Status={status} StoppedMode={mode} ✅ 无费用风险")
        return
    if datetime.now() >= deadline:
        log(args.self_log, f"Status=Running 且已过时限 {args.stop_after} → 强停")
        call(c, args.region, "StopInstance",
             {"RegionId": args.region, "InstanceId": args.instance,
              "StoppedMode": "StopCharging", "ForceStop": "false"})
        for _ in range(30):
            r2 = call(c, args.region, "DescribeInstances",
                      {"RegionId": args.region, "InstanceIds": json.dumps([args.instance])})
            i2 = r2.get("Instances", {}).get("Instance", [])
            if i2 and i2[0].get("Status") == "Stopped":
                log(args.self_log, f"复核 Stopped StoppedMode={i2[0].get('StoppedMode')} ✅")
                return
            time.sleep(5)
        log(args.self_log, "❌ 强停后复核超时，人工到控制台检查")
    else:
        log(args.self_log, f"Status=Running（时限 {args.stop_after} 未到，继续观察）")


if __name__ == "__main__":
    main()
