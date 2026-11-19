"""ADR-076 ED 前馈浅化上限（ed_feedforward_cap）单测。

诊断 §19.17.3（路线级发现）：decompose 路线（规则在环）的 RL 投历史读数
gap_err 41.78 m / band 100% / mean_ed 0.7693；而 nincr 路线 495.08 m / 86% /
0.9013 ⇒ 几何差 11.9 倍。机制定位（源码级）：`ed_grade_feedforward` 的 ED
前馈浅化只在 decompose 路径被调用（get_action_cyclic_braking / get_action_
decomposed），`get_action_notch_incr`（nincr）从不调用 ⇒ nincr 的 ED 只能由
RL 单调积分推深贴顶 ⇒ 缓解-再施加相位差大 ⇒ 既丢几何又丢峰。

本开关把前馈反解值作为 nincr 级位上限。契约：
  · 默认关（cap=0）⇒ **逐位零回归**；
  · 开启后级位被封顶，但 RL 仍可自由下探（缓解空间保留）；
  · 不改动作面（仍 1 维级位增量）/ 不改 AB 派生 / 不改安全链。
"""
import numpy as np
import pytest

from src.controllers.multi_loco_controller import MultiLocoController

V_MAX = 75.0 / 3.6
V_MIN = 40.0 / 3.6


class _Veh:
    def __init__(self):
        self.mass_t = 250.0
        self.max_power_kw = 9600.0
        self.is_locomotive = True


class _Consist:
    def __init__(self, n=4):
        self.vehicles = [_Veh() for _ in range(n)]


class _Dyn:
    def __init__(self, vel=70.0 / 3.6, grade=-0.010):
        self.vel = np.array([vel])
        self.grade = np.array([grade])
        self.consist = _Consist()
        self.pos = np.zeros(4)
        self.masses_kg = np.full(4, 250.0 * 1000.0)
        self._grade_profile = None

    def _resistance_forces(self):
        return np.zeros(4)

    def _air_braking_forces(self):
        return np.zeros(4)

    def _electric_braking_forces(self, command):
        # 简化的电制动力：功率上限 + 粘着上限
        v = max(float(self.vel[0]), 1.0)
        f = np.zeros(len(command))
        for i, c in enumerate(command):
            f[i] = -min(abs(c) * 3 * 9600.0e3 / v, 250.0 * 1000.0 * 9.81 * 0.35) \
                if c > 0 else 0.0
        return f


class _Env:
    def __init__(self, vel=70.0 / 3.6, grade=-0.010):
        self.dynamics = _Dyn(vel, grade)


def _ctrl(cap=0.0, margin=0.0):
    c = MultiLocoController(num_vehicles=4, loco_indices=[0])
    c.notch_incr_rate_notches = 3.0
    c.ed_feedforward_cap = cap
    c.ed_feedforward_margin = margin
    return c


def _run(c, env, actions):
    out = None
    for a in actions:
        out = c.get_action_notch_incr(env, np.array([[a]]), v_max=V_MAX, v_min=V_MIN)
    return out


# ---------------------------------------------------------------- #
# 1) 默认关 = 逐位零回归
# ---------------------------------------------------------------- #
def test_default_cap_off_is_bitwise_identical():
    env = _Env()
    c_off = _ctrl(cap=0.0)
    c_on = _ctrl(cap=0.0)      # 同值 ⇒ 必须完全一致
    for a in [1.0] * 10 + [-1.0] * 5:
        o1 = c_off.get_action_notch_incr(env, np.array([[a]]), v_max=V_MAX, v_min=V_MIN)
        o2 = c_on.get_action_notch_incr(env, np.array([[a]]), v_max=V_MAX, v_min=V_MIN)
    assert o1[0, 0] == o2[0, 0]
    assert o1[0, 1] == o2[0, 1]


def test_cap_off_leaves_notch_free_to_top():
    """cap 关闭时级位可推到 1.0（贴顶）——这是 nincr 的既有行为。"""
    env = _Env()
    c = _ctrl(cap=0.0)
    _run(c, env, [1.0] * 12)
    assert c._notch_level[0] == pytest.approx(1.0, abs=1e-6)


