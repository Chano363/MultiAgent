# -*- coding: utf-8 -*-
"""Tube MPC 基线评估（主仓场景：朔黄 49.6 km / 10 988 t ×3 / 4 300 m 起点 / 60 km/h）。

架构（`docs/knowledge/MPC_BASELINE_KNOWLEDGE_BASE.md` §6 修订版）：
- 被控对象：主库 `TrainDynamics` ×3（**物理同源，未改一行**；zba 复现报告 §4 已验证此路径）
- 控制器：`src/mpc_baseline/tube_mpc.py`（zba 忠实移植，3 实例对称 3 列）
- 参考轨迹：主仓 `ref_speed_table`（与 D-RL 同源，公平标定自动成立）
- 列间协调：跟随车 v_ref = min(v_t(s_self), v_lead + gap 修正)（zba v2 参考律）
- 安全：列间安全包络（ETCS 式）+ 50 kPa 循环制动（文献[22]）；`--atp` 尚未接入，禁用
- 车钩：`--coupler mt2|zero` 参数化（ADR-042 主对比 = 关车钩物理）

用法：
    python src/evaluation/evaluate_mpc_tube.py \
        --out_dir outputs/results/mpc_baseline/tube_v1_20261114 \
        --coupler mt2 --max_steps 31500
"""
import argparse
import hashlib
import json
import os
import sys
import time
from datetime import datetime
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from src.train_dynamics.train import TrainDynamics                       # noqa: E402
from src.train_dynamics.braking import AirBrakeNotch                     # noqa: E402
from src.train_dynamics.grade_profile import PROFILES                    # noqa: E402
from src.environments.train_env import CONSIST_PRESETS                   # noqa: E402
from src.mpc_baseline.params import (DT_MPC, M_LOCO, M_WAGON_GROUP,      # noqa: E402
                                     D_DES, V_INIT, GAP_T_ADJ, GAP_V_ADJ,
                                     ED_MAX, ED_AIR_CAP, R_CYCLE, KAPPA,
                                     V_MIN_RELEASE, V_STATIC)
from src.mpc_baseline.tube_mpc import TubeMPC                            # noqa: E402
from src.metadata import build_metadata                                  # noqa: E402

DT_DYN = 0.1
SUB = int(round(DT_MPC / DT_DYN))
N_TRAINS = 3
GA = (1, 54)                  # 货车组1 = 车辆索引 1..54（0=机车）
GB = (55, 108)                # 货车组2 = 55..108
S_HEAD0 = 4300.0              # m  领航列头位（ADR-068 起点）
HEAD_GAP = D_DES              # m  列间头对头距（与主仓 env reset 共用同一目标间距）
S_END = 49600.0               # m  终点（route_end_m，ADR-068）
A_EB = 0.15                   # m/s² 列间安全包络紧急制动率（zba v2）
MIN_GAP_AIR = 150.0           # m   安全包络静态最小间隔（zba v2）
V_CAP_MPS = 75.0 / 3.6        # m/s 绝对速度上限（ADR-068 口径，参考封顶）


def zero_coupler():
    """ADR-042 主对比：物理关车钩（全部阻抗置零）。"""
    return CouplerParams_stub()


def CouplerParams_stub():  # noqa: N802
    from src.train_dynamics.params import CouplerParams
    return CouplerParams(stiffness=0.0, preload_n=0.0, friction_n=0.0,
                         friction_static_n=0.0, friction_v_er=0.0,
                         max_impulse_n=0.0, stroke_m=1e9, rigid_stiffness_nm=0.0)


def make_train(coupler_mode, head_pos, profile):
    """主仓编组（10 kt 1+108）+ 主库物理；coupler ∈ {mt2, zero}。"""
    from src.train_dynamics.params import CouplerParams
    consist = CONSIST_PRESETS["10kt_1plus108"]()
    dyn = TrainDynamics(consist, dt=DT_DYN, simcase="official")
    if coupler_mode == "zero":
        dyn.set_couplers([CouplerParams_stub()
                          for _ in range(dyn.num_vehicles - 1)])
    dyn.set_grade_profile(profile)
    fl = float(CouplerParams().free_length_m)
    pos = head_pos - np.arange(dyn.num_vehicles) * fl
    dyn.set_initial(pos=pos, vel=np.full(dyn.num_vehicles, float(V_INIT)))
    return dyn


