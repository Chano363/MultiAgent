# -*- coding: utf-8 -*-
"""
Song2026 Tube-MPC × 朔黄线真实线路 × multi-agent-main 仿真器 复现运行器

被控对象：d:\\Z\\first station\\multi-agent-main.zip 内 traffic_rl_project 的
    TrainDynamics（NeTrainSim 牵引力 + 牵规法空气制动（制动波传播/缸压上升/
    缓解排气）+ MT-2 迟滞车钩 + Davis 阻力 + Newmark-β 积分）——物理层不改一行。
线路：仿真器内置真实数据
    - 纵断面 PROFILES['shuozhou_real_53km']（58 段实测坡段，全长 53.5 km，
      取自 reference/simulation/data_line/line_grade.xlsx 真实线路数据）
    - 限速 SHUOZHOU_REAL_SPEED_LIMIT（同源 speed_limit.xlsx，7 段；49.527 km 处
      由 75 km/h 跳变为 45 km/h——即用户所称"49.6 km"实为该限速突变点）
    注：压缩包内该条真实线路全长 53.5 km（非 49.6 km），本复现按内置真实剖面运行。
编组：论文表4 的 3 列单元列车（每列 1 台 HXD1 + 54 辆 C80 ≈ 5600 t，论文 5584 t），
    头对头间距 D_des = 2000 m、初速取入线处真实目标速度（论文表3/4 为 18 m/s），
    列间无物理车钩（虚拟耦合）。
控制器：论文 Tube-MPC（tube_mpc.py 原样复用，一行不改），采样周期 δ=1 s：
    - 机车1 跟踪目标曲线：v_t(s) = 真实限速经反向制动(a_dec=0.08)与正向牵引
      (a_acc=0.15)双向扫描得到的目标速度，按位置查表（含限速预览）
    - 机车2/3：v_ref = min(v_t(s_self), v_lead + 间距修正)，间距修正限幅 ±1.5 m/s；
      即"跟随前车速度以保持定距 + 不超本车限速"
    - 列间安全包络（ETCS 式）：v_allow = sqrt(v_lead² + 2 a_eb 净空)，超限时钳制 û≤0
    - 误差状态 x=[0, v_e1, s_e2, v_e2]（列间间距由 v_ref 律承担，位置误差置零）
    - 前馈（式11/13）：机车牵引指令 = û·m_loco − 机车非牵引合力（仿真器实测
      车钩合力/空气制动/阻力/坡道力），力→手柄按功率限幅反解
    - [ASM] 低速域适配规则：|v|<0.5 m/s 时车钩力由 MT-2 静态摩擦锁定，属约束力
      而非载荷，不纳入前馈（否则静止时 1.1 MN 锁死力会把 û 顶成纯电制动，
      见 §首轮卡死诊断）
监督级空气制动（文献[22] 循环制动模型，即论文参考文献[22]）：
    二进制 u_b∈{0,1}，施加时为固定 50 kPa 初制动减压量（SERVICE + reduction_kpa=50，
    制动波从第 1 节货车发出），缓解时排气至 0；两次施加之间强制满足最短充风时间
    T_AI（54 辆编组按 180×54/216 折算为 45 s），对应式(2-27)；机车只用电制动，
    由 Tube-MPC 连续调节。
用户指令消融：--coupler off 时把每列车全部车钩 CouplerParams 物理置零
    （刚度/预压/摩擦/限位=0，车辆互不传力），控制器与指令完全不变。

运行：python shuohuang_sim.py [--coupler on|off|both] [--steps 3600]
输出：outputs_shuohuang/sim_shuohuang_coupler_<on|off>.csv + summary_shuohuang.txt
"""
import argparse
import csv
import os
import sys
import time

import numpy as np

import params as P
from tube_mpc import TubeMPC

# ---- 接入 zip 仿真器（物理底座，不修改其任何代码） ----
SIM_ROOT = r"d:\Z\first station\multi-agent-main\traffic_rl_project"
if SIM_ROOT not in sys.path:
    sys.path.insert(0, SIM_ROOT)

from src.train_dynamics.train import TrainDynamics                       # noqa: E402
from src.train_dynamics.params import (TrainConsist, LocomotiveParams,   # noqa: E402
                                       VehicleParams, CouplerParams)
from src.train_dynamics.grade_profile import (PROFILES,                  # noqa: E402
                                              SHUOZHOU_REAL_SPEED_LIMIT)
from src.train_dynamics.braking import AirBrakeNotch, electric_brake_force_n  # noqa: E402
from src.train_dynamics.tractive import tractive_force                   # noqa: E402

