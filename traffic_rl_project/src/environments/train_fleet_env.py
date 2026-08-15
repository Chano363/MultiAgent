"""
重载列车群组（多列编队）协同控制 Gym 环境。

【核心定位（2026-08-14 架构澄清）】
- 多智能体 = 多列万吨列车（每列 = 1 个智能体，编队/群组协同）
- 列内（1 机车 + 100 拖挂）= 单列控制（车钩力作为该列状态/奖励的约束指标），不是多智能体

【任务场景（已确认）】
- 3 列万吨列车在长大下坡 leader-follower 编队巡航
- 目标 = 速度一致（20 m/s）+ 保持 100m 安全间距 + 车钩力 ≤1000kN

【分层架构】
层级一（本文件）：多列编队 MARL 环境
    - 智能体 = 每列万吨列车
    - 每列状态 = 该列速度 / 间距误差 / 前方坡度 / 自身车钩力统计（均值/峰值/超限）
    - 每列动作 = 该列目标加速度（宏观决策，m/s²，对齐 Zhang2021 控加速度）
    - 每列奖励 = 速度同步 + 列间安全间距 + 自身车钩力约束 + 舒适性

层级二（列内底层控制器）：TrainLowLevelController
    - 接收层级一的目标加速度 → 转为列级 throttle（get_action_accel）+ 车钩力安全钳制
    - 输出该列实际车钩力反馈给层级一作状态/奖励
"""

import numpy as np
from gym import spaces

from src.environments.train_env import TrainFormationEnv, COUPLER_FORCE_LIMIT_N
from src.controllers.low_level_controller import TrainLowLevelController


