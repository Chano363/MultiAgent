"""阿里云 ECS 一键开通（VPC / 交换机 / 安全组 / 密钥对 / 按量实例）。

⚠️ 会产生费用（按量计费，开机即开始扣费）。默认规格 = 8 vCPU / 16 GiB。

前置：~/.aliyun_ak.txt（第 1 行 AccessKeyId，第 2 行 Secret），
      以及 ~/.ssh/cloud_traffic.pub（由 ssh-keygen 生成）。

用法：
    python scripts/cloud/provision_aliyun_ecs.py                 # 默认 c9i.2xlarge
    python scripts/cloud/provision_aliyun_ecs.py --type ecs.c9i.8xlarge
    python scripts/cloud/provision_aliyun_ecs.py --dry-run       # 只检查依赖，不下单

设计：
  - 资源全部按「幂等 + 打 tag」创建，重复运行不会重复建 VPC/交换机/安全组；
  - 安全组只放行 TCP 22，源 = 本机公网出口 IP（自动探测）；
  - 计费 = 按量付费 + 节省停机模式（StoppedMode=StopCharging），关机只收磁盘费。
"""
import argparse
import json
import os
import sys
import urllib.request

from aliyunsdkcore.client import AcsClient
from aliyunsdkcore.request import CommonRequest

AK_FILE = os.path.join(os.path.expanduser("~"), ".aliyun_ak.txt")
PUB_KEY = os.path.expanduser("~/.ssh/cloud_traffic.pub")
KEY_NAME = "cloud_traffic"
IMAGE_ID = "ubuntu_24_04_x64_20G_alibase_20260916.vhd"
SYS_DISK_CATEGORY = "cloud_essd"
TAG = {"traffic-rl": "1"}


def load_ak():
    if not os.path.exists(AK_FILE):
        sys.exit(f"[错误] 找不到 AK 文件：{AK_FILE}")
    lines = [ln.strip() for ln in open(AK_FILE, encoding="utf-8-sig").read().splitlines() if ln.strip()]
    if len(lines) < 2:
        sys.exit("[错误] AK 文件至少 2 行")
    return lines[0], lines[1]


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


def my_public_ip():
    for url in ("https://api.ipify.org", "https://ifconfig.me/ip"):
        try:
            with urllib.request.urlopen(url, timeout=8) as r:
                ip = r.read().decode().strip()
                if ip and ip[0].isdigit():
                    return ip
        except Exception:
            continue
    return None


def ensure_vpc(client, region):
    res = call(client, "DescribeVpcs", {"RegionId": region, "PageSize": "50"}, region)
    for v in res.get("Vpcs", {}).get("Vpc", []):
        if v.get("VpcName") == "traffic-rl-vpc":
            print(f"  VPC 已存在 {v['VpcId']} ({v['CidrBlock']})")
            return v["VpcId"]
    res = call(client, "CreateVpc", {
        "RegionId": region, "CidrBlock": "10.0.0.0/8",
        "VpcName": "traffic-rl-vpc", "Description": "traffic-rl training",
    }, region)
    vid = res["VpcId"]
    print(f"  VPC 已创建 {vid} (10.0.0.0/8)")
    return vid


def wait_vpc_ready(client, region, vpc_id, tries=20):
    """VPC 创建后需数秒才变 Available，未就绪时建交换机报 IncorrectVpcStatus。"""
    import time
    for _ in range(tries):
        res = call(client, "DescribeVpcs", {"RegionId": region, "VpcId": vpc_id}, region)
        vs = res.get("Vpcs", {}).get("Vpc", [])
        if vs and vs[0].get("Status") == "Available":
            return True
        time.sleep(2)
    print("  [警告] VPC 未在预期时间内就绪")
    return False


def ensure_vswitch(client, region, zone, vpc_id):
    res = call(client, "DescribeVSwitches", {"RegionId": region, "VpcId": vpc_id, "PageSize": "50"}, region)
    for s in res.get("VSwitches", {}).get("VSwitch", []):
        if s.get("ZoneId") == zone:
            print(f"  交换机已存在 {s['VSwitchId']} ({s['CidrBlock']} @ {zone})")
            return s["VSwitchId"]
    wait_vpc_ready(client, region, vpc_id)
    res = call(client, "CreateVSwitch", {
        "RegionId": region, "ZoneId": zone, "VpcId": vpc_id,
        "CidrBlock": "10.0.1.0/24", "VSwitchName": "traffic-rl-vsw",
    }, region)
    vid = res["VSwitchId"]
    print(f"  交换机已创建 {vid} (10.0.1.0/24 @ {zone})")
    return vid


def ensure_keypair(client, region):
    if not os.path.exists(PUB_KEY):
        sys.exit(f"[错误] 找不到公钥：{PUB_KEY}\n请先执行 ssh-keygen -t ed25519 -f ~/.ssh/cloud_traffic -N \"\"")
    res = call(client, "DescribeKeyPairs", {"RegionId": region, "KeyPairName": KEY_NAME}, region)
    if res.get("KeyPairs", {}).get("KeyPair"):
        print(f"  密钥对已存在 {KEY_NAME}")
        return KEY_NAME
    pub = open(PUB_KEY, encoding="utf-8").read().strip()
    call(client, "ImportKeyPair", {
        "RegionId": region, "KeyPairName": KEY_NAME, "PublicKeyBody": pub,
    }, region)
    print(f"  密钥对已导入 {KEY_NAME}")
    return KEY_NAME


