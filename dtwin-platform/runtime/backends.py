# -*- coding: utf-8 -*-
"""仿真运行执行器：可替换的运行时后端（当前提供离线回放占位）。

平台与执行器之间只传 RunConfig + 算法名 + 回调，执行器内部怎么跑
（离线回放 / 联合仿真 / 硬件在环）对上层透明。新增执行器只需实现
RunBackend.execute() 并登记到 BACKENDS。
"""
from __future__ import annotations

import os
import sys
import traceback
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_LIVE_SIM_DIR = r"d:\Z\first station\multi-agent-main\traffic_rl_project"
LIVE_SIM_ENV_FLAG = "DTWIN_ENABLE_LIVE_SIM"

# 真实线路数据（限速表 / 坡度剖面）随第三方仿真器分发，回放也需要它
for _p in (_ROOT, _LIVE_SIM_DIR):
    if _p not in sys.path:
        sys.path.insert(0, _p)

ProgressFn = Callable[[float, str], None]


@dataclass
class RunOutcome:
    ok: bool
    message: str
    metrics: Dict[str, Any] = field(default_factory=dict)
    series: Dict[str, Any] = field(default_factory=dict)
    log: List[str] = field(default_factory=list)
    artifacts: List[str] = field(default_factory=list)


class RunBackend:
    key = "base"
    label = "基类"
    description = ""
    kind = "placeholder"       # placeholder / live

    @property
    def available(self) -> bool:
        return True

    @property
    def note(self) -> str:
        return ""

    def execute(self, algorithm: str, cfg, options: Dict[str, Any],
                progress: ProgressFn) -> RunOutcome:
        raise NotImplementedError


