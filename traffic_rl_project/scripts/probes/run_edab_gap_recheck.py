"""§19.51 追加验证队列：**在现版本代码下重跑 `ed_ab` 族 ckpt 的官方整程快评**。

为什么需要（本轮新增，2026-11-21）：
    §19.51.3b 的分层统计发现"列距优势与 `observation_schema` 完全共变且分布零重叠"
    （`loco_ed_ab_base12` n=29 中位 60.8 m vs `loco_notch_incr_v1` n=15 中位 651.1 m），
    但那是**历史产物**的横切统计——**不是受控对照**：
      · 历史 `ed_ab` 读数来自 **2026-11-11/12 的旧代码**（`git_commit=a589991d…`），
        而第 9 投读数来自 **2026-11-20 的新代码**（`git_commit=154c1b8e…`）；
      · 期间物理层/控制器层改过（ADR-076/077/080/081 全部在 `1bb7b02` 祖先链上）；
      · 因此"旧代码下的 42 m 列距"**能否在现版本代码下复现，是未知数**。
    ⇒ 第 11 投若要选"回 `ed_ab` schema"这个干预面，**必须先确认它在现版本代码下仍然成立**，
      否则会拿一个已失效的历史读数当可行性依据。

本脚本做的事（**零新增训练，只跑评估**）：
    ① 用**现版本代码**、与历史读数**同参**（31500 步 / decision_interval=10 / eval_seed=0 /
       init_speed 60 km/h / grade=shuozhou_ningwuxi_beidaniu_49km / consist=10kt_1plus108）
       跑 `ed_ab` 族代表 ckpt 的**官方整程确定性快评**；
    ② 同时跑一个 `notch_incr` 族 ckpt 作**同机同期对照**（排除"代码变了"的混淆）；
    ③ 输出 `outputs/logs/adr083_gap_primary_metric_sweep/edab_recheck.json`，
       含两族的 `gap_err_mean_abs_m` / `gap_err_peak_abs_m` / `band_rate` / `peak_coupler_kN` /
       `gap_min_m` / `rear_end_steps` 与 metadata（含 `git_commit` / `physics_version`）。

⚠️ **判读规则（前置写死，避免事后解释）**：
    · `ed_ab` 族在现版本代码下的 `gap_err_mean_abs_m` **仍 ≤ ~150 m 量级**
      ⇒ **"回 `ed_ab` schema"作为第 11 投干预面成立**（历史读数可搬运）；
    · `ed_ab` 族在现版本代码下的 `gap_err_mean_abs_m` **已退到 `notch_incr` 族量级**
      ⇒ **历史读数已失效**，"回 schema"干预面**不可直接用**，必须重新从头训；
    · 两种情况都**不构成对第 11 投方向的拍板**（方向属 owner），只回答"这个干预面还存不存在"。

⚠️ **口径与红线**：
    · **零新增训练**（只跑评估）⇒ 不触红线 1（云端实例审批）；
    · **同机串行**（红线 2 附则）⇒ 本脚本**等放大系数探针落盘后**才启动，
      且**不与 followup / primarysens 队列重叠**（由调度器保证先后）；
    · **短窗不得当峰值判据**（红线 3）⇒ 本脚本**只跑整程 31500 步**，无短窗模式；
    · **产物不落 `outputs/` 根级**（硬红线 4）⇒ 一律进 `outputs/logs/adr083_gap_primary_metric_sweep/`；
    · 读数属**机制层可行性检验**，**不得**直接当论文主表数字（须走 §0.8.2 与红线 5 验收）。

用法（WSL + conda traffic_rl 内执行）：
    python scripts/probes/run_edab_gap_recheck.py
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
OUT_DIR = ROOT / "outputs" / "logs" / "adr083_gap_primary_metric_sweep"

# (标签, ckpt 相对路径, experiment 配置, out_suffix)
# ed_ab 族代表：历史读数 gap_err_mean 42.0 m / band 1.0 / peak 1280.2 kN
EDAB_CKPTS = [
    ("edab_v10_ep13",
     "outputs/checkpoints/formation_10kt_1plus108/v10_l1_20261111_163412/seed0/"
     "mappo_fleet_ep13_dec_ad2_cp_seed0.pt",
     "configs/experiments/formation_ed_ab_3train_1plus108.yaml",
     "_sec1951_edab_v10_ep13"),
]

# notch_incr 族代表：第 9 投 ep4，历史/云端读数 gap_err_mean 940.4 m / band 0.9074
NOTCH_CKPTS = [
    ("notchincr_w4_ep4",
     "outputs/checkpoints/formation_10kt_1plus108/w4nincrgatecaprel_w4full_20261120_cloud/"
     "mappo_fleet_last_ep4_dec_ad1_cp_seed0_seed0.pt",
     "configs/experiments/formation_ed_ab_3train_1plus108_nincrgatecaprel.yaml",
     "_sec1951_notchincr_w4_ep4"),
]

METRIC_KEYS = [
    "peak_coupler_kN", "viol", "rear_end_steps", "band_rate",
    "gap_err_mean_abs_m", "gap_err_peak_abs_m", "gap_min_m",
    "atp_interventions", "final_speed_kmh", "reward",
]


def _run_one(label: str, ckpt: str, experiment: str, suffix: str, max_steps: int) -> dict:
    """跑一次官方整程确定性快评（`evaluate_decompose.py`），返回该集读数 + metadata。"""
    cmd = [
        sys.executable, "src/evaluation/evaluate_decompose.py",
        "--mode", "decompose_m1",
        "--checkpoint", ckpt,
        "--experiment", experiment,
        "--max_steps", str(max_steps),
        "--decision_interval", "10",
        "--eval_seed", "0",
        "--init_speed_kmh", "60",
        "--num_trains", "3",
        "--n_seed", "1",
        "--grade", "shuozhou_ningwuxi_beidaniu_49km",
        "--out_suffix", suffix,
    ]
    print(f"[recheck] === {label} 开始 ===", flush=True)
    print(f"[recheck] cmd: {' '.join(cmd)}", flush=True)
    t0 = time.time()
    proc = subprocess.run(cmd, cwd=str(ROOT), capture_output=True, text=True)
    rc = proc.returncode
    print(f"[recheck] {label} rc={rc} 用时 {time.time() - t0:.0f}s", flush=True)
    if rc != 0:
        print(proc.stdout[-3000:], flush=True)
        print(proc.stderr[-3000:], flush=True)
        return {"label": label, "checkpoint": ckpt, "experiment": experiment,
                "rc": rc, "error": "evaluate_decompose 非零退出"}

    # 找产物
    cands = sorted((ROOT / "outputs" / "results" / "decompose").glob(f"*{suffix}*.json"))
    if not cands:
        return {"label": label, "checkpoint": ckpt, "experiment": experiment,
                "rc": rc, "error": f"未找到产物 *{suffix}*.json"}
    path = cands[-1]
    with open(path, "r", encoding="utf-8") as f:
        doc = json.load(f)
    meta = doc.get("metadata", {}) or {}
    res = doc.get("results", {}) or {}
    metrics = {}
    for key, val in res.items():
        if isinstance(val, dict) and "peak_coupler_kN" in val:
            metrics = {k: val.get(k) for k in METRIC_KEYS}
            metrics["_result_key"] = key
            break
    return {
        "label": label,
        "checkpoint": ckpt,
        "experiment": experiment,
        "rc": rc,
        "artifact": str(path.relative_to(ROOT)),
        "metadata": {
            "git_commit": meta.get("git_commit"),
            "physics_version": meta.get("physics_version"),
            "simulator_model": meta.get("simulator_model"),
            "observation_schema": (meta.get("observation_schema") or {}).get("name"),
        },
        "metrics": metrics,
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--max_steps", type=int, default=31500,
                    help="整程步数（红线 3：短窗不作峰值/安全判据）")
    ap.add_argument("--out", default=None)
    args = ap.parse_args()

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    out_path = Path(args.out) if args.out else (OUT_DIR / "edab_recheck.json")

    rows = []
    for label, ckpt, exp, suffix in EDAB_CKPTS + NOTCH_CKPTS:
        if not (ROOT / ckpt).exists():
            rows.append({"label": label, "checkpoint": ckpt, "error": "ckpt 不存在（跳过）"})
            print(f"[recheck] SKIP {label}: ckpt 不存在 {ckpt}", flush=True)
            continue
        rows.append(_run_one(label, ckpt, exp, suffix, args.max_steps))

    # 判读（规则前置写死，见模块 docstring）
    def _gm(r):
        return (r.get("metrics") or {}).get("gap_err_mean_abs_m")

    edab = next((r for r in rows if r["label"].startswith("edab")), None)
    notch = next((r for r in rows if r["label"].startswith("notchincr")), None)
    verdict = "无法判定（缺少读数）"
    # ⚠️ 红线 3：短窗只作链路活性校验，**不得**当列距/峰值判据
    #    （列距发散发生在全程前 5%~10%，300 步窗口里尚未展开 ⇒ 短窗读数必然"都好"）
    if args.max_steps < 31500:
        verdict = (f"⚠️ 短窗（max_steps={args.max_steps}）读数**只作链路活性校验**，"
                   "不构成判据（红线 3）：列距发散发生在全程前 5%~10%，"
                   "短窗内尚未展开 ⇒ 短窗读数必然偏乐观。"
                   "本判决作废，须整程 31500 步复跑。")
    elif edab and _gm(edab) is not None and notch and _gm(notch) is not None:
        if _gm(edab) <= 150.0:
            verdict = ("ed_ab 族在现版本代码下仍 ≤~150 m ⇒ "
                       "『回 ed_ab schema』干预面成立（历史读数可搬运）")
        else:
            verdict = ("ed_ab 族在现版本代码下已退到 notch_incr 量级 ⇒ "
                       "历史读数已失效，『回 schema』不可直接用，须从头训")

    payload = {
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "purpose": "§19.51.3b 追加验证：ed_ab 族列距优势在现版本代码下是否仍成立",
        "max_steps": args.max_steps,
        "rows": rows,
        "verdict": verdict,
        "boundary": ("机制层可行性检验，不构成对第 11 投方向的拍板；"
                     "读数不得直接当论文主表数字（须走 §0.8.2 与红线 5）"),
    }
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
    print(f"[recheck] 落盘 {out_path}", flush=True)
    print(f"[recheck] 判决：{verdict}", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
