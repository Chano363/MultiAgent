"""阿里云 ECS 实例状态查询 / 停止 + 二次复核（最省钱原则的执行工具）。

用途：
  1. 查状态，确认是否已真正停费（Status=Stopped 且 StoppedMode=StopCharging）
  2. 停止实例后**自动二次复核**，把回执打印出来作为"已停费"证据

用法：
    python scripts/cloud/instance_state_aliyun_ecs.py                      # 列出本项目全部实例
    python scripts/cloud/instance_state_aliyun_ecs.py i-xxxx               # 查单个实例
    python scripts/cloud/instance_state_aliyun_ecs.py --stop i-xxxx        # 停止 + 自动复核
    python scripts/cloud/instance_state_aliyun_ecs.py --stop i-xxxx --release  # 释放（不可逆，慎用）

AK：~/.aliyun_ak.txt（第 1 行 AccessKeyId，第 2 行 Secret，第 3 行可选默认地域）
"""
import argparse
import json
import os
import sys
import time

from aliyunsdkcore.client import AcsClient
from aliyunsdkcore.request import CommonRequest

AK_FILE = os.path.join(os.path.expanduser("~"), ".aliyun_ak.txt")
DEFAULT_REGION = "cn-heyuan"


def load_ak():
    if not os.path.exists(AK_FILE):
        sys.exit(f"[错误] 找不到 AK 文件：{AK_FILE}")
    lines = [ln.strip() for ln in open(AK_FILE, encoding="utf-8-sig").read().splitlines() if ln.strip()]
    if len(lines) < 2:
        sys.exit("[错误] AK 文件至少 2 行")
    return lines[0], lines[1], (lines[2] if len(lines) > 2 else DEFAULT_REGION)


def call(client, action, params, region):
    req = CommonRequest()
    req.set_accept_format("json")
    req.set_domain(f"ecs.{region}.aliyuncs.com")
    req.set_version("2014-05-26")
    req.set_action_name(action)
    req.set_method("POST")
    for k, v in params.items():
        req.add_query_param(k, v)
    return json.loads(client.do_action_with_exception(req))


def describe(client, region, iid=None):
    params = {"RegionId": region, "PageSize": "100"}
    if iid:
        params["InstanceIds"] = json.dumps([iid])
    res = call(client, "DescribeInstances", params, region)
    return res.get("Instances", {}).get("Instance", [])


def show(items):
    if not items:
        print("  （无匹配实例）")
        return
    for it in items:
        print(f"  InstanceId   = {it.get('InstanceId')}")
        print(f"  Name         = {it.get('InstanceName')}")
        print(f"  Status       = {it.get('Status')}")
        print(f"  StoppedMode  = {it.get('StoppedMode')}")
        print(f"  ChargeType   = {it.get('InstanceChargeType')}")
        print(f"  Type         = {it.get('InstanceType')}")
        print(f"  PublicIp     = {(it.get('PublicIpAddress') or {}).get('IpAddress')}")
        print(f"  CreationTime = {it.get('CreationTime')}")
        print("  " + "-" * 46)


def verify_stopped(client, region, iid, tries=30):
    """二次复核：必须 Status=Stopped 且 StoppedMode=StopCharging。"""
    for _ in range(tries):
        items = describe(client, region, iid)
        if items:
            it = items[0]
            st = it.get("Status")
            mode = it.get("StoppedMode")
            print(f"  [复核] Status={st}  StoppedMode={mode}")
            if st == "Stopped":
                if mode == "StopCharging":
                    print("  ✅ 已停费（仅收磁盘费）")
                    return True
                print("  ⚠️ 已停止但 StoppedMode != StopCharging，**仍在收计算费**，请改配置")
                return False
        time.sleep(5)
    print("  ❌ 复核超时：未确认停机，请立刻到控制台检查")
    return False


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("instance_id", nargs="?", default=None)
    ap.add_argument("--region", default=None)
    ap.add_argument("--stop", metavar="IID", default=None, help="停止实例（节省停机）并自动复核")
    ap.add_argument("--release", action="store_true", help="配合 --stop 使用：停止后释放（不可逆）")
    args = ap.parse_args()

    ak_id, ak_secret, ak_region = load_ak()
    region = args.region or ak_region or DEFAULT_REGION
    client = AcsClient(ak_id, ak_secret, region_id=region)

    if args.stop:
        iid = args.stop
        print(f"=== 停止 {iid} @ {region}（StoppedMode=StopCharging）===")
        try:
            call(client, "StopInstance", {
                "RegionId": region, "InstanceId": iid,
                "StoppedMode": "StopCharging", "ForceStop": "false",
            }, region)
        except Exception as e:
            print(f"  StopInstance 报错：{str(e).splitlines()[0][:120]}")
        ok = verify_stopped(client, region, iid)
        show(describe(client, region, iid))

        if args.release and ok:
            print(f"=== 释放 {iid}（不可逆）===")
            call(client, "DeleteInstance", {
                "RegionId": region, "InstanceId": iid, "Force": "true",
            }, region)
            print("  已释放")
        return

    print(f"=== {region} 实例状态 ===")
    show(describe(client, region, args.instance_id))


if __name__ == "__main__":
    main()
