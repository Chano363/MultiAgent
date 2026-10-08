"""训练框架续训（resume）回归测试。

覆盖 src/trainer/resume.py 的解析/进度读取/历史拼接，以及 checkpoint 协议扩展：
- resolve_checkpoint：路径不存在 → 抛错（禁止静默从头）；'latest' 选中最新 ep
- plan_run_episodes：--episodes = 总目标集数 → 实跑 = 总 - 已训；目标 ≤ 已训 → 抛错
- read_progress：进度信号优先级（start_ep > metadata.done_ep > history 行数 > 文件名）
- load_source_history：从源 results 目录拼接既有曲线
- weights_only 续训：只加载权重，优化器/value_norm 重置
- RNG 状态随 checkpoint 保存/恢复
"""
import json
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest
import torch

from src.algorithms.mappo_agent import MAPPOAgent
from src.trainer import resume as R


def _agent():
    return MAPPOAgent(num_drones=3, obs_per_drone=4, act_per_drone=1, device='cpu')


def _cfg(**kw):
    base = dict(resume='', resume_weights_only=False, start_ep=-1, seed=0,
                episodes=10, checkpoint_dir='.')
    base.update(kw)
    return SimpleNamespace(**base)


def _save_ckpt(path, metadata=None, populate_optimizer=True, value_norm_count=0):
    a = _agent()
    if populate_optimizer:  # 伪造一步优化器状态，供 weights_only 对比
        a.policy.zero_grad()
        sum(p.pow(2).sum() for p in a.policy.parameters()).backward()
        a.optimizer.step()
    if value_norm_count:
        a.value_norm.update(np.array([-30000.0, -28000.0, -32000.0, -15000.0]))
    a.save(str(path), metadata=metadata)
    return a


# ---------------------------------------------------------------- resolve

def test_resolve_missing_path_raises(tmp_path):
    """路径写错必须抛错（旧行为会静默从头重训 → 白跑数小时）。"""
    cfg = _cfg(resume=str(tmp_path / 'nope.pt'))
    with pytest.raises(FileNotFoundError):
        R.resolve_checkpoint(cfg)


def test_resolve_empty_raises():
    with pytest.raises(ValueError):
        R.resolve_checkpoint(_cfg(resume=''))


def test_resolve_latest(tmp_path):
    _save_ckpt(tmp_path / 'mappo_fleet_ep10_dec_ad2_cp_seed0.pt')
    _save_ckpt(tmp_path / 'mappo_fleet_ep30_dec_ad2_cp_seed0.pt')
    _save_ckpt(tmp_path / 'mappo_fleet_best_dec_ad2_cp_seed0.pt')  # 无 ep 号，不参与
    cfg = _cfg(resume='latest', checkpoint_dir=str(tmp_path))
    picked = R.resolve_checkpoint(cfg)
    assert 'ep30' in picked


def test_resolve_latest_empty_dir_raises(tmp_path):
    with pytest.raises(FileNotFoundError):
        R.resolve_checkpoint(_cfg(resume='latest', checkpoint_dir=str(tmp_path)))


# ------------------------------------------------------- episode semantics

def test_plan_run_episodes_total_semantics():
    """--episodes = 总目标：done=8, total=10 → 实跑 2。"""
    assert R.plan_run_episodes(_cfg(episodes=10), 8) == 2


def test_plan_run_episodes_leq_done_raises():
    with pytest.raises(ValueError):
        R.plan_run_episodes(_cfg(episodes=8), 8)
    with pytest.raises(ValueError):
        R.plan_run_episodes(_cfg(episodes=5), 8)


# ------------------------------------------------------------ read_progress

def test_progress_from_metadata_precedence(tmp_path):
    """metadata.done_ep 优先于文件名。"""
    _save_ckpt(tmp_path / 'mappo_fleet_ep30_dec_ad2_cp_seed0.pt',
               metadata={'seed': 0, 'done_ep': 42, 'best_reward': 1234.0})
    plan = R.read_progress(_cfg(), str(tmp_path / 'mappo_fleet_ep30_dec_ad2_cp_seed0.pt'))
    assert plan.done_ep == 42
    assert plan.best_reward == 1234.0


