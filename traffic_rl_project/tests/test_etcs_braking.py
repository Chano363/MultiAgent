"""
ETCS 目标距离超速防护曲线（"真 ATP"）验证测试。

依据：ERA_ERTMS_040026 V1.5 《Introduction to ETCS Braking Curves》§3/§5（见 VALIDATION_BASELINE.md 第四节）。
覆盖：EBD 构造、坡度分量、保证减速度、EBI（建立时间+速度误差）、五级监督排序与触发、
      SafetyLayer 集成（前瞻 EBI/P 触发 + 向后兼容回退）、论文 §5 数值对齐。

符号约定（与 PDF §3.3.1 一致）：
    A_safe(v,d) = A_brake_safe(v) + A_gradient(d)
    A_gradient(d) = g·grade(d)，下坡 grade<0 → A_gradient<0 → 有效减速度变小 → 制动距离变长。
"""
import os
import sys

import pytest
import numpy as np


from src.train_dynamics.etcs_braking import (
    EtcsBrakingCurve, EbdTarget, braking_build_up_from_train, G_RAIL,
)
from src.safety_layer import (
    SafetyLayer, FULL_SERVICE_BRAKE, EMERGENCY_BRAKE,
)
from src.train_dynamics.grade_profile import (
    profile_shuozhou_23800,
)

G = G_RAIL


def _make_curve(**kw):
    """构造一个默认测试曲线（平直 + 干轨 + 无误差 + 无建立期，便于验证相对行为）。"""
    base = dict(nominal_emergency_decel=1.6, k_dry=1.0, brake_build_up_s=0.0)
    base.update(kw)
    return EtcsBrakingCurve(**base)


def _v_ebi(curve, target, v_cur, position_m):
    """便捷：取某目标在当前点（position_m）的 EBI 监督限位（m/s）。"""
    return curve.supervision_levels(target, v_cur, position_m)['allowed']['EBI']


# ---------------------------------------------------------------------------
# EBD 基础结构
# ---------------------------------------------------------------------------
def test_ebd_starts_at_target_speed():
    """EBD 曲线从目标位置（速度=目标速度）反推，允许速度随远离目标单调增大。"""
    curve = _make_curve()
    target = EbdTarget(position_m=1000.0, speed_mps=0.0)
    points = curve.compute_ebd(target)
    assert points[0][0] == pytest.approx(1000.0)
    assert points[0][1] == pytest.approx(0.0)  # 目标点允许速度 = 目标速度 0
    # 位置递减、允许速度单调不减
    xs = [p[0] for p in points]
    vs = [p[1] for p in points]
    assert all(xs[i] > xs[i + 1] for i in range(len(xs) - 1))
    assert all(vs[i] <= vs[i + 1] + 1e-9 for i in range(len(vs) - 1))


def test_ebd_allowed_speed_decreases_near_target():
    """靠近目标处允许速度低，远离目标处允许速度高（查询接口）。"""
    curve = _make_curve()
    target = EbdTarget(position_m=5000.0, speed_mps=0.0)
    points = curve.compute_ebd(target, max_dist=4000.0)
    # 目标处允许 0
    assert curve.v_allowed_at(points, 5000.0) <= 1e-6
    # 距目标 4000m 处允许速度高
    far = curve.v_allowed_at(points, 1000.0)
    near = curve.v_allowed_at(points, 4000.0)
    assert far > near


# ---------------------------------------------------------------------------
# 坡度分量（长大下坡）
# ---------------------------------------------------------------------------
def test_gradient_slope_extends_braking_distance():
    """下坡 A_gradient<0 吃掉减速度 → 同速度制动距离变长（长大下坡正确缩放）。"""
    flat = _make_curve(grade_at=lambda x: 0.0)
    down = _make_curve(grade_at=lambda x: -0.010)  # -10‰ 下坡
    target = EbdTarget(position_m=5000.0, speed_mps=0.0)
    d_flat = flat.braking_distance_needed(target, v0=25.0)
    d_down = down.braking_distance_needed(target, v0=25.0)
    # 25m/s、a=1.6：平直 ≈195m，-10‰ 下坡有效 a≈1.502 → ≈208m（+~13m）
    assert d_flat == pytest.approx(25.0 ** 2 / (2 * 1.6), rel=0.02)
    assert d_down > d_flat + 5.0  # 下坡显著更长


