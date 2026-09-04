"""
公平版 MPC 协同控制器（M-MPC baseline，替代简化线性 MPC / 阈值顾问式，2026-08-30）。

【定位】传统模型驱动优化基线（对标 Yang2025 多质点 MPC 范式 + 多列耦合），
与分层无模型 MARL（M-MARL）公平对比"无模型学习 vs 模型驱动在线优化"。

【为何用"直接加速度控制"而不用 coor 阈值顾问】
初始版本把 MPC 设计成输出 coor_adj（循环制动阈值偏移）喂给分层控制器——与 M1 同架构。
但冒烟发现：coor 只移动循环制动触发阈值 ±1.5km/h，而制动事件发生在分钟级，预测时域
（秒级）内根本"看不到"制动相位 → MPC 恒输出 0（退化为无协同），不公平地弱化传统方法。
传统 MPC 的真实形态是直接命令加速度（连续控制）——本实现回归该形态：MPC 直接给每列
目标加速度，列内低层（TrainLowLevelController + 车钩力 SafetyLayer）负责 throttle 映射，
与"分层 RL（规则循环制动+阈值协同）"对比。这正是论文想要的创新对比：
   M-MARL：分层 + 无模型策略（第1层规则循环制动控速 + 第2层 MAPPO 调阈值）
   M-MPC ：单层 + 模型预测（多列耦合预测 + 硬约束在线优化，直接控加速度）

【本实现（公平版）】
  1. 物理列模型预测：每列按 Davis 残差标定 + 坡度 + 加速度命令演化速度/位置/间距，
     列间通过前车位置耦合。
  2. 控制分块（control blocking）：时域分 B 块、每块常加速度 → 少量决策变量（B×n），
     使纯 Python SLSQP 在评估步长内可解。
  3. 显式硬约束（SLSQP ineq）：
       - 列间间距 gap(k) ≥ gap_min（追尾安全，多列耦合核心约束）
       - 车钩力代理 F_c(k) ≤ 1000 kN（由列间相对速度激发的纵向瞬态代理）
     —— 体现"传统方法依赖精确模型 + 在线求解约束"。
  4. 滚动时域：每控制步求 SLSQP，仅施加第 1 块的加速度。

【诚实的简化（论文如实声明）】
  - 列内不做 101 质点 Newmark 全耦合回归（优化器内跑不动），用聚合列模型 + 制动
    瞬态代理估计车钩力。
  - 车钩力的最终物理强制由环境 SafetyLayer 完成（M-MARL 与 M-MPC 完全相同）→ 公平，
    差异只在"控制器来源"。
  - 记录并报告每步求解耗时（工程复杂度 / 实时性叙事）。

用法（评估）：见 evaluate_m1_m3_long.py 的 'mpc_dir' 模式（hierarchical=False）。
"""
import time

import numpy as np
from scipy.optimize import minimize


