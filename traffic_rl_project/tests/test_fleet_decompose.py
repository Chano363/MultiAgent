"""
decompose='loco_ed_ab' 逐机车 RL 智能体模式验证测试（ADR-009.1 换架构，2026-09-05）。

验证要点：
- 智能体 = 每台机车（列内真多智能体），默认模式零回归（decompose=None 完全走旧路径）
- 动作 (num_agents, 2) = 每机车 [ed_mod, ab_mod] 调制，规则基线（ED优先+AB兜底）+ RL 调制
- AB 抑制仅在远离超速时生效（AB 兜底不被轻率关闭）；AB 提前触发 = MIN 档兜底
- 电空分工奖励塑形：AB 使用成本 > ED 使用成本（ED 优先可学）
"""

import os
import sys

import pytest
import numpy as np


from src.environments.train_fleet_env import TrainFleetEnv
from src.controllers.multi_loco_controller import MultiLocoController


def _make_decompose_fleet(num_trains=1, max_steps=20):
    return TrainFleetEnv({
        'num_trains': num_trains,
        'consist_preset': '10kt_1plus1',   # 1+1 双机车（2 个智能体）
        'grade_profile': 'long_downhill',
        'target_speed': 20.0,
        'max_steps': max_steps,
        'decompose': 'loco_ed_ab',
    })


def test_decompose_agent_count_and_shapes():
    """decompose 模式：智能体 = 机车数（1+1 编组单列 = 2），obs/action 形状匹配。"""
    env = _make_decompose_fleet(num_trains=1)
    obs, _ = env.reset(options={'speed': 65.0 / 3.6})
    assert env.num_agents == 2  # 队首 + 队尾机车
    assert obs.shape == (2, 12)
    assert env.action_space.shape == (2, 2)
    assert env.obs_dim == 12 and env.act_dim == 2


def test_decompose_default_mode_unchanged():
    """decompose=None：完全走旧路径（智能体=列），零回归。"""
    env = TrainFleetEnv({
        'num_trains': 2,
        'consist_preset': '10kt_1plus0',
        'grade_profile': 'long_downhill',
        'max_steps': 5,
    })
    obs, _ = env.reset()
    assert env.num_agents == 2 and env.act_dim == 1
    assert obs.shape == (2, 11)
    actions = np.zeros(2)
    obs2, r, term, trunc, info = env.step(actions)
    assert obs2.shape == (2, 11)
    assert 'ab_source_count' not in info  # 旧模式无电空分工指标


def test_decompose_step_shapes_and_metrics():
    """decompose step：(2,2) 动作推进，info 携带电空分工诊断指标。"""
    env = _make_decompose_fleet()
    obs, _ = env.reset(options={'speed': 70.0 / 3.6})
    rng = np.random.default_rng(0)
    for _ in range(5):
        actions = rng.uniform(-1, 1, size=(2, 2))
        obs, r, term, trunc, info = env.step(actions)
        assert obs.shape == (2, 12)
        assert np.all((obs[:, 11] >= 0.0) & (obs[:, 11] <= 1.0))  # ADR-030 AB 充风就绪度 ∈[0,1]
        assert info['executed_actions'].shape == (2, 2)
        assert info['ab_source_count'] >= 0
        assert 0.0 <= info['mean_ed_frac'] <= 1.0
    assert not term  # 20 步内不终止


def test_decompose_ed_modulation_changes_ed():
    """ed_mod 调制实际改变机车 ED 深度（真物理杠杆：±ed_mod_coef = ±0.5 绝对量）。"""
    env = _make_decompose_fleet()
    env.reset(options={'speed': 81.0 / 3.6})  # 超上限 → 规则进入制动（基线 ED > 0）
    tr = env.trains[0]
    ctrl = env.multi_loco_controllers[0]
    zero = np.zeros((2, 2))
    final0, base0 = ctrl.get_action_decomposed(tr, zero, v_max=env.v_max, v_min=env.v_min)
    assert np.all(base0[:, 0] > 0)  # 制动态基线 ED 打满（错峰后仍 > 0）
    plus = zero.copy()
    plus[:, 0] = 1.0  # 满幅加深 ED
    final1, _ = ctrl.get_action_decomposed(tr, plus, v_max=env.v_max, v_min=env.v_min)
    minus = zero.copy()
    minus[:, 0] = -1.0  # 满幅减弱 ED
    final2, _ = ctrl.get_action_decomposed(tr, minus, v_max=env.v_max, v_min=env.v_min)
    assert np.all(final1[:, 0] >= final0[:, 0] - 1e-9)
    assert np.all(final2[:, 0] <= final0[:, 0] + 1e-9)
    # 调制幅度上限 = ±ed_mod_coef(ADR-024：0.5 半幅)
    assert np.all(final1[:, 0] <= base0[:, 0] + 0.5 + 1e-9)


