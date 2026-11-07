# -*- coding: utf-8 -*-
"""仿真引擎：把 运行配置 -> 物理对象 -> 参考层 -> 算法 -> 保护层 串成一次 Episode。

每步执行顺序（与 shuohuang_sim.py 完全一致，保证行为可复现）：
    量测 -> 参考/包络 -> 算法 act -> 保护层钳制 -> 记录(步前) -> 物理 ZOH 推进
"""
from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any, Dict, List, Sequence

import numpy as np

from .contracts import (Action, ControlAlgorithm, Observation, PlantAdapter,
                        Protection, RunConfig, Reference, ActuatorReport)


KEYS = ["t", "s_head", "v_head", "v_ga", "thr", "ed", "b", "uhat",
        "fc_peak", "v_sup", "atp", "s_ref0", "v_ref0"]


@dataclass
class EpisodeResult:
    log: Dict[str, np.ndarray]
    summary: Dict[str, Any]


class SimulationEngine:
    def __init__(self, cfg: RunConfig, plant: PlantAdapter,
                 algorithm: ControlAlgorithm, reference: Any,
                 protections: Sequence[Protection], max_steps: int = 3600,
                 verbose: bool = True, abort_speed_kmh: float = 110.0):
        self.cfg = cfg
        self.plant = plant
        self.algorithm = algorithm
        self.reference = reference
        self.protections = list(protections)
        self.max_steps = int(max_steps)
        self.verbose = verbose
        self.abort_speed_kmh = float(abort_speed_kmh)

    # ------------------------------------------------------------------
    def _make_obs(self, k: int, i: int, st, rf: Reference) -> Observation:
        return Observation(
            train_id=i,
            t=k * self.cfg.dt_mpc,
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

    # ------------------------------------------------------------------
    def run(self) -> EpisodeResult:
        cfg = self.cfg
        states = self.plant.reset(self.reference.initial_speed())
        self.reference.reset(states)
        self.algorithm.reset(cfg)
        for p in self.protections:
            p.reset()

        log: Dict[str, List[Any]] = {k: [] for k in KEYS}
        solve_ms: List[float] = []
        t0 = time.time()
        n = 0
        for k in range(self.max_steps):
            states = self.plant.observe()
            refs = self.reference.compute(states)
            row: Dict[str, List[float]] = {key: [] for key in KEYS}
            commands: List[Action] = []
            for i, (st, rf) in enumerate(zip(states, refs)):
                obs = self._make_obs(k, i, st, rf)
                ts = time.time()
                action = self.algorithm.act(obs)
                solve_ms.append((time.time() - ts) * 1000.0)
                # ---- 平台保护层：与算法无关的二次钳制 ----
                for p in self.protections:
                    action = p.apply(obs, action)
                commands.append(action)
                row["t"].append(k * cfg.dt_mpc + cfg.dt_mpc)
                row["s_head"].append(st.s_head)
                row["v_head"].append(st.v_head)
                row["v_ga"].append(st.v_group[0])
                row["b"].append(float(action.brake_kpa))
                row["uhat"].append(float(action.u_hat))
                row["v_sup"].append(float(rf.v_sup))
                row["atp"].append(1.0 if action.brake_apply else 0.0)
            # 车钩力峰值取步前值（与旧脚本同口径）
            fc = self.plant.coupler_peak_forces()
            reports: Sequence[ActuatorReport] = self.plant.step(commands,
                                                               cfg.sub_steps)
            for i, rep in enumerate(reports):
                row["thr"].append(rep.throttle)
                row["ed"].append(rep.ed)
                row["fc_peak"].append(fc[i])
            row["s_ref0"].append(states[0].s_head)
            row["v_ref0"].append(refs[0].v_ref)
            for key in KEYS:
                log[key].append(row[key])
            n = k + 1

            if self.verbose and k % 300 == 0:
                btxt = ["50kPa" if c.brake_apply else "0" for c in commands]
                print(f"  [{cfg.name}] t={k*cfg.dt_mpc:6.0f}s "
                      f"s0={states[0].s_head/1000:6.2f}km "
                      f"v0={states[0].v_head*3.6:5.1f}km/h b={btxt}")

            post = self.plant.observe()
            if not np.isfinite(post[0].v_head) or \
                    post[0].v_head * 3.6 > self.abort_speed_kmh:
                print(f"  [{cfg.name}] 异常终止 t={k*cfg.dt_mpc:.0f}s")
                break
            if post[0].s_head >= cfg.s_end:
                if self.verbose:
                    print(f"  [{cfg.name}] 头车到达 {cfg.s_end/1000:.1f} km，提前结束")
                break

        log = {k: np.array(v[:n]) for k, v in log.items()}
        summary = self._summary(log, n, np.array(solve_ms), time.time() - t0)
        if self.verbose:
            print(f"[{cfg.name}] done: {n} MPC 步，壁钟 {summary['wall_s']:.0f}s")
        return EpisodeResult(log=log, summary=summary)

    # ------------------------------------------------------------------
    def _summary(self, log, n, solve_ms, wall_s) -> Dict[str, Any]:
        cfg = self.cfg
        v_err = np.abs(log["v_ref0"][:, 0] - log["v_head"][:, 0])[:, None]
        v_err = np.concatenate([
            v_err,
            np.abs(log["v_head"][:, :-1] - log["v_head"][:, 1:]),
        ], axis=1)
        s_err = np.abs(log["s_head"][:, :-1] - cfg.d_des - log["s_head"][:, 1:])
        s_err = np.concatenate([np.zeros((n, 1)), s_err], axis=1)
        return dict(
            tag=cfg.name,
            scenario=cfg.name,
            algorithm=getattr(self.algorithm, "name", type(self.algorithm).__name__),
            coupler_model=cfg.coupler_model,
            steps=n,
            t_end=float(log["t"][-1, 0]),
            dist_km=float(log["s_head"][-1, 0] / 1000),
            v_err_max=np.maximum(v_err, 0).max(axis=0),
            s_err_max=s_err.max(axis=0),
            v_err_avg=float(v_err.max(axis=0).mean()),
            s_err_avg=float(s_err.max(axis=0).mean()),
            fc_peak_kN=[float(log["fc_peak"][:, i].max()) for i in range(3)],
            gap_min_head=float((log["s_head"][:, :-1] - log["s_head"][:, 1:]).min()),
            v_max_kmh=float(log["v_head"].max() * 3.6),
            v_min_kmh=float(log["v_head"].min() * 3.6),
            energy_kwh=[float(x) for x in self.plant.energy_kwh()],
            solve_ms_mean=float(solve_ms.mean()) if solve_ms.size else 0.0,
            solve_ms_p95=float(np.percentile(solve_ms, 95)) if solve_ms.size else 0.0,
            wall_s=wall_s,
        )
