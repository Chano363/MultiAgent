"""朔黄表3 运营口径标定契约（2026-10-14，ADR-036/037）。

覆盖：CYCLIC(50 kPa) 档映射与常量、升档 rank 序、独立触发/缓解速度门、
ED 缓解协同时序（抬 900 kN 持 50 s）、kN→frac 换算锚、默认关=旧行为零回归。
"""
import numpy as np
import pytest

from src.environments.train_env import TrainFormationEnv
from src.environments.train_fleet_env import TrainFleetEnv
from src.controllers.multi_loco_controller import MultiLocoController
from src.train_dynamics.braking import (
    AirBrakeNotch, notch_from_throttle, AIR_BRAKE_RATIO, BRAKE_NOTCH_REDUCTION_KPA,
)
from src.train_dynamics.train import TrainDynamics


def _setup(**ctrl_kw):
    env = TrainFormationEnv({'consist_preset': '10kt_1plus1'})
    env.reset(options={'speed': 80 / 3.6})
    env.dynamics.set_grade(-0.012)
    ctrl = MultiLocoController(env.num_vehicles, env.loco_indices, **ctrl_kw)
    return env, ctrl


# ── CYCLIC 档映射与常量 ────────────────────────────────────────────────

def test_cyclic_notch_constants():
    assert AIR_BRAKE_RATIO[AirBrakeNotch.CYCLIC] == pytest.approx(0.17)
    assert BRAKE_NOTCH_REDUCTION_KPA[AirBrakeNotch.CYCLIC] == pytest.approx(50.0)


def test_sentinel_maps_to_cyclic_only_when_allowed():
    # 默认关：哨兵值 -0.05 落旧 MIN 带（逐位旧行为，零回归）
    assert notch_from_throttle(-0.05) is AirBrakeNotch.MIN
    # 开启：-0.05 ∈ (1e-6, 0.1) → CYCLIC
    assert notch_from_throttle(-0.05, allow_cyclic=True) is AirBrakeNotch.CYCLIC
    # 其他既有档位映射不受 allow_cyclic 影响（RL 兜底 -0.4 / 基线 -0.75 均 SERVICE）
    for allow in (False, True):
        assert notch_from_throttle(0.0, allow_cyclic=allow) is AirBrakeNotch.RELEASE
        assert notch_from_throttle(-0.4, allow_cyclic=allow) is AirBrakeNotch.SERVICE
        assert notch_from_throttle(-0.75, allow_cyclic=allow) is AirBrakeNotch.SERVICE
        assert notch_from_throttle(-0.15, allow_cyclic=allow) is AirBrakeNotch.MIN


def test_cyclic_rank_between_release_and_min():
    r = TrainDynamics._air_notch_rank
    assert r(AirBrakeNotch.RELEASE) < r(AirBrakeNotch.CYCLIC) < r(AirBrakeNotch.MIN)
    assert r(AirBrakeNotch.MIN) < r(AirBrakeNotch.SERVICE) < r(AirBrakeNotch.EMERGENCY)


# ── 独立触发/缓解速度门（表3：触发 58–65 / 缓解 50–60）─────────────────

def test_trigger_gate_brakes_early_without_relaxing_defense():
    env, ctrl = _setup(cyclic_brake_trigger_kmh=65.0)
    try:
        env.dynamics.vel[:] = 66 / 3.6
        ctrl.get_action_cyclic_braking(env)
        assert ctrl._cyclic_braking                # 66≥65 门 → 提前触发（旧行为 66<80 不触发）
    finally:
        env.close()

    env2, ctrl2 = _setup(cyclic_brake_trigger_kmh=85.0)
    try:
        # 触发门不得放宽超速防线：门=85 时 82 km/h 仍必须触发（夹回 80）
        env2.dynamics.vel[:] = 82 / 3.6
        ctrl2.get_action_cyclic_braking(env2)
        assert ctrl2._cyclic_braking
    finally:
        env2.close()

    env3, ctrl3 = _setup()                         # 默认无门
    try:
        env3.dynamics.vel[:] = 66 / 3.6
        ctrl3.get_action_cyclic_braking(env3)
        assert not ctrl3._cyclic_braking           # 旧行为：66<80 不触发
    finally:
        env3.close()


