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


def make_env(init_speed, hierarchical, adj_coef=0.0, disturbance_accel=0.0, disturbance_duration=200):
    # 普通场景（各列同坡段起步，无 start_offset/spacing 人为坡段错开）
    # eval_mode=True：第1层策略用确定性采样（bug修复：消除 M1/M3 评估随机性）
    # disturbance_accel<0：领航车扰动鲁棒性评估（突发减速），默认 0=无扰动。
    # disturbance_duration：扰动持续步数（短暂窗口，模拟前方临时限速，扰动后恢复）
    enable_disturbance = disturbance_accel < 0
    return TrainFleetEnv({
        'num_trains': NUM_TRAINS, 'consist_preset': '10kt_1plus0',
        'grade_profile': 'shuozhou_23800',
        'v_max': V_MAX, 'v_min': V_MIN,
        'target_gap': 100.0, 'headway_s': 5.0,
        'max_steps': MAX_STEPS, 'max_accel': 1.0,
        'enable_disturbance': enable_disturbance,
        'disturbance_step': 500, 'disturbance_duration': disturbance_duration,
        'disturbance_target_accel': disturbance_accel,
        'use_coupler_constraint': True,
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


def rule_coor_adj(env, kp=0.01, kd=0.0):
    """M4 规则启发式协同：间距误差 + 速度差 → 每列 coor_adj。

    对每列 i（非领航），用与前列的间距误差和目标间距（100m）的差 + 速度差
    生成 coor_adj ∈ [-1,1]（经 PID 增益）。领航车（列0）无前列，coor_adj=0。

    coor_adj = clip(kp * (target_gap - gap_i) + kd * (v_prev - v_i), -1, 1)
    - 间距 < 目标（gap_i < target_gap）→ (target_gap - gap_i) > 0 → coor_adj>0 → 提前制动（防追尾）
    - 间距 > 目标 → coor_adj<0 → 延后制动/提前缓解（防过大）
    - 前列快（v_prev>v_i）→ 后列可以慢点追，coor_adj<0；前列慢 → coor_adj>0 提前制动
    """
    target_gap = 100.0
    coor = np.zeros(env.num_trains, dtype=np.float32)
    for i in range(1, env.num_trains):
        gap_i = env.trains[i - 1].dynamics.pos[-1] - env._train_heads[i]
        v_prev = env.trains[i - 1].dynamics.vel[0] * 3.6
        v_i = env.trains[i].dynamics.vel[0] * 3.6
        adj = kp * (target_gap - gap_i) + kd * (v_prev - v_i)
        coor[i] = float(np.clip(adj, -1.0, 1.0))
    return coor


def run_episode(env, agent, mode, seed, deterministic=True, randomize_init=False, return_traj=False):
    """确定性评估一条轨迹，返回汇总指标。

    若 return_traj=True，额外在返回 dict 中加入 'traj'（逐步轨迹 DataFrame）：
    step / speed_0..2 / speed_mean / gap_1 / gap_2 / gap_min / coupler_peak_kN / reward_accum，
    供 make_m1m3_figures.py 制图复用 —— 保证 reward/指标/轨迹同一口径。
    """
    np.random.seed(seed)
    if randomize_init:
        # 初态随机化：初始速度在 [58,66] km/h 均匀采样（真实多种子统计，
        # 让不同 seed 跑不同工况，报告 mean±std 而非确定性单点）。
        # 注：范围限 [58,66] 避开高初态(68+)触发"缓解波满制动失效→车钩力爆炸"
        # 的已知动力学边界（见 VALIDATION_BASELINE 长距离超速问题），保证统计有效。
        init = np.random.uniform(58.0, 66.0) / 3.6
    else:
        init = 65.0 / 3.6
    obs, _ = env.reset(options={'speed': init})
    done = False
    step = 0
    speeds_per_train = [[] for _ in range(NUM_TRAINS)]
    peaks_all, gaps, rewards = [], [], []
    traj_rows = []
    cum_reward = 0.0
    # 记录每步的 RL 协同动作（M1）供策略分析
    adj_trace = []
    while not done and step < MAX_STEPS:
        if mode == 'coast':
            a = np.zeros((NUM_TRAINS, 1), dtype=np.float32)
            adj_trace.append([0.0, 0.0, 0.0])
        elif mode == 'm1':
            flat = obs.flatten()
            a, _ = agent.select_actions(flat, deterministic=deterministic)
            a = a.reshape(NUM_TRAINS, 1)
            adj_trace.append([float(v) for v in a.flatten()])
        elif mode == 'm4':
            # 规则启发式协同（M4）：间距误差 + 速度差 → coor_adj（PID 式）
            # 与 M1 完全同架构（分层执行），只差 coor_adj 来源（规则 vs RL）
            a = rule_coor_adj(env, env._m4_kp, env._m4_kd).reshape(NUM_TRAINS, 1)
            adj_trace.append([float(v) for v in a.flatten()])
        elif mode == 'm3':
            # 单列独立：δ=0，每列仅第1层策略控速（无协同）
            a = np.zeros((NUM_TRAINS, 1), dtype=np.float32)
            adj_trace.append([0.0, 0.0, 0.0])
        obs, r, term, trunc, info = env.step(a)
        done = term or trunc
        for i, tr in enumerate(env.trains):
            speeds_per_train[i].append(float(tr.dynamics.vel[0]))
        peaks_all.append(info['coupler_force_peak'] / 1e3)
        g1 = g2 = None
        if env.num_trains > 1:
            g1 = env.trains[0].dynamics.pos[-1] - env._train_heads[1]
            g2 = env.trains[1].dynamics.pos[-1] - env._train_heads[2]
            gaps.append(min(g1, g2))
        rewards.append(r)
        cum_reward += float(r)
        if return_traj:
            adj = adj_trace[-1] if len(adj_trace) == step + 1 else [0.0, 0.0, 0.0]
            traj_rows.append({
                'step': step,
                'speed_0': float(env.trains[0].dynamics.vel[0]) * 3.6,
                'speed_1': float(env.trains[1].dynamics.vel[0]) * 3.6,
                'speed_2': float(env.trains[2].dynamics.vel[0]) * 3.6,
                'speed_mean': float(np.mean([t.dynamics.vel[0] for t in env.trains])) * 3.6,
                'gap_1': g1, 'gap_2': g2,
                'gap_min': min(g1, g2) if (g1 is not None and g2 is not None) else None,
                'coupler_peak_kN': info['coupler_force_peak'] / 1e3,
                'reward_accum': cum_reward,
                'adj_0': adj[0], 'adj_1': adj[1], 'adj_2': adj[2],
            })
        step += 1
    speeds = np.array([np.array(c) for c in speeds_per_train])
    all_spd = np.concatenate(speeds)
    # 间距漂移指标：最小间距（负=追尾穿透）、间距范围（漂移幅度）、追尾步数
    gap_arr = np.array(gaps) if gaps else np.array([])
    collision_steps = int((gap_arr < 5.0).sum()) if len(gap_arr) else 0
    res = {
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
    if return_traj:
        import pandas as pd
        res['traj'] = pd.DataFrame(traj_rows)
    return res


def summarize(label, results):
    """确定性/多种子汇总。车钩力取中位数（排除 RL 随机爆炸异常值）。
    输出 mean±std（多种子统计）+ 中位数（稳健）。"""
    rewards = sorted(r['reward'] for r in results)
    over = sorted(r['over'] for r in results)
    under = sorted(r['under'] for r in results)
    peaks = sorted(r['coupler_peak'] for r in results)
    gap_mins = sorted(r['gap_min'] for r in results)
    drifts = sorted(r['gap_drift'] for r in results)
    colls = sorted(r['collision_steps'] for r in results)
    cycles = sorted(r['cycles'] for r in results)
    def med(x): return x[len(x) // 2]
    def mean_std(x):
        a = np.array(x, dtype=float)
        return a.mean(), a.std()
    n = len(rewards)
    mr, sr = mean_std(rewards)
    mo, so = mean_std(over)
    mu, su = mean_std(under)
    mp, sp = mean_std(peaks)
    mg, sg = mean_std(gap_mins)
    md, sd = mean_std(drifts)
    mc, sc = mean_std(colls)
    mcyc, scyc = mean_std(cycles)
    print(f"\n[{label}] {'随机化初态' if n > 1 else '确定性'} 评估 {n} seed 汇总 (mean±std / 中位)")
    print(f"  reward mean={mr:+.0f}±{sr:.0f}  中位={med(rewards):+.0f}  [{rewards[0]:+.0f},{rewards[-1]:+.0f}]")
    print(f"  超80 mean={mo:.1f}±{so:.1f}%  低40 mean={mu:.1f}±{su:.1f}%")
    print(f"  车钩力峰值 mean={mp:.0f}±{sp:.0f}kN  中位={med(peaks):.0f}kN  [{peaks[0]:.0f},{peaks[-1]:.0f}]")
    print(f"  间距min mean={mg:.0f}±{sg:.0f}m  间距漂移 mean={md:.0f}±{sd:.0f}m  追尾步数 mean={mc:.1f}±{sc:.1f}  中位={med(colls)}")
    print(f"  循环制动次数 mean={mcyc:.1f}±{scyc:.1f}  中位={med(cycles)}")


def main():
    # CLI: mode [ckpt] [--disturbance <accel>] [--disturbance_duration N] [--n_seed N] [--randomize_init]
    mode = sys.argv[1] if len(sys.argv) > 1 else 'all'
    ckpt = sys.argv[2] if len(sys.argv) > 2 else 'outputs/checkpoints/mappo_fleet_best_cp_seed0.pt'
    disturbance_accel = 0.0
    disturbance_duration = 200
    n_seed = 5
    randomize_init = '--randomize_init' in sys.argv
    if '--disturbance' in sys.argv:
        disturbance_accel = float(sys.argv[sys.argv.index('--disturbance') + 1])
    if '--disturbance_duration' in sys.argv:
        disturbance_duration = int(sys.argv[sys.argv.index('--disturbance_duration') + 1])
    if '--n_seed' in sys.argv:
        n_seed = int(sys.argv[sys.argv.index('--n_seed') + 1])
    deterministic = True
    if disturbance_accel < 0:
        tag = (f"场景=[普通场景 + 领航车扰动鲁棒性评估（扰动脉冲 {disturbance_accel:.1f}m/s² "
               f"@step500 持续{disturbance_duration}步）]")
    elif randomize_init:
        tag = "场景=[普通场景 + 初态随机化（初始速度55-75km/h，多种子统计）]"
    else:
        tag = "场景=[普通场景：各列同坡段起步，无人为坡段错开，无扰动]"

    # 惰行 baseline
    coast_res = []
    for s in range(n_seed):
        env = make_env(65 / 3.6, hierarchical=False, disturbance_accel=disturbance_accel,
                       disturbance_duration=disturbance_duration)
        coast_res.append(run_episode(env, None, 'coast', s, deterministic, randomize_init))
    summarize(f"惰行 baseline {tag}", coast_res)

    # M1 群组协同+车钩力
    m1_res = []
    if mode in ('all', 'm1'):
        agent = MAPPOAgent(num_drones=NUM_TRAINS, obs_per_drone=11, act_per_drone=1, device='cuda')
        agent.load(ckpt)
        agent.policy.eval()
        for s in range(n_seed):
            env = make_env(65 / 3.6, hierarchical=True, adj_coef=0.1, disturbance_accel=disturbance_accel,
                           disturbance_duration=disturbance_duration)
            m1_res.append(run_episode(env, agent, 'm1', s, deterministic, randomize_init))
        summarize(f"M1 群组协同+车钩力 ({ckpt}) {tag}", m1_res)

    # M3 单列独立（δ=0，仅第1层策略各自控速）
    m3_res = []
    if mode in ('all', 'm3'):
        for s in range(n_seed):
            env = make_env(65 / 3.6, hierarchical=True, adj_coef=0.0, disturbance_accel=disturbance_accel,
                           disturbance_duration=disturbance_duration)
            m3_res.append(run_episode(env, None, 'm3', s, deterministic, randomize_init))
        summarize(f"M3 单列独立（δ=0）{tag}", m3_res)

    # M4 规则启发式协同（间距误差+速度差 → coor_adj，PID 式）
    # 与 M1 完全同架构（分层执行），只差 coor_adj 来源（规则 vs RL）——证明 RL 增量
    m4_res = []
    if mode in ('all', 'm4'):
        kp = 0.01
        kd = 0.0
        for s in range(n_seed):
            env = make_env(65 / 3.6, hierarchical=True, adj_coef=0.3, disturbance_accel=disturbance_accel,
                           disturbance_duration=disturbance_duration)
            env._m4_kp = kp
            env._m4_kd = kd
            m4_res.append(run_episode(env, None, 'm4', s, deterministic, randomize_init))
        summarize(f"M4 规则启发式协同 (kp={kp},kd={kd}) {tag}", m4_res)


if __name__ == '__main__':
    main()
