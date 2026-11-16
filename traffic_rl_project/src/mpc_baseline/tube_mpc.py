# -*- coding: utf-8 -*-
"""Tube-MPC 求解器（自 zba 分支 song2026_tubempc 忠实移植，算法逐行保真）。

源文件：`traffic_rl_zba/MPC-baseline/song2026_tubempc/tube_mpc.py`（146 行）。
仅改动：import 路径（`src.mpc_baseline.params`）；算法、注释、数值全部保留。

论文对应（Song2026 式号，与 zba 注释一致）：
- 误差状态 x(i,j)=[s_e, v_e]（式 15-18）；机车 i 增广 x_i=[s_e1,v_e1,s_e2,v_e2]：
  (1) 对参考轨迹（列车 1 为目标曲线，列车 2/3 为前车实际状态 − 期望间距，式 20）；
  (2) 机车-货车组相对误差。
- 解耦：车钩力补偿器 μ（式 13）经前馈在对象端实现；残余项入有界扰动 w
- 名义模型（式 37/39，欧拉离散）：Ad=[[1,δ],[0,1+ξδ]], Bd=[0,δ]ᵀ
  已知量（参考加速度 a_ref、货车组空气制动等效加速度 d2）按式 11 精神进入名义预测
- 代价（式 21-23）：Σ x'Qx + R û² + 终端 x'Px；终端权重 P 取表 3 diag(0.6,0.4)
- 终端增益 K_f = -(R+Bd'PBd)⁻¹Bd'PAd（式 60）；终端约束集 X_f={x: K_f x ∈ Ū}（式 59）
- Tube 反馈（式 48）：û = û* + K z，K=[0,κ]；鲁棒不变集 Ω（式 49/54/55）
- 约束收紧（定理 2）：Ū=[Umin+κε, Umax-κε]（式 56），状态约束收紧 ε（式 57）
- 决策变量：机车归一化控制输入 û = u_MPC/m_loco（m/s²，B=[0,∓1]ᵀ）
"""
import numpy as np
from scipy.optimize import minimize
from src.mpc_baseline.params import (H_PRED, Q_W, P_W, R_W, KAPPA, W_LIM_KN,
                                     DT_MPC, U_MIN, U_MAX, M_LOCO, C1, C2,
                                     C0, V_LIM, SE_COUPLE_LIM, M_WAGON_GROUP)

BLK = np.zeros((2, 2))


def pair_A(m_follow, v0=18.0):
    """连续误差动力学 A=[[0,1],[0,ξ]]，ξ=-(c1+2c2 v0)/m_follow（式 19）"""
    xi = -(C1 + 2 * C2 * v0) / m_follow
    return np.array([[0.0, 1.0], [0.0, xi]]), xi