def test_release_gate_releases_above_vmin():
    env, gated = _setup(cyclic_brake_trigger_kmh=65.0, cyclic_release_kmh=55.0)
    try:
        env.dynamics.vel[:] = 66 / 3.6
        gated.get_action_cyclic_braking(env)
        assert gated._cyclic_braking
        env.dynamics.vel[:] = 54 / 3.6
        gated.get_action_cyclic_braking(env)
        assert not gated._cyclic_braking            # 54≤55 门 → 提前缓解（旧需 ≤40）
    finally:
        env.close()

    env2, plain = _setup(cyclic_brake_trigger_kmh=65.0)  # 无缓解门
    try:
        env2.dynamics.vel[:] = 66 / 3.6
        plain.get_action_cyclic_braking(env2)
        env2.dynamics.vel[:] = 54 / 3.6
        plain.get_action_cyclic_braking(env2)
        assert plain._cyclic_braking                # 旧行为：54>40 不缓解
    finally:
        env2.close()


def test_release_gate_clamped_below_suppress_ceiling():
    # 门=79 km/h 必须被夹到 release_ceiling(=80−0.5 m/s≈78.2)，不得在超速带内缓解
    env, ctrl = _setup(cyclic_release_kmh=79.0)
    try:
        env.dynamics.vel[:] = 80 / 3.6
        ctrl.get_action_cyclic_braking(env)
        assert ctrl._cyclic_braking
        env.dynamics.vel[:] = 79 / 3.6
        ctrl.get_action_cyclic_braking(env)
        assert ctrl._cyclic_braking                 # 未夹则 79≤79 会误缓解
    finally:
        env.close()


# ── ED 缓解协同时序（表3：缓解时抬 ≈900 kN 持 50 s）───────────────────

def test_ed_release_coordination_hold_window():
    env, ctrl = _setup(cyclic_brake_trigger_kmh=65.0, cyclic_release_kmh=55.0,
                       ed_release_coordination=True, ed_release_hold_s=50.0)
    try:
        env.dynamics.vel[:] = 66 / 3.6
        ctrl.get_action_cyclic_braking(env)
        assert ctrl._ed_hold_steps == 0             # 制动分支清零
        env.dynamics.vel[:] = 54 / 3.6
        act = ctrl.get_action_cyclic_braking(env)   # 触发缓解转换 → 进入 hold
        assert not ctrl._cyclic_braking
        assert ctrl._ed_hold_steps == int(round(50.0 / ctrl.dt)) - 1
        assert np.all(act[:, 0] > 0.5)              # 抬 ED（54 km/h 时 900 kN→frac≈0.83）
        assert np.all(act[:, 1] == 0)               # 缓解窗口不新增 AB
        ctrl._ed_hold_steps = 1
        act = ctrl.get_action_cyclic_braking(env)
        assert np.all(act[:, 0] > 0.5)
        assert ctrl._ed_hold_steps == 0
        act = ctrl.get_action_cyclic_braking(env)   # hold 用尽 → 回旧缓解输出（零）
        np.testing.assert_array_equal(act, 0)
    finally:
        env.close()


def test_coordination_off_default_zero_regression():
    env, ctrl = _setup()                            # 全默认关
    try:
        assert ctrl.ed_release_coordination is False
        env.dynamics.vel[:] = 80 / 3.6
        ctrl.get_action_cyclic_braking(env)
        assert ctrl._cyclic_braking
        env.dynamics.vel[:] = 39 / 3.6
        act = ctrl.get_action_cyclic_braking(env)   # 旧缓解路径
        assert not ctrl._cyclic_braking
        assert ctrl._ed_hold_steps == 0
        np.testing.assert_array_equal(act, 0)
    finally:
        env.close()


# ── 制动分支 AB 档选择（CYCLIC 哨兵 vs 旧 SERVICE）─────────────────────

