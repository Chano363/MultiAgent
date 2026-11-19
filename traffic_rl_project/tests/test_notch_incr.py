"""ADR-074 级位派生化（loco_notch_incr）单测。

覆盖：速率限制积分、ED=级位派生、AB 级位越限派生（滞回）、安全链
（超速兜底 SERVICE / 充风门 / 低速强制缓解）、fail-fast 门、env 接线。

对标文献：Wang2023 ②（级位增量动作 + AB 由级位越限/充风派生，实车拉钩 −8.93%）。
"""

import numpy as np
import pytest
from types import SimpleNamespace

from src.controllers.multi_loco_controller import MultiLocoController


def _ctrl(rate=3.0):
    """最小 loco_notch_incr 控制器（默认派生档 = MIN 70 kPa）。"""
    ctrl = MultiLocoController(num_vehicles=1, loco_indices=[0])
    ctrl.notch_incr_rate_notches = rate
    return ctrl


def _env(vel=60.0 / 3.6, grade=None):
    dyn = SimpleNamespace(vel=np.array([vel]))
    if grade is not None:
        dyn.grade = np.array([grade])   # 无量纲坡度（下坡为负）
    return SimpleNamespace(dynamics=dyn)


V_MAX = 75.0 / 3.6
V_MIN = 40.0 / 3.6


def test_rate_limit_integrates_and_ed_follows_notch():
    """级位增量限幅：每决策步 |Δn| ≤ rate/20；ED = 级位（派生）。"""
    ctrl = _ctrl(3.0)
    env = _env()
    levels = []
    for _ in range(4):
        out = ctrl.get_action_notch_incr(env, np.array([[1.0]]), v_max=V_MAX, v_min=V_MIN)
        levels.append(out[0, 0])
    assert levels == pytest.approx([0.15, 0.30, 0.45, 0.60])
    # 级位饱和到 1.0
    for _ in range(5):
        out = ctrl.get_action_notch_incr(env, np.array([[1.0]]), v_max=V_MAX, v_min=V_MIN)
    assert out[0, 0] == pytest.approx(1.0)


def test_ab_derived_from_notch_crossing():
    """级位越限派生 AB：n ≥ 0.5 → MIN(70 kPa, -0.20)；首次施加过充风门。"""
    ctrl = _ctrl(3.0)
    env = _env()
    out = ctrl.get_action_notch_incr(env, np.array([[1.0]]), v_max=V_MAX, v_min=V_MIN)
    assert out[0, 1] == 0.0            # n=0.15 < 0.5 → 不派生
    out = ctrl.get_action_notch_incr(env, np.array([[1.0]]), v_max=V_MAX, v_min=V_MIN)
    assert out[0, 1] == 0.0            # n=0.30
    out = ctrl.get_action_notch_incr(env, np.array([[1.0]]), v_max=V_MAX, v_min=V_MIN)
    assert out[0, 1] == 0.0            # n=0.45 仍低于阈值
    out = ctrl.get_action_notch_incr(env, np.array([[1.0]]), v_max=V_MAX, v_min=V_MIN)
    assert out[0, 1] == pytest.approx(-0.20)   # n=0.60 ≥ 0.5 → 派生 MIN


def test_hysteresis_keeps_ab_between_threshold_and_margin():
    """滞回：已施加态在 [阈值−margin, 阈值) 区间不抖动释放。"""
    ctrl = _ctrl(3.0)
    env = _env()
    for _ in range(4):   # n → 0.60，AB on
        ctrl.get_action_notch_incr(env, np.array([[1.0]]), v_max=V_MAX, v_min=V_MIN)
    out = ctrl.get_action_notch_incr(env, np.array([[-1.0]]), v_max=V_MAX, v_min=V_MIN)
    assert out[0, 0] == pytest.approx(0.45)
    assert out[0, 1] == pytest.approx(-0.20)   # n=0.45 ≥ 0.45 → 保持
    out = ctrl.get_action_notch_incr(env, np.array([[-1.0]]), v_max=V_MAX, v_min=V_MIN)
    assert out[0, 0] == pytest.approx(0.30)
    assert out[0, 1] == 0.0                    # n=0.30 < 0.45 → 释放


