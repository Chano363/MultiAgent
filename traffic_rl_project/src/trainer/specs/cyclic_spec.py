"""L1 单列循环制动的领域符号（统一框架 part）：obs/reward/notch量化/BC warm start。

【2026-09-06 从 train_cyclic_braking.py 迁移】统一训练框架复用点。
train_cyclic_braking 改为从此导入并 re-export，保持
`from src.trainer.train_cyclic_braking import cyclic_obs/...` 兼容。
限速由模块级 V_MAX_MPS/V_MIN_MPS 决定，框架按 config 用 set_cyclic_limits 显式设置。
"""
import logging

import numpy as np

from src.environments.train_env import TrainFormationEnv
from src.algorithms.mappo_agent import MAPPOAgent

logger = logging.getLogger('CyclicSpec')

# 默认限速（对齐 Zhang2024）
V_MAX_MPS = 80.0 / 3.6      # 80 km/h 最高限速
V_MIN_MPS = 40.0 / 3.6      # 40 km/h 最低缓解速度


def set_cyclic_limits(v_max_mps=None, v_min_mps=None):
    """按实验配置设置限速（cyclic_obs/cyclic_reward 读取模块级值）。"""
    global V_MAX_MPS, V_MIN_MPS
    if v_max_mps is not None:
        V_MAX_MPS = float(v_max_mps)
    if v_min_mps is not None:
        V_MIN_MPS = float(v_min_mps)


def cyclic_obs(env) -> np.ndarray:
    """整列观测（1 智能体）：[速度, 速度误差, 位置(缩放), 车钩力峰值归一化]。

    对齐 Zhang2024 s=[P,V,T]，加我们的车钩力增量。
    """
    vel = float(env.dynamics.vel[0])          # 机车速度（m/s）
    # 【2026-09-30 口径统一】obs 通道刻意保留**每车净力**口径（不改，
    # 避免作废第1层既有 checkpoint）；断面力口径只用于安全层门控/违规计数/评估指标。
    coupler = np.abs(env.dynamics._coupler_forces())
    coupler_peak = float(np.max(coupler)) if len(coupler) else 0.0
    return np.array([
        [vel, vel - env.target_speed, env.dynamics.pos[0] * 0.0001,
         coupler_peak / env.coupler_force_limit_n],
    ], dtype=np.float32)


# E17 离散档位表（对齐重载列车 Tang2020/VCTS：牵引+惰行+制动）
NOTCH_TABLE = np.array([0.7, 0.4, 0.2, 0.0, -0.3, -0.5, -0.8])


def quantize_to_notch(continuous: float) -> float:
    """连续动作量化到最近离散档位（对齐领域标准，避免连续策略mean塌缩）。"""
    idx = int(np.argmin(np.abs(NOTCH_TABLE - continuous)))
    return float(NOTCH_TABLE[idx])


