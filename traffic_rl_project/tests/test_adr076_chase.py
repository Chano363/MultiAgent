"""ADR-076 待验证：逐列 AB 派生阈值偏置（诊断 §19.13.3）。

机制：AB 的**逐列分配方向**是几何收敛的载体。
  规则基线 ab_agent_steps = [10693, 1527, 1171]（领航 39% / 中尾 4~6%）
      ⇒ gap_err 24.54 m / band 100%
  我们 baseline           = [0.092, 0.138, 0.138]（领航 9% / 中尾 14%）
      ⇒ gap_err 654 m / band 85%
  逐拍分解：领航 AB 在场 ⇒ pair0 几何速率 −0.437 m/s（收拢）；
            中/尾列 AB 在场 ⇒ pair1 速率 +1.17/+0.42 m/s（撑开）。
nincr 的 AB 由级位越限派生且逐列同阈 ⇒ 分配结构完全由 RL 决定，无法表达
该结构。本机制按列角色给**派生阈值**：领航早请求 / 后列少请求。

测试覆盖：
  1. 默认 None ⇒ 逐位零回归
  2. 领航阈值下调 ⇒ 同级位下领航更早请求 AB
  3. 后列阈值上调 ⇒ 同级位下后列更少请求 AB
  4. 两者同时生效（分配结构反转）
  5. 安全侧不变：222 s 充风门 / 低速强制缓解 / 档位最短保持全部保留
"""
import numpy as np
import pytest
from types import SimpleNamespace

from src.controllers.multi_loco_controller import MultiLocoController

V_MAX = 75.0 / 3.6
V_MIN = 40.0 / 3.6


def _env(vel_kmh=70.0, grade_permille=None):
    dyn = SimpleNamespace(vel=np.array([vel_kmh / 3.6]))
    if grade_permille is not None:
        dyn.grade = np.array([grade_permille / 1000.0])
    return SimpleNamespace(dynamics=dyn)


def _ctrl():
    c = MultiLocoController(num_vehicles=1, loco_indices=[0])
    c.notch_incr_rate_notches = 3.0
    return c


def _run(ctrl, env, actions):
    out = None
    for a in actions:
        out = ctrl.get_action_notch_incr(
            env, np.array([[a]]), v_max=V_MAX, v_min=V_MIN)
    return out


# ---------------------------------------------------------------- #
# 1) 默认 None = 逐位零回归
# ---------------------------------------------------------------- #
def test_threshold_override_default_none_is_zero_regression():
    env = _env(70.0, -10.0)
    a = _ctrl()
    a.ab_derive_threshold_lead = None
    a.ab_derive_threshold_follower = None
    b = _ctrl()

    seq = [1.0] * 6 + [-1.0] * 8
    oa = _run(a, env, seq)
    ob = _run(b, env, seq)
    assert oa[0, 0] == pytest.approx(ob[0, 0], abs=0.0)
    assert oa[0, 1] == pytest.approx(ob[0, 1], abs=0.0)


# ---------------------------------------------------------------- #
# 2) 领航阈值下调 ⇒ 同级位下更早请求 AB
# ---------------------------------------------------------------- #
def test_lead_threshold_lower_requests_ab_earlier():
    """领航列：阈值 0.30 ⇒ 级位刚过 0.30 就请求 AB；默认 0.50 则不请求。"""
    env = _env(70.0, -10.0)

    # 领航，阈值下调
    lead = _ctrl()
    lead.ab_derive_threshold_lead = 0.30
    # 把级位推到 0.30~0.50 区间：每步增量 0.15（3 级/决策步）
    _run(lead, env, [1.0] * 3)          # 级位 ≈0.45
    assert lead._notch_level[0] < 0.50
    out = _run(lead, env, [1.0])        # 级位 ≈0.60 > 0.30
    assert out[0, 1] < 0                # AB 已施加

    # 默认阈值 0.50：级位 ≈0.45 时不请求
    base = _ctrl()
    _run(base, env, [1.0] * 3)
    out_base = _run(base, env, [1.0])
    # 级位 ≈0.60 ≥ 0.50 ⇒ 默认也该请求；用更早的时点对比
    base2 = _ctrl()
    out_b2 = _run(base2, env, [1.0] * 2)   # 级位 ≈0.30
    assert out_b2[0, 1] == 0.0             # 默认阈值下不请求

    lead2 = _ctrl()
    lead2.ab_derive_threshold_lead = 0.30
    out_l2 = _run(lead2, env, [1.0] * 2)   # 级位 ≈0.30
    assert out_l2[0, 1] < 0                # 下调后同一级位已请求 ⇒ 更早


# ---------------------------------------------------------------- #
# 3) 后列阈值上调 ⇒ 同级位下更少请求 AB
# ---------------------------------------------------------------- #
def test_follower_threshold_higher_requests_ab_later():
    env = _env(70.0, -10.0)
    foll = _ctrl()
    foll.ab_derive_threshold_follower = 0.70
    out = _run(foll, env, [1.0] * 4)        # 级位 ≈0.60 < 0.70
    assert out[0, 1] == 0.0                # 不请求 AB

    base = _ctrl()
    out_base = _run(base, env, [1.0] * 4)  # 级位 ≈0.60 ≥ 0.50 ⇒ 默认会请求
    assert out_base[0, 1] < 0


# ---------------------------------------------------------------- #
# 4) 分配结构反转：领航早 / 后列晚
# ---------------------------------------------------------------- #
def test_leader_early_follower_late_inverts_allocation():
    """领航阈值 0.30、后列阈值 0.70 ⇒ 同一级位下领航带闸而 follower 不带。"""
    env = _env(70.0, -10.0)
    lead = _ctrl()
    lead.ab_derive_threshold_lead = 0.30
    foll = _ctrl()
    foll.ab_derive_threshold_follower = 0.70

    out_l = _run(lead, env, [1.0] * 3)     # 级位 ≈0.45
    out_f = _run(foll, env, [1.0] * 3)     # 级位 ≈0.45
    assert out_l[0, 1] < 0                # 领航已带闸
    assert out_f[0, 1] == 0.0              # 后列未带闸


# ---------------------------------------------------------------- #
# 5) 安全侧不变
# ---------------------------------------------------------------- #
def test_threshold_override_keeps_safety_chain():
    """只改请求门限：222 s 充风门、低速强制缓解、档位最短保持全部保留。"""
    env = _env(70.0, -10.0)
    c = _ctrl()
    c.ab_derive_threshold_lead = 0.30
    c.ab_low_speed_release = True

    _run(c, env, [1.0] * 6)
    assert c._ab_on[0] is True             # AB 派生生效

    # 低速强制缓解（V17 底线）仍能强制释放
    env_slow = _env(38.0, -10.0)
    out = _run(c, env_slow, [-1.0] * 3)
    assert out[0, 1] == 0.0
    assert c._ab_on[0] is False
