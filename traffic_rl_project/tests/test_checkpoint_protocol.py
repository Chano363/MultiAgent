"""自包含 checkpoint 协议回归测试（BaseRLAgent 模板方法，2026-09-10）。

验证三件事：
1. save(metadata=...) 把 metadata 嵌入 .pt（对标 YOLO best.pt，单文件可溯源）
2. load 兼容旧版裸 checkpoint（向后兼容，不破坏历史资产）
3. DQN 家族共享 BaseDQNAgent 行为与 MAPPO 统计量的存取一致
"""
import sys
from pathlib import Path

import pytest
import torch


from src.algorithms.mappo_agent import MAPPOAgent
from src.algorithms.dqn_agent import DQNAgent
from src.algorithms.coor_dqn_agent import CoorDQNAgent
from src.algorithms.base_agent import BaseRLAgent, BaseDQNAgent


@pytest.fixture
def mappo():
    return MAPPOAgent(num_drones=3, obs_per_drone=4, act_per_drone=1, device='cpu')


@pytest.fixture
def dqn():
    return DQNAgent(obs_dim=4, device='cpu')


@pytest.fixture
def coor_dqn():
    return CoorDQNAgent(obs_dim=11, device='cpu')


def test_hierarchy():
    """三个 agent 同源：MAPPO/DQN/CoorDQN 均继承 BaseRLAgent。"""
    assert issubclass(MAPPOAgent, BaseRLAgent)
    assert issubclass(DQNAgent, BaseDQNAgent)
    assert issubclass(CoorDQNAgent, BaseDQNAgent)


def test_mappo_save_with_metadata(mappo, tmp_path):
    p = tmp_path / "m.pt"
    mappo.save(str(p), metadata={'seed': 0, 'physics_version': 'test'})
    ck = torch.load(p, map_location='cpu', weights_only=False)
    assert ck['metadata']['seed'] == 0
    assert 'policy_state_dict' in ck and 'value_norm_mean' in ck


def test_mappo_load_legacy_bare_ckpt(mappo, tmp_path):
    """旧版裸 checkpoint（无 metadata/无统计量键）可正常加载。"""
    p = tmp_path / "old.pt"
    torch.save({'policy_state_dict': mappo.policy.state_dict(),
                'value_state_dict': mappo.value.state_dict(),
                'optimizer_state_dict': mappo.optimizer.state_dict()}, p)
    b = MAPPOAgent(num_drones=3, obs_per_drone=4, act_per_drone=1, device='cpu')
    ck = b.load(str(p))
    assert 'metadata' not in ck and b.training_step == 0


def test_mappo_save_without_metadata_matches_legacy(mappo, tmp_path):
    """不传 metadata 时与旧行为一致（字典键不变）。"""
    p = tmp_path / "n.pt"
    mappo.save(str(p))
    ck = torch.load(p, map_location='cpu', weights_only=False)
    assert 'metadata' not in ck and 'policy_state_dict' in ck


def test_dqn_family_roundtrip(dqn, coor_dqn, tmp_path):
    meta = {'seed': 1, 'grade': 'shuozhou_23800'}
    p1, p2 = tmp_path / "d.pt", tmp_path / "c.pt"
    dqn.save(str(p1), metadata=meta)
    coor_dqn.save(str(p2), metadata={'seed': 2})

    d2 = DQNAgent(obs_dim=4, device='cpu')
    assert d2.load(str(p1))['metadata']['seed'] == 1
    assert d2.eps == dqn.eps

    c2 = CoorDQNAgent(obs_dim=11, device='cpu')
    ck2 = c2.load(str(p2))
    assert ck2['metadata']['seed'] == 2 and c2.num_actions == 5
    assert coor_dqn.action_to_coor(2) == 0.0  # 中间档 = 无偏移


def test_dqn_load_legacy_bare_ckpt(coor_dqn, tmp_path):
    """旧版裸 checkpoint（q_net + eps）兼容。"""
    p = tmp_path / "old.pt"
    torch.save({'q_net': coor_dqn.q_net.state_dict(), 'eps': 0.5}, p)
    c = CoorDQNAgent(obs_dim=11, device='cpu')
    ck = c.load(str(p))
    assert 'metadata' not in ck and abs(c.eps - 0.5) < 1e-9
