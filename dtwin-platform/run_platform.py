# -*- coding: utf-8 -*-
"""数字孪生平台 CLI 入口（与 Web 端共用同一套执行器与任务调度）。

用法示例：
    python run_platform.py --algorithm tube_mpc --steps 1200
    python run_platform.py --algorithm pid_cruise --backend offline_replay

说明：netrainsim 执行器需要仿真运行环境接入（DTWIN_ENABLE_LIVE_SIM=1），
未接入时请使用默认的离线回放执行器。
"""
from __future__ import annotations

import argparse
import os
import sys
import time

_ROOT = os.path.dirname(os.path.abspath(__file__))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

import algorithms                                                # noqa: F401,E402
from dtwin.registry import describe_algorithms                   # noqa: E402
from runtime.backends import describe_backends, get_backend      # noqa: E402
from runtime.jobs import STORE                                   # noqa: E402


def main() -> None:
    ap = argparse.ArgumentParser(description="数字孪生仿真平台（骨架 CLI）")
    ap.add_argument("--algorithm", default="tube_mpc")
    ap.add_argument("--backend", default="offline_replay")
    ap.add_argument("--coupler", default="linear", choices=["mt2", "linear", "zero"])
    ap.add_argument("--brake", default="atp", choices=["atp", "cyclic"])
    ap.add_argument("--steps", type=int, default=1200)
    ap.add_argument("--s0", type=float, default=None, help="头车初始里程 m")
    ap.add_argument("--s-end", dest="s_end", type=float, default=None, help="头车终止里程 m")
    args = ap.parse_args()

    backend = get_backend(args.backend)
    if not backend.available:
        print(f"执行器不可用：{backend.note}")
        print(f"可用算法: {[a['key'] for a in describe_algorithms()]}")
        print(f"执行器: {[(b['key'], b['available']) for b in describe_backends()]}")
        return

    options = {"steps": args.steps, "coupler_model": args.coupler,
               "brake_supervisor": args.brake}
    if args.s0 is not None:
        options["s_start"] = args.s0
    if args.s_end is not None:
        options["s_end"] = args.s_end

    job = STORE.submit(args.algorithm, args.backend, options)
    print(f"[{job['id']}] {job['algorithm_name']} -> {job['backend_label']} 已提交")
    last = ""
    while True:
        cur = STORE.public(job["id"])
        line = f"  {int(cur['progress'] * 100):3d}% {cur['stage']}"
        if line != last:
            print(line, flush=True)
            last = line
        if cur["status"] in ("completed", "failed"):
            break
        time.sleep(0.5)

    m = cur.get("metrics") or {}
    print(f"\n状态: {cur['status_text']} | {cur['message']}")
    if m:
        print(f"  步数 {m.get('steps')} | 时长 {m.get('t_end_s')}s | 里程 {m.get('dist_km')}km")
        print(f"  平均求解 {m.get('solve_ms_mean')}ms | 跟踪误差均值 {m.get('track_err_avg_kmh')}km/h | "
              f"最大超速 {m.get('overspeed_max_kmh')}km/h")
        print(f"  车钩力峰值 {m.get('fc_peak_kN')} kN | 最小头车间距 {m.get('gap_min_m')} m")
    print(f"  任务归档: outputs_platform/jobs/{job['id']}.json")


if __name__ == "__main__":
    main()