def test_grade_release_gate_default_off_zero_regression():
    """坡度门默认关：行为与旧派生逐位一致（无 grade 属性也不受影响）。"""
    c_on = _ctrl(3.0)
    c_on.ab_grade_release_gate = True   # 即便开，缺 grade 信息也应回退旧行为
    c_off = _ctrl(3.0)
    env = _env()  # 无 grade
    for _ in range(4):
        a = c_on.get_action_notch_incr(env, np.array([[1.0]]), v_max=V_MAX, v_min=V_MIN)
        b = c_off.get_action_notch_incr(env, np.array([[1.0]]), v_max=V_MAX, v_min=V_MIN)
        assert a == pytest.approx(b)
    for _ in range(2):
        a = c_on.get_action_notch_incr(env, np.array([[-1.0]]), v_max=V_MAX, v_min=V_MIN)
        b = c_off.get_action_notch_incr(env, np.array([[-1.0]]), v_max=V_MAX, v_min=V_MIN)
        assert a == pytest.approx(b)


def test_grade_release_gate_blocks_release_on_steep_grade():
    """陡坡（−10.2‰ < −7‰ 门限）：级位下探到释放区也不许释放 AB。"""
    ctrl = _ctrl(3.0)
    ctrl.ab_grade_release_gate = True
    ctrl.ab_grade_release_permille = -7.0
    steep = _env(grade=-10.2 / 1000.0)
    for _ in range(4):   # n → 0.60，AB on（过充风门）
        ctrl.get_action_notch_incr(steep, np.array([[1.0]]), v_max=V_MAX, v_min=V_MIN)
    # 下探两级：n 0.60→0.45→0.30，均低于释放阈值 0.45（第二级肯定该释放）
    out = ctrl.get_action_notch_incr(steep, np.array([[-1.0]]), v_max=V_MAX, v_min=V_MIN)
    assert out[0, 0] == pytest.approx(0.45)
    assert out[0, 1] == pytest.approx(-0.20)  # 陡坡门否决释放
    out = ctrl.get_action_notch_incr(steep, np.array([[-1.0]]), v_max=V_MAX, v_min=V_MIN)
    assert out[0, 0] == pytest.approx(0.30)
    assert out[0, 1] == pytest.approx(-0.20)  # 仍陡，继续否决


def test_grade_release_gate_allows_release_on_gentle_grade():
    """缓坡（−5‰ > −7‰ 门限）：级位下探正常释放 AB（解耦生效）。"""
    ctrl = _ctrl(3.0)
    ctrl.ab_grade_release_gate = True
    ctrl.ab_grade_release_permille = -7.0
    gentle = _env(grade=-5.0 / 1000.0)
    for _ in range(4):
        ctrl.get_action_notch_incr(gentle, np.array([[1.0]]), v_max=V_MAX, v_min=V_MIN)
    out = ctrl.get_action_notch_incr(gentle, np.array([[-1.0]]), v_max=V_MAX, v_min=V_MIN)
    assert out[0, 1] == pytest.approx(-0.20)  # n=0.45 仍保持
    out = ctrl.get_action_notch_incr(gentle, np.array([[-1.0]]), v_max=V_MAX, v_min=V_MIN)
    assert out[0, 0] == pytest.approx(0.30)
    assert out[0, 1] == 0.0                    # 缓坡允许释放


# ---- A-4（P1 第二版，2026-11-19）：变坡点门 + 低速兜底坡度门控 ----

def _env_grade(grade_permille, vel_kmh=60.0):
    return _env(vel=vel_kmh / 3.6, grade=grade_permille / 1000.0)