class TubeMPC:
    """单台机车的 Tube-MPC（4 状态增广、单输入归一化 û）"""

    def __init__(self, idx, m_loco=M_LOCO, m_wagon=M_WAGON_GROUP,
                 H=H_PRED, Q=Q_W, Pw=P_W, R=R_W, kappa=KAPPA,
                 eta=None, delta=DT_MPC, u_min=U_MIN, u_max=U_MAX,
                 se_lim=SE_COUPLE_LIM, terminal="table"):
        self.idx = idx
        self.H, self.delta = H, delta
        # 扰动上界 η：|w|<=W_LIM_KN 折算到机车归一化加速度（m/s^2）
        eta = W_LIM_KN / m_loco if eta is None else eta
        self.Q4 = np.block([[Q, BLK], [BLK, Q]])
        self.P4 = np.block([[Pw, BLK], [BLK, Pw]])
        self.R = R
        self.kappa = kappa
        self.u_min_n = u_min / m_loco
        self.u_max_n = u_max / m_loco
        self.se_lim = se_lim
        self.m_loco = m_loco
        A1, xi1 = pair_A(m_loco)
        A2, xi2 = pair_A(m_wagon)
        Ac = np.block([[A1, BLK], [BLK, A2]])
        self.Ad = np.eye(4) + Ac * delta
        self.Bd = np.array([0.0, -1.0, 0.0, 1.0]) * delta
        self.xi = min(xi1, xi2)
        # Tube（式 54/55）：ε_v = η/(κ-ξ)，ε_s = ηHδ/(κ-ξ)
        self.eps_v = eta / (kappa - self.xi)
        self.eps_s = eta * H * delta / (kappa - self.xi)
        # 终端设计（式 60，P 取表 3；terminal="dare" 时按式 61）
        if terminal == "dare":
            from scipy.linalg import solve_discrete_are
            self.P4 = solve_discrete_are(self.Ad, self.Bd, self.Q4, self.R)
        self.Kf = -(self.Bd @ self.P4 @ self.Ad) / (
            self.R + self.Bd @ self.P4 @ self.Bd)          # 1x4（式 60）
        self.du_tight = kappa * self.eps_v          # 式 56 输入收紧
        self._build_condensed()
        self.xbar = np.zeros(4)                     # 名义状态

    def _build_condensed(self):
        H, Ad, Bd, nx = self.H, self.Ad, self.Bd, 4
        Psi = np.zeros((nx * H, nx))
        Gam = np.zeros((nx * H, H))
        for k in range(H):
            Psi[k * nx:(k + 1) * nx] = np.linalg.matrix_power(Ad, k + 1)
            for j in range(k + 1):
                Gam[k * nx:(k + 1) * nx, j] = np.linalg.matrix_power(
                    Ad, k - j) @ Bd
        self.Psi, self.Gam = Psi, Gam
        Qs = np.kron(np.eye(H), self.Q4)
        Qs[-nx:, -nx:] = Qs[-nx:, -nx:] - self.Q4 + self.P4   # 末端 P
        self.Qs = Qs
        self.Hmat = 2.0 * (Gam.T @ Qs @ Gam + self.R * np.eye(H))
        rows_v1 = [k * nx + 1 for k in range(H)]
        rows_s2 = [k * nx + 2 for k in range(H)]
        self.M_v1, self.M_s2 = Gam[rows_v1], Gam[rows_s2]
        self.p_v1, self.p_s2 = Psi[rows_v1], Psi[rows_s2]
        self.r_v1 = np.array(rows_v1)
        self.r_s2 = np.array(rows_s2)

    def known_vector(self, a_ref, d2):
        """已知输入（参考加速度/货车组空气制动等效加速度）的凝聚预测项"""
        e = np.array([0.0, a_ref, 0.0, d2]) * self.delta
        D = np.zeros(4 * self.H)
        acc = np.zeros(4)
        for k in range(self.H):
            acc = self.Ad @ acc + e
            D[k * 4:(k + 1) * 4] = acc
        return D

    def solve(self, x0, v_ref0, a_ref, d2):
        """求解名义最优问题（式 40-45）。返回 (û*_0, 名义轨迹终点)"""
        D = self.known_vector(a_ref, d2)
        base_v1 = self.p_v1 @ x0 + D[self.r_v1]
        base_s2 = self.p_s2 @ x0 + D[self.r_s2]
        lo_v1 = v_ref0 - V_LIM + self.eps_v
        hi_v1 = v_ref0 - self.eps_v
        se_b = self.se_lim - self.eps_s
        PsiD = self.Psi @ x0 + D

        def cost(U):
            X = PsiD + self.Gam @ U
            return float(U @ (self.Hmat / 2.0) @ U
                         + (2 * self.Gam.T @ self.Qs @ PsiD) @ U)

        cons = [
            dict(type="ineq", fun=lambda U: self.M_v1 @ U + base_v1 - lo_v1),
            dict(type="ineq", fun=lambda U: hi_v1 - (self.M_v1 @ U + base_v1)),
            dict(type="ineq", fun=lambda U: self.M_s2 @ U + base_s2 + se_b),
            dict(type="ineq", fun=lambda U: se_b - (self.M_s2 @ U + base_s2)),
            dict(type="ineq",
                 fun=lambda U: self._terminal_g(U, PsiD)),
        ]
        res = minimize(cost, np.zeros(self.H), method="SLSQP", constraints=cons,
                       bounds=[(self.u_min_n + self.du_tight,
                                self.u_max_n - self.du_tight)] * self.H,
                       options=dict(maxiter=60, ftol=1e-10))
        U = res.x if res.x is not None else np.zeros(self.H)
        return float(U[0])

    def _terminal_g(self, U, PsiD):
        """终端约束 K_f x_N ∈ [Umin+κ ε, Umax-κ ε]（式 56/59）"""
        xH = PsiD[-4:] + self.Gam[-4:] @ U
        kf_x = float(self.Kf @ xH)
        return np.array([kf_x - (self.u_min_n + self.du_tight),
                         (self.u_max_n - self.du_tight) - kf_x])

    def nominal_step(self, xbar, u_nom, a_ref, d2):
        """名义系统传播（式 37/39）"""
        e = np.array([0.0, a_ref, 0.0, d2]) * self.delta
        return self.Ad @ xbar + self.Bd * u_nom + e

    def drag_const(self, m, grad_permille):
        """(c0 + c2 v0²)m + 坡道阻力：式 11 中被前馈补偿的常数阻力项（kN）"""
        v0 = 18.0
        return m * (C0 + C2 * v0 * v0) + m * 9.81 * grad_permille / 1000.0
