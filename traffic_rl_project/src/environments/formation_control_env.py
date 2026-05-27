"""
多智能体编队控制环境
基于 gym-pybullet-drones 专业物理仿真器
支持稳定时距保持和编队协调
"""

import numpy as np
import gymnasium as gym
from gymnasium import spaces
from gym_pybullet_drones.envs.MultiHoverAviary import MultiHoverAviary
from gym_pybullet_drones.utils.enums import DroneModel, Physics, ActionType, ObservationType
import yaml
from typing import Dict, Any, Tuple, Optional


class FormationControlEnv(gym.Env):
    """
    多智能体无人机编队控制环境
    基于 gym-pybullet-drones 的专业物理仿真
    使用 VEL (速度控制) 动作空间，底层 PID 保证飞控稳定性
    """

    metadata = {'render.modes': ['human', 'rgb_array']}

    def __init__(self, config: Optional[Dict[str, Any]] = None):
        if config is None:
            config = {}

        self.num_drones = config.get('num_drones', 3)
        self.target_distance = config.get('target_distance', 5.0)
        self.target_altitude = config.get('target_altitude', 1.0)
        self.max_speed = config.get('max_speed', 3.0)
        self.gui = config.get('gui', False)
        self.max_steps = config.get('max_steps', 400)

        initial_xyzs = np.zeros((self.num_drones, 3))
        for i in range(self.num_drones):
            initial_xyzs[i] = [i * self.target_distance, 0, self.target_altitude]

        self.aviary = MultiHoverAviary(
            num_drones=self.num_drones,
            drone_model=DroneModel.CF2X,
            initial_xyzs=initial_xyzs,
            gui=self.gui,
            obs=ObservationType.KIN,
            act=ActionType.VEL
        )

        self.aviary.SPEED_LIMIT = self.max_speed

        self.observation_space = self.aviary.observation_space
        self.action_space = self.aviary.action_space

        self.steps = 0
        self._start_center_xy = None  # 用于净位移奖励

    def _get_observation(self):
        """获取当前观测"""
        obs, _ = self.aviary._getObservation()
        return obs

    def _calculate_reward(self, obs: np.ndarray) -> float:
        """
        优化后的奖励函数（按prompts.md方案）：
        - 水平速度奖励（降低权重）
        - 垂直速度惩罚（替代奖励）
        - 低速强制移动惩罚
        - 高度误差惩罚（略增）
        - 编队惩罚（大幅增加）
        - 净位移奖励（鼓励直线前进）
        """
        positions = obs[:, :3]
        velocities = obs[:, 6:9]

        reward = 0.0

        # 1. 水平速度奖励（降低权重）
        horizontal_speeds = np.linalg.norm(velocities[:, :2], axis=1)
        mean_horiz = np.mean(horizontal_speeds)
        reward += 8.0 * mean_horiz

        # 2. 垂直速度惩罚（替代奖励，防止上下抖动）
        vertical_speeds = np.abs(velocities[:, 2])
        mean_vert = np.mean(vertical_speeds)
        reward -= 1.0 * mean_vert

        # 3. 低速强制移动惩罚
        MIN_HORIZ_SPEED = 0.5
        if mean_horiz < MIN_HORIZ_SPEED:
            reward -= 5.0 * (MIN_HORIZ_SPEED - mean_horiz)

        # 4. 高度误差惩罚（略增）
        for i in range(self.num_drones):
            alt_error = abs(positions[i][2] - self.target_altitude)
            reward -= 0.8 * alt_error

            # 边界软惩罚（保留）
            if positions[i][2] > 8.0:
                reward -= 2.0 * (positions[i][2] - 8.0)
            if positions[i][2] < 0.2:
                reward -= 1.0 * (0.2 - positions[i][2])

        # 5. 速度超限惩罚
        for i in range(self.num_drones):
            speed = np.linalg.norm(velocities[i])
            if speed > self.max_speed:
                reward -= 0.5 * (speed - self.max_speed)

        # 6. 编队惩罚（大幅增加）
        for i in range(1, self.num_drones):
            dist_to_prev = np.linalg.norm(positions[i] - positions[i-1])
            dist_error = abs(dist_to_prev - self.target_distance)
            reward -= 0.1 * dist_error      # 原 0.01
            speed_diff = np.linalg.norm(velocities[i] - velocities[i-1])
            reward -= 0.02 * speed_diff     # 原 0.005

        # 7. 速度一致性奖励（保持）
        if mean_horiz > 0.1:
            mean_horiz_vec = np.mean(velocities[:, :2], axis=0)
            mean_speed_h = np.linalg.norm(mean_horiz_vec)
            if mean_speed_h > 0.01:
                alignment = 0.0
                for i in range(self.num_drones):
                    v_xy = velocities[i, :2]
                    speed_i = np.linalg.norm(v_xy)
                    if speed_i > 0.01:
                        alignment += np.dot(v_xy, mean_horiz_vec) / (speed_i * mean_speed_h)
                reward += 0.5 * alignment / self.num_drones   # 降低到 0.5

        # 8. 生存奖励（不变）
        reward += 0.05

        # 9. 净位移奖励（替代每步位移奖励，鼓励直线前进）
        center_pos_xy = np.mean(positions[:, :2], axis=0)
        net_displacement = np.linalg.norm(center_pos_xy - self._start_center_xy)
        reward += 1.0 * net_displacement   # 每米奖励

        # 10. 裁剪到合理范围
        reward = np.clip(reward, -5.0, 25.0)
        return reward

    def step(self, action: np.ndarray) -> Tuple[np.ndarray, float, bool, bool, Dict]:
        obs, _, terminated, truncated, info = self.aviary.step(action)

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

    def reset(self, seed: Optional[int] = None, options: Optional[Dict] = None) -> Tuple[np.ndarray, Dict]:
        """重置环境"""
        super().reset(seed=seed)
        self.steps = 0

        obs, info = self.aviary.reset()

        # 记录起点中心位置（用于净位移奖励）
        positions = obs[:, :3]
        self._start_center_xy = np.mean(positions[:, :2], axis=0).copy()

        return obs, info

    def render(self, mode: str = 'human'):
        """渲染环境"""
        return self.aviary.render(mode)

    def close(self):
        """关闭环境"""
        self.aviary.close()


def make_formation_control_env(config_path: str) -> FormationControlEnv:
    """工厂函数：创建编队控制环境

    Args:
        config_path: YAML 配置文件路径
    """
    with open(config_path, 'r', encoding='utf-8') as f:
        config = yaml.safe_load(f)
    return FormationControlEnv(config=config)
