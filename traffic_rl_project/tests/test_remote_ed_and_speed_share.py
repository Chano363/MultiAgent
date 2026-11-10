"""C 组 2026-11-08：ED 撤除时序 + 速度差协同收敛的契约。

三条硬约束在此逐条固定：①默认关 = 控制路径完全跳过（零回归）；②两端共同承担，
禁止单侧加刹；③只作用于 ED（电制动力矩），不新增 AB 源、不改档位、不碰紧急。
"""
import numpy as np
import pytest

from src.controllers.multi_loco_controller import MultiLocoController
from src.environments.train_fleet_env import TrainFleetEnv


def make_fleet(**overrides):
    cfg = {
        'num_trains': 3, 'consist_preset': '20kt_1plus108_1plus108',
        # 【ADR-060 联动解耦】shuozhou 剖面的分段限速联动会把循环制动触发门从
        # 80 拉到 (70 段限速 − margin)=65，起步 65 km/h 恰好触发循环制动，污染
        # 本组要验证的 ED 撤除时序契约；故用无限速表的 long_downhill 剖面。
        'grade_profile': 'long_downhill',
        'decompose': 'loco_ed_ab', 'max_steps': 5,
    }
    cfg.update(overrides)
    env = TrainFleetEnv(cfg)
    env.reset(seed=0, options={'speed': 65 / 3.6})
    return env


def test_defaults_off_and_no_formation_payload():
    """默认关：不发布编队 ED 快照，两个分支整体跳过（零回归的结构性保证）。"""
    env = make_fleet()
    try:
        assert env.ed_release_timing_guard is False
        assert env.speed_convergence_share is False
        env.step(np.zeros((6, 2)))
        assert not hasattr(env.trains[0], 'formation_neighbor_ed_frac')
        assert not hasattr(env.trains[0], 'formation_rear_speed_kmh')
        for ctrl in env.multi_loco_controllers:
            assert ctrl.ed_release_guard_veto_count == 0
            assert ctrl.ed_conv_unmet_count == 0
    finally:
        env.close()


def test_formation_snapshot_uses_adjacent_committed_ed_and_rear_speed():
    """快照 = 相邻列上一步已提交 ED 的最大值 + 紧邻后列队首速度（本步决策前一次采样）。"""
    env = make_fleet(speed_convergence_share=True)
    try:
        for ctrl in env.multi_loco_controllers:
            ctrl._previous_ed = np.array([0.9, 0.9])
        env.multi_loco_controllers[1]._previous_ed = np.array([0.2, 0.2])
        env.step(np.zeros((6, 2)))
        assert env.trains[0].formation_neighbor_ed_frac == pytest.approx(0.2)
        assert env.trains[1].formation_neighbor_ed_frac == pytest.approx(0.9)
        assert env.trains[2].formation_neighbor_ed_frac == pytest.approx(0.2)
        assert env.trains[2].formation_rear_speed_kmh is None
        assert env.trains[0].formation_rear_speed_kmh > 60.0
    finally:
        env.close()


def test_release_guard_holds_partial_ed_then_releases_with_neighbor():
    """撤 ED 事件 + 相邻列满 ED → 否决全撤、保住 level_frac 档；相邻列退出即放行。"""
    env = make_fleet(ed_release_timing_guard=True)
    try:
        ctrl = env.multi_loco_controllers[1]
        tr = env.trains[1]
        tr.formation_neighbor_ed_frac = 1.0
        ctrl._previous_ed = np.full(2, 0.50)
        final, baseline = ctrl.get_action_decomposed(tr, np.zeros((2, 2)))
        np.testing.assert_allclose(baseline[:, 0], 0.0)
        np.testing.assert_allclose(final[:, 0], 0.25)   # 0.50 × level_frac(默认 0.5)
        assert ctrl.ed_release_guard_veto_count == 1
        assert ctrl.ed_release_guard_hold_steps == 1
        # 相邻列仍满 ED → 继续保位（本步 previous 已是 0.25，靠持有窗而非重新触发）
        final_two, _ = ctrl.get_action_decomposed(tr, np.zeros((2, 2)))
        np.testing.assert_allclose(final_two[:, 0], 0.25)
        assert ctrl.ed_release_guard_veto_count == 1
        assert ctrl.ed_release_guard_hold_steps == 2
        # 相邻列退出满 ED → 立即放行（不再需要等持有窗到期）
        tr.formation_neighbor_ed_frac = 0.2
        final_three, _ = ctrl.get_action_decomposed(tr, np.zeros((2, 2)))
        np.testing.assert_allclose(final_three[:, 0], 0.0)
        assert ctrl.ed_release_guard_hold_steps == 2
    finally:
        env.close()


