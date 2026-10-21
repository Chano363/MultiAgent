"""阿里云 ECS 下单前置检查（只读，不下单、不产生费用）。

确认下单所需的全部依赖是否就绪：VPC / 交换机 / 安全组 / 密钥对 / Ubuntu 24.04 镜像。

用法：
    python scripts/cloud/preflight_aliyun_ecs.py cn-heyuan
"""
import os
import sys

from aliyunsdkcore.client import AcsClient
from aliyunsdkcore.request import CommonRequest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from probe_aliyun_ecs import call, load_ak  # noqa: E402


def main():
    region = sys.argv[1] if len(sys.argv) > 1 else "cn-heyuan"
    ak_id, ak_secret, _ = load_ak(os.environ.get(
        "ALIYUN_AK_FILE",
        os.path.join(os.path.expanduser("~"), ".aliyun_ak.txt"),
    ))
    client = AcsClient(ak_id, ak_secret, region_id=region)

    print(f"===== 地域 {region} 下单前置检查 =====")

    # 可用区
    res = call(client, "DescribeZones", {"RegionId": region}, region=region)
    zones = [z.get("ZoneId") for z in res.get("Zones", {}).get("Zone", [])]
    print(f"[可用区] {', '.join(zones)}")

    # VPC
    res = call(client, "DescribeVpcs", {"RegionId": region, "PageSize": "50"}, region=region)
    vpcs = res.get("Vpcs", {}).get("Vpc", [])
    print(f"[VPC] {len(vpcs)} 个")
    for v in vpcs:
        print(f'   {v.get("VpcId")}  {v.get("CidrBlock")}  default={v.get("IsDefault")}  {v.get("VpcName", "")}')

    # 交换机
    res = call(client, "DescribeVSwitches", {"RegionId": region, "PageSize": "50"}, region=region)
    vsws = res.get("VSwitches", {}).get("VSwitch", [])
    print(f"[交换机] {len(vsws)} 个")
    for s in vsws:
        print(f'   {s.get("VSwitchId")}  zone={s.get("ZoneId")}  cidr={s.get("CidrBlock")}')

    # 安全组
    res = call(client, "DescribeSecurityGroups", {"RegionId": region, "PageSize": "50"}, region=region)
    sgs = res.get("SecurityGroups", {}).get("SecurityGroup", [])
    print(f"[安全组] {len(sgs)} 个")
    for g in sgs:
        print(f'   {g.get("SecurityGroupId")}  vpc={g.get("VpcId")}  {g.get("SecurityGroupName", "")}')

    # 密钥对
    res = call(client, "DescribeKeyPairs", {"RegionId": region, "PageSize": "50"}, region=region)
    kps = res.get("KeyPairs", {}).get("KeyPair", [])
    print(f"[密钥对] {len(kps)} 个")
    for k in kps:
        print(f'   {k.get("KeyPairName")}  fp={k.get("FingerPrint", "")[:24]}')

    # Ubuntu 24.04 镜像
    res = call(client, "DescribeImages", {
        "RegionId": region,
        "OSType": "linux",
        "Architecture": "x86_64",
        "ImageOwnerAlias": "system",
        "PageSize": "100",
    }, region=region)
    imgs = [im for im in res.get("Images", {}).get("Image", [])
            if "24_04" in (im.get("ImageId") or "") or "24.04" in (im.get("OSName") or "")]
    print(f"[Ubuntu 24.04 镜像] {len(imgs)} 个")
    for im in sorted(imgs, key=lambda x: x.get("ImageId", ""))[-5:]:
        print(f'   {im.get("ImageId")}  {im.get("OSName", "")}  size={im.get("Size")}GiB')


if __name__ == "__main__":
    main()