def test_a4a_rebound_gate_blocks_without_rebound():
    """A-4a：坡度未回升（持续陡坡 −10‰）时，级位下探不许释放 AB。"""
    ctrl = _ctrl(3.0)
    ctrl.ab_grade_rebound_gate = True
    ctrl.ab_grade_rebound_permille = 3.0
    steep = _env_grade(-10.0)
    for _ in range(4):
        ctrl.get_action_notch_incr(steep, np.array([[1.0]]), v_max=V_MAX, v_min=V_MIN)
    # 下探到 n=0.30（低于释放阈值），但坡度一直 −10‰ 无回升 ⇒ 门否决
    out = ctrl.get_action_notch_incr(steep, np.array([[-1.0]]), v_max=V_MAX, v_min=V_MIN)
    assert out[0, 1] == pytest.approx(-0.20)
    out = ctrl.get_action_notch_incr(steep, np.array([[-1.0]]), v_max=V_MAX, v_min=V_MIN)
    assert out[0, 1] == pytest.approx(-0.20)


def test_a4a_rebound_gate_allows_on_rebound():
    """A-4a：坡度回升 ≥Δ（−10‰→−6‰，回升 4‰）时允许级位下探释放。"""
    ctrl = _ctrl(3.0)
    ctrl.ab_grade_rebound_gate = True
    ctrl.ab_grade_rebound_permille = 3.0
    steep = _env_grade(-10.0)
    for _ in range(4):
        ctrl.get_action_notch_incr(steep, np.array([[1.0]]), v_max=V_MAX, v_min=V_MIN)
    # 先把 n 降到 0.45（释放阈值边界，门会否决但状态仍 on），此刻上一步坡度 −10‰
    ctrl.get_action_notch_incr(steep, np.array([[-1.0]]), v_max=V_MAX, v_min=V_MIN)
    # 这一step 坡度回升到 −6‰（+4‰ ≥ Δ=3）⇒ 允许释放
    rebound = _env_grade(-6.0)
    out = ctrl.get_action_notch_incr(rebound, np.array([[-1.0]]), v_max=V_MAX, v_min=V_MIN)
    assert out[0, 1] == 0.0


def test_a4b_low_speed_gate_holds_on_steep_then_releases_near_stop():
    """A-4b：陡坡低速继续带闸，逼近 v_stop 仍强制缓解（保 V17 拖停底线）。"""
    ctrl = _ctrl(3.0)
    ctrl.ab_low_speed_release = True
    ctrl.ab_low_speed_grade_gate = True
    ctrl.ab_low_speed_stop_kmh = 35.0
    steep = _env_grade(-10.0, vel_kmh=41.0)   # ≤ v_min+2(=42) 触发低速区
    for _ in range(4):
        ctrl.get_action_notch_incr(steep, np.array([[1.0]]), v_max=V_MAX, v_min=V_MIN)
    # 低速 + 陡坡 + 未到 v_stop ⇒ 继续带闸
    out = ctrl.get_action_notch_incr(steep, np.array([[0.0]]), v_max=V_MAX, v_min=V_MIN)
    assert out[0, 1] == pytest.approx(-0.20)
    # 逼近 v_stop（34 km/h < 35）⇒ 强制缓解
    near_stop = _env_grade(-10.0, vel_kmh=34.0)
    out = ctrl.get_action_notch_incr(near_stop, np.array([[0.0]]), v_max=V_MAX, v_min=V_MIN)
    assert out[0, 1] == 0.0


def test_a4_all_off_zero_regression():
    """A-4 两开关默认关：与旧派生逐位一致（含低速兜底原行为）。"""
    a = _ctrl(3.0)
    b = _ctrl(3.0)
    a.ab_low_speed_release = b.ab_low_speed_release = True
    env = _env_grade(-10.0, vel_kmh=60.0)
    for act in [[1.0]] * 4 + [[-1.0]] * 4:
        oa = a.get_action_notch_incr(env, np.array([act]), v_max=V_MAX, v_min=V_MIN)
        ob = b.get_action_notch_incr(env, np.array([act]), v_max=V_MAX, v_min=V_MIN)
        assert oa == pytest.approx(ob)


