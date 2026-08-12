"""
列车 Gym 环境数值闭环验证。

验证 reset/step 接口契约、观察/动作维度、行为合理性。
"""

import os
import sys

import pytest
import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from src.environments.train_env import TrainFormationEnv


def test_env_reset_contract():
    """reset 返回 (obs, info)，维度符合契约。"""
    env = TrainFormationEnv({'num_vehicles': 4})
    obs, info = env.reset()
    assert obs.shape == (4, env.obs_dim)
    assert isinstance(info, dict)
    env.close()


def test_env_action_space():
    """动作空间为连续 [-1,1]，维度 = 车辆数。"""
    env = TrainFormationEnv({'num_vehicles': 4})
    assert env.action_space.shape == (4,)
    assert np.allclose(env.action_space.low, -1.0)
    assert np.allclose(env.action_space.high, 1.0)
    env.close()


def test_env_step_shape():
    """step 返回 5 元组，obs 维度正确，reward 为标量。"""
    env = TrainFormationEnv({'num_vehicles': 4})
    env.reset()
    action = np.zeros(4)
    obs, reward, terminated, truncated, info = env.step(action)
    assert obs.shape == (4, env.obs_dim)
    assert isinstance(reward, float)
    assert isinstance(terminated, bool)
    assert isinstance(truncated, bool)
    assert 'speed' in info and 'formation_gap_err' in info
    env.close()


def test_env_wrong_action_dim_raises():
    """动作维度错误应报错。"""
    env = TrainFormationEnv({'num_vehicles': 4})
    env.reset()
    with pytest.raises(ValueError):
        env.step(np.zeros(3))
    env.close()


def test_env_throttle_accelerates():
    """满油门（全正动作）应使列车前进加速。"""
    env = TrainFormationEnv({'num_vehicles': 4, 'max_steps': 100})
    env.reset()
    for _ in range(50):
        obs, reward, terminated, truncated, info = env.step(np.full(4, 1.0))
        if terminated or truncated:
            break
    assert info['speed'] > 0
    env.close()


def test_env_brake_decelerates():
    """全制动（全负动作）应从高速减速。"""
    env = TrainFormationEnv({'num_vehicles': 4, 'max_steps': 100})
    env.reset(options={'speed': 20.0})
    speeds = []
    for _ in range(60):
        obs, reward, terminated, truncated, info = env.step(np.full(4, -1.0))
        speeds.append(info['speed'])
    assert speeds[-1] < speeds[0]
    env.close()


def test_env_episode_truncates():
    """到达 max_steps 应 truncated。"""
    env = TrainFormationEnv({'num_vehicles': 4, 'max_steps': 10})
    env.reset()
    done = False
    steps = 0
    while not done:
        obs, reward, terminated, truncated, info = env.step(np.zeros(4))
        done = terminated or truncated
        steps += 1
        if steps > 50:
            break
    assert truncated
    assert steps == 10
    env.close()


def test_env_infos_present():
    """info 应包含速度、编队误差、车钩力、奖励。"""
    env = TrainFormationEnv({'num_vehicles': 4})
    env.reset()
    obs, reward, terminated, truncated, info = env.step(np.zeros(4))
    assert set(['speed', 'formation_gap_err', 'coupler_force', 'reward']) <= set(info.keys())
    env.close()
