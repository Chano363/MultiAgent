# -*- coding: utf-8 -*-
"""
Song2026 Tube-MPC 复现主仿真
运行：python run_reproduction.py [--scenario gentle|downhill|both] [--coupler on|off|both]
输出：outputs/ 下 CSV 数据与 PNG 图（图2/图4风格）、终端指标对照（表5/摘要）
协议：
  - 完全按论文模型与算法实现；未披露参数取 [ASM] 假设值（见 params.py 注释）
  - 用户指令：物理层面关掉车钩力 => --coupler off 时对象内 γ=c=0（控制器不变）
"""
import argparse
import csv
import os
import time
import numpy as np

import params as P
from plant import TrainPlant
from tube_mpc import TubeMPC
from scenarios import (target_position, target_speed, target_accel,
                       gradient_permille)

DT_MPC = P.DT_MPC
DT_PLANT = P.DT_PLANT
SUB = int(round(DT_MPC / DT_PLANT))

SCEN_LEN = {"gentle": 1000.0, "downhill": 1300.0}


def brake_commands(scenario, t, plant, cyc):
    """监督级循环空气制动（文献[22] 3.3 节）：
    - 二进制 u_b∈{0,1}：施加 / 缓解，无中间比例档
    - 初制动减压 50 kPa -> 制动缸压力 P_max=100 kPa（文献[22] 表3-1）
    - 约束 t_apply,j+1 - t_release,j >= T_AI（最短充风时间）
    - 机车电制动承担其余部分，由 Tube-MPC 连续调节（其输出仍受论文式25 的
      U_MIN/U_MAX 约束，未额外施加 80% 限幅）
    触发门限：v 高于参考速度 DV_APPLY 施加；低于参考速度 DV_RELEASE 缓解。
    """
    b = np.zeros(9)
    b_cycle = P.P_CYCLE / P.BRAKE_WAGON["Pmax"]
    for i in range(3):
        v = plant.v[i * 3]
        v_ref = target_speed(t, scenario) if i == 0 else plant.v[(i - 1) * 3]
        if cyc["applied"][i]:
            if v <= v_ref - P.DV_RELEASE:
                cyc["applied"][i] = False
                cyc["t_rel"][i] = t
        else:
            if v >= v_ref + P.DV_APPLY and (t - cyc["t_rel"][i]) >= P.T_AI:
                cyc["applied"][i] = True
        if cyc["applied"][i]:
            b[i * 3 + 1] = b_cycle
            b[i * 3 + 2] = b_cycle
    return b, cyc


