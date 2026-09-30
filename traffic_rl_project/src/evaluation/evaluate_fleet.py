"""
列间 MARL 统一评估框架：对比实验 + 轨迹记录 + 指标计算。

支持在同一场景下评估不同控制策略（用于论文对比实验）：
- 方法：你的 MAPPO（考虑车钩力）+ 列内底层控制器
- Baseline 1：单列独立控制（每列各自 PID，无协同）
- Baseline 2：忽略车钩力的群组 MARL（宋宗莹式）

统一评价指标（会议论文标准）：
- 速度一致性误差（mean/std）
- 间距误差（mean/max）
- 车钩力峰值 / 超限次数（≤1000kN 约束）
- 牵引能耗（kWh）
- 碰撞（追尾）检测
"""

import numpy as np


def run_episode(env, policy_fn, record=True, init_speed=None):
    """运行完整 episode，返回轨迹数据和最终指标（论文级，逐列记录）。

    Args:
        env: TrainFleetEnv 实例
        policy_fn: callable(obs) -> actions (每列加速度)
        record: 是否记录轨迹
        init_speed: 初始速度（m/s），默认对齐 Zhang2024 长大下坡 65 km/h

    Returns:
        metrics: dict（含逐列明细 metrics_per_train）
        traj: dict
    """
    if init_speed is None:
        init_speed = 65.0 / 3.6  # 对齐 Zhang2024 长大下坡循环制动初始速度
    obs, _ = env.reset(options={'speed': init_speed})
    done = False
    step = 0

    n = env.num_trains
    traj = {'t': [], 'speed': [], 'gap': [], 'coupler_peak': [], 'accel': []}
    collision = False
    total_energy = 0.0
    # 逐列记录（论文要求：群组对比必须逐列记录，不能只记所有列最大值）
    peak_coupler_per_train = np.zeros(n)          # 每列车钩力峰值（kN）
    viol_per_train = np.zeros(n)                  # 每列超限次数
    speed_over_vmax = np.zeros(n)                 # 每列超 v_max 步数
    speed_under_vmin = np.zeros(n)                # 每列低于 v_min 步数
    speed_sums = np.zeros(n)                      # 每列速度累计（算均值/一致性）
    speed_sq_sums = np.zeros(n)
    gap_errors = []                               # 所有列间间距误差
    max_gap_err = 0.0

    while not done and step < env.max_steps:
        actions = policy_fn(obs)

        speeds_before = np.array([tr.dynamics.vel[0] for tr in env.trains])
        if record:
            gaps = []
            for i in range(1, n):
                prev_tail = env.trains[i - 1].dynamics.pos[-1]
                gaps.append(prev_tail - env._train_heads[i])
            traj['gap'].append(min(gaps) if gaps else 0.0)
            traj['coupler_peak'].append(
                # 【2026-09-30 口径统一】断面力口径（单钩力，与论文/实测基准一致）
                max(np.max(np.abs(tr.dynamics.coupler_interface_forces()))
                    for tr in env.trains) / 1e3)

        obs, reward, terminated, truncated, info = env.step(actions)

        if record:
            traj['t'].append(env.steps)
            traj['speed'].append(env.trains[0].dynamics.vel[0])
            traj['accel'].append((env.trains[0].dynamics.vel[0] - speeds_before[0]) / env.dt)

        # 逐列：速度区间越界统计（限速 [v_min, v_max]）
        for i, tr in enumerate(env.trains):
            v = tr.dynamics.vel[0]
            if v > env.v_max:
                speed_over_vmax[i] += 1
            if v < env.v_min:
                speed_under_vmin[i] += 1
            speed_sums[i] += v
            speed_sq_sums[i] += v * v

        # 逐列：车钩力峰值/超限（用当前步该列最大车钩力）
        for i, tr in enumerate(env.trains):
            # 【2026-09-30 口径统一】断面力口径（单钩力）
            cf = np.abs(tr.dynamics.coupler_interface_forces())
            if len(cf) > 0:
                peak_coupler_per_train[i] = max(peak_coupler_per_train[i], np.max(cf) / 1e3)
                viol_per_train[i] += int(np.sum(cf > env.coupler_force_limit_n))

        # 间距误差（所有列间）
        for i in range(1, n):
            gap = (env.trains[i - 1].dynamics.pos[-1] - env._train_heads[i])
            ge = abs(gap - env.target_gap)
            gap_errors.append(ge)
            max_gap_err = max(max_gap_err, ge)
            if gap < 5.0:
                collision = True

        total_energy += sum(getattr(tr.dynamics, '_energy_delta_kwh', 0.0) for tr in env.trains)

        step += 1
        done = terminated or truncated

    # 逐列速度均值/标准差（速度一致性）
    mean_speed = speed_sums / max(step, 1)
    speed_std = np.sqrt(np.maximum(speed_sq_sums / max(step, 1) - mean_speed ** 2, 0.0))

    metrics = {
        'reward': reward,
        'speed_mean': float(np.mean(mean_speed)),            # 群组平均速度
        'speed_std_across': float(np.std(mean_speed)),       # 列间速度一致性（越小越好）
        'speed_over_vmax_frac': float(np.mean(speed_over_vmax) / max(step, 1)),  # 超速步数占比
        'speed_under_vmin_frac': float(np.mean(speed_under_vmin) / max(step, 1)),  # 低速步数占比
        'gap_err_mean': float(np.mean(gap_errors)) if gap_errors else 0.0,
        'gap_err_max': float(max_gap_err),
        'coupler_peak_kN': float(np.max(peak_coupler_per_train)),   # 全局峰值
        'coupler_violations': int(np.sum(viol_per_train)),
        'energy_kwh': float(total_energy),
        'collision': bool(collision),
        'steps': int(step),
        # 逐列明细（论文分组对比必需）
        'metrics_per_train': {
            'coupler_peak_kN': peak_coupler_per_train.tolist(),
            'coupler_violations': viol_per_train.tolist(),
            'speed_mean': mean_speed.tolist(),
            'speed_std': speed_std.tolist(),
        },
    }
    return metrics, traj


