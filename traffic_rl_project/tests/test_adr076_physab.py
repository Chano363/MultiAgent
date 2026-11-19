"""ADR-076 待验证：物理触发式 AB 兜底接入 nincr（诊断 §19.14.2）。

机制：规则基线的 AB 兜底是**物理触发**（`_ed_ab_price(train_env) < 0.99`），
逐列 ed_avail 不同 ⇒ 领航 AB 率天然最高（实测 39% vs 中尾 4~6%）⇒ 减速责任
落在领航 ⇒ 几何收敛（gap_err 24.5 m）。我们 nincr 的 AB 是级位派生 ⇒ 分配方向
相反（领航 9% / 中尾 14%）⇒ 后列自己慢下来撑开净空 ⇒ 几何发散（654 m）。

**最终语义**（与规则基线的循环制动状态机同构）：
  · 物理不足（ed_avail < 阈值）⇒ **持续**请求/保持 AB；
  · 释放权仍归既有链：222 s 充风门 / 档位最短保持 / 低速强制缓解（V17 底线）
    / 车钩力源头 veto —— 全部保留，物理触发**不放松**任何一条；
  · 级位滞回在物理触发下**不单独触发释放**（否则与物理请求每步打架 ⇒ 1 步抖动，
    实测），释放改由 ed_avail 恢复驱动（缓坡/低速 ⇒ ED 足够 ⇒ 缓解）。

**测试口径**：用桩函数替换 `_ed_ab_price`（精确控制 ed_avail）验证触发逻辑；
ed_avail 的物理真实性（真实编组实测中位 0.418、99.06% 时间 <1，诊断 §14）
由整程探针验证。

覆盖：①默认关逐位零回归 ②ed_avail 不足 ⇒ 未越限也请求
      ③充风门在位 ⇒ 请求被拒（不放松安全门）④ed_avail 恢复 ⇒ 释放
      ⑤低速强制缓解仍能强制释放 ⑥阈值可调 ⑦级位滞回不单独触发释放
"""
import numpy as np
import pytest
from types import SimpleNamespace

from src.controllers.multi_loco_controller import MultiLocoController

V_MAX = 75.0 / 3.6
V_MIN = 40.0 / 3.6


class _FakeVehicle:
    def __init__(self):
        self.mass_t = 250.0
        self.max_power_kw = 9600.0
        self.is_locomotive = True


class _FakeConsist:
    def __init__(self):
        self.vehicles = [_FakeVehicle() for _ in range(4)]


class _FakeDyn:
    def __init__(self, vel_kmh=70.0):
        self.vel = np.array([vel_kmh / 3.6])
        self.grade = np.array([-0.010])
        self.consist = _FakeConsist()
        self.pos = np.zeros(4)


def _env(vel_kmh=70.0):
    return SimpleNamespace(dynamics=_FakeDyn(vel_kmh))


class _Stubbed(MultiLocoController):
    """ed_avail 可变的控制器（桩）。"""

    def __init__(self, avail=0.42, refill_s=0.0):
        super().__init__(num_vehicles=4, loco_indices=[0])
        self.notch_incr_rate_notches = 3.0
        self.ab_min_refill_s = float(refill_s)
        self._avail_stub = float(avail)

    def _ed_ab_price(self, train_env):
        return float(self._avail_stub)


def _ctrl(avail=0.42, refill_s=0.0):
    return _Stubbed(avail=avail, refill_s=refill_s)


def _run(ctrl, env, actions):
    out = None
    for a in actions:
        out = ctrl.get_action_notch_incr(
            env, np.array([[a]]), v_max=V_MAX, v_min=V_MIN)
    return out


# ---------------------------------------------------------------- #
# 1) 默认关 = 逐位零回归
# ---------------------------------------------------------------- #
def test_physical_trigger_default_off_is_zero_regression():
    env = _env()
    a = _ctrl()
    a.ab_physical_trigger = False
    b = _ctrl()

    seq = [1.0] * 6 + [-1.0] * 8
    oa = _run(a, env, seq)
    ob = _run(b, env, seq)
    assert oa[0, 0] == pytest.approx(ob[0, 0], abs=0.0)
    assert oa[0, 1] == pytest.approx(ob[0, 1], abs=0.0)


