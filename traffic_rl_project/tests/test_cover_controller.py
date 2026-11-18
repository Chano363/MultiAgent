"""COVER 控制器单测（Lu 2026 arXiv:2602.06869 + owner 锁定语义）。

验收点：
1. 协方差符号正确（正/负/零）；
2. 单边提权：cov < target 才提，cov >= target 不动；
3. clip 上界不漂移；
4. 只对 3 个正项提权，负罚项不进控制器；
5. 默认乘子 1.0 = 零回归；
6. state_dict 往返一致。
"""
import numpy as np
import pytest

from src.algorithms.cover_controller import COVER_POSITIVE_TERMS, CoverController


def test_covariance_sign():
    assert CoverController.covariance([1, 2, 3], [1, 2, 3]) > 0
    assert CoverController.covariance([1, 2, 3], [3, 2, 1]) < 0
    assert abs(CoverController.covariance([1, 2, 3], [2, 2, 2])) < 1e-12  # 零方差
    assert CoverController.covariance([1], [1]) == 0.0  # 样本不足


def test_default_is_noop():
    c = CoverController()
    assert all(v == 1.0 for v in c.multipliers.values())
    assert tuple(c.terms) == COVER_POSITIVE_TERMS
    assert 'speed_over' not in c.multipliers  # 负罚项不参与
    assert 'gap_danger' not in c.multipliers
    assert 'notch_smooth' not in c.multipliers


def test_one_sided_upweight_on_negative_cov():
    c = CoverController(target_cov=0.0, up_factor=1.1)
    # gap_eff 与 clipped_adv 反相关 ⇒ cov<0 ⇒ 提权
    term_vals = {k: [3, 2, 1] for k in COVER_POSITIVE_TERMS}
    out = c.observe(term_vals, clipped_adv_weight=[1, 2, 3])
    assert out['gap_eff'] == pytest.approx(1.1)
    assert out['rel_anchor'] == pytest.approx(1.1)
    assert out['speed_band'] == pytest.approx(1.1)


def test_no_downweight_on_positive_cov():
    c = CoverController(target_cov=0.0, up_factor=1.1)
    term_vals = {k: [1, 2, 3] for k in COVER_POSITIVE_TERMS}
    out = c.observe(term_vals, clipped_adv_weight=[1, 2, 3])  # 正相关
    assert all(v == 1.0 for v in out.values())  # 不降权


def test_clip_upper_bound():
    c = CoverController(target_cov=0.0, up_factor=2.0, weight_max=3.0)
    term_vals = {k: [3, 2, 1] for k in COVER_POSITIVE_TERMS}
    for _ in range(10):
        out = c.observe(term_vals, clipped_adv_weight=[1, 2, 3])
    assert out['gap_eff'] == pytest.approx(3.0)  # 不得越过上界漂移


def test_all_positive_terms_present_even_if_one_missing():
    c = CoverController()
    # 只给一个项的数据，其余项乘子仍返回且保持 1.0
    out = c.observe({'gap_eff': [3, 2, 1]}, clipped_adv_weight=[1, 2, 3])
    assert out['gap_eff'] > 1.0
    assert out['speed_band'] == 1.0


def test_state_dict_roundtrip():
    c = CoverController(up_factor=1.2, weight_max=2.5)
    c.observe({k: [3, 2, 1] for k in COVER_POSITIVE_TERMS}, [1, 2, 3])
    s = c.state_dict()
    c2 = CoverController()
    c2.load_state_dict(s)
    assert c2.multipliers == c.multipliers
    assert c2.update_count == c.update_count
    assert c2.up_factor == c.up_factor
    assert c2.weight_max == c.weight_max
    assert tuple(c2.terms) == tuple(c.terms)


def test_target_cov_gate_stricter():
    # cov([1,2,3],[3,2,1]) = -2/3 ≈ -0.667（总体协方差）
    # target=-0.9 更宽松：-0.667 > -0.9 ⇒ 不提（验证 gate 方向）；
    # target=-0.5 更严格：-0.667 < -0.5 ⇒ 提权。
    c = CoverController(target_cov=-0.9, up_factor=1.1)
    out = c.observe({'gap_eff': [1, 2, 3]}, clipped_adv_weight=[3, 2, 1])
    assert out['gap_eff'] == 1.0  # 协方差高于地板 ⇒ 不动
    c2 = CoverController(target_cov=-0.5, up_factor=1.1)
    out2 = c2.observe({'gap_eff': [1, 2, 3]}, clipped_adv_weight=[3, 2, 1])
    assert out2['gap_eff'] > 1.0  # 协方差低于地板 ⇒ 提权