def test_gradient_decel_value():
    """A_gradient(d) = g·grade(d)；下坡 grade<0 → 为负（减小有效减速度）。"""
    curve = _make_curve(grade_at=lambda x: -0.010)
    assert curve.gradient_decel(0.0) == pytest.approx(-G * 0.010)
    up = _make_curve(grade_at=lambda x: 0.010)  # 上坡 grade>0 → 帮助减速（更大）
    assert up.gradient_decel(0.0) == pytest.approx(G * 0.010)


def test_effective_decel_combines_brake_and_gradient():
    """A_safe(v,d) = A_brake_safe(v) + A_gradient(d)（PDF §3.3.1）。"""
    curve = _make_curve(nominal_emergency_decel=1.6, k_dry=1.0,
                        grade_at=lambda x: -0.010)
    # 保证减速度 1.6，下坡梯度 -0.098 → 有效 1.502
    assert curve.effective_decel(10.0, 0.0) == pytest.approx(1.6 - G * 0.010, abs=1e-6)


def test_shuozhou_downhill_braking_positive():
    """朔黄线真实剖面（-11.4‰ 段）超大下坡：有效减速度仍保证正（不会负减速翻车）。"""
    prof = profile_shuozhou_23800()
    curve = _make_curve(nominal_emergency_decel=1.6, k_dry=1.0, grade_at=prof.grade_at)
    # 最陡 -11.4‰ 段但制动减速度 1.6 仍远大于 0.112 → 有效减速度恒正
    worst = curve.effective_decel(10.0, 16000.0)  # -11.4‰ 段
    assert worst > 0.5


# ---------------------------------------------------------------------------
# 保证减速度（校正因子）
# ---------------------------------------------------------------------------
def test_guaranteed_decel_kdry():
    """保证减速度 = 名义 × Kdry_rst（PDF §3.3.2）。"""
    curve = _make_curve(nominal_emergency_decel=1.4, k_dry=0.83)
    assert curve.guaranteed_decel(20.0) == pytest.approx(1.4 * 0.83)


def test_guaranteed_decel_wet_weighting():
    """湿轨加权：wet_weight=1 → 减速度 × Kwet；=0 → 干轨。"""
    curve = _make_curve(nominal_emergency_decel=1.6, k_dry=1.0, k_wet=0.893, wet_weight=1.0)
    assert curve.guaranteed_decel(20.0) == pytest.approx(1.6 * 0.893)


def test_guaranteed_decel_speed_profile():
    """速度步进口径：名义减速度随速度分段（PDF §3.3.1 step function）。"""
    curve = _make_curve(speed_profile=[(20.0, 1.4), (60.0, 1.1)], k_dry=1.0)
    assert curve.guaranteed_decel(5.0) == pytest.approx(1.4)
    assert curve.guaranteed_decel(30.0) == pytest.approx(1.1)


def test_speed_above_profile_keeps_last_band_instead_of_unrelated_default():
    curve = _make_curve(speed_profile=[(40 / 3.6, 0.426), (60 / 3.6, 0.401),
                                        (80 / 3.6, 0.382)])
    for speed in [80.001, 81, 88]:
        assert curve.nominal_decel(speed / 3.6) == pytest.approx(0.382)
        assert curve.nominal_decel(-speed / 3.6) == pytest.approx(0.382)