def run(scenario, coupler_on, out_tag, verbose=True):
    plant = TrainPlant(coupler_on=coupler_on, seed=2026)
    plant.reset(scenario)
    mpcs = [TubeMPC(idx=i, m_wagon=P.M_WAGON_GROUP,
                    se_lim=P.F_COUPLE_LIM / P.GAMMA) for i in range(3)]
    for mpc in mpcs:
        mpc.xbar = np.zeros(4)
    xbar = [np.zeros(4) for _ in range(3)]
    cyc = dict(applied=[False] * 3, t_rel=[-1e9] * 3)   # 循环制动状态

    n_steps = int(SCEN_LEN[scenario] / DT_MPC)
    log = dict(t=[], s=[], v=[], tr=[], fc=[], fa=[], bP=[], ref=[],
               ubar=[], xbar_log=[])
    v_loc_prev = plant.v[[0, 3, 6]].copy()   # 各机车上一采样时刻速度（求 a_ref）
    t0 = time.time()
    for k in range(n_steps):
        t = k * DT_MPC
        plant.resample_disturbance()
        s_ref1, v_ref1 = target_position(t, scenario), target_speed(t, scenario)
        a_ref1 = target_accel(t, scenario)
        grad1 = gradient_permille(plant.s[0], scenario)

        u_hats = []
        ubar_log = []
        for i in range(3):
            p_loc, p_w2 = i * 3, i * 3 + 1
            if i == 0:
                s_ref, v_ref, a_ref = s_ref1, v_ref1, a_ref1
            else:
                # 式20：追踪前车实际状态保持期望间距。表4初始头间距恰为 D_des=2000，
                # 故参考位置取 s(i-1,1) - D_des（头对头间距口径，见 params.py 注释）
                s_ref = plant.s[3 * (i - 1)] - P.D_DES
                v_ref = plant.v[3 * (i - 1)]
                # 式16 u_eMPC(i,1)=u_MPC(i,0)-u_MPC(i,1)：参考车（前车）输入
                # 经 V2V 可测，取前车机车实测加速度作为前馈 a_ref
                a_ref = float((plant.v[3 * (i - 1)] - v_loc_prev[i - 1])
                              / DT_MPC)
            # 误差状态（式15-18），s_e2 为相对标称间距 DP_INTRA 的偏差
            x0 = np.array([s_ref - plant.s[p_loc], v_ref - plant.v[p_loc],
                           plant.s[p_loc] - plant.s[p_w2] - P.DP_INTRA,
                           plant.v[p_loc] - plant.v[p_w2]])
            # 货车组1已知等效输入 d2（式11/19：a_w1=(Fc_net-F_air-R-G)/m，
            # v̇_e2=û-a_w1=û+d2 => d2=(F_air+R+G-Fc_net)/m，车钩合力为负号）
            grad_w2 = gradient_permille(plant.s[p_w2], scenario)
            fc_net_w2 = plant.F_couple[i * 2] - (plant.F_couple[i * 2 + 1]
                                                 if i * 2 + 1 < 6 else 0.0)
            d2 = (plant.F_air[p_w2] - fc_net_w2
                  + P.M_WAGON_GROUP * P.davis_w0(plant.v[p_w2])
                  + P.M_WAGON_GROUP * 9.81 * grad_w2 / 1000.0) / P.M_WAGON_GROUP
            # 论文算法步骤1：x̄(tk) := x(tk)（名义状态每个采样时刻重置为实测状态）
            xbar[i] = x0
            u_star = mpcs[i].solve(x0, v_ref, a_ref, d2)
            # Tube 反馈（式48）：u = ū* + K z，K=[0,κ]；步骤1 重置后 z=x-x̄=0
            z = x0 - xbar[i]
            u_hat = u_star + P.KAPPA * (z[1] - z[3])
            u_hats.append(u_hat)
            ubar_log.append((u_star, u_hat))
        # 前馈（式11/13）在 plant.step 每个积分子步内连续施加
        plant.set_mpc_input(u_hats)
        # 记录本采样时刻机车速度（下一拍差分求前车加速度 a_ref）
        v_loc_prev = np.array([plant.v[0], plant.v[3], plant.v[6]])
        b_cmd, cyc = brake_commands(scenario, t, plant, cyc)
        plant.set_brake_cmd(b_cmd, t)

        for sub in range(SUB):
            plant.step(t + sub * DT_PLANT, DT_PLANT)

        log["t"].append(t + DT_MPC)
        log["s"].append(plant.s.copy())
        log["v"].append(plant.v.copy())
        log["tr"].append(plant.traction.copy())
        log["fc"].append(plant.F_couple.copy())
        log["fa"].append(plant.F_air.copy())
        log["bP"].append([br.P for br in plant.brakes])
        # 参考与状态时刻对齐（状态为 t+DT_MPC 时刻）
        log["ref"].append((target_position(t + DT_MPC, scenario),
                           target_speed(t + DT_MPC, scenario)))
        log["ubar"].append(ubar_log)
    if verbose:
        print(f"[{out_tag}] sim done in {time.time()-t0:.1f}s")
    return log


