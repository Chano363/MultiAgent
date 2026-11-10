"""训练/评估"指标口径"回归单测（2026-10-01）。

同类缺陷两处，均为"看起来对、静默算错"型 —— 故统一在此以
**行为级 + 源码级断言**双重固定：

  ① `TrainRunner._long_eval` 违规计数把 episode 级**累计**计数器逐步相加 ⇒ O(n²) 放大；
  ⑤ `evaluate_decompose --decision_interval` 默认**写死 1**，而训练用 10 ⇒ 文档口径的
     主对比命令（未显式传参）会让 D-RL 行以 1 步决策跑，**训练/评估半 MDP 失配**。

共同根因：env 的 `coupler_limit_violations` / `coupler_force_peak` 是 **episode 级单调累计**
（`reset()` 清零、step 间不清零），复用同一条 env 跑多回合时不会自动清零。
"""

import logging
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest

from src.environments.train_fleet_env import TrainFleetEnv  # noqa: F401  (先导入环境包，避免循环导入)
from src.evaluation import evaluate_decompose as ev
from src.trainer import train_runner
from src.trainer.config_schema import ExperimentConfig
from src.trainer.train_runner import TrainRunner

V_MAX = 80.0 / 3.6
V_MIN = 40.0 / 3.6
_SRC = Path(__file__).resolve().parents[1] / 'src'


# =========================================================================== #
# ① `_long_eval` 违规计数：取每步增量之和，而非累计值逐步相加
# =========================================================================== #
class _StubFleetEnv:
    """复现"episode 级单调累计"的真实 env 语义（不起完整仿真）。"""

    num_agents = 2
    act_dim = 2
    v_min = V_MIN
    v_max = V_MAX
    coupler_force_limit_n = 1.0e6

    def __init__(self, cfg, n_steps=6, viol_from=3, peak_n=5.0e5, vel=20.0,
                 final_vel=None):
        self.cfg = cfg
        self.n_steps = n_steps
        self.viol_from = viol_from
        self.peak_n = peak_n
        self.vel0 = vel
        self.final_vel = vel if final_vel is None else final_vel
        self.reset()

    def reset(self, options=None):
        self._i = 0
        self._cum_viol = 0
        self.trains = [type('T', (), {'dynamics': type(
            'D', (), {'vel': np.array([self.vel0])})()})()]
        return np.zeros((self.num_agents, 11)), {}

    def _get_obs_decomposed(self):
        return np.zeros((self.num_agents, 11))

    def step(self, a):
        self._i += 1
        if self._i >= self.viol_from:
            self._cum_viol += 1                      # 单调累计（不因 step 归零）
        v = self.vel0 if self._i < self.n_steps else self.final_vel
        self.trains[0].dynamics = type('D', (), {'vel': np.array([v])})()
        info = {'coupler_force_peak': self.peak_n,
                'coupler_limit_violations': self._cum_viol}
        return None, 1.0, False, self._i >= self.n_steps, info

    def close(self):
        pass


class _StubAgents:
    def __init__(self):
        self.saved = []

    def select_actions(self, obs, deterministic=False):
        return np.zeros((_StubFleetEnv.num_agents, _StubFleetEnv.act_dim)), {}

    def save(self, path, metadata=None):
        self.saved.append((path, metadata))


class _StubNamer:
    def best_path(self, seed):
        return f"stub_best_seed{seed}.pt"


def _cfg(tmp_path):
    cfg = ExperimentConfig()
    cfg.seed = 0
    cfg.obs = 'env'
    cfg.decision_interval = 10
    cfg.long_eval_steps = 100                # stub 会在 6 步后 trunc，无需真跑 100
    cfg.long_eval_grade = ''
    cfg.long_eval_init_speed_kmh = 80.0
    cfg.env_cfg = {'grade_profile': 'stub', 'max_steps': 100}
    cfg.checkpoint_dir = str(tmp_path / 'ckpt')
    cfg.results_dir = str(tmp_path / 'results')
    Path(cfg.checkpoint_dir).mkdir(parents=True, exist_ok=True)
    Path(cfg.results_dir).mkdir(parents=True, exist_ok=True)
    return cfg


def _runner(cfg):
    r = TrainRunner(cfg)
    r._base_ckpt_meta = {}
    r._best_eval_ref = None
    return r


def _long_eval_log(caplog):
    hits = [rec.getMessage() for rec in caplog.records if '[long_eval]' in rec.getMessage()]
    assert hits, "未捕获到 [long_eval] 日志"
    return hits[0]


def test_long_eval_viol_uses_increment_not_cumulative(monkeypatch, tmp_path, caplog):
    """累计序列 0,0,1,2,3,4 ⇒ 真实总违规 = 4；O(n²) 旧写法会得到 10。"""
    cfg = _cfg(tmp_path)
    monkeypatch.setattr(train_runner, 'TrainFleetEnv',
                        lambda eval_cfg: _StubFleetEnv(eval_cfg))
    r = _runner(cfg)
    with caplog.at_level(logging.INFO, logger='TrainRunner'):
        r._long_eval(_StubAgents(), cfg, _StubNamer(), global_ep=50,
                     best_eval={'reward': float('-inf'), 'ep': 0})
    msg = _long_eval_log(caplog)
    assert '| viol 4 |' in msg, f"viol 口径错误（应为增量之和 4）：{msg}"
    assert '| viol 10 |' not in msg, f"仍在使用累计值逐步相加（O(n²)）：{msg}"


