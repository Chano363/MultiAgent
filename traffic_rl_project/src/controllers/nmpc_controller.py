"""
多体 NMPC 成熟对比基线（`NMPCController`，casadi + IPOPT，2026-09-17）。

> **术语（统一口径，勿再混用）**：本文件说的"多体"= **集中质量(lumped)多体** ——
> 每列车离散成 `n_lump` 个质量块，块间以 MT-2 缓冲器等效耦合；**不是**逐车（~101 节）
> 全耦合多体。

【定位】本项目**唯一** MPC 对比基线【ADR-022，2026-10-01：旧的 agg/SLSQP `FairMPCController`
与简化 `MPCController` 已删除；导师口径"不要留粗糙 MPC 当靶子"，目标是 MARL 效果达到与
成熟 MPC 相当】。相对已删除那版的升级：

  1. **预测模型 = 列内集中质量(lumped)多体 + MT-2 车钩**（替代已删除那版的单质点聚合列
     + 虚构车钩力代理）：
     每列车 lump 成 nLump 个质量块（机车 1 块 + 货车按车数加权分块），块间用 MT-2
     等效（预压 + 刚度 + 摩擦 + 间隙死区 + 行程饱和，符号化）耦合；车钩力为预测
     状态变量，约束 ≤1000kN 进优化器（"MPC 需精确动力学模型"痛点的体现）。
  2. **求解器 = casadi + IPOPT**（非线性规划，替代 SLSQP 短视界）。
  3. **终端代价**（末端速度带 + 间距误差，缓解"终端约束器不好设计"）。
  4. **Regime A 公平标定**：grade_at 前瞻（每线重喂剖面图纸）+ b0 在线差分标定。

【控制结构】与 D-RL 同构（用户决策）：规则循环制动内层 + 安全层不动，NMPC 只替换
"RL 调制"部分——决策变量 = 每机车 ED 调制 [ed_mod]∈[-1,1]（>0 制动、<0 牵引），
control blocking（B 块 × 每块常值），预测时 ED 力仅施加于机车块；输出第 1 块调制
经规则内层兜底后映射为**每列目标加速度** `(num_trains,)`。
⚠️ 该输出由 `evaluate_decompose.mpc_act` 桥接成 decompose 通道的**加性调制**
`[ed_mod, ab_mod]`（反解 `ed_mod=(desired_ed−baseline_ed)/0.5`，见该函数与 ADR-022 备注）；
`mpc_act` 已**不再**经 `get_action_accel`（那会把绝对 ED 当调制，量纲错配）。

【对比指标】solve_times 记录每步求解耗时（同档对冲主指标之一：MPC 求解成本 vs
MARL 推理恒定）；车钩力/ATP 触发/列距由评估脚本统一落 metadata JSON。
"""
import time

import casadi as ca
import numpy as np


