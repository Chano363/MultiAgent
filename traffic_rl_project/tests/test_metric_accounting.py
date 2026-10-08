"""训练/评估"指标口径"回归单测（2026-10-01）。

同类缺陷四处，均为"看起来对、静默算错"型 —— 故统一在此以
**行为级 + 源码级断言**双重固定：

  ① `TrainRunner._long_eval` 违规计数把 episode 级**累计**计数器逐步相加 ⇒ O(n²) 放大；
  ② `evaluate_decompose --mode all` 因 `--enable_mpc` 默认 False 而**静默只出 2 行、缺 MPC**；
  ③ `evaluate_decompose.rollout` 未逐回合 reset MPC 控制器 ⇒ `--n_seed 3` 时回合不独立；
  ⑤ `evaluate_decompose --decision_interval` 默认**写死 1**，而训练用 10 ⇒ 文档口径的
     主对比命令（未显式传参）会让 D-RL 行以 1 步决策跑，**训练/评估半 MDP 失配**。

共同根因：env 的 `coupler_limit_violations` / `coupler_force_peak` 是 **episode 级单调累计**
（`reset()` 清零、step 间不清零），而"每回合状态"（MPC 的 `_gap0_init` / `_gap_ref`）在
**复用同一条 env / 同一个控制器**跑多回合时不会自动清零。
"""

import logging
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest

from src.environments.train_fleet_env import TrainFleetEnv  # noqa: F401  (先导入环境包，避免循环导入)
from src.controllers.nmpc_controller import NMPCController
from src.controllers.multi_loco_controller import MultiLocoController
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
# ② `--mode all` 必须产出 MPC 行（防"静默缺行"回流）
# =========================================================================== #
def test_eval_mode_all_normalizes_enable_mpc():
    """`--mode all` 的口径 = 主对比全行（D-Rule / D-RL / MPC）。

    回归背景：旧写法把 MPC 行藏在 `if enable_mpc or mode=='mpc'` 里，而 `--enable_mpc`
    默认 False ⇒ `--mode all` 静默只出 2 行、缺 MPC，且三行 Δ 摘要（`len(results)>=3`）
    同步静默跳过。修复 = 解析后立即把 `all`/`mpc` 归一为 `enable_mpc=True`（且在
    `build_metadata` 之前，保证 metadata 与实际行为一致）。
    """
    text = (_SRC / 'evaluation' / 'evaluate_decompose.py').read_text(encoding='utf-8')
    norm = "if args.mode in ('all', 'mpc'):\n        args.enable_mpc = True"
    assert norm in text, "缺少 --mode all / mpc 的 enable_mpc 归一"
    assert text.index(norm) < text.index('_meta = build_metadata('), \
        "归一位于 build_metadata 之后 ⇒ metadata.eval_args.enable_mpc 会与实际行为矛盾"
    mpc_block = text[text.index("if args.mode in ('all', 'mpc'):\n        results['mpc'] = eval_method("):
                     text.index('单机单控(旧架构1+0)已从主对比中移除')]
    assert "getattr(args, 'enable_mpc', False)" not in mpc_block


# =========================================================================== #
# ③ MPC 控制器必须逐回合 reset（否则 --n_seed 3 的回合不独立）
# =========================================================================== #
class _StubMpc:
    def __init__(self):
        self.reset_calls = 0
        self.solve_times = []
        self.solve_statuses = []

    def reset(self):
        self.reset_calls += 1
        self.solve_times = []


