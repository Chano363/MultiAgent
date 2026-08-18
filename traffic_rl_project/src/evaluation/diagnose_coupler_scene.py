"""
【诊断】验证核心科学命题：车钩力是否在"群组协同"时才凸显？

命题（来自 2026-08-16 grill-me 讨论）：
    单列独立运行时，列车可自主选择循环制动时机，车钩力能守住 1000kN；
    一旦群组为保持安全间距而协同运行，后列必须跟随前列节奏，
    这种受间距约束的协同动作会放大列内冲动，导致车钩力逼近甚至超过上限。

即：车钩力 = 群组协同能力的"瓶颈"（协同越紧，车钩力越紧张）。

诊断工况（逐工况、逐列记录，满足项目规则第 8 条数据级留痕）：
  A. 单列独立：1 列万吨列车，底层控制器跟踪目标速度（自主制动），无列间间距约束
  B. 群组协同（松间距）：3 列编队，target_gap=200m，加扰动，间距响应策略
  C. 群组协同（紧间距）：3 列编队，target_gap=100m，加扰动，间距响应策略
  D. 群组协同（忽略车钩力策略）：间距响应策略 + 底层控制器不钳制车钩力（宋宗莹式对照）

每个工况测：每列车钩力峰值/超限次数/间距误差/速度，落盘 CSV 供论文引用。

用法（WSL，conda activate traffic_rl，在 traffic_rl_project 下）：
    python src/evaluation/diagnose_coupler_scene.py

输出：outputs/diagnostics/coupler_scene_<时间戳>.csv + 打印对比表
"""

import sys
import os
import csv
import time
import argparse
from pathlib import Path

sys.path.append(str(Path(__file__).parent.parent.parent))

import numpy as np

from src.environments.train_env import TrainFormationEnv
from src.environments.train_fleet_env import TrainFleetEnv
from src.controllers.low_level_controller import TrainLowLevelController
from src.evaluation.evaluate_fleet import baseline_no_coupler_mar


# ---------------------------------------------------------------------------
# 工况 A：单列独立
# ---------------------------------------------------------------------------
def run_single_train(grade_profile='long_downhill', target_speed=20.0,
                     max_steps=300, max_accel=1.0, enforce_coupler=True,
                     speed_kp=0.8, seed=0,
                     forced_brake_step=None, forced_brake_accel=-0.8):
    """单列独立：底层控制器跟踪目标速度（自主选择制动），无列间间距约束。

    等价于"单列长大下坡自动驾驶"，是群组协同的对立面。
    forced_brake_step/forced_brake_accel：可选，模拟单列也遭遇"突发强制制动"
        （对应群组里领航车被扰动），用于归因"978kN 是扰动造成的还是群组造成的"。
    """
    env = TrainFormationEnv({
        'consist_preset': '10kt_1plus0',
        'grade_profile': grade_profile,
        'target_speed': target_speed,
        'dt': 0.1,
        'max_steps': max_steps,
    })
    ctrl = TrainLowLevelController(
        num_vehicles=env.num_vehicles, dt=env.dt, max_accel=max_accel,
        enforce_coupler=enforce_coupler,
    )
    obs, _ = env.reset(options={'speed': target_speed * 0.8})

    peak = 0.0
    violations = 0
    speed_errors = []
    integral = 0.0
    prev_err = 0.0
    for step in range(max_steps):
        # PID 速度跟踪（同 baseline_single_train_pid 逻辑）
        speed_err = target_speed - env.dynamics.vel[0]
        # 模拟单列遭遇强制制动（对应群组领航车扰动）
        if forced_brake_step is not None and step >= forced_brake_step:
            target_accel = forced_brake_accel
        else:
            integral += speed_err * env.dt
            der = (speed_err - prev_err) / max(env.dt, 1e-6)
            prev_err = speed_err
            target_accel = float(np.clip(speed_kp * speed_err + 0.1 * integral + 0.1 * der,
                                         -max_accel, max_accel))
        actions = ctrl.get_action_accel(env, target_accel)
        obs, reward, term, trunc, info = env.step(actions)
        peak = max(peak, info['coupler_force_peak'])
        violations = info['coupler_limit_violations']
        speed_errors.append(abs(env.dynamics.vel[0] - target_speed))
        if term or trunc:
            break

    return {
        'coupler_peak_kN': peak / 1e3,
        'coupler_violations': violations,
        'speed_err_mean': float(np.mean(speed_errors)),
    }


