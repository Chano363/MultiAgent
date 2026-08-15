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


def run_episode(env, policy_fn, record=True):
    """运行完整 episode，返回轨迹数据和最终指标。

    Args:
        env: TrainFleetEnv 实例
        policy_fn: callable(obs) -> actions (每列加速度)
        record: 是否记录轨迹

    Returns:
        dict: 指标 + 轨迹
    """
    obs, _ = env.reset(options={'speed': env.target_speed * 0.8})
    done = False
    step = 0

    traj = {'t': [], 'speed': [], 'gap': [], 'coupler_peak': [], 'accel': []}
    collision = False
    total_energy = 0.0
    peak_coupler = 0.0
    coupler_violations = 0
    speed_errors = []
    gap_errors = []
    max_gap_err = 0.0

    while not done and step < env.max_steps:
        actions = policy_fn(obs)

        # 记录步前状态
        speeds_before = np.array([tr.dynamics.vel[0] for tr in env.trains])
        if record:
            gaps = []
            for i in range(1, env.num_trains):
                prev_tail = env.trains[i - 1].dynamics.pos[-1]
                gaps.append(prev_tail - env._train_heads[i])
            traj['gap'].append(min(gaps) if gaps else 0.0)
            traj['coupler_peak'].append(
                max(np.max(np.abs(tr.dynamics._coupler_forces())) for tr in env.trains) / 1e3)

        obs, reward, terminated, truncated, info = env.step(actions)

        # 记录指标
        if record:
            traj['t'].append(env.steps)
            traj['speed'].append(env.trains[0].dynamics.vel[0])
            traj['accel'].append((env.trains[0].dynamics.vel[0] - speeds_before[0]) / env.dt)

        # 速度误差
        speed_errors.append(np.mean([abs(tr.dynamics.vel[0] - env.target_speed) for tr in env.trains]))
        # 间距误差
        for i in range(1, env.num_trains):
            gap = (env.trains[i - 1].dynamics.pos[-1] - env._train_heads[i])
            ge = abs(gap - env.target_gap)
            gap_errors.append(ge)
            max_gap_err = max(max_gap_err, ge)
            if gap < 5.0:
                collision = True

        # 车钩力
        peak_coupler = max(peak_coupler, info['coupler_force_peak'])
        coupler_violations = info['coupler_limit_violations']
        # 能耗
        total_energy += sum(getattr(tr.dynamics, '_energy_delta_kwh', 0.0) for tr in env.trains)

        step += 1
        done = terminated or truncated

    metrics = {
        'reward': reward,
        'speed_consistency': float(np.mean(speed_errors)),     # 速度一致性误差（越小越好）
        'gap_err_mean': float(np.mean(gap_errors)) if gap_errors else 0.0,
        'gap_err_max': float(max_gap_err),
        'coupler_peak_kN': float(peak_coupler / 1e3),
        'coupler_violations': int(coupler_violations),
        'energy_kwh': float(total_energy),
        'collision': bool(collision),
        'steps': int(step),
    }
    return metrics, traj


def summarize(results_list):
    """多种子统计：mean ± std。"""
    keys = ['reward', 'speed_consistency', 'gap_err_mean', 'gap_err_max',
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