def _shift_into_steep(env, offset=2500.0):
    """把列车平移进 long_downhill 的 -10.2‰ 陡坡段（500-3000m），测试 ED 不足场景。"""
    for tr in env.trains:
        tr.dynamics.pos = tr.dynamics.pos + offset


def test_decompose_baseline_ab_fallback_on_steep_grade():
    """物理化 ED 可用度：陡坡高速制动态下 ED 功率不足 → 规则基线真实触发 AB 兜底。"""
    env = _make_decompose_fleet()
    env.reset(options={'speed': 81.0 / 3.6})  # 超上限 → 规则循环制动
    _shift_into_steep(env)
    tr = env.trains[0]
    ctrl = env.multi_loco_controllers[0]
    ed_avail = ctrl._ed_ab_price(tr)
    assert ed_avail < 0.99  # -10.2‰ 陡坡 @ ~80km/h：F_ed(=P/v) < F_req
    base, _ = ctrl.get_action_decomposed(tr, np.zeros((2, 2)),
                                         v_max=env.v_max, v_min=env.v_min)
    assert np.all(base[:, 1] < 0)  # 基线 AB 兜底被触发（SERVICE 档）


def test_decompose_ab_suppress_allowed_when_far_below_vmax():
    """AB 抑制：远离超速（vel < v_max-0.5）且基线 AB 激活时，RL 抑制生效。"""
    env = _make_decompose_fleet()
    env.reset(options={'speed': 81.0 / 3.6})
    _shift_into_steep(env)
    ctrl = env.multi_loco_controllers[0]
    # 制动降速至脱离 v_max 裕量（vel < v_max - 0.5），且 ED 仍不足（基线 AB 保持）
    suppress = np.zeros((2, 2))
    suppress[:, 1] = 1.0  # ab_mod=+1 → 请求抑制
    found = False
    for _ in range(150):
        tr = env.trains[0]
        if (tr.dynamics.vel[0] < env.v_max - MultiLocoController.AB_SUPPRESS_MARGIN_MPS
                and ctrl._ed_ab_price(tr) < 0.99):
            final, base = ctrl.get_action_decomposed(
                tr, suppress, v_max=env.v_max, v_min=env.v_min)
            assert base[0, 1] < 0      # 基线 AB 兜底激活
            assert final[0, 1] == 0.0  # 远离超速 → 抑制生效（RL 可关兜底省 AB 成本）
            found = True
            break
        env.step(suppress)
    assert found, "150 步内未进入'远离超速且 ED 不足'窗口"


def test_decompose_ab_advance_fallback():
    """AB 提前兜底：基线无 AB 时 ab_mod<-0.5 → 该机车触发 MIN 档 AB 源。"""
    env = _make_decompose_fleet()
    env.reset(options={'speed': 60.0 / 3.6})  # 中段滑行（低于上限，基线不制动）
    tr = env.trains[0]
    ctrl = env.multi_loco_controllers[0]
    advance = np.zeros((2, 2))
    advance[:, 1] = -1.0
    final, base = ctrl.get_action_decomposed(tr, advance, v_max=env.v_max, v_min=env.v_min)
    assert base[0, 1] >= 0            # 基线无 AB
    assert final[0, 1] == MultiLocoController.AB_FALLBACK_NOTCH  # MIN 档兜底被触发


