"""
ADR-021/043 单测：车钩力"受控超限项"进 reward + 峰值改断面力口径。

验证：
- REWARD_SCHEMA / COUPLER_OVER_W / COUPLER_OVER_CAP 常量存在且取值正确；
- peak_norm <= 1（未破线）时超限项恒为 0；
- peak_norm = 1.5 → 约 -3.0；peak_norm = 5（>3× 上限）→ 限幅到 -12.0。
"""

import numpy as np
import pytest

from src.environments.train_fleet_env import (
    TrainFleetEnv, REWARD_SCHEMA, COUPLER_OVER_W, COUPLER_OVER_CAP, COUPLER_PEAK_W,
)
from src.environments.train_env import COUPLER_FORCE_LIMIT_N


class _VelTrain:
    def __init__(self, v):
        self.dynamics = type('D', (), {'vel': np.array([v], dtype=float)})()


def _reward_env():
    """绕过 __init__ 构造一个只够 _calculate_reward_decomposed 用的环境骨架。"""
    env = object.__new__(TrainFleetEnv)
    env.v_min = 40.0 / 3.6
    env.v_max = 80.0 / 3.6
    env.num_trains = 1
    env.num_agents = 2
    env.coupler_force_limit_n = COUPLER_FORCE_LIMIT_N
    env.REL_ANCHOR_SPD_SCALE = 3.0
    env.REL_ANCHOR_SPD_W = 2.0
    env._prev_gap_err = None
    env.trains = [_VelTrain(20.0)]
    return env


def _over_term(env, peak_n):
    """从总 reward 中剥离出「超限项」：reward(p) - reward(0) - peak_term(p)。

    v6（ADR-043）奖励函数已无 obs/accels 参数，车钩项只有峰值比塑形
    peak_term(p) = -COUPLER_PEAK_W*(1-exp(-p/limit)) 与超限项；其余项与 peak 无关。
    故 over_term(p) = (r(p) - r(0)) - peak_term(p)（base 取 p=0，此时两项均为 0）。
    """
    limit = env.coupler_force_limit_n
    base = env._calculate_reward_decomposed(0, 0.0, step_coupler_peak_n=0.0)
    r = env._calculate_reward_decomposed(0, 0.0, step_coupler_peak_n=peak_n)
    peak_term = -COUPLER_PEAK_W * (1.0 - float(np.exp(-peak_n / limit)))
    return (r - base) - peak_term


def test_reward_schema_constants_exist():
    # 【ADR-026】奖励口径变更为 v3（ATP 对齐间距）；【ADR-028】→ v4（穿透危险项有界化）；
    # 【ADR-036 2026-10-14】→ v5（限值成为 env 可配档，超限项分母随运行档位变）；
    # 【ADR-043 2026-10-20】→ v6（13 项收敛为 6 个文献槽位，删车钩均值项）。
    # 超限项常量本身沿用 ADR-021。
    assert REWARD_SCHEMA == 'v6-literature-slots'
    assert COUPLER_OVER_W == 6.0
    assert COUPLER_OVER_CAP == 2.0


def test_overlimit_term_zero_below_limit():
    env = _reward_env()
    limit = env.coupler_force_limit_n
    assert _over_term(env, 0.5 * limit) == pytest.approx(0.0, abs=1e-9)
    assert _over_term(env, 1.0 * limit) == pytest.approx(0.0, abs=1e-9)


def test_overlimit_term_linear_then_capped():
    env = _reward_env()
    limit = env.coupler_force_limit_n
    # peak_norm=1.5 → -6.0*0.5 = -3.0
    assert _over_term(env, 1.5 * limit) == pytest.approx(-3.0, abs=1e-9)
    # peak_norm=5（over=4 → 限幅到 CAP=2）→ -12.0
    assert _over_term(env, 5.0 * limit) == pytest.approx(-12.0, abs=1e-9)
    # 更深也不超过 -12
    assert _over_term(env, 10.0 * limit) == pytest.approx(-12.0, abs=1e-9)