# ----------------------------------------------------------------------
# 离线回放执行器（仿真环境未接入时的占位）
# ----------------------------------------------------------------------
class OfflineReplayBackend(RunBackend):
    key = "offline_replay"
    label = "离线回放执行器"
    kind = "placeholder"
    description = ("在归档基线轨迹上回放观测，逐步调用所选算法并记录输出。"
                   "不做物理推进，用来验证算法接入、对比指令。")

    @property
    def note(self) -> str:
        return "联合仿真环境还没接上，先用离线回放跑算法；接上后换成 NeTrainSim 联合仿真。"

    def execute(self, algorithm: str, cfg, options: Dict[str, Any],
                progress: ProgressFn) -> RunOutcome:
        import time

        import numpy as np

        from dtwin.reference import ReferenceGenerator
        from dtwin.registry import get_algorithm

        from .replay import TRAIN_LENGTH_M, load_replay, states_at

        from dtwin.contracts import Observation
        from src.train_dynamics.grade_profile import SHUOZHOU_REAL_SPEED_LIMIT

        data = load_replay(options.get("dataset"))
        n_total = data.n_steps
        steps = int(options.get("steps") or n_total)
        steps = max(1, min(steps, n_total))

        algo = get_algorithm(algorithm)
        algo.reset(cfg)
        ref_gen = ReferenceGenerator(cfg, SHUOZHOU_REAL_SPEED_LIMIT.limit_at,
                                     TRAIN_LENGTH_M)
        ref_gen.reset(states_at(data, 0))

        u_arr = np.zeros((steps, cfg.n_trains))
        v_ref_arr = np.zeros((steps, cfg.n_trains))
        solve_ms: List[float] = []
        log: List[str] = [
            f"数据集: {os.path.basename(data.path)}（{n_total} 步归档记录）",
            f"回放步数: {steps} | 控制周期 {cfg.dt_mpc}s | 算法 {algorithm}",
        ]
        progress(0.0, "装载回放数据")
        t0 = time.time()
        for k in range(steps):
            states = states_at(data, k)
            refs = ref_gen.compute(states)
            for i in range(cfg.n_trains):
                rf = refs[i]
                st = states[i]
                obs = Observation(
                    train_id=i,
                    t=k * cfg.dt_mpc,
                    s_head=st.s_head,
                    v_head=st.v_head,
                    v_group=st.v_group,
                    intra_dev=rf.intra_dev,
                    v_ref=rf.v_ref,
                    a_ref=rf.a_ref,
                    v_sup=rf.v_sup,
                    v_allow=rf.v_allow,
                    d2=rf.d2,
                    gap_lead=st.gap_lead,
                    v_lead=st.v_lead,
                    is_leader=(i == 0),
                )
                ts = time.time()
                act = algo.act(obs)
                solve_ms.append((time.time() - ts) * 1000.0)
                u_arr[k, i] = float(act.u_hat)
                v_ref_arr[k, i] = float(rf.v_ref)
            if k % 30 == 0 or k == steps - 1:
                progress((k + 1) / steps, f"回放执行 {k + 1}/{steps} 步")
        wall = time.time() - t0

        v_head = np.array(data.v_head[:steps])
        v_sup = np.array(data.v_sup[:steps])
        fc = np.array(data.fc_peak[:steps])
        s_head = np.array(data.s_head[:steps])
        t_rec = np.array(data.t[:steps])

        track_err = np.abs(v_head - v_ref_arr) * 3.6
        over = np.clip(v_head - v_sup, 0.0, None) * 3.6
        metrics: Dict[str, Any] = {
            "steps": steps,
            "t_end_s": round(float(t_rec[-1]), 1),
            "dist_km": round(float((s_head[-1, 0] - s_head[0, 0]) / 1000.0), 2),
            "solve_ms_mean": round(float(np.mean(solve_ms)), 3),
            "solve_ms_p95": round(float(np.percentile(solve_ms, 95)), 3),
            "track_err_max_kmh": [round(float(x), 2) for x in track_err.max(axis=0)],
            "track_err_avg_kmh": round(float(track_err.max(axis=0).mean()), 2),
            "u_rms": [round(float(x), 4) for x in np.sqrt((u_arr ** 2).mean(axis=0))],
            "u_peak": [round(float(x), 4) for x in np.abs(u_arr).max(axis=0)],
            "overspeed_max_kmh": round(float(over.max()), 2),
            "overspeed_ratio": round(float((over > 0.1).mean()), 4),
            "fc_peak_kN": [round(float(x), 0) for x in fc.max(axis=0)],
            "gap_min_m": round(float((s_head[:, :-1] - s_head[:, 1:]).min()), 0),
            "wall_s": round(float(wall), 2),
            "engine": "offline_replay",
            "engine_label": self.label,
        }

        step_idx = np.arange(steps)
        stride = max(1, steps // 400)
        pick = step_idx[::stride]
        series: Dict[str, Any] = {
            "t": [round(float(t_rec[i]), 1) for i in pick],
            "v_lead": [round(float(v_head[i, 0] * 3.6), 2) for i in pick],
            "v_follow": [round(float(v_head[i, 1] * 3.6), 2) for i in pick],
            "v_tail": [round(float(v_head[i, 2] * 3.6), 2) for i in pick],
            "v_ref": [round(float(v_ref_arr[i, 0] * 3.6), 2) for i in pick],
            "v_sup": [round(float(v_sup[i, 0] * 3.6), 2) for i in pick],
            "u": [round(float(u_arr[i, 0]), 4) for i in pick],
            "fc": [round(float(fc[i, 0]), 1) for i in pick],
        }
        log.append(f"回放完成：壁钟 {wall:.1f}s，平均单步求解 {metrics['solve_ms_mean']}ms")
        return RunOutcome(ok=True, message="离线回放完成，未做物理推进",
                          metrics=metrics, series=series, log=log)


# ----------------------------------------------------------------------
# NeTrainSim 联合仿真执行器（环境未接入时不可用）
# ----------------------------------------------------------------------
class NeTrainSimBackend(RunBackend):
    key = "netrainsim"
    label = "NeTrainSim 联合仿真"
    kind = "live"
    description = ("调用第三方 TrainDynamics 物理层完成真实推进，"
                   "算法输出经平台保护层钳制后下发执行器。")

    @property
    def available(self) -> bool:
        if os.environ.get(LIVE_SIM_ENV_FLAG) != "1":
            return False
        return os.path.isdir(_LIVE_SIM_DIR)

    @property
    def note(self) -> str:
        if os.environ.get(LIVE_SIM_ENV_FLAG) != "1":
            return f"联合仿真环境还没接上（设置环境变量 {LIVE_SIM_ENV_FLAG}=1 并配置仿真器路径后启用）。"
        if not os.path.isdir(_LIVE_SIM_DIR):
            return f"未找到仿真器目录: {_LIVE_SIM_DIR}"
        return "已就绪。"

    def execute(self, algorithm: str, cfg, options: Dict[str, Any],
                progress: ProgressFn) -> RunOutcome:
        import adapters                                              # noqa: F401
        import algorithms                                             # noqa: F401
        from adapters.netrainsim import NeTrainSimPlant
        from dtwin.engine import SimulationEngine
        from dtwin.protections import build_protections
        from dtwin.recorder import write_csv, write_summary
        from dtwin.reference import ReferenceGenerator
        from dtwin.registry import get_algorithm

        from src.train_dynamics.grade_profile import SHUOZHOU_REAL_SPEED_LIMIT

        steps = int(options.get("steps") or 3600)
        progress(0.02, "构建物理对象与保护层")
        plant = NeTrainSimPlant(cfg)
        algo = get_algorithm(algorithm)
        reference = ReferenceGenerator(cfg, SHUOZHOU_REAL_SPEED_LIMIT.limit_at,
                                       plant.train_length)
        protections = build_protections(cfg)
        engine = SimulationEngine(cfg, plant, algo, reference, protections,
                                  max_steps=steps, verbose=False)
        progress(0.1, "联合仿真推进中")
        result = engine.run()
        progress(0.95, "写入运行记录")
        tag = f"{cfg.name}_{cfg.coupler_model}_{cfg.protection['brake_supervisor']}_web"
        out_dir = os.path.join(_ROOT, "outputs_platform")
        csv_path = os.path.join(out_dir, f"sim_{tag}.csv")
        txt_path = os.path.join(out_dir, f"summary_{tag}.txt")
        write_csv(result.log, csv_path)
        write_summary(result.summary, txt_path)
        m = {k: (v.tolist() if hasattr(v, "tolist") else v)
             for k, v in result.summary.items()}
        m["engine"] = "netrainsim"
        m["engine_label"] = self.label
        n_run = len(result.log["t"])
        stride = max(1, n_run // 400)
        pick = slice(None, None, stride)
        series = {
            "t": [round(float(x), 1) for x in result.log["t"][:, 0][pick]],
            "v_lead": [round(float(x * 3.6), 2) for x in result.log["v_head"][:, 0][pick]],
            "v_follow": [round(float(x * 3.6), 2) for x in result.log["v_head"][:, 1][pick]],
            "v_tail": [round(float(x * 3.6), 2) for x in result.log["v_head"][:, 2][pick]],
            "v_ref": [round(float(x * 3.6), 2) for x in result.log["v_ref0"][:, 0][pick]],
            "v_sup": [round(float(x * 3.6), 2) for x in result.log["v_sup"][:, 0][pick]],
            "u": [round(float(x), 4) for x in result.log["uhat"][:, 0][pick]],
            "fc": [round(float(x), 1) for x in result.log["fc_peak"][:, 0][pick]],
        }
        progress(1.0, "完成")
        return RunOutcome(ok=True, message="联合仿真完成", metrics=m, series=series,
                          artifacts=[csv_path, txt_path])


BACKENDS: Dict[str, RunBackend] = {b.key: b for b in (OfflineReplayBackend(),
                                                     NeTrainSimBackend())}


def get_backend(key: str) -> RunBackend:
    if key not in BACKENDS:
        raise KeyError(f"未知执行器: {key}，可用: {sorted(BACKENDS)}")
    return BACKENDS[key]


def describe_backends() -> List[Dict[str, Any]]:
    return [{
        "key": b.key,
        "label": b.label,
        "kind": b.kind,
        "description": b.description,
        "available": b.available,
        "note": b.note,
    } for b in BACKENDS.values()]


def describe_error(exc: BaseException) -> str:
    return "".join(traceback.format_exception_only(type(exc), exc)).strip()