def test_brake_branch_ab_sentinel_vs_service():
    env, cyclic = _setup(cyclic_notch_50=True)
    try:
        cyclic._ed_ab_price = lambda e: 0.5         # 强制 ED 不足 → AB 兜底分支
        env.dynamics.vel[:] = 80 / 3.6
        act = cyclic.get_action_cyclic_braking(env)
        np.testing.assert_allclose(act[:, 1], MultiLocoController.CYCLIC_AB_SENTINEL)
    finally:
        env.close()

    env2, plain = _setup()                          # 默认关 → 旧 brake_notch
    try:
        plain._ed_ab_price = lambda e: 0.5
        env2.dynamics.vel[:] = 80 / 3.6
        act = plain.get_action_cyclic_braking(env2)
        np.testing.assert_allclose(act[:, 1], -0.75)
    finally:
        env2.close()


# ── kN→frac 换算锚（表3：55 km/h 时 900 kN≈0.84 / 300 kN≈0.28）────────

def test_ed_frac_for_total_kn_anchor():
    env, ctrl = _setup()
    try:
        env.dynamics.vel[:] = 55 / 3.6
        assert ctrl._ed_frac_for_total_kn(env, 900.0) == pytest.approx(0.84, abs=0.02)
        assert ctrl._ed_frac_for_total_kn(env, 300.0) == pytest.approx(0.28, abs=0.02)
        assert ctrl._ed_frac_for_total_kn(env, 10000.0) == pytest.approx(1.0)  # clip 上限
    finally:
        env.close()


# ── H 组（2026-10-15/16）：300 kN 循环 floor 不被车钩 scale 侵蚀 ─────────
# 机理（G 组 t≈678s 探针）：峰值/limit>0.8 → scale 线性归零 → floor×scale=0
# → 前部"无 ED 只剩 AB" → 压缩正反馈。契约：scale=0 时制动分支 ED ≥ floor。

def test_cyclic_ed_floor_survives_coupler_scale_zero():
    env, ctrl = _setup(ed_release_coordination=True, ed_release_hold_s=50.0)
    try:
        ctrl._ed_ab_price = lambda e: 0.5            # 强制走 AB 兜底分支
        env.dynamics.vel[:] = 80 / 3.6               # 触发循环制动
        ctrl.get_action_cyclic_braking(env)
        assert ctrl._cyclic_braking
        ctrl._coupler_throttle_scale = lambda e: 0.0  # 模拟高压缩（ratio≥1）
        act = ctrl.get_action_cyclic_braking(env)
        floor = ctrl._ed_frac_for_total_kn(env, MultiLocoController.CYCLIC_ED_FLOOR_KN)
        assert floor > 0
        assert np.all(act[:, 0] >= floor - 1e-9)      # floor 不再乘 scale
    finally:
        env.close()


def test_decomposed_final_ed_floor_survives_scale_zero():
    # 【J 组 2026-10-16】I≡H 逐位相同的根因：baseline 制动分支已保住 floor，
    # 但 get_action_decomposed 末尾 `final[:,0] *= scale` 把它二次清零。
    # 契约：scale=0 + 循环制动分支 + 协调开 → final ED ≥ floor（与 baseline 同口径）。
    env, ctrl = _setup(ed_release_coordination=True, ed_release_hold_s=50.0,
                       ed_baseline_projection='legacy')
    try:
        env.dynamics.vel[:] = 80 / 3.6
        ctrl.get_action_cyclic_braking(env)            # 进入循环制动（latch）
        assert ctrl._cyclic_braking
        ctrl._coupler_throttle_scale = lambda e: 0.0   # 模拟 ratio≥1 高压缩
        final, baseline = ctrl.get_action_decomposed(env, np.zeros((2, 2)))
        floor = ctrl._ed_frac_for_total_kn(env, MultiLocoController.CYCLIC_ED_FLOOR_KN)
        assert floor > 0
        assert np.all(final[:, 0] >= floor - 1e-9)      # final 未被 scale 二次清零
        assert np.all(baseline[:, 0] >= floor - 1e-9)   # baseline 口径不变
    finally:
        env.close()


def test_decomposed_floor_off_when_coordination_disabled():
    # 默认关（协调不开）= 旧行为零回归：scale=0 时 final ED 允许被清零
    env, ctrl = _setup(ed_baseline_projection='legacy')
    try:
        env.dynamics.vel[:] = 80 / 3.6
        ctrl.get_action_cyclic_braking(env)
        assert ctrl._cyclic_braking and not ctrl.ed_release_coordination
        ctrl._coupler_throttle_scale = lambda e: 0.0
        final, _ = ctrl.get_action_decomposed(env, np.zeros((2, 2)))
        np.testing.assert_array_equal(final[:, 0], 0.0)   # 旧行为：scale 清零
    finally:
        env.close()


