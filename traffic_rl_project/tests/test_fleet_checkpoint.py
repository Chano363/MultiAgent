from pathlib import Path
import tempfile
import numpy as np
import pytest
import yaml

from src.environments.train_fleet_env import TrainFleetEnv
from src.evaluation.fleet_checkpoint import save_fleet_checkpoint, load_fleet_checkpoint


def test_three_train_history_roundtrip_and_payload_guard():
    cfg = yaml.safe_load(Path('configs/experiments/formation_ed_ab_3train_1plus108.yaml').read_text(encoding='utf-8'))['env_cfg']
    cfg.update(eval_mode=True, max_steps=50, start_randomization={'enabled': False})
    env = TrainFleetEnv(cfg)
    restored = None
    root = Path('outputs/sim_validation/phys_validation')
    root.mkdir(parents=True, exist_ok=True)
    try:
        env.reset(seed=0, options={'speed': 70/3.6})
        zero = np.zeros((env.num_agents, 2))
        env.step(zero)
        with tempfile.TemporaryDirectory(prefix='fleet_checkpoint_test_', dir=root) as directory:
            save_fleet_checkpoint(env, directory, {'solver': 'native', 'source_sha256': {}})
            restored, manifest = load_fleet_checkpoint(directory)
            assert manifest['num_trains'] == 3
            env.step(zero)
            restored.step(zero)
            for a, b, ca, cb in zip(env.trains, restored.trains,
                    env.multi_loco_controllers, restored.multi_loco_controllers):
                for key in ('pos', 'vel', '_acc0', '_brake_pressure', '_air_brake_active', '_air_brake_release_frac'):
                    np.testing.assert_array_equal(getattr(a.dynamics, key), getattr(b.dynamics, key))
                assert ca._ab_step == cb._ab_step
                assert ca._ab_last_release_step == cb._ab_last_release_step
            path = Path(directory)/'fleet_state.pkl'
            path.write_bytes(path.read_bytes()+b'changed')
            with pytest.raises(ValueError):
                load_fleet_checkpoint(directory)
    finally:
        env.close()
        if restored is not None:
            restored.close()