def test_progress_start_ep_override_wins(tmp_path):
    """--override start_ep=N 是人工校正逃生口，优先级最高。"""
    p = tmp_path / 'mappo_fleet_ep30_dec_ad2_cp_seed0.pt'
    _save_ckpt(p, metadata={'seed': 0, 'done_ep': 42})
    plan = R.read_progress(_cfg(start_ep=55), str(p))
    assert plan.done_ep == 55


def test_progress_fallback_to_filename(tmp_path):
    """旧格式裸 checkpoint（无 metadata.done_ep）→ 回退文件名 _ep{N}。"""
    p = tmp_path / 'mappo_fleet_ep30_dec_ad2_cp_seed0.pt'
    torch.save({'policy_state_dict': _agent().policy.state_dict()}, p)
    plan = R.read_progress(_cfg(), str(p))
    assert plan.done_ep == 30


def test_progress_splices_history(tmp_path):
    """源 results 目录的 train_history 被拼接（学习曲线连续）。"""
    cp = tmp_path / 'cp'
    res = cp / 'results'
    res.mkdir(parents=True)
    p = cp / 'mappo_fleet_best_dec_ad2_cp_seed0.pt'
    _save_ckpt(p, metadata={'seed': 0})  # 无 done_ep
    (res / 'train_history_dec_ad2_cp_seed0.json').write_text(json.dumps({
        'rewards': [1.0, 2.0, 3.0],
        'peak_coupler_kN': [10.0, 20.0, 30.0],
        'violations': [0, 1, 0],
        'meta': {'best_reward': 3.0},
    }), encoding='utf-8')
    plan = R.read_progress(_cfg(), str(p))
    assert plan.done_ep == 3
    assert plan.prior_rewards == [1.0, 2.0, 3.0]
    assert plan.prior_peak == [10.0, 20.0, 30.0]
    assert plan.best_reward == 3.0


def test_load_source_history_empty_dir(tmp_path):
    assert R.load_source_history(str(tmp_path), 0) == ([], [], [], {})


# --------------------------------------------------------- weights_only / RNG

def test_weights_only_resets_optimizer_and_value_norm(tmp_path):
    p = tmp_path / 'm.pt'
    src = _save_ckpt(p, metadata={'seed': 0}, value_norm_count=4)
    assert len(src.optimizer.state) > 0 and src.value_norm.count == 4

    w = _agent()
    w.load(str(p), weights_only=True)
    assert len(w.optimizer.state) == 0, "weights_only 应重置优化器状态"
    assert w.value_norm.count == 0, "weights_only 应重置 value_norm"
    # 权重仍一致
    for k, v in src.policy.state_dict().items():
        assert torch.equal(v, w.policy.state_dict()[k])

    full = _agent()
    full.load(str(p), weights_only=False)
    assert len(full.optimizer.state) > 0
    assert full.value_norm.count == 4


def test_rng_state_roundtrip(tmp_path):
    """完整续训恢复 RNG：续训抽样的随机数与保存时刻一致。"""
    p = tmp_path / 'r.pt'
    np.random.seed(1234)
    _agent().save(str(p))
    np.random.seed(1234)
    expected = np.random.rand(3)

    np.random.seed(9999)
    np.random.rand(7)  # 污染 RNG 状态
    _agent().load(str(p))
    got = np.random.rand(3)
    assert np.allclose(got, expected)


@pytest.mark.skipif(not torch.cuda.is_available(), reason="需 CUDA 复现 device 搬移")
def test_rng_state_roundtrip_on_cuda(tmp_path):
    """回归：checkpoint 用 map_location=cuda 加载时 torch RNG ByteTensor 被搬到 GPU，
    set_rng_state 只收 CPU ByteTensor → 必须 .cpu()（训练端 device=cuda 实测踩坑）。"""
    p = tmp_path / 'rcuda.pt'
    _agent().save(str(p))
    ag = MAPPOAgent(num_drones=3, obs_per_drone=4, act_per_drone=1, device='cuda')
    ag.load(str(p))  # 修复前抛 TypeError: RNG state must be a torch.ByteTensor
    assert torch.get_rng_state().device.type == 'cpu'