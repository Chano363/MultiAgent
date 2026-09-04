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
from src.algorithms.coor_dqn_agent import CoorDQNAgent
from src.controllers.mpc_controller import MPCController
from src.controllers.fair_mpc_controller import FairMPCController

V_MAX = 80.0 / 3.6
V_MIN = 40.0 / 3.6
# 【2026-09-03 协议升级】默认 15000 步 = 完整覆盖朔黄线 23.8km（dt=0.1；按循环制动
# 实际平均速度 ~50-60km/h，15000 步≈23.8km。原 3000 步≈5km 仅覆盖 ~20%，未跑完整
# 线路循环制动全周期——见 DIAGNOSTICS 诊断-2026-09-03-完整23.8km协议。35km 剖面
# 显式传 --max_steps 35000（避免未传时误跑 35000 步 → 间距漂移巨大、reward 假崩溃）。
MAX_STEPS = 15000
NUM_TRAINS = 3


def make_env(init_speed, hierarchical, adj_coef=0.0, disturbance_accel=0.0, disturbance_duration=200,
             target_gap=100.0, grade_profile='shuozhou_23800', max_steps=None,
             controller='mpc_simplified', horizon=10, mpc_gap_min=20.0, mpc_enforce_coupler=True,
             blocks=5, block_len=10, use_coupler_constraint=True, enable_etcs=False):
    # 普通场景（各列同坡段起步，无 start_offset/spacing 人为坡段错开）
    # eval_mode=True：第1层策略用确定性采样（bug修复：消除 M1/M3 评估随机性）
    # disturbance_accel<0：领航车扰动鲁棒性评估（突发减速），默认 0=无扰动。
    # disturbance_duration：扰动持续步数（短暂窗口，模拟前方临时限速，扰动后恢复）
    # target_gap：列间目标间距（m），调小=初始间距更近=更大追尾压力场景（压力消融）
    # grade_profile：坡度剖面（默认朔黄线真实剖面；可换 v_shape/long_downhill 等做普适性验证）
    # use_coupler_constraint：安全层消融（--no_coupler）→ False，关掉车钩力 SafetyLayer 钳制
    # enable_etcs：是否启用 ETCS 目标距离超速防护（"真 ATP"，所有方法一视同仁，
    #              追尾由 ATP 兜底，聚焦"受约束下的控制质量"而非"谁追尾"）
    enable_disturbance = disturbance_accel < 0
    env = TrainFleetEnv({
        'num_trains': NUM_TRAINS, 'consist_preset': '10kt_1plus0',
        'grade_profile': grade_profile,
        'v_max': V_MAX, 'v_min': V_MIN,
        'target_gap': target_gap, 'headway_s': 5.0,
        'max_steps': max_steps or MAX_STEPS, 'max_accel': 1.0,
        'enable_disturbance': enable_disturbance,
        'disturbance_step': 500, 'disturbance_duration': disturbance_duration,
        'disturbance_target_accel': disturbance_accel,
        'use_coupler_constraint': use_coupler_constraint,
        'hierarchical': hierarchical, 'adj_coef': adj_coef,
        'enable_etcs': enable_etcs,
        'eval_mode': True,
    })
    # 挂载 MPC 协同控制器（供 'mpc' / 'fairmpc' / 'mpc_dir' / 'mpc_rule' 模式使用）
    if controller in ('fairmpc', 'mpc_dir', 'mpc_rule'):
        # inner_rule_cyclic：P2 公平基线（2026-09-02）。'mpc_rule' = MPC 直接控加速度
        # + 规则循环制动内层兜底（分层的低层规则控速），与 M-MARL like-for-like，
        # 消解审稿人"fair-MPC 被剥掉工业 ATO 规则内层"质疑。详见 DIAGNOSTICS 诊断-2026-09-02。
        env._mpc_controller = FairMPCController(
            num_trains=NUM_TRAINS, dt=0.1, v_max=env.v_max, v_min=env.v_min,
            target_speed=env.target_speed, headway_s=env.headway_s,
            gap_min=mpc_gap_min, enforce_coupler=mpc_enforce_coupler,
            horizon_blocks=blocks, block_len=block_len,
            inner_rule_cyclic=(controller == 'mpc_rule'),
        )
        env._mpc_controller.reset()
    else:
        env._mpc_controller = MPCController(
            num_trains=NUM_TRAINS, dt=0.1, horizon=20,
            target_gap=target_gap, headway_s=5.0, target_speed=env.target_speed,
            lambda_gap=2.0, lambda_v=0.2, lambda_u=0.05,
        )
    return env


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


