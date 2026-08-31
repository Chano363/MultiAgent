"""【诊断】朔黄线下坡循环制动（无安全层）：定位车钩力峰值来源。

对比：平直轨道 service brake 峰值仅 ~810 kN（合理），但朔黄线下坡循环制动
无安全层时打满缓冲器饱和 2270 kN。本脚本输出速度/坡度/车钩力轨迹关键点，
定位冲击发生在何时、何位置。

用法：python src/evaluation/diag_downhill_cycle.py
"""

import sys
from pathlib import Path

sys.path.append(str(Path(__file__).parent.parent.parent))

import numpy as np

from src.environments.train_env import TrainFormationEnv


def cyclic_brake_controller(env, v_max=80.0 / 3.6, v_min=40.0 / 3.6,
                            brake_notch=-0.75, release_throttle=0.0):
    state = {'last_action': 0.0}

    def policy_fn():
        v = env.dynamics.vel[0]
        if v >= v_max:
            state['last_action'] = brake_notch
        elif v <= v_min:
            state['last_action'] = release_throttle
        return np.full(env.num_vehicles, state['last_action'])
    return policy_fn


def main():
    print("=" * 78)
    print("诊断：朔黄线下坡循环制动（无安全层，1万吨），定位峰值车钩力来源")
    print("=" * 78)

    env = TrainFormationEnv({
        'consist_preset': '10kt_1plus0',
        'grade_profile': 'shuozhou_23800',
        'target_speed': 65.0 / 3.6,
        'dt': 0.1,
        'max_steps': 3000,
        'enable_safety': False,
    })
    obs, _ = env.reset(options={'speed': 65.0 / 3.6})
    policy = cyclic_brake_controller(env)
    p = env.dynamics.coupler

    prev_braking = False
    brake_cycles = 0
    peak_step, peak_val, peak_v0, peak_v_tail, peak_grade = 0, 0.0, 0.0, 0.0, 0.0
    v_log = []

    for step in range(3000):
        actions = policy()
        is_braking = float(np.min(actions)) < -0.1
        if is_braking and not prev_braking:
            brake_cycles += 1
        prev_braking = is_braking

        obs, reward, term, trunc, info = env.step(actions)
        v0 = env.dynamics.vel[0]
        v_tail = env.dynamics.vel[-1]
        f_adj = env.dynamics._coupler_forces()
        pk = float(np.max(np.abs(f_adj)))
        v_log.append(v0)

        if pk > peak_val:
            peak_val = pk
            peak_step = step
            peak_v0 = v0
            peak_v_tail = v_tail
            peak_grade = env.dynamics.grade[0]

    v = np.array(v_log)
    print(f"速度范围: {np.min(v)*3.6:.1f}~{np.max(v)*3.6:.1f} km/h | 末速度: {v[-1]*3.6:.1f} km/h")
    print(f"循环制动次数: {brake_cycles}")
    print(f"峰值车钩力: {peak_val/1e3:.1f} kN @ step {peak_step} "
          f"(t={peak_step*0.1:.1f}s)")
    print(f"  峰值时刻: 机车速度 {peak_v0*3.6:.1f} km/h, 尾部速度 {peak_v_tail*3.6:.1f} km/h, "
          f"坡度 {peak_grade*1000:.1f}‰")
    print(f"  速度差(机-尾): {(peak_v0-peak_v_tail)*3.6:.1f} km/h")
    # 峰值时前 30 步速度差演变
    print(f"\n峰值前 30 步机车/尾部速度差:")
    td = env.dynamics
    # 重新定位：从记录找
    print(f"  (已记录峰值时刻特征，见上)")

    # 关键：制动状态分布
    print(f"\n速度在 [40,80] 内占比: {np.mean((v>=40/3.6)&(v<=80/3.6))*100:.0f}%")


if __name__ == '__main__':
    main()