class _StubEvalEnv:
    """`rollout()` 依赖的最小 env（decompose=True + 可选 _mpc_controller）。"""

    decompose = True
    v_min = V_MIN
    v_max = V_MAX

    def __init__(self, mpc=None, steps=3):
        self._mpc_controller = mpc
        self.n_steps = steps
        self._i = 0
        self.trains = [type('T', (), {'dynamics': type(
            'D', (), {'vel': np.array([20.0])})()})()]

    def reset(self, options=None):
        self._i = 0
        return np.zeros((2, 11)), {}

    def step(self, a):
        self._i += 1
        info = {'coupler_force_peak': 5.0e5, 'coupler_limit_violations': 0,
                'safety_events': 0, 'ab_source_count': 0,
                'executed_actions': np.zeros((2, 2))}
        return None, 1.0, False, self._i >= self.n_steps, info

    def close(self):
        pass


def test_rollout_resets_mpc_each_episode():
    """3 个回合（≈ `--n_seed 3`）⇒ MPC 的 reset 必须被调用 3 次。"""
    from src.evaluation.evaluate_decompose import rollout
    mpc = _StubMpc()
    env = _StubEvalEnv(mpc)
    args = SimpleNamespace(max_steps=3, init_speed_kmh=80.0, random_init_speed=False)
    rng = np.random.default_rng(0)
    for _ in range(3):
        rollout(env, lambda e: np.zeros((2, 2)), args, rng, act_interval=1)
    assert mpc.reset_calls == 3, \
        "MPC 未逐回合 reset ⇒ n_seed>1 时后续回合继承上一回合间距基准（回合不独立）"


def test_rollout_resets_mpc_source():
    """源码级断言：`rollout` 内存在逐回合 `_mpc.reset()`（防删除回流）。"""
    text = (_SRC / 'evaluation' / 'evaluate_decompose.py').read_text(encoding='utf-8')
    body = text[text.index('def rollout('):text.index('def eval_method(')]
    assert '_mpc.reset()' in body


# =========================================================================== #
# ④ "缺求解状态"不得让整轮评估崩掉（控制器无关的鲁棒性守卫）
#    【ADR-022】原用于 FairMPCController 的那条源码级断言已随该类删除；此处保留的
#    stub 型守卫仍有效（未来任何不记录 solve_statuses 的控制器都不该拖垮整行）。
# =========================================================================== #
class _StubMpcNoStatus:
    """只有 `solve_times`、**没有** `solve_statuses` 的控制器桩（复现历史事故形态）。"""

    def __init__(self):
        self.solve_times = []

    def reset(self):
        self.solve_times = []


class _StubEvalEnvWithSolver(_StubEvalEnv):
    """step 里模拟"求解一次"（往控制器 solve_times 追加）。"""

    def step(self, a):
        self._mpc_controller.solve_times.append(1e-3)
        return super().step(a)


def test_rollout_tolerates_missing_solve_statuses():
    """附加诊断缺失时不得崩 —— 历史事故：某 MPC 行的 AttributeError 连累已跑完的 M0/M1 也不落盘。"""
    from src.evaluation.evaluate_decompose import rollout
    env = _StubEvalEnvWithSolver(_StubMpcNoStatus(), steps=3)
    args = SimpleNamespace(max_steps=3, init_speed_kmh=80.0, random_init_speed=False)
    out = rollout(env, lambda e: np.zeros((2, 2)), args, np.random.default_rng(0), act_interval=1)
    assert 'mpc_solve_mean_ms' in out and 'mpc_solve_max_ms' in out
    assert 'mpc_solve_fail' not in out          # 无状态源 ⇒ 不产出该键，但绝不抛异常


def test_nmpc_records_solve_statuses():
    """源码级断言：**唯一的** MPC 控制器 NMPCController 记录 solve_statuses，且 reset() 清空。"""
    text = (_SRC / 'controllers' / 'nmpc_controller.py').read_text(encoding='utf-8')
    assert 'self.solve_statuses = []' in text
    assert 'self.solve_statuses.append(' in text
    body = text[text.index('def reset('):text.index('def __repr__')]
    assert 'self.solve_statuses = []' in body, "reset() 未清空 solve_statuses"


