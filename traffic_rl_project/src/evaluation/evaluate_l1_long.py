"""评估长距离RL第1层策略（15000步/初始65，完整朔黄 23.8km）。

指标：平均/最大速度、超80、低40、车钩力峰值、循环制动次数。
【可复现 2026-09-08】结果落盘 JSON 并内嵌 metadata（git_commit / physics_version /
simulator_model / 全物理配置 / seed / 模型路径 / 评估上下文），按时间戳归档不覆盖旧文件。
"""
import os
import sys
import json
from pathlib import Path
import numpy as np
from src.environments.train_env import TrainFormationEnv
from src.algorithms.mappo_agent import MAPPOAgent
from src.trainer.train_cyclic_braking import quantize_to_notch  # 与训练同一次量化
from src.physics_governance import official_entry_guard, official_world_config  # 【治理】
from src.physics_config import PhysicsConfig
from src.metadata import build_metadata  # 【可复现】评估元数据内嵌结果 JSON

V_MAX = 80.0/3.6
V_MIN = 40.0/3.6
# 完整协议（与多列 MARL 评估对齐，控制变量）：dt=0.1 × 15000 步 = 1500s ≈ 朔黄 23.8km。
# 此前 3000 步≈5km，未跑完整线路，作对比基线不公平、无意义。
MAX_STEPS = 15000
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
        a, _ = agent.select_actions(obs.flatten(), deterministic=True)
        throttle = quantize_to_notch(float(np.clip(a[0], -1, 1)))   # 与训练一致：离散档位
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
    res = {
        'mean_speed_kmh': float(speeds.mean()*3.6),
        'max_speed_kmh': float(speeds.max()*3.6),
        'over_80_rate': float((speeds > V_MAX).mean()),
        'below_40_rate': float((speeds < V_MIN).mean()),
        'peak_coupler_kN': float(max(peaks)),
        'n_brakes': int(n_brakes),
        'ok': ok,
    }
    print(f"[seed{seed}] {ok} 平均={res['mean_speed_kmh']:.1f}km/h 最大={res['max_speed_kmh']:.0f} "
          f"超80={res['over_80_rate']*100:.1f}% 低40={res['below_40_rate']*100:.1f}% "
          f"车钩力峰值={res['peak_coupler_kN']:.0f}kN 循环制动{n_brakes}次")
    return res


def main():
    official_entry_guard(__file__)
    ckpt = sys.argv[1] if len(sys.argv) > 1 else 'outputs/checkpoints/cyclic_mappo_best_seed0_v40-80_init65.pt'
    print(f"模型: {ckpt}")
    agent = MAPPOAgent(num_drones=1, obs_per_drone=4, act_per_drone=1, device='cuda')
    agent.load(ckpt)
    agent.policy.eval()
    # 【可复现】评估元数据（工况 OFFICIAL，无调试物理）内嵌结果 JSON
    PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
    meta = build_metadata(project_root=PROJECT_ROOT, case='official',
                          world_cfg=official_world_config(PhysicsConfig()),
                          seed=0, entry=__file__,
                          extra={'checkpoint': ckpt, 'max_steps': MAX_STEPS,
                                 'init_speed_kmh': INIT * 3.6, 'v_band_kmh': [V_MIN*3.6, V_MAX*3.6]})
    per_seed = [run(agent, seed) for seed in range(3)]
    agg = {k: float(np.mean([r[k] for r in per_seed])) for k in per_seed[0] if k != 'ok'}
    agg['ok'] = all(r['ok'] == per_seed[0]['ok'] for r in per_seed)
    # 【可复现】按时间戳归档，不覆盖旧文件
    from datetime import datetime
    stamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    results_dir = os.path.join(PROJECT_ROOT, 'outputs', 'results_l1')
    os.makedirs(results_dir, exist_ok=True)
    out = os.path.join(results_dir, f"eval_l1_long_{stamp}.json")
    with open(out, 'w', encoding='utf-8') as f:
        json.dump({'metadata': meta, 'aggregate': agg, 'per_seed': per_seed},
                  f, ensure_ascii=False, indent=2)
    print(f"已保存: {out}")


if __name__ == '__main__':
    main()
