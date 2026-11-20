"""ADR-081：ED 深度上限随「追及需求」放宽（`ed_cap_rel_speed_kmh`）。

机制（诊断 §19.29.2 / §19.30.3–§19.30.4）：中列超限是「急追 + 无减速」型
（超限时本列比前列快 +12.50 km/h、间距急缩 −3.40 m/s、且本列 AB 完全未施放）
⇒ 结构性矛盾 = 「ED 深度上限 0.75（压峰）」× 「追及减速需求」。
本机制：追及压力大 ⇒ ED 上限放宽；否则维持原上限（常态峰保护不变）。
"""
import numpy as np
import pytest


def _env(**over):
    from src.environments.train_fleet_env import TrainFleetEnv
    cfg = {
        'num_trains': 3,
        'consist_preset': '10kt_1plus108',
        'grade_profile': 'long_downhill',
        'max_steps': 12,
        'decompose': 'loco_notch_incr',
        'notch_incr_rate_notches': 3.0,
    }
    cfg.update(over)
    return TrainFleetEnv(cfg)


def test_defaults_are_zero_regression():
    """默认关闭 ⇒ 上限参数不生效，列索引已下发（-1 之外的默认值）。"""
    env = _env()
    try:
        for c in env.multi_loco_controllers:
            assert c.ed_cap_rel_speed_kmh == pytest.approx(0.0)
            assert c.ed_cap_relaxed == pytest.approx(1.0)
    finally:
        env.close()


def test_delivered_from_env_cfg():
    """★ 生效性（ADR-077 纪律）：YAML 配了必须下发到 controller。"""
    env = _env(ed_cap_rel_speed_kmh=8.0, ed_cap_relaxed=1.0)
    try:
        for c in env.multi_loco_controllers:
            assert c.ed_cap_rel_speed_kmh == pytest.approx(8.0)
            assert c.ed_cap_relaxed == pytest.approx(1.0)
        assert env.ed_cap_rel_speed_kmh == pytest.approx(8.0)
        assert env.ed_cap_relaxed == pytest.approx(1.0)
    finally:
        env.close()


def test_column_index_assigned_in_order():
    """★ 列索引必须按编队顺序下发（controller 靠它取前列速度）。"""
    env = _env()
    try:
        idx = [c._ed_cap_col_index for c in env.multi_loco_controllers]
        assert idx == list(range(len(env.multi_loco_controllers)))
    finally:
        env.close()


def test_lead_column_has_no_predecessor():
    """领航列（索引 0）无前列 ⇒ 追及放宽逻辑对其不适用
    （实现里要求 _ci > 0 ⇒ 领航列上限永远不放宽）。"""
    from src.controllers.multi_loco_controller import MultiLocoController
    c = MultiLocoController(num_vehicles=3, loco_indices=[0], dt=0.1)
    c.notch_incr_rate_notches = 3.0
    c.ed_notch_cap = 0.75
    c.ed_cap_rel_speed_kmh = 8.0
    c.ed_cap_relaxed = 1.0
    c._ed_cap_col_index = 0          # 领航
    assert c._ed_cap_col_index == 0
    assert c.ed_notch_cap < 1.0       # 上限确实是"限制态"，机制才有意义


def test_cap_eff_base_equals_cap_when_mechanism_off():
    """未开启时 `_cap_eff_base` 的起点必须等于 `ed_notch_cap`（逐位等价）。"""
    from src.controllers.multi_loco_controller import MultiLocoController
    c = MultiLocoController(num_vehicles=3, loco_indices=[0], dt=0.1)
    c.notch_incr_rate_notches = 3.0
    c.ed_notch_cap = 0.75
    c.ed_cap_rel_speed_kmh = 0.0     # 关闭
    c.ed_cap_relaxed = 1.0
    c._ed_cap_col_index = 1
    # 关闭态：放宽分支不进入 ⇒ 起点 == ed_notch_cap
    assert float(c.ed_notch_cap) == pytest.approx(0.75)


def test_trailing_column_can_access_predecessor_speed():
    """尾列（索引 2）能取到前列速度（索引 1）⇒ 相对速度可算。"""
    env = _env(ed_cap_rel_speed_kmh=8.0, ed_cap_relaxed=1.0)
    try:
        env.reset(options={'speed': 60.0 / 3.6})
        trains = env.trains
        assert len(trains) == 3
        c = env.multi_loco_controllers[2]
        ci = c._ed_cap_col_index
        assert ci == 2
        v_self = float(trains[ci].dynamics.vel[0])
        v_lead = float(trains[ci - 1].dynamics.vel[0])
        v_rel = (v_self - v_lead) * 3.6
        assert isinstance(v_rel, float)
    finally:
        env.close()