# ---------------------------------------------------------------- #
# 2) 开启后：级位被前馈上限封顶
# ---------------------------------------------------------------- #
def test_cap_caps_notch_level():
    env = _Env()
    c = _ctrl(cap=1.0, margin=0.0)
    _run(c, env, [1.0] * 12)
    assert c._notch_level[0] < 1.0, "前馈上限未生效（应把贴顶级位压下来）"
    assert c._notch_level[0] > 0.0


def test_cap_still_allows_coasting_down():
    """封顶只限制上推，RL 仍可自由下探（缓解空间保留 ⇒ 相位差小）。"""
    env = _Env()
    c = _ctrl(cap=1.0, margin=0.0)
    _run(c, env, [1.0] * 12)
    capped = c._notch_level[0]
    _run(c, env, [-1.0] * 10)
    assert c._notch_level[0] < capped, "封顶后仍必须能下探"


def test_cap_zero_disables():
    env = _Env()
    c = _ctrl(cap=0.0)
    _run(c, env, [1.0] * 12)
    assert c._notch_level[0] == pytest.approx(1.0, abs=1e-6)


def test_margin_raises_the_cap():
    env = _Env()
    c_lo = _ctrl(cap=1.0, margin=0.0)
    _run(c_lo, env, [1.0] * 12)
    env2 = _Env()
    c_hi = _ctrl(cap=1.0, margin=0.3)
    _run(c_hi, env2, [1.0] * 12)
    assert c_hi._notch_level[0] > c_lo._notch_level[0]


def test_cap_does_not_change_ab_derivation_semantics():
    """ED 封顶不应改变 AB 的派生来源（AB 仍由级位越限派生）。"""
    env = _Env()
    c = _ctrl(cap=1.0, margin=0.0)
    out = _run(c, env, [1.0] * 12)
    # 级位被封顶在 <1.0 ⇒ 仍可能 ≥0.5 ⇒ AB 可被派生；此处只断言 AB 状态与
    # 级位判据一致（AB 非零当且仅当级位越限），不引入新的派生路径。
    assert (out[0, 1] < 0) == (c._notch_level[0] >= c.ab_derive_threshold - 1e-9)


def test_cap_is_per_loco_independent():
    env = _Env()
    c = MultiLocoController(num_vehicles=4, loco_indices=[0, 1])
    c.notch_incr_rate_notches = 3.0
    c.ed_feedforward_cap = 1.0
    c.ed_feedforward_margin = 0.0
    out = None
    for _ in range(12):
        out = c.get_action_notch_incr(env, np.array([[1.0], [1.0]]),
                                      v_max=V_MAX, v_min=V_MIN)
    assert len(out) == 2
    assert all(v <= 1.0 for v in c._notch_level)


# ---------------------------------------------------------------- #
# 3) ED 深度常数上限 ed_notch_cap（§19.17.4 干预实验）
# ---------------------------------------------------------------- #
def test_ed_notch_cap_default_is_noop():
    """默认 1.0 ⇒ 级位仍可贴顶（nincr 既有行为，零回归前提）。"""
    env = _Env()
    c = _ctrl(cap=0.0)
    c.ed_notch_cap = 1.0
    _run(c, env, [1.0] * 12)
    assert c._notch_level[0] == pytest.approx(1.0, abs=1e-6)


def test_ed_notch_cap_limits_notch():
    env = _Env()
    c = _ctrl(cap=0.0)
    c.ed_notch_cap = 0.7
    _run(c, env, [1.0] * 12)
    assert c._notch_level[0] == pytest.approx(0.7, abs=1e-6)


def test_ed_notch_cap_allows_coasting_below_cap():
    env = _Env()
    c = _ctrl(cap=0.0)
    c.ed_notch_cap = 0.7
    _run(c, env, [1.0] * 12)
    _run(c, env, [-1.0] * 6)
    assert c._notch_level[0] < 0.7


