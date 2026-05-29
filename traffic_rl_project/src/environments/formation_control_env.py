"""
无人机编队控制环境
基于 gym-pybullet-drones 的多智能体强化学习环境
"""

import numpy as np
from gym import spaces
from typing import Tuple, Dict, Any
from gym_pybullet_drones.envs.MultiHoverAviary import MultiHoverAviary
from gym_pybullet_drones.utils.enums import ActionType, ObservationType

class FormationControlEnv:
    """
    无人机编队控制环境

    Args:
        config (Dict): 配置参数
            - num_drones: 无人机数量
            - target_distance: 目标编队间距
            - target_altitude: 目标高度
            - max_speed: 最大速度 (m/s)
            - max_steps: 最大步数
    """

    def __init__(self, config: Dict = None):
        # 默认配置
        self.num_drones = config.get('num_drones', 3)
        self.target_distance = config.get('target_distance', 5.0)
        self.target_altitude = config.get('target_altitude', 1.0)
        self.max_speed = config.get('max_speed', 3.0)
        self.max_steps = config.get('max_steps', 400)

        # 设置初始位置：排成编队队形，所有无人机从目标高度开始
        initial_xyzs = np.array([[i * self.target_distance, 0, self.target_altitude]
                                for i in range(self.num_drones)])

        # 创建底层 aviary 环境 (使用VEL模式)
        self.aviary = MultiHoverAviary(
            num_drones=self.num_drones,
            obs=ObservationType.KIN,
            act=ActionType.VEL,
            gui=False,
            initial_xyzs=initial_xyzs
        )

        self.aviary.SPEED_LIMIT = self.max_speed

        self.observation_space = self.aviary.observation_space

        # 4D动作空间: [vx, vy, vz, mag] ∈ [-1, 1] per 无人机
        # vx,vy,vz = 方向分量（VEL模式内部会归一化为单位向量）
        # mag = 速度幅度（绝对值控制, 0=悬停, 1=全速）
        # action=[0,0,0,0] → target_vel=[0,0,0] → PID积分项自动补偿重力
        self.action_space = spaces.Box(
            low=-1.0,
            high=1.0,
            shape=(self.num_drones, 4),
            dtype=np.float32
        )

        self.steps = 0

    def _get_observation(self):
        """获取当前观测"""
        obs, _ = self.aviary._getObservation()
        return obs

    def _calculate_reward(self, obs: np.ndarray) -> float:
        positions = obs[:, :3]
        reward = 0.0

        alt_errors = [abs(p[2] - self.target_altitude) for p in positions]
        mean_alt_error = np.mean(alt_errors)
        reward -= 0.2 * mean_alt_error
        height_performance = max(0, 1.0 - mean_alt_error)
        reward += height_performance

        for i in range(1, self.num_drones):
            dist_to_prev = np.linalg.norm(positions[i] - positions[i-1])
            dist_error = abs(dist_to_prev - self.target_distance)
            reward -= 0.1 * dist_error

        reward += 0.05

        for i in range(self.num_drones):
            if positions[i][2] > 8.0:
                reward -= 2.0
            elif positions[i][2] < 0.3:
                reward -= 0.4 * (0.3 - positions[i][2])

        return reward

    def step(self, action: np.ndarray) -> Tuple[np.ndarray, float, bool, bool, Dict]:
        # 4D动作直接传递到VEL模式: [vx, vy, vz, mag]
        # mag取绝对值确保非负（SAC可能输出负值，模拟器内部用abs(mag)）
        scaled_action = action.copy()
        scaled_action[:, 3] = np.abs(scaled_action[:, 3])
        obs, _, terminated, truncated, info = self.aviary.step(scaled_action)

        if truncated and self.steps < self.max_steps - 10:
            states = np.array([self.aviary._getDroneStateVector(i) for i in range(self.num_drones)])
            reasons = []
            for i in range(self.num_drones):
                if abs(states[i][0]) > 30.0:
                    reasons.append(f"Drone{i}:|x|={abs(states[i][0]):.1f}>30")
                if abs(states[i][1]) > 30.0:
                    reasons.append(f"Drone{i}:|y|={abs(states[i][1]):.1f}>30")
                if states[i][2] > 10.0:
                    reasons.append(f"Drone{i}:z={states[i][2]:.1f}>10")
                if abs(states[i][7]) > 10.0:
                    reasons.append(f"Drone{i}:roll={abs(states[i][7]):.2f}>10")
                if abs(states[i][8]) > 10.0:
                    reasons.append(f"Drone{i}:pitch={abs(states[i][8]):.2f}>10")
            if reasons:
                import logging
                logging.warning(f"提前截断 @ step {self.steps}: {'; '.join(reasons)}")

        reward = self._calculate_reward(obs)

        positions = obs[:, :3]
        velocities = obs[:, 6:9]

        formation_errors = []
        for i in range(1, self.num_drones):
            dist = np.linalg.norm(positions[i] - positions[i-1])
            formation_errors.append(abs(dist - self.target_distance))

        info['formation_error'] = np.mean(formation_errors) if formation_errors else 0.0
        info['height_error'] = np.mean([abs(p[2] - self.target_altitude) for p in positions])

        self.steps += 1
        if self.steps >= self.max_steps:
            truncated = True

        return obs, reward, terminated, truncated, info

    def reset(self, seed: int = None, options: Dict = None) -> Tuple[np.ndarray, Dict]:
        self.steps = 0

        # 设置初始位置为编队队形
        obs, info = self.aviary.reset()

        return obs, info

    def close(self):
        """关闭环境"""
        self.aviary.close()

    def render(self):
        """渲染环境"""
        self.aviary.render()


def make_formation_control_env(config_path: str = None) -> FormationControlEnv:
    """
    创建编队控制环境的工厂函数

    Args:
        config_path: 配置文件路径（可选）

    Returns:
        FormationControlEnv: 编队控制环境实例
    """
    config = {}

    if config_path:
        import yaml
        with open(config_path, 'r') as f:
            config = yaml.safe_load(f)
            if 'environment' in config:
                config = config['environment']

    return FormationControlEnv(config=config)
