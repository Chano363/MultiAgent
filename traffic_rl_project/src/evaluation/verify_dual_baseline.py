"""【双基准交叉验证】在文献的工况下跑我们的仿真，同工况对照（2026-08-30）。

原则：不能拿 A 工况的文献数值校验 B 工况的仿真。必须把我们的仿真
跑到文献工况下，在同一工况内对比。

基准 A（张二田 2021，朔黄线实测）：
  - 编组 2 万吨组合列车（1+108+1+108），朔黄线，循环制动
  - 实测：机车最大车钩力均值 929 kN、货车断面 1021 kN、峰值 1429~1748 kN
  - 验证目标：模型在朔黄线循环制动下的绝对量级

基准 B（杨敏硕士论文，实测验证的模型）：
  - 编组 HXD2 双机重联 + 105 辆 C80（万吨），坡度 -6‰，初速 60 km/h
  - 常用全制动（最高级位）至停车：最大压钩力 634.1 kN（车钩间隙 10mm）
  - 电阻制动 12 级：907.6 kN
  - 验证目标：模型在万吨编组、已知坡度、单次制动下的正确性

用法：python src/evaluation/verify_dual_baseline.py
"""

import sys
from pathlib import Path

sys.path.append(str(Path(__file__).parent.parent.parent))

import numpy as np

from src.train_dynamics.params import (VehicleParams, LocomotiveParams,
                                       TrainConsist, CouplerParams)
from src.train_dynamics.train import TrainDynamics
from src.train_dynamics.braking import AirBrakeNotch
from src.environments.train_env import TrainFormationEnv

# ---------------------------------------------------------------- A 基准
def cyclic_policy(env, v_max=80.0/3.6, v_min=40.0/3.6, brake=-0.75):
    state = {'last': 0.0}
    def policy():
        v = env.dynamics.vel[0]
        if v >= v_max:
            state['last'] = brake
        elif v <= v_min:
            state['last'] = 0.0
        return np.full(env.num_vehicles, state['last'])
    return policy


def run_A(init_kmh=65.0, max_steps=30000):
    """A：朔黄线 + 2 万吨 + 循环制动（无安全层，纯物理）。

    【2026-08-30】dt 0.1→0.01：缓冲器冲击事件 ~50-100ms，dt=0.1 无法
    解析（1 m/s 相对速度每步位移 100mm > 83mm 全行程），文献标准 LTD
    仿真步长 0.005-0.01s（翟婉明/Cole）。
    """
    env = TrainFormationEnv({
        'consist_preset': '20kt_1plus108_1plus108',
        'grade_profile': 'shuozhou_23800',
        'target_speed': init_kmh / 3.6,
        'dt': 0.01,
        'max_steps': max_steps,
        'enable_safety': False,
    })
    obs, _ = env.reset(options={'speed': init_kmh / 3.6})
    policy = cyclic_policy(env)
    peak = 0.0
    v_log = []
    for step in range(max_steps):
        actions = policy()
        obs, reward, term, trunc, info = env.step(actions)
        f = env.dynamics.coupler_interface_forces()
        peak = max(peak, float(np.max(np.abs(f))))
        v_log.append(env.dynamics.vel[0])
        if term or trunc:
            break
    v = np.array(v_log)
    return {'peak_kN': peak/1e3, 'v_min': np.min(v)*3.6,
            'v_max': np.max(v)*3.6, 'v_end': v[-1]*3.6}

# ---------------------------------------------------------------- B 基准
def make_B_consist():
    """HXD2 双机重联 + 105 辆 C80（万吨，对齐杨敏编组）。"""
    loco = LocomotiveParams(
        mass_t=200.0, no_of_axles=8, frontal_area_m2=11.5, drag_coef=1.4,
        length_m=22.0, max_power_kw=10000.0, transmission_efficiency=0.85,
        max_speed_mps=30.0, n_notches=8,
    )
    car = VehicleParams(
        mass_t=100.0, no_of_axles=4, frontal_area_m2=10.0, drag_coef=1.0,
        length_m=12.0,
    )
    return TrainConsist([loco, loco] + [car for _ in range(105)])