def test_long_eval_zero_viol_still_ok_and_saves_best(monkeypatch, tmp_path, caplog):
    """零违规时判据仍成立（回归保护：修复不能把 ok 门改坏）。"""
    cfg = _cfg(tmp_path)
    # viol_from 远大于步数 ⇒ 累计恒为 0；峰值 500 kN < 1000 kN 限值；末速 20 m/s ∈ 速度带
    monkeypatch.setattr(train_runner, 'TrainFleetEnv',
                        lambda eval_cfg: _StubFleetEnv(eval_cfg, viol_from=999))
    r = _runner(cfg)
    agents = _StubAgents()
    best_eval = {'reward': float('-inf'), 'ep': 0}
    with caplog.at_level(logging.INFO, logger='TrainRunner'):
        r._long_eval(agents, cfg, _StubNamer(), global_ep=50, best_eval=best_eval)
    msg = _long_eval_log(caplog)
    assert '| viol 0 |' in msg
    assert '达标=True' in msg, f"零违规应判达标：{msg}"
    assert len(agents.saved) == 1 and best_eval['viol'] == 0
    assert (Path(cfg.results_dir) / 'long_eval_best.json').exists()


def test_long_eval_source_has_no_cumulative_sum():
    """源码级断言：防"累计值逐步相加"回流。"""
    text = (_SRC / 'trainer' / 'train_runner.py').read_text(encoding='utf-8')
    body = text[text.index('def _long_eval'):text.index('def _eval_obs')]
    assert 'viol += cur_viol - prev_viol' in body
    assert "viol += int(info.get('coupler_limit_violations', 0))" not in body


# =========================================================================== #
# ⑤ `--decision_interval` 静默默认 1（而训练用 10）⇒ 训练/评估半 MDP 失配
#    同类根因 = "被 CLI 默认值静默改变的文档语义"。
# =========================================================================== #
def _stub_eval_args(**kw):
    base = dict(decision_interval=None, mode='decompose_m1',
                checkpoint='__definitely_missing__.pt')
    base.update(kw)
    return SimpleNamespace(**base)


def test_decision_interval_explicit_passthrough():
    """显式传值必须原样生效 ⇒ 修复不改动任何"已显式指定间隔"的既有数值。"""
    assert ev.resolve_decision_interval(_stub_eval_args(decision_interval=10)) == 10
    assert ev.resolve_decision_interval(_stub_eval_args(decision_interval=1)) == 1


def test_decision_interval_reads_ckpt_metadata(tmp_path):
    """默认 None ⇒ 自 ckpt 内嵌 metadata 的 hyperparameters.decision_interval 读取。"""
    import torch
    p = tmp_path / 'stub_ckpt.pt'
    torch.save({'metadata': {'hyperparameters': {'decision_interval': 10}}}, str(p))
    args = _stub_eval_args(checkpoint=str(p))
    assert ev.resolve_decision_interval(args) == 10


def test_decision_interval_falls_back_to_train_default():
    """ckpt 不存在 ⇒ 退回**训练标准值 10**（而非旧的静默 1），且不抛异常。"""
    args = _stub_eval_args(checkpoint='__definitely_missing__.pt')
    assert ev.resolve_decision_interval(args) == ev.TRAIN_DEFAULT_DECISION_INTERVAL
    assert ev.TRAIN_DEFAULT_DECISION_INTERVAL == 10


def test_decision_interval_ckpt_without_field_falls_back(tmp_path):
    """旧 ckpt（无 hyperparameters）⇒ 同样退回训练标准值，不崩。"""
    import torch
    p = tmp_path / 'old_ckpt.pt'
    torch.save({'policy_state_dict': {}}, str(p))
    args = _stub_eval_args(checkpoint=str(p))
    assert ev.resolve_decision_interval(args) == ev.TRAIN_DEFAULT_DECISION_INTERVAL


def test_decision_interval_source_guards():
    """源码级断言：① argparse 默认必须为 None（防退回写死 1/10）；② 解析须在 build_metadata 之前。"""
    text = (_SRC / 'evaluation' / 'evaluate_decompose.py').read_text(encoding='utf-8')
    assert "p.add_argument('--decision_interval', type=int, default=None," in text, \
        '缺少 None 默认 ⇒ 又回到「CLI 默认值静默决定语义」'
    call = 'args.decision_interval = resolve_decision_interval(args)'
    assert call in text, "缺少 resolve_decision_interval 调用"
    assert text.index(call) < text.index('_meta = build_metadata('), \
        "解析发生在 build_metadata 之后 ⇒ metadata.eval_args 与实际行为矛盾"