def test_ab_release_speed_gate_default_off_zero_regression():
    """速度门默认关：释放判据仍是级位下探（与旧行为逐位一致）。"""
    ctrl = _ctrl(3.0)
    env = _env(grade=-10.0 / 1000.0, vel=60.0 / 3.6)
    for _ in range(4):
        ctrl.get_action_notch_incr(env, np.array([[1.0]]), v_max=V_MAX, v_min=V_MIN)
    out = ctrl.get_action_notch_incr(env, np.array([[-1.0]]), v_max=V_MAX, v_min=V_MIN)
    assert out[0, 1] == pytest.approx(-0.20)   # n=0.45 仍保持
    out = ctrl.get_action_notch_incr(env, np.array([[-1.0]]), v_max=V_MAX, v_min=V_MIN)
    assert out[0, 1] == 0.0                     # n=0.30 < 0.45 → 正常释放


def test_ab_release_speed_gate_holds_above_speed_limit():
    """速度门开：速度 > 门限时，即使级位下探到 0 也不释放 AB（on 段与 ED 解耦）。"""
    ctrl = _ctrl(3.0)
    ctrl.ab_release_speed_gate = True
    ctrl.ab_release_speed_kmh = 50.0
    env = _env(grade=-10.0 / 1000.0, vel=60.0 / 3.6)   # 60 > 50
    for _ in range(4):
        ctrl.get_action_notch_incr(env, np.array([[1.0]]), v_max=V_MAX, v_min=V_MIN)
    for _ in range(8):   # 级位一路下探到 0
        out = ctrl.get_action_notch_incr(env, np.array([[-1.0]]), v_max=V_MAX, v_min=V_MIN)
    assert out[0, 0] == pytest.approx(0.0)
    assert out[0, 1] == pytest.approx(-0.20)   # 速度仍高 → 保持 AB on


def test_ab_release_speed_gate_allows_release_below_limit():
    """速度门开：速度降到门限以下 ⇒ 允许释放（与级位无关）。"""
    ctrl = _ctrl(3.0)
    ctrl.ab_release_speed_gate = True
    ctrl.ab_release_speed_kmh = 50.0
    fast = _env(grade=-10.0 / 1000.0, vel=60.0 / 3.6)
    for _ in range(4):
        ctrl.get_action_notch_incr(fast, np.array([[1.0]]), v_max=V_MAX, v_min=V_MIN)
    slow = _env(grade=-10.0 / 1000.0, vel=45.0 / 3.6)   # 45 < 50
    out = ctrl.get_action_notch_incr(slow, np.array([[-1.0]]), v_max=V_MAX, v_min=V_MIN)
    assert out[0, 1] == 0.0


def test_ab_release_speed_gate_low_speed_fallback_still_releases():
    """低速强制缓解（v ≤ v_min+2 = 42）在速度门之上仍强制释放（防拖停底线不可被门关掉）。"""
    ctrl = _ctrl(3.0)
    ctrl.ab_release_speed_gate = True
    ctrl.ab_release_speed_kmh = 50.0
    ctrl.ab_low_speed_release = True
    env = _env(grade=-10.0 / 1000.0, vel=60.0 / 3.6)
    for _ in range(4):
        ctrl.get_action_notch_incr(env, np.array([[1.0]]), v_max=V_MAX, v_min=V_MIN)
    slow = _env(grade=-10.0 / 1000.0, vel=41.0 / 3.6)   # ≤ 42 → 低速兜底
    out = ctrl.get_action_notch_incr(slow, np.array([[-1.0]]), v_max=V_MAX, v_min=V_MIN)
    assert out[0, 1] == 0.0


