"""
重载列车群组协同控制 Gym 环境。

多车厢列车纵向编队任务：每节车厢独立控制（牵引/制动），
目标 = 速度同步 + 间距保持 + 纵向冲动（车钩力）最小化。

底层动力学基于 src/train_dynamics（NeTrainSim 公式 + 多体车钩模型）。
"""

import numpy as np
from gym import spaces

from src.train_dynamics.params import VehicleParams, LocomotiveParams, CouplerParams, TrainConsist
from src.train_dynamics.train import TrainDynamics


def default_consist(num_vehicles: int = 4, num_locomotives: int = 1):
    """默认重载列车编组：1 机车在前 + (num_vehicles-1) 节货车。"""
    loco = LocomotiveParams(
        mass_t=188.0, no_of_axles=6, frontal_area_m2=11.5, drag_coef=1.4,
        length_m=21.0, max_power_kw=9600.0, transmission_efficiency=0.85,
        max_speed_mps=30.0, n_notches=8,
    )
    car = VehicleParams(
        mass_t=100.0, no_of_axles=4, frontal_area_m2=10.0, drag_coef=1.0,
        length_m=20.0,
    )
    return TrainConsist([loco] + [car for _ in range(num_vehicles - num_locomotives)])


class TrainFormationEnv:
    """
    重载列车编队控制环境（多智能体）。

    Args:
        config (Dict): 配置
            - num_vehicles: 车辆数（默认 4）
            - num_locomotives: 机车数（默认 1，位于队首）
            - dt: 积分步长（秒）
            - target_speed: 目标巡航速度（m/s）
            - target_gap: 目标车钩间距（m）
            - max_steps: 每回合最大步数
            - grade: 坡度（默认 0）
    """

    def __init__(self, config: dict = None):
        config = config or {}
        self.num_vehicles = config.get('num_vehicles', 4)
        self.num_locomotives = config.get('num_locomotives', 1)
        self.dt = config.get('dt', 0.1)
        self.target_speed = config.get('target_speed', 20.0)
        self.target_gap = config.get('target_gap', 1.0)
        self.max_steps = config.get('max_steps', 500)
        self.grade = config.get('grade', 0.0)

        consist = default_consist(self.num_vehicles, self.num_locomotives)
        self.dynamics = TrainDynamics(consist, dt=self.dt)
        if self.grade:
            self.dynamics.set_grade(self.grade)

        # 车钩力范围估计（约束观察/奖励缩放）
        self._max_coupler_n = 1.0e6

        # 每节车的观察：速度误差、位置误差（相对前车）、车钩力、位置
        self.obs_dim = 4
        self.observation_space = spaces.Box(
            low=-np.inf, high=np.inf,
            shape=(self.num_vehicles, self.obs_dim), dtype=np.float32,
        )
        # 动作：每节车 throttle ∈ [-1,1]，>0 牵引，<0 制动
        self.action_space = spaces.Box(
            low=-1.0, high=1.0, shape=(self.num_vehicles,), dtype=np.float32,
        )

        self.steps = 0

    def reset(self, seed=None, options=None):
        self.steps = 0
        self.dynamics.set_initial_speed(0.0)
        if options and 'speed' in options:
            self.dynamics.set_initial_speed(options['speed'])
        return self._get_obs(), {}

    def _get_obs(self) -> np.ndarray:
        """构造观察：每节车 [速度误差, 与前车间距误差, 车钩力, 位置]。"""
        pos = self.dynamics.pos
        vel = self.dynamics.vel
        coupler = self.dynamics._coupler_forces()
        obs = np.zeros((self.num_vehicles, self.obs_dim), dtype=np.float32)
        for i in range(self.num_vehicles):
            speed_err = vel[i] - self.target_speed
            gap_err = 0.0
            if i > 0:
                gap_err = (pos[i - 1] - pos[i]) - self.target_gap
            obs[i, 0] = speed_err
            obs[i, 1] = gap_err
            obs[i, 2] = coupler[i] / self._max_coupler_n
            obs[i, 3] = pos[i] * 0.01  # 位置缩放
        return obs

    def _calculate_reward(self, obs: np.ndarray, coupler: np.ndarray) -> float:
        """奖励：速度同步 + 间距保持 + 冲动最小化（所有车共享）。"""
        speed_err = np.mean(np.abs(obs[:, 0]))
        gap_err = np.mean(np.abs(obs[:, 1]))
        impulse = np.mean(np.abs(coupler)) / self._max_coupler_n
        reward = -0.5 * speed_err - 0.3 * gap_err - 0.2 * impulse
        return reward

    def step(self, actions: np.ndarray):
        actions = np.asarray(actions, dtype=float).flatten()
        if actions.shape[0] != self.num_vehicles:
            raise ValueError(f"动作维度应为 {self.num_vehicles}, 实际 {actions.shape[0]}")

        # 每节车独立控制：>0 牵引，<0 制动（仅机车能产生牵引力）
        throttle = np.zeros(self.num_vehicles)
        brake = np.zeros(self.num_vehicles)
        for i, a in enumerate(actions):
            vehicle = self.dynamics.consist.vehicles[i]
            if a > 0 and vehicle.is_locomotive:
                throttle[i] = float(a)
            elif a < 0:
                brake[i] = float(-a)

        self.dynamics.step_vehicles(throttle, brake)

        obs = self._get_obs()
        coupler = self.dynamics._coupler_forces()
        reward = self._calculate_reward(obs, coupler)

        self.steps += 1
        terminated = False
        truncated = self.steps >= self.max_steps

        # 安全终止：车速溢出
        if np.max(np.abs(self.dynamics.vel)) > 200.0:
            terminated = True
            reward -= 10.0

        info = {
            'speed': float(np.mean(self.dynamics.vel)),
            'formation_gap_err': float(np.mean(np.abs(obs[:, 1]))),
            'coupler_force': float(np.mean(np.abs(coupler))),
            'reward': reward,
        }
        return obs, reward, terminated, truncated, info

    def close(self):
        pass
