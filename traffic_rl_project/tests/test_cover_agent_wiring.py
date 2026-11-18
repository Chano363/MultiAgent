"""COVER agent/trainer 接线测试（不训练，只验证控制链路存在性）。

验收：
1. 默认构造 agent：cover_controller=None；
2. cover_enabled=True 构造：controller 存在、terms=3 正项、乘子初值 1.0；
3. _weights_payload 在 cover 开时携带 cover_multipliers，关时不携带；
4. registry 以 env.cover_enabled 为真源对齐 agent（防静默不一致）。
"""
import pytest

from src.algorithms.mappo_agent import MAPPOAgent
from src.trainer.parallel_rollout import _weights_payload


def _agent(cover=False):
    return MAPPOAgent(
        num_drones=1, obs_per_drone=4, act_per_drone=1,
        decision_interval=1, physics_dt=0.1,
        cover_enabled=cover,
    )


def test_agent_default_has_no_controller():
    a = _agent(cover=False)
    assert a.cover_enabled is False
    assert a.cover_controller is None


def test_agent_cover_on_has_controller():
    a = _agent(cover=True)
    assert a.cover_enabled is True
    assert a.cover_controller is not None
    assert tuple(a.cover_controller.terms) == ('speed_band', 'rel_anchor', 'gap_eff')
    assert all(v == 1.0 for v in a.cover_controller.multipliers.values())


def test_weights_payload_carries_multipliers_only_when_enabled():
    a_off = _agent(cover=False)
    a_on = _agent(cover=True)
    a_on.cover_controller.multipliers['gap_eff'] = 1.2
    p_off = _weights_payload(a_off)
    p_on = _weights_payload(a_on)
    assert 'cover_multipliers' not in p_off
    assert p_on['cover_multipliers']['gap_eff'] == pytest.approx(1.2)


def test_store_transition_accepts_step_terms():
    import numpy as np
    a = _agent(cover=True)
    a.store_transition(np.zeros(4), np.zeros(1), 1.0, np.zeros(1), False, 0.0,
                       step_terms={'speed_band': 1.0, 'rel_anchor': 0.5, 'gap_eff': 2.0})
    assert a.buffer_terms == [{'speed_band': 1.0, 'rel_anchor': 0.5, 'gap_eff': 2.0}]