def test_rollout_metric_assembly_guards_statuses():
    """源码级断言：`rollout` 用 getattr 兜住 solve_statuses（防退回直接下标取值）。"""
    text = (_SRC / 'evaluation' / 'evaluate_decompose.py').read_text(encoding='utf-8')
    body = text[text.index('def rollout('):text.index('def eval_method(')]
    assert "sts = getattr(_mpc, 'solve_statuses', None)" in body
    assert '_mpc.solve_statuses[st0:]' not in body


# =========================================================================== #
# ⑤ `--decision_interval` 静默默认 1（而训练用 10）⇒ 训练/评估半 MDP 失配
#    同类根因 = "被 CLI 默认值静默改变的文档语义"（同 ②）。
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


# =========================================================================== #
# ⑥ MPC 桥接量纲（M1）：decompose 通道的动作 = **规则基线的加性调制**，不是绝对 ED
#    旧实现把 get_action_accel 的绝对 ED 深度直接当 ed_mod ⇒ clip 后恒 ≥ 基线且 ≈1.0、
#    AB 通道恒 0（落在 ±0.15 死区）⇒ MPC 只剩"单调加 ED"一根杠杆 = strawman。
#    修复（甲方 2026-10-01）= 反解加性关系 ed_mod = (desired_ed − baseline_ed)/ED_MOD_COEF。
# =========================================================================== #
class _StubMpcU:
    """只提供 `compute_actions_from_env` 的 MPC 桩（返回每列目标加速度 U）。"""

    def __init__(self, U):
        self._U = np.asarray(U, dtype=float)
        self.solve_times = []
        self.solve_statuses = []

    def compute_actions_from_env(self, env):
        return self._U.copy()

    def reset(self):
        self.solve_times = []


def _fleet_env(num_trains=2):
    return TrainFleetEnv({
        'num_trains': num_trains,
        'consist_preset': '10kt_1plus1',
        'grade_profile': 'long_downhill',
        'target_speed': 20.0,
        'max_steps': 50,
        'eval_mode': True,
        'decompose': 'loco_ed_ab',
    })


def _bridge_step(env, U, ti=0):
    """过一遍 mpc_act，再让第 ti 列按 env 的**同一路径**执行一步。

    返回 (final, desired_ed, out, row)：final = get_action_decomposed 交付的 ED/AB；
    desired_ed = MPC 期望的绝对 ED 深度；out = mpc_act 的调制输出；row = 该列调制动作。
    """
    env._mpc_controller = _StubMpcU(U)
    out = ev.mpc_act(env)
    ctrl = env.multi_loco_controllers[ti]
    tr = env.trains[ti]
    n_loco = len(tr.loco_indices)
    a = sum(len(t.loco_indices) for t in env.trains[:ti])
    row = out[a:a + n_loco]
    max_a = max(float(getattr(ctrl, 'max_accel', 1.0)), 1e-6)
    desired = float(np.clip(-float(U[ti]) / max_a, 0.0, 1.0))
    final, _ = ctrl.get_action_decomposed(
        tr, row, v_max=env.v_max, v_min=env.v_min, v_max_adj=0.0, v_min_adj=0.0)
    return np.asarray(final, dtype=float), desired, out, row


def test_mpc_bridge_inverts_additive_modulation():
    """反解必须精确：带内（规则基线 ED=0）时 env 交付 ED == MPC 期望 ED。

    这也是**旧缺陷的回归守卫**：旧实现把绝对 ED 当 ed_mod ⇒ 交付 = baseline + coef×期望
    ≠ 期望（旧 coef=0.5 时恰为 0.5×期望，本例 0.2），本断言会红。修复后交付 == 期望，
    调制量按 ED_MOD_COEF 恰好反解出来。
    """
    env = _fleet_env()
    env.reset(options={'speed': 60.0 / 3.6})       # 带内：_cyclic_braking=False ⇒ 基线 ED=0
    final, desired, out, row = _bridge_step(env, [-0.4, -0.4])
    assert out.min() >= -1.0 and out.max() <= 1.0, "桥接输出必须是调制量 ∈[-1,1]²"
    assert abs(desired - 0.4) < 1e-12
    assert np.allclose(final[:, 0], desired, atol=1e-9), (
        f"反解后 env 交付 ED={final[:, 0]} 应 == MPC 期望 {desired}；"
        "若为 coef×期望则退回「绝对 ED 当调制」旧缺陷")
    assert np.allclose(row[:, 0], desired / ev.ED_MOD_COEF, atol=1e-9), \
        "基线 ED=0 ⇒ ed_mod 应为期望 / ED_MOD_COEF"
    env.close()


