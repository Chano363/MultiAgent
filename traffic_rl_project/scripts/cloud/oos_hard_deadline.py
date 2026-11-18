"""云端硬顶（OOS TimerTrigger + StopInstance）——本地机器/会话全死也必停费。

一手依据：
  - ACS::TimerTrigger：help.aliyun.com/zh/oos/user-guide/acs-timertrigger
    （Type=at / Expression=绝对时刻 ISO8601 / EndDate 必填 / TimeZone / 触发器必须是第一个任务）
  - ACS::ECS::StopInstance：help.aliyun.com/en/oos/user-guide/acs-ecs-stopinstance
    （stoppedMode=StopCharging、forceStop=false）
  - StartExecution：help.aliyun.com/zh/oos/developer-reference/api-oos-2019-06-01-startexecution

为什么用 TimerTrigger 而不是"定时任务 API"：OOS 没有独立 CreateSchedule API；
定时器是模板内第一个任务（执行进入 Waiting，到点自动建子执行跳过 trigger 跑停机）。
子执行与父执行同模板同参数 ⇒ 每次开窗传新 deadline 即可，一次执行=一次停机。

用法（本地 Windows Python，AK 只读）：
  python oos_hard_deadline.py --deploy-template                 # 一次性部署模板
  python oos_hard_deadline.py --arm --deadline 2026-11-19T03:00:00+08:00  # 开窗建执行
  python oos_hard_deadline.py --disarm --execution-id exec-xxx   # 收工取消执行
  python oos_hard_deadline.py --list                             # 查模板/执行
  python oos_hard_deadline.py --dry-run --arm --deadline ...     # 验证链路，不调用任何写 API

安全：--arm 只创建"到点后 StopInstance"的执行；实例已停机时到点执行 StopInstance
是幂等的（阿里云 API 对 Stopped 实例再停无副作用）。取消执行 = CancelExecution。
"""
import argparse
import json
import os
import sys
from datetime import datetime, timedelta, timezone

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from ak_path import resolve_ak_file
from aliyunsdkcore.client import AcsClient
from aliyunsdkcore.request import CommonRequest

REGION = "cn-heyuan"
TEMPLATE_NAME = "TrainingHardDeadlineStop"
DOMAIN = f"oos.{REGION}.aliyuncs.com"
VERSION = "2019-06-01"

TEMPLATE = {
    "FormatVersion": "OOS-2019-06-01",
    "Description": "One-shot hard deadline stop for training ECS (StopCharging)",
    "Parameters": {
        "regionId": {"Type": "String", "Description": "Instance region"},
        "instanceId": {"Type": "String", "Description": "ECS instance to stop at deadline"},
        "deadline": {"Type": "String", "Description": "ISO8601 absolute deadline, e.g. 2026-11-19T03:00:00+08:00"}
    },
    # 【2026-11-18 21:30】OOSServiceRole 已由 owner 在控制台建好（信任 oos.aliyuncs.com）。
    # TimerTrigger 模板强制要求 RamRole（平台硬约束，已实测两种路径都拒），必须显式指定。
    "RamRole": "OOSServiceRole",
    "Tasks": [
        {
            "Name": "waitUntilDeadline",
            "Action": "ACS::TimerTrigger",
            "Properties": {
                "Type": "at",
                "Expression": "{{ deadline }}",
                "EndDate": "{{ deadline }}",
                "TimeZone": "Asia/Shanghai"
            }
        },
        {
            "Name": "stopAtHardDeadline",
            "Action": "ACS::ECS::StopInstance",
            "Properties": {
                "regionId": "{{ regionId }}",
                "instanceId": "{{ instanceId }}",
                "stoppedMode": "StopCharging",
                "forceStop": False
            }
        }
    ],
    "Outputs": {}
}


def client():
    lines = [ln.strip() for ln in open(resolve_ak_file(), encoding="utf-8-sig").read().splitlines() if ln.strip()]
    return AcsClient(lines[0], lines[1], region_id=REGION)


