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
from src.controllers.hierarchical_controller import HierarchicalController


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
        self.grade_profile = config.get('grade_profile', 'shuozhou_23800')
        # 限速区间（m/s）：对齐 Zhang2024（朔黄线 23.8km 长大下坡循环制动）[40,80] km/h。
        # 依据（V5.24 系统核对）：
        # - 上限 80 km/h = 朔黄线实际线路限速（Zhang2024: "speed limit on this line was 80 km/h"，
        #   行业/线路标准，与研究对象1万吨朔黄线一致）
        # - 下限 40 km/h = 2万吨列车最小缓解速度（行业规则"重载30km/h以下不应缓解制动"，
        #   Zhang2024取40保守值；为与其直接对标+物理可行）
        # 弃用 [45,65]：那是樊运新（3万吨）参数，与1万吨对象不一致，且物理上不可行
        # （1.2km万吨列车在窄区间制动频繁→车钩力爆炸+掉速）。
        self.v_max = config.get('v_max', 80.0 / 3.6)   # 上限（80 km/h，线路限速）
        self.v_min = config.get('v_min', 40.0 / 3.6)   # 下限（40 km/h，最小缓解速度）
        # 巡航参考速度 = 限速区间中值（作为 obs 速度误差参考，非硬目标）
        self.target_speed = config.get('target_speed', (self.v_min + self.v_max) / 2.0)
        self.target_gap = config.get('target_gap', 100.0)  # 列间参考间距（m，用于初始布置/时间间隔换算）
        # E4 时间间隔（VCTS 虚拟耦合范式）：动态目标间距 = headway_s × 本列速度。
        # 论文依据：VCTS 用时间间隔而非固定距离（速度快时拉大、慢时缩小，自适应），
        # Wang2021 动态安全间距 x_safe 随速度/制动力变化；固定 100m 在真实剖面多坡段
        # 无法与控速同时满足。默认 5s：20m/s 时 = 100m（与历史一致），速度自适应。
        self.headway_s = config.get('headway_s', 5.0)
        self.coupler_force_limit_n = config.get('coupler_force_limit_n', COUPLER_FORCE_LIMIT_N)
        self.max_steps = config.get('max_steps', 500)
        self.dt = config.get('dt', 0.1)
        # 最大加速度（方案 B）：RL 输出 ∈ [-1,1]，映射到目标加速度 ∈ [-max_accel, max_accel]
        # 动作直接影响物理（列车加速度），有真实学习区分度（解决"学无可学"）
        self.max_accel = config.get('max_accel', 1.0)
        # 最小允许速度（长大下坡只能制动降速，速度下限）
        self.min_speed = config.get('min_speed', self.v_min)
        # 扰动（突发工况）配置：领航车在某时刻突发减速，测试跟随车协同制动
        self.enable_disturbance = config.get('enable_disturbance', False)
        self.disturbance_step = config.get('disturbance_step', 100)   # 扰动触发步
        # 扰动持续步数（默认大值=扰动触发后永久生效；评估设短暂窗口模拟"前方临时限速"）
        self.disturbance_duration = config.get('disturbance_duration', 1 << 30)
        # 扰动时领航车的目标加速度（负值 = 强制制动，模拟前方障碍/限速）
        self.disturbance_target_accel = config.get('disturbance_target_accel', -0.5)
        # 是否考虑车钩力约束（消融实验：use_coupler_constraint=False 模拟"忽略车钩力"，
        # 奖励去掉车钩力项 + 底层控制器不钳制，证明"车钩力建模必要性"）
        self.use_coupler_constraint = config.get('use_coupler_constraint', True)
        # E4 分层框架：层级二用第1层策略控速（hierarchical=True），层级一 RL 只学协同调整。
        # 依据：论文分层框架（层级一生成宏观决策 + 层级二执行）+ 物理诊断（第2层从零学
        # 控速+协同过重，第1层已验证能控速车钩力150kN/速度71km/h）。
        self.hierarchical = config.get('hierarchical', False)
        self.layer1_checkpoint = config.get(
            'layer1_checkpoint',
            'outputs/checkpoints/cyclic_mappo_best_seed0_v40-80_init80.pt',  # [40,80]第1层策略（初始80循环制动）
        )
        self.adj_coef = config.get('adj_coef', 0.3)
        # 【bug修复 2026-08-20】eval_mode：评估时第1层策略用确定性采样（消除
        # M1/M3 结果随机性）；训练时 False 保持探索。评估脚本应设 eval_mode=True。
        self.eval_mode = config.get('eval_mode', False)
        # 注：方案A（start_offset_m/spacing_m 人为坡段错开）已于 2026-08-20 移除。
        # 它偏离正确场景（各列同坡段起步、随间距保持自然产生动态相位差），
        # 且导致前列/后列缓解持续不同步 → 车钩力持续超限 + M1 训练不收敛。
        # 正确场景 = 普通 reset 布局（各列同坡段起步，见 reset()），协同由场景天然驱动。

        # 每列内部用单列动力学环境（列车内车钩力由此计算）
        # line_speed_limit_mps：场景线路限速（80km/h），传给内层 ATP 安全层作
        # 限速保护 + 超速指标口径（bug修复：原内层用机车物理限速 108km/h）
        self.trains = [
            TrainFormationEnv({
                'consist_preset': self.consist_preset,
                'grade_profile': self.grade_profile,
                'target_speed': self.target_speed,
                'coupler_force_limit_n': self.coupler_force_limit_n,
                'line_speed_limit_mps': self.v_max,
                'dt': self.dt,
                'max_steps': self.max_steps,
            })
            for _ in range(self.num_trains)
        ]
        # 每列的底层控制器（列内：加速度执行 + 车钩力约束，可开关）
        self.controllers = [
            TrainLowLevelController(
                num_vehicles=tr.num_vehicles,
                dt=self.dt,
                coupler_force_limit_n=self.coupler_force_limit_n,
                enforce_coupler=self.use_coupler_constraint,
            )
            for tr in self.trains
        ]
        # 分层控制器（2026-08-19 定位确认）：层级二用 RL 第1层策略控速
        # （warm start 自规则循环制动，缓解波下循环制动稳定，E16实测训练稳定avg+2.1万），
        # 层级一 RL 输出协同阈值偏移（v_max_adj/v_min_adj），层级二规则循环制动控速。
        # 【重构 2026-08-22】HierarchicalController 不再用 RL 第1层策略（RL 学单列
        # 循环制动结构性失败），改用规则循环制动 + 阈值协同。
        self.hier_controllers = None
        if self.hierarchical:
            self.hier_controllers = [
                HierarchicalController(
                    num_vehicles=tr.num_vehicles,
                    coupler_force_limit_n=self.coupler_force_limit_n,
                    target_speed=self.target_speed,
                    v_max=self.v_max,  # 规则循环制动限速上限
                    v_min=self.v_min,  # 规则循环制动限速下限
                    adj_coef=self.adj_coef,
                )
                for tr in self.trains
            ]
        # 记录每列参考点位置（队首位置，用于列间间距）
        self._train_heads = np.zeros(self.num_trains)
        # 每列初始基准位置（reset 时据此重建，避免跨 reset 累积平移）
        self._base_pos = [np.array(tr.dynamics.pos, dtype=float) for tr in self.trains]

        # 列级观测（E3+E4 增强，借鉴第1层成功设计：位置推断坡度 + 协同预判信息）：
        # [0]=速度误差 [1]=间距误差 [2]=前方坡度(队首) [3]=车钩力均值 [4]=车钩力峰值 [5]=超限数
        # [6]=本列队首位置(归一化,推断坡度剖面) [7]=本列队尾坡度(前方坡度变化)
        # [8]=前列队首速度 [9]=前列是否制动 [10]=前列减速度强度（协同制动预判，E4 新增）
        self.obs_dim = 11
        # 记录每列上一步实际目标加速度（供 obs 的"前列制动状态"使用）
        self._last_target_accels = np.zeros(self.num_trains)
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
        # E21 追尾趋势：上一步各列间距误差（检测间距缩小→追尾风险，引导RL提前协同）
        self._prev_gap_err = None

    def reset(self, seed=None, options=None):
        self.steps = 0
        self._peak_coupler_n = 0.0
        self._coupler_limit_violations = 0
        self._safety_events = 0
        self._last_target_accels = np.zeros(self.num_trains)
        self._prev_gap_err = None
        self._executed_actions = np.zeros(self.num_trains)

        # 记录每列参考点位置（队首位置，用于列间间距）
        cumulative_offset = 0.0
        # 初始速度：对齐 Zhang2024 长大下坡循环制动初始速度 65 km/h（18.06 m/s）
        init_speed = (options or {}).get('speed', 65.0 / 3.6)
        for i, (tr, ctrl) in enumerate(zip(self.trains, self.controllers)):
            tr.reset(options={'speed': init_speed})
            ctrl.reset()
            tr.dynamics.reset_energy()  # 重置能耗累计（避免跨回合累积）
            # 从基准初始位置重建（避免跨 reset 的累积平移）
            base_pos = self._base_pos[i].copy()
            if i == 0:
                # 领航列在原点（各列同坡段起步，普通场景）
                tr.dynamics.set_initial(pos=base_pos, vel=tr.dynamics.vel)
            else:
                # 跟随列：整列向后平移（列内长度 + 动态目标间距，E4 时间间隔）。
                # 各列同坡段起步，随编队推进自然产生动态相位差（真实编队总长~4km，
                # 前列后列进入同一坡段的时机天然不同）——协同由场景驱动，非人为错开。
                train_len = abs(base_pos[0] - base_pos[-1])
                init_gap = self._dynamic_gap()
                offset = train_len + init_gap
                cumulative_offset += offset
                tr.dynamics.set_initial(
                    pos=base_pos - cumulative_offset,
                    vel=tr.dynamics.vel,
                )
            self._train_heads[i] = float(tr.dynamics.pos[0])
        return self._get_obs(), {}

    def _dynamic_gap(self) -> float:
        """动态目标间距（VCTS 时间间隔范式）：target_gap + headway_s × 参考速度。

        E4 修正：目标间距用**固定参考速度**（限速区间中值），而非本列速度。
        原实现用本列速度导致 RL 漏洞——速度越高目标间距越大，RL 通过超速"逃避"间距
        惩罚（E4 评估超速 83.4%、间距 1194m）。用固定参考速度则动态间距为常数，
        既保留 VCTS 时间间隔语义（headway×速度尺度），又不让 RL 操纵目标。
        对齐 Wang2021 动态安全间距、Chen2024 虚拟耦合重载列车编队。
        【代码清理 2026-08-20】原签名带 vel 参数但恒被忽略（死参数），现移除。
        """
        return float(self.target_gap + self.headway_s * max(self.target_speed, 0.0))

    def _get_obs(self) -> np.ndarray:
        """构造每列观测（E3 增强）。

        [0]=速度误差 [1]=间距误差 [2]=前方坡度(队首) [3]=车钩力均值 [4]=车钩力峰值 [5]=超限数
        [6]=本列队首位置(归一化,推断坡度剖面位置) [7]=本列队尾坡度(前方坡度变化预判)
        [8]=前列队首速度 [9]=前列是否制动 [10]=前列减速度强度（协同制动预判，跟随车用；领航列=自身）
        """
        obs = np.zeros((self.num_trains, self.obs_dim), dtype=np.float32)
        # 先算各列队首速度（协同预判用）
        head_speeds = np.array([tr.dynamics.vel[0] for tr in self.trains])
        for i, tr in enumerate(self.trains):
            # 每列内部车钩力
            coupler = np.abs(tr.dynamics._coupler_forces())
            coupler_mean = np.mean(coupler) if len(coupler) else 0.0
            coupler_peak = np.max(coupler) if len(coupler) else 0.0
            viol = int(np.sum(coupler > self.coupler_force_limit_n))

            # 列间间距误差：前车（i-1）尾部 vs 本列队首 - 动态目标间距
            # E4：目标间距 = 时间间隔×本列速度（VCTS 动态安全间距），非固定 100m
            gap_err = 0.0
            if i > 0:
                prev_tail = self.trains[i - 1].dynamics.pos[-1]
                dyn_gap = self._dynamic_gap()
                gap_err = (prev_tail - self._train_heads[i]) - dyn_gap

            # 坡度：队首（当前）与队尾（前方将遇到）所在坡度
            grade_head = float(tr.dynamics.grade[0]) if hasattr(tr.dynamics, 'grade') else 0.0
            grade_tail = float(tr.dynamics.grade[-1]) if hasattr(tr.dynamics, 'grade') else grade_head

            # 本列队首位置归一化（用于推断坡度剖面位置，借鉴第1层 pos*0.0001）
            pos_norm = float(tr.dynamics.pos[0]) * 0.0001
            # 前列状态（跟随车预判协同制动；领航列用自身）
            prev_speed = head_speeds[i - 1] if i > 0 else head_speeds[i]
            prev_accel = self._last_target_accels[i - 1] if i > 0 else self._last_target_accels[i]
            prev_braking = float(prev_accel < -0.05)   # 前列是否正在制动（目标加速度<0）
            prev_decel = float(min(prev_accel, 0.0)) / max(self.max_accel, 1e-6)  # 前列减速度强度 ∈[-1,0]

            obs[i, 0] = tr.dynamics.vel[0] - self.target_speed   # 速度误差
            obs[i, 1] = gap_err                                   # 列间间距误差
            obs[i, 2] = grade_head                                # 前方坡度(队首)
            obs[i, 3] = coupler_mean / self.coupler_force_limit_n  # 车钩力均值（归一化）
            obs[i, 4] = coupler_peak / self.coupler_force_limit_n  # 车钩力峰值（归一化）
            obs[i, 5] = float(viol)                                # 车钩力超限次数
            obs[i, 6] = pos_norm                                   # 本列队首位置（推断坡度）
            obs[i, 7] = grade_tail                                 # 本列队尾坡度（前方坡度变化）
            obs[i, 8] = prev_speed / self.v_max                    # 前列速度（协同预判，归一化）
            obs[i, 9] = prev_braking                               # 前列是否制动（E4 协同预判）
            obs[i, 10] = prev_decel                                # 前列减速度强度（E4 协同预判）
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
        executed_throttles = np.zeros(self.num_trains)  # 每列实际执行 throttle（安全层修正后）
        for i, (tr, ctrl) in enumerate(zip(self.trains, self.controllers)):
            # 记录步前速度（算实际加速度用）
            v_before = float(tr.dynamics.vel[0])

            if self.hierarchical:
                # 分层模式：层级一 RL 输出"协同调整量" δ ∈ [-1,1]，
                # 层级二（第1层策略）负责列内控速，叠加 δ 得到最终 throttle。
                coor_adj = float(actions[i])
                if self.enable_disturbance and i == 0 and self.disturbance_step <= self.steps < self.disturbance_step + self.disturbance_duration:
                    # 【扰动鲁棒性评估 2026-08-22】领航车突发强制制动（模拟前方临时限速/障碍），
                    # 走底层控制器（含车钩力钳制），驱动后列协同响应。默认 enable_disturbance=False 不受影响。
                    col_actions = ctrl.get_action_accel(tr, self.disturbance_target_accel)
                else:
                    col_actions = self.hier_controllers[i].get_action(tr, coor_adj)
                target_accel = float(coor_adj) * self.max_accel  # 供奖励/obs 用
                target_accels[i] = target_accel
            else:
                # 非分层模式：层级一动作 → 该列目标加速度（动作直接影响物理）
                target_accel = float(actions[i]) * self.max_accel
                # 领航车（第0列）扰动：突发强制制动（模拟前方障碍/限速），
                if self.enable_disturbance and i == 0 and self.disturbance_step <= self.steps < self.disturbance_step + self.disturbance_duration:
                    target_accel = self.disturbance_target_accel
                target_accels[i] = target_accel
                # 层级二底层控制器：目标加速度 → 列级 throttle（执行 + 车钩力约束）
                col_actions = ctrl.get_action_accel(tr, target_accel)

            # 记录实际执行 throttle（分层/映射模式取第0节，即整列统一动作）
            executed_throttles[i] = float(col_actions[0])
            # 关键：RL 输出的列级动作（δ 协同调整 / 目标加速度）经底层控制器
            # 确定性映射为 throttle 后才执行。策略分布定义在"RL 输出动作"空间，
            # log_prob 应基于原始 RL 动作计算，无需用 throttle 重算（V5.1 教训
            # 仅适用于"同一动作空间内的安全层修正"，如 train_cyclic_braking）。
            # 此处仅记录实际执行 throttle 供 info 诊断，不覆盖 RL 动作。
            self._executed_actions[i] = executed_throttles[i]
            tr.step(col_actions)
            self._train_heads[i] = float(tr.dynamics.pos[0])
            # 实际加速度 = (新速度 - 旧速度) / dt（舒适性奖励项，对齐 Hua2024 w3·u²）
            accels[i] = (float(tr.dynamics.vel[0]) - v_before) / max(self.dt, 1e-6)

            # 该列车钩力指标（车钩力超限计数，列内累计）
            coupler = np.abs(tr.dynamics._coupler_forces())
            self._peak_coupler_n = max(self._peak_coupler_n, float(np.max(coupler)) if len(coupler) else 0.0)
            self._coupler_limit_violations += int(np.sum(coupler > self.coupler_force_limit_n))
            self._safety_events += tr._safety_events

        # 记录本步各列目标加速度（供 obs 的"前列制动状态"，E4 协同预判用）
        self._last_target_accels = target_accels.copy()

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
            # 实际执行 throttle（列级，供诊断/评估）
            'executed_actions': self._executed_actions.copy(),
            # 恒 False：RL 输出动作（δ 协同 / 目标加速度）经确定性映射才执行，
            # 策略分布定义在 RL 动作空间，log_prob 应基于原始动作，无需重算。
            # （V5.1 教训仅针对"同一动作空间内安全层修正"，见 train_cyclic_braking）
            'actions_modified': False,
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
        # 【E3 奖励重构，借鉴第1层 train_cyclic_braking 已验证有效的"稀疏清晰"哲学】
        # 第1层成功关键：速度在限速区间内给清晰正向(+5/步)，超出硬惩罚(-20/步)，制动有成本(-0.5)。
        # 第2层原奖励全是连续负惩罚，RL 无法判断"该制动还是缓解"，导致 v1 贴上限超速(97%)、
        # v2 二次惩罚探索期崩溃。重构为与第1层一致的清晰区间引导 + 多列协同项。
        # 速度一致性（各列速度相互差，越小越好）——协同制动时各列应协调减速
        speeds = np.array([tr.dynamics.vel[0] for tr in self.trains])
        speed_consistency = float(np.std(speeds))

        # 避免追尾（势场硬惩罚）：间距低于安全阈值 → 强惩罚（协同制动核心）
        # V5.x 修正：势场二次惩罚在追尾穿透时二次爆炸（单步可到 -4万）导致 GAE 尺度爆炸、
        # 训练发散（E3 实测 Ep70 崩盘到 -2000万）。加 clip 上限保证数值稳定，
        # 同时保留足够强的惩罚引导（协同制动核心目标）。
        potential_field = 0.0
        collision_penalty = 0.0
        # E21 追尾趋势惩罚：间距在缩小（后列逼近前列）→ 早期惩罚，引导 RL 提前协同
        # 减速避免追尾（seed1 灾难根因：追尾698步累积-172万，需提前预防而非等追尾势场爆炸）
        gap_trend_penalty = 0.0
        current_gap_err = obs[1:, 1].copy() if self.num_trains > 1 else np.array([])
        if self._prev_gap_err is not None and len(current_gap_err) == len(self._prev_gap_err):
            for i, cur in enumerate(current_gap_err):
                prev = self._prev_gap_err[i]
                # 间距误差在变小（实际间距缩短，逼近前列）→ 追尾趋势 → 惩罚
                shrink = prev - cur
                if shrink > 1.0 and cur < 30.0:  # 间距缩短且已较近 → 追尾风险
                    gap_trend_penalty -= 0.5 * shrink
        self._prev_gap_err = current_gap_err

        for i in range(1, self.num_trains):
            # E4 动态间距：实际间距 = 动态目标 + gap_err（obs[1] 基于动态目标）
            dyn_gap = self._dynamic_gap()
            actual_gap = dyn_gap + obs[i, 1]
            min_gap = dyn_gap * 0.4
            if actual_gap < min_gap:
                # 势场惩罚：间距越近惩罚越重（二次），clip 防爆炸
                potential_field += -2.0 * (min_gap - actual_gap) ** 2
            # 追尾硬惩罚（间距接近 0）
            if actual_gap < 5.0:
                collision_penalty -= 50.0
        potential_field = max(potential_field, -200.0)  # E22：数值稳定+降灾难量级（原-2000长距离累积爆炸）

        # 限速区间约束 [v_min, v_max]（循环制动核心目标，对齐 Zhang2024 朔黄线[40,80]，V5.24）：
        # 借鉴第1层 train_cyclic_braking 哲学（对齐 Zhang2024 Eq.22 的 Rc/Rd）：
        # - 速度在区间内 → 每列 +5 清晰正向（鼓励保持有效运行速度，非"免罚"）
        # - 超 v_max / 低于 v_min → 每列 -20 硬惩罚（长大下坡必须制动降速）
        # 这样 RL 有明确动机在 [v_min,v_max] 循环，而非贴上限超速（v1）或探索期崩溃（v2）。
        speed_band_reward = 0.0
        for i, tr in enumerate(self.trains):
            vel = tr.dynamics.vel[0]
            if self.v_min <= vel <= self.v_max:
                speed_band_reward += 5.0
            else:
                speed_band_reward -= 20.0

        # 制动成本：鼓励"只在必要时制动"（循环制动关键——学到"到上限制动，区间内缓解滑行"）
        # 借鉴第1层 brake_engaged → -0.5（Zhang2024 制动距离维护成本）
        brake_cost = 0.0
        if target_accels is not None:
            # target_accels<0 = 请求制动（加速度为负）
            brake_cost = -0.5 * float(np.sum(np.asarray(target_accels) < -0.05))

        # 间距保持（跟随车）——E4 重构为"安全跟车"语义（对齐虚拟耦合 VCTS 安全间隔）。
        # E4 诊断：真实剖面多坡段 → 3列速度天然不同步（列间实距~1300m），精确保持固定
        # 间距物理上不可行。且 speed_band_reward(超速-20) 与"追车需速度差"冲突，RL 学不会
        # 追车（v4 间距拉到1106m）。改为"安全跟车"：间距误差在安全区间内无惩罚（跟住了），
        # 拉开过大（跟丢，协同失败）→ 硬惩罚。过近由势场处理（避免追尾）。
        # 依据：VCTS 用安全间隔而非精确间距；Chen2024 虚拟耦合重载列车 = 安全间隔约束。
        gap_reward = 0.0
        if self.num_trains > 1:
            for i in range(1, self.num_trains):
                ge = obs[i, 1]  # 该跟随列间距误差（带符号：正=拉大，负=逼近）
                # 过近由势场/碰撞惩罚处理；这里给"协同保持间距"正向 + "拉开跟丢"惩罚。
                # E25 方案A（坡段错开）：各列因坡段不同前列加速/后列缓坡，间距天然易拉开，
                # 需给 RL"协同保持间距"正向信号（而非纯惩罚），引导后列主动跟进。
                # 安全区间内（-100~100m）给 +1.0/列 正向；拉开过大（>200m）→ 惩罚。
                if -100.0 <= ge <= 100.0:
                    gap_reward += 1.0
                elif ge > 200.0:
                    gap_reward -= 2.0 * (ge - 200.0) / 100.0  # 跟丢硬惩罚（随拉大加重）

        # 舒适性（加速度惩罚，对齐 Hua2024 w3·u²）：惩罚剧烈加减速 → RL 学平稳驾驶。
        # 这是底层 PID 不优化的目标，是列间 RL 的增量价值（解决"学无可学"）。
        comfort_penalty = 0.0
        if accels is not None and len(accels) > 0:
            comfort_penalty = -0.3 * float(np.mean(accels ** 2))

        # 车钩力约束（创新点：考虑车钩力）——消融实验可关闭（use_coupler_constraint=False）
        if self.use_coupler_constraint:
            coupler_mean = np.mean(obs[:, 3])
            coupler_peak = np.max(obs[:, 4]) if self.num_trains else 0.0
            violation_penalty = 0.0
            if coupler_peak > 1.0:
                violation_penalty = -5.0 * (coupler_peak - 1.0)
            coupler_term = -0.2 * coupler_mean - 0.2 * coupler_peak + violation_penalty
        else:
            coupler_term = 0.0  # 忽略车钩力（奖励不含车钩力项）

        reward = (
            + speed_band_reward        # 限速区间内+5/超限-20（E3 重构，第1层哲学）
            - 0.1 * speed_consistency  # 速度一致性（E4 降低权重：真实剖面多坡段各列速度天然不同，且追车需速度差）
            + gap_reward               # 间距保持（E4：安全跟车，拉开过大硬惩罚）
            + potential_field          # 避免追尾势场（clip 防爆炸）
            + collision_penalty        # 追尾硬惩罚
            + gap_trend_penalty        # E21 追尾趋势早期惩罚（间距缩小→提前协同避免追尾）
            + brake_cost               # 制动成本（E3 新增，鼓励循环制动）
            + comfort_penalty          # 舒适性
            + coupler_term             # 车钩力约束（可关闭）
        )
        return reward

    def close(self):
        for tr in self.trains:
            tr.close()