def metrics(log, scenario):
    """论文表5口径：机车1对目标曲线，机车2/3对前车实际状态"""
    t = np.array(log["t"])
    s = np.array(log["s"])
    v = np.array(log["v"])
    v_err = np.zeros((len(t), 3))
    s_err = np.zeros((len(t), 3))
    for kk in range(len(t)):
        sr, vr = log["ref"][kk]
        v_err[kk, 0] = abs(vr - v[kk, 0])
        s_err[kk, 0] = abs(sr - s[kk, 0])
        for i in (1, 2):
            v_err[kk, i] = abs(v[kk, 3 * (i - 1)] - v[kk, 3 * i])
            s_err[kk, i] = abs(s[kk, 3 * (i - 1)] - P.D_DES - s[kk, 3 * i])
    fc = np.array(log["fc"])
    out = dict(
        v_err_max=v_err.max(axis=0), s_err_max=s_err.max(axis=0),
        v_err_avg=float(v_err.max(axis=0).mean()),
        s_err_avg=float(s_err.max(axis=0).mean()),
        fc_max=float(np.abs(fc).max()),
        fc_rms=float(np.sqrt((fc ** 2).mean())),
        v_min=float(v.min()), v_max=float(v.max()),
    )
    return out, v_err, s_err


def save_csv(log, path):
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["t"] + [f"s{i}{j}" for i in range(3) for j in range(3)]
                   + [f"v{i}{j}" for i in range(3) for j in range(3)]
                   + [f"u{i}" for i in range(3)]
                   + [f"fc{i}{k}" for i in range(3) for k in range(2)]
                   + [f"P{i}{j}" for i in range(3) for j in range(3)])
        for kk, tt in enumerate(log["t"]):
            row = [tt] + list(log["s"][kk]) + list(log["v"][kk]) \
                + list(log["tr"][kk]) + list(log["fc"][kk]) + list(log["bP"][kk])
            w.writerow([f"{x:.4f}" for x in row])


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--scenario", default="both",
                    choices=["gentle", "downhill", "both"])
    ap.add_argument("--coupler", default="both", choices=["on", "off", "both"])
    args = ap.parse_args()
    scenarios = ["gentle", "downhill"] if args.scenario == "both" else [args.scenario]
    cfgs = [("on", True), ("off", False)] if args.coupler == "both" else \
        [(args.coupler, args.coupler == "on")]

    print("=" * 72)
    print("Song2026 Tube-MPC 复现 | 车钩力物理开关消融")
    print("论文报告值：平均最大速度误差 0.44 m/s，平均最大间距误差 0.66 m，")
    print("            最大车钩力约 330.4 kN（限值 1500 kN）")
    print("=" * 72)
    summary = []
    for sc in scenarios:
        for tag, c_on in cfgs:
            out_tag = f"{sc}_coupler_{tag}"
            log = run(sc, c_on, out_tag)
            save_csv(log, os.path.join(P.OUT_DIR, f"sim_{out_tag}.csv"))
            m, _, _ = metrics(log, sc)
            summary.append((out_tag, c_on, m))
            print(f"\n--- {out_tag} ---")
            print(f"机车最大速度误差 [1,2,3] (m/s): "
                  f"{np.round(m['v_err_max'], 3)}  平均 {m['v_err_avg']:.3f}")
            print(f"机车最大间距误差 [1,2,3] (m)  : "
                  f"{np.round(m['s_err_max'], 3)}  平均 {m['s_err_avg']:.3f}")
            print(f"最大车钩力 (kN): {m['fc_max']:.1f} | RMS: {m['fc_rms']:.1f}"
                  f" | v范围 [{m['v_min']:.2f}, {m['v_max']:.2f}] m/s")
    with open(os.path.join(P.OUT_DIR, "summary.txt"), "w", encoding="utf-8") as f:
        for tag, c_on, m in summary:
            f.write(f"{tag}: v_err_avg={m['v_err_avg']:.3f} "
                    f"s_err_avg={m['s_err_avg']:.3f} fc_max={m['fc_max']:.1f}\n")
    print(f"\n结果已保存至 {P.OUT_DIR}")


if __name__ == "__main__":
    main()