def grp_mean(dyn, lo_hi, key="vel"):
    lo, hi = lo_hi
    arr = dyn.vel if key == "vel" else dyn.pos
    return float(np.mean(arr[lo:hi + 1]))


def v_ref_at(s_m, tbl_s, tbl_v):
    return float(np.interp(s_m, tbl_s, tbl_v))


def safety_envelope(dyn, lead_dyn):
    """ETCS 式列间安全包络（zba v2）：v_allow = sqrt(v_lead² + 2·a_eb·净空)。"""
    gap_air = lead_dyn.pos[-1] - dyn.pos[0]      # 前车尾 → 本车头
    clearance = max(gap_air - MIN_GAP_AIR, 0.0)
    return float(np.sqrt(max(lead_dyn.vel[0], 0.0) ** 2 + 2.0 * A_EB * clearance))


def solve_tube_command(mpc, x0, v_ref, a_ref, d2):
    """按 zba 原实现求解并合成 tube 反馈；名义状态每控制步重置为实测误差。"""
    mpc.xbar = np.asarray(x0, dtype=float).copy()
    u_star = mpc.solve(x0, v_ref, a_ref, d2)
    z = x0 - mpc.xbar
    return float(u_star + KAPPA * (z[1] - z[3]))       # 式 48 tube 反馈


def speed_guard(dyn, v_ref, thr, ed):
    """绝对速度保护：超参考 0.5 m/s 时强制零牵引、满电制动。

    Tube MPC 的硬约束只限制“不低于参考带下界”，并不保证从超速态回落到参考；
    其前馈又会抵消已施加的 AB/坡度分力，可能反解出牵引。故在执行层加独立保护，
    与主环境 ATP 的兜底语义一致；AB 仍由循环制动状态机负责。
    """
    if float(dyn.vel[0]) > v_ref + 0.5:
        return 0.0, ED_MAX
    return thr, ed


