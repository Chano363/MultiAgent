"""【验证】编组规模效应：同一仿真器下 1 万吨 vs 2 万吨车钩力对比（2026-08-30）。

目标：验证仿真器能否代表"1 万吨 1+0 重载列车"。

背景：文献实测数据（张二田，朔黄线）：
- 2 万吨组合列车（1+108+1+108）正常循环制动：机车最大车钩力均值 929 kN、货车断面 1021 kN
- 我们的仿真（1 万吨 1+0，1 机 + 100 货）循环制动：车钩力 527/597 kN

用户澄清：527/597 是 1 万吨编组的结果，不能直接与 2 万吨实测比"偏低 40%"。
本验证要回答：差异是否由编组规模造成（物理规律）？即：
- 同一模型、同一参数、同一线路剖面、同一制动规则下
- 1 万吨 → 车钩力应显著低于 2 万吨
- 2 万吨 → 应接近实测 929-1021 kN
- 若成立 → 仿真器模型正确，1 万吨 527 kN 是合理值，能代表 1 万吨 1+0 重载列车

同时验证物理特征（王宏宇 2020 万吨循环制动规律）：
- 最大车钩力出现在列车中部
- 最大车钩力出现在制动缓解后
- 初始制动速度对纵向冲动影响小

用法（WSL）：
    python src/evaluation/verify_consist_scaling.py
输出：outputs/diagnostics/consist_scaling_<ts>.csv + 打印对比
"""

import sys
import os
import csv
import time
from pathlib import Path

sys.path.append(str(Path(__file__).parent.parent.parent))

import numpy as np

from src.environments.train_env import TrainFormationEnv


# ---------- 循环制动控制 ----------

def cyclic_brake_controller(env, v_max=80.0 / 3.6, v_min=40.0 / 3.6,
                            brake_notch=-0.75, release_throttle=0.0):
    """循环制动规则控制器（制动-缓解交替）。"""
    state = {'last_action': 0.0}

    def policy_fn():
        v = env.dynamics.vel[0]
        if v >= v_max:
            state['last_action'] = brake_notch
        elif v <= v_min:
            state['last_action'] = release_throttle
        return np.full(env.num_vehicles, state['last_action'])
    return policy_fn


def run_cyclic(consist_preset, v_init_mps=65.0 / 3.6, max_steps=3000):
    """跑朔黄线循环制动，记录峰值单钩断面力。

    工程级口径：
    - enable_safety=False（验证纯物理车钩力，不被安全层钳制掩盖）
    - 单钩断面力用 dynamics.coupler_interface_forces()（与实测 929/1021 kN 同口径）
    - 峰值取全程最大 |单钩力|，并记录其列车位置（验证"中部最大"规律）
    """
    env = TrainFormationEnv({
        'consist_preset': consist_preset,
        'grade_profile': 'shuozhou_23800',
        'target_speed': v_init_mps,
        'dt': 0.1,
        'max_steps': max_steps,
        'enable_safety': False,   # 纯物理验证：暴露真实车钩力峰值
    })
    obs, _ = env.reset(options={'speed': v_init_mps})
    policy = cyclic_brake_controller(env)

    n = env.num_vehicles
    coupler_peak = 0.0
    peak_at_release = 0.0   # 缓解后峰值车钩力（王宏宇：缓解后最大）
    peak_idx = 0            # 峰值车钩位置
    peak_step = 0
    records = []
    prev_braking = False
    brake_cycles = 0

    for step in range(max_steps):
        actions = policy()
        is_braking = float(np.min(actions)) < -0.1
        if is_braking and not prev_braking:
            brake_cycles += 1
        release_window = (not prev_braking) and is_braking   # 缓解→制动切换窗口
        prev_braking = is_braking

        obs, reward, term, trunc, info = env.step(actions)

        # 单钩断面力（与动力学同源，口径=实测）
        f_adj = env.dynamics.coupler_interface_forces()
        f_abs = np.abs(f_adj) / 1e3                     # kN
        pk = float(np.max(f_abs)) if len(f_abs) else 0.0
        if pk > coupler_peak:
            coupler_peak = pk
            peak_idx = int(np.argmax(f_abs))
            peak_step = step
        if release_window:
            peak_at_release = max(peak_at_release, pk)
        records.append((step * env.dt, pk, 1.0 if is_braking else 0.0))
        if term or trunc:
            break

    return {
        'n_vehicles': n,
        'total_mass_t': sum(v.mass_t for v in env.dynamics.consist.vehicles),
        'coupler_peak_kN': coupler_peak,
        'peak_idx': peak_idx,
        'peak_frac': peak_idx / max(n - 1, 1),
        'peak_step': peak_step,
        'peak_at_release_kN': peak_at_release,
        'brake_cycles': brake_cycles,
        'dist_km': float(env.dynamics.pos[0]) / 1000.0,
        'records': records,
    }


