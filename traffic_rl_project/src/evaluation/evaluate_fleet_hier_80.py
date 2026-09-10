"""第2层分层模型评估（初始80循环制动场景，朔黄线/缓解波/1500步）。

指标：reward/车钩力/速度区间/循环制动次数/列间间距/能耗。
"""
import sys
import numpy as np
from pathlib import Path
from src.environments.train_fleet_env import TrainFleetEnv
from src.algorithms.mappo_agent import MAPPOAgent

INIT = 80.0 / 3.6
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
                range=(speeds.min()*3.6, speeds.max()*3.6), over=over/len(speeds)*100,
                under=under/len(speeds)*100, gaps=(gaps.min(), gaps.max()), nbr=n_brakes,
                steps=step)


def main():
    ckpt = sys.argv[1] if len(sys.argv) > 1 else 'outputs/checkpoints/mappo_fleet_best_cp_seed0.pt'
    agent = MAPPOAgent(num_drones=3, obs_per_drone=11, act_per_drone=1, device='cuda')
    agent.load(ckpt)
    agent.policy.eval()
    print(f"第2层分层评估（初始80 循环制动, 朔黄线, 缓解波, {MAX_STEPS}步）")
    print(f"checkpoint: {ckpt}")
    # M1：分层MAPPO
    m1 = evaluate(make_env(), lambda obs: agent.select_actions(obs.flatten(), deterministic=True)[0].reshape(3, 1))
    # 纯第1层（δ=0，隔离RL协同增量）
    l1 = evaluate(make_env(), lambda obs: np.zeros(3))
    for name, d in [('M1分层MAPPO', m1), ('纯第1层(δ=0)', l1)]:
        print(f"[{name}] Reward={d['reward']:.0f} 车钩力={d['peak']:.0f}kN 超限={d['viol']} "
              f"平均={d['mean']:.1f}km/h 范围={tuple(round(x) for x in d['range'])} "
              f"超80={d['over']:.1f}% 低40={d['under']:.1f}% 间距={tuple(round(x) for x in d['gaps'])}m "
              f"循环制动={d['nbr']}次 步数={d['steps']}")


if __name__ == '__main__':
    main()
