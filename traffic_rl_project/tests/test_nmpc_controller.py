"""
多体 NMPC 成熟对比基线冒烟测试（NMPCController，casadi + IPOPT，2026-09-17）。

验证要点（对应 plan Step 3）：
- 求解成功：首次滚动时域 IPOPT 求解 status == 'optimal'，输出契约 (num_trains,) 且有限
- 车钩力约束生效：NMPC 驱动的短 rollout 全程车钩力 ≤ 1000kN、viol==0
- solve_times 有值：每步求解耗时被记录（同档对冲主指标）
- 与 D-Rule 数值量级一致：同剖面/同时域下 NMPC 与规则基线（RL 调制恒 0）的车钩力峰值
  与 ED 深度同量级（非粗糙靶子：成熟 MPC 与规则基线在物理带内一致）

背景：列距符号约定（2026-09-17 诊断）——编队中 head 递减（后列在前列后方），
gap = 前列尾 - 后列头；早期实现写成 head 差导致 gap 为负 → IPOPT 不可行
（violation 220 = 符号反置的 -200m 列距）。本测试覆盖 3 列 fleet env 以确保回归。
"""
import numpy as np
import pytest

from src.environments.train_fleet_env import TrainFleetEnv
from src.controllers.nmpc_controller import NMPCController
from src.train_dynamics.params import CouplerParams


def _make_fleet(num_trains=3, grade='long_downhill', max_steps=200):
    return TrainFleetEnv({
        'num_trains': num_trains,
        'consist_preset': '10kt_1plus1',
        'grade_profile': grade,
        'target_speed': 20.0,
        'max_steps': max_steps,
        'eval_mode': True,
        'decompose': 'loco_ed_ab',
    })


def _make_nmpc(env):
    return NMPCController(
        num_trains=env.num_trains, dt=0.1,
        v_max=env.v_max, v_min=env.v_min,
        target_speed=env.target_speed,
        headway_s=getattr(env, 'headway_s', 5.0),
        gap_min=20.0,
        coupler_params=CouplerParams(),
        inner_rule_cyclic=True,
        ipopt_max_iter=300,
    )


def _nmpc_act(env):
    """评估侧同流程：NMPC 每列目标加速度 → 每机车动作（evaluate_decompose.mpc_act）。"""
    U = env._mpc_controller.compute_actions_from_env(env)
    acts = []
    for ti, tr in enumerate(env.trains):
        row = env.multi_loco_controllers[ti].get_action_accel(tr, float(U[ti]))
        acts.append(np.asarray(row, dtype=float))
    return np.concatenate(acts, axis=0).astype(np.float32)


def _rollout(env, act_fn, steps=60, init_speed_kmh=80.0):
    env.reset(options={'speed': init_speed_kmh / 3.6})
    peak = viol = 0.0
    ed_sum = n = 0
    for _ in range(steps):
        obs, r, term, trunc, info = env.step(act_fn(env))
        peak = max(peak, float(info['coupler_force_peak']))
        viol += float(info['coupler_limit_violations'])
        ed_sum += float(np.mean(info['executed_actions'][:, 0]))
        n += 1
        if term or trunc:
            break
    return {'peak_kN': peak / 1e3, 'viol': int(viol),
            'mean_ed': ed_sum / max(n, 1)}


def test_nmpc_solves_and_output_contract():
    """首次滚动时域求解成功 + 输出契约 (num_trains,) 有限且落在加速度边界内。"""
    env = _make_fleet()
    ctrl = _make_nmpc(env)
    env._mpc_controller = ctrl
    env.reset(options={'speed': 80.0 / 3.6})
    U = ctrl.compute_actions_from_env(env)
    assert ctrl._last_status == 'optimal', f"IPOPT 应求解成功，实际 {ctrl._last_status}"
    assert U.shape == (env.num_trains,)
    assert np.all(np.isfinite(U))
    assert np.all(U >= ctrl.accel_lo - 1e-9) and np.all(U <= ctrl.accel_hi + 1e-9)
    assert len(ctrl.solve_times) == 1 and ctrl.solve_times[0] > 0
    assert ctrl.solve_statuses == ['optimal']
    env.close()


def test_nmpc_three_train_infeasibility_regression():
    """【回归 2026-09-17】3 列 fleet（head 递减）首次求解必须 optimal，不得不可行。"""
    env = _make_fleet(num_trains=3)
    ctrl = _make_nmpc(env)
    env._mpc_controller = ctrl
    env.reset(options={'speed': 65.0 / 3.6})
    U = ctrl.compute_actions_from_env(env)
    assert ctrl._last_status == 'optimal', f"3 列 fleet 求解应 optimal，实际 {ctrl._last_status}"
    assert U.shape == (3,) and np.all(np.isfinite(U))
    env.close()


def test_nmpc_coupler_constraint_in_rollout():
    """NMPC 驱动短 rollout：车钩力硬约束生效（峰值 ≤ 1000kN、viol==0）。"""
    env = _make_fleet()
    ctrl = _make_nmpc(env)
    env._mpc_controller = ctrl
    res = _rollout(env, _nmpc_act, steps=40)
    assert res['viol'] == 0
    assert res['peak_kN'] <= 1000.0, f"车钩力峰值 {res['peak_kN']:.0f}kN 超过 1000kN"
    env.close()


def test_nmpc_magnitude_comparable_to_rule_baseline():
    """同剖面同时域：NMPC 与 D-Rule（RL 调制恒 0）车钩力/ED 深度同量级（非粗糙靶子）。"""
    # D-Rule：decompose env + 全零动作（MultiLocoController 规则基线）
    env_r = _make_fleet()
    r_rule = _rollout(env_r, lambda e: np.zeros((e.num_agents, 2), dtype=np.float32),
                      steps=40)
    env_r.close()
    # NMPC：同环境同协议
    env_n = _make_fleet()
    ctrl = _make_nmpc(env_n)
    env_n._mpc_controller = ctrl
    r_nmpc = _rollout(env_n, _nmpc_act, steps=40)
    env_n.close()

    assert r_rule['viol'] == 0 and r_nmpc['viol'] == 0
    # 同量级：车钩力峰值相互在 2 倍带内，ED 深度差 < 0.6（两者都在物理制动带内）
    assert r_nmpc['peak_kN'] <= 2.0 * r_rule['peak_kN'] + 1e-9, \
        f"NMPC 车钩力峰值 {r_nmpc['peak_kN']:.0f}kN 远超规则基线 {r_rule['peak_kN']:.0f}kN"
    assert abs(r_nmpc['mean_ed'] - r_rule['mean_ed']) < 0.6, \
        f"NMPC ED深度 {r_nmpc['mean_ed']:.3f} vs D-Rule {r_rule['mean_ed']:.3f} 量级不一致"


def test_nmpc_solve_times_recorded_across_steps():
    """多步滚动：solve_times/solve_statuses 逐帧累积且 reset() 清空。"""
    env = _make_fleet(num_trains=2)
    ctrl = _make_nmpc(env)
    env._mpc_controller = ctrl
    env.reset(options={'speed': 65.0 / 3.6})
    for _ in range(3):
        ctrl.compute_actions_from_env(env)
    assert len(ctrl.solve_times) == 3
    assert len(ctrl.solve_statuses) == 3
    assert all(s == 'optimal' for s in ctrl.solve_statuses)
    ctrl.reset()
    assert len(ctrl.solve_times) == 0 and len(ctrl.solve_statuses) == 0
    env.close()
