# -*- coding: utf-8 -*-
"""运行任务调度：算法管理"发送"-> 选执行器 -> 后台执行 -> 结果归档。

任务在内存中维护，同时逐条落盘到 outputs_platform/jobs/<job_id>.json，
既不依赖数据库，重启后也能读到历史运行。
"""
from __future__ import annotations

import copy
import json
import os
import threading
import time
import uuid
from dataclasses import asdict
from typing import Any, Dict, List, Optional

from dtwin.contracts import RunConfig
from dtwin.registry import describe_algorithms, get_algorithm

from .backends import RunOutcome, describe_error, describe_backends, get_backend

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
JOBS_DIR = os.path.join(_ROOT, "outputs_platform", "jobs")

_STATUS_TEXT = {
    "queued": "排队中",
    "running": "运行中",
    "completed": "已完成",
    "failed": "失败",
}


def build_run_config(options: Dict[str, Any]) -> RunConfig:
    """默认 RunConfig + 运行请求里的少量可调项。"""
    cfg = RunConfig()
    coupler = options.get("coupler_model")
    if coupler in ("mt2", "linear", "zero"):
        cfg.coupler_model = coupler
    brake = options.get("brake_supervisor")
    if brake in ("atp", "cyclic"):
        cfg = cfg.with_brake_mode(brake)
    for key in ("s_start", "s_end"):
        if options.get(key) is not None:
            setattr(cfg, key, float(options[key]))
    return cfg


