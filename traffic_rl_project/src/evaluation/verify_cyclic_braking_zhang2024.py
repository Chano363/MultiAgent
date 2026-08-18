"""
【验证】复现 Zhang2024 朔黄线长大下坡循环制动场景（仿真器正确性）。

Zhang2024（Algorithms 2024,17,190）场景：
- 线路：朔黄线 Longgong→Beidaniu 段 23,800m，坡度 -1.5~-11.4‰（已构建为 grade_profile 'shuozhou_23800'）
- 限速：最高 80 km/h（22.2 m/s），最低缓解速度 40 km/h（11.1 m/s）
- 目标：在长大下坡通过**循环制动**（制动-缓解反复）把速度控制在 [40,80] km/h 内
- 验证点：我们的动力学能否在这条真实线路上实现"循环制动、速度不超限/不低于缓解速度"

注意：Zhang2024 用 2万吨双机编组（1+108+1+108），我们的研究对象是万吨 1+0（1机+100货）。
本验证用**我们自己的万吨 1+0 编组 + Zhang2024 真实线路剖面**，验证循环制动行为正确性，
符合我们论文研究对象（万吨级 1+0）。

用法（WSL）：
    python src/evaluation/verify_cyclic_braking_zhang2024.py
输出：outputs/diagnostics/cyclic_braking_zhang2024_<ts>.csv + 打印速度轨迹/制动次数
"""

import sys
import os
import csv
import time
from pathlib import Path

sys.path.append(str(Path(__file__).parent.parent.parent))

import numpy as np

from src.environments.train_env import TrainFormationEnv
from src.train_dynamics.grade_profile import PROFILES
from src.train_dynamics.braking import AirBrakeNotch, notch_from_throttle


# Zhang2024 限速参数
V_MAX_MPS = 80.0 / 3.6      # 80 km/h 最高限速
V_MIN_MPS = 40.0 / 3.6      # 40 km/h 最低缓解速度


def cyclic_brake_controller(env, v_max=V_MAX_MPS, v_min=V_MIN_MPS,
                            brake_notch=-0.75, release_throttle=0.0):
    """循环制动规则控制器（模拟 Zhang2024 的制动-缓解循环）。

    策略：
    - 速度 > v_max 上限 → 制动（减速）
    - 速度 < v_min 下限 → 缓解（惰行/牵引）
    - 中间区间 → 维持上次动作（避免频繁切换，类似循环制动的保持）
    返回每步 throttle ∈ [-1,1]（正=牵引，负=制动），由 TrainFormationEnv.step 执行。
    """
    state = {'last_action': 0.0}

    def policy_fn():
        v = env.dynamics.vel[0]  # 机车速度
        if v >= v_max:
            state['last_action'] = brake_notch   # 超速 → 制动
        elif v <= v_min:
            state['last_action'] = release_throttle  # 低速 → 缓解
        # 中间区间保持上次动作（循环制动：制动-缓解交替，减少频繁切换）
        return np.full(env.num_vehicles, state['last_action'])
    return policy_fn


def run_cyclic_braking(grade_profile='shuozhou_23800', consist_preset='10kt_1plus0',
                       v_init_mps=65.0/3.6, max_steps=3000, dt=0.1):
    """在朔黄线剖面跑循环制动，记录速度/车钩力/制动次数。"""
    env = TrainFormationEnv({
        'consist_preset': consist_preset,
        'grade_profile': grade_profile,
        'target_speed': v_init_mps,
        'dt': dt,
        'max_steps': max_steps,
        'enable_safety': True,
    })
    obs, _ = env.reset(options={'speed': v_init_mps})
    policy = cyclic_brake_controller(env)

    t, speed, coupler, brake_cycles = [], [], [], 0
    prev_braking = False
    for step in range(max_steps):
        actions = policy()
        # 统计制动循环次数（缓解→制动 的切换）
        is_braking = float(np.min(actions)) < -0.1
        if is_braking and not prev_braking:
            brake_cycles += 1
        prev_braking = is_braking

        obs, reward, term, trunc, info = env.step(actions)
        t.append(env.steps * dt)
        speed.append(env.dynamics.vel[0])
        coupler.append(np.max(np.abs(env.dynamics._coupler_forces())) / 1e3)
        if term or trunc:
            break

    return {
        't': np.array(t), 'speed': np.array(speed), 'coupler_kN': np.array(coupler),
        'brake_cycles': brake_cycles,
        'v_max_reached': float(np.max(speed)),
        'v_min_reached': float(np.min(speed)),
        'v_final': float(speed[-1]) if speed else 0.0,
        'coupler_peak_kN': float(np.max(coupler)) if coupler else 0.0,
        'overspeed': int(np.sum(np.array(speed) > V_MAX_MPS + 0.5)),  # 超速次数
        'below_min': int(np.sum(np.array(speed) < V_MIN_MPS - 0.5)),   # 低于缓解速度次数
        'dist_km': (float(env.dynamics.pos[0]) - 0.0) / 1000.0,        # 机车位移 km
        'steps': len(t),
    }