def test_bridge_ed_band_derives_from_controller_default():
    """ED_MOD_COEF 必须**派生**自 get_action_decomposed 的默认值，不得在评估侧手抄字面量。

    防的正是 M1 同族缺陷：评估侧一个数、执行侧另一个数 ⇒ 静默失配（LRN-20261001-017）。
    """
    import inspect

    default = inspect.signature(
        MultiLocoController.get_action_decomposed).parameters['ed_mod_coef'].default
    assert float(default) == ev.ED_MOD_COEF, "评估侧带宽与控制器默认值不一致"
    text = (_SRC / 'evaluation' / 'evaluate_decompose.py').read_text(encoding='utf-8')
    assert "parameters['ed_mod_coef'].default" in text, "ED_MOD_COEF 又变回手抄字面量"


def test_mpc_bridge_ab_intent_channels():
    """AB 通道必须有权限（旧实现恒 0 = 落在 ±0.15 死区，等于无 AB 权限）。"""
    env = _fleet_env()
    env.reset(options={'speed': 60.0 / 3.6})
    _, _, _, row_sup = _bridge_step(env, [+0.2, +0.2])      # MPC 想加速 ⇒ 请求抑制 AB
    assert np.allclose(row_sup[:, 1], ev.AB_SUPPRESS_MOD)
    assert ev.AB_SUPPRESS_MOD > 0.15, "抑制值须越过 get_action_decomposed 的 +0.15 阈值"

    env.reset(options={'speed': 60.0 / 3.6})
    _, _, _, row_trig = _bridge_step(env, [-0.75, -0.75])   # 顶满自有权限 ⇒ 请求预触发兜底
    assert np.allclose(row_trig[:, 1], ev.AB_TRIGGER_MOD)
    assert ev.AB_TRIGGER_MOD < -0.15, "预触发值须越过 -0.15 阈值"

    env.reset(options={'speed': 60.0 / 3.6})
    _, _, _, row_mid = _bridge_step(env, [-0.3, -0.3])      # 中间带 ⇒ 不动 AB
    assert np.allclose(row_mid[:, 1], 0.0)
    env.close()


def test_mpc_bridge_ab_trigger_reachable():
    """AB 预触发阈值必须**严格小于** MPC 期望 ED 的上限，否则该分支是死代码（同 LRN-20261001-007）。

    【ADR-022】唯一 MPC 控制器 = NMPCController（旧 fair/简化 MPC 已删除）。
    """
    import inspect

    params = inspect.signature(NMPCController.__init__).parameters
    lo = float(params['accel_lo'].default)
    ma = float(params['max_accel'].default) if 'max_accel' in params else 1.0
    ceiling = abs(lo) / ma
    assert ev.MPC_AB_TRIGGER_ED < ceiling, (
        f"NMPCController 期望 ED 上限 {ceiling} ≤ 触发阈值 {ev.MPC_AB_TRIGGER_ED} ⇒ 不可达")


def test_rule_baseline_edab_preserves_latch():
    """复算基线不得污染控制器两态闩锁（否则评估侧"预演"会改变 env 的实际制动分支）。"""
    env = _fleet_env()
    env.reset(options={'speed': 80.0 / 3.6})
    ctrl = env.multi_loco_controllers[0]
    for latch in (False, True):
        ctrl._cyclic_braking = latch
        ev._rule_baseline_edab(ctrl, env.trains[0], env)
        assert ctrl._cyclic_braking is latch, "复算基线污染了控制器两态闩锁"
    env.close()


