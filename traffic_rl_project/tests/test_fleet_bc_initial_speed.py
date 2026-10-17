"""BC receives the configured speed through the real native training path."""
import pytest
import torch

from src.trainer.config_schema import CkptDirs, ExperimentConfig
from src.trainer.train_runner import TrainRunner
from src.trainer.specs import fleet_spec
from src.algorithms.mappo_agent import MAPPOAgent
from src.environments.train_fleet_env import TrainFleetEnv


@pytest.mark.parametrize('explicit_speed, expected', [(None, 65.0), (64.0, 64.0)])
def test_bc_initial_speed_matches_config(tmp_path, monkeypatch, explicit_speed, expected):
    env_cfg = {
        'num_trains': 3, 'consist_preset': '20kt_1plus108_1plus108',
        'grade_profile': 'shuozhou_ningwuxi_beidaniu_49km',
        'decompose': 'loco_ed_ab', 'max_steps': 2,
        'formation_start_randomization': {
            'enabled': True, 'speed_offset_kmh': [-5, 5],
            'gap_offset_m': [0, 200], 'require_clear_sbi': True,
        },
    }
    if explicit_speed is not None:
        env_cfg['init_speed_kmh'] = explicit_speed
    original = fleet_spec.warm_start_decompose_bc
    captured = []

    def short_native_bc(agent, env, **kwargs):
        captured.append(kwargs['init_speed'] * 3.6)
        # Only shorten collection; retain the real simulator and BC optimizer.
        return original(agent, env, max_steps=2, **kwargs)

    monkeypatch.setattr(fleet_spec, 'warm_start_decompose_bc', short_native_bc)
    cfg = ExperimentConfig(
        env_cfg=env_cfg, episodes=1, curriculum='2:0', init_speed_kmh=65,
        warm_start=True, bc_episodes=1, bc_epochs=1, yolo_logging=False,
        yolo_tb=False, algo_params={'batch_size': 2, 'epochs': 1},
        dirs=CkptDirs(*(str(tmp_path / n) for n in ['checkpoints', 'results', 'figures'])),
    )
    result = TrainRunner(cfg).run()
    assert captured == pytest.approx([expected])
    assert len(result['rewards']) == 1
    assert (tmp_path / 'results' / 'metadata.json').exists()


def test_bc_uses_own_learning_rate_without_mutating_rl_optimizer():
    torch.manual_seed(0)
    env = TrainFleetEnv({
        'num_trains': 3, 'consist_preset': '20kt_1plus108_1plus108',
        'grade_profile': 'shuozhou_ningwuxi_beidaniu_49km',
        'decompose': 'loco_ed_ab', 'max_steps': 2,
    })
    try:
        agent = MAPPOAgent(6, 12, 2, device='cpu', learning_rate=0.00002)
        before = [p.detach().clone() for p in agent.policy.parameters()]
        rates = [g['lr'] for g in agent.optimizer.param_groups]
        assert not agent.optimizer.state
        fleet_spec.warm_start_decompose_bc(
            agent, env, episodes=1, bc_epochs=1, max_steps=2,
            init_speed=65 / 3.6, lr=0.001,
        )
        change = max(float((a - b.detach()).abs().max())
                     for a, b in zip(before, agent.policy.parameters()))
        assert change > 0.0001  # A step at the RL rate cannot reach this.
        assert [g['lr'] for g in agent.optimizer.param_groups] == rates
        assert not agent.optimizer.state
    finally:
        env.close()