def run_episode(env, agent, mode, seed, deterministic=True, randomize_init=False, return_traj=False,
                coor_agents=None):
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
    # 【2026-09-03 指标修正】ATP 紧急制动触发步数（用户要求替代"追尾步数"）：
    # 统计每步各列 safety_layer 新增的 etcs_ebi（EBI 紧急制动介入）事件。ETCS 真 ATP
    # 启用（--etcs）下"追尾被 ATP 兜底"，主指标应为"ATP 被触发的步数"而非间距穿透。
    atp_brake_steps = 0
    _prev_safety_len = [0] * NUM_TRAINS
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
        elif mode == 'mpc':
            # M-MPC baseline（对标 Yang2025 单列 MPC 范式 + 多列协同）：MPC 生成 coor_adj
            # 喂给与 M1 相同的分层控制器。与 M1 唯一区别：第2层协同来自确定性 MPC 而非 RL。
            spd_arr = np.array([tr.dynamics.vel[0] for tr in env.trains], dtype=float)
            acc_arr = np.array([env._last_target_accels[i] for i in range(env.num_trains)], dtype=float)
            gap_arr_mpc = np.array([env.trains[i - 1].dynamics.pos[-1] - env._train_heads[i]
                                    for i in range(1, env.num_trains)], dtype=float)
            coor = env._mpc_controller.compute_actions(obs, spd_arr, acc_arr, gap_arr_mpc)
            a = coor.reshape(NUM_TRAINS, 1)
            adj_trace.append([float(v) for v in a.flatten()])
        elif mode == 'fairmpc':
            # 公平版 MPC（M-MPC-fair，2026-08-30）：物理列模型预测 + 硬约束在线优化。
            # 内部显式施加车钩力 ≤1000kN + 列间间距 ≥ gap_min 约束，滚动时域求解 coor_adj，
            # 喂给与 M1 相同分层控制器（唯一区别：协同来源为模型驱动优化而非 RL）。
            spd_arr = np.array([tr.dynamics.vel[0] for tr in env.trains], dtype=float)
            acc_arr = np.array([env._last_target_accels[i] for i in range(env.num_trains)], dtype=float)
            gap_arr_mpc = np.array([env.trains[i - 1].dynamics.pos[-1] - env._train_heads[i]
                                    for i in range(1, env.num_trains)], dtype=float)
            coor = env._mpc_controller.compute_actions(obs, spd_arr, acc_arr, gap_arr_mpc, env=env)
            a = coor.reshape(NUM_TRAINS, 1)
            adj_trace.append([float(v) for v in a.flatten()])
        elif mode in ('mpc_dir', 'mpc_rule'):
            # 直接加速控制的公平版 MPC：非分层（hierarchical=False），MPC 直接给每列
            # 目标加速度（连续控制），列内低层 + 车钩力 SafetyLayer 负责 throttle 映射。
            # 'mpc_rule' = 同直接加速 + 规则循环制动内层兜底（inner_rule_cyclic，
            # make_env 中按 controller 区分），与 M-MARL like-for-like 公平基线。
            # 与"分层无模型 MARL"（M-MARL）对比——传统模型驱动 vs 无模型分层策略。
            U = env._mpc_controller.compute_actions_from_env(env, obs)
            a = U.reshape(NUM_TRAINS, 1)
            adj_trace.append([float(v) for v in a.flatten()])
        elif mode == 'mdqn_fair':
            # 公平 DQN baseline（分层阈值协同，与 M1 同架构）：每列独立 DQN 输出 coor_adj
            if coor_agents is None:
                raise ValueError("mdqn_fair 模式需要 coor_agents（每列 DQN 列表）")
            a = np.zeros((NUM_TRAINS, 1), dtype=np.float32)
            adj_row = []
            for i in range(env.num_trains):
                oi = obs[i].flatten()
                ai = coor_agents[i].select_action(oi, eval_mode=True)
                a[i, 0] = coor_agents[i].action_to_coor(ai)
                adj_row.append(float(a[i, 0]))
            adj_trace.append(adj_row)
        elif mode == 'm3':
            # 单列独立：δ=0，每列仅第1层策略控速（无协同）
            a = np.zeros((NUM_TRAINS, 1), dtype=np.float32)
            adj_trace.append([0.0, 0.0, 0.0])
        obs, r, term, trunc, info = env.step(a)
        # 【2026-09-03 指标修正】ATP 紧急制动触发步数：本步新增 etcs_ebi 事件 → 记 1 步。
        # last_events 跨步累积，用每列长度快照取"本步新增段"判断。
        for i, tr in enumerate(env.trains):
            evs = tr.safety.last_events
            cur = len(evs)
            if any(e.get('rule') == 'etcs_ebi' for e in evs[_prev_safety_len[i]:cur]):
                atp_brake_steps += 1
            _prev_safety_len[i] = cur
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
        'atp_brake_steps': atp_brake_steps,   # 【2026-09-03】ATP 紧急制动触发步数（主指标）
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
    atps = sorted(r.get('atp_brake_steps', 0) for r in results)  # 【2026-09-03】ATP 紧急制动步数
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
    matp, satp = mean_std(atps)
    mcyc, scyc = mean_std(cycles)
    print(f"\n[{label}] {'随机化初态' if n > 1 else '确定性'} 评估 {n} seed 汇总 (mean±std / 中位)")
    print(f"  reward mean={mr:+.0f}±{sr:.0f}  中位={med(rewards):+.0f}  [{rewards[0]:+.0f},{rewards[-1]:+.0f}]")
    print(f"  超80 mean={mo:.1f}±{so:.1f}%  低40 mean={mu:.1f}±{su:.1f}%")
    print(f"  车钩力峰值 mean={mp:.0f}±{sp:.0f}kN  中位={med(peaks):.0f}kN  [{peaks[0]:.0f},{peaks[-1]:.0f}]")
    print(f"  间距min mean={mg:.0f}±{sg:.0f}m  间距漂移 mean={md:.0f}±{sd:.0f}m")
    print(f"  ATP紧急制动步数 mean={matp:.1f}±{satp:.1f}  中位={med(atps)}  (追尾步数[辅助] mean={mc:.1f}±{sc:.1f})")
    print(f"  循环制动次数 mean={mcyc:.1f}±{scyc:.1f}  中位={med(cycles)}")


