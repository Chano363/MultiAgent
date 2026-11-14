# -*- coding: utf-8 -*-
"""Tube MPC 基线参数（主仓口径，ADR-042 两基线之一）。

逐项对齐关系见 `docs/knowledge/MPC_BASELINE_KNOWLEDGE_BASE.md` §6（2026-11-13 修订版）。
源：`zba` 分支 `MPC-baseline/song2026_tubempc/params.py`（Song2026 表 2/3/4 + 复现者 [ASM] 标注）。

口径纪律：
- 物理真值由主仓 `TrainDynamics` 保证；本文件只含 MPC **内部预测模型**的参数
  （MPC 内部模型允许简化，与真实 plant 的偏差进 tube 扰动界 W_LIM_KN——标准做法）。
- 忠实性优先：Song2026 给出数值的参数（表 2/3/4）原样保留；[ASM] 项注明。
"""
import numpy as np

# ---- 采样与预测（与主仓 decision_interval 完全一致，无需换算）----
DT_MPC = 1.0            # s  MPC 采样周期 δ（= decision_interval 10 × dt 0.1）
H_PRED = 5              # 步  预测时域（Song2026 表 3，T=5）

# ---- 质量（主仓 consist_10kt_1plus0/108：HXD3B 188 t + 108×100 t）----
M_LOCO = 188.0          # t  机车（zba=200 t HXD1 ⇒ 改主仓 HXD3B）
M_WAGON_GROUP = 5400.0   # t  货车组1 = 前 54 辆（54×100 t；与 zba 每列
                        #     "机车+2 质点货车组"结构对齐：zba 组=2 692 t/27 辆，
                        #     主仓同构组=5 400 t/54 辆——pair_A 的 ξ 与扰动界按此重算）

# ---- MPC 内部预测模型的 Davis 阻力系数（Song2026 表 3 原值）----
# 注意：主仓 `_resistance_forces` 是另一套（曲线 + 单位阻力）式；MPC 内部模型
# 保留 Song2026 形式（忠实性），模型-真值偏差由 W_LIM_KN 覆盖。
C0 = 0.0063
C1 = 1.08e-4
C2 = 1.4918e-5

# ---- 机车力边界（kN；zba=HXD1 760/−470 ⇒ 主仓 HXD3B 重算）----
# 牵引：40 km/h 功率限 0.85×9600/11.1 ≈ 734 kN，起步粘着 1 659 kN ⇒ 取运行段 760（量级一致）
# 电制动：60 km/h 功率限 0.85×9600/16.7 ≈ 489 kN ⇒ 取 490
U_MAX = 760.0           # kN  机车最大牵引力
U_MIN = -490.0          # kN  机车最大电制动力（负 = 制动）

# ---- 速度口径（75 km/h，ADR-068）----
V_LIM = 75.0 / 3.6      # m/s 速度带半宽对应的上界（zba=80/3.6 ⇒ 改 75）

# ---- tube / 终端设计 ----
Q_W = np.diag([0.5, 0.5])    # 运行状态误差权重 Q（2x2，表 3）
R_W = 0.1                    # 控制量权重（表 3）
P_W = np.diag([0.6, 0.4])    # 终端状态误差权重 P（2x2，表 3）
KAPPA = 1.0             # tube 反馈增益 κ（论文未给数值，zba [ASM]=1.0 保留）
W_LIM_KN = 1.0          # kN  每质点有界扰动（zba [ASM] 保留起步；MT-2 迟滞残余可后续上调）

# ---- 车内间距误差限（机车-货车组；zba = F_COUPLE_LIM/GAMMA = 1500/500 = 3 m）----
SE_COUPLE_LIM = 3.0     # m  车内误差约束 |s_e2| ≤ 此值 − 收紧量

# ---- 场景（主仓口径，ADR-068）----
D_DES = 1434.5          # m  期望头对头间距（= 车长 1294.06 + d_eff 138.5）
V_INIT = 60.0 / 3.6     # m/s 初始速度（60 km/h）
GAP_T_ADJ = 120.0       # s  间距误差 → 速度修正时间常数（zba v2 =120 保留）
GAP_V_ADJ = 1.5         # m/s 间距修正限幅（zba v2 =1.5 保留）

# ---- 执行层（文献[22] + zba v2 实测改进，照搬）----
ED_MAX = 0.8            # 文献[22] 式(2-25)：电制动输出率 p_d ∈ [0, 0.8]
ED_AIR_CAP = 0.2        # 空气制动已施加且接近参考速度时，电制动输出率上限
R_CYCLE = 50.0          # kPa 循环制动初减压量（文献[22]）
V_MIN_RELEASE = 40.0 / 3.6   # m/s 低于此强制缓解空气制动（文献式 2-26；
                        # 主仓 v_min=40 km/h，比 zba 的 30 更保守）
V_STATIC = 0.5          # m/s 静止/极低速阈值（车钩力由静态摩擦锁定）
SUB = 10                # ZOH 子步数（DT_MPC / DT_DYN = 1.0 / 0.1）
