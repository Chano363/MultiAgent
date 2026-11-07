# -*- coding: utf-8 -*-
"""离线回放数据集：把已归档的基线轨迹读成平台 Observer 流。

用途：仿真运行环境（NeTrainSim 联合仿真）暂时无法接入时，平台仍可
用"离线回放执行器"在真实基线轨迹上驱动所选算法插件，
产出可对比的控制指令与跟踪指标。回放不做物理推进，仅执行算法。
"""
from __future__ import annotations

import csv
import os
from dataclasses import dataclass
from typing import Dict, List, Sequence, Tuple

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(_ROOT, "outputs_shuohuang")
DEFAULT_DATASET = os.path.join(DATA_DIR, "sim_shuohuang_coupler_linear_atp.csv")

# 编组几何：54 辆 C80（车钩参考点间距 12 m）+ HXD1 车长 12.1 m
N_WAGON = 54
COUPLER_FREE_LENGTH = 12.0
LOCO_LENGTH = 12.1
TRAIN_LENGTH_M = N_WAGON * COUPLER_FREE_LENGTH + LOCO_LENGTH


@dataclass
class ReplayData:
    path: str
    t: List[float]
    s_head: List[Tuple[float, float, float]]
    v_head: List[Tuple[float, float, float]]
    v_ga: List[Tuple[float, float, float]]
    v_sup: List[Tuple[float, float, float]]
    fc_peak: List[Tuple[float, float, float]]
    atp: List[Tuple[float, float, float]]

    @property
    def n_steps(self) -> int:
        return len(self.t)


def _f(row: Dict[str, str], key: str) -> float:
    try:
        return float(row.get(key, 0.0))
    except (TypeError, ValueError):
        return 0.0


def load_replay(path: str | None = None) -> ReplayData:
    path = path or DEFAULT_DATASET
    if not os.path.exists(path):
        raise FileNotFoundError(f"未找到离线回放数据集: {path}")
    cols = ("s_head", "v_head", "v_ga", "v_sup", "fc_peak", "atp")
    buf: Dict[str, List[Tuple[float, float, float]]] = {c: [] for c in cols}
    ts: List[float] = []
    with open(path, "r", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            ts.append(_f(row, "t"))
            for c in cols:
                buf[c].append(tuple(_f(row, f"{c}{i}") for i in range(3)))
    return ReplayData(path=path, t=ts, s_head=buf["s_head"], v_head=buf["v_head"],
                      v_ga=buf["v_ga"], v_sup=buf["v_sup"],
                      fc_peak=buf["fc_peak"], atp=buf["atp"])


def states_at(data: ReplayData, k: int) -> Sequence:
    """把第 k 行记录翻译成平台 TrainState 序列（几何按刚体编组近似）。"""
    from dtwin.contracts import TrainState

    out: List[TrainState] = []
    for i in range(3):
        s_head = data.s_head[k][i]
        v_head = data.v_head[k][i]
        v_ga = data.v_ga[k][i]
        lead = out[i - 1] if i > 0 else None
        out.append(TrainState(
            train_id=i,
            s_head=s_head,
            v_head=v_head,
            v_group=(v_ga, v_ga),
            s_group=(s_head - 250.0, s_head - 500.0),
            gap_lead=(lead.s_head - s_head if lead else float("inf")),
            v_lead=(lead.v_head if lead else float("inf")),
        ))
    return out