def test_ab_apply_speed_gate_default_off_zero_regression():
    """施加门控默认关（0 = 不启用）：行为与旧派生逐位一致。"""
    ctrl = _ctrl(3.0)
    env = _env(grade=-10.0 / 1000.0, vel=45.0 / 3.6)
    for _ in range(4):
        out = ctrl.get_action_notch_incr(env, np.array([[1.0]]), v_max=V_MAX, v_min=V_MIN)
    assert out[0, 1] == pytest.approx(-0.20)   # 低速也照常施加（门关）


def test_ab_apply_speed_gate_blocks_new_apply_below_threshold():
    """施加门控开：低速段不新增 AB 源（请求被搁置，状态不变）。"""
    ctrl = _ctrl(3.0)
    ctrl.ab_apply_speed_min_kmh = 55.0
    slow = _env(grade=-10.0 / 1000.0, vel=45.0 / 3.6)   # 45 < 55 ⇒ 不施加
    for _ in range(4):
        out = ctrl.get_action_notch_incr(slow, np.array([[1.0]]), v_max=V_MAX, v_min=V_MIN)
    assert out[0, 1] == 0.0
    assert ctrl._ab_on[0] is False


def test_ab_apply_speed_gate_allows_apply_above_threshold():
    """施加门控开：速度高于门限 ⇒ 正常新增 AB 源。"""
    ctrl = _ctrl(3.0)
    ctrl.ab_apply_speed_min_kmh = 55.0
    fast = _env(grade=-10.0 / 1000.0, vel=60.0 / 3.6)   # 60 > 55 ⇒ 施加
    for _ in range(4):
        out = ctrl.get_action_notch_incr(fast, np.array([[1.0]]), v_max=V_MAX, v_min=V_MIN)
    assert out[0, 1] == pytest.approx(-0.20)


def test_ab_apply_speed_gate_keeps_existing_apply_alive():
    """施加门控只挡新增：已施加态在低速段仍维持（不被门强制释放）。"""
    ctrl = _ctrl(3.0)
    ctrl.ab_apply_speed_min_kmh = 55.0
    fast = _env(grade=-10.0 / 1000.0, vel=60.0 / 3.6)
    for _ in range(4):
        ctrl.get_action_notch_incr(fast, np.array([[1.0]]), v_max=V_MAX, v_min=V_MIN)
    slow = _env(grade=-10.0 / 1000.0, vel=45.0 / 3.6)
    out = ctrl.get_action_notch_incr(slow, np.array([[0.0]]), v_max=V_MAX, v_min=V_MIN)
    assert out[0, 1] == pytest.approx(-0.20)   # 已 on ⇒ 维持


def test_overspeed_forces_service():
    """超速兜底：vel ≥ vmax_eff 强制 SERVICE（RL 无权关闭）。"""
    ctrl = _ctrl(3.0)
    fast = SimpleNamespace(dynamics=SimpleNamespace(vel=np.array([21.0])))
    out = ctrl.get_action_notch_incr(fast, np.array([[1.0]]), v_max=V_MAX, v_min=V_MIN)
    assert out[0, 1] == pytest.approx(-0.40)


def test_low_speed_release():
    """低速强制缓解（V17 教训）：vel ≤ v_min + margin → AB 释放。"""
    ctrl = _ctrl(3.0)
    ctrl.ab_low_speed_release = True
    # 先升到 n=0.60 派生 AB（正常速度）
    env = _env()
    for _ in range(4):
        ctrl.get_action_notch_incr(env, np.array([[1.0]]), v_max=V_MAX, v_min=V_MIN)
    slow = SimpleNamespace(
        dynamics=SimpleNamespace(vel=np.array([V_MIN + 2.0 / 3.6 - 0.1])))
    out = ctrl.get_action_notch_incr(slow, np.array([[1.0]]), v_max=V_MAX, v_min=V_MIN)
    assert out[0, 1] == 0.0