def test_mpc_bridge_and_m3_source_guards():
    """源码级断言：① 桥接必须用"反解"而非直接取绝对 ED；② M3 不得退回硬编码 inner_rule_cyclic。"""
    text = (_SRC / 'evaluation' / 'evaluate_decompose.py').read_text(encoding='utf-8')
    assert 'def _rule_baseline_edab(' in text, "缺少规则基线复算（反解的前提）"
    assert '(desired_ed - base[i, 0]) / ED_MOD_COEF' in text, "缺少反解表达式"
    mount = text[text.index('def _mount_mpc('):text.index('def rollout(')]
    # 只看**调用实参**形态（带尾逗号），避免匹配到注释里的"原硬编码 inner_rule_cyclic=True"
    assert 'inner_rule_cyclic=True,' not in mount and 'inner_rule_cyclic=False,' not in mount, \
        "M3 回流：inner_rule_cyclic 又被硬编码，评估口径不可由 CLI 复现"
    assert 'inner_rule_cyclic=inner_cyclic,' in mount, "缺少统一开关的实参传递"
    assert '--mpc_inner_rule_cyclic' in text, "缺少 M3 显式开关"


def test_mpc_bridge_saturation_diag_is_recorded():
    """桥接饱和计数（主表 MPC 行的可量化审计信号）：随「期望 ED × 带宽」关系正确开合。

    【ADR-024】带宽 = ED_MOD_COEF = 0.5（半幅），判据：
      - 期望 ED ≤ 带宽（U=-0.4 ⇒ desired 0.4 ⇒ ed_mod 0.8）⇒ 可兑现 ⇒ 计数 0；
      - 期望 ED > 带宽（U=-0.75 ⇒ desired 0.75 ⇒ ed_mod 1.5 须 clip）⇒ 越权 ⇒ 计数 > 0，
        且此时 desired 0.75 ≥ MPC_AB_TRIGGER_ED(0.7) ⇒ 每列都请求 AB 预触发。
    """
    env = _fleet_env()
    env.reset(options={'speed': 60.0 / 3.6})        # 带内 ⇒ 基线 ED=0
    _bridge_step(env, [-0.4, -0.4])                 # 期望 ED 0.4 ≤ 带宽 0.5 ⇒ 可兑现
    assert env._mpc_bridge_diag['ed_saturated'] == 0, "期望 ED 未超带宽，不该判越权"

    env.reset(options={'speed': 60.0 / 3.6})
    _bridge_step(env, [-0.75, -0.75])               # 期望 ED 0.75 > 带宽 0.5 ⇒ 越权
    diag = env._mpc_bridge_diag
    assert diag['ed_saturated'] > 0, "期望 ED 超带宽却未计数 ⇒ 计数器成死码"
    assert diag['ab_trigger'] == len(env.trains), "顶满自有权限 ⇒ 每列都应请求 AB 预触发"
    env.close()


def test_eval_method_print_guards_optional_mpc_keys():
    """源码级断言：MPC 附加诊断须逐项 `in agg` 守卫（防 KeyError 连累整行不落盘，同 LRN-20261001-013）。"""
    text = (_SRC / 'evaluation' / 'evaluate_decompose.py').read_text(encoding='utf-8')
    body = text[text.index('def eval_method('):text.index('def mpc_act(')]
    assert "'mpc_solve_fail' in agg" in body, "mpc_solve_fail 未被守卫"
    assert "'mpc_bridge_ed_saturated' in agg" in body, "桥接饱和键未被守卫"
    assert "if 'mpc_solve_mean_ms' in agg else" not in body, \
        "回流：仍在 mpc_solve_mean_ms 命中时直接取 mpc_solve_fail"