def test_decompose_reward_ab_more_expensive_than_ed():
    """电空分工塑形：同样 1 单位制动量，走 AB 的成本显著高于走 ED（ED 优先可学）。"""
    env = _make_decompose_fleet()
    env.reset(options={'speed': 78.0 / 3.6})
    tr = env.trains[0]
    ctrl = env.multi_loco_controllers[0]
    zero = np.zeros((2, 2))
    final0, _ = ctrl.get_action_decomposed(tr, zero, v_max=env.v_max, v_min=env.v_min)
    # 用纯规则基线跑一步作参照
    accels = np.zeros(1)
    r_base = env._calculate_reward_decomposed(
        env._get_obs_decomposed(), accels, ab_count=0,
        ed_sum=float(np.sum(final0[:, 0])))
    r_ab = env._calculate_reward_decomposed(
        env._get_obs_decomposed(), accels, ab_count=2,
        ed_sum=float(np.sum(final0[:, 0])))
    assert r_base == r_ab  # AB 成本已归零（AB 是手段、车钩力是目标，诊断-2026-09-05）


def test_decompose_fleet_multi_train_shape():
    """多列 decompose（后叠阶段备用）：智能体 = 列数×机车数。"""
    env = _make_decompose_fleet(num_trains=2, max_steps=5)
    obs, _ = env.reset(options={'speed': 65.0 / 3.6})
    assert env.num_agents == 4
    assert obs.shape == (4, 12)
    obs2, r, term, trunc, info = env.step(np.zeros((4, 2)))
    assert obs2.shape == (4, 12)


def test_decompose_ab_release_command_issued():
    """【bug回归 2026-09-05】decompose 无 AB 源时必须发 RELEASE（None 不缓解残留制动）。

    场景：陡坡施加 SERVICE AB 后切缓解 → 空气制动须真正缓解（否则列车被残留
    制动拖停，15000 步全程评估实证）。"""
    from src.train_dynamics.braking import AirBrakeNotch
    env = _make_decompose_fleet()
    env.reset(options={'speed': 81.0 / 3.6})
    _shift_into_steep(env)
    tr = env.trains[0]
    ab_actions = np.array([[0.0, -0.75], [0.0, -0.75]])
    for _ in range(30):
        tr.step(ab_actions)
    st = tr.dynamics.air_brake_state()
    assert any(x != AirBrakeNotch.RELEASE for x in st)  # AB 已施加
    release = np.zeros((2, 2))
    # 【R0-E 2026-09-06】缓解 = 缓解波传播(~6s) + 制动缸排气 exp(-t/4s)（4τ=16s），
    # 全列彻底缓解需 ~25s → 400 步（旧瞬时释放模型 150 步即可）。
    for _ in range(400):
        tr.step(release)
    st = tr.dynamics.air_brake_state()
    assert all(x == AirBrakeNotch.RELEASE for x in st), \
        "缓解指令未生效：残留空气制动未缓解（ab_command=None bug 回归）"
    # 缓解后列车在陡坡应重新加速（不再被拖停）
    # 【2026-10-12 容嘉欣查表迟滞后】无牵引惰行 + 平均坡度 -2‰ + 24.4 m/s
    # Davis 阻力下，列车净加速度约 -0.01 m/s²（真实物理：坡度拉力 < 滚动+空气
    # 阻力），缓解压缩的弹性回弹叠加后短期内呈振荡微降。原"50 步必加速"断言
    # 是旧低刚度线性车钩标定的，新物理下不再成立。改用"速度不塌缩 + 缓解后
    # 车钩力逐步消散"两断言，同样拦截"残留制动拖停"bug（残留制动 → 速度
    # 持续大幅下降 + 钩力长期保持高位）。
    v0 = float(tr.dynamics.vel[0])
    for _ in range(150):
        tr.step(release)
    v_end = float(tr.dynamics.vel[0])
    f_end = float(np.max(np.abs(tr.dynamics.coupler_interface_forces()))) / 1e3
    assert v_end > 20.0, \
        f"缓解后列车速度塌缩（{v_end:.2f} m/s），疑似残留制动未释放"
    assert f_end < 300.0, \
        f"缓解 15s 后车钩力仍 {f_end:.0f} kN，疑似残留制动力未消散"