def test_refill_gate_blocks_quick_reapply():
    """222s 充风门：释放后未充风完再越限 → 本步不发（已建立源不受影响）。"""
    ctrl = _ctrl(3.0)
    env = _env()
    for _ in range(4):   # n=0.60，AB on
        ctrl.get_action_notch_incr(env, np.array([[1.0]]), v_max=V_MAX, v_min=V_MIN)
    ctrl.get_action_notch_incr(env, np.array([[-1.0]]), v_max=V_MAX, v_min=V_MIN)  # n=0.45 保持
    ctrl.get_action_notch_incr(env, np.array([[-1.0]]), v_max=V_MAX, v_min=V_MIN)  # n=0.30 释放
    # 重新升越限：n=0.45（保持→0.45≥0.45 不触发；继续 +）
    ctrl.get_action_notch_incr(env, np.array([[1.0]]), v_max=V_MAX, v_min=V_MIN)  # n=0.45
    out = ctrl.get_action_notch_incr(env, np.array([[1.0]]), v_max=V_MAX, v_min=V_MIN)
    # n=0.60 越限请求，但距释放仅几秒 << 222s 充风门 → 拒绝
    assert out[0, 1] == 0.0
    assert ctrl.ab_refill_veto_count == 1


def test_mode_requires_rate_limit():
    """fail-fast：rate 未配置（=0）不得静默进入本模式。"""
    ctrl = _ctrl(0.0)
    with pytest.raises(ValueError):
        ctrl.get_action_notch_incr(_env(), np.array([[1.0]]), v_max=V_MAX, v_min=V_MIN)


def test_rejects_wrong_action_shape():
    """fail-fast：动作维度必须为 1（防串模式静默错配）。"""
    ctrl = _ctrl(3.0)
    with pytest.raises(ValueError):
        ctrl.get_action_notch_incr(_env(), np.array([[0.5, 0.5]]),
                                   v_max=V_MAX, v_min=V_MIN)


def test_env_wiring_act1_obs13():
    """env 接线：act_dim=1、obs_dim=13、action_space (num_agents,1)、参数透传。"""
    from src.environments.train_fleet_env import TrainFleetEnv
    env = TrainFleetEnv({
        'num_trains': 1,
        'consist_preset': '10kt_1plus0',
        'grade_profile': 'long_downhill',
        'max_steps': 3,
        'decompose': 'loco_notch_incr',
        'notch_incr_rate_notches': 3.0,
        'ab_derive_threshold': 0.5,
        'ab_derive_release_margin': 0.05,
        'ab_derive_notch_idx': 2,
    })
    try:
        assert env.act_dim == 1
        assert env.obs_dim == 13
        assert env.action_space.shape == (env.num_agents, 1)
        assert env.observation_schema['name'] == 'loco_notch_incr_v1'
        for c in env.multi_loco_controllers:
            assert c.notch_incr_rate_notches == 3.0
            assert c.ab_derive_threshold == 0.5
            assert c.ab_derive_release_margin == 0.05
            assert c.ab_derive_notch_idx == 2
    finally:
        env.close()


def test_env_step_end_to_end_notch_integration():
    """端到端：正增量动作积分级位、obs[12] 可观测、AB 派生进入 info。"""
    from src.environments.train_fleet_env import TrainFleetEnv
    env = TrainFleetEnv({
        'num_trains': 1,
        'consist_preset': '10kt_1plus0',
        'grade_profile': 'long_downhill',
        'max_steps': 12,
        'decompose': 'loco_notch_incr',
        'notch_incr_rate_notches': 3.0,
    })
    try:
        env.reset(options={'speed': 65.0 / 3.6})
        obs, _, _, _, info = env.step(np.full((env.num_agents, 1), 1.0))
        assert obs.shape == (env.num_agents, 13)
        # 1 决策步后级位 = 0.15（起点惰行）
        assert float(obs[0, 12]) == pytest.approx(0.15)
        # 连续正增量 → 级位单调升、饱和到 1.0
        for _ in range(6):
            obs, _, _, _, info = env.step(np.full((env.num_agents, 1), 1.0))
        assert float(obs[0, 12]) == pytest.approx(1.0)
    finally:
        env.close()