def test_decomposed_floor_not_applied_when_not_braking():
    # 缓解段（非循环制动）不抬 floor：boost/hold 窗口走 baseline 原逻辑
    env, ctrl = _setup(ed_release_coordination=True, ed_release_hold_s=0.0,
                       cyclic_brake_trigger_kmh=65.0,
                       ed_baseline_projection='legacy')
    try:
        env.dynamics.vel[:] = 66 / 3.6
        ctrl.get_action_cyclic_braking(env)            # 66≥65 → 触发制动
        env.dynamics.vel[:] = 40 / 3.6                 # ≤ v_min(40) → 缓解
        ctrl.get_action_cyclic_braking(env)            # _cyclic_braking=False
        assert not ctrl._cyclic_braking
        ctrl._ed_hold_steps = 0                        # 排除 hold 窗口
        ctrl._coupler_throttle_scale = lambda e: 0.0
        final, _ = ctrl.get_action_decomposed(env, np.zeros((2, 2)))
        np.testing.assert_array_equal(final[:, 0], 0.0)   # 非制动段不抬 floor
    finally:
        env.close()


def test_release_boost_kn_configurable():
    env, ctrl = _setup(cyclic_brake_trigger_kmh=65.0, cyclic_release_kmh=55.0,
                       ed_release_coordination=True, ed_release_hold_s=50.0,
                       ed_release_boost_kn=300.0)     # 文献锚定调低（Oxford 50%≈230）
    try:
        assert ctrl.ed_release_boost_kn == 300.0
        ctrl._coupler_throttle_scale = lambda e: 1.0  # 隔离 scale（本测只验 boost 档位）
        env.dynamics.vel[:] = 66 / 3.6
        ctrl.get_action_cyclic_braking(env)           # 进入制动分支
        env.dynamics.vel[:] = 44 / 3.6
        act = ctrl.get_action_cyclic_braking(env)     # 缓解转换 → hold 窗口
        assert ctrl._ed_hold_steps > 0
        # hold 窗口 ED = 300 kN 的 frac（44 km/h 下 ≈0.30），且 < 900 kN 档
        expect = ctrl._ed_frac_for_total_kn(env, 300.0)
        np.testing.assert_allclose(act[:, 0], expect, rtol=1e-6)
        assert expect < 0.8                          # 明显低于表3 900 kN 档
    finally:
        env.close()


def test_release_boost_default_is_900kN_table3():
    env, ctrl = _setup(ed_release_coordination=True)
    try:
        assert ctrl.ed_release_boost_kn == 900.0      # 默认=表3 口径
    finally:
        env.close()


# ── I 组（2026-10-16）：coupler_override 配置接线（安全层规则 A 档位）────

def test_coupler_override_wiring_default_release():
    # 默认 'release'：单列 env 直构 + fleet 透传 = 旧行为零回归
    env = TrainFormationEnv({'consist_preset': '10kt_1plus1'})
    try:
        assert env.coupler_override == 'release'
        assert env.safety.coupler_override == 'release'
    finally:
        env.close()

    fleet = TrainFleetEnv({'num_trains': 1, 'consist_preset': '10kt_1plus1'})
    try:
        assert fleet.coupler_override == 'release'
        assert fleet.trains[0].safety.coupler_override == 'release'
    finally:
        fleet.close()


def test_coupler_override_min_brake_wired_through_fleet():
    # 'min_brake'：fleet env_cfg → 内层单列 env → SafetyLayer 规则 A 档位
    fleet = TrainFleetEnv({'num_trains': 1, 'consist_preset': '10kt_1plus1',
                           'coupler_override': 'min_brake'})
    try:
        assert fleet.coupler_override == 'min_brake'
        assert fleet.trains[0].coupler_override == 'min_brake'
        assert fleet.trains[0].safety.coupler_override == 'min_brake'
    finally:
        fleet.close()


