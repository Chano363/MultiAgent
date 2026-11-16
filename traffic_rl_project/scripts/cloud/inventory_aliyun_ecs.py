"""阿里云资源全景盘点（本项目专用）：实例 / 镜像 / 快照 / VPC / 交换机 / 安全组 / 密钥对。

用途：一眼看清"我现在还有哪些资源、哪些在花钱、哪些该删"。
只调 Describe*（只读），不产生任何费用、不修改任何资源。

用法：
    python scripts/cloud/inventory_aliyun_ecs.py                 # 默认地域（AK 文件第 3 行或 cn-heyuan）
    python scripts/cloud/inventory_aliyun_ecs.py --region cn-heyuan
    python scripts/cloud/inventory_aliyun_ecs.py --cost          # 附带费用估算

AK：~/.aliyun_ak.txt（第 1 行 AccessKeyId，第 2 行 Secret，第 3 行可选默认地域）
"""
import argparse
import json
import os
import sys

from aliyunsdkcore.client import AcsClient
from aliyunsdkcore.request import CommonRequest

from ak_path import resolve_ak_file

AK_FILE = resolve_ak_file()
TAG = "traffic-rl"

# 单价（元），用于费用估算；实际以账单为准
PRICE_INSTANCE_PER_VCPU_H = 0.1756   # c9i 折合每 vCPU·小时（32 vCPU = 5.619）
PRICE_ESSD_GB_H = 0.084 / 40         # ESSD PL0：40 GiB = 0.084 元/h
PRICE_SNAPSHOT_GB_MONTH = 0.1385     # 快照/镜像存储
HOURS_PER_MONTH = 730


def load_ak():
    if not os.path.exists(AK_FILE):
        sys.exit(f"[错误] 找不到 AK 文件：{AK_FILE}\n"
                 f"请创建该文件：第 1 行 AccessKeyId，第 2 行 AccessKeySecret，"
                 f"第 3 行可选默认地域（如 cn-heyuan）")
    lines = [ln.strip() for ln in open(AK_FILE, encoding="utf-8-sig").read().splitlines() if ln.strip()]
    if len(lines) < 2:
        sys.exit("[错误] AK 文件至少需要 2 行（AccessKeyId / Secret）")
    return lines[0], lines[1], (lines[2] if len(lines) > 2 else "cn-heyuan")


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


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--region", default=None)
    ap.add_argument("--cost", action="store_true", help="附带每小时/每月费用估算")
    args = ap.parse_args()

    ak_id, ak_secret, ak_region = load_ak()
    region = args.region or ak_region
    client = AcsClient(ak_id, ak_secret, region_id=region)
    print(f"===== 地域 {region} =====\n")

    total_hour = 0.0
    total_month = 0.0

    # ---------- 实例 ----------
    items = call(client, "DescribeInstances", {"RegionId": region, "PageSize": "100"}, region) \
        .get("Instances", {}).get("Instance", [])
    print(f"[实例] {len(items)} 台")
    for it in items:
        vcpu = None
        for k in ("Cpu", "CpuOptions"):
            if k == "Cpu" and it.get(k):
                vcpu = it.get(k)
        st = it.get("Status")
        mode = it.get("StoppedMode")
        fee = ""
        if st == "Running":
            fee = "计费中"
            total_hour += 5.619
            total_month += 5.619 * HOURS_PER_MONTH
        elif st == "Stopped" and mode == "StopCharging":
            fee = "仅磁盘 0.084元/h"
            total_hour += 0.084
            total_month += 0.084 * HOURS_PER_MONTH
        else:
            fee = "计费中（未启用节省停机）"
            total_hour += 5.619
            total_month += 5.619 * HOURS_PER_MONTH
        print(f"   {it.get('InstanceId')}  {it.get('InstanceName')}  {it.get('InstanceType')}")
        print(f"      Status={st}  StoppedMode={mode}  PublicIp={(it.get('PublicIpAddress') or {}).get('IpAddress')}  → {fee}")

    # ---------- 镜像 ----------
    imgs = call(client, "DescribeImages",
                {"RegionId": region, "ImageOwnerAlias": "self", "PageSize": "50"}, region) \
        .get("Images", {}).get("Image", [])
    print(f"\n[自定义镜像] {len(imgs)} 个")
    for im in imgs:
        size = im.get("Size") or 0
        month = size * PRICE_SNAPSHOT_GB_MONTH
        total_month += month
        print(f"   {im.get('ImageId')}  {im.get('ImageName')}  {im.get('Status')}  {size}GiB  "
              f"{im.get('CreationTime')}  → 上限 {month:.1f} 元/月")

    # ---------- 快照 ----------
    try:
        snaps = call(client, "DescribeSnapshots",
                     {"RegionId": region, "PageSize": "50"}, region) \
            .get("Snapshots", {}).get("Snapshot", [])
        print(f"\n[快照] {len(snaps)} 个（镜像是快照的引用，删除镜像后快照可单独删）")
        for s in snaps:
            print(f"   {s.get('SnapshotId')}  {s.get('SnapshotName')}  "
                  f"源盘 {s.get('SourceDiskSize')}GiB  实际 {s.get('SnapshotSize')}GiB  {s.get('Status')}")
    except Exception as e:
        print(f"\n[快照] 查询失败：{str(e).splitlines()[0][:100]}")

    # ---------- 网络 ----------
    vpcs = call(client, "DescribeVpcs", {"RegionId": region, "PageSize": "50"}, region) \
        .get("Vpcs", {}).get("Vpc", [])
    print(f"\n[VPC] {len(vpcs)} 个（免费）")
    for v in vpcs:
        print(f"   {v.get('VpcId')}  {v.get('VpcName')}  {v.get('CidrBlock')}  {v.get('Status')}")
        vsw = call(client, "DescribeVSwitches",
                   {"RegionId": region, "VpcId": v.get("VpcId"), "PageSize": "50"}, region) \
            .get("VSwitches", {}).get("VSwitch", [])
        for s in vsw:
            print(f"      └ 交换机 {s.get('VSwitchId')}  {s.get('VSwitchName')}  "
                  f"{s.get('CidrBlock')}  {s.get('ZoneId')}")

    sgs = call(client, "DescribeSecurityGroups", {"RegionId": region, "PageSize": "50"}, region) \
        .get("SecurityGroups", {}).get("SecurityGroup", [])
    print(f"\n[安全组] {len(sgs)} 个（免费）")
    for g in sgs:
        print(f"   {g.get('SecurityGroupId')}  {g.get('SecurityGroupName')}  Vpc={g.get('VpcId')}")

    kps = call(client, "DescribeKeyPairs", {"RegionId": region, "PageSize": "50"}, region) \
        .get("KeyPairs", {}).get("KeyPair", [])
    print(f"\n[密钥对] {len(kps)} 个（免费，只是公钥登记）")
    for k in kps:
        print(f"   {k.get('KeyPairName')}  fp={k.get('KeyPairFingerPrint')}")

    if args.cost:
        print("\n===== 费用估算 =====")
        print(f"  当前每小时 ≈ {total_hour:.3f} 元")
        print(f"  当前每月   ≈ {total_month:.1f} 元（按 {HOURS_PER_MONTH} h/月）")
        print("  注：镜像/快照按实际数据量计费，此处用镜像标称容量取上限；以账单为准。")


if __name__ == "__main__":
    main()