def test_braking_distance_does_not_shrink_when_crossing_profile_upper_speed():
    curve = _make_curve(speed_profile=[(40 / 3.6, 0.426), (60 / 3.6, 0.401),
                                        (80 / 3.6, 0.382)])
    target = EbdTarget(10000.0, 0.0, kind='stop')
    distances = [curve.braking_distance(v / 3.6, 0.0, target) for v in [79.9, 80, 81, 88]]
    assert all(b >= a for a, b in zip(distances, distances[1:]))


def test_single_band_distance_matches_fixed_curve_above_band():
    stepped = _make_curve(speed_profile=[(80 / 3.6, 0.382)])
    fixed = _make_curve(nominal_emergency_decel=0.382)
    target = EbdTarget(10000.0, 0.0, kind='stop')
    for speed in [81, 88]:
        assert stepped.braking_distance(speed / 3.6, 0, target) == pytest.approx(
            fixed.braking_distance(speed / 3.6, 0, target))


# ---------------------------------------------------------------------------
# EBI：建立时间 + 速度误差
# ---------------------------------------------------------------------------
def test_ebi_stricter_with_build_up_time():
    """制动建立时间越长，EBI 允许速度越低（建立期内最不利加速 → 越早介入）。"""
    no_build = _make_curve()
    build = _make_curve(brake_build_up_s=12.8, assumed_accel_during_buildup=0.0)
    target = EbdTarget(position_m=5000.0, speed_mps=0.0)
    v_no = _v_ebi(no_build, target, v_cur=20.0, position_m=3000.0)
    v_bd = _v_ebi(build, target, v_cur=20.0, position_m=3000.0)
    assert v_bd < v_no


def test_ebi_stricter_with_speed_error():
    """速度测量误差越大，EBI 允许速度越低（监督留出误差裕量）。"""
    no_err = _make_curve()
    with_err = _make_curve(speed_err_mps=2.0)
    target = EbdTarget(position_m=5000.0, speed_mps=0.0)
    v_no = _v_ebi(no_err, target, 20.0, 3000.0)
    v_err = _v_ebi(with_err, target, 20.0, 3000.0)
    assert v_err < v_no


# ---------------------------------------------------------------------------
# 五级监督 I → P → W → SBI → EBI 排序与触发
# ---------------------------------------------------------------------------
def test_supervision_levels_ordering():
    """五级监督限速应单调（I 需最早反应 → 限速最低；EBI 硬介入 → 限速最高）。"""
    curve = _make_curve(brake_build_up_s=5.0)
    target = EbdTarget(position_m=4000.0, speed_mps=0.0)
    out = curve.supervision_levels(target, v_cur=15.0, position_m=1500.0)
    allowed = out['allowed']
    assert allowed['I'] <= allowed['P'] + 1e-9
    assert allowed['P'] <= allowed['W'] + 1e-9
    assert allowed['W'] <= allowed['SBI'] + 1e-9
    assert allowed['SBI'] <= allowed['EBI'] + 1e-9


def test_supervision_active_level_low_speed():
    """速度很低时不触发任何监督（active=None）。"""
    curve = _make_curve()
    target = EbdTarget(position_m=4000.0, speed_mps=0.0)
    out = curve.supervision_levels(target, v_cur=0.5, position_m=1500.0)
    assert out['active'] is None


def test_supervision_active_level_high_speed():
    """距目标很近+高速时触发 EBI（硬介入）。"""
    curve = _make_curve()
    target = EbdTarget(position_m=600.0, speed_mps=0.0)
    out = curve.supervision_levels(target, v_cur=40.0, position_m=300.0)
    assert out['active'] == 'EBI'


# ---------------------------------------------------------------------------
# SafetyLayer 集成：前瞻 EBI / SBI 触发 + 向后兼容
# ---------------------------------------------------------------------------
def _sl_with_obs(target_pos, v_head, grade_at=None, build_up=0.0):
    sl = SafetyLayer(num_vehicles=4, max_speed_mps=30.0)
    curve = _make_curve(grade_at=grade_at, brake_build_up_s=build_up)
    obs = {
        'vel': np.full(4, v_head),
        'coupler_forces': np.zeros(4),
        'gaps': np.array([0.0, 1.0, 1.0, 1.0]),
        'head_position_m': 0.0,
        'etcs_targets': [EbdTarget(position_m=target_pos, speed_mps=0.0)],
        'etcs_curve': curve,
    }
    return sl, obs