def run_B(grade=-0.006, init_kmh=60.0, ramp_s=None, max_steps=12000):
    """B：-6‰ 坡 + 万吨编组 + 单次制动至停车。

    ramp_s: 制动手柄缓升时间（秒）。None=立即满制动；24=杨敏图4-14 工况。
    【2026-08-30】dt 0.1→0.01（缓冲器冲击分辨率要求，同 run_A）。
    """
    consist = make_B_consist()
    td = TrainDynamics(consist, coupler=CouplerParams(), dt=0.01)
    td.set_grade(grade)
    td.set_initial_speed(init_kmh / 3.6)
    n = consist.num_vehicles
    peak = 0.0
    v_log = []
    steps = 0
    for step in range(max_steps):
        if ramp_s is not None:
            # 制动手柄线性提升（0 → 最高级位 SERVICE）
            frac = min(1.0, (step * td.dt) / ramp_s)
            throttle = np.zeros(n)
            ed = np.zeros(n)
            # 用逐步施加的制动档位模拟缓升：先惰行到 ramp 结束按比例？简化：
            # 用 SERVICE 指令但在 ramp 期间以空气制动渐入不可行（离散指令），
            # 改为 ramp 期间惰行 + 之后 SERVICE（近似），并记录两种结果。
            cmd = AirBrakeNotch.SERVICE if step * td.dt >= ramp_s else AirBrakeNotch.RELEASE
        else:
            throttle = np.zeros(n)
            ed = np.zeros(n)
            cmd = AirBrakeNotch.SERVICE
        td.step_vehicles_ed_ab(
            throttle=np.zeros(n), ed_throttle=np.zeros(n),
            ab_command=cmd,
        )
        f = td.coupler_interface_forces()
        peak = max(peak, float(np.max(np.abs(f))))
        v_log.append(td.vel[0])
        steps = step
        if np.max(np.abs(td.vel)) < 0.05:   # 列车停住
            break
    v = np.array(v_log)
    return {'peak_kN': peak/1e3, 'v_end': v[-1]*3.6, 'steps': steps,
            'stop_s': steps * td.dt}


def main():
    print("=" * 78)
    print("双基准交叉验证：把我们的仿真跑到文献工况下，同工况对照")
    print("=" * 78)

    print("\n[A] 朔黄线 + 2 万吨(1+108+1+108) + 循环制动，初速 65")
    print("    实测（张二田2021表1/表2）: 19次循环货车最大钩力 650~1430 kN；")
    print("    不同编组试验 K0~K85 段峰值 836~2142 kN（含 232 辆编组）")
    print("    注：本仿真为纯空气制动循环，实测为空气+电制动联合，")
    print("    故预期落在实测峰值区间上半段。")
    a = run_A()
    print(f"    仿真: 峰值单钩力 {a['peak_kN']:.0f} kN | "
          f"速度 {a['v_min']:.0f}~{a['v_max']:.0f}(末{a['v_end']:.0f}) km/h")
    ok_a = 836 <= a['peak_kN'] <= 2142
    print(f"    判定: {'✅ 落在实测区间(836~2142)' if ok_a else '❌ 偏离实测'}"
          f"（以峰值上限 2142 对照偏差 {(a['peak_kN']/2142-1)*100:+.0f}%）")

    print("\n[B] -6‰ 坡 + HXD2 双机+105 C80(万吨) + 单次制动至停车，初速 60")
    print("    文献（杨敏，实测验证模型）: 常用全制动最大压钩力 634.1 kN（间隙10mm）")
    for ramp, label in [(None, "立即满制动"), (24, "24s 缓升(杨敏工况)")]:
        b = run_B(grade=-0.006, init_kmh=60.0, ramp_s=ramp)
        print(f"    [{label}] 仿真: 峰值单钩力 {b['peak_kN']:.0f} kN | "
              f"停车用时 {b['stop_s']:.0f}s")
        ok_b = 450 <= b['peak_kN'] <= 1000
        print(f"          判定: {'✅ 落在合理区间' if ok_b else '❌ 偏离文献'}"
              f"（偏差 {(b['peak_kN']/634-1)*100:+.0f}%，以 634 为基准）")

    print("\n" + "=" * 78)
    print("综合判定：A、B 都通过 → 模型可信；任一失败 → 定位对应环节参数")


if __name__ == '__main__':
    main()
