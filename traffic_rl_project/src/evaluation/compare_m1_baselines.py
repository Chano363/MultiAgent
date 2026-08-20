"""论文对比矩阵（M1）：分层环境下 初始65/朔黄线/缓解波，对比 M1 vs 纯第1层 vs 惰行。

- M1（分层MAPPO）：第1层策略控速 + RL学协同调整 δ
- 纯第1层（δ=0）：第1层策略控速，无协同（隔离RL协同增量）
- 惰行：完全惰行（无控制）
指标：reward/车钩力/速度区间/间距/能耗/循环制动次数。
"""
import sys
import time
import numpy as np
from pathlib import Path

sys.path.append(str(Path(__file__).parent.parent.parent))

from src.environments.train_fleet_env import TrainFleetEnv
from src.algorithms.mappo_agent import MAPPOAgent

INIT_SPEED = 65.0 / 3.6  # 论文标准初始（Zhang2024 V0=65）
MAX_STEPS = 1500


def make_env():
    return TrainFleetEnv({
        'num_trains': 3, 'consist_preset': '10kt_1plus0',
        'grade_profile': 'shuozhou_23800',
        'v_max': 80.0 / 3.6, 'v_min': 40.0 / 3.6,
        'target_gap': 100.0, 'headway_s': 5.0,
        'max_steps': MAX_STEPS, 'max_accel': 1.0,
        'enable_disturbance': False, 'use_coupler_constraint': True,
        'hierarchical': True,
    })


def evaluate(env, action_fn):
    obs, _ = env.reset(options={'speed': INIT_SPEED})
    done = False
    step = 0
    cum_r = 0.0
    peak_coupler = 0.0
    viol = 0
    speeds = []
    gaps = []
    over = under = 0
    energy = 0.0
    n_brakes = 0
    prev_v = None
    braking = False
    while not done and step < MAX_STEPS:
        a = action_fn(obs)
        obs, r, term, trunc, info = env.step(a)
        done = term or trunc
        cum_r += r
        peak_coupler = max(peak_coupler, info['coupler_force_peak'])
        viol += info['coupler_limit_violations']
        vs = [tr.dynamics.vel[0] for tr in env.trains]
        speeds.extend(vs)
        over += sum(1 for v in vs if v > env.v_max)
        under += sum(1 for v in vs if v < env.v_min)
        if env.num_trains > 1:
            g1 = env.trains[0].dynamics.pos[-1] - env._train_heads[1]
            g2 = env.trains[1].dynamics.pos[-1] - env._train_heads[2]
            gaps.append(min(g1, g2))
        energy += info.get('energy_kwh', 0.0)
        # 循环制动次数（列0：速度下降→上升 切换）
        v0 = vs[0]
        if prev_v is not None and v0 < prev_v - 0.5 and not braking:
            braking = True
        elif braking and v0 > prev_v + 0.5:
            n_brakes += 1
            braking = False
        prev_v = v0
        step += 1
    speeds = np.array(speeds)
    gaps = np.array(gaps)
    return {
        'reward': cum_r,
        'peak_coupler_kN': peak_coupler / 1e3,
        'violations': viol,
        'speed_mean_kmh': speeds.mean() * 3.6,
        'speed_range_kmh': (speeds.min() * 3.6, speeds.max() * 3.6),
        'over_vmax_pct': over / len(speeds) * 100,
        'under_vmin_pct': under / len(speeds) * 100,
        'gap_range_m': (gaps.min(), gaps.max()) if len(gaps) else (0, 0),
        'energy_kwh': energy,
        'n_brakes': n_brakes,
        'steps': step,
    }


def main():
    ckpt = sys.argv[1] if len(sys.argv) > 1 else 'outputs/checkpoints/mappo_fleet_best_cp_seed0.pt'
    agent = MAPPOAgent(num_drones=3, obs_per_drone=11, act_per_drone=1, device='cuda')
    agent.load(ckpt)
    agent.policy.eval()

    print(f"对比矩阵 M1（论文标准初始65km/h, 朔黄线, 缓解波, {MAX_STEPS}步）")
    print(f"checkpoint: {ckpt}\n")
    header = f"{'方法':<22}{'Reward':>10}{'车钩力kN':>10}{'超限':>5}{'平均km/h':>9}{'超上限%':>8}{'低下限%':>8}{'间距m':>12}{'循环制动':>8}{'能耗kWh':>8}"
    print(header)
    print('-' * len(header))

    # M1：分层MAPPO（RL学协同δ）
    env = make_env()
    m1 = evaluate(env, lambda obs: agent.select_actions(obs.flatten(), deterministic=True)[0].reshape(3, 1))
    print(f"{'M1 分层MAPPO':<22}{m1['reward']:>10.0f}{m1['peak_coupler_kN']:>10.0f}{m1['violations']:>5}{m1['speed_mean_kmh']:>9.1f}"
          f"{m1['over_vmax_pct']:>8.1f}{m1['under_vmin_pct']:>8.1f}{m1['gap_range_m']!s:>12}{m1['n_brakes']:>8}{m1['energy_kwh']:>8.1f}")

    # 纯第1层（δ=0，无协同）
    env2 = make_env()
    l1 = evaluate(env2, lambda obs: np.zeros(3))
    print(f"{'纯第1层(δ=0)':<22}{l1['reward']:>10.0f}{l1['peak_coupler_kN']:>10.0f}{l1['violations']:>5}{l1['speed_mean_kmh']:>9.1f}"
          f"{l1['over_vmax_pct']:>8.1f}{l1['under_vmin_pct']:>8.1f}{l1['gap_range_m']!s:>12}{l1['n_brakes']:>8}{l1['energy_kwh']:>8.1f}")

    # 惰行（非分层环境，完全无控制）
    env3 = TrainFleetEnv({
        'num_trains': 3, 'consist_preset': '10kt_1plus0',
        'grade_profile': 'shuozhou_23800',
        'v_max': 80.0 / 3.6, 'v_min': 40.0 / 3.6,
        'target_gap': 100.0, 'headway_s': 5.0,
        'max_steps': MAX_STEPS, 'max_accel': 1.0,
        'enable_disturbance': False, 'use_coupler_constraint': True,
        'hierarchical': False,  # 非分层：完全无第1层控速，action 直接生效
    })
    coast = evaluate(env3, lambda obs: np.zeros(3))
    print(f"{'惰行':<22}{coast['reward']:>10.0f}{coast['peak_coupler_kN']:>10.0f}{coast['violations']:>5}{coast['speed_mean_kmh']:>9.1f}"
          f"{coast['over_vmax_pct']:>8.1f}{coast['under_vmin_pct']:>8.1f}{coast['gap_range_m']!s:>12}{coast['n_brakes']:>8}{coast['energy_kwh']:>8.1f}")


if __name__ == '__main__':
    main()
