"""阿里云 ECS 按量实例「库存 + 价格」探查（运维辅助脚本，可随时删除）。

解决的问题：控制台里 32 核显示无货，不知道该换哪个规格 / 哪个地域。

AK 文件（默认 ~/.aliyun_ak.txt，可用环境变量 ALIYUN_AK_FILE 覆盖）：
    第 1 行  AccessKeyId
    第 2 行  AccessKeySecret
    第 3 行  （可选）默认地域，如 cn-wulanchabu

用法：
    python scripts/cloud/probe_aliyun_ecs.py                # 查默认地域
    python scripts/cloud/probe_aliyun_ecs.py cn-beijing     # 查指定地域
    python scripts/cloud/probe_aliyun_ecs.py --regions      # 列出全部地域
    python scripts/cloud/probe_aliyun_ecs.py cn-wulanchabu --price   # 附带单价

注意：只查询（Describe* 只读接口），不下单、不产生任何费用。
"""
import argparse
import json
import os
import sys

from aliyunsdkcore.client import AcsClient
from aliyunsdkcore.request import CommonRequest

AK_FILE = os.environ.get(
    "ALIYUN_AK_FILE",
    os.path.join(os.path.expanduser("~"), ".aliyun_ak.txt"),
)


def load_ak(path: str):
    if not os.path.exists(path):
        sys.exit(f"[错误] 找不到 AK 文件：{path}\n"
                 f"请创建该文件：第 1 行 AccessKeyId，第 2 行 AccessKeySecret，第 3 行（可选）地域")
    with open(path, encoding="utf-8-sig") as f:
        lines = [ln.strip() for ln in f if ln.strip() and not ln.strip().startswith("#")]
    if len(lines) < 2:
        sys.exit("[错误] AK 文件至少需要 2 行（AccessKeyId / AccessKeySecret）")
    return lines[0], lines[1], (lines[2] if len(lines) > 2 else None)


def call(client, action: str, params: dict, region: str = "cn-hangzhou") -> dict:
    """调用 ECS OpenAPI（endpoint 必须带地域，否则新地域会报 NotSupportedEndpoint）。"""
    req = CommonRequest()
    req.set_accept_format("json")
    req.set_domain(f"ecs.{region}.aliyuncs.com")
    req.set_version("2014-05-26")
    req.set_action_name(action)
    req.set_method("POST")
    for k, v in params.items():
        req.add_query_param(k, v)
    return json.loads(client.do_action_with_exception(req))


def list_regions(client):
    res = call(client, "DescribeRegions", {})
    for r in res.get("Regions", {}).get("Region", []):
        print(f'{r.get("RegionId", ""):26s} {r.get("LocalName", "")}')


def available_types(client, region: str) -> dict:
    """返回 {instance_type: set(zone_ids)}，仅含按量付费且状态可用的规格。"""
    res = call(client, "DescribeAvailableResource", {
        "RegionId": region,
        "DestinationResource": "InstanceType",
        "InstanceChargeType": "PostPaid",
        "SpotStrategy": "NoSpot",
    }, region=region)
    avail = {}
    for z in res.get("AvailableZones", {}).get("AvailableZone", []):
        zid = z.get("ZoneId")
        for ar in z.get("AvailableResources", {}).get("AvailableResource", []):
            for sr in ar.get("SupportedResources", {}).get("SupportedResource", []):
                if sr.get("Status") == "Available" and sr.get("Value"):
                    avail.setdefault(sr["Value"], set()).add(zid)
    return avail


def type_info(client, region: str, types: list) -> dict:
    info = {}
    for i in range(0, len(types), 100):
        batch = types[i:i + 100]
        params = {"RegionId": region, "MaxResults": "100"}
        for j, t in enumerate(batch, 1):
            params[f"InstanceTypes.{j}"] = t
        res = call(client, "DescribeInstanceTypes", params, region=region)
        for it in res.get("InstanceTypes", {}).get("InstanceType", []):
            info[it["InstanceTypeId"]] = it
    return info


