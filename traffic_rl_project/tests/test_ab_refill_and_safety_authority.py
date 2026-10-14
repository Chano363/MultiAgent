"""
ADR-021 单测：改造 A（AB 最小充风/保持时间进动作空间）+ 改造 D（安全层对 AB 的投影/禁新增权限）。

A：MultiLocoController 的 _ab_gate / get_action_decomposed 充风门（文献 Zhang2024）。
D：TrainFormationEnv._step_decomposed 的安全层 AB 新源"丢弃 / 降级"（不撤销已建立源）。
"""

from pathlib import Path

import numpy as np
import pytest

from src.environments.train_fleet_env import TrainFleetEnv  # noqa: F401  (先导入环境包，避免循环导入)
from src.controllers.multi_loco_controller import MultiLocoController
from src.environments.train_env import TrainFormationEnv

V_MAX = 80.0 / 3.6
V_MIN = 40.0 / 3.6


# --------------------------------------------------------------------------- #
# Use production dynamics for controller capability queries.
_OPEN_ENVS = []


@pytest.fixture(autouse=True)
def close_gate_environments():
    yield
    while _OPEN_ENVS:
        _OPEN_ENVS.pop().close()


def _StubTrainEnv(vel=5.0, grade=0.0):
    from src.train_dynamics.grade_profile import GradeProfile, GradeSegment
    env = TrainFormationEnv({'consist_preset': '20kt_1plus108_1plus108'})
    env.reset(options={'speed': vel})
    env.dynamics.set_grade_profile(GradeProfile([GradeSegment(0, grade * 1000)]))
    _OPEN_ENVS.append(env)
    return env


def _ctrl(**kw):
    return MultiLocoController(
        num_vehicles=218, loco_indices=[0, 109], dt=0.1,
        coupler_force_limit_n=1.0e6, **kw)


# --------------------------------------------------------------------------- #
# 改造 A
# --------------------------------------------------------------------------- #
def test_ab_refill_veto_within_window():
    """A①：释放后充风窗口内新增 AB 源被拒（计数增加 + final 不发该新源）。"""
    stub = _StubTrainEnv(vel=25.0, grade=-0.012)
    ctrl = _ctrl()  # 默认 ab_min_refill_s=222.0

    # 步1：进入制动带 → 规则基线发 AB 源（off→on）
    final, baseline = ctrl.get_action_decomposed(stub, np.zeros((2, 2)))
    assert baseline[0, 1] < 0 and final[0, 1] < 0
    assert ctrl._ab_on[0] is True

    # 步2：速度落回带内（latch 仍 True，基线仍发 AB），RL 抑制 → 释放该源
    stub.dynamics.vel[:] = 15.0
    final, baseline = ctrl.get_action_decomposed(
        stub, np.array([[0.5, 0.5], [0.0, 0.0]]))
    assert baseline[0, 1] < 0
    assert final[0, 1] == 0.0              # 已释放
    assert ctrl._ab_on[0] is False

    # 步3：离开制动带（基线不再发 AB），RL 要求新增源 → 充风窗口内被拒
    stub.dynamics.vel[:] = 5.0
    final, baseline = ctrl.get_action_decomposed(
        stub, np.array([[0.0, -0.5], [0.0, 0.0]]))
    assert baseline[0, 1] >= 0
    assert ctrl.ab_refill_veto_count == 1
    assert final[0, 1] == 0.0              # 新源被拒（本步不发）


def test_ab_hold_veto_within_window():
    """A②：ab_min_hold_s>0 时保持窗口内释放被拒。"""
    stub = _StubTrainEnv(vel=25.0, grade=-0.012)
    ctrl = _ctrl(ab_min_hold_s=300.0)

    ctrl.get_action_decomposed(stub, np.zeros((2, 2)))     # 步1：on
    stub.dynamics.vel[:] = 15.0
    final, baseline = ctrl.get_action_decomposed(
        stub, np.array([[0.5, 0.5], [0.0, 0.0]]))          # 步2：要求释放
    assert final[0, 1] < 0                 # 保持窗口内 → 释放被拒
    assert ctrl.ab_hold_veto_count == 1
    assert ctrl._ab_on[0] is True          # 仍处于 on


def test_ab_gate_outside_window_allows():
    """A③：窗口外不干预（充风足够后允许新增源）。"""
    stub = _StubTrainEnv(vel=25.0, grade=-0.012)
    ctrl = _ctrl(ab_min_refill_s=0.1)      # 1 步 = 0.1s 即满足

    ctrl.get_action_decomposed(stub, np.zeros((2, 2)))     # 步1：on
    stub.dynamics.vel[:] = 15.0
    ctrl.get_action_decomposed(stub, np.array([[0.5, 0.5], [0.0, 0.0]]))  # 步2：释放
    assert ctrl._ab_on[0] is False
    # 步3：Δstep=1 → 0.1s ≥ 0.1s → 允许新增源
    final, baseline = ctrl.get_action_decomposed(
        stub, np.array([[0.0, 0.0], [0.0, 0.0]]))
    assert baseline[0, 1] < 0
    assert final[0, 1] < 0
    assert ctrl.ab_refill_veto_count == 0


