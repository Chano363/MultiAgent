"""per-agent critic（ADR-021 方向 B）回归测试。

覆盖：
1. CentralizedValueNetwork output_dim=3/1 前向形状；
2. per_agent 的 compute_gae 返回 [T, N] 且按 agent 维度各自标准化；
3. centralized_scalar 的 compute_gae 形状与改造前一致（[T]）；
4. critic 传非法值抛 ValueError；
5. update() 在两种 critic 下都能跑通且返回 8 个字段；
6. effective_horizon_steps = 1/(1-γλ) 数值正确，且 γ=0.999/λ=0.99、DI=10、dt=0.1 时
   物理视界 ≥ 90 s（而默认 γ=0.99/λ=0.95 不足以覆盖）。
"""
import numpy as np
import pytest
import torch

from src.algorithms.mappo_agent import CentralizedValueNetwork, MAPPOAgent


def _make_agent(critic='centralized_scalar', num_drones=3, batch_size=8, **kw):
    return MAPPOAgent(num_drones=num_drones, obs_per_drone=4, act_per_drone=1,
                      learning_rate=5e-5, epochs=2, batch_size=batch_size,
                      device='cpu', critic=critic, **kw)


def _fill_buffer(agent, T, N, per_agent, seed=1):
    """手工填 buffer：per_agent 时 value 为 [N] 向量，centralized 时为标量。"""
    rng = np.random.default_rng(seed)
    obs_dim = agent.total_obs_dim
    for t in range(T):
        flat = rng.normal(size=obs_dim).astype(np.float32)
        actions = np.zeros(N, dtype=np.float32)
        log_probs = rng.normal(size=N).astype(np.float32)
        reward = float(rng.normal())
        done = (t == T - 1)
        value = rng.normal(size=N).astype(np.float32) if per_agent else float(rng.normal())
        agent.store_transition(flat, actions, reward, log_probs, done, value)


# 1 -----------------------------------------------------------------------
def test_value_net_output_dim_shapes():
    net3 = CentralizedValueNetwork(state_dim=8, hidden_sizes=[16], output_dim=3)
    out3 = net3(torch.randn(5, 8))
    assert tuple(out3.shape) == (5, 3)

    net1 = CentralizedValueNetwork(state_dim=8, hidden_sizes=[16], output_dim=1)
    out1 = net1(torch.randn(5, 8))
    assert tuple(out1.shape) == (5, 1)


# 2 -----------------------------------------------------------------------
def test_per_agent_gae_shape_and_per_agent_standardization():
    N, T = 3, 12
    agent = _make_agent(critic='per_agent', num_drones=N)
    rng = np.random.default_rng(0)
    rewards = rng.normal(size=T).astype(np.float32)
    values = rng.normal(size=(T, N)).astype(np.float32)
    dones = np.zeros(T, dtype=np.float32)
    dones[-1] = 1.0

    adv, ret = agent.compute_gae(rewards, values, dones)
    assert adv.shape == (T, N)
    assert ret.shape == (T, N)
    # 每个 agent 维度各自标准化：均值≈0、std≈1
    assert np.allclose(adv.mean(axis=0), 0.0, atol=1e-5)
    assert np.allclose(adv.std(axis=0), 1.0, atol=1e-4)
    # 各 agent 的 advantage 不应退化为"同一个广播值"
    assert not np.allclose(adv[:, 0], adv[:, 1])


# 3 -----------------------------------------------------------------------
def test_centralized_gae_shape_unchanged():
    T = 12
    agent = _make_agent(critic='centralized_scalar', num_drones=3)
    rng = np.random.default_rng(0)
    rewards = rng.normal(size=T).astype(np.float32)
    values = rng.normal(size=T).astype(np.float32)
    dones = np.zeros(T, dtype=np.float32)
    dones[-1] = 1.0

    adv, ret = agent.compute_gae(rewards, values, dones)
    assert adv.shape == (T,)
    assert ret.shape == (T,)


# 4 -----------------------------------------------------------------------
def test_invalid_critic_raises_value_error():
    with pytest.raises(ValueError):
        _make_agent(critic='per_train')


