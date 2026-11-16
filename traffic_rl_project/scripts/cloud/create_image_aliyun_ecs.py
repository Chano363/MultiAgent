"""Aliyun ECS CreateImage: snapshot current instance (env + code) as reusable custom image.

Usage:
    python scripts/cloud/create_image_aliyun_ecs.py --instance i-xxx --name traffic_rl_env_YYYYMMDD [--region cn-heyuan]

Notes:
    - Instance must be Running; snapshot runs online (brief disk IO jitter).
    - This is the SSOT fix for the 2026-11-11 lesson: a fresh instance cost ~48 min
      env-install before first training step because no custom image existed.
      ALWAYS CreateImage before releasing an instance that has a provisioned env.
"""
import argparse
import os
import sys

from aliyunsdkcore.client import AcsClient
from aliyunsdkecs.request.v20140526.CreateImageRequest import CreateImageRequest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from probe_aliyun_ecs import call, load_ak  # noqa: E402
from ak_path import resolve_ak_file  # noqa: E402


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--instance", required=True)
    ap.add_argument("--name", required=True)
    ap.add_argument("--region", default="cn-heyuan")
    ap.add_argument("--desc", default="traffic_rl env snapshot")
    args = ap.parse_args()

    ak_id, ak_secret, _ = load_ak(resolve_ak_file())
    client = AcsClient(ak_id, ak_secret, region_id=args.region)

    res = call(client, "CreateImage", {
        "InstanceId": args.instance,
        "ImageName": args.name,
        "Description": args.desc,
    }, region=args.region)
    image_id = res.get("ImageId", "")
    print(f"[OK] CreateImage accepted: image_id={image_id} name={args.name}")
    print("     (build takes several minutes; check DescribeImages Status=Available before use)")


if __name__ == "__main__":
    main()
