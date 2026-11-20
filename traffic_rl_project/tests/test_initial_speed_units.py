"""Precise line-speed units must preserve intended at-limit supervision."""
from pathlib import Path

import numpy as np
import pytest
import yaml

from src.environments.train_fleet_env import TrainFleetEnv


ROOT = Path(__file__).resolve().parents[1]


@pytest.mark.parametrize('filename,expected_kmh', [
    # 【ADR-068 2026-11-13】全局上界 v_max 由 80 改为 75 km/h（宁武西—北大牛
    # 分段限速表最高 75，见 V01；80 无依据）。逐配置跟随现行口径：
    #   - single_10kt108_coupler_rulecal.yaml = 80 km/h 旧口径存档（该 YAML 首行
    #     明确标注「⛔ 旧口径 v_max=80，其结果不得与 v_max=75 口径并列引用」）；
    #   - formation_ed_ab_3train_1plus108.yaml = 75 km/h 现行口径（ADR-068 锁定）。
    # 本测的守护点不是"80 这个数"，而是**线速单位换算必须精确**（YAML 里存
    # km/h ÷ 3.6 的精确值，贴线速判定才不会被浮点误差击穿）。
    ('single_10kt108_coupler_rulecal.yaml', 80.0),
    ('formation_ed_ab_3train_1plus108.yaml', 75.0),
])
def test_line_speed_limit_keeps_conversion_precision(filename, expected_kmh):
    config = yaml.safe_load((ROOT / 'configs/experiments' / filename).read_text(encoding='utf-8'))
    assert config['env_cfg']['v_max'] == expected_kmh / 3.6


@pytest.mark.parametrize('speed_kmh,expect_overspeed', [(79.9996, False), (80.0, True), (80.001, True)])
def test_startup_supervision_preserves_the_at_limit_braking_rule(speed_kmh, expect_overspeed):
    """贴线速 80 的精确判定（无表剖面 → 线速门恒 80/3.6，联动关闭）。

    【ADR-060 联动解耦】shuozhou 剖面起步（K15.9）处分段限速 70 km/h，联动会把
    线速门拉到 70、覆盖"80 转换精度"语义；本测试改用无限速表的 long_downhill
    剖面保持原语义，联动语义见 test_startup_supervision_line_limit_linkage。
    """
    path = ROOT / 'configs/experiments/single_10kt108_coupler_rulecal.yaml'
    cfg = yaml.safe_load(path.read_text(encoding='utf-8'))['env_cfg']
    cfg.update(num_trains=1, start_randomization={'enabled': False}, eval_mode=True,
               grade_profile='long_downhill')
    env = TrainFleetEnv(cfg)
    try:
        env.reset(seed=0, options={'speed': speed_kmh / 3.6})
        train = env.trains[0]
        assert train.dynamics._brake_segment == 0
        env.step(np.zeros((env.num_agents, 2)))
        events = train.safety.last_events
        assert any(event.get('rule') == 'overspeed' for event in events) == expect_overspeed
        if expect_overspeed:
            assert train.dynamics._brake_segment == 1
            assert np.any(train.dynamics._air_brake_active)
        else:
            assert train.dynamics._brake_segment == 0
            assert not np.any(train.dynamics._air_brake_active)
    finally:
        env.close()


@pytest.mark.parametrize('speed_kmh,expect_overspeed',
                         [(69.9996, False), (70.0, True), (79.9996, True)])
def test_startup_supervision_line_limit_linkage(speed_kmh, expect_overspeed):
    """【ADR-060 限速逐段联动】起步监督按头车位置分段限速联动：
    shuozhou 49km 剖面起步（K15.9 = 0 m）处限速 70 km/h → 线速门 = 70/3.6，
    69.9996 不超、70.0 及以上触发安全层强制制动（brake_segment=1）。"""
    path = ROOT / 'configs/experiments/single_10kt108_coupler_rulecal.yaml'
    cfg = yaml.safe_load(path.read_text(encoding='utf-8'))['env_cfg']
    cfg.update(num_trains=1, start_randomization={'enabled': False}, eval_mode=True)
    env = TrainFleetEnv(cfg)   # grade_profile 沿用 YAML = shuozhou_ningwuxi_beidaniu_49km
    try:
        # lookup 暴露在内层单列 env 上（动态代理，随 dynamics 当前剖面生效）
        assert env.trains[0].line_limit_lookup_kmh(0.0) == pytest.approx(70.0)
        env.reset(seed=0, options={'speed': speed_kmh / 3.6})
        train = env.trains[0]
        assert train.dynamics._brake_segment == 0
        env.step(np.zeros((env.num_agents, 2)))
        events = train.safety.last_events
        assert any(event.get('rule') == 'overspeed' for event in events) == expect_overspeed
        if expect_overspeed:
            assert train.dynamics._brake_segment == 1
            assert np.any(train.dynamics._air_brake_active)
        else:
            assert train.dynamics._brake_segment == 0
            assert not np.any(train.dynamics._air_brake_active)
    finally:
        env.close()
