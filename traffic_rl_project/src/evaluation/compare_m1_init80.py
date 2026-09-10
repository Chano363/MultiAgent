"""论文对比矩阵v2：初始80km/h（长大下坡循环制动场景），M1 vs 纯第1层 vs 惰行。

初始80立即进入需制动状态，触发循环制动。对比 M1 是否学会循环制动守速。
"""
import sys
import numpy as np
from pathlib import Path
from src.environments.train_fleet_env import TrainFleetEnv
from src.algorithms.mappo_agent import MAPPOAgent

INIT = 80.0 / 3.6
MAX_STEPS = 3000


def make_env(hier=True):
    return TrainFleetEnv({
        'num_trains': 3, 'consist_preset': '10kt_1plus0',
        'grade_profile': 'shuozhou_23800',
        'v_max': 80.0 / 3.6, 'v_min': 40.0 / 3.6,
        'target_gap': 100.0, 'headway_s': 5.0,
        'max_steps': MAX_STEPS, 'max_accel': 1.0,
        'enable_disturbance': False, 'use_coupler_constraint': True,
        'hierarchical': hier,
    })


def evaluate(env, action_fn):
    obs, _ = env.reset(options={'speed': INIT})
    done = False
    step = 0
    cum_r = 0.0
    peak = 0.0
    viol = 0
    speeds = []
    gaps = []
    over = under = 0
    n_brakes = 0
    prev = None
    braking = False
    while not done and step < MAX_STEPS:
        a = action_fn(obs)
        obs, r, term, trunc, info = env.step(a)
        done = term or trunc
        cum_r += r
        peak = max(peak, info['coupler_force_peak'])
        viol += info['coupler_limit_violations']
        vs = [tr.dynamics.vel[0] for tr in env.trains]
        speeds.extend(vs)
        over += sum(1 for v in vs if v > env.v_max)
        under += sum(1 for v in vs if v < env.v_min)
        if env.num_trains > 1:
            gaps.append(min(env.trains[0].dynamics.pos[-1] - env._train_heads[1],
                            env.trains[1].dynamics.pos[-1] - env._train_heads[2]))
        v0 = vs[0]
        if prev is not None and v0 < prev - 0.5 and not braking:
            braking = True
        elif braking and v0 > prev + 0.5:
            n_brakes += 1
            braking = False
        prev = v0
        step += 1
    speeds = np.array(speeds)
    gaps = np.array(gaps)
    return dict(reward=cum_r, peak=peak/1e3, viol=viol, mean=speeds.mean()*3.6,
                over=over/len(speeds)*100, under=under/len(speeds)*100,
                gaps=(gaps.min(), gaps.max()), nbr=n_brakes, steps=step)


def main():
    ckpt = sys.argv[1] if len(sys.argv) > 1 else 'outputs/checkpoints/mappo_fleet_best_cp_seed0.pt'
    agent = MAPPOAgent(num_drones=3, obs_per_drone=11, act_per_drone=1, device='cuda')
    agent.load(ckpt)
    agent.policy.eval()
    print(f"对比矩阵v2（初始80km/h 长大下坡循环制动, 朔黄线, 缓解波, {MAX_STEPS}步）")
    print(f"{'方法':<18}{'Reward':>9}{'车钩力kN':>9}{'超限':>4}{'平均':>7}{'超80%':>7}{'低40%':>7}{'间距m':>14}{'循环':>4}")
    m1 = evaluate(make_env(True), lambda obs: agent.select_actions(obs.flatten(), deterministic=True)[0].reshape(3,1))
    l1 = evaluate(make_env(True), lambda obs: np.zeros(3))
    coast = evaluate(make_env(False), lambda obs: np.zeros(3))
    for name, d in [('M1', m1), ('纯第1层', l1), ('惰行', coast)]:
        print(f"{name:<18}{d['reward']:>9.0f}{d['peak']:>9.0f}{d['viol']:>4}{d['mean']:>7.0f}"
              f"{d['over']:>7.1f}{d['under']:>7.1f}{str(tuple(round(x) for x in d['gaps'])):>14}{d['nbr']:>4}")


if __name__ == '__main__':
    main()
