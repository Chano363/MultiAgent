# -*- coding: utf-8 -*-
"""平台 Web 入口：启动数字孪生平台前端与 JSON 接口服务。

用法：
    python run_web.py --port 8765
"""
from __future__ import annotations

import argparse
import os
import sys

_ROOT = os.path.dirname(os.path.abspath(__file__))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from webapp.server import serve  # noqa: E402


def main() -> None:
    ap = argparse.ArgumentParser(description="重载虚拟编组数字孪生平台 Web 服务")
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=8765)
    args = ap.parse_args()
    serve(args.host, args.port)


if __name__ == "__main__":
    main()
