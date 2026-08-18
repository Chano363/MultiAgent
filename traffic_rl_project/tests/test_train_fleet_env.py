"""
多列编队环境（TrainFleetEnv）验证测试。

验证架构澄清（2026-08-14）：
- 多智能体 = 多列万吨列车（每列 = 1 智能体，列间编队协同）
- 列内 = 单列控制（车钩力作为该列状态/奖励约束，非多智能体）
"""

import os
import sys

import pytest
import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from src.environments.train_fleet_env import TrainFleetEnv
from src.environments.train_env import TrainFormationEnv


def _make_fleet(num_trains=3, max_steps=30):
    return TrainFleetEnv({
        'num_trains': num_trains,
        'consist_preset': '10kt_1plus0',
        'grade_profile': 'long_downhill',
        'target_speed': 20.0,
        'target_gap': 100.0,
        'max_steps': max_steps,
    })


def test_fleet_env_agent_count_matches_num_trains():
    """多智能体数量 = 列车列数（每列 1 个智能体，不是每车厢）。"""
    env = _make_fleet(num_trains=3)
    obs, _ = env.reset()
    assert obs.shape == (3, 11)  # 3 列，每列 11 维状态（E3+E4：+位置/队尾坡度/前列速度/前列制动/前列减速度）
    assert env.action_space.shape == (3,)  # 每列 1 个动作


def test_fleet_env_initial_spacing():
    """编队初始列间间距应等于动态目标间距（VCTS 时间间隔，E4 修正版）。

    目标间距 = target_gap + headway_s × 参考速度（固定 target_speed，非本列速度，
    避免 RL 用速度操纵目标间距的漏洞）。
    """
    env = _make_fleet(num_trains=3)
    env.reset()
    dyn_gap = env.target_gap + env.headway_s * env.target_speed
    # 列间间距 = 前车尾部 - 本列队首，应等于动态目标间距
    for i in range(1, env.num_trains):
        prev_tail = env.trains[i - 1].dynamics.pos[-1]
        gap = prev_tail - env._train_heads[i]
        assert gap == pytest.approx(dyn_gap, abs=1.0)
    # 初始 obs 间距误差应为 0（恰好满足动态目标间距）
    obs, _ = env.reset()
    assert np.allclose(obs[:, 1], 0.0, atol=1.0)


def test_fleet_env_step_closed_loop():
    """reset/step 闭环能跑通，且车钩力在正常量级（用温和控制，非随机动作）。

    注意：缓解波（release_sync=False）下随机动作会爆车钩力（物理现象——快速切换
    制动/缓解，缓解波来不及传播，实测峰值可达19860kN），不代表真实控制。真实控制
    （第1层策略/分层）车钩力守住452kN。故用温和恒定牵引验证闭环与量级。
    """
    env = _make_fleet(max_steps=20)
    obs, _ = env.reset()
    peak = 0.0
    for _ in range(20):
        a = np.full(env.num_trains, 0.2)  # 温和恒定牵引（真实控制量级）
        obs, reward, term, trunc, info = env.step(a)
        peak = max(peak, info['coupler_force_peak'])
        if term or trunc:
            break
    # 温和控制下车钩力不应异常爆表（< 1500kN，正常控制范围内）
    assert peak < 1.5e6
    assert 'coupler_force_peak' in info
    assert 'coupler_force_limit' in info


def test_fleet_env_obs_contains_coupler_stats():
    """每列 obs 应包含车钩力均值/峰值（归一化）与超限计数。"""
    env = _make_fleet(max_steps=10)
    obs, _ = env.reset()
    # obs[:, 3]=车钩力均值, obs[:, 4]=峰值（归一化）, obs[:, 5]=超限
    assert obs.shape[1] == 11  # E3+E4 增强：obs_dim 6→11
    assert np.all(obs[:, 3] >= 0)
    assert np.all(obs[:, 4] >= 0)
    assert np.all(obs[:, 5] >= 0)


def test_fleet_env_accel_action_affects_speed():
    """加速度动作应直接影响速度（正加速度加速，负加速度减速），且有区分度。"""
    # 负加速度（制动）→ 速度下降
    env_brake = _make_fleet(max_steps=60)
    obs, _ = env_brake.reset(options={'speed': 20.0})
    v0 = env_brake.trains[0].dynamics.vel[0]
    for _ in range(40):
        obs, reward, term, trunc, info = env_brake.step(np.full(env_brake.num_trains, -1.0))
        if term or trunc:
            break
    v_brake = env_brake.trains[0].dynamics.vel[0]
    # 正加速度（牵引）→ 速度不降或升高
    env_accel = _make_fleet(max_steps=60)
    obs, _ = env_accel.reset(options={'speed': 20.0})
    for _ in range(40):
        obs, reward, term, trunc, info = env_accel.step(np.full(env_accel.num_trains, 1.0))
        if term or trunc:
            break
    v_accel = env_accel.trains[0].dynamics.vel[0]
    # 制动后速度显著低于牵引后速度（动作有真实区分度）
    assert v_accel - v_brake > 0.5
    # 车钩力不应爆表（底层控制器保证 ≤ 上限量级）
    assert info['coupler_force_peak'] < 1.5e6


def test_fleet_env_disturbance_leader_slowdown():
    """扰动工况：领航车突发强制制动时，跟随车应能协同降速（避免追尾）。

    长大下坡本质是制动控制问题，协同制动策略 = 领航车减速时跟随车保持安全间距。
    """
    env = _make_fleet(num_trains=3, max_steps=300)
    # 开启扰动：领航车在 150 步强制制动（负加速度）
    env.enable_disturbance = True
    env.disturbance_step = 150
    env.disturbance_target_accel = -0.8
    obs, _ = env.reset(options={'speed': 16.0})
    min_gap_seen = float('inf')
    for t in range(300):
        obs, reward, term, trunc, info = env.step(np.zeros(env.num_trains))
        # 记录所有跟随列的最小间距
        for i in range(1, env.num_trains):
            gap = env.target_gap + obs[i, 1]
            min_gap_seen = min(min_gap_seen, gap)
        if term or trunc:
            break
    # 协同制动应避免追尾（间距不接近 0）
    assert min_gap_seen > 10.0
    # 领航车应显著降速（被强制制动）
    assert env.trains[0].dynamics.vel[0] < 16.0


def test_fleet_env_reward_includes_coupler_and_spacing():
    """列间奖励应包含速度一致性 + 间距（安全跟车）+ 车钩力。"""
    env = _make_fleet(max_steps=10)
    obs, _ = env.reset()
    # 奖励函数能接受 obs（11维）且返回有限值
    r_base = env._calculate_reward(np.zeros((3, env.obs_dim)))
    assert np.isfinite(r_base)
    # 间距拉开过大（跟丢，E4 安全跟车：ge>200 触发惩罚）→ 奖励低
    obs_gap = np.zeros((3, env.obs_dim))
    obs_gap[:, 1] = 300.0  # 间距误差 300m（严重跟丢）
    r_gap = env._calculate_reward(obs_gap)
    assert r_base > r_gap  # 间距拉开越大奖励越低