# ── K 组（2026-10-16）：CYCLIC 兜底 AB 预升级（先于 ATP 规则 C 事后猛刹）────
# 机理（J 负结果归档时间线）：最陡段 CYCLIC 制动力不足 → 车速缓爬到 80 →
# ATP 规则 C 事后把全列改 SERVICE 单源猛刹 → 头波撞中后部成 2530 kN 主团簇。
# 契约：速度达预升级门时，规则层自己先把 CYCLIC 兜底升为 SERVICE（错峰双源）。

def test_cyclic_ab_upgrade_default_off_zero_regression():
    # 默认 None = 旧行为：任何车速下 CYCLIC 兜底档不变（零回归）
    env, ctrl = _setup(cyclic_notch_50=True, cyclic_brake_trigger_kmh=65.0)
    try:
        assert ctrl.cyclic_ab_upgrade_kmh is None
        ctrl._ed_ab_price = lambda e: 0.5          # 强制 ED 不足 → AB 兜底分支
        env.dynamics.vel[:] = 79 / 3.6             # 高于任意常见升级门，验证默认关不升级
        ctrl.get_action_cyclic_braking(env)        # 65 门 → 已触发循环制动
        assert ctrl._cyclic_braking
        act = ctrl.get_action_cyclic_braking(env)
        np.testing.assert_allclose(act[:, 1], MultiLocoController.CYCLIC_AB_SENTINEL)
    finally:
        env.close()


def test_cyclic_ab_upgrade_triggers_at_margin():
    # 升级门 76 km/h：75.9 保持 CYCLIC，76.1 预升级 SERVICE（brake_notch=-0.75）
    env, ctrl = _setup(cyclic_notch_50=True, cyclic_brake_trigger_kmh=65.0,
                       cyclic_ab_upgrade_kmh=76.0)
    try:
        ctrl._ed_ab_price = lambda e: 0.5
        env.dynamics.vel[:] = 75.9 / 3.6
        ctrl.get_action_cyclic_braking(env)        # 触发循环制动（65 门）
        assert ctrl._cyclic_braking
        act = ctrl.get_action_cyclic_braking(env)
        np.testing.assert_allclose(act[:, 1], MultiLocoController.CYCLIC_AB_SENTINEL)
        env.dynamics.vel[:] = 76.1 / 3.6           # 达预升级门
        act = ctrl.get_action_cyclic_braking(env)
        np.testing.assert_allclose(act[:, 1], -0.75)   # SERVICE（140 kPa）
        # 预升级仅在制动分支生效：缓解段（≤40）无 AB 输出，不误升级
        env.dynamics.vel[:] = 40 / 3.6
        act = ctrl.get_action_cyclic_braking(env)
        assert not ctrl._cyclic_braking
        np.testing.assert_array_equal(act[:, 1], 0.0)
    finally:
        env.close()


def test_cyclic_ab_upgrade_ed_only_window():
    # 【L 组】K 负结果补洞：最陡段 ed_avail≥0.99 → ab_nominal=0.0（纯 ED 无 AB），
    # 原条件只认 CYCLIC 哨兵，该空窗预升级永不成立，ATP 规则 C 三次抢先猛刹。
    # 契约：0.0 空窗同样纳入升级条件——v ≥ 76 门即发 SERVICE(-0.75)。
    env, ctrl = _setup(cyclic_notch_50=True, cyclic_brake_trigger_kmh=65.0,
                       cyclic_ab_upgrade_kmh=76.0)
    try:
        ctrl._ed_ab_price = lambda e: 0.99          # ED 足够 → ab_nominal 走 0.0 空窗
        env.dynamics.vel[:] = 75.9 / 3.6            # 门下：保持 ED-only（0.0），不误升级
        ctrl.get_action_cyclic_braking(env)
        assert ctrl._cyclic_braking
        act = ctrl.get_action_cyclic_braking(env)
        np.testing.assert_array_equal(act[:, 1], 0.0)
        env.dynamics.vel[:] = 77.0 / 3.6            # 达升级门 → 空窗同样升 SERVICE
        act = ctrl.get_action_cyclic_braking(env)
        np.testing.assert_allclose(act[:, 1], -0.75)
    finally:
        env.close()

    # 默认关（None）：ED-only 空窗保持 0.0，零回归
    env2, ctrl2 = _setup(cyclic_notch_50=True, cyclic_brake_trigger_kmh=65.0)
    try:
        ctrl2._ed_ab_price = lambda e: 0.99
        env2.dynamics.vel[:] = 79 / 3.6
        ctrl2.get_action_cyclic_braking(env2)
        assert ctrl2._cyclic_braking
        act = ctrl2.get_action_cyclic_braking(env2)
        np.testing.assert_array_equal(act[:, 1], 0.0)
    finally:
        env2.close()