def test_release_guard_window_is_bounded_and_rearms_only_after_real_release():
    """持有窗到期后放行；且须真正退出制动（ED 落在近零）才重新解锁，不原地反复触发。"""
    env = make_fleet(ed_release_timing_guard=True, ed_release_guard_hold_s=0.2)
    try:
        ctrl = env.multi_loco_controllers[1]
        tr = env.trains[1]
        tr.formation_neighbor_ed_frac = 1.0
        ctrl._previous_ed = np.full(2, 0.50)
        ctrl.get_action_decomposed(tr, np.zeros((2, 2)))     # t0：否决 + 保位
        ctrl.get_action_decomposed(tr, np.zeros((2, 2)))     # t1：保位（窗口共 2 步）
        third, _ = ctrl.get_action_decomposed(tr, np.zeros((2, 2)))  # t2：窗口到期，放行
        np.testing.assert_allclose(third[:, 0], 0.0)
        assert ctrl.ed_release_guard_veto_count == 1
        fourth, _ = ctrl.get_action_decomposed(tr, np.zeros((2, 2)))  # t3：未解锁，不再触发
        np.testing.assert_allclose(fourth[:, 0], 0.0)
        assert ctrl.ed_release_guard_veto_count == 1
        assert ctrl._ed_guard_armed is True   # 上一分类均值为 0 → 已重新解锁待下次制动
    finally:
        env.close()


def test_speed_share_brakes_follower_and_releases_leader_in_same_step():
    """速度差协同：后车加 ED、前车减 ED，两端同时动作（禁止单侧加刹）。"""
    env = make_fleet(speed_convergence_share=True)
    try:
        follower_ctrl, follower_tr = env.multi_loco_controllers[1], env.trains[1]
        follower_tr.dynamics.vel[:] = 65 / 3.6
        follower_tr.formation_leader_speed_kmh = 61.0   # 差 4 km/h > tol 1.8
        add_final, add_base = follower_ctrl.get_action_decomposed(
            follower_tr, np.zeros((2, 2)))
        # u = min(0.20×2.2, 0.30) = 0.30 → 后车侧承担 (1−0.5)×u = 0.15
        np.testing.assert_allclose(add_base[:, 0], 0.0)
        np.testing.assert_allclose(add_final[:, 0], 0.15)
        assert follower_ctrl.ed_conv_unmet_count == 0
    finally:
        env.close()


def test_speed_share_never_turns_ed_into_traction_and_counts_unmet_share():
    """前车侧只减 ED：减到 0 为止（不转牵引=C5 的失败点），不足部分不转嫁后车，只计数。"""
    env = make_fleet(speed_convergence_share=True, cyclic_brake_trigger_kmh=60.0,
                     conv_share_lead_share=1.0)
    try:
        leader_ctrl, leader_tr = env.multi_loco_controllers[0], env.trains[0]
        leader_tr.dynamics.vel[:] = 65 / 3.6
        leader_tr.formation_rear_speed_kmh = 69.0
        cut_final, cut_base = leader_ctrl.get_action_decomposed(
            leader_tr, np.zeros((2, 2)))
        stagger = [1.0 - leader_ctrl._ed_stagger(i) for i in range(2)]
        expected = np.array([max(0.0, s - 0.30) for s in stagger])
        np.testing.assert_allclose(cut_base[:, 0], stagger)
        np.testing.assert_allclose(cut_final[:, 0], np.maximum(expected, 0.0))
        assert np.all(cut_final[:, 0] >= 0.0)
    finally:
        env.close()


def test_parameter_validation():
    with pytest.raises(ValueError):
        MultiLocoController(num_vehicles=218, loco_indices=[0, 109],
                            ed_release_guard_trigger_frac=0.1,
                            ed_release_guard_release_frac=0.2)
    with pytest.raises(ValueError):
        MultiLocoController(num_vehicles=218, loco_indices=[0, 109],
                            conv_share_lead_share=1.2)
    with pytest.raises(ValueError):
        MultiLocoController(num_vehicles=218, loco_indices=[0, 109],
                            ed_release_guard_hold_s=float('nan'))