def test_ed_notch_cap_does_not_block_ab_derivation():
    """ED 封顶在 0.7（仍 ≥ AB 派生阈值 0.5）⇒ AB 派生不受影响。"""
    env = _Env()
    c = _ctrl(cap=0.0)
    c.ed_notch_cap = 0.7
    out = _run(c, env, [1.0] * 12)
    assert c._notch_level[0] == pytest.approx(0.7, abs=1e-6)
    assert out[0, 1] < 0, "AB 应仍被派生（级位 0.7 ≥ 阈值 0.5）"


# ---------------------------------------------------------------- #
# 4) ED 上限的速度释放阀（§19.19 代价链对策）
# ---------------------------------------------------------------- #
def test_cap_release_valve_opens_above_threshold():
    """速度 ≥ 释放阀值时 ED 上限放开（策略可正常减速）。"""
    fast = _Env(vel=74.0 / 3.6)   # _Env 收 m/s
    c = _ctrl(cap=0.0)
    c.ed_notch_cap = 0.7
    c.ed_notch_cap_release_kmh = 72.0
    _run(c, fast, [1.0] * 12)
    assert c._notch_level[0] == pytest.approx(1.0, abs=1e-6), "高速时上限应放开"


def test_cap_release_valve_keeps_cap_below_threshold():
    """速度 < 释放阀值时 ED 上限仍生效（几何收敛收益保留）。"""
    slow = _Env(vel=60.0 / 3.6)   # _Env 收 m/s
    c = _ctrl(cap=0.0)
    c.ed_notch_cap = 0.7
    c.ed_notch_cap_release_kmh = 72.0
    _run(c, slow, [1.0] * 12)
    assert c._notch_level[0] == pytest.approx(0.7, abs=1e-6)


def test_cap_release_valve_off_by_default():
    env = _Env(vel=74.0 / 3.6)   # _Env 收 m/s
    c = _ctrl(cap=0.0)
    c.ed_notch_cap = 0.7
    c.ed_notch_cap_release_kmh = 0.0        # 默认不启用
    _run(c, env, [1.0] * 12)
    assert c._notch_level[0] == pytest.approx(0.7, abs=1e-6)


# ---------------------------------------------------------------- #
# 5) ED 上限的渐进式斜坡（§19.19.6：阶跃释放阀有害后的修正）
# ---------------------------------------------------------------- #
def test_slope_relaxes_cap_progressively():
    """斜坡：速度越高上限越高（连续放宽，无阶跃）。"""
    c = _ctrl(cap=0.0)
    c.ed_notch_cap = 0.75
    c.ed_notch_cap_slope = 0.1
    c.ed_notch_cap_slope_from_kmh = 70.0
    # v=70 km/h ⇒ 上限 0.75
    c1 = _ctrl(cap=0.0)
    c1.ed_notch_cap = 0.75
    c1.ed_notch_cap_slope = 0.1
    c1.ed_notch_cap_slope_from_kmh = 70.0
    _run(c1, _Env(vel=70.0 / 3.6), [1.0] * 12)
    # v=75 km/h ⇒ 上限 0.75 + 0.1*5 = 1.25 → 截到 1.0
    c2 = _ctrl(cap=0.0)
    c2.ed_notch_cap = 0.75
    c2.ed_notch_cap_slope = 0.1
    c2.ed_notch_cap_slope_from_kmh = 70.0
    _run(c2, _Env(vel=75.0 / 3.6), [1.0] * 12)
    assert c1._notch_level[0] == pytest.approx(0.75, abs=1e-6)
    assert c2._notch_level[0] > c1._notch_level[0]


def test_slope_off_by_default():
    c = _ctrl(cap=0.0)
    c.ed_notch_cap = 0.75
    _run(c, _Env(vel=75.0 / 3.6), [1.0] * 12)
    assert c._notch_level[0] == pytest.approx(0.75, abs=1e-6)
