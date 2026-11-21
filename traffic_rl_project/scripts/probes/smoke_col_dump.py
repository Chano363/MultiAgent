"""冒烟（ADR-083 / §19.44 候选前提①）：训练期逐列车钩力量落盘链路端到端自检。

⚠️ **不是**峰值/安全判据（红线 3）：本脚本只验"逐列量能从 env info 一路
落到产物文件"，horizon 只有几十步，物理量本身无参考意义。

跑法（WSL + conda traffic_rl）：
    python scripts/probes/smoke_col_dump.py
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

OUT = ROOT / "outputs" / "logs" / "adr083_col_smoke"


def main() -> int:
    from src.trainer.train_fleet import train

    OUT.mkdir(parents=True, exist_ok=True)
    seed = 999  # 与正式 seed 隔离，避免撞既有产物名
    train(
        episodes=2,
        num_trains=3,
        consist_preset="20kt_1plus108_1plus108",
        grade_profile="shuozhou_ningwuxi_beidaniu_49km",
        max_steps=60,
        decompose="loco_ed_ab",
        decision_interval=10,
        seed=seed,
        checkpoint_dir=str(OUT / "ckpt"),
        results_dir=str(OUT / "results"),
        figures_dir=str(OUT / "figures"),
    )

    res = OUT / "results"
    hist_files = sorted(res.glob("train_history_*.json"))
    col_files = sorted(res.glob("train_col_coupler_*.csv"))
    if not hist_files:
        print("[FAIL] 未生成 train_history_*.json")
        return 1
    if not col_files:
        print("[FAIL] 未生成 train_col_coupler_*.csv")
        return 1

    hist = json.loads(hist_files[0].read_text(encoding="utf-8"))
    for k in ("col_peak_coupler_kN", "col_violations"):
        if k not in hist:
            print(f"[FAIL] history 缺键 {k}")
            return 1
    cp, cv = hist["col_peak_coupler_kN"], hist["col_violations"]
    n_cols = len(cp[0])
    ok = (len(cp) == len(cv) == len(hist["rewards"])
          and all(len(r) == n_cols for r in cp)
          and all(len(r) == n_cols for r in cv))
    if not ok:
        print(f"[FAIL] 形状不一致 cp={len(cp)}x{len(cp[0])} cv={len(cv)}x{len(cv[0])} "
              f"rewards={len(hist['rewards'])}")
        return 1
    if n_cols != 3:
        print(f"[FAIL] 期望 3 列，实际 {n_cols}")
        return 1

    print(f"[OK] 逐列落盘链路贯通：ep={len(cp)} 列数={n_cols}")
    print(f"     col_peak_coupler_kN[0] = {[round(float(x), 2) for x in cp[0]]}")
    print(f"     col_violations[0]      = {[int(x) for x in cv[0]]}")
    print(f"     文件：{col_files[0].name}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
