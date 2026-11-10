"""训练进程心跳（存活可视化）。

【动机 2026-11-08】首次 200 集阶段门在第 1 集 checkpoint 落盘后被外部连根杀掉，
**静默 40 分钟无人发现**——日志停在最后一行、无 traceback、计划任务只剩一个
`Last Result=0x8007042B`，事后只能靠"结果目录只有 1 行 CSV"反推死亡。
仅靠 schtasks 的 Last Result 不足以"一眼看出活着还是死了"。

【机制】主进程起一个 daemon 线程，每 `interval_s` 秒把当前阶段/集号/已用时写进
`<results_dir>/heartbeat.txt`（原子替换，避免半写）。外部看护进程（Windows 侧，
见 `scripts/watchdog_heartbeat.ps1`）只读这个文件：
  - mtime 新鲜 → 活着；
  - mtime 超过阈值 且 无 exit_code.txt → 判死并写明确标记。

【为什么不用"进程自己写死亡标记"】进程被连根杀掉时没有任何机会执行 finally，
所以死亡必须由**进程外**的看护者判定。本模块只负责"活着时留下时间戳"。
"""
import json
import os
import threading
import time
from datetime import datetime
from pathlib import Path


class Heartbeat:
    """训练主进程的心跳写入器（daemon 线程，不影响训练逻辑）。"""

    def __init__(self, results_dir, interval_s: float = 60.0, tag: str = ''):
        self.dir = Path(results_dir)
        self.interval = max(5.0, float(interval_s))
        self.tag = tag
        self.path = self.dir / 'heartbeat.txt'
        self.json_path = self.dir / 'heartbeat.json'
        self._state = {'phase': 'init', 'episode': 0, 'total': 0,
                       'elapsed_s': 0.0, 'note': ''}
        self._lock = threading.Lock()
        self._stop = threading.Event()
        self._thread = None
        self._t0 = time.time()

    # ------------------------------------------------------------------
    def start(self, phase: str = 'start', **kw):
        self.update(phase=phase, **kw)
        self._thread = threading.Thread(target=self._loop, daemon=True,
                                        name='heartbeat')
        self._thread.start()
        return self

    def update(self, **kw):
        with self._lock:
            self._state.update({k: v for k, v in kw.items() if v is not None})
            self._state['elapsed_s'] = round(time.time() - self._t0, 1)
        self._write()

    def stop(self, phase: str = 'finished', **kw):
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=5)
        self.update(phase=phase, **kw)

    # ------------------------------------------------------------------
    def _loop(self):
        while not self._stop.wait(self.interval):
            self.update()

    def _write(self):
        with self._lock:
            body = dict(self._state)
        body['ts'] = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        body['tag'] = self.tag
        try:
            self.dir.mkdir(parents=True, exist_ok=True)
            tmp = self.path.with_suffix('.tmp')
            tmp.write_text(
                f"{body['ts']} | phase={body['phase']} | "
                f"ep={body['episode']}/{body['total']} | "
                f"elapsed={body['elapsed_s']:.0f}s | {body['note']}\n",
                encoding='utf-8')
            os.replace(tmp, self.path)          # 原子替换：看护进程不会读到半截文件
            self.json_path.write_text(
                json.dumps(body, ensure_ascii=False), encoding='utf-8')
        except Exception:
            # 心跳失败绝不影响训练（只影响可观测性）
            pass