def summarize(results_list):
    """多种子统计：mean ± std。"""
    keys = ['reward', 'speed_mean', 'speed_std_across', 'speed_over_vmax_frac',
            'speed_under_vmin_frac', 'gap_err_mean', 'gap_err_max',
            'coupler_peak_kN', 'coupler_violations', 'energy_kwh', 'collision']
    out = {}
    for k in keys:
        vals = [r[k] for r in results_list]
        out[k] = (float(np.mean(vals)), float(np.std(vals)))
    return out


# ---------------------------------------------------------------------------
# Baseline 策略
# ---------------------------------------------------------------------------

def baseline_single_train_pid(env, speed_kp=0.8):
    """Baseline 1：单列独立控制（无协同）。

    每列各自用 PID 把本列速度收敛到目标速度，**不观测/不使用列间间距**。
    即：每列独立跟随目标速度，不协同调整 → 无法应对领航车扰动导致间距变化。
    """
    state = {'integral': np.zeros(env.num_trains), 'prev_err': np.zeros(env.num_trains)}

    def policy_fn(obs):
        # 只用自己的速度误差（obs[:,0]），忽略间距误差（obs[:,1]）
        speed_err = env.target_speed - np.array([tr.dynamics.vel[0] for tr in env.trains])
        state['integral'] += speed_err * env.dt
        der = (speed_err - state['prev_err']) / max(env.dt, 1e-6)
        state['prev_err'] = speed_err
        # 目标加速度 = PID 输出，clip 到 max_accel
        accel = np.clip(speed_kp * speed_err + 0.1 * state['integral'] + 0.1 * der,
                        -env.max_accel, env.max_accel)
        return accel

    return policy_fn


def baseline_no_coupler_mar(env, target_gap_weight=0.4):
    """Baseline 2：忽略车钩力的群组 MARL（宋宗莹式）。

    智能体仍为每列，但奖励/决策**不包含车钩力约束**（假设列车为单质点、无车钩力）。
    只优化：速度一致性 + 间距保持。
    实现：用一个简单的集中式规则策略——根据间距误差调整加速度（间距过近就减速），
    但不考虑车钩力。作为"忽略车钩力"的对照 baseline。
    """
    def policy_fn(obs):
        actions = np.zeros(env.num_trains)
        for i in range(env.num_trains):
            # 速度同步（向目标速度调整）
            speed_err = env.target_speed - env.trains[i].dynamics.vel[0]
            a = 0.5 * speed_err
            # 间距保持（只用间距误差，不管车钩力）
            if i > 0:
                gap_err = obs[i, 1]  # 间距误差
                a -= target_gap_weight * np.clip(gap_err / 100.0, -1, 1)  # 间距过近（负误差）→ 减速
            actions[i] = np.clip(a, -env.max_accel, env.max_accel)
        return actions

    return policy_fn


def policy_learned_marl(agent, env):
    """你的方法：MAPPO（考虑车钩力）+ 列内底层控制器。"""
    def policy_fn(obs):
        flat = obs.flatten()
        actions, _ = agent.select_actions(flat, deterministic=True)
        return actions
    return policy_fn