DT_MPC = P.DT_MPC          # 1.0 s（论文采样周期 δ）
DT_DYN = 0.1               # 仿真器控制步（内部自动 0.01 s 物理子步）
SUB = int(round(DT_MPC / DT_DYN))

N_WAGON = 54                          # 每列货车数（54×100t+200t=5600t≈论文5584t）
GA = (1, 27)                          # 货车组1 = 第1..27辆（≈论文质点(i,2)，2692t≈2700t）
GB = (28, 54)                         # 货车组2 = 第28..54辆（≈论文质点(i,3)）
D_DES = P.D_DES                       # 2000 m 头对头期望间距（论文表3）
S_HEAD0 = 10000.0                     # 机车1初始头部位置（论文表4 口径）
S_END = 51800.0                       # 头车到达该里程结束（覆盖真实限速 45km/h 区段）

OUT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                       "outputs_shuohuang")
os.makedirs(OUT_DIR, exist_ok=True)


def make_consist():
    """论文编组映射到仿真器：HXD1（8轴 200t，表3/4）+ 54×C80（100t, 12.1m）。"""
    loco = LocomotiveParams(
        mass_t=200.0, no_of_axles=8, frontal_area_m2=11.5, drag_coef=1.4,
        length_m=35.3, max_power_kw=9600.0, transmission_efficiency=0.85,
        max_speed_mps=33.3, n_notches=8,
    )
    car = VehicleParams(mass_t=100.0, no_of_axles=4, frontal_area_m2=10.0,
                        drag_coef=1.0, length_m=12.1)
    return TrainConsist([loco] + [car] * N_WAGON)


def zero_coupler():
    """物理层面关掉车钩力：全部阻抗项置零（刚度/预压/摩擦/行程限位）。"""
    return CouplerParams(stiffness=0.0, preload_n=0.0, friction_n=0.0,
                         friction_static_n=0.0, friction_v_er=0.0,
                         max_impulse_n=0.0, stroke_m=1e9, rigid_stiffness_nm=0.0)


def linear_spring_coupler(gamma_npm=500_000.0):
    """物理层纯线性弹簧车钩（论文式10 的被控对象假设）。

    设置策略（对照仿真器 _coupler_forces 代码路径）：
      stiffness = γ  →  F = stiffness · Δs
      preload_n = 0, friction_* = 0  →  无预压、无库仑/静态摩擦
      unload_stiffness_ratio = 1.0   →  卸载刚度=加载刚度，无迟滞软化
      max_impulse_n = 1e12           →  不封顶
      stroke_m = 1e9, rigid_stiffness_nm = 0  →  无行程限位、无刚性接触
      coupler_gap_m = 1e-9           →  无游隙，直接接触（tanh 平滑函数的最小正参数）
    这样 _coupler_forces() 自然退化为 F ≈ γ · Δs，和论文式(10) F_C = γ (s_p − s_q) 完全一致。
    注意：γ=500 kN/m 比 MT-2 默认刚度 2e7 N/m 软 40 倍，且无摩擦阻尼，
    物理上会出现更大的车钩相对位移甚至振荡——这是线性弹簧假设的预期行为，不是 bug。
    """
    return CouplerParams(
        stiffness=gamma_npm,
        preload_n=0.0,
        friction_n=0.0,
        friction_static_n=0.0,
        friction_v_er=0.0,
        max_impulse_n=1e12,
        stroke_m=1e9,
        rigid_stiffness_nm=0.0,
        coupler_gap_m=1e-9,
        unload_stiffness_ratio=1.0,
    )


def make_train(coupler_model, head_pos, v_init, profile):
    """coupler_model ∈ {'mt2', 'linear', 'zero'}：
       mt2      = 仿真器默认 MT-2 迟滞车钩（物理层原样，一行未改）
       linear   = 纯线性弹簧（γ=500 kN/m，论文式10 对象假设）
       zero     = 全部车钩阻抗置零（物理层消融）"""
    dyn = TrainDynamics(make_consist(), dt=DT_DYN, simcase="official")
    if coupler_model == "linear":
        dyn.set_couplers([linear_spring_coupler() for _ in range(dyn.num_vehicles - 1)])
    elif coupler_model == "zero":
        dyn.set_couplers([zero_coupler() for _ in range(dyn.num_vehicles - 1)])
    # 'mt2'：不调 set_couplers，用仿真器默认齐次 MT-2
    dyn.set_grade_profile(profile)
    fl = float(CouplerParams().free_length_m)
    pos = head_pos - np.arange(dyn.num_vehicles) * fl
    dyn.set_initial(pos=pos, vel=np.full(dyn.num_vehicles, float(v_init)))
    return dyn


