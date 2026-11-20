"""ADR-076 AB 保持/释放改用「当前实际坡度」的物理判据（`ab_release_by_local_grade`）。

诊断 §19.21 的判别结论：
  · `ed_avail` 的需求项 F_req 取**全剖面最陡下坡**（`_ed_ab_price`:
    `steepest_down = max(0, -min(grades))`）⇒ **位置无关**；且 F_ed = P/v 随速度
    降低而增大 ⇒ **低速时 ed_avail 反而 ≥ 1 ⇒ 误判「ED 已够用」⇒ 释放 AB
    ⇒ 222 s 充风门锁死 ⇒ 陡坡拖停**（今早物理触发整程 peak 1842.4 / 尾列末速 0.0
    的死因）。
  · 陡坡上**纯 ED 物理上无法平衡**：沿坡分力 ≈1163 kN > 单台机车粘着上限 ≈645 kN
    ⇒ AB 是物理刚需，释放代价极高。
  ⇒ 改用**位置相关**的 `_ed_cannot_hold_speed`（按各车实际坡度算）：
    陡坡（含低速）保持 AB；进缓坡才释放。

契约：默认关 = 逐位零回归；开启后只改 AB 的**保持/释放**判据，
不动动作面/物理/奖励面/安全层（222 s 充风门、档位最短保持、低速强制缓解、
车钩 veto 全在）。
"""
import numpy as np
import pytest

from src.controllers.multi_loco_controller import MultiLocoController

V_MAX = 75.0 / 3.6
V_MIN = 40.0 / 3.6


class _Veh:
    def __init__(self, loco=True):
        self.mass_t = 188.0 if loco else 100.0
        self.max_power_kw = 9600.0
        self.is_locomotive = loco
        self.length_m = 21.0 if loco else 14.0


class _Consist:
    def __init__(self, n=109):
        self.vehicles = [_Veh(loco=(i == 0)) for i in range(n)]


class _Dyn:
    def __init__(self, vel=70.0 / 3.6, grade=-0.010):
        self.vel = np.array([vel])
        self.grade = np.array([grade])
        self.consist = _Consist()
        self.pos = np.zeros(len(self.consist.vehicles))
        self.masses_kg = np.array([v.mass_t * 1000.0
                                   for v in self.consist.vehicles])
        self._grade_profile = None

    def _resistance_forces(self):
        return np.zeros(len(self.masses_kg))

    def _air_braking_forces(self):
        return np.zeros(len(self.masses_kg))

    def _electric_braking_forces(self, command):
        v = max(float(self.vel[0]), 1.0)
        out = np.zeros(len(command))
        for i, c in enumerate(command):
            if c > 0:
                out[i] = -min(c * 9600.0e3 / v,
                              0.35 * 188.0e3 * 9.81)
        return out


class _Env:
    def __init__(self, vel=70.0 / 3.6, grade=-0.010):
        self.dynamics = _Dyn(vel, grade)


def _ctrl(**kw):
    c = MultiLocoController(num_vehicles=109, loco_indices=[0])
    c.notch_incr_rate_notches = 3.0
    c.ab_min_refill_s = 0.0     # 充风门放开，聚焦判据本身
    for k, v in kw.items():
        setattr(c, k, v)
    return c


def _run(c, env, actions):
    out = None
    for a in actions:
        out = c.get_action_notch_incr(env, np.array([[a]]),
                                      v_max=V_MAX, v_min=V_MIN)
    return out


# ---------------------------------------------------------------- #
# 1) 默认关 = 逐位零回归
# ---------------------------------------------------------------- #
def test_default_off_is_bitwise_identical():
    env = _Env()
    a = _ctrl()
    b = _ctrl(ab_release_by_local_grade=False)
    for act in [1.0] * 6 + [-1.0] * 3:
        o1 = a.get_action_notch_incr(env, np.array([[act]]), v_max=V_MAX, v_min=V_MIN)
        o2 = b.get_action_notch_incr(env, np.array([[act]]), v_max=V_MAX, v_min=V_MIN)
    assert o1[0, 0] == o2[0, 0]
    assert o1[0, 1] == o2[0, 1]