class TrainFleetEnv:
    """
    多列万吨列车编队协同控制环境。

    智能体 = 每列万吨列车。列内用底层控制器（TrainLowLevelController）跟踪目标速度。

    Args:
        config (Dict):
            - num_trains: 编队列车列数（默认 3）
            - consist_preset: 单列编组预设（默认 '10kt_1plus0'，1机车+100拖挂）
            - grade_profile: 坡度剖面（默认 'long_downhill'）
            - target_speed: 目标巡航速度（m/s）
            - target_gap: 列间目标安全间距（m）
            - coupler_force_limit_n: 车钩力上限（默认 1000kN）
            - max_steps: 每回合最大步数
            - dt: 积分步长
            - action_speed_range: 目标速度动作范围（m/s，相对 target_speed 的偏差范围）
    """

    def __init__(self, config: dict = None):
        config = config or {}
        self.num_trains = config.get('num_trains', 3)
        self.consist_preset = config.get('consist_preset', '10kt_1plus0')
        self.grade_profile = config.get('grade_profile', 'long_downhill')
        self.target_speed = config.get('target_speed', 20.0)
        self.target_gap = config.get('target_gap', 100.0)  # 列间安全间距（m）
        self.coupler_force_limit_n = config.get('coupler_force_limit_n', COUPLER_FORCE_LIMIT_N)
        self.max_steps = config.get('max_steps', 500)
        self.dt = config.get('dt', 0.1)
        # 最大加速度（方案 B）：RL 输出 ∈ [-1,1]，映射到目标加速度 ∈ [-max_accel, max_accel]
        # 动作直接影响物理（列车加速度），有真实学习区分度（解决"学无可学"）
        self.max_accel = config.get('max_accel', 1.0)
        # 最小允许速度（长大下坡只能制动降速，速度下限）
        self.min_speed = config.get('min_speed', 10.0)
        # 扰动（突发工况）配置：领航车在某时刻突发减速，测试跟随车协同制动
        self.enable_disturbance = config.get('enable_disturbance', False)
        self.disturbance_step = config.get('disturbance_step', 100)   # 扰动触发步
        # 扰动时领航车的目标加速度（负值 = 强制制动，模拟前方障碍/限速）
        self.disturbance_target_accel = config.get('disturbance_target_accel', -0.5)

        # 每列内部用单列动力学环境（列车内车钩力由此计算）
        self.trains = [
            TrainFormationEnv({
                'consist_preset': self.consist_preset,
                'grade_profile': self.grade_profile,
                'target_speed': self.target_speed,
                'coupler_force_limit_n': self.coupler_force_limit_n,
                'dt': self.dt,
                'max_steps': self.max_steps,
            })
            for _ in range(self.num_trains)
        ]
        # 每列的底层控制器（列内：跟踪目标速度 + 车钩力约束）
        self.controllers = [
            TrainLowLevelController(
                num_vehicles=tr.num_vehicles,
                dt=self.dt,
                coupler_force_limit_n=self.coupler_force_limit_n,
            )
            for tr in self.trains
        ]
        # 记录每列参考点位置（队首位置，用于列间间距）
        self._train_heads = np.zeros(self.num_trains)
        # 每列初始基准位置（reset 时据此重建，避免跨 reset 累积平移）
        self._base_pos = [np.array(tr.dynamics.pos, dtype=float) for tr in self.trains]

        # 列级观测：每列 [速度误差, 间距误差, 前方坡度, 车钩力均值, 车钩力峰值, 车钩力超限]
        self.obs_dim = 6
        self.observation_space = spaces.Box(
            low=-np.inf, high=np.inf,
            shape=(self.num_trains, self.obs_dim), dtype=np.float32,
        )
        # 列级动作：每列目标速度偏差 ∈ [-1,1]（RL 输出），映射到实际目标速度
        self.action_space = spaces.Box(
            low=-1.0, high=1.0, shape=(self.num_trains,), dtype=np.float32,
        )

        self.steps = 0
        self._peak_coupler_n = 0.0
        self._coupler_limit_violations = 0
        self._safety_events = 0

    def reset(self, seed=None, options=None):
        self.steps = 0
        self._peak_coupler_n = 0.0
        self._coupler_limit_violations = 0
        self._safety_events = 0

        # 记录每列参考点位置（队首位置，用于列间间距）
        cumulative_offset = 0.0
        for i, (tr, ctrl) in enumerate(zip(self.trains, self.controllers)):
            tr.reset(options={'speed': self.target_speed * 0.8})
            ctrl.reset()
            tr.dynamics.reset_energy()  # 重置能耗累计（避免跨回合累积）
            # 从基准初始位置重建（避免跨 reset 的累积平移）
            base_pos = self._base_pos[i].copy()
            if i == 0:
                # 领航列在原点
                tr.dynamics.set_initial(pos=base_pos, vel=tr.dynamics.vel)
            else:
                # 跟随列：整列向后平移（列内长度 + 列间目标间距）
                train_len = abs(base_pos[0] - base_pos[-1])
                offset = train_len + self.target_gap
                cumulative_offset += offset
                tr.dynamics.set_initial(
                    pos=base_pos - cumulative_offset,
                    vel=tr.dynamics.vel,
                )
            self._train_heads[i] = float(tr.dynamics.pos[0])
        return self._get_obs(), {}

    def _get_obs(self) -> np.ndarray:
        """构造每列观测 [速度误差, 间距误差, 前方坡度, 车钩力均值, 车钩力峰值, 车钩力超限]。"""
        obs = np.zeros((self.num_trains, self.obs_dim), dtype=np.float32)
        for i, tr in enumerate(self.trains):
            # 每列内部车钩力
            coupler = np.abs(tr.dynamics._coupler_forces())
            coupler_mean = np.mean(coupler) if len(coupler) else 0.0
            coupler_peak = np.max(coupler) if len(coupler) else 0.0
            viol = int(np.sum(coupler > self.coupler_force_limit_n))

            # 列间间距误差：前车（i-1）尾部 vs 本列队首
            gap_err = 0.0
            if i > 0:
                prev_tail = self.trains[i - 1].dynamics.pos[-1]
                gap_err = (prev_tail - self._train_heads[i]) - self.target_gap

            # 前方坡度（取本列队首位置所在坡度）
            grade = float(tr.dynamics.grade[0]) if hasattr(tr.dynamics, 'grade') else 0.0

            obs[i, 0] = tr.dynamics.vel[0] - self.target_speed  # 本列速度误差
            obs[i, 1] = gap_err                                   # 列间间距误差
            obs[i, 2] = grade                                     # 前方坡度
            obs[i, 3] = coupler_mean / self.coupler_force_limit_n  # 车钩力均值（归一化）
            obs[i, 4] = coupler_peak / self.coupler_force_limit_n  # 车钩力峰值（归一化）
            obs[i, 5] = float(viol)                                # 车钩力超限次数
        return obs

    def step(self, actions: np.ndarray):
        """推进所有列车一步。

        Args:
            actions: 每列目标速度偏差 ∈ [-1,1]，长度 = num_trains。
                映射到该列目标速度 = target_speed + action * action_speed_range，
                由列内底层控制器跟踪（保证车钩力 ≤1000kN）。
        """
        actions = np.asarray(actions, dtype=float).flatten()
        if actions.shape[0] != self.num_trains:
            raise ValueError(f"动作维度应为 {self.num_trains}, 实际 {actions.shape[0]}")

        reward = 0.0
        self._safety_events = 0
        target_accels = np.zeros(self.num_trains)  # 记录每列实际目标加速度（奖励判断用）
        accels = np.zeros(self.num_trains)         # 记录每列实际加速度（舒适性奖励项）
        for i, (tr, ctrl) in enumerate(zip(self.trains, self.controllers)):
            # 层级一动作 → 该列目标加速度（动作直接影响物理，有学习区分度）
            target_accel = float(actions[i]) * self.max_accel

            # 领航车（第0列）扰动：突发强制制动（模拟前方障碍/限速），
            # 跟随车需观察并协同制动保持间距 → 这是列间协同制动策略的价值所在
            if self.enable_disturbance and i == 0 and self.steps >= self.disturbance_step:
                target_accel = self.disturbance_target_accel
            target_accels[i] = target_accel

            # 记录步前速度（算实际加速度用）
            v_before = float(tr.dynamics.vel[0])
            # 层级二底层控制器：目标加速度 → 列级 throttle（执行 + 车钩力约束）
            col_actions = ctrl.get_action_accel(tr, target_accel)
            tr.step(col_actions)
            self._train_heads[i] = float(tr.dynamics.pos[0])
            # 实际加速度 = (新速度 - 旧速度) / dt（舒适性奖励项，对齐 Hua2024 w3·u²）
            accels[i] = (float(tr.dynamics.vel[0]) - v_before) / max(self.dt, 1e-6)

            # 该列车钩力指标（车钩力超限计数，列内累计）
            coupler = np.abs(tr.dynamics._coupler_forces())
            self._peak_coupler_n = max(self._peak_coupler_n, float(np.max(coupler)) if len(coupler) else 0.0)
            self._coupler_limit_violations += int(np.sum(coupler > self.coupler_force_limit_n))
            self._safety_events += tr._safety_events

        obs = self._get_obs()
        reward = self._calculate_reward(obs, target_accels, accels)

        self.steps += 1
        terminated = False
        truncated = self.steps >= self.max_steps

        info = {
            'reward': reward,
            'coupler_force_peak': float(self._peak_coupler_n),
            'coupler_force_limit': float(self.coupler_force_limit_n),
            'coupler_limit_violations': int(self._coupler_limit_violations),
            'safety_events': int(self._safety_events),
        }
        return obs, reward, terminated, truncated, info

    def _calculate_reward(self, obs: np.ndarray, target_accels: np.ndarray = None,
                          accels: np.ndarray = None) -> float:
        """列间奖励（聚焦协同制动策略 + 舒适性）：避免追尾 + 平稳驾驶 + 车钩力 + 间距。

        领域认知（2026-08-14）：长大下坡本质是制动控制问题——列车无法牵引超速，
        只能制动降速。因此列间 RL 的价值是"协同制动策略"（多列如何协同制动避免追尾、
        保持安全间距、车钩力不超限）。

        对齐业界（Hua2024 w3·u² 舒适性 / Zhang2021 APF 势场）：
        - 舒适性（加速度惩罚）：惩罚剧烈加减速 → RL 学"平稳驾驶"（底层 PID 不会优化
          舒适性，这是 RL 的增量价值，解决"学无可学"）
        - 避免追尾（势场）：间距低于安全阈值 → 强惩罚（协同制动核心目标）
        - 速度不超限：速度超目标 → 惩罚（长大下坡制动控速）
        - 车钩力约束：超限 → 成比例惩罚（本项目创新点）
        - 间距保持 + 速度一致性：跟随车协同保持间距

        奖励项：
        - 舒适性（accels）：各列加速度平方和 → 惩罚
        - 避免追尾（势场）：间距低于安全阈值 → 强惩罚（协同制动核心目标）
        - 速度不超限：速度超目标 → 惩罚（长大下坡制动控速）
        - 车钩力约束：超限 → 成比例惩罚（本项目创新点）
        - 间距保持：间距误差 → 惩罚（跟随车协同保持间距）
        - 速度一致性：各列速度差 → 惩罚（协同制动一致）
        """
        # 速度误差（各列 vs 目标速度，越小越好）——惩罚"大家一起慢速滑行"的次优解。
        # V5.14 发现：只用 speed_consistency（各列速度差）会让策略学到"各列同速但偏离目标"
        # （速度一致就 reward 最优，无论是否达到 target_speed）。必须加速度绝对值约束。
        speed_err = np.mean(np.abs(obs[:, 0]))
        # 速度一致性（各列速度相互差，越小越好）——协同制动时各列应协调减速
        speeds = np.array([tr.dynamics.vel[0] for tr in self.trains])
        speed_consistency = float(np.std(speeds))

        # 避免追尾（势场硬惩罚）：间距低于安全阈值 → 强惩罚（协同制动核心）
        potential_field = 0.0
        min_gap = self.target_gap * 0.4
        collision_penalty = 0.0
        for i in range(1, self.num_trains):
            actual_gap = self.target_gap + obs[i, 1]
            if actual_gap < min_gap:
                # 势场惩罚：间距越近惩罚越重（二次）
                potential_field += -2.0 * (min_gap - actual_gap) ** 2
            # 追尾硬惩罚（间距接近 0）
            if actual_gap < 5.0:
                collision_penalty -= 50.0

        # 速度不超限：速度超目标速度太多 → 惩罚（长大下坡需制动控速）
        overspeed_penalty = 0.0
        for i, tr in enumerate(self.trains):
            overspeed = tr.dynamics.vel[0] - self.target_speed - 0.5  # 允许小余量
            if overspeed > 0:
                overspeed_penalty -= 2.0 * overspeed

        # 间距保持（跟随车）：间距误差 → 惩罚
        gap_err = np.mean(np.abs(obs[1:, 1])) if self.num_trains > 1 else 0.0

        # 舒适性（加速度惩罚，对齐 Hua2024 w3·u²）：惩罚剧烈加减速 → RL 学平稳驾驶。
        # 这是底层 PID 不优化的目标，是列间 RL 的增量价值（解决"学无可学"）。
        # 加速度归一化：典型制动/牵引加速度 ~1 m/s²，平方后 ~1，权重 0.3 合适
        comfort_penalty = 0.0
        if accels is not None and len(accels) > 0:
            comfort_penalty = -0.3 * float(np.mean(accels ** 2))

        # 车钩力约束（创新点：考虑车钩力）
        coupler_mean = np.mean(obs[:, 3])
        coupler_peak = np.max(obs[:, 4]) if self.num_trains else 0.0
        violation_penalty = 0.0
        if coupler_peak > 1.0:
            violation_penalty = -5.0 * (coupler_peak - 1.0)

        reward = (
            -0.5 * speed_err          # 速度绝对值误差（必须接近目标速度，V5.14 新增）
            - 0.3 * speed_consistency  # 速度一致性（各列协同）
            - 0.4 * gap_err            # 间距保持
            + potential_field          # 避免追尾势场
            + collision_penalty        # 追尾硬惩罚
            + overspeed_penalty        # 速度超限
            + comfort_penalty          # 舒适性
            - 0.2 * coupler_mean       # 车钩力均值
            - 0.2 * coupler_peak       # 车钩力峰值
            + violation_penalty        # 车钩力超限
        )
        return reward

    def close(self):
        for tr in self.trains:
            tr.close()