A_DEC = 0.08       # m/s^2  [ASM] 目标曲线反向制动约束的服务减速度（整定：由 0.12
                   #         调缓至 0.08，提前施划更长、更平缓的减速段）
A_ACC = 0.15       # m/s^2  [ASM] 目标曲线正向牵引约束（限速阶跃上升时的加速度
                   #         上限；全列最大牵引 760 kN/5600 t≈0.136 m/s^2）
DS_TBL = 10.0      # m      目标速度曲线抽样间隔


def target_speed_curve(line_len=53600.0):
    """真实限速 + 反向制动/正向牵引约束的目标速度曲线 v_t(s) (m/s)。

    [ASM] 真实限速表在 49.527 km 处由 75 直接跳变为 45 km/h，若按阶跃跟踪会
    触发剧烈制动（正是首轮卡死的诱因）。实际 ATO/司机在限速突变前即按制动
    曲线提前减速，故对限速做一次反向扫描：
        v_t(s) = min( v_lim(s), sqrt(v_t(s+ds)^2 + 2*a_dec*ds) )
    限速上升（如 30 km 处 60→75 km/h）同理需要正向牵引约束，否则参考速度在
    一个采样内跳变 15 km/h，前馈加速度 a_ref 会瞬间达到 4.16 m/s^2，MPC 会
    误以为参考在猛加速而持续给牵引（实测跟随车超速至 82.9 km/h）：
        v_t(s) = min( v_t(s), sqrt(v_t(s-ds)^2 + 2*a_acc*ds) )
    """
    n_s = int(line_len / DS_TBL) + 2
    v = np.array([min(SHUOZHOU_REAL_SPEED_LIMIT.limit_at(i * DS_TBL), 80.0) / 3.6
                  for i in range(n_s)])
    for i in range(n_s - 2, -1, -1):
        v[i] = min(v[i], np.sqrt(v[i + 1] ** 2 + 2.0 * A_DEC * DS_TBL))
    for i in range(1, n_s):
        v[i] = min(v[i], np.sqrt(v[i - 1] ** 2 + 2.0 * A_ACC * DS_TBL))
    return v


# ---- 监督级循环空气制动（文献[22] 3.3 节，论文参考文献[22]） ----
R_CYCLE = 50.0     # kPa  初制动减压量（文献[22] 仅考虑 50 kPa 的初制动减压）
T_AI = P.T_AI      # s    最短充风时间（54 辆编组按 180×54/216 折算为 45 s）
DV_APPLY = P.DV_APPLY      # m/s 高于参考速度该值即施加
DV_RELEASE = P.DV_RELEASE  # m/s 低于参考速度该值即缓解
ED_MAX = 0.8       # 文献[22] 式(2-25)：电制动输出率 p_d ∈ [0, 0.8]
V_RELEASE_MIN = 30.0 / 3.6   # m/s 文献[22] 式(2-26)：最低缓解速度 v_min^r，
                             # 低于该速度强制缓解空气制动（万吨列车规程值）
V_REL_LEAD = 0.0   # m/s 缓解提前量。实测设为 2.0 时，在大坡道段空气制动提前
                   # 释放、而 T_AI 又禁止立即重施，导致连续循环制动力不足、超速至
                   # 92 km/h，故不采用；改由"电制动条件限幅"抑制减速超调
ED_AIR_CAP = 0.2   # 空气制动已施加且车速已接近/低于参考速度时，电制动输出率
                   # 上限（分工仲裁：避免空气制动 + 满电制动叠加造成近停车）
# 列间安全包络（P0 兜底，扩展项）：ETCS 式速度监督
A_EB = 0.15        # m/s² 安全制动包络所依据的保守可用减速度
D_MIN = 150.0      # m    静态最小间隔
# 跟随车间距调节律参数（扩展项）
T_ADJ = 120.0      # s  间距误差 -> 速度修正的时间常数
V_ADJ = 1.5        # m/s 间距修正速度限幅（与 v_t 取小，不会造成超速）


def cyclic_brake(dyn, v_ref, state, t_now):
    """文献[22] 循环制动：二进制施加/缓解 + 最短充风时间约束（式2-27）。

    - u_b∈{0,1}：施加时为固定 50 kPa 减压量，缓解时排气至 0，无比例档；
    - 缓解后必须经过 T_AI 才能再次施加（保证列车管充满，否则制动力逐次衰减）；
    - 式(2-26)：v ≤ v_min^r 时强制缓解，抑制减速超调（本线 45 km/h 限速段
      此前被压到 1.3 km/h 的直接原因）；
    - 电制动由 Tube-MPC 连续调节，承担空气制动以外的调节量。
    """
    v = dyn.vel[0]
    if v <= V_RELEASE_MIN:                 # 最低缓解速度：强制缓解
        if state["applied"]:
            state["applied"] = False
            state["t_rel"] = t_now
        return False
    if state["applied"]:
        if v <= v_ref - DV_RELEASE:
            state["applied"] = False
            state["t_rel"] = t_now
    else:
        if v >= v_ref + DV_APPLY and (t_now - state["t_rel"]) >= T_AI:
            state["applied"] = True
    return state["applied"]