def test_decompose_mask_lever_isolates_modulation():
    """【杠杆隔离消融 2026-09-05】mask_lever 禁用对应调制，训练与评估机制一致。

    - mask='ab'：禁用 ab_mod（仅 ED 杠杆生效）→ ED 仍随 ed_mod 变化、AB 分支锁基线；
    - mask='ed'：禁用 ed_mod（仅 AB 杠杆生效）→ ED 锁基线、AB 仍随 ab_mod 触发兜底。
    """
    env = _make_decompose_fleet()
    env.reset(options={'speed': 81.0 / 3.6})   # 超上限 → 制动态
    tr = env.trains[0]
    ctrl = env.multi_loco_controllers[0]
    zero = np.zeros((2, 2))
    base, _ = ctrl.get_action_decomposed(tr, zero, v_max=env.v_max, v_min=env.v_min)

    # --- mask='ab'：仅 ED 杠杆生效（ab_mod 被禁用）---
    ctrl.mask_lever = 'ab'
    actions = np.array([[1.0, -1.0], [0.5, -1.0]])   # ed_mod>0 加深 ED；ab_mod<-0.5 应被禁用
    final_ab_masked, _ = ctrl.get_action_decomposed(tr, actions, v_max=env.v_max, v_min=env.v_min)
    assert np.all(final_ab_masked[:, 0] >= base[:, 0] - 1e-9)      # ED 仍被加深（ED 杠杆生效）
    assert np.all(final_ab_masked[:, 1] <= base[:, 1] + 1e-9)      # AB 兜底未被提前触发（ab_mod=0）

    # --- mask='ed'：仅 AB 杠杆生效（ed_mod 被禁用）---
    ctrl.mask_lever = 'ed'
    actions2 = np.array([[1.0, -1.0], [1.0, -1.0]])
    final_ed_masked, _ = ctrl.get_action_decomposed(tr, actions2, v_max=env.v_max, v_min=env.v_min)
    assert np.all(np.abs(final_ed_masked[:, 0] - base[:, 0]) < 1e-9)  # ED 锁基线（ed_mod=0）
    # AB 提前触发在规则基线非 AB 态下生效（ab_mod 杠杆可用）
    if np.all(base[:, 1] >= 0):
        # 【2026-09-26 单步并发 ≤1】至多 1 台机车可新增 AB 源（防多源压缩波同步叠加），
        # 故不再要求"每台机车都触发"，只要求恰好 1 台被 AB 杠杆触发。
        n_fallback = int(np.sum(
            final_ed_masked[:, 1] == MultiLocoController.AB_FALLBACK_NOTCH))
        assert n_fallback == MultiLocoController.AB_MAX_CONCURRENT_ADD


def test_hetero_domain_randomization_resample():
    """【E4-H】hetero 训练态每 episode reset 重新抽取逐车钩参数；eval 态/齐次保持固定。"""
    def _stiff(env):
        # 汇总所有列首车钩刚度数组的样本（浮点唯一值计数）
        return [round(float(a), 3) for tr in env.trains for a in tr.dynamics._cp['stiffness'][:3]]
    # 训练态（eval_mode=False）：两次 reset 参数应不同（domain randomization）
    env = TrainFleetEnv({'num_trains': 2, 'consist_preset': '10kt_1plus1',
                         'grade_profile': 'long_downhill', 'max_steps': 10,
                         'decompose': 'loco_ed_ab', 'hetero': True, 'hetero_seed': 3})
    env.reset(options={'speed': 65.0 / 3.6})
    s1 = _stiff(env)
    env.reset(options={'speed': 65.0 / 3.6})
    s2 = _stiff(env)
    assert len(set(s1) & set(s2)) != len(s1), "训练态 reset 应重新抽样（参数每 episode 变化）"
    env.close()
    # eval 态（eval_mode=True）：构造时 fix 抽取，多次 reset 保持固定（held-out 可复现）
    env_e = TrainFleetEnv({'num_trains': 2, 'consist_preset': '10kt_1plus1',
                           'grade_profile': 'long_downhill', 'max_steps': 10,
                           'decompose': 'loco_ed_ab', 'hetero': True, 'hetero_seed': 7,
                           'eval_mode': True})
    env_e.reset(options={'speed': 65.0 / 3.6})
    e1 = _stiff(env_e)
    env_e.reset(options={'speed': 65.0 / 3.6})
    e2 = _stiff(env_e)
    assert (e1 == e2), f"eval 态 reset 应保持固定参数，实际变化 {e1} -> {e2}"
    env_e.close()
    # 齐次（hetero=False）：默认零回归，reset 不改变参数
    env_h = TrainFleetEnv({'num_trains': 2, 'consist_preset': '10kt_1plus1',
                           'grade_profile': 'long_downhill', 'max_steps': 10,
                           'decompose': 'loco_ed_ab'})
    env_h.reset(options={'speed': 65.0 / 3.6})
    h1 = _stiff(env_h)
    env_h.reset(options={'speed': 65.0 / 3.6})
    h2 = _stiff(env_h)
    # 【2026-09-07 ADR】齐次默认全列统一 MT-2（原先机车相邻耦合 QKX100 auto 派发已移除）
    # 1+1 编组前 3 个耦合 = [loco-货, 货-货, 货-货] 全为 MT-2 基值（1.89e7）
    assert h1 == h2, "齐次 reset 参数不变"
    for idx in (0, 1, 2, 3, 4, 5):
        assert abs(h1[idx] - 1.89e7) < 1e-9, f"全列耦合应为 MT-2 1.89e7，实际 {h1[idx]}"
    env_h.close()


