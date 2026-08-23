"""
MPC 协同控制器（M-MPC baseline，对标 Yang2025 单列 MPC 范式 + 多列协同）。

【定位】与 M1（MAPPO 协同阈值）完全同架构：第1层规则循环制动 + 车钩力安全层，
第2层用模型预测控制（MPC）生成每列协同阈值偏移 coor_adj ∈ [-1,1]，
喂给与 M1 相同的 HierarchicalController.get_action(train_env, coor_adj)。

与 M1 唯一区别：第2层协同决策来自确定性 MPC 而非 RL（MAPPO）——回答审稿人
"RL 协同 vs 确定性模型预测协同"哪个更稳健/有效。

【预测模型（简化列级）】在分层架构下，coor_adj 通过 v_max_adj/v_min_adj 间接
影响该列循环制动，进而影响速度与列间间距。用一阶离散模型近似：
    v_i(k+1) = v_i(k) + a_i(k)*dt        # a_i 当前加速度（从环境观测）
    gap_i(k+1) = gap_i(k) + (v_{i-1}-v_i)*dt
协同修正量 delta_v_i = K_gap*gap_err_i + K_v*(v_prev-v_i)，映射为 coor_adj。
MPC 在预测时域内滚动优化 coor_adj 序列，最小化间距误差+速度一致，约束 coor_adj∈[-1,1]。

注：本实现为"简化线性 MPC 参考线"，非 Yang2025 的多质点 QP 完整复现；
论文中如实说明其简化性与作为 MPC 范式的参考意义。
"""
import numpy as np
from scipy.optimize import minimize


class MPCController:
    """多列 MPC 协同控制器：每列输出 coor_adj（滚动时域优化）。"""

    def __init__(self, num_trains: int, dt: float = 0.1, horizon: int = 10,
                 target_gap: float = 100.0, headway_s: float = 5.0,
                 target_speed: float = 60.0 / 3.6,
                 lambda_gap: float = 1.0, lambda_v: float = 0.5,
                 lambda_u: float = 0.1):
        self.num_trains = num_trains
        self.dt = dt
        self.horizon = horizon          # 预测时域（步数）
        self.target_gap = target_gap
        self.headway_s = headway_s
        self.target_speed = target_speed
        self.lambda_gap = lambda_gap
        self.lambda_v = lambda_v
        self.lambda_u = lambda_u

    def _predict(self, v: np.ndarray, a: np.ndarray, gap: np.ndarray,
                 u: np.ndarray, n_followers: int) -> tuple:
        """简化一阶预测：u=coor_adj 影响减速度，更新速度与间距序列。

        u_i>0 → 提前制动（减速）→ v 下降 → 间距扩大（防追尾）。
        """
        V = np.zeros((self.horizon + 1, self.num_trains))
        G = np.zeros((self.horizon + 1, n_followers))
        V[0] = v
        # 间距（仅跟随列，i=0..n_followers-1 对应实际列 1..num_trains-1）
        G[0] = gap
        for k in range(self.horizon):
            # coor_adj 对减速度的简化增益：coor_adj=1 → 额外 -0.3 m/s²
            decel_effect = u[:self.num_trains] * 0.3
            V[k + 1] = V[k] + (a + decel_effect) * self.dt
            # 间距变化 = (前列速度 - 本列速度)*dt；领航列(0)前列不存在，用目标
            for fi in range(n_followers):
                i = fi + 1  # 实际列索引
                v_prev = V[k, i - 1]
                v_self = V[k, i]
                G[k + 1, fi] = G[k, fi] + (v_prev - v_self) * self.dt
        return V, G

    def compute_actions(self, obs: np.ndarray, speeds: np.ndarray,
                        accels: np.ndarray, gaps: np.ndarray) -> np.ndarray:
        """给定当前状态，滚动优化每列 coor_adj。

        Args:
            obs: 每列观测 (num_trains, obs_dim)，obs[:,1]=间距误差
            speeds: 每列当前速度 (m/s)
            accels: 每列当前加速度 (m/s²)
            gaps: 跟随列当前间距 (m)（长度 num_trains-1）

        Returns:
            coor_adj: 每列 ∈ [-1,1]
        """
        n = self.num_trains
        n_follow = n - 1

        def cost(u):
            u = np.clip(u, -1.0, 1.0)
            V, G = self._predict(speeds, accels, gaps, u, n_follow)
            c = 0.0
            for k in range(1, self.horizon + 1):
                # 间距误差（预测序列）
                if n_follow > 0:
                    dyn_gap = self.target_gap + self.headway_s * self.target_speed
                    c += self.lambda_gap * np.sum((G[k] - dyn_gap) ** 2)
                # 速度一致 + 贴近目标
                c += self.lambda_v * np.sum((V[k] - self.target_speed) ** 2)
            # 控制量变化惩罚（平稳）
            c += self.lambda_u * np.sum(u ** 2)
            return c

        # 决策变量 = 每列 coor_adj（领航列可协同也可为0，这里所有列都优化）
        u0 = np.zeros(n)
        # 边界约束 [-1,1]
        bounds = [(-1.0, 1.0)] * n
        res = minimize(cost, u0, method='SLSQP', bounds=bounds,
                       options={'maxiter': 50, 'ftol': 1e-4})
        return np.clip(res.x, -1.0, 1.0)