# ---- ATP 硬限速层（扩展项）：以线路原始限速为监督目标的速度防护 ----
# 由最终运行 CSV 反解得到的精确制动律（残差 0）：
#     b = 22.222 + 27.778 · Δv[km/h]  ⇒  b = 50 + 100·(Δv[m/s] − 1/3.6) kPa
# 即超速 1 km/h 起触发常用制动，每超 1 m/s 增加 100 kPa，上限 170 kPa。
ATP_DV_ON = 1.0 / 3.6     # m/s  触发阈值 = 超速 1 km/h
ATP_DV_OFF = 0.5          # m/s  缓解阈值（低于监督速度 0.5 m/s）
ATP_B_BASE = 50.0         # kPa  最小常用制动减压量
ATP_B_GAIN = 100.0        # kPa  每 1 m/s 超速对应的减压量增量
ATP_B_MAX = 170.0         # kPa  减压量上限（常用制动全制动位）


def atp_brake(dyn, v_sup, state, t_now):
    """ATP 硬限速监督：返回 (applied, b_kpa)。

    - v_sup 为线路原始限速（= v_t(s) 的上包络，最大值恰等于 speed_limit 表值）；
    - 超速 ≥ 1 km/h 触发常用制动，减压量随超速线性增加，上限 170 kPa；
    - 低于 v_sup − 0.5 m/s 缓解，排气至 0；
    - 缓解后须经 T_AI 才能再次施加（与循环制动共用同一充风时间约束）；
    - v ≤ v_min^r 时强制缓解（式2-26），避免低速被 ATP 压停。
    """
    v = dyn.vel[0]
    if v <= V_RELEASE_MIN:
        if state["applied"]:
            state["applied"] = False
            state["t_rel"] = t_now
        return False, 0.0
    dv = v - v_sup
    if state["applied"]:
        if dv <= -ATP_DV_OFF:
            state["applied"] = False
            state["t_rel"] = t_now
    else:
        if dv >= ATP_DV_ON and (t_now - state["t_rel"]) >= T_AI:
            state["applied"] = True
    if not state["applied"]:
        return False, 0.0
    b = ATP_B_BASE + ATP_B_GAIN * (dv - ATP_DV_ON)
    return True, float(np.clip(b, ATP_B_BASE, ATP_B_MAX))


def safety_envelope(dyn, lead, l_train):
    """以前车尾端为监督目标，按保守可用减速度反推允许速度：
        v_allow = sqrt( v_lead^2 + 2 a_eb max(净空 - D_min, 0) )
    净空 <= D_min 时 v_allow = v_lead，此时间距导数 = v_lead - v >= 0，
    即间距不再缩小，数学上排除穿越。
    """
    clearance = (lead.pos[0] - l_train) - dyn.pos[0]
    v_lead = max(lead.vel[0], 0.0)
    room = max(clearance - D_MIN, 0.0)
    return float(np.sqrt(v_lead * v_lead + 2.0 * A_EB * room))


V_STATIC = 0.5     # m/s  [ASM] 静止/极低速阈值：此处车钩力由静态摩擦锁定，
                   #            属约束力而非载荷，不作为前馈补偿（首轮卡死根因）


def loco_force_command(dyn, u_hat, ed_cap=ED_MAX):
    """式11/13 前馈 + û·m_loco -> 机车牵引/电制动手柄（力->手柄按功率反解）。

    ed_cap：电制动输出率上限。空气制动施加期间取 ED_AIR_CAP，避免空气制动与
    满电制动同时作用造成近停车（49.5 km 限速段的实测问题）。
    """
    v_abs = abs(dyn.vel[0])
    cpl = 0.0 if v_abs < V_STATIC else dyn._coupler_forces()[0]
    f_non = (dyn._air_braking_forces()[0] - dyn._resistance_forces()[0]
             + dyn._grade_forces()[0] + cpl)
    u_n = u_hat * P.M_LOCO * 1000.0 - f_non           # 期望机车净牵引力 (N)
    v = max(v_abs, 0.5)
    loco = dyn.consist.vehicles[0]
    if u_n >= 0.0:
        f_max = tractive_force(loco.max_power_kw, loco.transmission_efficiency,
                               1.0, v, loco.mass_t)
        throttle = float(np.clip(u_n / max(f_max, 1.0), 0.0, 1.0))
        ed = 0.0
    else:
        f_ed = electric_brake_force_n(loco.mass_t, v, 1.0, loco.max_power_kw,
                                      loco.transmission_efficiency)
        ed = float(np.clip(-u_n / max(f_ed, 1.0), 0.0, ed_cap))
        throttle = 0.0
    return throttle, ed