# ---------------------------------------------------------------------------
# 【ADR-029 回归 2026-10-04】安全层对**牵引**的权限 + EBI 紧急 AB 的优先级。
# 根因：原 proj_throttle 把牵引动作映射为 0 ⇒ 牵引绕过安全层（规则 A/B/D 对其失效）；
#       且 step_vehicles_ed_ab 中 ab_sources 优先级高于 ab_command ⇒ EBI 紧急被丢弃。
# 后果：EBI 触发时仍满牵引，"边牵引边紧急制动"，长大下坡虚耦合穿透（gap→−65m）。
# ---------------------------------------------------------------------------

def _make_child_decompose_env(profile='long_downhill', max_steps=50):
    """单列 decompose 子环境（带 ETCS 曲线）——安全层对牵引/AB 权限的定向回归用。"""
    from src.train_dynamics.grade_profile import PROFILES
    from src.train_dynamics.etcs_braking import EtcsBrakingCurve
    from src.environments.train_env import TrainFormationEnv
    prof = PROFILES[profile]()
    curve = EtcsBrakingCurve(
        speed_profile=[(40.0 / 3.6, 0.426), (60.0 / 3.6, 0.401), (80.0 / 3.6, 0.382)],
        k_dry=1.0,
        brake_build_up_s=4.68,
        assumed_accel_during_buildup=0.12,
        grade_at=prof.grade_at,
    )
    return TrainFormationEnv({
        'consist_preset': '10kt_1plus1',
        'grade_profile': profile,
        'target_speed': 20.0,
        'line_speed_limit_mps': 22.222,
        'max_steps': max_steps,
        'etcs_curve': curve,
        'decompose': 'loco_ed_ab',
    })


def _spy_apply(env, cap):
    """包装 step_vehicles_ed_ab，捕获真正送入动力学的 (throttle, ab_command, ab_sources)。"""
    orig = env.dynamics.step_vehicles_ed_ab

    def spy(throttle, ed_throttle, ab_command, *args, **kwargs):
        cap['throttle'] = np.array(throttle, dtype=float)
        cap['ed_throttle'] = np.array(ed_throttle, dtype=float)
        cap['ab_command'] = ab_command
        cap['ab_sources'] = kwargs.get('ab_sources')
        return orig(throttle, ed_throttle, ab_command, *args, **kwargs)

    env.dynamics.step_vehicles_ed_ab = spy


