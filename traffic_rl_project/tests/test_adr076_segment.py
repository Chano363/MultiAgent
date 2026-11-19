# -*- coding: utf-8 -*-
"""ADR-076（M-A offset 参数化 + M-B 分段权重调度）单测。

覆盖：
  M-A ① 默认 leader_tail_offset_mps == 5.0（= 原类常量 ⇒ 零回归）
      ② 默认 follower_chase_offset_mps == 5.0
      ③ 段查询：未配置 ⇒ 空 dict；落在段内 ⇒ 该段权重；段外 ⇒ default
      ④ 迟滞带归属正确
  M-B ⑤ 默认（空配置）⇒ 段系数全 1.0 ⇒ reward 逐位不变
      ⑥ 段内只缩放指定正项，负罚项恒定
"""
import inspect

import pytest

from src.environments.train_fleet_env import TrainFleetEnv


# ---------------------------------------------------------------- M-A
def test_offset_defaults_equal_class_constants():
    """零回归前提：默认 offset 必须等于改动前的类常量。"""
    assert TrainFleetEnv.LEAD_TAIL_OFFSET_MPS == 5.0
    assert TrainFleetEnv.FOLLOWER_CHASE_OFFSET_MPS == 5.0
    init_src = inspect.getsource(TrainFleetEnv.__init__)
    assert "config.get('leader_tail_offset_mps', self.LEAD_TAIL_OFFSET_MPS)" in init_src
    assert ("config.get('follower_chase_offset_mps', "
            "self.FOLLOWER_CHASE_OFFSET_MPS)") in init_src


def test_offset_params_are_independent():
    """两项语义不同 ⇒ 必须独立参数化（改一个不连带另一个）。"""
    init_src = inspect.getsource(TrainFleetEnv.__init__)
    assert "self.leader_tail_offset_mps" in init_src
    assert "self.follower_chase_offset_mps" in init_src
    src = inspect.getsource(TrainFleetEnv)
    # 使用点：leader 迁就用 leader_*，follower 上限用 follower_*
    assert "tail_speed + self.leader_tail_offset_mps" in src
    assert "lead_speed + self.follower_chase_offset_mps" in src
    # 不得有残留：follower 上限不得再用 leader 的参数
    assert "lead_speed + self.LEAD_TAIL_OFFSET_MPS" not in src


# ---------------------------------------------------------------- M-B
def _env_with(segment_weights=None, default=None, hys=0.0):
    """构造一个只带段查询方法的最小桩（不跑物理，避免重依赖）。"""
    env = TrainFleetEnv.__new__(TrainFleetEnv)
    env.segment_reward_weights = list(segment_weights or [])
    env.segment_reward_weights_default = dict(default or {})
    env.segment_weight_hysteresis_m = float(hys)
    env.segment_weight_terms = ("speed_band", "rel_anchor", "gap_eff")
    env._train_heads = [1000.0, 900.0, 800.0]
    return env


def test_segment_weights_disabled_returns_empty():
    """未配置分段 ⇒ 空 dict ⇒ 调用方按 1.0 处理（零回归）。"""
    env = _env_with()
    assert env._segment_weights(1000.0) == {}


def test_segment_weights_lookup_by_position():
    env = _env_with([
        {"start_m": 0.0, "end_m": 5000.0, "weights": {"gap_eff": 0.0}},
        {"start_m": 5000.0, "end_m": 20000.0, "weights": {"gap_eff": 2.0}},
    ])
    assert env._segment_weights(1000.0) == {"gap_eff": 0.0}
    assert env._segment_weights(10000.0) == {"gap_eff": 2.0}
    assert env._segment_weights(30000.0) == {}


def test_segment_weights_default_outside_all_segments():
    env = _env_with(
        [{"start_m": 0.0, "end_m": 5000.0, "weights": {"gap_eff": 0.0}}],
        default={"gap_eff": 1.5})
    assert env._segment_weights(30000.0) == {"gap_eff": 1.5}


def test_segment_weights_hysteresis_holds_segment():
    """迟滞带内仍归属本段（防边界抖动）。"""
    env = _env_with(
        [{"start_m": 10000.0, "end_m": 20000.0, "weights": {"gap_eff": 3.0}}],
        default={}, hys=500.0)
    assert env._segment_weights(9800.0) == {"gap_eff": 3.0}   # 迟滞带内
    assert env._segment_weights(20200.0) == {"gap_eff": 3.0}  # 迟滞带内
    assert env._segment_weights(9400.0) == {}                 # 迟滞带外（带下界 9500）


def test_segment_weights_only_scales_positive_terms():
    """分段系数只作用于 3 正项；负罚项不得被缩放。"""
    src = inspect.getsource(TrainFleetEnv._calculate_reward_decomposed)
    assert "speed_band_reward *= float(_seg_w.get('speed_band', 1.0))" in src
    assert "rel_anchor_reward *= float(_seg_w.get('rel_anchor', 1.0))" in src
    assert "gap_eff_reward *= float(_seg_w.get('gap_eff', 1.0))" in src
    for neg in ("force_penalty", "gap_danger_penalty", "coupler_peak_term",
                "coupler_over_term", "pressure_gradient_penalty",
                "notch_smooth_term", "ab_cost", "ed_cost"):
        assert ("%s *= float(_seg_w" % neg) not in src, \
            "负罚项 %s 不得被分段权重缩放" % neg
