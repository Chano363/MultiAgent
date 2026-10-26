# -*- coding: utf-8 -*-
"""
HHVCTS 多质点被控对象（论文式8-10）
- 3 列单元列车 x 3 质点（机车 + 2 个货车组），质点间距 250 m [T4]
- 机车：MPC 电牵引/电制动力（含式11/13 前馈补偿）+ 空气制动
- 货车组：仅空气制动，靠车钩由机车调节（论文 4.2 节叙述）
- 车钩：线性弹簧 γ(式10) + 缓冲器阻尼 [ASM]；可物理关闭（用户指令）
- 阻力：戴维斯基本阻力(式9) + 坡道附加阻力
- 扰动 w(i,j)：有界均匀分布（固定管压降空气制动/坡道匹配偏差，论文3.1节）
"""
import numpy as np
from params import (MASSES, DP_INTRA, GAMMA, CDAMP, COUPLER_ON, W_LIM_KN, G,
                    davis_w0, S_INIT, V_INIT, U_MIN, U_MAX)
from air_brake import AirBrake
from scenarios import gradient_permille

N_PER_GROUP = MASSES[1] / 100.0   # 26.92 等效 C80 辆数（质量精确对应）


class TrainPlant:
    """3 x 3 质点纵向动力学。s 增大方向为运行方向；同列车内头部质点 s 更大。
    车钩 k(0..5)：k=0,1 属于列车0 连接质点(0,1)(1,2)；k=2,3 列车1；k=4,5 列车2。
    F_c[k] = γ(s_p - s_q) + c(v_p - v_q)，p 在前、q 在后；拉为正：
    前质点受力 -F_c[k]，后质点受力 +F_c[k]。列车之间无物理车钩（虚拟编组）。"""

    def __init__(self, coupler_on=COUPLER_ON, seed=2026):
        self.coupler_on = coupler_on
        self.rng = np.random.default_rng(seed)
        self.m = np.tile(MASSES, 3)              # t, 9 点
        self.scenario = "gentle"
        self.brakes = [AirBrake(is_loco=(j == 0), d_hafe=0.0 if j == 0 else DP_INTRA * j)
                       for _i in range(3) for j in range(3)]
        self.s = S_INIT.copy()
        self.v = np.full(9, V_INIT)
        self.w = np.zeros(9)
        self.traction = np.zeros(3)
        self.u_hat = np.zeros(3)
        self.F_air = np.zeros(9)
        self.F_couple = np.zeros(6)

    def reset(self, scenario):
        self.scenario = scenario
        self.s = S_INIT.copy()
        self.v = np.full(9, V_INIT)
        for br in self.brakes:
            br.P = 0.0
            br.b_cmd = 0.0
            br.t_cmd = -1e9
        self.w = np.zeros(9)
        self.traction = np.zeros(3)
        self.u_hat = np.zeros(3)
        self.F_air = np.zeros(9)
        self.F_couple = np.zeros(6)

    def resample_disturbance(self):
        """每个 MPC 采样周期更新一次有界扰动 |w| <= W_LIM_KN kN（式52）"""
        self.w = self.rng.uniform(-W_LIM_KN, W_LIM_KN, size=9)

    def _coupler_idx(self, k):
        tr, c = divmod(k, 2)
        return tr * 3 + c, tr * 3 + c + 1

    def _coupler_forces_now(self):
        if not self.coupler_on:
            return np.zeros(6)
        return np.array([GAMMA * ((self.s[p] - self.s[q]) - DP_INTRA)
                         + CDAMP * (self.v[p] - self.v[q])
                         for k in range(6)
                         for p, q in [self._coupler_idx(k)]])

    def _ff_loco(self, i):
        """机车 i 前馈（式11/13）：+F_c(μ补偿) + 空气制动 + 基本阻力 + 坡道阻力"""
        p = i * 3
        grad = gradient_permille(self.s[p], self.scenario)
        return (self.F_couple[i * 2] + self.F_air[p]
                + self.m[p] * davis_w0(self.v[p])
                + self.m[p] * G * grad / 1000.0)

    def set_mpc_input(self, u_hat_norm):
        """记录各机车 MPC 归一化输出 û（m/s^2）；实际牵引 = û·m + 前馈(连续补偿)"""
        self.u_hat = np.asarray(u_hat_norm, dtype=float).copy()

    def set_brake_cmd(self, b_cmds, t_now):
        for k, br in enumerate(self.brakes):
            br.command(float(b_cmds[k]), t_now)

    def step(self, t_now, dt):
        """单步 RK4 积分。制动缸压强先更新（式1-2），其力在步内冻结；
        车钩力（弹簧+阻尼）随状态在 RK4 内更新。
        机车牵引 = û·m_loco + 前馈（式11/13 连续补偿：空气制动、车钩合力 μ、阻力），
        每积分子步刷新，保证误差模型解耦精度。"""
        for br in self.brakes:
            br.step(t_now, dt)
        F_air = self._air_forces().copy()
        self.F_couple = self._coupler_forces_now()
        tr = np.array([self.u_hat[i] * self.m[i * 3] + self._ff_loco(i)
                       for i in range(3)])
        # 物理约束（式25 U_min(v)）：制动力不能使列车倒行
        tr = np.maximum(tr, -self.m[[0, 3, 6]] * np.maximum(self.v[[0, 3, 6]],
                                                            0.0) / dt)
        tr = np.clip(tr, U_MIN, U_MAX)
        self.traction = tr.copy()
        w = self.w.copy()
        m = self.m
        g_on = self.coupler_on

        def coupler_f(s, v):
            if not g_on:
                return np.zeros(6)
            # 弹簧原长 = 初始质点间距（论文式10中 s 为相对平衡位置的偏差）
            return np.array([GAMMA * ((s[p] - s[q]) - DP_INTRA)
                             + CDAMP * (v[p] - v[q])
                             for k in range(6)
                             for p, q in [self._coupler_idx(k)]])

        def deriv(s, v):
            Fc = coupler_f(s, v)
            F = np.zeros(9)
            for i in range(3):
                for j in range(3):
                    p = i * 3 + j
                    f = tr[i] if j == 0 else 0.0
                    f -= F_air[p]
                    if j == 0:
                        f += -Fc[i * 2]
                    else:
                        f += Fc[i * 2 + j - 1] - (Fc[i * 2 + j] if j < 2 else 0.0)
                    f -= m[p] * davis_w0(v[p]) if v[p] >= 0.0 \
                        else -m[p] * davis_w0(-v[p])   # 阻力与速度反向（奇对称）
                    grad = gradient_permille(s[p], self.scenario)
                    f -= m[p] * G * grad / 1000.0
                    F[p] = f + w[p]
            return v, F / m                      # kN/t = m/s^2

        s0, v0 = self.s.copy(), self.v.copy()
        k1s, k1v = deriv(s0, v0)
        k2s, k2v = deriv(s0 + 0.5 * dt * k1s, v0 + 0.5 * dt * k1v)
        k3s, k3v = deriv(s0 + 0.5 * dt * k2s, v0 + 0.5 * dt * k2v)
        k4s, k4v = deriv(s0 + dt * k3s, v0 + dt * k3v)
        self.s = s0 + dt / 6.0 * (k1s + 2 * k2s + 2 * k3s + k4s)
        self.v = v0 + dt / 6.0 * (k1v + 2 * k2v + 2 * k3v + k4v)
        self.F_couple = coupler_f(self.s, self.v)
        self._air_forces()

    def _air_forces(self):
        for k, br in enumerate(self.brakes):
            if self.v[k] > 0.0:
                f = br.brake_force(self.v[k])
                if not br.is_loco:
                    f *= N_PER_GROUP             # 货车组等效多辆
            elif br.P > 1e-6:
                # 停车保持 [物理]：倒溜时全容量反向制动，接近静止后抵消坡道
                # 重力分量保持（受闸瓦容量限制）
                cap = br.brake_force(0.0) * (1.0 if br.is_loco else N_PER_GROUP)
                grad = gradient_permille(self.s[k], self.scenario)
                if self.v[k] < -0.05:
                    f = -cap
                else:
                    f = float(np.clip(-self.m[k] * G * grad / 1000.0,
                                      -cap, cap))
            else:
                f = 0.0
            self.F_air[k] = f
        return self.F_air
