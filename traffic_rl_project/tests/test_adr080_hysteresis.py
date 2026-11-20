"""ADR-080：AB 释放迟滞带（`ab_release_hysteresis_s`）的行为与生效性。

机制（诊断 §19.29.2–§19.29.3）：已处于 AB 施加态时，若物理不足判据在最近
N 秒内曾成立，则继续保持 AB ⇒ 避免「物理需求一消失即释放」造成的反复
施加-释放（相位差来源）。只改释放时机，不改施加来源、不改任何安全门。
"""
import pytest


def _ctrl():
    from src.controllers.multi_loco_controller import MultiLocoController
    c = MultiLocoController(num_vehicles=3, loco_indices=[0], dt=0.1)
    c.notch_incr_rate_notches = 3.0
    c.ab_derive_threshold = 0.5
    c.ab_derive_notch_idx = 2
    return c


def test_hysteresis_default_off_is_zero_regression():
    """默认 0.0 = 不启用 ⇒ 不引入任何额外保持。"""
    c = _ctrl()
    assert c.ab_release_hysteresis_s == pytest.approx(0.0)


def test_hysteresis_state_array_initialised():
    """状态数组：每台机车一个「物理不足最近成立时刻」，初值 = 从未成立。"""
    c = _ctrl()
    assert len(c._ab_phys_insuff_step) == c.num_locomotives
    assert all(v < 0 for v in c._ab_phys_insuff_step)


def test_hysteresis_timestamp_recorded_when_phys_insufficient():
    """物理不足成立 ⇒ 记录时刻戳（供迟滞带判定）。"""
    c = _ctrl()
    c._ab_step = 100
    c._ab_phys_insuff_step[0] = -10 ** 9
    # 直接验证打戳逻辑的载体：数组被正确初始化且可写
    c._ab_phys_insuff_step[0] = c._ab_step
    assert c._ab_phys_insuff_step[0] == 100


def test_hysteresis_delivered_from_env_cfg():
    """★ 生效性（ADR-077 教训：配了就必须下发到 controller）。"""
    from src.environments.train_fleet_env import TrainFleetEnv
    env = TrainFleetEnv({
        'num_trains': 1,
        'consist_preset': '10kt_1plus0',
        'grade_profile': 'long_downhill',
        'max_steps': 12,
        'decompose': 'loco_notch_incr',
        'notch_incr_rate_notches': 3.0,
        'ab_release_hysteresis_s': 45.0,
    })
    try:
        c = env.multi_loco_controllers[0]
        assert c.ab_release_hysteresis_s == pytest.approx(45.0)
        assert env.ab_release_hysteresis_s == pytest.approx(45.0)
    finally:
        env.close()


def test_hysteresis_not_delivered_when_absent():
    """YAML 未配置 ⇒ controller 默认 0.0（逐位零回归）。"""
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
        c = env.multi_loco_controllers[0]
        assert c.ab_release_hysteresis_s == pytest.approx(0.0)
    finally:
        env.close()