def cyclic_reward(env, prev_speed, prev_coupler_peak, brake_engaged, throttle) -> float:
    """奖励：对齐 Zhang2024（速度约束 + 制动距离）+ 我们的车钩力 + 循环制动引导。

    Zhang2024: 速度<40 或 >80 → 惩罚 Rc；空气制动中 → 0；缓解 → +Rd（鼓励减制动距离）
    我们加：车钩力超限成比例惩罚 + 车钩力峰值最小化（创新点）。
    E16/E16.1：循环制动引导 + 缓解时机增强。
    """
    vel = float(env.dynamics.vel[0])
    # 【2026-09-30 口径统一】reward 塑形刻意保留**每车净力**口径（不改，避免作废既有 checkpoint）
    coupler = np.abs(env.dynamics._coupler_forces())
    coupler_peak = float(np.max(coupler)) if len(coupler) else 0.0

    reward = 0.0
    if vel < V_MIN_MPS or vel > V_MAX_MPS:
        reward -= 20.0   # Rc（超出 [40,80] 限速）
    else:
        reward += 5.0    # Rd（在限速内）

    # E16 循环制动引导
    v_kmh = vel * 3.6
    if v_kmh > 75.0 and throttle >= 0.0:
        reward -= 2.0
    elif v_kmh < 55.0 and throttle <= 0.0:
        reward -= 2.0
    elif v_kmh < 48.0 and throttle <= 0.0:
        reward -= 3.0    # E16.1 低于48仍不缓解+牵引 → 强惩罚
    elif 48.0 <= v_kmh <= 52.0 and throttle <= 0.0:
        reward -= 1.0    # E16.1 应缓解未缓解 → 轻惩罚
    elif v_kmh < 52.0 and throttle > 0.0:
        reward += 1.0    # E16.1 低速度缓解+牵引 → 正向

    if brake_engaged:
        reward -= 0.5    # 空气制动距离惩罚（Zhang2024 La）

    if coupler_peak > env.coupler_force_limit_n:
        over_ratio = (coupler_peak - env.coupler_force_limit_n) / env.coupler_force_limit_n
        reward -= 5.0 * over_ratio
    reward -= 0.2 * (coupler_peak / env.coupler_force_limit_n)  # 车钩力峰值最小化
    return reward


def warm_start_bc(
    agent: MAPPOAgent,
    env: TrainFormationEnv,
    num_vehicles: int,
    obs_fn,
    v_max: float,
    v_min: float,
    episodes: int = 3,
    bc_epochs: int = 5,
    brake_notch: float = -0.8,
    max_steps: int = 1500,
):
    """行为克隆 warm start：用规则循环制动采集 (obs, action)，预训练策略。

    E15：RL 第1层在缓解波下学到"持续牵引"而非"循环制动"。用规则循环制动
    做行为克隆初始化，RL 再微调。
    """
    import torch
    from src.controllers.low_level_controller import TrainLowLevelController
    ctrl = TrainLowLevelController(num_vehicles=num_vehicles, dt=env.dt,
                                   coupler_force_limit_n=env.coupler_force_limit_n,
                                   enforce_coupler=True)
    bc_obs, bc_acts = [], []
    for ep in range(episodes):
        env.reset(options={'speed': 80.0 / 3.6})
        obs = obs_fn(env)
        done = False
        step = 0
        while not done and step < max_steps:
            rule = ctrl.get_action_cyclic_braking(env, v_max, v_min,
                                                  brake_notch=brake_notch,
                                                  release_throttle=0.5)
            throttle = float(np.clip(rule[0], -1, 1))
            bc_obs.append(obs.flatten())
            bc_acts.append(throttle)
            obs, r, term, trunc, info = env.step(np.full(num_vehicles, throttle))
            done = term or trunc
            obs = obs_fn(env)
            step += 1
    bc_obs = np.array(bc_obs, dtype=np.float32)
    bc_acts = np.array(bc_acts, dtype=np.float32)
    logger.info(f"Warm start 行为克隆: 采集 {len(bc_obs)} 条，预训练 {bc_epochs} epochs")
    bc_obs_t = torch.tensor(bc_obs, dtype=torch.float32, device=agent.device)
    bc_acts_t = torch.tensor(bc_acts.reshape(-1, 1), dtype=torch.float32, device=agent.device)
    for epoch in range(bc_epochs):
        mean, log_std = agent.policy(bc_obs_t)
        dist = torch.distributions.Normal(mean, log_std.exp())
        log_prob = dist.log_prob(bc_acts_t).sum(dim=-1)
        entropy = dist.entropy().sum(dim=-1).mean()
        loss = -(log_prob.mean() + 0.01 * entropy)
        agent.optimizer.zero_grad()
        loss.backward()
        torch.nn.utils.clip_grad_norm_(agent.policy.parameters(), 0.5)
        agent.optimizer.step()
    logger.info(f"Warm start 完成，BC loss={loss.item():.3f}")