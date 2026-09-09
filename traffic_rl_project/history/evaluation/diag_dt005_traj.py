"""【诊断】dt=0.05 循环制动速度/动作轨迹，理解为何 62-73 km/h 稳定不循环。"""

import sys
from pathlib import Path

sys.path.append(str(Path(__file__).parent.parent.parent))

import numpy as np

from src.environments.train_env import TrainFormationEnv


def run(dt, n_steps, label, damping=None):
    env = TrainFormationEnv({
        'consist_preset': '10kt_1plus0',
        'grade_profile': 'shuozhou_23800',
        'target_speed': 65.0 / 3.6,
        'dt': dt,
        'max_steps': n_steps,
        'enable_safety': False,
    })
    if damping is not None:
        from src.train_dynamics.params import CouplerParams
        old = env.dynamics.coupler
        env.dynamics.coupler = CouplerParams(
            stiffness=old.stiffness, damping=damping,
            coupler_gap_m=old.coupler_gap_m, max_impulse_n=old.max_impulse_n)
    obs, _ = env.reset(options={'speed': 65.0 / 3.6})

    state = {'last': 0.0}
    vmax, vmin = 80.0/3.6, 40.0/3.6
    peak = 0.0
    peak_unsat = 0.0
    log = []
    cycles = 0
    prev_brake = False
    p = env.dynamics.coupler
    for step in range(n_steps):
        v = env.dynamics.vel[0]
        if v >= vmax:
            state['last'] = -0.75
        elif v <= vmin:
            state['last'] = 0.0
        actions = np.full(env.num_vehicles, state['last'])
        is_brake = state['last'] < -0.1
        if is_brake and not prev_brake:
            cycles += 1
        prev_brake = is_brake
        obs, reward, term, trunc, info = env.step(actions)
        pos = env.dynamics.pos; vel = env.dynamics.vel
        e = (pos[1:] - pos[:-1]) + p.free_length_m
        e_eff = e if p.coupler_gap_m <= 0 else np.where(
            e > p.coupler_gap_m, e - p.coupler_gap_m,
            np.where(e < -p.coupler_gap_m, e + p.coupler_gap_m, 0.0))
        dv = vel[:-1] - vel[1:]
        f_adj = p.stiffness * e_eff - p.damping * dv
        peak_unsat = max(peak_unsat, float(np.max(np.abs(f_adj))))
        if p.max_impulse_n > 0:
            f_adj = np.clip(f_adj, -p.max_impulse_n, p.max_impulse_n)
        peak = max(peak, float(np.max(np.abs(f_adj))))
        # 每 100 步记录关键帧
        if step % 100 == 0 or (is_brake and not prev_brake):
            log.append((step*dt, v*3.6, state['last'],
                        env.dynamics.vel[-1]*3.6, env.dynamics.grade[0]*1000,
                        peak_unsat/1e3))
        if term or trunc:
            break
    print(f"\n===== {label} (dt={dt}, {len(log)*0+int(log[-1][0]) if log else 0:.0f}s) =====")
    print(f"循环次数: {cycles} | 末速: {env.dynamics.vel[0]*3.6:.1f} km/h | "
          f"位移: {env.dynamics.pos[0]/1000:.2f} km")
    print(f"饱和峰值: {peak/1e3:.1f} kN | 未饱和峰值: {peak_unsat/1e3:.1f} kN")
    print("t(s)  机速(km/h)  动作   尾速(km/h)  坡度‰  未饱和峰(kN)")
    for row in log:
        print(f"{row[0]:6.1f}  {row[1]:9.1f}  {row[2]:+.2f}  {row[3]:9.1f}  {row[4]:6.1f}  {row[5]:8.1f}")
    return peak_unsat


def main():
    print("=" * 78)
    print("修复验证：更小 dt + 接近临界阻尼（ζ≈0.5-1.0）能否稳定制动瞬态")
    print(f"当前: k=5e6, c=5e4 → ζ={5.0e4/(2*(5.0e6*1.0e5)**0.5):.3f} (严重欠阻尼)")
    print(f"临界阻尼: c_crit=2√(km)={2*(5.0e6*1.0e5)**0.5:.2e} N·s/m")
    print("=" * 78)
    # 关键组合：dt=0.02 + 大阻尼（接近临界的一半）
    for dt, c in [(0.02, 5.0e4), (0.02, 2.0e5), (0.02, 5.0e5),
                  (0.05, 5.0e5), (0.05, 1.0e6)]:
        try:
            run(dt, int(400/dt), f"dt={dt}, c={c:.0e}", damping=c)
        except Exception as e:
            print(f"dt={dt}, c={c:.0e}: 异常 {type(e).__name__}")


if __name__ == '__main__':
    main()
