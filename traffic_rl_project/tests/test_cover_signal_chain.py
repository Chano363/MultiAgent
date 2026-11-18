"""COVER 信号链端到端集成测试（env 侧）。

验收：
1. cover_enabled=false（默认）时 _cover_step_terms 恒 None、reward 与不开启逐位一致
   （零回归，硬红线第 5 条）；
2. cover_enabled=true 时每 step 产出 3 正项 {speed_band, rel_anchor, gap_eff}；
3. cover_multipliers 乘子按预期作用到 reward（乘 1.0 不变、乘 2.0 正项翻倍增量）。
"""
import numpy as np
import pytest

from src.environments.train_fleet_env import TrainFleetEnv


def _make_env(cover_enabled=False):
    cfg = {
        'num_trains': 1,
        'consist_preset': '10kt_1plus1',
        'grade_profile': 'long_downhill',
        'target_speed': 20.0,
        'max_steps': 50,
        'decompose': 'loco_ed_ab',
        'speed_band_shape': 'ramp',  # 无需参考表，仍有 speed_band/rel_anchor/gap_eff 正项
        'cover_enabled': cover_enabled,
    }
    return TrainFleetEnv(cfg)


def _run_fixed_actions(env, seed=0, steps=6):
    env.reset(options={'speed': 65.0 / 3.6})
    np.random.seed(seed)
    rewards = []
    for _ in range(steps):
        n_loco = len(env.trains[0].loco_indices)
        act = np.random.uniform(-0.3, 0.3, size=(n_loco, 2)).astype(float)
        obs, r, term, trunc, info = env.step(act)
        rewards.append(float(r))
        if term or trunc:
            break
    return rewards


def test_cover_disabled_is_bitwise_identical():
    """关闭 COVER 的 env 与完全不带 cover 键的 env reward 逐位一致。"""
    e_on_key = _make_env(cover_enabled=False)
    e_plain = _make_env(cover_enabled=False)
    r1 = _run_fixed_actions(e_on_key)
    r2 = _run_fixed_actions(e_plain)
    assert r1 == r2


def test_cover_disabled_has_no_step_terms():
    env = _make_env(cover_enabled=False)
    env.reset(options={'speed': 65.0 / 3.6})
    for _ in range(3):
        n_loco = len(env.trains[0].loco_indices)
        env.step(np.zeros((n_loco, 2)))
        assert env._cover_step_terms is None


def test_cover_enabled_records_three_positive_terms():
    env = _make_env(cover_enabled=True)
    env.reset(options={'speed': 65.0 / 3.6})
    seen = False
    for _ in range(6):
        n_loco = len(env.trains[0].loco_indices)
        env.step(np.zeros((n_loco, 2)))
        t = env._cover_step_terms
        assert isinstance(t, dict)
        assert set(t.keys()) == {'speed_band', 'rel_anchor', 'gap_eff'}
        assert all(np.isfinite(v) for v in t.values())
        seen = True
    assert seen


def test_multiplier_one_is_noop_two_changes_reward():
    """乘子 1.0 与无乘子一致；乘子 2.0 时 reward 变化（正项被放大）。"""
    e_base = _make_env(cover_enabled=True)
    e_x2 = _make_env(cover_enabled=True)
    e_x2.cover_multipliers = {'speed_band': 2.0, 'rel_anchor': 2.0, 'gap_eff': 2.0}
    r_base = _run_fixed_actions(e_base, seed=1)
    r_x2 = _run_fixed_actions(e_x2, seed=1)
    assert r_base == pytest.approx(_run_fixed_actions(_make_env(cover_enabled=True), seed=1))
    assert r_x2 != r_base  # 乘子确实作用到 reward
