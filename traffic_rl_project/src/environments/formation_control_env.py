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
        self.max_steps = config.get('max_steps', 300)
        
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
        self._prev_positions = None
    
    def _get_observation(self):
        """获取当前观测"""
        obs, _ = self.aviary._getObservation()
        return obs
    
    def _calculate_reward(self, obs: np.ndarray) -> float:
        positions = obs[:, :3]
        velocities = obs[:, 6:9]
        
        reward = 0.0
        
        # 编队移动奖励 - 鼓励沿x轴正向移动（大幅提高权重）
        # 领航者的x方向速度作为编队移动速度的基准
        formation_speed = velocities[0][0]  # x轴速度
        if formation_speed > 0:
            reward += 1.0 * formation_speed  # 移动奖励权重从0.5提高到1.0
        
        # 速度限制惩罚（所有无人机）
        for i in range(self.num_drones):
            speed = np.linalg.norm(velocities[i])
            if speed > self.max_speed:
                reward -= 0.1 * (speed - self.max_speed)
        
        # 编队距离保持惩罚（跟随者）- 适当降低权重
        for i in range(1, self.num_drones):
            dist_to_prev = np.linalg.norm(positions[i] - positions[i-1])
            dist_error = abs(dist_to_prev - self.target_distance)
            reward -= 0.03 * dist_error  # 从0.05降低到0.03
            
            alt_error = abs(positions[i][2] - self.target_altitude)
            reward -= 0.02 * alt_error
            
            speed_diff = np.linalg.norm(velocities[i] - velocities[i-1])
            reward -= 0.01 * speed_diff
        
        # 速度一致性奖励 - 所有无人机速度方向一致
        mean_velocity = np.mean(velocities, axis=0)
        mean_speed = np.linalg.norm(mean_velocity)
        if mean_speed > 0.1:  # 只有在移动时才计算一致性奖励
            velocity_alignment = 0.0
            for i in range(self.num_drones):
                speed_i = np.linalg.norm(velocities[i])
                if speed_i > 0.01:
                    velocity_alignment += np.dot(velocities[i], mean_velocity) / (speed_i * mean_speed)
            reward += 0.1 * velocity_alignment / self.num_drones
        
        # 生存奖励（适度降低，鼓励移动）
        reward += 0.05
        
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
        
        self.steps += 1
        if self.steps >= self.max_steps:
            truncated = True
        
        return obs, reward, terminated, truncated, info
    
    def reset(self, seed: Optional[int] = None, options: Optional[Dict] = None) -> Tuple[np.ndarray, Dict]:
        """重置环境"""
        super().reset(seed=seed)
        self.steps = 0
        
        obs, info = self.aviary.reset()
        return obs, info
    
    def render(self, mode: str = 'human'):
        """渲染环境"""
        return self.aviary.render(mode)
    
    def close(self):
        """关闭环境"""
        self.aviary.close()


def make_formation_control_env(config_path: str = None) -> FormationControlEnv:
    """
    创建编队控制环境
    
    Args:
        config_path: 配置文件路径
        
    Returns:
        FormationControlEnv 实例
    """
    config = {}
    
    if config_path:
        with open(config_path, 'r') as f:
            config = yaml.safe_load(f)
        config = config.get('environment', config)
    
    return FormationControlEnv(config)