# 5 -----------------------------------------------------------------------
def test_update_runs_both_critic_modes_with_all_fields():
    expected = {'total_loss', 'policy_loss', 'value_loss', 'entropy',
                'grad_norm', 'approx_kl', 'value_norm_mean', 'value_norm_std'}
    for critic in ('centralized_scalar', 'per_agent'):
        agent = _make_agent(critic=critic, num_drones=3, batch_size=8)
        _fill_buffer(agent, T=16, N=3, per_agent=(critic == 'per_agent'))
        metrics = agent.update()
        assert expected.issubset(set(metrics.keys())), (critic, metrics.keys())
        for k in ('approx_kl', 'value_norm_mean', 'value_norm_std'):
            assert np.isfinite(metrics[k]), (critic, k, metrics[k])


def test_advantage_ndim_matches_critic_mode():
    """per_agent → advantage 2 维 [T, N]（不广播）；centralized → 1 维 [T]（旧行为）。"""
    N = 3
    for critic, ndim in (('centralized_scalar', 1), ('per_agent', 2)):
        agent = _make_agent(critic=critic, num_drones=N)
        _fill_buffer(agent, T=16, N=N, per_agent=(critic == 'per_agent'))
        adv, ret = agent.compute_gae(
            np.array(agent.buffer_rewards),
            np.array(agent.buffer_values),
            np.array(agent.buffer_dones),
        )
        assert adv.ndim == ndim, critic
        assert ret.ndim == ndim, critic


# 6 -----------------------------------------------------------------------
def test_effective_horizon_matches_formula():
    g, lam = 0.99, 0.95
    agent = _make_agent(gamma=g, gae_lambda=lam)
    assert agent.effective_horizon_steps == pytest.approx(1.0 / (1.0 - g * lam), rel=1e-9)
    assert agent.effective_horizon_steps == pytest.approx(16.807, abs=1e-2)

    # 物理秒 = 决策步数 × decision_interval(原始步) × dt（决策间隔由 registry 从 cfg 注入）
    agent_di = _make_agent(gamma=0.999, gae_lambda=0.99, decision_interval=10, physics_dt=0.1)
    assert agent_di.decision_interval_s == pytest.approx(1.0, rel=1e-9)
    assert agent_di.effective_horizon_s == pytest.approx(
        agent_di.effective_horizon_steps * 10 * 0.1, rel=1e-9)


def test_effective_horizon_covers_physical_lag_when_long():
    """γ=0.999/λ=0.99 + DI=10 步 + dt=0.1 s → 有效视界 ≥ 90 s（覆盖 ≈90 s 物理滞后）。"""
    agent = _make_agent(gamma=0.999, gae_lambda=0.99, decision_interval=10, physics_dt=0.1)
    assert agent.effective_horizon_s >= 90.0
    # 反例：训练默认 γ=0.99/λ=0.95 在同 DI/dt 下仅 ≈16.8 s，不足以覆盖（故须调 γ/λ）
    default = _make_agent(gamma=0.99, gae_lambda=0.95, decision_interval=10, physics_dt=0.1)
    assert default.effective_horizon_s < 90.0


# 7 -----------------------------------------------------------------------
def test_probe_critic_mode_reads_metadata_and_infers_shape(tmp_path):
    """评估侧按 ckpt 判定价值头形态（否则 per-agent 权重装不进标量头，评估直接失败）。"""
    from src.evaluation.evaluate_decompose import probe_critic_mode

    p1 = tmp_path / 'pa.pt'
    _make_agent(critic='per_agent', num_drones=3).save(str(p1), metadata={'critic': 'per_agent'})
    assert probe_critic_mode(str(p1)) == 'per_agent'

    p2 = tmp_path / 'sc.pt'
    _make_agent(critic='centralized_scalar', num_drones=3).save(
        str(p2), metadata={'critic': 'centralized_scalar'})
    assert probe_critic_mode(str(p2)) == 'centralized_scalar'

    # 旧 ckpt 无 metadata.critic → 按 value 末层输出维度兜底（1=标量 / >1=per-agent）
    p3 = tmp_path / 'pa_nometa.pt'
    _make_agent(critic='per_agent', num_drones=3).save(str(p3))
    assert probe_critic_mode(str(p3)) == 'per_agent'

    p4 = tmp_path / 'sc_nometa.pt'
    _make_agent(critic='centralized_scalar', num_drones=3).save(str(p4))
    assert probe_critic_mode(str(p4)) == 'centralized_scalar'