def run_coasting_balance(grade_profile='shuozhou_23800', consist_preset='10kt_1plus0',
                         v_init_mps=65.0/3.6, max_steps=5000, dt=0.1):
    """纯惰行下坡（不牵引不制动），测列车在 -11‰ 陡坡段的平衡速度。

    对照 Zhang2024："坡道速度 68 km/h"（不制动时下坡平衡速度，需制动才能不超 80）。
    若我们的平衡速度也在此量级（60-75 km/h），则动力学正确。
    """
    env = TrainFormationEnv({
        'consist_preset': consist_preset,
        'grade_profile': grade_profile,
        'target_speed': v_init_mps,
        'dt': dt,
        'max_steps': max_steps,
        'enable_safety': True,
    })
    obs, _ = env.reset(options={'speed': v_init_mps})
    coasting = np.zeros(env.num_vehicles)  # 惰行
    t, speed, grade = [], [], []
    for step in range(max_steps):
        obs, reward, term, trunc, info = env.step(coasting)
        t.append(env.steps * dt)
        speed.append(env.dynamics.vel[0])
        grade.append(env.dynamics.grade[0])
        if term or trunc:
            break
    speed = np.array(speed)
    return {
        'v_max': float(np.max(speed)),
        'v_final': float(speed[-1]),
        'v_kmh': float(speed[-1]) * 3.6,
        'dist_km': (float(env.dynamics.pos[0]) - 0.0) / 1000.0,
        'grade_at_end': float(grade[-1]) * 1000 if grade else 0.0,  # ‰
        'steps': len(t),
    }


def main():
    print("=" * 78)
    print("验证：复现 Zhang2024 朔黄线长大下坡循环制动（万吨 1+0 编组 + 真实线路剖面）")
    print("=" * 78)
    print(f"线路剖面: shuozhou_23800 (朔黄线 23.8km, -1.5~-11.4‰)")
    print(f"限速范围: {V_MIN_MPS:.1f}~{V_MAX_MPS:.1f} m/s ({40}~{80} km/h)")
    print(f"初始速度: 65 km/h = {65/3.6:.1f} m/s")

    # 第一步：纯惰行下坡测平衡速度（对照 Zhang2024 坡道速度 ~68 km/h）
    print("\n[1] 纯惰行下坡：测平衡速度（对照 Zhang2024 坡道速度 ~68 km/h）")
    c = run_coasting_balance()
    print(f"    末速度: {c['v_kmh']:.1f} km/h | 最高: {c['v_max']*3.6:.1f} km/h | "
          f"位移: {c['dist_km']:.2f} km | 末端坡度: {c['grade_at_end']:.1f}‰")
    print(f"    ✅ 若 ~60-75 km/h 则动力学正确（Zhang2024 坡道速度 68 km/h）")

    # 第二步：循环制动
    r = run_cyclic_braking()
    print("\n[2] 循环制动（制动-缓解，限速 40-80 km/h）")
    print("-" * 78)
    print(f"循环制动次数: {r['brake_cycles']} 次")
    print(f"速度范围: {r['v_min_reached']:.1f}~{r['v_max_reached']:.1f} m/s "
          f"({r['v_min_reached']*3.6:.0f}~{r['v_max_reached']*3.6:.0f} km/h)")
    print(f"末速度: {r['v_final']*3.6:.1f} km/h | 位移: {r['dist_km']:.2f} km | 步数: {r['steps']}")
    print(f"车钩力峰值: {r['coupler_peak_kN']:.1f} kN | 超速 {r['overspeed']} 次 | 低于缓解 {r['below_min']} 次")

    # 判断是否复现 Zhang2024 行为
    print("-" * 78)
    in_range = r['v_min_reached'] >= V_MIN_MPS - 0.5 and r['v_max_reached'] <= V_MAX_MPS + 0.5
    has_cycles = r['brake_cycles'] >= 2
    print(f"速度保持在 [40,80]km/h 区间: {'✅' if in_range else '❌'} "
          f"(实际 {r['v_min_reached']*3.6:.0f}~{r['v_max_reached']*3.6:.0f})")
    print(f"出现多次循环制动: {'✅' if has_cycles else '❌'} ({r['brake_cycles']} 次)")

    # 落盘
    ts = time.strftime('%Y%m%d_%H%M%S')
    out_dir = Path(__file__).parent.parent.parent / 'outputs' / 'diagnostics'
    out_dir.mkdir(parents=True, exist_ok=True)
    csv_path = out_dir / f"cyclic_braking_zhang2024_{ts}.csv"
    with open(csv_path, 'w', newline='') as f:
        w = csv.writer(f)
        w.writerow(['t_s', 'speed_mps', 'coupler_kN'])
        for ti, si, ci in zip(r['t'], r['speed'], r['coupler_kN']):
            w.writerow([f"{ti:.1f}", f"{si:.2f}", f"{ci:.1f}"])
    print(f"数据落盘: {csv_path}")


if __name__ == '__main__':
    main()
