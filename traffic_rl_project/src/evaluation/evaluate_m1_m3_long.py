"""M1(群组协同+车钩力) vs M3(单列独立δ=0) vs 惰行 —— 长距离朔黄线正确场景对比评估。

【工作方针（PROJECT_PIPELINE 4.0）】验证 M1 相对 M3 的协同增量。
正确场景 = 朔黄线真实剖面 + 多列保持间距（虚拟耦合）+ 长大下坡天然循环制动，
不引入人为扰动。

- M1：加载群组分层模型（RL 输出 δ 协同调整 + 第1层策略控速）
- M3：δ=0，每列仅第1层策略各自控速（隔离协同变量，无列间信息/协同）
- 惰行：throttle=0 baseline

指标：Reward、平均速度、超80/低40占比、车钩力峰值/超限、列间间距、循环制动次数。
随机采样多次取均值（MAPPO 标准，工作记忆已确认）。
"""
import sys
import numpy as np
from pathlib import Path
sys.path.append(str(Path(__file__).parent.parent.parent))
import torch
from src.environments.train_fleet_env import TrainFleetEnv
from src.algorithms.mappo_agent import MAPPOAgent

V_MAX = 80.0 / 3.6
V_MIN = 40.0 / 3.6
MAX_STEPS = 3000
NUM_TRAINS = 3


def make_env(init_speed, hierarchical, adj_coef=0.0):
    # 普通场景（各列同坡段起步，无 start_offset/spacing 人为坡段错开）
    # eval_mode=True：第1层策略用确定性采样（bug修复：消除 M1/M3 评估随机性）
    return TrainFleetEnv({
        'num_trains': NUM_TRAINS, 'consist_preset': '10kt_1plus0',
        'grade_profile': 'shuozhou_23800',
        'v_max': V_MAX, 'v_min': V_MIN,
        'target_gap': 100.0, 'headway_s': 5.0,
        'max_steps': MAX_STEPS, 'max_accel': 1.0,
        'enable_disturbance': False, 'use_coupler_constraint': True,
        'hierarchical': hierarchical, 'adj_coef': adj_coef,
        'eval_mode': True,
    })


def count_cycles(speeds_per_train):
    """统计各列循环制动次数。

    以速度下限 V_MIN（40km/h）为参考：速度跌破 V_MIN 后回升到 V_MIN 之上算一次
    "制动-缓解"循环。每列独立统计后求和。用前一列速度与当前速度跨 V_MIN 阈值
    的上升沿计数（速度从 <V_MIN 到 >=V_MIN 即一次缓解完成）。
    """
    total = 0
    for col in speeds_per_train:
        below = np.asarray(col) < V_MIN
        crossings = 0
        for k in range(1, len(below)):
            # 从低于下限恢复到高于下限 = 一次缓解（一次循环结束）
            if below[k] and not below[k - 1]:
                crossings += 1
        total += crossings
    return total


def run_episode(env, agent, mode, seed, deterministic=True):
    np.random.seed(seed)
    init = 65.0 / 3.6
    obs, _ = env.reset(options={'speed': init})
    done = False
    step = 0
    speeds_per_train = [[] for _ in range(NUM_TRAINS)]
    peaks_all, gaps, rewards = [], [], []
    while not done and step < MAX_STEPS:
        if mode == 'coast':
            a = np.zeros((NUM_TRAINS, 1), dtype=np.float32)
        elif mode == 'm1':
            flat = obs.flatten()
            a, _ = agent.select_actions(flat, deterministic=deterministic)
            a = a.reshape(NUM_TRAINS, 1)
        elif mode == 'm3':
            # 单列独立：δ=0，每列仅第1层策略控速（无协同）
            a = np.zeros((NUM_TRAINS, 1), dtype=np.float32)
        obs, r, term, trunc, info = env.step(a)
        done = term or trunc
        for i, tr in enumerate(env.trains):
            speeds_per_train[i].append(float(tr.dynamics.vel[0]))
        peaks_all.append(info['coupler_force_peak'] / 1e3)
        if env.num_trains > 1:
            g1 = env.trains[0].dynamics.pos[-1] - env._train_heads[1]
            g2 = env.trains[1].dynamics.pos[-1] - env._train_heads[2]
            gaps.append(min(g1, g2))
        rewards.append(r)
        step += 1
    speeds = np.array([np.array(c) for c in speeds_per_train])
    all_spd = np.concatenate(speeds)
    # 间距漂移指标：最小间距（负=追尾穿透）、间距范围（漂移幅度）、追尾步数
    gap_arr = np.array(gaps) if gaps else np.array([])
    collision_steps = int((gap_arr < 5.0).sum()) if len(gap_arr) else 0
    return {
        'reward': float(sum(rewards)),
        'speed_mean': float(all_spd.mean()) * 3.6,
        'speed_max': float(all_spd.max()) * 3.6,
        'over': float((all_spd > V_MAX).mean()) * 100,
        'under': float((all_spd < V_MIN).mean()) * 100,
        'coupler_peak': float(max(peaks_all)) if peaks_all else 0.0,
        'gap_min': float(gap_arr.min()) if len(gap_arr) else None,
        'gap_max': float(gap_arr.max()) if len(gap_arr) else None,
        'gap_drift': float(gap_arr.max() - gap_arr.min()) if len(gap_arr) else 0.0,
        'collision_steps': collision_steps,
        'cycles': count_cycles(speeds_per_train),  # 【接入 2026-08-20】循环制动次数指标
        'steps': step,
    }


