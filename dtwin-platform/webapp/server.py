# -*- coding: utf-8 -*-
"""平台 Web 服务（Python 标准库实现，无第三方依赖）。

接口：
  GET  /                      单页前端
  GET  /api/overview          总览：功能域 / 算法 / 执行器 / 任务统计
  GET  /api/algorithms        算法清单（算法管理域）
  GET  /api/backends          执行器清单（仿真运行域）
  GET  /api/runs              任务列表
  POST /api/runs              发送算法到仿真运行（{algorithm, backend, options}
  GET  /api/runs/<id>         任务详情（含指标与曲线）
  GET  /api/records           运行记录（CSV / 指标 JSON）
  GET  /api/analysis          分析服务：已完成任务的横向对比
  GET  /api/demo              演示模式：预置任务状态与演示动线
  GET  /files?path=<rel>      下载运行记录
"""
from __future__ import annotations

import json
import mimetypes
import os
import posixpath
import sys
import threading
import time
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any, Dict, List
from urllib.parse import parse_qs, urlparse

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

import algorithms                                            # noqa: F401,E402  注册插件
from dtwin.registry import describe_algorithms               # noqa: E402
from runtime.backends import describe_backends              # noqa: E402
from runtime.demo import demo_script, ensure_demo_presets    # noqa: E402
from runtime.jobs import STORE, platform_overview            # noqa: E402

STATIC_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "static")
RECORD_DIRS = ("outputs_platform", "outputs_shuohuang")
DOWNLOADABLE = {".csv", ".json", ".txt", ".md"}


# ----------------------------------------------------------------------
# 业务处理
# ----------------------------------------------------------------------
def api_records() -> List[Dict[str, Any]]:
    items: List[Dict[str, Any]] = []
    for sub in RECORD_DIRS:
        base = os.path.join(_ROOT, sub)
        if not os.path.isdir(base):
            continue
        for name in sorted(os.listdir(base)):
            path = os.path.join(base, name)
            if not os.path.isfile(path) or name.startswith("."):
                continue
            ext = os.path.splitext(name)[1].lower()
            if ext not in DOWNLOADABLE:
                continue
            rel = f"{sub}/{name}"
            items.append({
                "name": name,
                "domain": sub,
                "kind": ext.lstrip(".").upper(),
                "size_kb": round(os.path.getsize(path) / 1024.0, 1),
                "modified": time.strftime("%Y-%m-%d %H:%M",
                                          time.localtime(os.path.getmtime(path)),
                                          ),
                "downloadable": True,
                "url": f"/files?path={rel}",
            })
    items.sort(key=lambda r: r["modified"], reverse=True)
    return items


def api_analysis() -> Dict[str, Any]:
    done = [j for j in STORE.list() if j["status"] == "completed"]
    latest: Dict[str, Dict[str, Any]] = {}
    for job in done:                     # STORE.list() 已按创建时间倒序
        latest.setdefault(job["algorithm"], job)
    rows: List[Dict[str, Any]] = []
    for job in latest.values():
        m = job.get("metrics", {})
        rows.append({
            "id": job["id"],
            "algorithm": job["algorithm"],
            "algorithm_name": job["algorithm_name"],
            "backend": job["backend_label"],
            "steps": m.get("steps"),
            "t_end_s": m.get("t_end_s"),
            "dist_km": m.get("dist_km"),
            "solve_ms_mean": m.get("solve_ms_mean"),
            "track_err_avg_kmh": m.get("track_err_avg_kmh"),
            "overspeed_max_kmh": m.get("overspeed_max_kmh"),
            "fc_peak_kN": m.get("fc_peak_kN"),
            "finish": job.get("finished_at"),
        })
    return {
        "note": ("每个算法只取最近一次已完成任务，按运行指标横向比较。"
                 "分析只读数据记录域，不参与控制回路。"),
        "count": len(rows),
        "rows": rows,
    }


