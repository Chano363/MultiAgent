"""评估长距离RL第1层策略（3000步/初始65），随机采样（MAPPO标准）。

指标：平均/最大速度、超80、低40、车钩力峰值、循环制动次数。
"""
import sys
import numpy as np
from pathlib import Path
sys.path.append(str(Path(__file__).parent.parent.parent))
from src.environments.train_env import TrainFormationEnv
from src.algorithms.mappo_agent import MAPPOAgent

V_MAX = 80.0/3.6
V_MIN = 40.0/3.6
MAX_STEPS = 3000
INIT = 65.0/3.6


def cyclic_obs(env):
    vel = float(env.dynamics.vel[0])
    coupler = np.abs(env.dynamics._coupler_forces())
    peak = float(np.max(coupler)) if len(coupler) else 0.0
    return np.array([[vel, vel - env.target_speed, env.dynamics.pos[0]*0.0001, peak/env.coupler_force_limit_n]], dtype=np.float32)


def run(agent, seed):
    np.random.seed(seed)
    env = TrainFormationEnv({
        'consist_preset': '10kt_1plus0', 'grade_profile': 'shuozhou_23800',
        'target_speed': 20.0, 'max_steps': MAX_STEPS, 'enable_safety': True, 'dt': 0.1,
        'release_sync': False,
    })
    env.reset(options={'speed': INIT})
    obs = cyclic_obs(env)
    done = False
    step = 0
    speeds = []
    peaks = []
    braking = False
    n_brakes = 0
    prev = None
    while not done and step < MAX_STEPS:
        a, _ = agent.select_actions(obs.flatten(), deterministic=False)
        throttle = float(np.clip(a[0], -1, 1))
        obs, r, term, trunc, info = env.step(np.full(env.num_vehicles, throttle))
        done = term or trunc
        speeds.append(float(env.dynamics.vel[0]))
        peaks.append(np.max(np.abs(env.dynamics._coupler_forces()))/1e3)
        if prev is not None and float(env.dynamics.vel[0]) < prev - 0.5 and not braking:
            braking = True
        elif braking and float(env.dynamics.vel[0]) > prev + 0.5:
            n_brakes += 1
            braking = False
        prev = float(env.dynamics.vel[0])
        obs = cyclic_obs(env)
        step += 1
    speeds = np.array(speeds)
    ok = "✅" if (speeds > V_MAX).mean() < 0.2 and (speeds < V_MIN).mean() < 0.3 and max(peaks) < 1000 else "❌"
    print(f"[seed{seed}] {ok} 平均={speeds.mean()*3.6:.1f}km/h 最大={speeds.max()*3.6:.0f} "
          f"超80={(speeds>V_MAX).mean()*100:.1f}% 低40={(speeds<V_MIN).mean()*100:.1f}% "
          f"车钩力峰值={max(peaks):.0f}kN 循环制动{n_brakes}次")


def main():
    ckpt = sys.argv[1] if len(sys.argv) > 1 else 'outputs/checkpoints/cyclic_mappo_best_seed0_v40-80_init65.pt'
    print(f"模型: {ckpt}")
    agent = MAPPOAgent(num_drones=1, obs_per_drone=4, act_per_drone=1, device='cuda')
    agent.load(ckpt)
    agent.policy.eval()
    for seed in range(3):
        run(agent, seed)


if __name__ == '__main__':
    main()