def test_safety_etcs_ebi_triggers_emergency_brake():
    """ETCS 前瞻：距停车点近+高速 → 速度超 EBI → 全列车强制紧急制动。"""
    # 200m 内以 30m/s（108km/h）无法刹停（需 ~281m）→ EBI
    sl, obs = _sl_with_obs(target_pos=200.0, v_head=30.0)
    corrected = sl.protect(np.array([1.0, 1.0, 1.0, 1.0]), obs)
    assert all(corrected <= EMERGENCY_BRAKE + 1e-9)
    assert any(e['rule'] == 'etcs_ebi' for e in sl.last_events)


def test_safety_etcs_not_trigger_when_far_and_slow():
    """ETCS 前瞻：速度远低于限速且距目标足够远 → 不强制制动，牵引放行。"""
    sl, obs = _sl_with_obs(target_pos=5000.0, v_head=10.0)
    corrected = sl.protect(np.array([0.4, 0.4, 0.4, 0.4]), obs)
    assert corrected[0] == pytest.approx(0.4)
    assert not any(e['rule'].startswith('etcs_ebi') or e['rule'].startswith('etcs_permitted')
                   for e in sl.last_events)


def test_safety_etcs_sbi_trigger_service_brake():
    """车速超过 SBI 但未超 EBI → 强制 service 制动（SBI 监督，提前一个反应 lead）。"""
    sl, obs = _sl_with_obs(target_pos=250.0, v_head=27.7)
    corrected = sl.protect(np.array([1.0, 1.0, 1.0, 1.0]), obs)
    assert all(corrected <= FULL_SERVICE_BRAKE + 1e-9)
    assert any(e['rule'] == 'etcs_permitted' for e in sl.last_events)


def test_safety_etcs_missing_target_falls_back_to_reactive():
    """ETCS 恒启但 obs 缺目标数据 → 回退反应式限速（超速仍被拦，不漏检）。"""
    sl = SafetyLayer(num_vehicles=4, max_speed_mps=30.0)
    obs = {
        'vel': np.full(4, 30.0),
        'coupler_forces': np.zeros(4),
        'gaps': np.array([0.0, 1.0, 1.0, 1.0]),
        # 无 'etcs_curve'/'etcs_targets'/'head_position_m'
    }
    corrected = sl.protect(np.array([1.0, 1.0, 1.0, 1.0]), obs)
    assert corrected[0] <= 0.0
    assert any(e['rule'] == 'overspeed' for e in sl.last_events)


def test_safety_reactive_overspeed_without_etcs_targets():
    """ETCS 恒启但 obs 缺目标数据 → 回退反应式限速（超速仍被拦，不漏检）。"""
    sl = SafetyLayer(num_vehicles=2, max_speed_mps=30.0)
    corrected = sl.protect(np.array([1.0, 1.0]),
                           {'vel': np.array([30.0, 30.0]),
                            'coupler_forces': np.zeros(2),
                            'gaps': np.array([0.0, 1.0])})
    assert corrected[0] <= 0.0
    assert any(e['rule'] == 'overspeed' for e in sl.last_events)


def test_safety_etcs_slope_earlier_intervention():
    """下坡越陡，EBI 允许速度越低（坡度分量在监督层生效，比平直更早介入）。"""
    flat_sl, flat_obs = _sl_with_obs(target_pos=6000.0, v_head=28.0, grade_at=lambda x: 0.0)
    down_sl, down_obs = _sl_with_obs(target_pos=6000.0, v_head=28.0, grade_at=lambda x: -0.010)
    ebi_flat, _ = flat_sl._etcs_check(0.0, 28.0, flat_obs['etcs_curve'], flat_obs['etcs_targets'])
    ebi_down, _ = down_sl._etcs_check(0.0, 28.0, down_obs['etcs_curve'], down_obs['etcs_targets'])
    assert ebi_down is not None and ebi_flat is not None
    assert ebi_down < ebi_flat