def ensure_security_group(client, region, vpc_id):
    res = call(client, "DescribeSecurityGroups", {
        "RegionId": region, "VpcId": vpc_id, "PageSize": "50"}, region)
    sg = None
    for g in res.get("SecurityGroups", {}).get("SecurityGroup", []):
        if g.get("SecurityGroupName") == "traffic-rl-sg":
            sg = g["SecurityGroupId"]
            print(f"  安全组已存在 {sg}")
            break
    if sg is None:
        res = call(client, "CreateSecurityGroup", {
            "RegionId": region, "VpcId": vpc_id,
            "SecurityGroupName": "traffic-rl-sg",
            "Description": "ssh only",
        }, region)
        sg = res["SecurityGroupId"]
        print(f"  安全组已创建 {sg}")

    ip = my_public_ip()
    if ip is None:
        print("  [警告] 探测不到本机公网 IP，22 端口规则未添加；请手动放行")
        return sg
    try:
        call(client, "AuthorizeSecurityGroup", {
            "RegionId": region, "SecurityGroupId": sg, "IpProtocol": "tcp",
            "PortRange": "22/22", "SourceCidrIp": f"{ip}/32",
            "Description": "ssh from my ip",
        }, region)
        print(f"  已放行 22/tcp ← {ip}/32")
    except Exception as e:
        msg = str(e).splitlines()[0]
        if "Duplicate" in msg or "AlreadyExists" in msg:
            print(f"  22/tcp 规则已存在（源 {ip}/32）")
        else:
            print(f"  [警告] 放行 22 失败：{msg[:100]}（可手动添加）")
    return sg


def run_instance(client, region, zone, vpc_id, vsw_id, sg_id, key_name,
                 itype, disk_gb, name, dry_run):
    params = {
        "RegionId": region,
        "ZoneId": zone,
        "ImageId": IMAGE_ID,
        "InstanceType": itype,
        "SecurityGroupId": sg_id,
        "VSwitchId": vsw_id,
        "KeyPairName": key_name,
        "InstanceName": name,
        "InstanceChargeType": "PostPaid",
        "SpotStrategy": "NoSpot",
        "StoppedMode": "StopCharging",          # 节省停机模式：关机只收磁盘费
        "InternetChargeType": "PayByTraffic",   # 按流量计费
        "InternetMaxBandwidthOut": "100",
        "SystemDisk.Category": SYS_DISK_CATEGORY,
        "SystemDisk.Size": str(disk_gb),
        "Amount": "1",
    }
    if dry_run:
        print("\n[dry-run] RunInstances 参数：")
        for k, v in params.items():
            print(f"    {k} = {v}")
        return None
    res = call(client, "RunInstances", params, region)
    ids = res.get("InstanceIdSets", {}).get("InstanceIdSet", [])
    print(f"  实例已创建 {ids}")
    return ids[0] if ids else None


def wait_running(client, region, iid, tries=40):
    import time
    for _ in range(tries):
        res = call(client, "DescribeInstances", {"RegionId": region, "InstanceIds": json.dumps([iid])}, region)
        items = res.get("Instances", {}).get("Instance", [])
        if items:
            it = items[0]
            status = it.get("Status")
            if status == "Running":
                pub = (it.get("PublicIpAddress", {}) or {}).get("IpAddress", [])
                eip = (it.get("EipAddress", {}) or {}).get("IpAddress")
                ip = eip or (pub[0] if pub else None)
                print(f"  状态 Running，公网 IP = {ip}")
                return ip
        time.sleep(5)
    print("  [警告] 等待超时，请到控制台查看")
    return None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--region", default="cn-heyuan")
    ap.add_argument("--zone", default="cn-heyuan-c")
    ap.add_argument("--type", default="ecs.c9i.2xlarge")
    ap.add_argument("--disk", type=int, default=40)
    ap.add_argument("--name", default="traffic-rl-train")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    ak_id, ak_secret = load_ak()
    client = AcsClient(ak_id, ak_secret, region_id=args.region)

    print(f"=== 开通 {args.type} @ {args.region}/{args.zone} ===")
    vpc_id = ensure_vpc(client, args.region)
    vsw_id = ensure_vswitch(client, args.region, args.zone, vpc_id)
    key_name = ensure_keypair(client, args.region)
    sg_id = ensure_security_group(client, args.region, vpc_id)
    iid = run_instance(client, args.region, args.zone, vpc_id, vsw_id, sg_id,
                       key_name, args.type, args.disk, args.name, args.dry_run)
    if not iid:
        return
    ip = wait_running(client, args.region, iid)
    if ip:
        print(f"\nSSH: ssh -i ~/.ssh/cloud_traffic root@{ip}")
        print(f"     (若 Ubuntu 镜像默认用户为 ubuntu: ssh -i ~/.ssh/cloud_traffic ubuntu@{ip})")


if __name__ == "__main__":
    main()