def test_cyclic_ab_upgrade_notch_min_intermediate():
    # 【M 组】升级档强度：'min' 时预升级发 -0.15 → notch_from_throttle → MIN(70 kPa)
    # 而非 SERVICE(-0.75, 140 kPa)；默认 'service' = K/L 行为逐位不变（零回归）。
    env, ctrl = _setup(cyclic_notch_50=True, cyclic_brake_trigger_kmh=65.0,
                       cyclic_ab_upgrade_kmh=76.0, cyclic_ab_upgrade_notch='min')
    try:
        ctrl._ed_ab_price = lambda e: 0.5
        env.dynamics.vel[:] = 76.1 / 3.6
        ctrl.get_action_cyclic_braking(env)
        assert ctrl._cyclic_braking
        act = ctrl.get_action_cyclic_braking(env)
        np.testing.assert_allclose(act[:, 1], -0.15)
        # 档位确实映射为 MIN（不是 CYCLIC/SERVICE）
        assert notch_from_throttle(-0.15, allow_cyclic=True) is AirBrakeNotch.MIN
        # 门下保持 CYCLIC 哨兵（升级档强度不改门槛语义）
        env.dynamics.vel[:] = 75.9 / 3.6
        act = ctrl.get_action_cyclic_braking(env)
        np.testing.assert_allclose(act[:, 1], MultiLocoController.CYCLIC_AB_SENTINEL)
    finally:
        env.close()

    # 默认 'service' = K/L 逐位不变
    env2, ctrl2 = _setup(cyclic_notch_50=True, cyclic_brake_trigger_kmh=65.0,
                         cyclic_ab_upgrade_kmh=76.0)
    try:
        assert ctrl2.cyclic_ab_upgrade_notch == 'service'
        ctrl2._ed_ab_price = lambda e: 0.5
        env2.dynamics.vel[:] = 76.1 / 3.6
        ctrl2.get_action_cyclic_braking(env2)
        act = ctrl2.get_action_cyclic_braking(env2)
        np.testing.assert_allclose(act[:, 1], -0.75)
    finally:
        env2.close()

    # 非法值直接拒绝（配置错配不静默回退）
    with pytest.raises(ValueError):
        _setup(cyclic_ab_upgrade_notch='emergency')


def test_ed_upgrade_ramp_downscales_ed_within_window():
    # 【Z 组】release→braking **施加沿**启动 ramp 窗 → 窗内 ED × scale（尾波到齐前
    # 头中不猛减速）；窗到期恢复满值。参数沿用 Y2 验证剂量 6.0/0.7。
    env, ctrl = _setup(cyclic_notch_50=True, cyclic_brake_trigger_kmh=65.0,
                       cyclic_ab_upgrade_kmh=76.0,
                       ed_upgrade_ramp_s=0.5, ed_upgrade_ramp_scale=0.7)
    try:
        ctrl._ed_ab_price = lambda e: 0.5   # ED 不满 → 走 AB 兜底升级分支
        env.dynamics.vel[:] = 76.1 / 3.6
        ctrl.get_action_cyclic_braking(env)      # 施加沿：进 braking + 启动窗
        assert ctrl._cyclic_braking
        assert ctrl._ed_ramp_steps_left > 0
        act = ctrl.get_action_cyclic_braking(env)
        # 窗内 ED = 满值(错峰后) × 0.7
        full = 1.0 - ctrl._ed_stagger(0)
        assert act[0, 0] == pytest.approx(full * 0.7, rel=1e-6)
        # 窗到期（0.5s = 5 步后）恢复满值
        for _ in range(6):
            act = ctrl.get_action_cyclic_braking(env)
        assert ctrl._ed_ramp_steps_left == 0
        assert act[0, 0] == pytest.approx(full, rel=1e-6)
        # AB 升级档不因 ramp 改变（ramp 只降 ED，不改 AB 源强度）
        np.testing.assert_allclose(act[:, 1], -0.75)
    finally:
        env.close()