# ----------------------------------------------------------------------
# HTTP
# ----------------------------------------------------------------------
class Handler(BaseHTTPRequestHandler):
    server_version = "DTwinPlatform/0.3"

    def log_message(self, fmt: str, *args: Any) -> None:    # 静默访问日志
        pass

    # -- 工具 ----------------------------------------------------------
    def _json(self, payload: Any, status: int = HTTPStatus.OK) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def _error(self, message: str, status: int = HTTPStatus.BAD_REQUEST) -> None:
        self._json({"ok": False, "error": message}, status)

    def _file(self, path: str, download: bool = False) -> None:
        if not os.path.isfile(path):
            self._error("文件不存在", HTTPStatus.NOT_FOUND)
            return
        ctype = mimetypes.guess_type(path)[0] or "application/octet-stream"
        with open(path, "rb") as f:
            body = f.read()
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", f"{ctype}; charset=utf-8"
                         if ctype.startswith("text/") else ctype)
        self.send_header("Content-Length", str(len(body)))
        if download:
            self.send_header("Content-Disposition",
                             f'attachment; filename="{os.path.basename(path)}"')
        self.end_headers()
        self.wfile.write(body)

    def _body(self) -> Dict[str, Any]:
        length = int(self.headers.get("Content-Length") or 0)
        if not length:
            return {}
        raw = self.rfile.read(length)
        try:
            return json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            return {}

    # -- 路由 ----------------------------------------------------------
    def do_GET(self) -> None:                                # noqa: N802
        parsed = urlparse(self.path)
        route = parsed.path
        query = parse_qs(parsed.query)

        if route in ("/", "/index.html"):
            self._file(os.path.join(STATIC_DIR, "index.html"))
            return
        if route.startswith("/static/"):
            rel = posixpath.normpath(route[len("/static/"):])
            target = os.path.join(STATIC_DIR, rel)
            if os.path.commonpath([os.path.abspath(target), STATIC_DIR]) != STATIC_DIR:
                self._error("非法路径", HTTPStatus.FORBIDDEN)
                return
            self._file(target)
            return

        if route == "/api/overview":
            self._json(platform_overview())
        elif route == "/api/algorithms":
            self._json({"algorithms": describe_algorithms()})
        elif route == "/api/backends":
            self._json({"backends": describe_backends()})
        elif route == "/api/runs":
            self._json({"runs": STORE.list()})
        elif route.startswith("/api/runs/"):
            job_id = route[len("/api/runs/"):]
            try:
                self._json(STORE.public(job_id))
            except KeyError:
                self._error("任务不存在", HTTPStatus.NOT_FOUND)
        elif route == "/api/records":
            self._json({"records": api_records()})
        elif route == "/api/analysis":
            self._json(api_analysis())
        elif route == "/api/demo":
            ensure_demo_presets()
            self._json(demo_script())
        elif route == "/files":
            rel = (query.get("path") or [""])[0].replace("\\", "/")
            target = os.path.abspath(os.path.join(_ROOT, rel))
            if os.path.commonpath([target, _ROOT]) != _ROOT:
                self._error("非法路径", HTTPStatus.FORBIDDEN)
                return
            if os.path.splitext(target)[1].lower() not in DOWNLOADABLE:
                self._error("该类型不支持下载", HTTPStatus.FORBIDDEN)
                return
            self._file(target, download=True)
        else:
            self._error("接口不存在", HTTPStatus.NOT_FOUND)

    def do_POST(self) -> None:                               # noqa: N802
        parsed = urlparse(self.path)
        if parsed.path != "/api/runs":
            self._error("接口不存在", HTTPStatus.NOT_FOUND)
            return
        body = self._body()
        algorithm = str(body.get("algorithm") or "").strip()
        backend = str(body.get("backend") or "").strip()
        options = body.get("options") or {}
        if not algorithm or not backend:
            self._error("缺少 algorithm 或 backend")
            return
        try:
            job = STORE.submit(algorithm, backend, options)
        except KeyError as exc:
            self._error(str(exc), HTTPStatus.NOT_FOUND)
            return
        except RuntimeError as exc:
            self._error(str(exc), HTTPStatus.CONFLICT)
            return
        except ValueError as exc:
            self._error(str(exc), HTTPStatus.BAD_REQUEST)
            return
        self._json({"ok": True, "job": job}, HTTPStatus.CREATED)


def serve(host: str = "127.0.0.1", port: int = 8765) -> None:
    threading.Thread(target=ensure_demo_presets, name="demo-presets",
                     daemon=True).start()
    httpd = ThreadingHTTPServer((host, port), Handler)
    print(f"数字孪生平台已启动: http://{host}:{port}")
    print(f"  可用执行器: {[b['key'] for b in describe_backends() if b['available']]}")
    print(f"  已注册算法: {[a['key'] for a in describe_algorithms()]}")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\n已停止。")
    finally:
        httpd.server_close()


if __name__ == "__main__":
    serve()
