# -*- coding: utf-8 -*-
"""数据记录：把 Episode 日志落成 CSV / 指标汇总。

CSV 列名与旧脚本 outputs_shuohuang/sim_shuohuang_coupler_*.csv 完全一致，
便于逐列比对验证"平台化改造不改变行为"。
"""
from __future__ import annotations

import csv
import json
import os
from typing import Any, Dict

import numpy as np

COLUMNS = (["t"] + [f"s_head{i}" for i in range(3)]
           + [f"v_head{i}" for i in range(3)]
           + [f"v_ga{i}" for i in range(3)]
           + [f"thr{i}" for i in range(3)] + [f"ed{i}" for i in range(3)]
           + [f"b{i}" for i in range(3)] + [f"uhat{i}" for i in range(3)]
           + [f"fc_peak{i}" for i in range(3)]
           + [f"v_sup{i}" for i in range(3)] + [f"atp{i}" for i in range(3)]
           + ["s_ref0", "v_ref0"])


def write_csv(log: Dict[str, np.ndarray], path: str) -> None:
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    n = len(log["t"])
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(COLUMNS)
        for k in range(n):
            vals = ([float(log["t"][k, 0])] + list(log["s_head"][k])
                    + list(log["v_head"][k]) + list(log["v_ga"][k])
                    + list(log["thr"][k]) + list(log["ed"][k])
                    + list(log["b"][k]) + list(log["uhat"][k])
                    + list(log["fc_peak"][k]) + list(log["v_sup"][k])
                    + list(log["atp"][k])
                    + [float(log["s_ref0"][k, 0]), float(log["v_ref0"][k, 0])])
            w.writerow([f"{x:.4f}" for x in vals])


def write_summary(summary: Dict[str, Any], path: str) -> None:
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(f"{summary['tag']}: steps={summary['steps']} "
                f"dist={summary['dist_km']:.1f}km "
                f"v_err_avg={summary['v_err_avg']:.3f} "
                f"s_err_avg={summary['s_err_avg']:.1f} "
                f"fc_peak={[f'{x:.0f}' for x in summary['fc_peak_kN']]} "
                f"gap_min={summary['gap_min_head']:.0f} "
                f"v_max={summary['v_max_kmh']:.1f} "
                f"v_min={summary['v_min_kmh']:.1f}\n")
    with open(os.path.splitext(path)[0] + ".json", "w", encoding="utf-8") as f:
        json.dump({k: (v.tolist() if isinstance(v, np.ndarray) else v)
                   for k, v in summary.items()}, f, ensure_ascii=False, indent=2)