# ---------------------------------------------------------------------------
# 工况 B/C/D：群组协同
# ---------------------------------------------------------------------------
def run_fleet(num_trains=3, grade_profile='long_downhill', target_speed=20.0,
              target_gap=100.0, max_steps=300, max_accel=1.0,
              enable_disturbance=True, disturbance_step=100,
              disturbance_target_accel=-0.8, use_coupler_constraint=True,
              use_fleet_strategy=True, seed=0):
    """群组协同：3 列编队，加扰动，列间间距响应策略。

    use_coupler_constraint：底层控制器是否钳制车钩力（True=工程真实，False=宋宗莹式忽略）
    use_fleet_strategy：True=间距响应策略（baseline_no_coupler_mar，协同），
                        False=每列独立PID（baseline_single_train_pid，无协同）
    """
    env = TrainFleetEnv({
        'num_trains': num_trains, 'consist_preset': '10kt_1plus0',
        'grade_profile': grade_profile, 'target_speed': target_speed,
        'target_gap': target_gap, 'dt': 0.1, 'max_steps': max_steps,
        'max_accel': max_accel, 'enable_disturbance': enable_disturbance,
        'disturbance_step': disturbance_step,
        'disturbance_target_accel': disturbance_target_accel,
        'use_coupler_constraint': use_coupler_constraint,
    })
    obs, _ = env.reset(options={'speed': target_speed * 0.8})

    # 每列 PID 状态（baseline_single_train_pid）
    integral = np.zeros(num_trains)
    prev_err = np.zeros(num_trains)

    # 逐列统计
    per_train_peak = np.zeros(num_trains)
    per_train_viol = np.zeros(num_trains)
    gap_errors = []
    speed_errors = []
    collision = False

    for step in range(max_steps):
        if use_fleet_strategy:
            # 间距响应协同策略（baseline_no_coupler_mar：只用间距，不管车钩力）
            actions = baseline_no_coupler_mar(env, target_gap_weight=0.4)(obs)
        else:
            # 每列独立 PID（无协同，只看本列速度）
            speed_err = target_speed - np.array([tr.dynamics.vel[0] for tr in env.trains])
            integral += speed_err * env.dt
            der = (speed_err - prev_err) / max(env.dt, 1e-6)
            prev_err = speed_err
            actions = np.clip(0.8 * speed_err + 0.1 * integral + 0.1 * der,
                              -max_accel, max_accel)

        obs, reward, term, trunc, info = env.step(actions)
        # 逐列车钩力峰值
        for i, tr in enumerate(env.trains):
            c = np.abs(tr.dynamics._coupler_forces())
            if len(c):
                per_train_peak[i] = max(per_train_peak[i], float(np.max(c)))
                per_train_viol[i] += int(np.sum(c > env.coupler_force_limit_n))
        # 列间间距
        for i in range(1, env.num_trains):
            gap = env.trains[i - 1].dynamics.pos[-1] - env._train_heads[i]
            gap_errors.append(abs(gap - target_gap))
            if gap < 5.0:
                collision = True
        speed_errors.append(np.mean([abs(tr.dynamics.vel[0] - target_speed) for tr in env.trains]))
        if term or trunc:
            break

    return {
        'per_train_peak_kN': per_train_peak / 1e3,
        'per_train_viol': per_train_viol,
        'max_coupler_peak_kN': float(np.max(per_train_peak)) / 1e3,
        'total_violations': int(np.sum(per_train_viol)),
        'gap_err_mean': float(np.mean(gap_errors)) if gap_errors else 0.0,
        'gap_err_max': float(np.max(gap_errors)) if gap_errors else 0.0,
        'speed_err_mean': float(np.mean(speed_errors)),
        'collision': bool(collision),
    }