def test_ab_gate_zero_threshold_no_regression():
    """A④：ab_min_refill_s=0 / ab_min_hold_s=0 时行为与改造前一致（零回归、门不拒绝）。"""
    stub = _StubTrainEnv(vel=25.0, grade=-0.012)
    ctrl = _ctrl(ab_min_refill_s=0.0, ab_min_hold_s=0.0)

    # 无状态变化 → 直接允许
    assert ctrl._ab_gate(0, True) is True
    assert ctrl._ab_gate(0, False) is True

    ctrl.get_action_decomposed(stub, np.zeros((2, 2)))     # 步1：on
    stub.dynamics.vel[:] = 15.0
    final, _ = ctrl.get_action_decomposed(
        stub, np.array([[0.5, 0.5], [0.0, 0.0]]))          # 步2：释放
    assert final[0, 1] == 0.0
    stub.dynamics.vel[:] = 5.0
    final, _ = ctrl.get_action_decomposed(
        stub, np.array([[0.0, -0.5], [0.0, 0.0]]))         # 步3：新增源
    assert final[0, 1] < 0                                 # 允许（与改造前一致）
    assert ctrl.ab_refill_veto_count == 0
    assert ctrl.ab_hold_veto_count == 0


# --------------------------------------------------------------------------- #
# 改造 D
# --------------------------------------------------------------------------- #
def _make_decompose_env():
    return TrainFormationEnv({
        'num_vehicles': 5,
        'num_locomotives': 1,
        'target_speed': 20.0,
        'line_speed_limit_mps': V_MAX,
        'max_steps': 5,
        'decompose': 'loco_ed_ab',
    })


def _ab_action(env, ab_frac=-0.4):
    act = np.zeros((env.num_locomotives, 2), dtype=float)
    act[0, 1] = ab_frac
    return act


def test_safety_veto_drops_new_ab_source():
    """D①：高力场景（安全层预测式否决）新源被丢弃，不生成立即生效的 AB 源。"""
    env = _make_decompose_env()
    env.reset()
    loco = env.loco_indices[0]
    env.safety.ab_new_source_veto = lambda snap: True   # 强制高力否决

    _, _, _, _, info = env._step_decomposed(_ab_action(env))
    assert info['ab_safety_vetoed'] is True
    assert env.dynamics._air_brake_active[loco] == False   # 新源未施加


def test_safety_low_force_no_intervention():
    """D②：低力场景不干预（新源照常施加，无否决）。"""
    env = _make_decompose_env()
    env.reset()
    loco = env.loco_indices[0]
    env.safety.ab_new_source_veto = lambda snap: False

    _, _, _, _, info = env._step_decomposed(_ab_action(env))
    assert info['ab_safety_vetoed'] is False
    assert env.dynamics._air_brake_active[loco] == True     # 新源已施加


def test_step_decomposed_has_no_revoke_path():
    """D③：源码级断言 —— _step_decomposed 内不存在撤销已建立源的调用。"""
    src = Path(__file__).resolve().parents[1] / 'src' / 'environments' / 'train_env.py'
    text = src.read_text(encoding='utf-8')
    body = text[text.index('def _step_decomposed'):text.index('def _air_brake_priority')]
    # 不存在撤销/重置类动力学调用
    assert '_reset_air_brake_command' not in body
    # 新增了 AB 安全权限诊断键
    assert 'ab_safety_vetoed' in body
    # 不存在"降级一档"的梯度投影臂（可证不可达，已移除；见 ADR-021「执行闭环」）
    assert 'ab_safety_downgraded' not in body
    assert 'for idx, notch in ab_sources' not in body


def test_fleet_info_exposes_ab_safety_counts():
    """D④（fleet 层）：`TrainFleetEnv.info` 跨列车聚合暴露安全层 AB 权限计数。

    子环境（TrainFormationEnv）已暴露该计数，但 fleet 层若不聚合就被丢弃 → 生产
    接口上根本看不见 D 是否生效。这里固定控制器本步发 AB 新源 + 强制安全层否决，
    断言聚合值 ≥ 1（纯 plumbing 验证；D 的物理语义已由 D①/D②/D③ 覆盖）。
    """
    env = TrainFleetEnv({
        'num_trains': 1,
        'consist_preset': '10kt_1plus1',
        'grade_profile': 'long_downhill',
        'target_speed': 20.0,
        'max_steps': 5,
        'decompose': 'loco_ed_ab',
    })
    env.reset(options={'speed': 65.0 / 3.6})
    n_loco = len(env.trains[0].loco_indices)
    ab_req = np.zeros((n_loco, 2), dtype=float)
    ab_req[:, 1] = -0.4                                    # 每机车请求 SERVICE 新源
    env.multi_loco_controllers[0].get_action_decomposed = (
        lambda *a, **k: (ab_req.copy(), ab_req.copy()))
    for tr in env.trains:
        tr.safety.ab_new_source_veto = lambda snap: True    # 强制高力否决
    act = np.zeros((env.num_agents, 2), dtype=float)
    _, _, _, _, info = env.step(act)
    assert 'ab_safety_vetoed' in info
    assert info['ab_safety_vetoed'] >= 1
    env.close()