def test_ed_upgrade_ramp_default_off_zero_regression():
    # 【Z 组】默认 0.0/1.0 = 关：升级全程 ED 逐位等于满值（旧行为）。
    env, ctrl = _setup(cyclic_notch_50=True, cyclic_brake_trigger_kmh=65.0,
                       cyclic_ab_upgrade_kmh=76.0)
    try:
        ctrl._ed_ab_price = lambda e: 0.5
        env.dynamics.vel[:] = 76.1 / 3.6
        full = 1.0 - ctrl._ed_stagger(0)
        for _ in range(8):
            act = ctrl.get_action_cyclic_braking(env)
            assert act[0, 0] == pytest.approx(full, rel=1e-6)
        assert ctrl._ed_ramp_steps_left == 0   # 窗永不启动
    finally:
        env.close()


def test_ed_upgrade_ramp_rearms_each_apply_edge():
    # 【Z 组】每次 release→braking 施加沿都重启动窗（高速段门不退出也覆盖每个
    # 施加波 —— Y2 判读定案的机理缺陷修复点）。
    env, ctrl = _setup(cyclic_notch_50=True, cyclic_brake_trigger_kmh=65.0,
                       cyclic_release_kmh=45.0,
                       cyclic_ab_upgrade_kmh=76.0,
                       ed_upgrade_ramp_s=0.5, ed_upgrade_ramp_scale=0.7)
    try:
        ctrl._ed_ab_price = lambda e: 0.5
        env.dynamics.vel[:] = 76.1 / 3.6
        ctrl.get_action_cyclic_braking(env)          # 第 1 次施加沿 → 窗启动
        assert ctrl._ed_ramp_steps_left > 0
        # 缓解（v<=45 退出 braking）→ 窗耗尽
        env.dynamics.vel[:] = 44.0 / 3.6
        for _ in range(8):
            ctrl.get_action_cyclic_braking(env)
        assert not ctrl._cyclic_braking
        assert ctrl._ed_ramp_steps_left == 0
        # 第 2 次施加沿（门仍 76 未退出过没关系 —— 沿来自 braking 重触发）
        env.dynamics.vel[:] = 76.1 / 3.6
        ctrl.get_action_cyclic_braking(env)
        assert ctrl._cyclic_braking
        assert ctrl._ed_ramp_steps_left > 0          # 窗重启
    finally:
        env.close()


def test_ed_upgrade_ramp_invalid_params_raise():
    with pytest.raises(ValueError):
        _setup(ed_upgrade_ramp_s=-1.0)
    with pytest.raises(ValueError):
        _setup(ed_upgrade_ramp_scale=1.5)
    # fleet 透传（默认关零回归 + 显式值生效）
    fleet = TrainFleetEnv({'num_trains': 1, 'consist_preset': '10kt_1plus1',
                           'decompose': 'loco_ed_ab'})
    try:
        ctrl = fleet.multi_loco_controllers[0]
        assert ctrl.ed_upgrade_ramp_s == 0.0
        assert ctrl.ed_upgrade_ramp_scale == 1.0
    finally:
        fleet.close()
    fleet2 = TrainFleetEnv({'num_trains': 1, 'consist_preset': '10kt_1plus1',
                            'decompose': 'loco_ed_ab',
                            'ed_upgrade_ramp_s': 7.5, 'ed_upgrade_ramp_scale': 0.4})
    try:
        ctrl2 = fleet2.multi_loco_controllers[0]
        assert ctrl2.ed_upgrade_ramp_s == 7.5
        assert ctrl2.ed_upgrade_ramp_scale == 0.4
    finally:
        fleet2.close()