def call(action, params, c):
    r = CommonRequest()
    r.set_accept_format("json")
    r.set_protocol_type("https")
    r.set_domain(DOMAIN)
    r.set_version(VERSION)
    r.set_action_name(action)
    r.set_method("POST")
    for k, v in params.items():
        r.add_query_param(k, v)
    return json.loads(c.do_action_with_exception(r))


def normalize_deadline(s):
    """TimerTrigger Type=at 接受 ISO8601；EndDate 需 UTC 'Z' 格式。"""
    dt = datetime.fromisoformat(s)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone(timedelta(hours=8)))
    utc = dt.astimezone(timezone.utc)
    return s, utc.strftime("%Y-%m-%dT%H:%M:%SZ")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--deploy-template", action="store_true")
    ap.add_argument("--arm", action="store_true", help="创建到点停机的执行")
    ap.add_argument("--disarm", action="store_true", help="取消执行")
    ap.add_argument("--list", action="store_true")
    ap.add_argument("--dry-run", action="store_true", help="只打印将发的请求，不调用任何写 API")
    ap.add_argument("--deadline", default="", help="ISO8601 绝对时刻，如 2026-11-19T03:00:00+08:00")
    ap.add_argument("--execution-id", default="")
    ap.add_argument("--instance", default="i-f8zcp6vvis4rnztw0p9y")
    args = ap.parse_args()

    if args.dry_run:
        print("[dry-run] 以下请求不会真正发出")
        if args.deadline:
            expr, end = normalize_deadline(args.deadline)
            print(f"  TimerTrigger: Type=at Expression={expr} EndDate={end} TimeZone=Asia/Shanghai")
            print(f"  StopInstance: regionId={REGION} instanceId={args.instance} stoppedMode=StopCharging")
        return

    c = client()
    if args.list:
        t = call("ListTemplates", {"Limit": 50}, c)
        print("TEMPLATES:", [x.get("TemplateName") for x in t.get("Templates", [])])
        e = call("ListExecutions", {"Limit": 20}, c)
        for x in e.get("Executions", []):
            print("EXEC:", x.get("ExecutionId"), x.get("Status"), x.get("TemplateName"),
                  x.get("Parameters", "")[:120], x.get("StartDate"))
        return
    if args.deploy_template:
        res = call("CreateTemplate", {
            "TemplateName": TEMPLATE_NAME,
            "Content": json.dumps(TEMPLATE, ensure_ascii=False),
        }, c)
        t = res.get("Template", {})
        print(f"DEPLOYED template={t.get('TemplateName')} version={t.get('TemplateVersion')} id={t.get('TemplateId')}")
        return
    if args.arm:
        if not args.deadline:
            ap.error("--arm 需要 --deadline")
        expr, end = normalize_deadline(args.deadline)
        # TimerTrigger 实测（exec-ff871...）：Expression 必须是 UTC 'Z' 格式，
        # 传 '+08:00' 会 Failed: "The (...) format is invalid. Example: 2019-06-18T09:12:43Z."
        params = {
            "regionId": REGION,
            "instanceId": args.instance,
            "deadline": end,
        }
        res = call("StartExecution", {
            "TemplateContent": json.dumps(TEMPLATE, ensure_ascii=False),
            "Parameters": json.dumps(params),
            "Description": f"hard deadline {expr} -> StopCharging {args.instance}",
        }, c)
        ex = res.get("Execution", {})
        print(f"ARMED execution={ex.get('ExecutionId')} status={ex.get('Status')} "
              f"params={ex.get('Parameters')}")
        return
    if args.disarm:
        if not args.execution_id:
            ap.error("--disarm 需要 --execution-id")
        call("CancelExecution", {"ExecutionId": args.execution_id}, c)
        print(f"DISARMED execution={args.execution_id}")
        return
    ap.print_help()


if __name__ == "__main__":
    main()
