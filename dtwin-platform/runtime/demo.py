# -*- coding: utf-8 -*-
"""答辩演示：为三个算法准备同场景预置任务，并给出演示动线。"""
from __future__ import annotations

import threading
from typing import Any, Dict, List, Optional

from .jobs import STORE

DEMO_ALGORITHMS = ("tube_mpc", "pid_cruise", "rule_follow")
DEMO_STEPS = 1200
DEMO_OPTIONS = {
    "steps": DEMO_STEPS,
    "coupler_model": "linear",
    "brake_supervisor": "atp",
    "demo": True,
}

_lock = threading.Lock()


def _demo_jobs() -> Dict[str, Dict[str, Any]]:
    """每个算法取最新的一个演示任务。"""
    rows: Dict[str, Dict[str, Any]] = {}
    for job in STORE.list():
        if not (job.get("options") or {}).get("demo"):
            continue
        prev = rows.get(job["algorithm"])
        if prev is None or job["created_at"] > prev["created_at"]:
            rows[job["algorithm"]] = job
    return rows


def demo_presets() -> Dict[str, Optional[str]]:
    jobs = _demo_jobs()
    return {alg: (jobs.get(alg) or {}).get("id") for alg in DEMO_ALGORITHMS}


def ensure_demo_presets() -> None:
    """缺哪个算法的演示任务就补一个，已有则跳过。"""
    with _lock:
        jobs = _demo_jobs()
        for alg in DEMO_ALGORITHMS:
            job = jobs.get(alg)
            if job and job["status"] in ("queued", "running", "completed"):
                continue
            try:
                STORE.submit(alg, "offline_replay", dict(DEMO_OPTIONS))
            except (KeyError, RuntimeError, ValueError):
                pass


def demo_script() -> Dict[str, Any]:
    jobs = _demo_jobs()
    presets = {alg: jobs.get(alg) for alg in DEMO_ALGORITHMS}
    ready = all(p and p["status"] == "completed" for p in presets.values())
    tube = presets.get("tube_mpc") or {}

    steps: List[Dict[str, Any]] = [
        {"view": "home", "label": "平台概览", "seconds": 7,
         "note": "朔黄线真实区段 49.527 km，三列车群组，每列 1 台 HXD1 牵引 54 辆 C80"},
        {"view": "algorithms", "label": "算法管理", "seconds": 9,
         "note": "Tube-MPC、PID 速度巡航、规则跟随；算法只拿到观测，安全约束由保护层钳制"},
        {"view": "runtime", "label": "闭环运行", "seconds": 12, "run_id": tube.get("id"),
         "note": "右侧是本次运行的速度曲线：头车、跟随车、尾车与 ATP 监督限速，算法输出经保护层钳制"},
        {"view": "analysis", "label": "指标对比", "seconds": 10,
         "note": "同一归档轨迹、同一 1200 步：车辆指标一致，差异在算法指令与求解耗时"},
        {"view": "records", "label": "结果归档", "seconds": 7,
         "note": "仿真 CSV、指标 JSON 与摘要落盘，可下载复核"},
    ]
    return {
        "ready": ready,
        "steps": steps,
        "presets": {alg: (job or {}).get("id") for alg, job in presets.items()},
        "status": {alg: (job or {}).get("status") for alg, job in presets.items()},
    }