def test_cyclic_ab_upgrade_notch_wired_through_fleet():
    # fleet env_cfg → MultiLocoController 透传；默认 'service' 零回归
    base = {'num_trains': 1, 'consist_preset': '10kt_1plus1',
            'decompose': 'loco_ed_ab'}
    fleet = TrainFleetEnv(dict(base))
    try:
        assert fleet.cyclic_ab_upgrade_notch == 'service'
        assert fleet.multi_loco_controllers[0].cyclic_ab_upgrade_notch == 'service'
    finally:
        fleet.close()

    fleet2 = TrainFleetEnv({**base, 'cyclic_notch_50': True,
                            'cyclic_brake_trigger_kmh': 65.0,
                            'cyclic_ab_upgrade_kmh': 76.0,
                            'cyclic_ab_upgrade_notch': 'min'})
    try:
        ctrl = fleet2.multi_loco_controllers[0]
        assert ctrl.cyclic_ab_upgrade_notch == 'min'
    finally:
        fleet2.close()


def test_cyclic_ab_upgrade_wired_through_fleet():
    # fleet env_cfg → MultiLocoController 透传；默认 None 零回归
    base = {'num_trains': 1, 'consist_preset': '10kt_1plus1',
            'decompose': 'loco_ed_ab'}
    fleet = TrainFleetEnv(dict(base))
    try:
        assert fleet.cyclic_ab_upgrade_kmh is None
        assert fleet.multi_loco_controllers[0].cyclic_ab_upgrade_kmh is None
    finally:
        fleet.close()

    fleet2 = TrainFleetEnv({**base, 'cyclic_notch_50': True,
                            'cyclic_brake_trigger_kmh': 65.0,
                            'cyclic_ab_upgrade_kmh': 76.0})
    try:
        ctrl = fleet2.multi_loco_controllers[0]
        assert ctrl.cyclic_ab_upgrade_kmh == 76.0
        assert ctrl.cyclic_notch_50 is True
    finally:
        fleet2.close()


def test_eot_wired_through_fleet():
    # 【R 组】fleet env_cfg → 单列 TrainFormationEnv.eot 透传；默认 False 零回归
    base = {'num_trains': 1, 'consist_preset': '10kt_1plus1',
            'decompose': 'loco_ed_ab'}
    fleet = TrainFleetEnv(dict(base))
    try:
        assert fleet.eot is False
        assert fleet.trains[0].eot is False
    finally:
        fleet.close()

    fleet2 = TrainFleetEnv({**base, 'eot': True})
    try:
        assert fleet2.eot is True
        assert fleet2.trains[0].eot is True   # 缓解时尾部同为缓解波源（双向波）
    finally:
        fleet2.close()


def test_mid_source_delay_wired_through_fleet():
    # 【AD 组】fleet env_cfg → 单列 TrainFormationEnv → TrainDynamics
    # mid_source_delay_s 透传；缺省 0.0 = 同步多源零回归
    base = {'num_trains': 1, 'consist_preset': '10kt_1plus1',
            'decompose': 'loco_ed_ab'}
    fleet = TrainFleetEnv(dict(base))
    try:
        assert fleet.mid_source_delay_s == 0.0
        assert fleet.trains[0].dynamics.mid_source_delay_s == 0.0
    finally:
        fleet.close()

    fleet2 = TrainFleetEnv({**base, 'mid_source_delay_s': 3.5})
    try:
        assert fleet2.mid_source_delay_s == 3.5
        assert fleet2.trains[0].dynamics.mid_source_delay_s == 3.5
    finally:
        fleet2.close()


def test_veto_margin_wired_through_fleet():
    # 【V 组】fleet env_cfg → 单列 TrainFormationEnv → SafetyLayer veto 三参数透传；
    # 缺省 None = 安全层默认（0.9，零回归）
    base = {'num_trains': 1, 'consist_preset': '10kt_1plus1',
            'decompose': 'loco_ed_ab'}
    fleet = TrainFleetEnv(dict(base))
    try:
        sl = fleet.trains[0].safety
        assert sl._coupler_veto_margin == 0.9      # 安全层默认
        assert sl._coupler_veto_ratio == 0.6
        assert fleet.veto_cfg == {}                # 缺省不注入
    finally:
        fleet.close()

    fleet2 = TrainFleetEnv({**base, 'coupler_veto_margin': 0.75,
                            'coupler_veto_ratio': 0.5,
                            'coupler_veto_lag_s': 60.0})
    try:
        sl = fleet2.trains[0].safety
        assert sl._coupler_veto_margin == 0.75
        assert sl._coupler_veto_ratio == 0.5
        assert sl._coupler_veto_lag_s == 60.0
    finally:
        fleet2.close()