class NMPCController:
    """多列多体 NMPC：每机车 ED 调制，滚动时域带多体预测 + 硬约束优化。"""

    def __init__(
        self,
        num_trains: int,
        dt: float = 0.1,
        n_lump: int = 4,
        horizon_blocks: int = 5,
        block_len: int = 10,
        v_max: float = 80.0 / 3.6,
        v_min: float = 40.0 / 3.6,
        max_accel: float = 1.0,
        grade_const: float = 9.81,
        gap_min: float = 20.0,
        lambda_gap: float = 2.0,
        lambda_v: float = 0.5,
        lambda_u: float = 0.02,
        lambda_j: float = 0.5,
        lambda_term: float = 1.0,
        coupler_force_limit_n: float = 1.0e6,
        target_gap: float = 100.0,
        headway_s: float = 5.0,
        target_speed: float = 60.0 / 3.6,
        coupler_params=None,
        accel_lo: float = -0.75,
        accel_hi: float = 0.4,
        grade_at=None,
        inner_rule_cyclic: bool = True,
        ipopt_max_iter: int = 300,
        ipopt_tol: float = 1e-4,
    ):
        self.num_trains = int(num_trains)
        self.dt = dt
        self.n_lump = max(3, int(n_lump))          # 每列车 lump 质量块数（≥3）
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
        self.lambda_term = lambda_term
        self.coupler_force_limit_n = coupler_force_limit_n
        self.target_gap = target_gap
        self.headway_s = headway_s
        self.target_speed = target_speed
        self.coupler_params = coupler_params
        self.accel_lo = accel_lo
        self.accel_hi = accel_hi
        self.grade_at = grade_at
        self.inner_rule_cyclic = inner_rule_cyclic
        self.ipopt_max_iter = ipopt_max_iter
        self.ipopt_tol = ipopt_tol

        # 每列机车块索引：编组 1+1 = 头机车(块0) + 尾机车(块 nLump-1)。
        # 由第一次 compute_actions_from_env 从 env 动态读取（兼容任意机车数）。
        self._loco_blocks = None        # list[list[int]] per train
        self._n_loco_total = 0
        self._block_mass_kg = None      # (n, nLump) 每块质量
        self._block_area = None         # (n, nLump) Davis 聚合迎风面积
        self._block_cd = None           # (n, nLump) Davis 聚合阻力系数
        self._block_spacing_m = None    # (n,) 块间参考间距（lump 化后）
        self._loco_mass_kg = None       # (n, nLump) 每块机车质量（ED 力仅乘此；非机车块=0）
        self._n_coup_chain = None       # (n,) 块间等效串联车钩数（lump 车钩刚度/间隙/行程按此缩放）

        # casadi 符号问题（懒构建一次，滚动时域参数化复用）
        self._opti = None
        self._x = None                  # 决策变量 (B, nLoco)
        self._p_init = None             # 参数：初始状态 (pos/vel per block)
        self._p_gap_ref = None          # 参数：目标列距
        self._p_grade = None            # 参数：每块坡度快照 (n, nLump)（符号化前瞻）
        self._prev_sol = None           # 热启动初值

        self._meas_accel = np.zeros(self.num_trains)
        self._last_vel = np.zeros(self.num_trains)
        self._last_cmd = np.zeros(self.num_trains)
        self.solve_times = []
        self.solve_statuses = []      # 每步求解状态（'optimal' / 'fail:...'，评估侧统计失败率）

    # ------------------------------------------------------------------ #
    # 编组信息（从 env 读取：质量 / 机车块 / Davis 聚合）
    # ------------------------------------------------------------------ #
    def _read_consist(self, env):
        """从 env 每列 TrainConsist 读取 lump 质量分配与机车块索引。"""
        n = self.num_trains
        nL = self.n_lump
        masses = np.zeros((n, nL))
        areas = np.zeros((n, nL))
        cds = np.zeros((n, nL))
        loco_mass = np.zeros((n, nL))
        loco_blocks = []
        total_loco = 0
        spacing = np.zeros(n)
        n_chain = np.zeros(n)
        for ti, tr in enumerate(env.trains):
            dyn = tr.dynamics
            consist = dyn.consist
            nv = consist.num_vehicles
            mass_t = np.array([v.mass_t for v in consist.vehicles], dtype=float)
            areas_v = np.array([v.frontal_area_m2 for v in consist.vehicles], dtype=float)
            cds_v = np.array([v.drag_coef for v in consist.vehicles], dtype=float)
            loco_idx = np.array(consist.locomotive_indices, dtype=int)
            # 块分配：按车辆索引均分到 nL 块（覆盖全部块，勿漏最后一块）
            block_of = np.minimum(np.floor(np.arange(nv) * nL / nv), nL - 1).astype(int)
            for b in range(nL):
                sel = block_of == b
                masses[ti, b] = float(mass_t[sel].sum()) if np.any(sel) else 0.0
                areas[ti, b] = float(areas_v[sel].sum()) if np.any(sel) else 0.0
                cds[ti, b] = float(cds_v[sel].sum()) if np.any(sel) else 0.0
            # 每块机车质量（ED 力只乘机车质量，不乘整块质量）
            for i in loco_idx:
                loco_mass[ti, int(block_of[i])] += float(mass_t[i])
            # 机车块：机车索引所在块（去重、保序）
            lb = sorted({int(block_of[i]) for i in loco_idx})
            if not lb:  # 无机车 → 全列 ED 退化为块0（防御）
                lb = [0]
            loco_blocks.append(lb)
            total_loco += len(lb)
            train_len = float(abs(dyn.pos[0] - dyn.pos[-1])) if nv > 1 else 100.0
            spacing[ti] = train_len / max(nL - 1, 1)
            n_chain[ti] = max(nv / max(nL - 1, 1), 1.0)   # 块间等效串联车钩数
        self._block_mass_kg = masses * 1000.0          # t → kg
        self._block_area = areas
        self._block_cd = cds
        self._block_spacing_m = spacing
        self._loco_mass_kg = loco_mass * 1000.0
        self._n_coup_chain = n_chain
        self._loco_blocks = loco_blocks
        self._n_loco_total = total_loco

    # ------------------------------------------------------------------ #
    # MT-2 车钩力符号化（块间等效）
    # ------------------------------------------------------------------ #
    def _coupler_force_sym(self, s, dv):
        """块间车钩力（MT-2 等效，符号化；块间 = n_chain 个真实车钩串联）。

        s: 块间伸长量（正=拉伸，m）；dv: 相对速度（前块 - 后块，m/s）。
        串联等效：刚度 k/n_chain（更软）、间隙/行程 ×n_chain（分摊位移），
        预压/摩擦/饱和力不变（串联弹簧力相同）——否则 lump 模型对纵向冲击"虚刚"，
        车钩力约束被毫米级伸长瞬间违反，求解不可行。
        保留：预压 F0 + 弹性刚度 k·s_eff + 库仑摩擦 μ·tanh(dv) + 间隙死区 + 行程饱和。
        """
        cp = self.coupler_params
        n_chain = ca.DM(self._n_coup_chain.reshape(-1, 1))     # (n,1)
        gap = float(cp.coupler_gap_m) * n_chain
        stroke = float(cp.stroke_m) * n_chain
        k = float(cp.stiffness) / n_chain
        f0 = float(cp.preload_n)
        fric = float(cp.friction_n)
        # 【2026-10-11】plant 侧速度法已把 friction_v_eps 收窄到 0.002（sign(Δv)），
        # 但本符号代理要进 IPOPT：过窄的 tanh 陡梯度（dv≈0 处斜率 ~fric/ε）会让
        # NLP 求解卡顿/抖振。代理本就是光滑近似（非 plant 精确复刻），保留下限
        # 0.05 = 维持既有 NMPC 基线行为不随 plant 参数漂移（对比可比性）。
        v_eps = max(float(cp.friction_v_eps), 0.05)
        # 间隙死区：|s|<=gap 弹性项为 0（平滑近似）
        abs_s = ca.sqrt(s * s + 1e-8)
        s_eff = ca.fmax(0.0, abs_s - gap) * ca.tanh(s / (gap + 1e-6))
        # 弹性 + 预压（按拉伸/压缩方向）+ 摩擦（tanh 平滑方向）
        F = k * s_eff + f0 * ca.tanh(s / (gap + 1e-6)) + fric * ca.tanh(dv / v_eps)
        # 行程硬饱和（缓冲器打满后力剧增）
        over = ca.fmax(0.0, abs_s - stroke)
        F = F + float(cp.rigid_stiffness_nm) * over * ca.tanh(s / (gap + 1e-6))
        # 不做 fmin/fmax 硬饱和：饱和区导数平坦会困死 IPOPT（局部不可行陷阱），
        # 限界由车钩力硬约束（±1000kN）承担，表达式保持处处光滑。
        return F

    # ------------------------------------------------------------------ #
    # casadi 符号问题构建（懒构建一次，参数化滚动）
    # ------------------------------------------------------------------ #
    def _build_opti(self):
        n = self.num_trains
        nL = self.n_lump
        B = self.horizon_blocks
        L = self.block_len
        H = self.horizon_steps
        nLoco = self._n_loco_total

        opti = ca.Opti()
        # 决策变量：每机车 ED 调制 [ed_mod]∈[-1,1]，control blocking
        X = opti.variable(B, nLoco)
        opti.subject_to(opti.bounded(-1.0, X, 1.0))
        # 参数：初始状态（逻辑布局 (train, block)）。⚠ 勿用 1D 参数 + reshape：
        # casadi reshape 列主序填充，与 numpy row-major ravel 不匹配会把块位置打乱。
        p_pos0 = opti.parameter(n, nL)
        p_vel0 = opti.parameter(n, nL)
        p_gap_ref = opti.parameter()
        p_grade = opti.parameter(n, nL)   # 每块坡度快照（无量纲）

        pos0 = p_pos0
        vel0 = p_vel0

        # ---- 预测（显式欧拉，块间 MT-2 耦合） ----
        # 状态序列：pos[k]/vel[k] 为 (n, nL) MX 表达式，k=0..H
        pos = [pos0]
        vel = [vel0]
        # 每块 ED 力：机车块 = ed_mod × max_accel × loco_mass；非机车块 = 0
        mass = ca.DM(self._block_mass_kg)          # (n, nL) kg
        loco_mass = ca.DM(self._loco_mass_kg)      # (n, nL) 每块机车质量 kg（ED 力用）
        area = ca.DM(self._block_area)
        cd = ca.DM(self._block_cd)
        spacing = ca.DM(self._block_spacing_m.reshape(n, 1))  # (n,1)
        loco_map = np.full((n, nL), -1, dtype=int)  # 机车块 → 全局 loco 列索引；-1 = 非机车块
        gi = 0
        for ti, lb in enumerate(self._loco_blocks):
            for b in lb:
                loco_map[ti, b] = gi
                gi += 1

        for b in range(B):
            for s in range(L):
                p = pos[-1]
                v = vel[-1]
                # 块间伸长量（同列相邻块）：s_{i,k} = pos_{i,k} - pos_{i,k+1} - spacing
                rel = p[:, :-1] - p[:, 1:] - ca.repmat(spacing, 1, nL - 1)   # (n, nL-1)
                relv = v[:, :-1] - v[:, 1:]
                F_c = self._coupler_force_sym(rel, relv)                     # (n, nL-1)
                # 车钩力对首/尾块作用：块 k 受 F_c[:,k-1] - F_c[:,k]
                F_c_pad = ca.horzcat(ca.DM.zeros(n, 1), F_c)                 # 左侧
                F_c_next = ca.horzcat(F_c, ca.DM.zeros(n, 1))                # 右侧
                F_c_net = F_c_pad - F_c_next                                 # (n, nL)
                # ED 命令（每块一列）：机车块取该块对应全局机车列的调制 X[b,j]；非机车块 = 0
                ed_cols = []
                for k in range(nL):
                    ed_cols.append(ca.vertcat(*[
                        X[b, int(loco_map[ti, k])] if int(loco_map[ti, k]) >= 0 else ca.DM.zeros(1)
                        for ti in range(n)
                    ]))
                ed_cmd = ca.horzcat(*ed_cols)   # (n, nL)
                # ED 制动力（ed_mod>0 制动、<0 牵引）：仅乘机车质量（物理：ED 只作用于机车）
                F_ed = -ed_cmd * self.max_accel * loco_mass
                # Davis 阻力（每块聚合：0.0018*C*A*v²，独立于车重）
                R = 0.0018 * cd * area * (v * v)
                # 坡度力：正=上坡阻力（向后），负=下坡助力（向前）
                # （grade 约定正=上坡、负=下坡，故取 -mass*g*grade）
                F_g = -mass * self.grade_const * p_grade
                F = F_ed - R + F_g + F_c_net
                a = F / ca.fmax(mass, 1e-6)
                v_new = ca.fmin(ca.fmax(v + a * self.dt, 0.0), 2.0 * self.v_max)
                p_new = p + v_new * self.dt
                pos.append(p_new)
                vel.append(v_new)

        # ---- 目标函数 ----
        gap_ref = p_gap_ref
        mid = (self.v_min + self.v_max) / 2.0
        a_norm = self.v_max - self.v_min
        cost = 0.0
        for k in range(1, H + 1):
            # 速度带（所有块）
            cost += self.lambda_v * ca.sumsqr((vel[k] - mid) / a_norm) / nL
            # 列距（前列尾车 vs 后列头车，正 = 安全间距）。
            # ⚠ 符号：编队中 head 递减（后列在前列后方），故 gap = 前列尾 - 后列头；
            #   block 中心 ≈ 车位置 − 0.5·sp，两端车位置各 +0.5·sp 抵消 → 直接用块中心差。
            for i in range(1, n):
                gap_i = pos[k][i - 1, -1] - pos[k][i, 0]
                cost += self.lambda_gap * (gap_i - gap_ref) ** 2
        # 控制量 + jerk（块间平滑）
        cost += self.lambda_u * ca.sumsqr(X)
        if B > 1:
            cost += self.lambda_j * ca.sumsqr(X[1:] - X[:-1])
        # 终端代价（末端速度带 + 列距）——缓解"终端约束器不好设计"
        cost += self.lambda_term * (ca.sumsqr((vel[H] - mid) / a_norm) / nL)
        for i in range(1, n):
            gap_term = pos[H][i - 1, -1] - pos[H][i, 0]
            cost += self.lambda_term * (gap_term - gap_ref) ** 2
        opti.minimize(cost)

        # ---- 约束 ----
        # 列距 ≥ gap_min（跟随列，全程）
        for k in range(1, H + 1):
            for i in range(1, n):
                gap_i = pos[k][i - 1, -1] - pos[k][i, 0]
                opti.subject_to(gap_i >= self.gap_min)
        # 车钩力 ≤ 1000kN（每块间，全程；展平为逐元素不等式）
        for k in range(1, H + 1):
            rel_k = pos[k][:, :-1] - pos[k][:, 1:] - ca.repmat(spacing, 1, nL - 1)
            relv_k = vel[k][:, :-1] - vel[k][:, 1:]
            F_c_k = ca.vec(self._coupler_force_sym(rel_k, relv_k))
            opti.subject_to(F_c_k <= self.coupler_force_limit_n)
            opti.subject_to(F_c_k >= -self.coupler_force_limit_n)

        opti.solver(
            'ipopt',
            {'print_time': False, 'expand': True},
            {'print_level': 0, 'max_iter': self.ipopt_max_iter,
             'tol': self.ipopt_tol, 'sb': 'yes'},
        )
        self._opti = opti
        self._x = X
        self._p_pos0 = p_pos0
        self._p_vel0 = p_vel0
        self._p_gap_ref = p_gap_ref
        self._p_grade = p_grade
        self._loco_map = loco_map
        self._mass = mass
        self._spacing = spacing

    # ------------------------------------------------------------------ #
    # 主接口（统一契约：`compute_actions_from_env(env) -> (num_trains,)` 每列目标加速度，
    # 供 `evaluate_decompose._mount_mpc` / `mpc_act` 使用）
    # ------------------------------------------------------------------ #
    def compute_actions_from_env(self, env, obs=None) -> np.ndarray:
        """求解每机车 ED 调制 → 规则内层兜底 → 每列目标加速度 (num_trains,)。"""
        n = self.num_trains
        # ---- 首次调用：读编组 + 构建符号问题 ----
        if self._opti is None:
            self._read_consist(env)
            self._build_opti()
        # grade_at 前瞻：环境剖面自动重建（Regime A 公平标定）
        if self.grade_at is None and getattr(env, 'grade_profile', None):
            from src.train_dynamics.grade_profile import PROFILES
            prof_name = env.grade_profile
            if prof_name in PROFILES:
                self.grade_at = PROFILES[prof_name]().grade_at

        nL = self.n_lump
        # ---- 当前状态快照 ----
        v0 = np.array([tr.dynamics.vel[0] for tr in env.trains], dtype=float)
        if np.all(self._last_vel == 0):
            measured = np.zeros(n)
        else:
            measured = (v0 - self._last_vel) / max(self.dt, 1e-6)
        self._meas_accel = np.clip(measured, -1.5, 1.5)
        pos0 = np.zeros((n, nL))
        vel0 = np.zeros((n, nL))
        grade0 = np.zeros((n, nL))
        for ti, tr in enumerate(env.trains):
            head = float(env._train_heads[ti])
            sp = self._block_spacing_m[ti]
            for k in range(nL):
                pk = head - (k + 0.5) * sp        # 块中心位置（坡度/状态代表点）
                pos0[ti, k] = pk
                vel0[ti, k] = v0[ti]
                grade0[ti, k] = self._grade_at_pos(pk)
        # 列距参考
        gap_ref = getattr(env, '_dynamic_gap', None)
        gap_ref = float(gap_ref()) if callable(gap_ref) else self.target_gap

        # ---- 滚动时域求解 ----
        self._opti.set_value(self._p_pos0, pos0)
        self._opti.set_value(self._p_vel0, vel0)
        self._opti.set_value(self._p_gap_ref, gap_ref)
        self._opti.set_value(self._p_grade, grade0)
        if self._prev_sol is not None:
            self._opti.set_initial(self._x, self._prev_sol)
        else:
            self._opti.set_initial(self._x, 0.0)

        t0 = time.perf_counter()
        try:
            sol = self._opti.solve()
            X_star = sol.value(self._x)
            status = 'optimal'
        except RuntimeError as e:
            # 求解失败：回退第 0 块全 0（惰行），如实记录 status 供评估侧统计
            X_star = np.zeros_like(self._opti.value(self._x))
            status = f'fail:{str(e)[:200]}'
        self._last_status = status
        self.solve_times.append(time.perf_counter() - t0)
        self.solve_statuses.append(status)
        self._prev_sol = X_star

        self._last_vel = v0.copy()
        cmd_block0 = np.clip(X_star[0], -1.0, 1.0)   # (nLoco,)

        # ---- 每列目标加速度：机车 ED 调制的列内均值 ----
        U = np.zeros(n)
        gi = 0
        for ti in range(n):
            vals = []
            for _b in self._loco_blocks[ti]:
                vals.append(float(cmd_block0[gi]))
                gi += 1
            U[ti] = -float(np.mean(vals)) * self.max_accel   # ed>0(制动) → 加速度<0
        U = np.clip(U, self.accel_lo, self.accel_hi)
        self._last_cmd = U

        # ---- 规则循环制动内层兜底（与 D-RL 规则层同语义，P2 公平基线）----
        if self.inner_rule_cyclic:
            for i in range(n):
                v_i = v0[i]
                if v_i >= self.v_max:
                    U[i] = min(U[i], -0.75)
                elif v_i <= self.v_min:
                    U[i] = max(U[i], 0.0)
        return U

    def _grade_at_pos(self, pos_m: float) -> float:
        """坡度查询（Regime A：注入剖面图纸；无则 0）。"""
        if self.grade_at is None:
            return 0.0
        try:
            return float(self.grade_at(float(pos_m)))
        except Exception:
            return 0.0

    # 兼容旧统一接口（评估里用 compute_actions_from_env）
    def compute_actions(self, obs, speeds, accels, gaps, env=None) -> np.ndarray:
        return self.compute_actions_from_env(env, obs)

    def reset(self):
        self._meas_accel = np.zeros(self.num_trains)
        self._last_vel = np.zeros(self.num_trains)
        self._last_cmd = np.zeros(self.num_trains)
        self._prev_sol = None
        self.solve_times = []
        self.solve_statuses = []

    def __repr__(self):
        return (f"NMPCController(B={self.horizon_blocks}×{self.block_len}步, "
                f"lump={self.n_lump}/列, gap_min={self.gap_min}m, "
                f"coupler≤{self.coupler_force_limit_n/1e3:.0f}kN, "
                f"inner_rule_cyclic={self.inner_rule_cyclic})")
