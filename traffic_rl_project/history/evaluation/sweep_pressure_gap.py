"""更强压力场景压力消融：扫描 target_gap（初始间距更近=更大追尾压力）。

用现有 M1 checkpoint 评估 M1/M3/M4/惰行在不同 target_gap 下的表现。
判断：目标间距调小（压力↑）→ M3/M4 追尾是否更严重 → 协同防追尾价值是否更突出。
注意：M1 在 100m 间距训练，更近间距未训练，验证其泛化是否仍防追尾。
"""
import sys
from pathlib import Path
import numpy as np
sys.path.append(str(Path(__file__).parent.parent.parent))
from src.evaluation import evaluate_m1_m3_long as ev
from src.algorithms.mappo_agent import MAPPOAgent


def eval_mode(mode, agent, target_gap, kp=0.01):
    env = ev.make_env(65.0 / 3.6, hierarchical=(mode != 'coast'),
                      adj_coef=0.1 if mode == 'm1' else (0.3 if mode == 'm4' else 0.0),
                      target_gap=target_gap)
    if mode == 'm4':
        env._m4_kp = kp
        env._m4_kd = 0.0
    r = ev.run_episode(env, agent, mode, 0, deterministic=True)
    return r


def main():
    agent = MAPPOAgent(num_drones=ev.NUM_TRAINS, obs_per_drone=11, act_per_drone=1, device='cuda')
    agent.load('outputs/checkpoints/mappo_fleet_best_cp_seed0_orig.pt')
    agent.policy.eval()

    print(f"{'gap':>5} | {'mode':>5} | {'reward':>9} | {'coupler':>7} | {'gap_min':>7} | {'coll':>5}")
    for gap in [100.0, 80.0, 60.0, 50.0, 40.0]:
        for mode in ['coast', 'm1', 'm3', 'm4']:
            r = eval_mode(mode, agent, gap)
            gm = r['gap_min'] if r['gap_min'] is not None else float('nan')
            print(f"{gap:>5.0f} | {mode:>5} | {r['reward']:+9.0f} | {r['coupler_peak']:>7.0f} | "
                  f"{gm:>7.0f} | {r['collision_steps']:>5}")
        print('-' * 55)


if __name__ == '__main__':
    main()