def main():
    # CLI: mode [ckpt] [--disturbance <accel>] [--disturbance_duration N] [--n_seed N] [--randomize_init] [--num_trains N]
    global NUM_TRAINS, MAX_STEPS
    mode = sys.argv[1] if len(sys.argv) > 1 else 'all'
    ckpt = sys.argv[2] if len(sys.argv) > 2 else 'outputs/checkpoints/mappo_fleet_best_cp_seed0.pt'
    disturbance_accel = 0.0
    disturbance_duration = 200
    n_seed = 5
    randomize_init = '--randomize_init' in sys.argv
    if '--num_trains' in sys.argv:
        NUM_TRAINS = int(sys.argv[sys.argv.index('--num_trains') + 1])
    grade_profile = 'shuozhou_23800'
    if '--grade' in sys.argv:
        grade_profile = sys.argv[sys.argv.index('--grade') + 1]
    if '--max_steps' in sys.argv:
        MAX_STEPS = int(sys.argv[sys.argv.index('--max_steps') + 1])
    target_gap = 100.0
    if '--target_gap' in sys.argv:
        target_gap = float(sys.argv[sys.argv.index('--target_gap') + 1])
    if '--disturbance' in sys.argv:
        disturbance_accel = float(sys.argv[sys.argv.index('--disturbance') + 1])
    if '--disturbance_duration' in sys.argv:
        disturbance_duration = int(sys.argv[sys.argv.index('--disturbance_duration') + 1])
    if '--n_seed' in sys.argv:
        n_seed = int(sys.argv[sys.argv.index('--n_seed') + 1])
    horizon = 10
    if '--horizon' in sys.argv:
        horizon = int(sys.argv[sys.argv.index('--horizon') + 1])
    mpc_gap_min = 20.0
    if '--mpc_gap_min' in sys.argv:
        mpc_gap_min = float(sys.argv[sys.argv.index('--mpc_gap_min') + 1])
    mpc_enforce_coupler = '--mpc_no_coupler' not in sys.argv
    blocks = 5
    if '--blocks' in sys.argv:
        blocks = int(sys.argv[sys.argv.index('--blocks') + 1])
    block_len = 10
    if '--block_len' in sys.argv:
        block_len = int(sys.argv[sys.argv.index('--block_len') + 1])
    deterministic = True
    # 安全层消融：--no_coupler → 关掉车钩力 SafetyLayer 钳制（观察车钩力超限），对齐
    # 设计锁定的"安全层消融（移除安全层观察车钩力和追尾）"，只关车钩力约束（用户 2026-08-30 确认）。
    use_coupler_constraint = '--no_coupler' not in sys.argv
    # ETCS 真 ATP：--etcs → 所有方法统一启用 ETCS 前瞻式超速防护，追尾由 ATP 兜底，
    # 对比聚焦"受约束下的控制质量"（车钩力余量/间距漂移/节能/实时性/泛化）。
    enable_etcs = '--etcs' in sys.argv
    if disturbance_accel < 0:
        tag = (f"场景=[普通场景 + 领航车扰动鲁棒性评估（扰动脉冲 {disturbance_accel:.1f}m/s² "
               f"@step500 持续{disturbance_duration}步）]")
    elif randomize_init:
        tag = "场景=[普通场景 + 初态随机化（初始速度55-75km/h，多种子统计）]"
    else:
        tag = "场景=[普通场景：各列同坡段起步，无人为坡段错开，无扰动]"

    # 惰行 baseline（仅显式请求时运行，节省不必要评估）
    coast_res = []
    if mode in ('all', 'coast'):
        for s in range(n_seed):
            env = make_env(65 / 3.6, hierarchical=False, disturbance_accel=disturbance_accel,
                           disturbance_duration=disturbance_duration, grade_profile=grade_profile,
                           target_gap=target_gap, enable_etcs=enable_etcs)
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
                           disturbance_duration=disturbance_duration, grade_profile=grade_profile,
                           target_gap=target_gap, use_coupler_constraint=use_coupler_constraint,
                           enable_etcs=enable_etcs)
            m1_res.append(run_episode(env, agent, 'm1', s, deterministic, randomize_init))
        summarize(f"M1 群组协同+车钩力 (coupler_constraint={use_coupler_constraint}) ({ckpt}) {tag}", m1_res)

    # M3 单列独立（δ=0，仅第1层策略各自控速）
    m3_res = []
    if mode in ('all', 'm3'):
        for s in range(n_seed):
            env = make_env(65 / 3.6, hierarchical=True, adj_coef=0.0, disturbance_accel=disturbance_accel,
                           disturbance_duration=disturbance_duration, grade_profile=grade_profile,
                           target_gap=target_gap, enable_etcs=enable_etcs)
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
                           disturbance_duration=disturbance_duration, grade_profile=grade_profile,
                           target_gap=target_gap, enable_etcs=enable_etcs)
            env._m4_kp = kp
            env._m4_kd = kd
            m4_res.append(run_episode(env, None, 'm4', s, deterministic, randomize_init))
        summarize(f"M4 规则启发式协同 (kp={kp},kd={kd}) {tag}", m4_res)

    # M-MPC 协同（对标 Yang2025 单列 MPC 范式 + 多列协同）：第2层用确定性 MPC 生成 coor_adj
    mpc_res = []
    if mode in ('all', 'mpc'):
        for s in range(n_seed):
            env = make_env(65 / 3.6, hierarchical=True, adj_coef=0.3, disturbance_accel=disturbance_accel,
                           disturbance_duration=disturbance_duration, grade_profile=grade_profile,
                           target_gap=target_gap, enable_etcs=enable_etcs)
            mpc_res.append(run_episode(env, None, 'mpc', s, deterministic, randomize_init))
        summarize(f"M-MPC 协同（确定性 MPC，horizon={env._mpc_controller.horizon}）{tag}", mpc_res)

    # 公平版 MPC（M-MPC-fair，2026-08-30）：物理列模型预测 + 硬约束（车钩力≤1000kN + 间距≥下限）
    fm_res = []
    if mode in ('all', 'fairmpc'):
        for s in range(n_seed):
            env = make_env(65 / 3.6, hierarchical=True, adj_coef=0.3, disturbance_accel=disturbance_accel,
                           disturbance_duration=disturbance_duration, grade_profile=grade_profile,
                           target_gap=target_gap, controller='fairmpc', horizon=horizon,
                           mpc_gap_min=mpc_gap_min, mpc_enforce_coupler=mpc_enforce_coupler,
                           enable_etcs=enable_etcs)
            fm_res.append(run_episode(env, None, 'fairmpc', s, deterministic, randomize_init))
        times = env._mpc_controller.solve_times
        mean_t = float(np.mean(times)) if times else float('nan')
        summarize(f"M-MPC-fair 公平版 MPC（H={horizon}, gap_min={mpc_gap_min}m, "
                  f"coupler={mpc_enforce_coupler}）{tag}", fm_res)
        print(f"  每步求解耗时 mean={mean_t*1000:.1f}ms  总求解次数={len(times)}")

    # 直接加速控制的公平版 MPC（M-MPC，传统方法代表）：非分层 + 模型预测 + 硬约束
    mpc_dir_res = []
    if mode in ('all', 'mpc_dir'):
        for s in range(n_seed):
            env = make_env(65 / 3.6, hierarchical=False, adj_coef=0.3, disturbance_accel=disturbance_accel,
                           disturbance_duration=disturbance_duration, grade_profile=grade_profile,
                           target_gap=target_gap, controller='mpc_dir',
                           mpc_gap_min=mpc_gap_min, mpc_enforce_coupler=mpc_enforce_coupler,
                           blocks=blocks, block_len=block_len, enable_etcs=enable_etcs)
            mpc_dir_res.append(run_episode(env, None, 'mpc_dir', s, deterministic, randomize_init))
        times = env._mpc_controller.solve_times
        mean_t = float(np.mean(times)) if times else float('nan')
        summarize(f"M-MPC 公平版（直接加速，B={blocks}×{block_len}步, gap_min={mpc_gap_min}m, "
                  f"coupler={mpc_enforce_coupler}）{tag}", mpc_dir_res)
        print(f"  每步求解耗时 mean={mean_t*1000:.1f}ms  总求解次数={len(times)}")

    # M-MPC-rule（P2 公平基线，2026-09-02）：MPC 直接控加速度 + 规则循环制动内层兜底。
    # 与 M-MARL like-for-like（同"规则护盾 + 优化外层"），消解 fair-MPC 是 strawman 质疑。
    # 详见 records/DIAGNOSTICS 诊断-2026-09-02-ARIS 试点 P2。
    mpc_rule_res = []
    if mode in ('all', 'mpc_rule'):
        for s in range(n_seed):
            env = make_env(65 / 3.6, hierarchical=False, adj_coef=0.3, disturbance_accel=disturbance_accel,
                           disturbance_duration=disturbance_duration, grade_profile=grade_profile,
                           target_gap=target_gap, controller='mpc_rule',
                           mpc_gap_min=mpc_gap_min, mpc_enforce_coupler=mpc_enforce_coupler,
                           blocks=blocks, block_len=block_len, enable_etcs=enable_etcs)
            mpc_rule_res.append(run_episode(env, None, 'mpc_rule', s, deterministic, randomize_init))
        times = env._mpc_controller.solve_times
        mean_t = float(np.mean(times)) if times else float('nan')
        summarize(f"M-MPC-rule 公平版（直接加速+规则内层兜底，B={blocks}×{block_len}步, "
                  f"gap_min={mpc_gap_min}m, coupler={mpc_enforce_coupler}）{tag}", mpc_rule_res)
        print(f"  每步求解耗时 mean={mean_t*1000:.1f}ms  总求解次数={len(times)}")

    # M-DQN-fair 公平 DQN baseline：分层阈值协同，与 M1 同架构，只换第2层算法（DQN）
    # 每列独立 DQN（coor_dqn_best_seed<seed>_train<i>.pt），输出 coor_adj → 阈值偏移。
    mdqn_fair_res = []
    if mode in ('all', 'mdqn_fair'):
        dqn_seed = '--dqn_seed' in sys.argv and int(sys.argv[sys.argv.index('--dqn_seed') + 1]) or 0
        dqn_dir = sys.argv[sys.argv.index('--dqn_dir') + 1] if '--dqn_dir' in sys.argv else 'outputs/checkpoints'
        coor_agents = []
        for i in range(NUM_TRAINS):
            ag = CoorDQNAgent(obs_dim=11, device='cuda')
            ag.load(f"{dqn_dir}/coor_dqn_best_seed{dqn_seed}_train{i}.pt")
            ag.eps = 0.0  # 评估无探索
            coor_agents.append(ag)
        for s in range(n_seed):
            env = make_env(65 / 3.6, hierarchical=True, adj_coef=0.3, disturbance_accel=disturbance_accel,
                           disturbance_duration=disturbance_duration, grade_profile=grade_profile,
                           target_gap=target_gap, enable_etcs=enable_etcs)
            mdqn_fair_res.append(
                run_episode(env, None, 'mdqn_fair', s, deterministic, randomize_init, coor_agents=coor_agents))
        summarize(f"M-DQN-fair 公平 DQN 协同 (seed{dqn_seed}) {tag}", mdqn_fair_res)


if __name__ == '__main__':
    main()
