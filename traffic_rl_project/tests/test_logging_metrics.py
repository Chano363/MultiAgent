"""X2（2026-09-30）：优化器诊断量落盘回归测试。

背景：诊断「训练后期 value 发散」时，historically 训练日志只落 `total_loss`，
value_loss / entropy / KL / value_norm_std 全被丢弃 ⇒ 该叙事既不能证真也不能证伪。

本测试锁定两件事：
1. `MAPPOAgent.update()` 的返回 dict 含 `approx_kl` / `value_norm_mean` / `value_norm_std`
   且为有限值（跳过更新时由 `_zero_stats()` 保证字段齐全、不丢列）；
2. `TrainingLogger` 逐集写 `train_loss_{tag}.csv`（表头含上述字段），且续训 append
   不截断既有行（对齐 ADR-019 的 CSV/曲线连续性要求）。
"""
import csv
import os
import sys

import numpy as np
import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.algorithms.mappo_agent import MAPPOAgent      # noqa: E402
from src.environments.train_env import TrainFormationEnv   # noqa: E402
from src.trainer.logger import TrainingLogger          # noqa: E402

_LOSS_KEYS = ('approx_kl', 'value_norm_mean', 'value_norm_std')
_LOSS_HEADER = ['episode', 'value_loss', 'policy_loss', 'entropy', 'approx_kl',
                'grad_norm', 'value_norm_mean', 'value_norm_std', 'total_loss']


def _make_agent(num_vehicles, batch_size=8):
    return MAPPOAgent(num_drones=num_vehicles, obs_per_drone=4, act_per_drone=1,
                      learning_rate=5e-5, entropy_coef=0.005, epochs=2,
                      batch_size=batch_size, device='cpu')


def test_update_returns_optimizer_diagnostics():
    """update() 返回含 KL / value_norm 统计且有限（X2 落盘的数据源）。"""
    env = TrainFormationEnv({'num_vehicles': 6, 'max_steps': 20})
    agent = _make_agent(6)
    obs, _ = env.reset()
    for _ in range(30):
        flat = obs.flatten()
        actions, log_prob = agent.select_actions(flat)
        value = agent.get_value(flat)
        next_obs, reward, t, tr, info = env.step(actions.reshape(6, 1))
        done = t or tr
        agent.store_transition(flat, actions, reward, log_prob, done, value)
        obs = next_obs
        if done:
            obs, _ = env.reset()
    metrics = agent.update()
    for k in _LOSS_KEYS:
        assert k in metrics, f"update() 缺字段 {k}"
        assert np.isfinite(metrics[k]), f"{k} 非有限：{metrics[k]}"
    assert metrics['value_norm_std'] > 0.0


def test_zero_stats_fields_match():
    """跳过更新时的零值统计字段与正常返回一致（防下游 CSV 缺列）。"""
    zero = MAPPOAgent._zero_stats()
    assert set(zero) == {'total_loss', 'policy_loss', 'value_loss', 'entropy',
                         'grad_norm', 'approx_kl', 'value_norm_mean', 'value_norm_std'}


def test_logger_writes_loss_csv(tmp_path):
    """逐集写 train_loss_{tag}.csv，表头/行数与 episode 对齐。"""
    log = TrainingLogger(log_dir=str(tmp_path), figures_dir=str(tmp_path),
                         checkpoint_dir=str(tmp_path), tag='ut', seed=0,
                         total_episodes=3, tb=False, save_fn=None)
    for ep in (1, 2, 3):
        log.log_episode(ep=ep, reward=1.0 * ep, peak_coupler_kN=800.0 + ep,
                        violations=0, total_loss=0.5,
                        value_loss=0.1 * ep, policy_loss=0.2 * ep,
                        entropy=1.5, approx_kl=0.01 * ep, grad_norm=0.4,
                        value_norm_mean=100.0, value_norm_std=50.0 * ep)
    log.close()
    p = tmp_path / 'train_loss_ut.csv'
    rows = list(csv.reader(open(p, encoding='utf-8')))
    assert rows[0] == _LOSS_HEADER
    assert len(rows) == 4 and [r[0] for r in rows[1:]] == ['1', '2', '3']
    assert float(rows[3][7]) == pytest.approx(150.0)   # value_norm_std 逐集落盘


def test_logger_resume_appends_loss_csv(tmp_path):
    """续训不截断既有 train_loss CSV（append 语义）。"""
    log = TrainingLogger(log_dir=str(tmp_path), figures_dir=str(tmp_path),
                         checkpoint_dir=str(tmp_path), tag='ut', seed=0,
                         total_episodes=2, tb=False, save_fn=None)
    log.log_episode(ep=1, reward=1.0, peak_coupler_kN=800.0, violations=0,
                    value_norm_std=10.0)
    log.close()
    log2 = TrainingLogger(log_dir=str(tmp_path), figures_dir=str(tmp_path),
                          checkpoint_dir=str(tmp_path), tag='ut', seed=0,
                          total_episodes=4, tb=False, save_fn=None,
                          initial=1, resume=True)
    log2.log_episode(ep=2, reward=2.0, peak_coupler_kN=810.0, violations=0,
                     value_norm_std=20.0)
    log2.close()
    rows = list(csv.reader(open(tmp_path / 'train_loss_ut.csv', encoding='utf-8')))
    assert len(rows) == 3          # 表头 + 旧 1 行 + 新 1 行（未被截断）
    assert [r[0] for r in rows[1:]] == ['1', '2']