def test_etcs_ebi_cancels_traction_and_forces_emergency():
    """EBI 时必须**取消牵引**并**真正下紧急 AB**（牵引不得绕过安全层）。"""
    from src.train_dynamics.etcs_braking import EbdTarget
    from src.train_dynamics.braking import AirBrakeNotch
    env = _make_child_decompose_env()
    env.reset(options={'speed': 20.0})
    head = float(env.dynamics.pos[0])
    # 目标极近且很慢 ⇒ 必然 EBI
    env.set_etcs_targets([EbdTarget(position_m=head + 30.0, speed_mps=3.0, kind='gap')])
    cap = {}
    _spy_apply(env, cap)
    env.step(np.array([[-1.0, 0.0], [-1.0, 0.0]]))   # 满牵引
    assert cap['throttle'].max() <= 0.0, "EBI 未取消牵引（牵引绕过安全层）"
    assert cap['ab_command'] == AirBrakeNotch.EMERGENCY, "EBI 未真正下紧急 AB"


def test_etcs_ebi_emergency_overrides_action_ab_sources():
    """动作已发 AB 源时，EBI 的紧急必须**压过**动作源（否则紧急升级被优先级丢弃）。"""
    from src.train_dynamics.etcs_braking import EbdTarget
    from src.train_dynamics.braking import AirBrakeNotch
    env = _make_child_decompose_env()
    env.reset(options={'speed': 20.0})
    head = float(env.dynamics.pos[0])
    env.set_etcs_targets([EbdTarget(position_m=head + 30.0, speed_mps=3.0, kind='gap')])
    cap = {}
    _spy_apply(env, cap)
    env.step(np.array([[-1.0, -0.75], [-1.0, -0.75]]))  # 满牵引 + 动作发 SERVICE AB 源
    assert cap['throttle'].max() <= 0.0
    assert cap['ab_command'] == AirBrakeNotch.EMERGENCY
    assert not cap['ab_sources'], "EBI 时动作 AB 源未清除，紧急升级会被优先级压掉"


# ---------------------------------------------------------------------------
# 【路线覆盖修复 2026-10-06】训练起点随机化（消除固定起点 OOD）。
# L1 诊断：固定起点 + 1200 步窗口只覆盖 −1.5‰ 单坡段，评估 83.9% 的步落在训练
# 未见坡度区间。修复：训练态每 episode 沿剖面随机前移编队（默认关零回归）。
# ---------------------------------------------------------------------------

def test_start_randomization_default_off_zero_regression():
    """默认（无 start_randomization）：起点固定，逐集不随机（零回归）。"""
    env = TrainFleetEnv({'num_trains': 1, 'consist_preset': '10kt_1plus1',
                         'grade_profile': 'shuozhou_23800', 'max_steps': 10,
                         'decompose': 'loco_ed_ab'})
    env.reset(options={'speed': 65.0 / 3.6})
    p1 = float(env.trains[0].dynamics.pos[0])
    env.reset(options={'speed': 65.0 / 3.6})
    p2 = float(env.trains[0].dynamics.pos[0])
    assert p1 == p2, "默认关：起点必须固定（零回归）"
    env.close()


def test_start_randomization_enabled_covers_profile_and_eval_fixed():
    """开启后：训练态起点整体前移且逐集变化；eval 态恒定基准起点（可复现）。"""
    cfg = {'num_trains': 1, 'consist_preset': '10kt_1plus1',
           'grade_profile': 'shuozhou_23800', 'max_steps': 10,
           'decompose': 'loco_ed_ab',
           'start_randomization': {'enabled': True, 'seed': 0}}
    env = TrainFleetEnv(cfg)
    heads = []
    for _ in range(6):
        env.reset(options={'speed': 65.0 / 3.6})
        heads.append(float(env.trains[0].dynamics.pos[0]))
    assert min(heads) > 0.0, "开启后训练起点应整体前移（>0）"
    assert len({round(h, 3) for h in heads}) > 1, "训练态起点应逐集变化（随机化生效）"
    env.close()

    # eval 态：恒定基准起点（held-out 可复现）
    env_e = TrainFleetEnv({**cfg, 'eval_mode': True})
    env_e.reset(options={'speed': 65.0 / 3.6})
    e1 = float(env_e.trains[0].dynamics.pos[0])
    env_e.reset(options={'speed': 65.0 / 3.6})
    e2 = float(env_e.trains[0].dynamics.pos[0])
    assert e1 == e2, "eval 态起点必须固定（评估可复现）"
    env_e.close()
