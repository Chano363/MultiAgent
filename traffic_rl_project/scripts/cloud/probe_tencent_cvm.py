"""腾讯云 CVM 按量实例「库存 + 价格」探查（运维辅助脚本，可随时删除）。

AK 文件（默认 D:\\tencent_ak.txt，可用环境变量 TENCENT_AK_FILE 覆盖）：
    第 1 行  SecretId
    第 2 行  SecretKey
    第 3 行  （可选）默认地域，如 ap-beijing

用法：
    python scripts/cloud/probe_tencent_cvm.py                 # 查默认地域
    python scripts/cloud/probe_tencent_cvm.py ap-beijing      # 查指定地域
    python scripts/cloud/probe_tencent_cvm.py --regions       # 列出全部地域

注意：只查询，不下单、不产生任何费用。
"""
import argparse
import json
import os
import sys

from tencentcloud.common import credential
from tencentcloud.cvm.v20170312 import cvm_client, models

AK_FILE = os.environ.get("TENCENT_AK_FILE", r"D:\tencent_ak.txt")


def load_ak(path: str):
    if not os.path.exists(path):
        sys.exit(f"[错误] 找不到 AK 文件：{path}\n"
                 f"请创建该文件：第 1 行 SecretId，第 2 行 SecretKey，第 3 行（可选）地域")
    with open(path, encoding="utf-8") as f:
        lines = [ln.strip() for ln in f if ln.strip() and not ln.strip().startswith("#")]
    if len(lines) < 2:
        sys.exit("[错误] AK 文件至少需要 2 行（SecretId / SecretKey）")
    return lines[0], lines[1], (lines[2] if len(lines) > 2 else None)


def make_client(secret_id, secret_key, region):
    return cvm_client.CvmClient(credential.Credential(secret_id, secret_key), region)


def list_regions(client):
    resp = client.DescribeRegions(models.DescribeRegionsRequest())
    data = json.loads(resp.to_json_string())
    for r in data.get("RegionSet", []):
        print(f'{r.get("Region", ""):22s} {r.get("RegionName", "")}')


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("region", nargs="?", default=None)
    ap.add_argument("--regions", action="store_true")
    ap.add_argument("--min-cpu", type=int, default=8)
    ap.add_argument("--max-mem", type=float, default=128.0)
    args = ap.parse_args()

    sid, skey, default_region = load_ak(AK_FILE)

    if args.regions:
        list_regions(make_client(sid, skey, "ap-guangzhou"))
        return

    region = args.region or default_region
    if not region:
        sys.exit("[错误] 未指定地域。请用参数传入，或在 AK 文件第 3 行写默认地域")

    client = make_client(sid, skey, region)
    req = models.DescribeZoneInstanceConfigInfosRequest()
    req.Filters = [models.Filter(name="instance-charge-type", values=["POSTPAID_BY_HOUR"])]
    resp = client.DescribeZoneInstanceConfigInfos(req)
    data = json.loads(resp.to_json_string())

    rows = []
    for q in data.get("InstanceTypeQuotaSet", []):
        cpu = int(q.get("Cpu") or 0)
        mem = float(q.get("Memory") or 0)
        if cpu < args.min_cpu or mem > args.max_mem:
            continue
        status = q.get("Status", "")
        price = q.get("Price") or {}
        unit = price.get("UnitPrice")
        rows.append((cpu, mem, q.get("InstanceType", ""), q.get("Zone", ""), status, unit))

    print(f"[查询] 地域 {region} 按量付费规格（vCPU>={args.min_cpu}）")
    if not rows:
        print("  没有符合条件的规格，建议换地域 / 降低 vCPU 门槛")
        return

    rows.sort(key=lambda r: (r[0], r[1], r[2]))
    print(f'{"实例规格":26s} {"vCPU":>5} {"内存GiB":>8} {"状态":>8} {"元/时":>9}  可用区')
    print("-" * 84)
    sell = 0
    for cpu, mem, itype, zone, status, unit in rows:
        if status == "SELL":
            sell += 1
        p = f"{float(unit):.3f}" if unit is not None else "?"
        print(f'{itype:26s} {cpu:5d} {mem:8.0f} {status:>8} {p:>9}  {zone}')

    print(f"\n共 {len(rows)} 个规格，其中可售(SELL) {sell} 个。"
          f"租前确认：按量计费 + Ubuntu 24.04 + 开 22 端口 + 关机不退还实例。")


if __name__ == "__main__":
    main()