class FairMPCController:
    """多列公平版 MPC：直接命令每列目标加速度，滚动时域带约束优化。"""

    def __init__(self, num_trains, dt=0.1, horizon_blocks=5, block_len=10,
                 v_max=80.0 / 3.6, v_min=40.0 / 3.6, max_accel=1.0,
                 grade_const=9.81, gap_min=20.0, lambda_gap=2.0, lambda_v=0.5,
                 lambda_u=0.02, lambda_j=0.5, coupler_force_limit_n=1.0e6,
                 headway_s=5.0, target_speed=60.0 / 3.6, enforce_coupler=True,
                 coupler_k=1000.0e3, accel_lo=-0.75, accel_hi=0.4,
                 grade_at=None, inner_rule_cyclic=False):
        self.num_trains = int(num_trains)
        self.dt = dt
        self.horizon_blocks = max(1, int(horizon_blocks))
        self.block_len = max(1, int(block_len))
        self.horizon_steps = self.horizon_blocks * self.block_len
        self.v_max = v_max
        self.v_min = v_min
        self.max_accel = max_accel
        self.grade_const = grade_const
        self.gap_min = gap_min
        self.lambda_gap = lambda_gap
        self.lambda_v = lambda_v
        self.lambda_u = lambda_u
        self.lambda_j = lambda_j
        self.coupler_force_limit_n = coupler_force_limit_n
        self.headway_s = headway_s
        self.target_speed = target_speed
        self.enforce_coupler = enforce_coupler
        self.coupler_k = coupler_k
        self.accel_lo = accel_lo
        self.accel_hi = accel_hi
        # 【2026-09-02 P2 公平基线】inner_rule_cyclic=True：MPC 仍直接输出目标加速度
        # （保留模型驱动在线优化本质），但每列动作先经规则循环制动内层做限速兜底
        # （超 v_max 强制制动、低于 v_min 缓解），与 M-MARL 的电空制动+规则控速同语义。
        # 意义：消解审稿人"fair-MPC 是 strawman（被剥掉工业 ATO 的规则内层）"质疑——
        # M-MPC-rule 与 M-MARL 一样具备"规则护盾 + 优化/学习外层"，对比才是 like-for-like。
        self.inner_rule_cyclic = inner_rule_cyclic
        # 前瞻坡度回调: grade_at(position_m) -> 无量纲坡度（‰/1000）。
        # 公平性关键: 真实 MPC 出厂前已掌握完整线路图纸，坡度剖面是先验已知，
        # 预测时必须沿预测位置查询真实坡度（而非恒定取前5车均值——那是对 MPC
        # 的不公平弱化，会把"模型精度"局限混进"MPC 结构性局限"）。
        self.grade_at = grade_at

        self._last_vel = np.zeros(self.num_trains)
        self._meas_accel = np.zeros(self.num_trains)
        self._last_cmd_accel = np.zeros(self.num_trains)
        self._gap0_init = np.full(self.num_trains, 1e9)
        self._gap_ref = 1e9
        self.solve_times = []

    # ------------------------------------------------------------------ 预测
    def _predict(self, v0, pos0, grade0, gap0, coupler0, U):
        """沿物理列模型预测: U shape (B, n) 常加速度(m/s²·倍率 max_accel)。

        pos0: 每列当前车头绝对位置(m)。预测用前瞻真实坡度（若 grade_at 已注入），
        否则回退 grade0 恒定（用前5车均值=每列平均坡度）。
        """
        n = self.num_trains
        B = self.horizon_blocks
        L = self.block_len
        H = self.horizon_steps
        V = np.zeros((H + 1, n)); P = np.zeros((H + 1, n))
        G = np.zeros((H + 1, n)); FC = np.zeros((H + 1, n))
        V[0] = v0; P[0] = pos0; G[0] = gap0; FC[0] = coupler0
        # 标定残差：使 k=0 的预测加速度与实测一致
        cmd0 = self._last_cmd_accel * self.max_accel
        b0 = self._meas_accel - (cmd0 + self.grade_const * self._grade_now(pos0, grade0))
        idx = 0
        for b in range(B):
            cmd = U[b] * self.max_accel
            for s in range(L):
                # 前瞻坡度（沿预测位置实时查询）；无 grade_at 时回退恒定 grade0
                gr = self._grade_now(P[idx], grade0)
                a = cmd + self.grade_const * gr + b0
                V[idx + 1] = np.clip(V[idx] + a * self.dt, self.v_min * 0.9, self.v_max * 1.03)
                P[idx + 1] = P[idx] + V[idx] * self.dt
                for i in range(1, n):
                    G[idx + 1, i] = G[idx, i] + (V[idx, i - 1] - V[idx, i]) * self.dt
                G[idx + 1, 0] = G[idx, 0]
                FC[idx + 1] = FC[idx]
                if self.enforce_coupler and n > 1:
                    # 车钩力代理：列间相对速度激发的纵向瞬态
                    for i in range(1, n):
                        rel = abs(V[idx, i] - V[idx, i - 1])
                        add = self.coupler_k * rel * self.dt
                        FC[idx + 1, i] = min(coupler0[i] + add, 2.5 * self.coupler_force_limit_n)
                idx += 1
        return V, G, FC

    def _grade_now(self, pos, grade0):
        """返回 pos（形状 (n,) 位置数组）对应的坡度数组。

        - 若注入了 grade_at 回调：沿整列车头位置前瞻真实坡度（公平 MPC 掌握线路图纸）。
        - 否则回退恒定 grade0（各列当前前5车平均坡度），保证默认行为向后兼容。
        """
        n = self.num_trains
        pos = np.atleast_1d(np.asarray(pos, dtype=float))
        if self.grade_at is not None:
            return np.array([self.grade_at(float(p)) for p in pos], dtype=float)
        return np.broadcast_to(np.asarray(grade0, dtype=float), (n,)).copy()

    # ------------------------------------------------------------------ 接口
    def compute_actions_from_env(self, env, obs=None) -> np.ndarray:
        """从环境读状态，求解每列目标加速度 action ∈ [-1,1]（施加第 1 块）。"""
        n = self.num_trains
        v0 = np.array([tr.dynamics.vel[0] for tr in env.trains], dtype=float)
        # 实测加速度（速度差分标定；首步兜底）
        if np.all(self._last_vel == 0):
            measured = np.zeros(n)
        else:
            measured = (v0 - self._last_vel) / max(self.dt, 1e-6)
        self._meas_accel = np.clip(measured, -1.5, 1.5)
        # 公平 MPC：注入完整线路坡度图纸（先验已知），沿预测位置前瞻查询真实坡度。
        # 若环境暴露了 grade_profile 名，重建同一剖面；否则维持用户注入的 grade_at。
        if self.grade_at is None and getattr(env, 'grade_profile', None):
            from src.train_dynamics.grade_profile import PROFILES
            prof_name = env.grade_profile
            if prof_name in PROFILES:
                self.grade_at = PROFILES[prof_name]().grade_at
        pos0 = np.array([float(env._train_heads[i]) for i in range(n)], dtype=float)
        grade0 = np.array([np.mean(tr.dynamics.grade[:5]) for tr in env.trains], dtype=float)
        coupler0 = np.array([float(np.max(np.abs(tr.dynamics._coupler_forces())))
                             if tr.num_vehicles else 0.0 for tr in env.trains], dtype=float)
        gap_ref = env._dynamic_gap()
        gap0 = np.full(n, gap_ref)
        for i in range(1, n):
            gap0[i] = env.trains[i - 1].dynamics.pos[-1] - env._train_heads[i]

        self._gap0_init = gap0
        self._gap_ref = gap_ref

        t0 = time.perf_counter()
        B = self.horizon_blocks
        nv = n * B
        mid = (self.v_min + self.v_max) / 2.0

        def cost(z):
            U = np.clip(z, self.accel_lo, self.accel_hi).reshape(B, n)
            V, G, FC = self._predict(v0, pos0, grade0, gap0, coupler0, U)
            c = 0.0
            c += self.lambda_gap * np.sum((G[1:, 1:] - gap_ref) ** 2)
            a_norm = self.v_max - self.v_min
            c += self.lambda_v * np.sum(((V[1:] - mid) / a_norm) ** 2)
            c += self.lambda_u * np.sum(U ** 2)
            # 控制平滑（相邻块之间，jerk 代理 → 车钩力/舒适性）
            if B > 1:
                c += self.lambda_j * np.sum((U[1:] - U[:-1]) ** 2)
            return c

        def ineq(z):
            U = np.clip(z, self.accel_lo, self.accel_hi).reshape(B, n)
            V, G, FC = self._predict(v0, pos0, grade0, gap0, coupler0, U)
            cons = []
            if n > 1:
                cons += list((G[1:, 1:] - self.gap_min).flatten())
            if self.enforce_coupler and n > 0:
                cons += list((self.coupler_force_limit_n - FC[1:]).flatten())
            return np.array(cons)

        z0 = np.zeros(nv)
        bounds = [(self.accel_lo, self.accel_hi)] * nv
        res = minimize(cost, z0, method='SLSQP', bounds=bounds,
                       constraints={'type': 'ineq', 'fun': ineq},
                       options={'maxiter': 90, 'ftol': 1e-3})
        U = np.clip(res.x, self.accel_lo, self.accel_hi).reshape(B, n)
        self.solve_times.append(time.perf_counter() - t0)
        self._last_cmd_accel = U[0]
        self._last_vel = v0.copy()

        # 【2026-09-02 P2 公平基线】规则循环制动内层兜底：MPC 目标加速度先经限速规则
        # 修偏（与 M-MARL 的电空制动规则语义一致）。不动 MPC 的优化本质，只在
        # MPC 决策之上叠加"规则护盾"，使其具备工业 ATO 的纵向控速保障。
        # 【2026-09-03 修复】原实现只处理 v≥v_max（超上限强制制动），低40 分支为 pass
        # → MPC 持续制动导致速度崩溃到下限以下（低40 53.7%，与 M-MARL 语义不一致）。
        # 补全：v≤v_min 时强制解除制动/恢复牵引（action ≥ 0），与规则循环制动
        # "低于下限 → 缓解/牵引"语义对齐。
        a_out = U[0].copy()
        if self.inner_rule_cyclic:
            for i in range(n):
                v_i = v0[i]
                if v_i >= self.v_max:
                    # 超上限 → 强制制动（SERVICE 档 brake_notch=-0.75）：若 MPC 给定
                    # 牵引/惰行（≥0）则压到 -0.75，若 MPC 已给更果断的制动则保持其值。
                    a_out[i] = min(a_out[i], -0.75)
                elif v_i <= self.v_min:
                    # 【2026-09-03 修复】低于下限 → 强制恢复牵引/缓解（≥0，
                    # 模拟司机缓解再充风），防止 MPC 短视制动把速度压到下限之下。
                    a_out[i] = max(a_out[i], 0.0)
        return a_out  # 第 1 块 = 当前步每列 action ∈ [-1,1]

    # 兼容旧统一接口（hierarchical=False 的评估里不用 obs/accels/gaps）
    def compute_actions(self, obs, speeds, accels, gaps, env=None) -> np.ndarray:
        return self.compute_actions_from_env(env, obs)

    def reset(self):
        self._last_vel = np.zeros(self.num_trains)
        self._meas_accel = np.zeros(self.num_trains)
        self._last_cmd_accel = np.zeros(self.num_trains)
        self._gap0_init = np.full(self.num_trains, 1e9)
        self._gap_ref = 1e9
        self.solve_times = []

    def __repr__(self):
        return (f"FairMPCController(B={self.horizon_blocks}×{self.block_len}步, "
                f"gap_min={self.gap_min}m, coupler={self.enforce_coupler}, "
                f"inner_rule_cyclic={self.inner_rule_cyclic})")