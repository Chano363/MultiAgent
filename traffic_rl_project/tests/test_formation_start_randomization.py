"""Paired, opt-in native fleet initial conditions and validity checks."""
import numpy as np
import pytest

from src.environments.train_fleet_env import TrainFleetEnv


def config(**updates):
    cfg = {
        'num_trains': 3, 'consist_preset': '20kt_1plus108_1plus108',
        'grade_profile': 'shuozhou_ningwuxi_beidaniu_49km',
        'decompose': 'loco_ed_ab', 'max_steps': 2,
        'formation_start_randomization': {
            'enabled': True, 'seed': 7,
            'speed_offset_kmh': [-5, 5], 'gap_offset_m': [-50, 200],
        },
    }
    cfg.update(updates)
    return cfg


def test_paired_schemas_have_identical_initial_state_sequences():
    a = TrainFleetEnv(config())
    b = TrainFleetEnv(config(formation_relative_speed_obs=True))
    seen = []
    try:
        for _ in range(8):
            oa, ia = a.reset(options={'speed': 65 / 3.6})
            ob, ib = b.reset(options={'speed': 65 / 3.6})
            np.testing.assert_array_equal(oa, ob[:, :12])
            assert ia == ib
            snapshot = ia['formation_initialization']
            assert snapshot['sampled']
            for x, y in zip(a.trains, b.trains):
                np.testing.assert_array_equal(x.dynamics.pos, y.dynamics.pos)
                np.testing.assert_array_equal(x.dynamics.vel, y.dynamics.vel)
            for item in snapshot['context']:
                assert 60 <= item['head_speed_mps'] * 3.6 <= 70
                if item['train_index']:
                    assert -50 <= item['gap_error_m'] <= 200
                    assert item['gap_m'] > 0
            seen.append(snapshot['context'][0]['head_speed_mps'])
        assert len(set(seen)) == len(seen)
    finally:
        a.close()
        b.close()


def test_explicit_reset_seed_replays_initial_conditions():
    env = TrainFleetEnv(config())
    try:
        a, ia = env.reset(seed=11, options={'speed': 65 / 3.6})
        env.step(np.zeros((6, 2)))
        b, ib = env.reset(seed=11, options={'speed': 65 / 3.6})
        np.testing.assert_array_equal(a, b)
        assert ia == ib
    finally:
        env.close()


def test_evaluation_skips_randomization_and_disabled_mode_preserves_reset_info():
    env = TrainFleetEnv(config(eval_mode=True))
    base_cfg = config()
    base_cfg['formation_start_randomization']['enabled'] = False
    base = TrainFleetEnv(base_cfg)
    try:
        a, info = env.reset(options={'speed': 65 / 3.6})
        b, old_info = base.reset(options={'speed': 65 / 3.6})
        np.testing.assert_array_equal(a, b)
        assert info['formation_initialization']['sampled'] is False
        assert old_info == {}
    finally:
        env.close()
        base.close()


@pytest.mark.parametrize('key,value,match', [
    ('gap_offset_m', [-200, 0], 'overlapping'),
    ('speed_offset_kmh', [-70, 0], 'speed offset'),
    ('speed_offset_kmh', [0, 20], 'speed offset'),
    ('speed_offset_kmh', [5, -5], 'finite'),
    ('gap_offset_m', [0, float('nan')], 'finite'),
])
def test_invalid_ranges_fail_without_silent_clipping(key, value, match):
    cfg = config()
    cfg['formation_start_randomization'][key] = value
    env = None
    try:
        with pytest.raises(ValueError, match=match):
            env = TrainFleetEnv(cfg)
            env.reset(options={'speed': 65 / 3.6})
    finally:
        if env is not None:
            env.close()


def test_initial_supervision_is_reported_not_silently_discarded():
    cfg = config()
    cfg['formation_start_randomization'].update(speed_offset_kmh=[-5, 5],
                                               gap_offset_m=[-180, -180])
    env = TrainFleetEnv(cfg)
    try:
        _, info = env.reset(options={'speed': 65 / 3.6})
        supervision = info['formation_initialization']['supervision']
        assert len(supervision) == 2
        assert any(item['above_ebi'] for item in supervision)
        assert all(item['gap_m'] > 0 for item in env.get_formation_context()[1:])
    finally:
        env.close()


def test_normal_state_filter_is_paired_bounded_and_reports_rejections():
    cfg = config()
    cfg['formation_start_randomization']['require_clear_sbi'] = True
    a = TrainFleetEnv(cfg)
    b = TrainFleetEnv({**cfg, 'formation_relative_speed_obs': True})
    try:
        for _ in range(12):
            oa, ia = a.reset(options={'speed': 65 / 3.6})
            ob, ib = b.reset(options={'speed': 65 / 3.6})
            np.testing.assert_array_equal(oa, ob[:, :12])
            assert ia == ib
            initial = ia['formation_initialization']
            assert initial['require_clear_sbi']
            assert 1 <= initial['attempts'] <= 64
            assert not any(s['above_sbi'] or s['above_ebi'] for s in initial['supervision'])
    finally:
        a.close()
        b.close()
    cfg['formation_start_randomization'].update(max_attempts=1,
                                               gap_offset_m=[-180, -180])
    env = TrainFleetEnv(cfg)
    try:
        with pytest.raises(ValueError, match='No clear-SBI'):
            env.reset(options={'speed': 65 / 3.6})
    finally:
        env.close()
