"""ADR-077：AB 门三键（释放速度门 / 释放门限 / 施加门）的 env 侧下发。

缺陷（诊断 §19.23）：这三个键此前只写在 YAML 里，`train_fleet_env` 从未读取、
也从未下发到 controller ⇒ 训练与探针实际都吃 controller 默认值
（`ab_release_speed_gate=False` / `ab_release_speed_kmh=50.0` /
`ab_apply_speed_min_kmh=0.0`）⇒ YAML 里的 `true` / `56.0` / `60.0` 从未生效。

本测试锁死「YAML 配了就必须生效」，防止同类死配置再次出现。
"""
import pytest


def _env(**over):
    from src.environments.train_fleet_env import TrainFleetEnv
    cfg = {
        'num_trains': 1,
        'consist_preset': '10kt_1plus0',
        'grade_profile': 'long_downhill',
        'max_steps': 12,
        'decompose': 'loco_notch_incr',
        'notch_incr_rate_notches': 3.0,
    }
    cfg.update(over)
    return TrainFleetEnv(cfg)


def test_ab_gates_default_matches_controller_defaults():
    """未在 YAML 配置时 ⇒ 下发值与 controller 构造默认逐位相同（零回归）。"""
    env = _env()
    try:
        c = env.multi_loco_controllers[0]
        assert c.ab_release_speed_gate is False
        assert c.ab_release_speed_kmh == pytest.approx(50.0)
        assert c.ab_apply_speed_min_kmh == pytest.approx(0.0)
    finally:
        env.close()


def test_ab_gates_are_delivered_from_env_cfg():
    """YAML 配了 ⇒ 必须真正下发到 controller（本次修复的核心断言）。"""
    env = _env(ab_release_speed_gate=True,
               ab_release_speed_kmh=56.0,
               ab_apply_speed_min_kmh=60.0)
    try:
        c = env.multi_loco_controllers[0]
        assert c.ab_release_speed_gate is True
        assert c.ab_release_speed_kmh == pytest.approx(56.0)
        assert c.ab_apply_speed_min_kmh == pytest.approx(60.0)
        # env 侧同源属性也应一致（便于探针/评估侧直接读 env）
        assert env.ab_release_speed_gate is True
        assert env.ab_release_speed_kmh == pytest.approx(56.0)
        assert env.ab_apply_speed_min_kmh == pytest.approx(60.0)
    finally:
        env.close()


def test_ab_gates_delivered_to_every_column():
    """逐列下发 ⇒ 多列编队每一列都拿到同样的门参数。"""
    env = _env(num_trains=3,
               consist_preset='10kt_1plus108',
               ab_release_speed_gate=True,
               ab_release_speed_kmh=56.0,
               ab_apply_speed_min_kmh=60.0)
    try:
        assert len(env.multi_loco_controllers) == 3
        for c in env.multi_loco_controllers:
            assert c.ab_release_speed_gate is True
            assert c.ab_release_speed_kmh == pytest.approx(56.0)
            assert c.ab_apply_speed_min_kmh == pytest.approx(60.0)
    finally:
        env.close()


def test_ab_gate_speed_kmh_zero_is_delivered_not_dropped():
    """0.0 是合法取值（= 关闭施加门）⇒ 不能被「假值」逻辑吞掉。"""
    env = _env(ab_release_speed_gate=True,
               ab_release_speed_kmh=56.0,
               ab_apply_speed_min_kmh=0.0)
    try:
        c = env.multi_loco_controllers[0]
        assert c.ab_release_speed_gate is True
        assert c.ab_apply_speed_min_kmh == pytest.approx(0.0)
    finally:
        env.close()
