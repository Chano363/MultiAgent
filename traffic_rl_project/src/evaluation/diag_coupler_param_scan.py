"""【诊断】MT-2 摩擦参数敏感性扫描：μs/μd 比值 与 v_er 对朔黄23.8km 循环制动车钩力峰值的独立影响。

复用 fig3（plot_physical_curves.run_cyclic_shuozhou）协议：10kt_1plus0 + shuozhou_23800 +
15000 步 + TrainLowLevelController 规则循环制动（80↔40km/h，SERVICE -0.8 / 牵引 0.5）+ enable_safety=True。
通过 dataclasses.replace 注入单参数覆盖，记录峰值车钩力（kN）随参数的单调性/敏感段。

用法：python src/evaluation/diag_coupler_param_scan.py
输出：标准输出表格 + outputs/coupler_param_scan/ 下 CSV（带运行命令/seed 说明）。
"""

import sys
import csv
from dataclasses import replace
from pathlib import Path

sys.path.append(str(Path(__file__).parent.parent.parent))

import numpy as np

from src.train_dynamics.params import CouplerParams
from src.environments.train_env import TrainFormationEnv
from src.controllers.low_level_controller import TrainLowLevelController
from src.train_dynamics.braking import AirBrakeNotch


def make_env(max_steps=15000, init_speed=65.0 / 3.6):
    env = TrainFormationEnv({
        'consist_preset': '10kt_1plus0',
        'grade_profile': 'shuozhou_23800',
        'max_steps': max_steps,
        'init_speed': init_speed,
        'enable_safety': True,
    })
    return env


def run_cycle(ov: dict, max_steps=15000, init_speed=65.0 / 3.6, dt=0.1):
    """运行一次 fig3 循环制动，返回 (峰值车钩力 kN, 末速 km/h)。"""
    env = make_env(max_steps=max_steps, init_speed=init_speed)
    n_veh = env.num_vehicles
    # 注入单参数覆盖（其余保持官方 MT-2 默认）
    env.dynamics.coupler = replace(CouplerParams(), **ov)
    # 【关键】向量化力计算读缓存的 self._cp，覆盖后必须 set_couplers(None)
    # 重建参数数组（2026-09-06 修正：先前扫描峰值恒 1403.6 因 override 未生效）。
    env.dynamics.set_couplers(None)
    ctrl = TrainLowLevelController(num_vehicles=n_veh, dt=dt,
                                   coupler_force_limit_n=env.coupler_force_limit_n,
                                   enforce_coupler=True)
    ctrl.reset()
    V_MAX = 80.0 / 3.6
    V_MIN = 40.0 / 3.6
    peak = 0.0
    v_log = []
    for k in range(max_steps):
        c = env.dynamics.coupler_interface_forces()
        if len(c):
            peak = max(peak, float(np.max(np.abs(c))) / 1e3)
        actions = ctrl.get_action_cyclic_braking(env, V_MAX, V_MIN,
                                                 brake_notch=-0.8, release_throttle=0.5)
        env.step(actions)
        v_log.append(env.dynamics.vel[0])
    return peak, v_log[-1] * 3.6


def main():
    outdir = Path(__file__).resolve().parent.parent.parent / 'outputs' / 'coupler_param_scan'
    outdir.mkdir(parents=True, exist_ok=True)

    # 基线（官方默认）
    base = CouplerParams()
    print('=' * 84)
    print('MT-2 摩擦敏感性扫描：朔黄23.8km 循环制动 车钩力峰值 (kN)')
    print(f'基线 friction_static_n={base.friction_static_n/1e3:.0f}kN, '
          f'friction_n={base.friction_n/1e3:.0f}kN, v_er={base.friction_v_er} m/s')
    print('=' * 84)

    rows = []
    # ---- μs/μd 比值扫描（friction_v_er 固定 0.2）----
    print(f"\n[A] μs/μd 比值（静/动摩擦）@v_er={base.friction_v_er}")
    print(f"  {'μs/μd':<7} {'静摩擦(kN)':<10} {'峰值(kN)':<10} {'末速(km/h)':<10}")
    for ratio in [1.2, 1.3, 1.5, 1.8]:
        sn = base.friction_n * ratio
        peak, vf = run_cycle({'friction_static_n': sn,
                              'friction_v_er': base.friction_v_er})
        print(f"  {ratio:<7} {sn/1e3:<10.0f} {peak:<10.1f} {vf:<10.1f}")
        rows.append({'param': 'mus/mud', 'value': ratio,
                     'statickn': round(sn/1e3, 1), 'peakkn': round(peak, 1),
                     'vfinal': round(vf, 2)})

    # ---- v_er 扫描（μs/μd 固定 1.5）----
    print(f"\n[B] v_er（动静摩擦转换速度）@μs/μd=1.5")
    print(f"  {'v_er(m/s)':<9} {'峰值(kN)':<10} {'末速(km/h)':<10}")
    for ver in [0.05, 0.1, 0.2, 0.5]:
        peak, vf = run_cycle({'friction_static_n': base.friction_n * 1.5,
                              'friction_v_er': ver})
        print(f"  {ver:<9} {peak:<10.1f} {vf:<10.1f}")
        rows.append({'param': 'v_er', 'value': ver,
                     'statickn': round(base.friction_n * 1.5 / 1e3, 1),
                     'peakkn': round(peak, 1), 'vfinal': round(vf, 2)})

    # 带时间戳输出，避免覆盖（先前一次为 override 未生效的无效数据 1403.6 恒值）
    stamp = '2026-09-06_fix'
    csv_path = outdir / f'coupler_param_scan_{stamp}.csv'
    with open(csv_path, 'w', newline='') as f:
        w = csv.DictWriter(f, fieldnames=['param', 'value', 'statickn', 'peakkn', 'vfinal'])
        w.writeheader()
        w.writerows(rows)
    print(f"\n结果已存: {csv_path}")

    # 峰值对 log(param) 的一阶影响（归一化到基线 1.5 / 0.2）——供 Morris 一阶敏度"骨架"
    print("\n[归一化一阶影响] 相对基线（μs/μd=1.5, v_er=0.2）的峰值变化 (kN)")
    base_peak = next(r for r in rows if r['param'] == 'mus/mud' and r['value'] == 1.5)['peakkn']
    for r in rows:
        d = r['peakkn'] - base_peak
        print(f"  {r['param']}={r['value']:<5} -> Δ{d:+.1f} kN  ({100*d/base_peak:+.1f}%)")


if __name__ == '__main__':
    main()