# ---------------------------------------------------------------- #
# 2) 开启 + ed_avail 不足 ⇒ 级位未越限也请求 AB
# ---------------------------------------------------------------- #
def test_physical_trigger_requests_ab_below_threshold():
    env = _env()
    c = _ctrl(avail=0.42)
    c.ab_physical_trigger = True
    c.ab_physical_avail_threshold = 0.99

    out = _run(c, env, [1.0] * 2)     # 级位 ≈0.30 < 派生阈值 0.5
    assert c._notch_level[0] < 0.5
    assert out[0, 1] < 0               # 物理触发 ⇒ AB 已请求并落地

    # 对照：关闭时同一场景不请求
    c2 = _ctrl(avail=0.42)
    out2 = _run(c2, env, [1.0] * 2)
    assert out2[0, 1] == 0.0


# ---------------------------------------------------------------- #
# 3) 充风门在位时：物理触发仍发起请求，但新增源被充风门拒（不放松安全门）
# ---------------------------------------------------------------- #
def test_physical_trigger_respects_refill_gate():
    """222 s 充风门在位 ⇒ 已释放过的源不能立刻重新新增（物理触发不放宽该门）。"""
    env = _env()
    c = _ctrl(refill_s=222.0, avail=0.42)
    c.ab_physical_trigger = True

    # 先让 AB 施加一次（充风门初始放行）
    _run(c, env, [1.0] * 2)
    assert c._ab_on[0] is True
    # 物理恢复 ⇒ 释放（记 _ab_last_release_step）
    c._avail_stub = 1.5
    _run(c, env, [-1.0] * 6)
    assert c._ab_on[0] is False

    # 再次物理不足 ⇒ 请求新增，但 222 s 未到 ⇒ 被充风门拒
    c._avail_stub = 0.42
    before = c.ab_refill_veto_count
    out = _run(c, env, [1.0] * 2)
    assert out[0, 1] == 0.0                  # 未落地（被充风门拒）
    assert c.ab_refill_veto_count > before    # 但确实发起了请求 ⇒ 只加不减、不放松安全门


# ---------------------------------------------------------------- #
# 4) ed_avail 恢复（ED 足够）⇒ 释放
# ---------------------------------------------------------------- #
def test_physical_trigger_releases_when_ed_sufficient():
    env = _env()
    c = _ctrl(avail=0.42)
    c.ab_physical_trigger = True

    _run(c, env, [1.0] * 2)
    assert c._ab_on[0] is True

    # 物理恢复：ed_avail ≥ 阈值 ⇒ ED 足够 ⇒ 允许缓解
    c._avail_stub = 1.5
    out = _run(c, env, [-1.0] * 6)
    assert out[0, 1] == 0.0
    assert c._ab_on[0] is False


# ---------------------------------------------------------------- #
# 5) 安全侧不变：低速强制缓解仍能强制释放
# ---------------------------------------------------------------- #
def test_physical_trigger_keeps_low_speed_release():
    env = _env()
    c = _ctrl(avail=0.42)
    c.ab_physical_trigger = True
    c.ab_low_speed_release = True

    _run(c, env, [1.0] * 2)
    assert c._ab_on[0] is True

    env_slow = _env(38.0)
    out = _run(c, env_slow, [-1.0] * 3)
    assert out[0, 1] == 0.0
    assert c._ab_on[0] is False


# ---------------------------------------------------------------- #
# 6) 阈值可调（触发条件 = ed_avail < threshold）
# ---------------------------------------------------------------- #
def test_physical_trigger_threshold_is_tunable():
    env = _env()
    c = _ctrl(avail=0.42)
    c.ab_physical_trigger = True

    c.ab_physical_avail_threshold = 0.50     # 门槛 > avail(0.42) ⇒ 触发
    out = _run(c, env, [1.0] * 2)
    assert out[0, 1] < 0

    c2 = _ctrl(avail=0.42)
    c2.ab_physical_trigger = True
    c2.ab_physical_avail_threshold = 0.30    # 门槛 < avail(0.42) ⇒ 不触发
    out2 = _run(c2, env, [1.0] * 2)
    assert out2[0, 1] == 0.0


# ---------------------------------------------------------------- #
# 7) 级位滞回不单独触发释放（避免 1 步抖动）
# ---------------------------------------------------------------- #
def test_physical_trigger_no_one_step_chatter():
    """物理不足期间：级位下探不得造成 on/off 抖动（实测旧实现会抖）。"""
    env = _env()
    c = _ctrl(avail=0.42)
    c.ab_physical_trigger = True

    seq = [1.0] * 4 + [-1.0] * 6
    states = []
    for a in seq:
        out = _run(c, env, [a])
        states.append(bool(out[0, 1] < 0))
    # 全程物理不足 ⇒ AB 持续在场，无抖动
    assert all(states), "物理不足期间出现 AB 释放（抖动）"