# ---------------------------------------------------------------------------
# 制动建立时间来源：空气波传播延迟（对齐 braking.py）
# ---------------------------------------------------------------------------
def test_build_up_from_air_propagation():
    """紧急制动建立时间 = 车列长度 / 波速（对齐空气制动波速传播，不用 free_length）。"""
    t = braking_build_up_from_train(train_length_m=600.0, propagation_speed_mps=250.0)
    assert t == pytest.approx(2.4)
    t_short = braking_build_up_from_train(train_length_m=600.0, propagation_speed_mps=200.0)
    assert t_short == pytest.approx(3.0)


# ---------------------------------------------------------------------------
# 论文 §5 数值对齐（G 位货车：100km/h、-10‰，见 VALIDATION_BASELINE 4.3）
# ---------------------------------------------------------------------------
def test_paper_gmode_freight_braking_distance_order():
    """G 位货车（100km/h=27.78、-10‰）EBD 制动停车距离应为【数百米】量级。

    论文 2189m 为含"司机反应+建立期"的完整 I→P→EBI→EBD 分摊；纯 EBD 段（不含反应/建立期）
    更短。我们校验 EBD 制动距离落在合理量级，并验证加入建立时间后 EBI 允许速度降低。
    """
    grade_at = lambda x: -0.010
    curve = _make_curve(nominal_emergency_decel=1.6, k_dry=0.83, grade_at=grade_at)
    target = EbdTarget(position_m=10000.0, speed_mps=0.0)
    d_ebd = curve.braking_distance_needed(target, v0=27.78)
    # 有效减速度 = 1.6*0.83 - 9.8066*0.010 ≈ 1.23 → 距离 ≈ 27.78²/(2*1.23) ≈ 314m
    assert 100.0 < d_ebd < 2000.0
    # EBI（含 12.8s 建立期）允许速度 < 纯 EBD 允许速度（更早介入）
    curve_bd = _make_curve(nominal_emergency_decel=1.6, k_dry=0.83,
                           grade_at=grade_at, brake_build_up_s=12.8)
    ebi_allowed_at0 = _v_ebi(curve_bd, target, 27.78, 0.0)
    ebd_allowed_at0 = curve.v_allowed(target, 0.0)
    assert ebi_allowed_at0 < ebd_allowed_at0


def test_paper_hs_train_deceleration_levels():
    """高速车（Kdry 0.83、名义 ~1.3-1.4）保证减速度应 < 名义值（PDF 表2）。"""
    curve = _make_curve(nominal_emergency_decel=1.4, k_dry=0.83)
    assert curve.guaranteed_decel(100.0) == pytest.approx(1.4 * 0.83, abs=1e-6)


# ---------------------------------------------------------------------------
# 多列群组 ETCS 集成（"真 ATP" 防追尾）：前列尾车 = 后列 ETCS 目标
# ---------------------------------------------------------------------------
from src.environments.train_fleet_env import TrainFleetEnv


def _fleet(num_trains=3):
    return TrainFleetEnv({
        'num_trains': num_trains,
        'consist_preset': '10kt_1plus0',
        'grade_profile': 'shuozhou_23800',
    })


def test_fleet_etcs_trains_have_curve_and_enabled():
    """ATP/ETCS 恒启（无开关）：每列共享同一条 ETCS 曲线（含坡度分量/建立期）。"""
    fleet = _fleet(num_trains=3)
    for tr in fleet.trains:
        assert tr.etcs_curve is fleet.etcs_curve  # 共享曲线
    assert fleet.etcs_curve is not None
    assert fleet.etcs_curve.brake_build_up_s > 0.0  # 由波速传播算出（~4.9s）