def summarize(label, results):
    """确定性评估 + 多 seed 汇总。车钩力取中位数（排除 RL 随机爆炸异常值）。"""
    rewards = sorted(r['reward'] for r in results)
    over = sorted(r['over'] for r in results)
    under = sorted(r['under'] for r in results)
    peaks = sorted(r['coupler_peak'] for r in results)
    gap_mins = sorted(r['gap_min'] for r in results)
    drifts = sorted(r['gap_drift'] for r in results)
    colls = sorted(r['collision_steps'] for r in results)
    cycles = sorted(r['cycles'] for r in results)
    def med(x): return x[len(x) // 2]
    print(f"\n[{label}] 确定性评估 5 seed 汇总")
    print(f"  reward 中位={med(rewards):+.0f}  min={rewards[0]:+.0f} max={rewards[-1]:+.0f}")
    print(f"  超80中位={med(over):.1f}%  低40中位={med(under):.1f}%")
    print(f"  车钩力峰值中位={med(peaks):.0f}kN  min={peaks[0]:.0f} max={peaks[-1]:.0f}")
    print(f"  间距min中位={med(gap_mins):.0f}m  间距漂移(范围)中位={med(drifts):.0f}m  追尾步数中位={med(colls)}")
    print(f"  循环制动次数中位={med(cycles)}")


def main():
    mode = sys.argv[1] if len(sys.argv) > 1 else 'all'
    ckpt = sys.argv[2] if len(sys.argv) > 2 else 'outputs/checkpoints/mappo_fleet_best_cp_seed0.pt'
    n_seed = 5
    deterministic = True
    tag = "场景=[普通场景：各列同坡段起步，无人为坡段错开]"

    # 惰行 baseline
    coast_res = []
    for s in range(n_seed):
        env = make_env(65 / 3.6, hierarchical=False)
        coast_res.append(run_episode(env, None, 'coast', s, deterministic))
    summarize(f"惰行 baseline {tag}", coast_res)

    # M1 群组协同+车钩力
    m1_res = []
    if mode in ('all', 'm1'):
        agent = MAPPOAgent(num_drones=NUM_TRAINS, obs_per_drone=11, act_per_drone=1, device='cuda')
        agent.load(ckpt)
        agent.policy.eval()
        for s in range(n_seed):
            env = make_env(65 / 3.6, hierarchical=True, adj_coef=0.1)
            m1_res.append(run_episode(env, agent, 'm1', s, deterministic))
        summarize(f"M1 群组协同+车钩力 ({ckpt}) {tag}", m1_res)

    # M3 单列独立（δ=0，仅第1层策略各自控速）
    m3_res = []
    if mode in ('all', 'm3'):
        for s in range(n_seed):
            env = make_env(65 / 3.6, hierarchical=True, adj_coef=0.0)
            m3_res.append(run_episode(env, None, 'm3', s, deterministic))
        summarize(f"M3 单列独立（δ=0）{tag}", m3_res)


if __name__ == '__main__':
    main()