def cycle_brake(dyn, v_ref, t_now):
    """文献[22] 循环制动：50 kPa 初制动 + 缓解后 45 s 最短充风。"""
    st = getattr(dyn, "_mpc_cycle_state", None)
    if st is None:
        st = dict(b_app=False, t_rel=-1e9)
        dyn._mpc_cycle_state = st
    v = float(dyn.vel[0])
    if v <= V_MIN_RELEASE:                 # 式 2-26：低速强制缓解
        if st["b_app"]:
            st["b_app"] = False
            st["t_rel"] = float(t_now)
        return False
    if st["b_app"]:
        if v <= v_ref - 0.5:
            st["b_app"] = False
            st["t_rel"] = float(t_now)
    elif v >= v_ref + 0.5 and t_now - st["t_rel"] >= 45.0:
        st["b_app"] = True                 # 仅缓解后计时；施加时长不设 45 s 上限
    return st["b_app"]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out_dir", required=True)
    ap.add_argument("--coupler", choices=["mt2", "zero"], default="mt2")
    ap.add_argument("--max_steps", type=int, default=31500)
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--atp", action="store_true")
    args = ap.parse_args()
    if args.atp:
        raise SystemExit("--atp 尚未接入执行链，禁止用它产出 ATP 指标")

    out = Path(args.out_dir)
    out.mkdir(parents=True, exist_ok=True)

    profile = PROFILES["shuozhou_ningwuxi_beidaniu_49km"]()
    ref = np.load("outputs/sim_validation/phys_validation/"
                  "refspeed_baseline_20261113_095953/ref_speed_table.npz")
    tbl_s = np.asarray(ref["s_m"], dtype=float)
    # ⚠️ 表内 v_mps 已经是 m/s（首点 16.4 m/s ≈ 59 km/h），**不得再 ×3.6**——
    #    v1 曾误乘 3.6 后当 m/s 用，参考线 59→212 km/h，MPC 全程追假参考（LRN 级 bug）
    tbl_v = np.asarray(ref["v_mps"], dtype=float)

    dyns = [make_train(args.coupler, S_HEAD0 - i * HEAD_GAP, profile)
            for i in range(N_TRAINS)]
    mpcs = [TubeMPC(idx=i) for i in range(N_TRAINS)]
    train_len0 = float(dyns[0].pos[0] - dyns[0].pos[-1])
    intra0 = [dyns[i].pos[0] - grp_mean(dyns[i], GA, "pos") for i in range(3)]
    v_lead_prev = [d.vel[0] for d in dyns]
    v_ga_prev = [grp_mean(d, GA) for d in dyns]

    keys = ["t", "s_head", "v_head", "v_ga", "thr", "ed", "b", "uhat",
            "fc_peak", "v_ref0", "gap_lead", "gap_air_lead"]
    log = {k: [] for k in keys}
    per_train_peak = np.zeros(N_TRAINS)
    solve_ms = []
    solve_ok = []
    solve_attempts = []

    n_steps = int(args.max_steps)
    t0 = time.time()
    route_reached = False
    for k in range(n_steps):
        cmds = []
        for i in range(N_TRAINS):
            dyn = dyns[i]
            if i == 0:
                s_ref = v_ref_at(dyn.pos[0], tbl_s, tbl_v)
                v_ref = s_ref
                a_ref = 0.0
            else:
                gap_now = dyns[i - 1].pos[0] - dyn.pos[0]
                v_lead = max(float(dyns[i - 1].vel[0]), 0.0)
                corr = float(np.clip((gap_now - D_DES) / GAP_T_ADJ,
                                     -GAP_V_ADJ, GAP_V_ADJ))
                v_ref = min(v_ref_at(dyn.pos[0], tbl_s, tbl_v), v_lead + corr)
                a_ref = float((v_lead - v_lead_prev[i - 1]) / DT_MPC)
            v_allow = (safety_envelope(dyn, dyns[i - 1]) if i > 0
                       else np.inf)
            if v_ref > v_allow:
                v_ref = v_allow
            if v_ref > V_CAP_MPS:            # 绝对上限（75 km/h 口径，ADR-068）
                v_ref = V_CAP_MPS
            v_ga = grp_mean(dyn, GA)
            x0 = np.array([0.0,
                           v_ref - dyn.vel[0],
                           dyn.pos[0] - grp_mean(dyn, GA, "pos") - intra0[i],
                           dyn.vel[0] - v_ga])
            d2 = float(-(v_ga - v_ga_prev[i]) / DT_MPC)
            ts = time.time()
            u_hat = solve_tube_command(mpcs[i], x0, v_ref, a_ref, d2)
            solve_ms.append((time.time() - ts) * 1000.0)
            solve_ok.append(bool(mpcs[i].last_solve_success))
            solve_attempts.append(int(mpcs[i].last_solve_attempts))
            if i > 0 and dyn.vel[0] > v_allow:
                u_hat = min(u_hat, 0.0)                     # 安全包络内禁加速
            b_app = cycle_brake(dyn, v_ref, k * DT_MPC)
            ed_cap = ED_AIR_CAP if (b_app and dyn.vel[0] < v_ref + 0.3) else ED_MAX
            # 式 11/13 前馈：非控制力补偿后反解手柄（zba :276 同款）
            v_abs = abs(dyn.vel[0])
            cpl = 0.0 if v_abs < V_STATIC else dyn._coupler_forces()[0]
            f_non = (dyn._air_braking_forces()[0]
                     - dyn._resistance_forces()[0]
                     + dyn._grade_forces()[0] + cpl)
            u_n = u_hat * M_LOCO * 1000.0 - f_non
            loco = dyn.consist.vehicles[0]
            v = max(v_abs, 0.5)
            if u_n >= 0.0:
                from src.train_dynamics.tractive import tractive_force
                f_max = tractive_force(loco.max_power_kw,
                                       loco.transmission_efficiency, 1.0, v,
                                       loco.mass_t)
                thr = float(np.clip(u_n / max(f_max, 1.0), 0.0, 1.0))
                ed = 0.0
            else:
                from src.train_dynamics.braking import electric_brake_force_n
                f_ed = electric_brake_force_n(loco.mass_t, v, 1.0,
                                              loco.max_power_kw,
                                              loco.transmission_efficiency)
                ed = float(np.clip(abs(u_n) / max(f_ed, 1.0), 0.0, ed_cap))
                thr = 0.0
            thr, ed = speed_guard(dyn, v_ref, thr, ed)
            cmds.append((dyn, thr, ed, b_app))
            row_i = dict(t=k * DT_MPC + DT_MPC, s_head=dyn.pos[0],
                         v_head=dyn.vel[0], v_ga=v_ga, thr=thr, ed=ed,
                         b=float(b_app), uhat=float(u_hat))
            fc = np.abs(dyn.coupler_interface_forces())
            row_i["fc_peak"] = float(fc.max()) / 1e3 if fc.size else 0.0
            row_i["v_ref0"] = v_ref
            row_i["gap_lead"] = (dyns[i - 1].pos[0] - dyn.pos[0]) if i else np.nan
            row_i["gap_air_lead"] = (dyns[i - 1].pos[-1] - dyn.pos[0]) if i else np.nan
            for kk, vv in row_i.items():
                log[kk].append(vv)
            per_train_peak[i] = max(per_train_peak[i],
                                    float(np.max(np.abs(
                                        dyn.coupler_interface_forces()))) / 1e3
                                        if dyn.coupler_interface_forces().size
                                        else 0.0)
        v_lead_prev = [d.vel[0] for d in dyns]
        v_ga_prev = [grp_mean(d, GA) for d in dyns]
        for _ in range(SUB):                      # ZOH 保持 1 s
            for dyn, thr, ed, b_app in cmds:
                thr_arr = np.zeros(dyn.num_vehicles)
                ed_arr = np.zeros(dyn.num_vehicles)
                thr_arr[0], ed_arr[0] = thr, ed
                if b_app:
                    dyn.step_vehicles_ed_ab(thr_arr, ed_arr,
                                            AirBrakeNotch.SERVICE,
                                            brake_origin=1,
                                            reduction_kpa=R_CYCLE)
                else:
                    dyn.step_vehicles_ed_ab(thr_arr, ed_arr,
                                            AirBrakeNotch.RELEASE,
                                            brake_origin=1)
        if not np.isfinite(dyns[0].vel).all():
            print(f"异常终止 t={k * DT_MPC:.0f}s（非有限速度）")
            break
        if dyns[0].pos[0] >= S_END:
            route_reached = True
            print(f"头车到达 {S_END/1000:.1f} km，提前结束")
            break

    # log 按“控制步 → 列”交错展开；steps/full_route 必须与主环境一致，
    # 以领航列是否到达 route_end 判定，不能误用数组末尾的第三列状态。
    T = len(log["t"]) // N_TRAINS
    def matrix(key):
        return np.asarray(log[key], dtype=float).reshape(T, N_TRAINS)

    v_mat = matrix("v_head")
    b_mat = matrix("b")
    gap_air = matrix("gap_air_lead")
    gap_head = matrix("gap_lead")
    # 日志在每控制步下达指令前记录；末态须取最后一次 ZOH 子步之后的状态。
    final_heads = np.array([d.pos[0] for d in dyns], dtype=float)
    final_speeds = np.array([d.vel[0] for d in dyns], dtype=float)
    # 主指标用与主环境 reset 同源的头对头间距；零车钩下车辆可纵向拉开，
    # 尾端净空只作诊断，不能拿末态尾位反推参考间距。
    d_eff = D_DES - train_len0
    gap_err = gap_head[:, 1:] - D_DES
    gap_err_mean = np.mean(gap_err, axis=1)
    lead_band = (v_mat[:, 0] >= V_MIN_RELEASE) & (v_mat[:, 0] <= V_CAP_MPS)
    min_gap_m = float(np.nanmin(gap_air[:, 1:]))
    rear_end_steps = int(np.sum(gap_air[:, 1:] <= 0.0))
    src_hashes = {}
    for rel in ("src/evaluation/evaluate_mpc_tube.py",
                "src/mpc_baseline/params.py",
                "src/mpc_baseline/tube_mpc.py"):
        src_hashes[rel] = hashlib.sha256(
            (Path(__file__).resolve().parents[2] / rel).read_bytes()).hexdigest()
    meta = build_metadata(
        project_root=str(Path(__file__).resolve().parents[2]),
        case="official",
        world_cfg={"simcase": "official", "coupler": args.coupler,
                   "v_max_kmh": 75.0, "init_speed_kmh": 60.0,
                   "start_m": S_HEAD0, "d_des_m": D_DES,
                   "train_len_m": train_len0, "d_eff_m": D_DES - train_len0,
                   "route_end_m": S_END, "grade_profile":
                       "shuozhou_ningwuxi_beidaniu_49km",
                   "consist_preset": "10kt_1plus108",
                   "H_pred": 5, "DT_MPC": DT_MPC, "M_LOCO_t": M_LOCO,
                   "M_WAGON_GROUP_t": M_WAGON_GROUP, "W_LIM_KN": 1.0,
                   "KAPPA": 1.0, "mpc_solver": "SLSQP",
                   "cycle_reduction_kpa": R_CYCLE, "recharge_s": 45.0,
                   "speed_guard_margin_mps": 0.5,
                   "speed_guard_action": "zero_traction_full_ed",
                   "reference_table": ("refspeed_baseline_20261113_095953/"
                                       "ref_speed_table.npz")},
        seed=args.seed,
        entry="src/evaluation/evaluate_mpc_tube.py",
        extra={"max_steps": n_steps, "actual_steps": T,
               "solve_ms_mean": float(np.mean(solve_ms)),
               "solve_success_rate": float(np.mean(solve_ok)),
               "solve_attempts_mean": float(np.mean(solve_attempts)),
               "source_sha256": src_hashes})
    result = {
        "metadata": meta,
        "summary": {
            "steps": T,
            "peak_coupler_kN": float(np.max(per_train_peak)),
            "per_train_peak_kN": per_train_peak.tolist(),
            "coupler_reporting": ("mt2_physical_diagnostic_not_mpc_claim"
                                  if args.coupler == "mt2" else
                                  "zero_impedance_not_a_comparison_metric"),
            "mean_fleet_speed_kmh": float(np.mean(v_mat) * 3.6),
            "mean_lead_speed_kmh": float(np.mean(v_mat[:, 0]) * 3.6),
            "final_head_speed_kmh": float(final_speeds[0] * 3.6),
            "final_head_speeds_kmh": (final_speeds * 3.6).tolist(),
            "final_head_positions_m": final_heads.tolist(),
            "band_rate": float(np.mean(lead_band)),
            "d_eff_m": d_eff,
            "gap_err_mean_abs_m": float(np.mean(np.abs(gap_err_mean))),
            "gap_err_peak_abs_m": float(np.max(np.abs(gap_err_mean))),
            "min_gap_m": min_gap_m,
            "rear_end_steps": rear_end_steps,
            "min_gap_head_m": float(np.nanmin(gap_head[:, 1:])),
            "ab_steps": int(np.any(b_mat > 0.0, axis=1).sum()),
            "ab_agent_ratio": (b_mat > 0.0).mean(axis=0).tolist(),
            "mean_ed": float(np.mean(matrix("ed"))),
            "cycle_brake_train_steps": int(np.sum(b_mat > 0.0)),
            "atp_interventions": None,
            "atp_metric_note": "not_available_in_independent_tube_mpc_entry",
            "solve_ms_mean": float(np.mean(solve_ms)),
            "solve_success_rate": float(np.mean(solve_ok)),
            "solve_attempts_mean": float(np.mean(solve_attempts)),
            "wall_clock_s": time.time() - t0,
            "full_route": bool(route_reached),
        },
    }
    (out / "result.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=1), encoding="utf-8")
    np.savez_compressed(out / "trajectory.npz",
                        **{k: np.asarray(v, dtype=float) for k, v in log.items()})
    print(json.dumps(result["summary"], ensure_ascii=False, indent=1))


def _git_commit():
    try:
        import subprocess
        return subprocess.check_output(
            ["git", "rev-parse", "HEAD"], text=True).strip()
    except Exception:
        return "unknown"


if __name__ == "__main__":
    main()