def hourly_price(client, region: str, itype: str):
    res = call(client, "DescribePrice", {
        "RegionId": region,
        "ResourceType": "instance",
        "InstanceType": itype,
        "PriceUnit": "Hour",
        "Amount": "1",
        # 必须显式给系统盘类型：部分地域默认值不支持（如河源），否则报
        # InvalidSystemDiskCategory.ValueNotSupported
        "SystemDisk.Category": "cloud_essd",
    }, region=region)
    # PriceInfo.Price 在单资源查询时可能是对象而非数组，两种都要兼容
    price = res.get("PriceInfo", {}).get("Price")
    if isinstance(price, list):
        price = price[0] if price else None
    if not isinstance(price, dict):
        return None
    inner = price.get("Price") if isinstance(price.get("Price"), dict) else price
    for key in ("TradePrice", "OriginalPrice", "DiscountPrice"):
        if inner.get(key) is not None:
            return float(inner[key])
    return None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("region", nargs="?", default=None, help="地域 ID，如 cn-wulanchabu")
    ap.add_argument("--regions", action="store_true", help="只列出全部地域")
    ap.add_argument("--price", action="store_true", help="顺带查询按量单价（较慢）")
    ap.add_argument("--min-cpu", type=int, default=8, help="最小 vCPU 数（默认 8）")
    ap.add_argument("--max-mem", type=float, default=128.0, help="最大内存 GiB（默认 128）")
    args = ap.parse_args()

    ak_id, ak_secret, default_region = load_ak(AK_FILE)
    client = AcsClient(ak_id, ak_secret, region_id="cn-hangzhou")

    if args.regions:
        list_regions(client)
        return

    region = args.region or default_region
    if not region:
        sys.exit("[错误] 未指定地域。请用参数传入，或在 AK 文件第 3 行写默认地域")

    print(f"[查询] 地域 {region} 按量付费可用规格 ...")
    avail = available_types(client, region)
    if not avail:
        print("  该地域没有任何按量可用规格（可能全部售罄），建议换地域或换抢占式")
        return

    info = type_info(client, region, list(avail.keys()))

    rows = []
    for itype, zones in avail.items():
        it = info.get(itype)
        if not it:
            continue
        cpu = int(it.get("CpuCoreCount", 0) or 0)
        mem = float(it.get("MemorySize", 0) or 0)
        if cpu < args.min_cpu or mem > args.max_mem:
            continue
        freq = it.get("CpuSpeed", "") or ""
        rows.append((cpu, mem, itype, freq, sorted(zones)))

    rows.sort(key=lambda r: (r[0], r[1], r[2]))
    if not rows:
        print(f"  没有 vCPU>={args.min_cpu} 的可用规格；该地域最大可用规格如下：")
        for itype, zones in sorted(avail.items())[:20]:
            it = info.get(itype, {})
            print(f'    {itype:28s} {it.get("CpuCoreCount", "?"):>4} vCPU '
                  f'{it.get("MemorySize", "?"):>6} GiB  可用区 {",".join(sorted(zones))}')
        return

    header = f'{"实例规格":30s} {"vCPU":>5} {"内存GiB":>8} {"主频GHz":>8}  可用区'
    if args.price:
        header += "  按量元/时"
    print(header)
    print("-" * (len(header) + 6))
    for cpu, mem, itype, freq, zones in rows:
        line = f'{itype:30s} {cpu:5d} {mem:8.0f} {str(freq):>8}  {",".join(zones)}'
        if args.price:
            try:
                p = hourly_price(client, region, itype)
                line += f'  {p:>9.3f}' if p is not None else "        ?"
            except Exception as e:
                line += f"  err({str(e).splitlines()[0][:70]})"
        print(line)

    print(f"\n共 {len(rows)} 个 vCPU>={args.min_cpu} 的可用规格。"
          f"租前请确认：按量付费 + 节省停机模式 + Ubuntu 24.04 + 开 22 端口。")


if __name__ == "__main__":
    main()