# ---------------------------------------------------------------- #
# 2) 位置相关语义：陡坡判「ED 不够」⇒ 保持 AB；缓坡判「够用」⇒ 允许释放
# ---------------------------------------------------------------- #
def test_steep_grade_holds_ab_even_at_low_speed():
    """陡坡（-10‰）低速时仍判 ED 不够 ⇒ 保持 AB（不误释放）。"""
    env = _Env(vel=45.0 / 3.6, grade=-0.010)
    c = _ctrl(ab_release_by_local_grade=True)
    assert c._ed_cannot_hold_speed(env) is True, "陡坡应判 ED 不足以维持速度"
    _run(c, env, [1.0] * 6)
    assert c._ab_on[0] is True, "陡坡下 AB 应保持"


def test_mild_grade_allows_release():
    """缓坡（-1.5‰）判 ED 够用 ⇒ 级位下探可释放。"""
    env = _Env(vel=60.0 / 3.6, grade=-0.0015)
    c = _ctrl(ab_release_by_local_grade=True)
    assert c._ed_cannot_hold_speed(env) is False, "缓坡应判 ED 足够"
    _run(c, env, [1.0] * 6)
    _run(c, env, [-1.0] * 4)
    assert c._ab_on[0] is False, "缓坡下级位下探应可释放"


def test_local_grade_judgement_is_position_dependent():
    """同一速度下，陡坡判不够、缓坡判够 —— 证明判据是位置相关而非速度相关。"""
    steep = _Env(vel=60.0 / 3.6, grade=-0.010)
    mild = _Env(vel=60.0 / 3.6, grade=-0.0015)
    c = _ctrl(ab_release_by_local_grade=True)
    assert c._ed_cannot_hold_speed(steep) is True
    assert c._ed_cannot_hold_speed(mild) is False


# ---------------------------------------------------------------- #
# 3) 安全链不受影响
# ---------------------------------------------------------------- #
def test_low_speed_release_still_works_with_local_grade():
    """低速强制缓解（V17 底线）仍能强制释放 AB，即使陡坡判「ED 不够」。"""
    env = _Env(vel=38.0 / 3.6, grade=-0.010)
    c = _ctrl(ab_release_by_local_grade=True)
    c.ab_low_speed_release = True
    c.ab_low_speed_margin_mps = 2.0 / 3.6
    _run(c, env, [1.0] * 4)
    out = _run(c, env, [-1.0] * 3)
    assert out[0, 1] == 0.0, "低速兜底必须能强制释放"
    assert c._ab_on[0] is False


def test_refill_gate_still_blocks_new_source():
    """222 s 充风门仍拦新增 AB 源（不放宽任何安全门）。

    注：充风门对**第一个**源放行（`_ab_last_release_step` 初值 −1e9），
    故须先让 AB 释放过一次产生 release 记录，后续新增源才应被拒。
    """
    env_mild = _Env(vel=60.0 / 3.6, grade=-0.0015)   # 缓坡：允许释放
    env_steep = _Env(vel=60.0 / 3.6, grade=-0.010)   # 陡坡：物理不足 ⇒ 想重新施加
    c = _ctrl(ab_release_by_local_grade=True, ab_min_refill_s=222.0)
    # 1) 缓坡：上推让 AB on，再下探释放（产生 release 记录）
    _run(c, env_mild, [1.0] * 8)
    assert c._ab_on[0] is True
    _run(c, env_mild, [-1.0] * 6)
    assert c._ab_on[0] is False
    # 2) 陡坡：物理不足 ⇒ 请求重新施加，但被 222 s 充风门拒
    before = c.ab_refill_veto_count
    out = _run(c, env_steep, [1.0] * 2)
    assert out[0, 1] == 0.0                  # 未落地
    assert c.ab_refill_veto_count > before   # 但确实发起了请求


def test_notch_derivation_still_works():
    """AB 仍由级位越限派生（判据只改保持/释放，不改派生来源）。"""
    env = _Env(vel=60.0 / 3.6, grade=-0.0015)
    c = _ctrl(ab_release_by_local_grade=True)
    out = _run(c, env, [1.0] * 8)
    assert out[0, 1] < 0, "级位越限应仍派生 AB"
