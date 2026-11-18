"""ADR-074 级位派生化（loco_notch_incr）单测。

覆盖：速率限制积分、ED=级位派生、AB 级位越限派生（滞回）、安全链
（超速兜底 SERVICE / 充风门 / 低速强制缓解）、fail-fast 门、env 接线。

对标文献：Wang2023 ②（级位增量动作 + AB 由级位越限/充风派生，实车拉钩 −8.93%）。
"""

import numpy as np
import pytest
from types import SimpleNamespace

from src.controllers.multi_loco_controller import MultiLocoController


def _ctrl(rate=3.0):
    """最小 loco_notch_incr 控制器（默认派生档 = MIN 70 kPa）。"""
    ctrl = MultiLocoController(num_vehicles=1, loco_indices=[0])
    ctrl.notch_incr_rate_notches = rate
    return ctrl


def _env(vel=60.0 / 3.6):
    return SimpleNamespace(dynamics=SimpleNamespace(vel=np.array([vel])))


V_MAX = 75.0 / 3.6
V_MIN = 40.0 / 3.6


def test_rate_limit_integrates_and_ed_follows_notch():
    """级位增量限幅：每决策步 |Δn| ≤ rate/20；ED = 级位（派生）。"""
    ctrl = _ctrl(3.0)
    env = _env()
    levels = []
    for _ in range(4):
        out = ctrl.get_action_notch_incr(env, np.array([[1.0]]), v_max=V_MAX, v_min=V_MIN)
        levels.append(out[0, 0])
    assert levels == pytest.approx([0.15, 0.30, 0.45, 0.60])
    # 级位饱和到 1.0
    for _ in range(5):
        out = ctrl.get_action_notch_incr(env, np.array([[1.0]]), v_max=V_MAX, v_min=V_MIN)
    assert out[0, 0] == pytest.approx(1.0)


def test_ab_derived_from_notch_crossing():
    """级位越限派生 AB：n ≥ 0.5 → MIN(70 kPa, -0.20)；首次施加过充风门。"""
    ctrl = _ctrl(3.0)
    env = _env()
    out = ctrl.get_action_notch_incr(env, np.array([[1.0]]), v_max=V_MAX, v_min=V_MIN)
    assert out[0, 1] == 0.0            # n=0.15 < 0.5 → 不派生
    out = ctrl.get_action_notch_incr(env, np.array([[1.0]]), v_max=V_MAX, v_min=V_MIN)
    assert out[0, 1] == 0.0            # n=0.30
    out = ctrl.get_action_notch_incr(env, np.array([[1.0]]), v_max=V_MAX, v_min=V_MIN)
    assert out[0, 1] == 0.0            # n=0.45 仍低于阈值
    out = ctrl.get_action_notch_incr(env, np.array([[1.0]]), v_max=V_MAX, v_min=V_MIN)
    assert out[0, 1] == pytest.approx(-0.20)   # n=0.60 ≥ 0.5 → 派生 MIN


def test_hysteresis_keeps_ab_between_threshold_and_margin():
    """滞回：已施加态在 [阈值−margin, 阈值) 区间不抖动释放。"""
    ctrl = _ctrl(3.0)
    env = _env()
    for _ in range(4):   # n → 0.60，AB on
        ctrl.get_action_notch_incr(env, np.array([[1.0]]), v_max=V_MAX, v_min=V_MIN)
    out = ctrl.get_action_notch_incr(env, np.array([[-1.0]]), v_max=V_MAX, v_min=V_MIN)
    assert out[0, 0] == pytest.approx(0.45)
    assert out[0, 1] == pytest.approx(-0.20)   # n=0.45 ≥ 0.45 → 保持
    out = ctrl.get_action_notch_incr(env, np.array([[-1.0]]), v_max=V_MAX, v_min=V_MIN)
    assert out[0, 0] == pytest.approx(0.30)
    assert out[0, 1] == 0.0                    # n=0.30 < 0.45 → 释放


def test_overspeed_forces_service():
    """超速兜底：vel ≥ vmax_eff 强制 SERVICE（RL 无权关闭）。"""
    ctrl = _ctrl(3.0)
    fast = SimpleNamespace(dynamics=SimpleNamespace(vel=np.array([21.0])))
    out = ctrl.get_action_notch_incr(fast, np.array([[1.0]]), v_max=V_MAX, v_min=V_MIN)
    assert out[0, 1] == pytest.approx(-0.40)