def main():
    print("=" * 78)
    print("工程级对照：编组规模效应 + 车钩力对照实测")
    print("实测基准（张二田 2021，朔黄线 2 万吨组合列车正常循环制动）：")
    print("  机车最大车钩力均值 929 kN、货车断面 1021 kN、峰值 1429/1748 kN")
    print("=" * 78)

    # 工程级：多个初速 seed，峰值取保守最大值（最不利工况）
    seeds_kmh = [60.0, 65.0, 70.0]
    results = {}
    for name in ['10kt_1plus0', '20kt_1plus108_1plus108']:
        peaks = []
        r_best = None
        for vk in seeds_kmh:
            r = run_cyclic(name, v_init_mps=vk / 3.6)
            peaks.append(r['coupler_peak_kN'])
            if r_best is None or r['coupler_peak_kN'] > r_best['coupler_peak_kN']:
                r_best = r
        results[name] = {'peaks': peaks, 'max': max(peaks), 'r': r_best}
        print(f"\n[{name}] {r_best['n_vehicles']} 节, {r_best['total_mass_t']:.0f} t")
        print(f"  循环制动次数: {r_best['brake_cycles']} | 位移: {r_best['dist_km']:.2f} km")
        print(f"  峰值车钩力（3 seed: {', '.join(f'{p:.0f}' for p in peaks)}）: "
              f"保守最大 {max(peaks):.0f} kN")
        print(f"    峰值位置: 列车 {r_best['peak_frac']*100:.0f}% 处"
              f"  ({'✅ 中部' if 0.3 <= r_best['peak_frac'] <= 0.7 else '⚠️ 非中部'})")
        print(f"    缓解后峰值: {r_best['peak_at_release_kN']:.0f} kN"
              f"  ({'✅ 缓解后冲击显著' if r_best['peak_at_release_kN'] >= r_best['coupler_peak_kN']*0.6 else '⚠️ 非缓解后'})")

    print("\n" + "=" * 78)
    r1, r2 = results['10kt_1plus0'], results['20kt_1plus108_1plus108']
    print("工程判定（对照实测）：")
    print(f"  1 万吨仿真峰值: {r1['max']:.0f} kN")
    print(f"  2 万吨仿真峰值: {r2['max']:.0f} kN")
    print(f"  实测 2 万吨正常循环制动: 929~1021 kN（峰值 1429~1748）")
    print(f"  2 万吨仿真/实测: {r2['max']/975:.2f}×（正常循环均值 975 基准）")
    ratio = r2['max'] / max(r1['max'], 1e-6)
    print(f"  编组规模效应（2万/1万）: {ratio:.2f}×"
          f"  ({'✅ 随编组增长' if ratio > 1.2 else '⚠️ 无显著增长'})")
    # 判定：2万吨仿真应落在实测正常循环区间内（允许 ±40%）
    lo, hi = 929 * 0.6, 1021 * 1.4
    ok = lo <= r2['max'] <= hi
    print(f"  2 万吨仿真落在实测区间 [{lo:.0f}, {hi:.0f}]: {'✅ 通过' if ok else '❌ 需标定'}")
    if not ok:
        print(f"  → 偏差 {(r2['max']/975-1)*100:+.0f}%，需调整缓冲器参数（刚度/阻尼）")

    # 落盘（单钩断面力轨迹）
    ts = time.strftime('%Y%m%d_%H%M%S')
    out_dir = Path(__file__).parent.parent.parent / 'outputs' / 'diagnostics'
    out_dir.mkdir(parents=True, exist_ok=True)
    csv_path = out_dir / f"consist_scaling_{ts}.csv"
    with open(csv_path, 'w', newline='') as f:
        w = csv.writer(f)
        w.writerow(['consist', 'init_kmh', 't_s', 'peak_kN', 'braking'])
        for name, rd in results.items():
            vk = seeds_kmh[0]
            for (t, pk, br) in rd['r']['records']:
                w.writerow([name, vk, t, pk, br])
    print(f"\n数据落盘: {csv_path}")


if __name__ == '__main__':
    main()