def grp_mean(dyn, a, b, field="vel"):
    return float(np.mean(getattr(dyn, field)[a:b + 1]))


def run(coupler_model, out_tag, n_steps=3600, verbose=True,
        s_head0=S_HEAD0, s_end=S_END, atp=False):
    """coupler_model ∈ {'mt2', 'linear', 'zero'} 三种物理层车钩假设：
       mt2      = 仿真器默认 MT-2 迟滞车钩（刚度 2e7 N/m + 预压 + 库仑/静态摩擦 + 限位）
       linear   = 纯线性弹簧（γ=500 kN/m，论文式10 被控对象假设）
       zero     = 全部车钩阻抗置零（物理层消融）
    控制器 Tube-MPC 代码与 γ=500 kN/m 前馈补偿项在三种假设下均保持不变，仅物理层替换。
    s_head0/s_end：头车起止里程，默认 10 km→51.8 km；跑满宁武西→北大牛
    49.527 km 站间区段时取 1932 m→51459 m（见 docs 车站索引 sheet3）。
    atp=True：以线路原始限速（v_sup）为监督目标，超速即施加常用制动（ATP 硬限速层），
    取代文献[22] 的循环制动触发律。"""
    profile = PROFILES["shuozhou_real_53km"]()
    v_t = target_speed_curve()
    v_init = float(v_t[int(np.clip(s_head0 / DS_TBL, 0, len(v_t) - 1))])
    dyns = [make_train(coupler_model, s_head0 - D_DES * i, v_init, profile)
            for i in range(3)]
    mpcs = [TubeMPC(idx=i, m_wagon=P.M_WAGON_GROUP,
                    se_lim=P.F_COUPLE_LIM / P.GAMMA) for i in range(3)]
    xbar = [np.zeros(4) for _ in range(3)]
    b_state = [dict(applied=False, t_rel=-1e9) for _ in range(3)]  # 循环制动状态

    v_head_prev = np.array([d.vel[0] for d in dyns])   # 前车加速度差分用
    v_ga_prev = np.array([grp_mean(d, *GA) for d in dyns])  # d2 差分用
    # 名义内车间距（机车->货车组1中心）：论文 250 m 对应论文表4初始几何；
    # 真实编组下取仿真器实际初始几何（连续车辆），控制器量测"相对名义的偏差"不变
    dyn_intra0 = np.array([d.pos[0] - grp_mean(d, *GA, "pos") for d in dyns])
    # 列车物理长度（头端->尾端），用于列间安全包络的净空计算
    l_train = (dyns[0].num_vehicles - 1) * float(CouplerParams().free_length_m) \
        + 12.1

    keys = ["t", "s_head", "v_head", "v_ga", "thr", "ed", "b", "uhat",
            "fc_peak", "v_sup", "atp", "s_ref0", "v_ref0"]
    log = {k: [] for k in keys}          # 每个键 = 每步一行（3 列车向量/标量）
    t0 = time.time()
    solve_ms = []
    for k in range(n_steps):
        cmds = []
        row = {k: [] for k in keys}
        for i, dyn in enumerate(dyns):
            # ---- 参考与误差状态（论文式15-20） ----
            v_allow = np.inf
            if i == 0:
                # 头车：按"位置"查目标速度曲线，而非按时间积分的参考轨迹。
                # 若沿时间积分成位置参考，任何累积速度偏差都变成恒定位置偏差
                # （实测下坡段超速 7 km/h 累积成 ~570 m 领先量），MPC 会为
                # "追平位置"在 49.5 km 处硬刹至停车；且时间索引参考在列车
                # 提前抵达 45 km/h 区段时仍给出高速度，造成 7.9 km/h 超速。
                # 位置索引天然具备限速预览能力。
                s_ref = dyn.pos[0]
                j_now = int(np.clip(dyn.pos[0] / DS_TBL, 0, len(v_t) - 1))
                j_nxt = int(np.clip(
                    (dyn.pos[0] + dyn.vel[0] * DT_MPC) / DS_TBL, 0, len(v_t) - 1))
                v_ref = float(v_t[j_now])
                v_sup = float(v_t[j_now])          # ATP 监督目标 = 本车位置目标速度
                a_ref = float((v_t[j_nxt] - v_t[j_now]) / DT_MPC)
            else:
                s_ref = dyns[i - 1].pos[0] - D_DES
                # 跟随车参考（论文式20 + 扩展项）：论文直接跟踪前车实测速度，
                # 这在限速空间变化时正是保持定距所必需的——前车 2 km 外进入
                # 45 km/h 区段时，跟随车若仍按本车位置的目标速度跑 75 km/h，
                # 两者速度差会让间距在 ~100 s 内被吃掉 500 m（实测 2000→1372 m）。
                # 故取
                #     v_ref = min( v_t(s_self), v_lead + clip((gap-D_des)/T_ADJ) )
                # 既跟随前车缩小/恢复间距，又绝不超过本车位置处的线路目标速度
                # （正修正曾被顶到 89.5 km/h，故必须与 v_t 取小）。
                j_prev = int(np.clip(dyn.pos[0] / DS_TBL, 0, len(v_t) - 1))
                gap_now = dyns[i - 1].pos[0] - dyn.pos[0]
                v_lead = max(float(dyns[i - 1].vel[0]), 0.0)
                corr = float(np.clip((gap_now - D_DES) / T_ADJ, -V_ADJ, V_ADJ))
                v_ref = min(float(v_t[j_prev]), v_lead + corr)
                v_sup = float(v_t[j_prev])         # 本车位置处的监督速度
                a_ref = float((v_lead - v_head_prev[i - 1]) / DT_MPC)
                # 列间安全包络（P0）：以前车尾端为目标反推允许速度
                v_allow = safety_envelope(dyn, dyns[i - 1], l_train)
                if v_ref > v_allow:
                    v_ref = v_allow
            v_ga = grp_mean(dyn, *GA)
            # 列间间距完全由跟随车的 v_ref 调节律承担。若再把位置误差送入
            # MPC，其代价权重 0.5·s_e² 会在"间距偏大"时持续要求牵引，把跟随车
            # 顶到本车线路目标速度以上（实测 60 km/h 区段超速至 68.4 km/h）；
            # 而式(10)(15) 的一阶线性化也只在平衡点附近有效。故位置误差项取零，
            # MPC 只负责速度跟踪 + 机车/货车组耦合状态。
            s_err = 0.0
            x0 = np.array([s_err,
                           v_ref - dyn.vel[0],
                           dyn.pos[0] - grp_mean(dyn, *GA, "pos")
                           - dyn_intra0[i],
                           dyn.vel[0] - v_ga])
            d2 = float(-(v_ga - v_ga_prev[i]) / DT_MPC)   # 式19 量测实现
            xbar[i] = x0                                  # 步骤1：x̄(tk) := x(tk)
            ts = time.time()
            u_star = mpcs[i].solve(x0, v_ref, a_ref, d2)
            solve_ms.append((time.time() - ts) * 1000.0)
            z = x0 - xbar[i]
            u_hat = u_star + P.KAPPA * (z[1] - z[3])      # 式48 Tube 反馈
            if dyn.vel[0] > v_allow:                      # 安全包络生效时不得加速
                u_hat = min(u_hat, 0.0)
            if atp:
                # ATP 硬限速层：监督目标为线路原始限速，减压量随超速线性增加
                b_app, b = atp_brake(dyn, v_sup, b_state[i], k * DT_MPC)
            else:
                # 文献[22] 循环制动：以 v_ref 为速度带中心，固定 50 kPa
                b_app = cyclic_brake(dyn, v_ref, b_state[i], k * DT_MPC)
                b = R_CYCLE if b_app else 0.0      # 减压量 kPa（0 / 50）
            thr, ed = loco_force_command(
                dyn, u_hat,
                ED_AIR_CAP if (b_app and dyn.vel[0] < v_ref + 0.3) else ED_MAX)
            cmds.append((dyn, thr, ed, b_app, u_hat, b))
            row["t"].append(k * DT_MPC + DT_MPC)
            row["s_head"].append(dyn.pos[0])
            row["v_head"].append(dyn.vel[0])
            row["v_ga"].append(v_ga)
            row["thr"].append(thr)
            row["ed"].append(ed)
            row["b"].append(b)
            row["uhat"].append(float(u_hat))
            fc = np.abs(dyn.coupler_interface_forces())
            row["fc_peak"].append(float(fc.max()) / 1e3 if fc.size else 0.0)
            row["v_sup"].append(float(v_sup))
            row["atp"].append(1.0 if b_app else 0.0)
            row["s_ref0"].append(s_ref)
            row["v_ref0"].append(v_ref)
        for k_ in keys:
            log[k_].append(row[k_])
        v_head_prev = np.array([d.vel[0] for d in dyns])
        v_ga_prev = np.array([grp_mean(d, *GA) for d in dyns])
        # ---- 保持指令 1 s（ZOH，论文 δ 采样） ----
        for _ in range(SUB):
            for dyn, thr, ed, b_app, _u, b in cmds:
                thr_arr = np.zeros(dyn.num_vehicles)
                ed_arr = np.zeros(dyn.num_vehicles)
                thr_arr[0], ed_arr[0] = thr, ed
                if b_app:        # 施加：减压量 b（循环制动=50 kPa，ATP=50~170 kPa）
                    dyn.step_vehicles_ed_ab(
                        thr_arr, ed_arr, AirBrakeNotch.SERVICE, brake_origin=1,
                        reduction_kpa=b)
                else:
                    dyn.step_vehicles_ed_ab(
                        thr_arr, ed_arr, AirBrakeNotch.RELEASE, brake_origin=1)
        if verbose and k % 300 == 0:
            print(f"  [{out_tag}] t={k * DT_MPC:6.0f}s "
                  f"s0={dyns[0].pos[0]/1000:6.2f}km v0={dyns[0].vel[0]*3.6:5.1f}"
                  f"km/h b={[('50kPa' if c[3] else '0') for c in cmds]}")
        if not np.isfinite(dyns[0].vel).all() or dyns[0].vel[0] * 3.6 > 110:
            print(f"  [{out_tag}] 异常终止 t={k * DT_MPC:.0f}s")
            break
        if dyns[0].pos[0] >= s_end:
            if verbose:
                print(f"  [{out_tag}] 头车到达 {s_end/1000:.1f} km，提前结束")
            break

    # 截断日志为实际步数
    n = min(len(v) for v in log.values())
    log = {k: np.array(v[:n]) for k, v in log.items()}
    sol = np.array(solve_ms)
    out = dict(
        v_err=np.zeros((n, 3)), s_err=np.zeros((n, 3)))
    for kk in range(n):
        out["v_err"][kk, 0] = abs(log["v_ref0"][kk, 0] - log["v_head"][kk, 0])
        out["s_err"][kk, 0] = abs(log["s_ref0"][kk, 0] - log["s_head"][kk, 0])
        for i in (1, 2):
            out["v_err"][kk, i] = abs(log["v_head"][kk, i - 1]
                                      - log["v_head"][kk, i])
            out["s_err"][kk, i] = abs(log["s_head"][kk, i - 1] - D_DES
                                      - log["s_head"][kk, i])
    summary = dict(
        tag=out_tag, coupler_model=coupler_model, steps=n,
        t_end=float(log["t"][-1, 0]), dist_km=float(log["s_head"][-1, 0] / 1000),
        v_err_max=np.maximum(out["v_err"], 0).max(axis=0),
        s_err_max=out["s_err"].max(axis=0),
        v_err_avg=float(out["v_err"].max(axis=0).mean()),
        s_err_avg=float(out["s_err"].max(axis=0).mean()),
        fc_peak_kN=[float(log["fc_peak"][:, i].max()) for i in range(3)],
        gap_min_head=float((log["s_head"][:, :-1] - log["s_head"][:, 1:])
                           .min()),
        v_max_kmh=float(log["v_head"].max() * 3.6),
        v_min_kmh=float(log["v_head"].min() * 3.6),
        energy_kwh=[float(d.energy_kwh) for d in dyns],
        solve_ms_mean=float(sol.mean()) if sol.size else 0.0,
        solve_ms_p95=float(np.percentile(sol, 95)) if sol.size else 0.0,
        wall_s=time.time() - t0,
    )
    if verbose:
        print(f"[{out_tag}] done: {n} MPC 步, 壁钟 {summary['wall_s']:.0f}s")
    return log, summary