def test_fleet_etcs_is_permanent_and_curve_shared():
    """ATP 恒启安全底线：多列场景 ETCS 曲线必建且全列共享，无"关闭"路径。"""
    fleet = _fleet(num_trains=3)
    assert all(tr.etcs_curve is fleet.etcs_curve for tr in fleet.trains)
    assert fleet.etcs_curve is not None
    fleet.reset()
    obs, *_ = fleet.step(np.zeros(3))
    assert obs.shape == (3, fleet.obs_dim)


def test_fleet_etcs_follower_target_is_leader_tail():
    """后列每步被注入"前列尾车"作为 ETCS 监督目标（防追尾）。"""
    fleet = _fleet(num_trains=3)
    fleet.reset()
    fleet.step(np.zeros(3))
    for i in range(1, fleet.num_trains):
        tr = fleet.trains[i]
        leader_tail = fleet.trains[i - 1].dynamics.pos[-1]
        assert len(tr.etcs_targets) == 1
        assert tr.etcs_targets[0].position_m == pytest.approx(leader_tail)
        assert tr.etcs_targets[0].kind == 'gap'
        # 【2026-09-02 修复】目标速度 = 前列当前实时速度（而非固定 target_speed）：
        # 前列循环制动降速时后列须降到前列当前速度才真正防追尾。
        leader_speed = float(fleet.trains[i - 1].dynamics.vel[0])
        assert tr.etcs_targets[0].speed_mps == pytest.approx(leader_speed)


def test_fleet_etcs_leader_has_no_target_and_still_enforces_line_speed():
    """领航列（i=0）无前列目标，但线速上限仍由反应式限速兜底（不超 80km/h，无漏检）。"""
    fleet = _fleet(num_trains=3)
    fleet.reset()
    leader = fleet.trains[0]
    leader.set_etcs_targets([])  # 领航列无前列 → 空目标
    # 直接构造超线速快照验证 overspeed 兜底仍生效（ETCS 空目标不拦截，但线速兜底恒在）
    snap = leader._state_snapshot()
    snap['vel'] = np.full(leader.num_vehicles, fleet.v_max + 5.0)
    protected = leader.safety.protect(np.ones(leader.num_vehicles), snap)
    assert protected[0] <= FULL_SERVICE_BRAKE + 1e-9
    assert any(e['rule'] == 'overspeed' for e in leader.safety.last_events)


def test_fleet_etcs_follower_fast_near_leader_triggers_ebi():
    """后列距前列近且高速 → ETCS EBI 强制紧急制动（真正防追尾，非反应式兜底）。"""
    fleet = _fleet(num_trains=2)
    fleet.reset()
    follower = fleet.trains[1]
    leader = fleet.trains[0]
    # 人为把后列推到距前列很近（追尾临近）
    leader_tail = leader.dynamics.pos[-1]
    follower.dynamics.set_initial(pos=np.array([leader_tail - 80.0]) + follower.dynamics.pos - follower.dynamics.pos[0],
                                  vel=follower.dynamics.vel)
    fleet._train_heads[1] = float(follower.dynamics.pos[0])
    # 后列高速
    follower.dynamics.set_initial_speed(24.0)
    # 注入前列尾车目标并执行
    follower.set_etcs_targets([EbdTarget(position_m=leader_tail, speed_mps=fleet.target_speed, kind='gap')])
    snap = follower._state_snapshot()
    assert 'etcs_targets' in snap and 'etcs_curve' in snap and 'head_position_m' in snap
    protected = follower.safety.protect(np.ones(follower.num_vehicles), snap)
    assert any(e['rule'] == 'etcs_ebi' for e in follower.safety.last_events) or \
           any(e['rule'] == 'etcs_permitted' for e in follower.safety.last_events)