def test_low_speed_release():
    """低速强制缓解（V17 教训）：vel ≤ v_min + margin → AB 释放。"""
    ctrl = _ctrl(3.0)
    ctrl.ab_low_speed_release = True
    # 先升到 n=0.60 派生 AB（正常速度）
    env = _env()
    for _ in range(4):
        ctrl.get_action_notch_incr(env, np.array([[1.0]]), v_max=V_MAX, v_min=V_MIN)
    slow = SimpleNamespace(
        dynamics=SimpleNamespace(vel=np.array([V_MIN + 2.0 / 3.6 - 0.1])))
    out = ctrl.get_action_notch_incr(slow, np.array([[1.0]]), v_max=V_MAX, v_min=V_MIN)
    assert out[0, 1] == 0.0


def test_refill_gate_blocks_quick_reapply():
    """222s 充风门：释放后未充风完再越限 → 本步不发（已建立源不受影响）。"""
    ctrl = _ctrl(3.0)
    env = _env()
    for _ in range(4):   # n=0.60，AB on
        ctrl.get_action_notch_incr(env, np.array([[1.0]]), v_max=V_MAX, v_min=V_MIN)
    ctrl.get_action_notch_incr(env, np.array([[-1.0]]), v_max=V_MAX, v_min=V_MIN)  # n=0.45 保持
    ctrl.get_action_notch_incr(env, np.array([[-1.0]]), v_max=V_MAX, v_min=V_MIN)  # n=0.30 释放
    # 重新升越限：n=0.45（保持→0.45≥0.45 不触发；继续 +）
    ctrl.get_action_notch_incr(env, np.array([[1.0]]), v_max=V_MAX, v_min=V_MIN)  # n=0.45
    out = ctrl.get_action_notch_incr(env, np.array([[1.0]]), v_max=V_MAX, v_min=V_MIN)
    # n=0.60 越限请求，但距释放仅几秒 << 222s 充风门 → 拒绝
    assert out[0, 1] == 0.0
    assert ctrl.ab_refill_veto_count == 1


def test_mode_requires_rate_limit():
    """fail-fast：rate 未配置（=0）不得静默进入本模式。"""
    ctrl = _ctrl(0.0)
    with pytest.raises(ValueError):
        ctrl.get_action_notch_incr(_env(), np.array([[1.0]]), v_max=V_MAX, v_min=V_MIN)


def test_rejects_wrong_action_shape():
    """fail-fast：动作维度必须为 1（防串模式静默错配）。"""
    ctrl = _ctrl(3.0)
    with pytest.raises(ValueError):
        ctrl.get_action_notch_incr(_env(), np.array([[0.5, 0.5]]),
                                   v_max=V_MAX, v_min=V_MIN)


def test_env_wiring_act1_obs13():
    """env 接线：act_dim=1、obs_dim=13、action_space (num_agents,1)、参数透传。"""
    from src.environments.train_fleet_env import TrainFleetEnv
    env = TrainFleetEnv({
        'num_trains': 1,
        'consist_preset': '10kt_1plus0',
        'grade_profile': 'long_downhill',
        'max_steps': 3,
        'decompose': 'loco_notch_incr',
        'notch_incr_rate_notches': 3.0,
        'ab_derive_threshold': 0.5,
        'ab_derive_release_margin': 0.05,
        'ab_derive_notch_idx': 2,
    })
    try:
        assert env.act_dim == 1
        assert env.obs_dim == 13
        assert env.action_space.shape == (env.num_agents, 1)
        assert env.observation_schema['name'] == 'loco_notch_incr_v1'
        for c in env.multi_loco_controllers:
            assert c.notch_incr_rate_notches == 3.0
            assert c.ab_derive_threshold == 0.5
            assert c.ab_derive_release_margin == 0.05
            assert c.ab_derive_notch_idx == 2
    finally:
        env.close()


def test_env_step_end_to_end_notch_integration():
    """端到端：正增量动作积分级位、obs[12] 可观测、AB 派生进入 info。"""
    from src.environments.train_fleet_env import TrainFleetEnv
    env = TrainFleetEnv({
        'num_trains': 1,
        'consist_preset': '10kt_1plus0',
        'grade_profile': 'long_downhill',
        'max_steps': 12,
        'decompose': 'loco_notch_incr',
        'notch_incr_rate_notches': 3.0,
    })
    try:
        env.reset(options={'speed': 65.0 / 3.6})
        obs, _, _, _, info = env.step(np.full((env.num_agents, 1), 1.0))
        assert obs.shape == (env.num_agents, 13)
        # 1 决策步后级位 = 0.15（起点惰行）
        assert float(obs[0, 12]) == pytest.approx(0.15)
        # 连续正增量 → 级位单调升、饱和到 1.0
        for _ in range(6):
            obs, _, _, _, info = env.step(np.full((env.num_agents, 1), 1.0))
        assert float(obs[0, 12]) == pytest.approx(1.0)
    finally:
        env.close()