class JobStore:
    def __init__(self, jobs_dir: str = JOBS_DIR):
        self.dir = jobs_dir
        os.makedirs(self.dir, exist_ok=True)
        self._lock = threading.Lock()
        self._jobs: Dict[str, Dict[str, Any]] = {}
        self._load_existing()

    # ------------------------------------------------------------------
    def _load_existing(self) -> None:
        for name in sorted(os.listdir(self.dir)):
            if not name.endswith(".json"):
                continue
            try:
                with open(os.path.join(self.dir, name), "r", encoding="utf-8") as f:
                    job = json.load(f)
            except (OSError, json.JSONDecodeError):
                continue
            if job.get("status") == "running":
                job["status"] = "failed"
                job["stage"] = "服务重启，任务已中断"
                job["message"] = "服务重启导致任务中断"
            self._jobs[job["id"]] = job

    def _persist(self, job: Dict[str, Any]) -> None:
        path = os.path.join(self.dir, f"{job['id']}.json")
        with open(path, "w", encoding="utf-8") as f:
            json.dump(job, f, ensure_ascii=False, indent=2)

    # ------------------------------------------------------------------
    def submit(self, algorithm: str, backend_key: str,
               options: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        options = dict(options or {})
        get_algorithm(algorithm)                        # 未注册则抛 KeyError
        backend = get_backend(backend_key)
        if not backend.available:
            raise RuntimeError(backend.note)

        job_id = f"run-{time.strftime('%Y%m%d-%H%M%S')}-{uuid.uuid4().hex[:4]}"
        cfg = build_run_config(options)
        meta = {m["key"]: m for m in describe_algorithms()}[algorithm]
        job: Dict[str, Any] = {
            "id": job_id,
            "algorithm": algorithm,
            "algorithm_name": meta["display_name"],
            "algorithm_category": meta["category"],
            "backend": backend_key,
            "backend_label": backend.label,
            "status": "queued",
            "status_text": _STATUS_TEXT["queued"],
            "progress": 0.0,
            "stage": "等待执行",
            "message": "",
            "created_at": time.strftime("%Y-%m-%d %H:%M:%S"),
            "started_at": None,
            "finished_at": None,
            "options": options,
            "config": {
                "coupler_model": cfg.coupler_model,
                "brake_supervisor": cfg.protection["brake_supervisor"],
                "s_start": cfg.s_start,
                "s_end": cfg.s_end,
                "dt_mpc": cfg.dt_mpc,
                "n_trains": cfg.n_trains,
            },
            "metrics": {},
            "series": {},
            "log": [],
            "artifacts": [],
        }
        with self._lock:
            self._jobs[job_id] = job
            self._persist(job)
        threading.Thread(target=self._execute, args=(job_id, cfg, backend),
                         name=f"job-{job_id}", daemon=True).start()
        return self.public(job_id)

    # ------------------------------------------------------------------
    def _execute(self, job_id: str, cfg: RunConfig, backend) -> None:
        job = self._jobs[job_id]
        self._update(job_id, status="running", stage="启动执行器",
                     started_at=time.strftime("%Y-%m-%d %H:%M:%S"))
        last = {"progress": -1.0}

        def progress(value: float, stage: str) -> None:
            value = max(0.0, min(1.0, float(value)))
            if value - last["progress"] < 0.01 and stage == job["stage"]:
                return
            last["progress"] = value
            self._update(job_id, progress=value, stage=stage)

        try:
            outcome: RunOutcome = backend.execute(job["algorithm"], cfg,
                                                  job["options"], progress)
        except Exception as exc:                     # noqa: BLE001
            self._update(job_id, status="failed", progress=1.0,
                         stage="执行失败", message=describe_error(exc),
                         finished_at=time.strftime("%Y-%m-%d %H:%M:%S"),
                         log=[f"错误: {describe_error(exc)}"])
            return

        if not outcome.ok:
            self._update(job_id, status="failed", progress=1.0, stage="执行失败",
                         message=outcome.message, metrics=outcome.metrics,
                         series=outcome.series, log=outcome.log,
                         finished_at=time.strftime("%Y-%m-%d %H:%M:%S"))
            return

        self._update(job_id, status="completed", progress=1.0, stage="已完成",
                     message=outcome.message, metrics=outcome.metrics,
                     series=outcome.series, log=outcome.log,
                     artifacts=outcome.artifacts,
                     finished_at=time.strftime("%Y-%m-%d %H:%M:%S"))

    def _update(self, job_id: str, **fields: Any) -> None:
        with self._lock:
            job = self._jobs[job_id]
            job.update(fields)
            if "status" in fields:
                job["status_text"] = _STATUS_TEXT.get(job["status"], job["status"])
            self._persist(job)

    # ------------------------------------------------------------------
    def public(self, job_id: str, detail: bool = True) -> Dict[str, Any]:
        job = self._jobs.get(job_id)
        if job is None:
            raise KeyError(job_id)
        out = copy.deepcopy(job)
        if not detail:
            out.pop("series", None)
            out.pop("log", None)
        return out

    def list(self) -> List[Dict[str, Any]]:
        jobs = sorted(self._jobs.values(), key=lambda j: j["created_at"], reverse=True)
        return [self.public(j["id"], detail=False) for j in jobs]

    def stats(self) -> Dict[str, Any]:
        jobs = list(self._jobs.values())
        done = [j for j in jobs if j["status"] == "completed"]
        return {
            "total": len(jobs),
            "running": sum(1 for j in jobs if j["status"] == "running"),
            "completed": len(done),
            "failed": sum(1 for j in jobs if j["status"] == "failed"),
            "algorithms_used": sorted({j["algorithm"] for j in jobs}),
            "backends_used": sorted({j["backend"] for j in jobs}),
        }


STORE = JobStore()


def platform_overview() -> Dict[str, Any]:
    algorithms = describe_algorithms()
    backends = describe_backends()
    return {
        "platform": "重载列车群组运行数字孪生平台",
        "version": "0.3-skeleton",
        "domains": [
            {"key": "algorithms", "label": "算法管理"},
            {"key": "runtime", "label": "仿真运行"},
            {"key": "records", "label": "数据记录"},
            {"key": "analysis", "label": "分析服务"},
        ],
        "algorithm_count": len(algorithms),
        "algorithms": algorithms,
        "backends": backends,
        "stats": STORE.stats(),
        "defaults": asdict(RunConfig()),
    }
