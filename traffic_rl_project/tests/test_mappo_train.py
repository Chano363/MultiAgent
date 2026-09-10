"""
MAPPO 迁移到列车环境的冒烟测试（P1 第15条）。

验证：
- 环境 obs 维度与 MAPPO 接口匹配（flatten 后 = num_vehicles × obs_dim）
- MAPPO agent 能对列车环境选择动作、存储 transition、update
- 完整跑几个 episode 不报错（长大下坡 + 万吨级编组）
"""

import os
import sys

import pytest
import numpy as np


from src.environments.train_env import TrainFormationEnv
from src.algorithms.mappo_agent import MAPPOAgent


def _make_agent(num_vehicles, obs_dim=4, act_dim=1, device='cpu', batch_size=8):
    return MAPPOAgent(
        num_drones=num_vehicles,
        obs_per_drone=obs_dim,
        act_per_drone=act_dim,
        learning_rate=5e-5,
        entropy_coef=0.005,
        epochs=2,
        batch_size=batch_size,
        device=device,
    )


def test_dimension_matches():
    """列车 obs 维度与 MAPPO 接口匹配。"""
    env = TrainFormationEnv({'num_vehicles': 6, 'max_steps': 10})
    obs, _ = env.reset()
    assert obs.shape == (6, 4)
    flat = obs.flatten()
    assert flat.shape[0] == 6 * 4
    # MAPPO 接收 flattened obs，输出 6 维动作 + per-agent log_prob（shape=[num_agents]）
    agent = _make_agent(6)
    actions, log_prob = agent.select_actions(flat)
    assert actions.shape[0] == 6
    assert isinstance(log_prob, np.ndarray)
    assert log_prob.shape[0] == 6
    assert np.all(np.isfinite(log_prob))


def test_action_scope_and_reshape():
    """动作 ∈ [-1,1]，可 reshape 成 (num_vehicles, 1) 喂给环境。"""
    env = TrainFormationEnv({'num_vehicles': 6, 'max_steps': 10})
    obs, _ = env.reset()
    agent = _make_agent(6)
    for _ in range(3):
        flat = obs.flatten()
        actions, _ = agent.select_actions(flat)
        assert np.all(actions >= -1.0) and np.all(actions <= 1.0)
        action_env = actions.reshape(6, 1)
        assert action_env.shape == (6, 1)
        obs, reward, t, tr, info = env.step(action_env)
        if t or tr:
            obs, _ = env.reset()


def test_store_and_update_small():
    """收集足够 transition 后能 update（loss 数值合理）。"""
    env = TrainFormationEnv({'num_vehicles': 6, 'max_steps': 20})
    agent = _make_agent(6, batch_size=8)
    obs, _ = env.reset()
    for _ in range(30):  # 收集 30 条 transition > batch_size 8
        flat = obs.flatten()
        actions, log_prob = agent.select_actions(flat)
        value = agent.get_value(flat)
        next_obs, reward, t, tr, info = env.step(actions.reshape(6, 1))
        done = t or tr
        agent.store_transition(flat, actions, reward, log_prob, done, value)
        obs = next_obs
        if done:
            obs, _ = env.reset()
    metrics = agent.update()
    # loss 应为有限正数（训练发生了），但不应爆炸
    assert metrics['total_loss'] >= 0
    assert np.isfinite(metrics['total_loss'])


def test_full_episode_loop_10kt_downhill():
    """万吨级编组 + 长大下坡，MAPPO 完整跑几个 episode 不报错。"""
    env = TrainFormationEnv({
        'consist_preset': '10kt_1plus0',
        'grade_profile': 'long_downhill',
        'max_steps': 20,
    })
    agent = _make_agent(env.num_vehicles, batch_size=16)
    for ep in range(2):
        obs, _ = env.reset(options={'speed': 16.0})
        done = False
        step = 0
        while not done and step < 20:
            flat = obs.flatten()
            actions, log_prob = agent.select_actions(flat)
            value = agent.get_value(flat)
            next_obs, reward, t, tr, info = env.step(actions.reshape(env.num_vehicles, 1))
            done = t or tr
            agent.store_transition(flat, actions, reward, log_prob, done, value)
            obs = next_obs
            step += 1
        agent.update()
    # 验证跑完没有异常
    assert env.num_vehicles == 101


def test_update_large_return_scale_no_skip():
    """回归：累计回报尺度大时 update 不应触发阈值跳过（value_loss 爆炸）。

    历史 bug：|returns| 可达 1e4~1e5，value 网络初始输出 ~0 → value_loss ~1e8
    → 硬编码 total_loss>1000 阈值整回合跳过更新，value 网络完全不训练。
    ValueNorm 修复后 value_loss 应为 O(1)，total_loss 有限且 loss 不为 0。
    """
    env = TrainFormationEnv({'num_vehicles': 6, 'max_steps': 30})
    agent = _make_agent(6, batch_size=8)
    obs, _ = env.reset()
    for _ in range(60):  # 收集 60 条 transition，放大累计回报尺度
        flat = obs.flatten()
        actions, log_prob = agent.select_actions(flat)
        value = agent.get_value(flat)
        next_obs, reward, t, tr, info = env.step(actions.reshape(6, 1))
        done = t or tr
        agent.store_transition(flat, actions, reward, log_prob, done, value)
        obs = next_obs
        if done:
            obs, _ = env.reset()
    metrics = agent.update()
    # 修复前：total_loss 返回 0（阈值跳过）；修复后：正常非零有限值
    assert metrics['total_loss'] > 0, "value 尺度修复后 update 不应被跳过"
    assert np.isfinite(metrics['total_loss'])
    assert np.isfinite(metrics['value_loss'])


def test_value_norm_save_load():
    """回归：value_norm 统计量随 checkpoint 保存/加载，get_value 尺度一致。"""
    agent = _make_agent(6, batch_size=8)
    # 手动喂一批大尺度 returns 更新统计量
    big_returns = np.array([-30000.0, -28000.0, -32000.0, -15000.0])
    agent.value_norm.update(big_returns)
    norm_before = agent.value_norm.normalize(np.array([-30000.0]))[0]
    denorm_before = agent.value_norm.denormalize(np.array([norm_before]))[0]

    tmp_path = os.path.join(os.path.dirname(__file__), '_tmp_value_norm.pt')
    agent.save(tmp_path)
    agent2 = _make_agent(6, batch_size=8)
    agent2.load(tmp_path)
    os.remove(tmp_path)

    norm_after = agent2.value_norm.normalize(np.array([-30000.0]))[0]
    denorm_after = agent2.value_norm.denormalize(np.array([norm_after]))[0]
    # 归一化/反归一化往返一致，且统计量保存后还原
    assert abs(norm_before - norm_after) < 1e-6
    assert abs(denorm_before - denorm_after) < 1e-3
    assert abs(agent2.value_norm.mean - (-26250.0)) < 1e-2
    assert agent2.value_norm.count == 4
