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
    """
    
    metadata = {'render.modes': ['human', 'rgb_array']}
    
    def __init__(self, config: Optional[Dict[str, Any]] = None):
        """
        初始化编队控制环境
        
        Args:
            config: 配置字典，包含以下参数：
                num_drones: 无人机数量（默认3）
                target_distance: 目标距离（米，默认5）
                max_speed: 最大速度（m/s，默认10）
                max_acceleration: 最大加速度（m/s²，默认2）
                gui: 是否显示GUI（默认False）
        """
        if config is None:
            config = {}
        
        self.num_drones = config.get('num_drones', 3)
        self.target_distance = config.get('target_distance', 5.0)
        self.max_speed = config.get('max_speed', 10.0)
        self.max_acceleration = config.get('max_acceleration', 2.0)
        self.gui = config.get('gui', False)
        self.max_steps = config.get('max_steps', 1000)
        
        initial_xyzs = np.zeros((self.num_drones, 3))
        for i in range(self.num_drones):
            initial_xyzs[i] = [i * self.target_distance, 0, 1]
        
        self.aviary = MultiHoverAviary(
            num_drones=self.num_drones,
            drone_model=DroneModel.CF2X,
            initial_xyzs=initial_xyzs,
            gui=self.gui,
            obs=ObservationType.KIN,
            act=ActionType.RPM
        )
        
        self.observation_space = self.aviary.observation_space
        self.action_space = self.aviary.action_space
        
        self.steps = 0
    
    def _get_observation(self):
        """获取当前观测"""
        obs, _ = self.aviary._getObservation()
        return obs
    
    def _calculate_reward(self, obs: np.ndarray) -> float:
        """
        计算编队控制奖励
        包含：
        1. 距离保持奖励 - 保持稳定距离
        2. 速度奖励 - 运输效率
        3. 平滑性奖励 - 抑制扰动
        4. 编队协调奖励 - 速度一致性
        """
        reward = 0.0
        
        positions = obs[:, :3]
        velocities = obs[:, 6:9]
        
        for i in range(1, self.num_drones):
            dist_to_leader = np.linalg.norm(positions[i] - positions[i-1])
            dist_error = abs(dist_to_leader - self.target_distance)
            reward -= 0.2 * dist_error
            
            speed_i = np.linalg.norm(velocities[i])
            reward += 0.2 * min(speed_i, self.max_speed) / self.max_speed
            
            speed_diff = np.linalg.norm(velocities[i] - velocities[i-1])
            reward -= 0.2 * speed_diff
        
        return reward
    
    def step(self, action: np.ndarray) -> Tuple[np.ndarray, float, bool, bool, Dict]:
        """
        执行一步动作
        
        Args:
            action: 每个无人机的动作（4维：RPM）
        
        Returns:
            obs: 观测
            reward: 奖励
            terminated: 是否终止
            truncated: 是否截断
            info: 额外信息
        """
        obs, _, terminated, truncated, info = self.aviary.step(action)
        
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