def save_csv(log, path):
    n = len(log["t"])
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["t"] + [f"s_head{i}" for i in range(3)]
                   + [f"v_head{i}" for i in range(3)]
                   + [f"v_ga{i}" for i in range(3)]
                   + [f"thr{i}" for i in range(3)] + [f"ed{i}" for i in range(3)]
                   + [f"b{i}" for i in range(3)] + [f"uhat{i}" for i in range(3)]
                   + [f"fc_peak{i}" for i in range(3)]
                   + [f"v_sup{i}" for i in range(3)] + [f"atp{i}" for i in range(3)]
                   + ["s_ref0", "v_ref0"])
        for kk in range(n):
            row = [float(log["t"][kk, 0])] + list(log["s_head"][kk]) \
                + list(log["v_head"][kk]) \
                + list(log["v_ga"][kk]) + list(log["thr"][kk]) + list(log["ed"][kk]) \
                + list(log["b"][kk]) + list(log["uhat"][kk]) \
                + list(log["fc_peak"][kk]) + list(log["v_sup"][kk]) \
                + list(log["atp"][kk]) + [float(log["s_ref0"][kk, 0]),
                                          float(log["v_ref0"][kk, 0])]
            w.writerow([f"{x:.4f}" for x in row])


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--coupler", default="both",
                    choices=["on", "off", "both", "mt2", "linear", "zero", "all"])
    ap.add_argument("--steps", type=int, default=3600)
    ap.add_argument("--s0", type=float, default=S_HEAD0,
                    help="头车初始里程 (m)，跑宁武西→北大牛取 1932")
    ap.add_argument("--s-end", dest="s_end", type=float, default=S_END,
                    help="头车终止里程 (m)，北大牛站取 51459")
    ap.add_argument("--tag-suffix", default="", help="输出文件名后缀，如 _49km")
    ap.add_argument("--atp", action="store_true",
                    help="启用 ATP 硬限速层（监督目标=线路原始限速，减压量随超速"
                         "线性增加至 170 kPa），替代文献[22] 循环制动触发律")
    args = ap.parse_args()
    # 把旧 on/off/both 映射到新的 mt2/zero/[mt2,zero]，同时支持 linear 和 all
    old_map = {"on": "mt2", "off": "zero", "mt2": "mt2",
               "zero": "zero", "linear": "linear"}
    if args.coupler == "both":
        cfgs = [("mt2", "mt2"), ("zero", "zero")]
    elif args.coupler == "all":
        cfgs = [("mt2", "mt2"), ("linear", "linear"), ("zero", "zero")]
    else:
        m = old_map[args.coupler]
        cfgs = [(m, m)]

    MODEL_NAME = {"mt2": "MT-2 迟滞车钩（真实对象）",
                  "linear": "纯线性弹簧（γ=500 kN/m，论文式10）",
                  "zero": "全部阻抗置零（物理层消融）"}
    print("=" * 72)
    print("Song2026 Tube-MPC × 朔黄线真实线路(53.5km) × multi-agent 仿真器")
    print("物理层三种车钩假设：MT-2迟滞 / 线性弹簧 / 全部置零")
    print("控制器 Tube-MPC 代码与 γ=500 kN/m 前馈补偿在三组下均不变")
    print(f"监督级：{'ATP 硬限速（原始限速，50~170 kPa 比例减压）' if args.atp else '文献[22] 循环制动（50 kPa 二进制）'}")
    print("=" * 72)
    summaries = []
    suffix = args.tag_suffix
    if args.atp and "_atp" not in suffix:
        suffix += "_atp"
    for tag, mdl in cfgs:
        out_tag = f"shuohuang_coupler_{tag}{suffix}"
        log, m = run(mdl, out_tag, n_steps=args.steps,
                     s_head0=args.s0, s_end=args.s_end, atp=args.atp)
        save_csv(log, os.path.join(OUT_DIR, f"sim_{out_tag}.csv"))
        summaries.append(m)
        print(f"\n--- {out_tag}  [{MODEL_NAME[mdl]}] ---")
        print(f"机车最大速度误差 [1,2,3] (m/s): {np.round(m['v_err_max'], 3)}"
              f"  平均 {m['v_err_avg']:.3f}")
        print(f"机车最大间距误差 [1,2,3] (m)  : {np.round(m['s_err_max'], 1)}"
              f"  平均 {m['s_err_avg']:.1f}")
        print(f"车钩力峰值/列 (kN): {[f'{x:.0f}' for x in m['fc_peak_kN']]}"
              f" | 头车间距最小值 {m['gap_min_head']:.0f} m")
        print(f"速度范围 [{m['v_min_kmh']:.1f}, {m['v_max_kmh']:.1f}] km/h"
              f" | 里程 {m['dist_km']:.1f} km | SLSQP mean/p95"
              f" {m['solve_ms_mean']:.0f}/{m['solve_ms_p95']:.0f} ms")
    with open(os.path.join(OUT_DIR, "summary_shuohuang.txt"), "w",
              encoding="utf-8") as f:
        for m in summaries:
            f.write(f"{m['tag']}: steps={m['steps']} dist={m['dist_km']:.1f}km "
                    f"v_err_avg={m['v_err_avg']:.3f} s_err_avg={m['s_err_avg']:.1f} "
                    f"fc_peak={[f'{x:.0f}' for x in m['fc_peak_kN']]} "
                    f"gap_min={m['gap_min_head']:.0f} "
                    f"v_max={m['v_max_kmh']:.1f} v_min={m['v_min_kmh']:.1f}\n")
    print(f"\n结果已保存至 {OUT_DIR}")


if __name__ == "__main__":
    main()
