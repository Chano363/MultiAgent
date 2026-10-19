"""Precise line-speed units must preserve intended at-limit supervision."""
from pathlib import Path

import numpy as np
import pytest
import yaml

from src.environments.train_fleet_env import TrainFleetEnv


ROOT = Path(__file__).resolve().parents[1]


@pytest.mark.parametrize('filename', [
    'single_10kt108_coupler_rulecal.yaml',
    'formation_ed_ab_3train_1plus108.yaml',
])
def test_current_80_kmh_limit_keeps_conversion_precision(filename):
    config = yaml.safe_load((ROOT / 'configs/experiments' / filename).read_text(encoding='utf-8'))
    assert config['env_cfg']['v_max'] == 80.0 / 3.6


@pytest.mark.parametrize('speed_kmh,expect_overspeed', [(79.9996, False), (80.0, True), (80.001, True)])
def test_startup_supervision_preserves_the_at_limit_braking_rule(speed_kmh, expect_overspeed):
    path = ROOT / 'configs/experiments/single_10kt108_coupler_rulecal.yaml'
    cfg = yaml.safe_load(path.read_text(encoding='utf-8'))['env_cfg']
    cfg.update(num_trains=1, start_randomization={'enabled': False}, eval_mode=True)
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