# ---------------------------------------------------------------------------
# 主流程
# ---------------------------------------------------------------------------
def main(seed=0, disturbance_target_accel=-0.8):
    results = {}

    print("=" * 78)
    print("诊断：车钩力是否在群组协同时才凸显？")
    print("=" * 78)

    # 工况 A：单列独立（自主制动）
    print("\n[A1] 单列独立（自主制动，无列间间距约束，无扰动）")
    a = run_single_train(enforce_coupler=True, seed=seed)
    results['A_single'] = a
    print(f"    车钩力峰值: {a['coupler_peak_kN']:.1f} kN | "
          f"超限: {a['coupler_violations']} 次 | "
          f"速度误差均值: {a['speed_err_mean']:.2f} m/s")

    # 工况 A2：单列独立 + 强制制动（归因：978kN 是扰动造成还是群组造成？）
    print("\n[A2] 单列独立 + 强制制动（同扰动 %.1f，无群组）" % disturbance_target_accel)
    a2 = run_single_train(enforce_coupler=True, seed=seed,
                          forced_brake_step=100, forced_brake_accel=disturbance_target_accel)
    results['A2_single_braked'] = a2
    print(f"    车钩力峰值: {a2['coupler_peak_kN']:.1f} kN | "
          f"超限: {a2['coupler_violations']} 次 | "
          f"速度误差均值: {a2['speed_err_mean']:.2f} m/s")

    # 工况 B：群组协同（松间距 200m，加扰动）
    print("\n[B] 群组协同 3列（松间距 200m，领航车突发减速 %.1f，间距响应）" % disturbance_target_accel)
    b = run_fleet(target_gap=200.0, disturbance_target_accel=disturbance_target_accel,
                  use_coupler_constraint=True, use_fleet_strategy=True, seed=seed)
    results['B_group_loose'] = b
    print(f"    各列车钩力峰值: {np.round(b['per_train_peak_kN'],1)} kN | "
          f"最大: {b['max_coupler_peak_kN']:.1f} | "
          f"超限: {b['total_violations']} 次 | "
          f"间距误差: {b['gap_err_mean']:.1f} m")

    # 工况 C：群组协同（紧间距 100m，加扰动）
    print("\n[C] 群组协同 3列（紧间距 100m，领航车突发减速 %.1f，间距响应）" % disturbance_target_accel)
    c = run_fleet(target_gap=100.0, disturbance_target_accel=disturbance_target_accel,
                  use_coupler_constraint=True, use_fleet_strategy=True, seed=seed)
    results['C_group_tight'] = c
    print(f"    各列车钩力峰值: {np.round(c['per_train_peak_kN'],1)} kN | "
          f"最大: {c['max_coupler_peak_kN']:.1f} | "
          f"超限: {c['total_violations']} 次 | "
          f"间距误差: {c['gap_err_mean']:.1f} m")

    # 工况 D：群组协同（紧间距，忽略车钩力策略=底层不钳制）
    print("\n[D] 群组协同 3列（紧间距 100m，忽略车钩力=底层不钳制，宋宗莹式对照）")
    d = run_fleet(target_gap=100.0, disturbance_target_accel=disturbance_target_accel,
                  use_coupler_constraint=False, use_fleet_strategy=True, seed=seed)
    results['D_group_nocoupler'] = d
    print(f"    各列车钩力峰值: {np.round(d['per_train_peak_kN'],1)} kN | "
          f"最大: {d['max_coupler_peak_kN']:.1f} | "
          f"超限: {d['total_violations']} 次 | "
          f"间距误差: {d['gap_err_mean']:.1f} m")

    # 工况 E：群组协同（无扰动，纯协同归因）
    print("\n[E] 群组协同 3列（紧间距 100m，无扰动，纯协同归因）")
    e = run_fleet(target_gap=100.0, enable_disturbance=False,
                  use_coupler_constraint=True, use_fleet_strategy=True, seed=seed)
    results['E_group_nodisturb'] = e
    print(f"    各列车钩力峰值: {np.round(e['per_train_peak_kN'],1)} kN | "
          f"最大: {e['max_coupler_peak_kN']:.1f} | "
          f"超限: {e['total_violations']} 次 | "
          f"间距误差: {e['gap_err_mean']:.1f} m")

    # 落盘 CSV（数据级留痕，规则第 8 条）
    ts = time.strftime('%Y%m%d_%H%M%S')
    out_dir = Path(__file__).parent.parent.parent / 'outputs' / 'diagnostics'
    out_dir.mkdir(parents=True, exist_ok=True)
    csv_path = out_dir / f"coupler_scene_{ts}.csv"

    with open(csv_path, 'w', newline='') as f:
        w = csv.writer(f)
        w.writerow(['seed', 'disturbance_accel', 'scenario', 'coupler_peak_kN',
                    'violations', 'gap_err_mean_m', 'speed_err_mean_mps',
                    'per_train_peak_kN_0', 'per_train_peak_kN_1', 'per_train_peak_kN_2',
                    'collision'])
        # 单列无列别信息（A1, A2）
        w.writerow([seed, '', 'A1_single', f"{a['coupler_peak_kN']:.2f}",
                    a['coupler_violations'], '', f"{a['speed_err_mean']:.2f}",
                    '', '', '', ''])
        w.writerow([seed, disturbance_target_accel, 'A2_single_braked', f"{a2['coupler_peak_kN']:.2f}",
                    a2['coupler_violations'], '', f"{a2['speed_err_mean']:.2f}",
                    '', '', '', ''])
        for name, r in [('B_group_loose', b), ('C_group_tight', c),
                        ('D_group_nocoupler', d), ('E_group_nodisturb', e)]:
            per = r['per_train_peak_kN']
            w.writerow([seed, disturbance_target_accel, name, f"{r['max_coupler_peak_kN']:.2f}",
                        r['total_violations'], f"{r['gap_err_mean']:.2f}",
                        f"{r['speed_err_mean']:.2f}",
                        f"{per[0]:.2f}", f"{per[1]:.2f}", f"{per[2]:.2f}",
                        int(r['collision'])])
    print(f"\n数据已落盘: {csv_path}")

    # 结论判断（核心归因）
    print("\n" + "=" * 78)
    print("诊断结论（归因：车钩力放大是'扰动'还是'群组'？）")
    print("=" * 78)
    print(f"A1 单列独立(无扰动)         峰值: {a['coupler_peak_kN']:6.1f} kN "
          f"({'守住' if a['coupler_violations']==0 else '超限'})")
    print(f"A2 单列独立(强制制动)       峰值: {a2['coupler_peak_kN']:6.1f} kN "
          f"({'守住' if a2['coupler_violations']==0 else '超限'})")
    print(f"E  群组协同(无扰动)         峰值: {e['max_coupler_peak_kN']:6.1f} kN "
          f"({'守住' if e['total_violations']==0 else '超限'})")
    print(f"C  群组协同(扰动)           峰值: {c['max_coupler_peak_kN']:6.1f} kN "
          f"({'守住' if c['total_violations']==0 else '超限'})")
    print(f"D  群组协同(扰动+忽略车钩力) 峰值: {d['max_coupler_peak_kN']:6.1f} kN "
          f"({'守住' if d['total_violations']==0 else '超限'})")
    print("-" * 78)
    print("归因分析：")
    print(f"  扰动效应 = C(群组扰动) vs E(群组无扰动): {c['max_coupler_peak_kN']-e['max_coupler_peak_kN']:.1f} kN")
    print(f"  扰动效应(单列) = A2(单列扰动) vs A1(单列无扰动): {a2['coupler_peak_kN']-a['coupler_peak_kN']:.1f} kN")
    print(f"  群组效应(无扰动) = E(群组) vs A1(单列): {e['max_coupler_peak_kN']-a['coupler_peak_kN']:.1f} kN")
    print(f"  群组效应(有扰动) = C(群组) vs A2(单列): {c['max_coupler_peak_kN']-a2['coupler_peak_kN']:.1f} kN")
    return results, csv_path


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='车钩力场景诊断')
    parser.add_argument('--seed', type=int, default=0)
    parser.add_argument('--disturbance_accel', type=float, default=-0.8)
    args = parser.parse_args()
    main(seed=args.seed, disturbance_target_accel=args.disturbance_accel)
