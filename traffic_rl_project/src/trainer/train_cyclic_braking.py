"""
【第1层】单列循环制动 MAPPO 训练（对齐 Zhang2024 DQN）。

Zhang2024（Algorithms 2024,17,190）在朔黄线真实线路上用 DQN 学**单列循环制动**：
- 智能体 = 1 个（机车/整列），动作 = 制动设置（空气制动 + 电制动）
- 目标 = 在长大下坡把速度控制在 [40,80] km/h（V_min~V_max）
- 奖励 = 速度超限惩罚 + 最小化空气制动距离（维护成本）

本脚本用**我们的 MAPPO** 在同一场景学循环制动，并**显式建模车钩力**（Zhang2024 忽略）：
- 智能体 = 整列（1 个），列级 throttle ∈ [-1,1]（正=机车牵引，负=制动）
- obs = 机车速度/速度误差/位置/车钩力峰值（对齐 Zhang2024 s=[P,V,T] + 我们的车钩力增量）
- 奖励 = Zhang2024 式（超速/低速惩罚 + 鼓励缓解减制动距离）+ 我们的车钩力约束
- 场景 = shuozhou_23800 朔黄线真实剖面 + 万吨 1+0 编组

对照：Zhang2024 制动距离 -2.1%、平均速度 +7%（DQN vs Q-learning）。
我们验证：MAPPO 能否学会循环制动，且车钩力守住 1000kN（Zhang2024 无此指标）。

用法（WSL）：
    python src/trainer/train_cyclic_braking.py --episodes 300 --grade shuozhou_23800
"""

import sys
import os
from pathlib import Path
import time
import argparse
import logging
from typing import Dict

sys.path.append(str(Path(__file__).parent.parent.parent))

import numpy as np
import torch

logging.basicConfig(level=logging.INFO, format='%(message)s')
logger = logging.getLogger('CyclicBraking')

from src.environments.train_env import TrainFormationEnv
from src.algorithms.mappo_agent import MAPPOAgent


# Zhang2024 限速参数
V_MAX_MPS = 80.0 / 3.6      # 80 km/h 最高限速
V_MIN_MPS = 40.0 / 3.6      # 40 km/h 最低缓解速度


def set_seed(seed: int):
    np.random.seed(seed)
    torch.manual_seed(seed)
    if torch.cuda.is_available():
        torch.cuda.manual_seed(seed)


def cyclic_obs(env) -> np.ndarray:
    """整列观测（1 智能体）：[速度, 速度误差, 位置(缩放), 车钩力峰值归一化]。

    对齐 Zhang2024 s=[P,V,T]（位置/速度/时间），加我们的车钩力增量。
    """
    vel = float(env.dynamics.vel[0])          # 机车速度（m/s）
    coupler = np.abs(env.dynamics._coupler_forces())
    coupler_peak = float(np.max(coupler)) if len(coupler) else 0.0
    return np.array([
        [vel, vel - env.target_speed, env.dynamics.pos[0] * 0.0001,
         coupler_peak / env.coupler_force_limit_n],
    ], dtype=np.float32)


# E17 离散档位表（对齐重载列车 Tang2020/VCTS：牵引+惰行+制动）
# 档位值（throttle）：[大牵引, 中牵引, 小牵引, 惰行, MIN制动, SERVICE制动, 紧急制动]
NOTCH_TABLE = np.array([0.7, 0.4, 0.2, 0.0, -0.3, -0.5, -0.8])


def quantize_to_notch(continuous: float) -> float:
    """连续动作量化到最近离散档位（对齐领域标准，避免连续策略mean塌缩）。"""
    idx = int(np.argmin(np.abs(NOTCH_TABLE - continuous)))
    return float(NOTCH_TABLE[idx])


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

    E15：RL 第1层在缓解波下学到"持续牵引"而非"循环制动"（动作均值+0.61，
    掉速+车钩力1849kN超限）。用规则循环制动（get_action_cyclic_braking，稳定
    523kN）做行为克隆初始化，让策略从"规则式循环制动"开始，RL 再微调优化
    （如车钩力约束/制动时机）。规则循环制动能稳定是因为"中间维持上次动作"。
    """
    from src.controllers.low_level_controller import TrainLowLevelController
    ctrl = TrainLowLevelController(num_vehicles=num_vehicles, dt=env.dt,
                                   coupler_force_limit_n=env.coupler_force_limit_n,
                                   enforce_coupler=True)
    bc_obs = []
    bc_acts = []
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
    bc_obs = np.array(bc_obs, dtype=np.float32)      # [N, obs_dim]
    bc_acts = np.array(bc_acts, dtype=np.float32)    # [N, 1]
    logger.info(f"Warm start 行为克隆: 采集 {len(bc_obs)} 条 (obs, action)，预训练策略 {bc_epochs} epochs")
    # bc_obs 已是 batch（[N,4]），直接用 tensor，不 reshape 成单obs
    bc_obs_t = torch.tensor(bc_obs, dtype=torch.float32, device=agent.device)
    bc_acts_t = torch.tensor(bc_acts.reshape(-1, 1), dtype=torch.float32, device=agent.device)
    for epoch in range(bc_epochs):
        mean, log_std = agent.policy(bc_obs_t)
        dist = torch.distributions.Normal(mean, log_std.exp())
        log_prob = dist.log_prob(bc_acts_t).sum(dim=-1)
        # BC loss = -log_prob（最大化模仿规则动作），加小熵项防确定性塌缩
        entropy = dist.entropy().sum(dim=-1).mean()
        loss = -(log_prob.mean() + 0.01 * entropy)
        agent.optimizer.zero_grad()
        loss.backward()
        torch.nn.utils.clip_grad_norm_(agent.policy.parameters(), 0.5)
        agent.optimizer.step()
    logger.info(f"Warm start 完成，BC loss={loss.item():.3f}")


def cyclic_reward(env, prev_speed, prev_coupler_peak, brake_engaged, throttle) -> float:
    """奖励：对齐 Zhang2024（速度约束 + 制动距离）+ 我们的车钩力 + 循环制动引导。

    Zhang2024: 速度<40 或 >80 → 惩罚 Rc；空气制动中 → 0；缓解 → +Rd（鼓励减制动距离）
    我们加：车钩力超限成比例惩罚 + 车钩力峰值最小化（创新点）。
    E16 加循环制动引导：速度接近上限不制动→惩罚（引导制动降速），速度低于中值不牵引
    →惩罚（引导牵引恢复）。修复 RL 只学"贴上限[76,81]"不学"40-80完整循环"。
    """
    vel = float(env.dynamics.vel[0])
    coupler = np.abs(env.dynamics._coupler_forces())
    coupler_peak = float(np.max(coupler)) if len(coupler) else 0.0

    # 速度约束（Zhang2024 Eq.22）
    reward = 0.0
    if vel < V_MIN_MPS or vel > V_MAX_MPS:
        reward -= 20.0   # Rc（超出 [40,80] 限速）
    else:
        reward += 5.0    # Rd（在限速内，鼓励；Zhang2024 缓解时+5，制动时0）

    # E16 循环制动引导（对齐规则循环制动：上限制动/下限牵引/中值缓解）：
    # - 速度接近上限(>75km/h)但不制动 → 惩罚（引导制动降速，避免贴上限持续牵引掉速）
    # - 速度低于中值(<55km/h)但不牵引 → 惩罚（引导牵引恢复，避免低速掉速）
    # E16.1 缓解时机增强（2026-08-21，修复低40掉速）：
    #   诊断显示第1层策略"50 就强制动、跌穿40才牵引"→ 缓解太晚导致低40。
    #   增强：速度进入 48-52 区间未开始缓解→惩罚（引导提前缓解）；<48 必须缓解+牵引
    #   （防跌穿40），且缓解加牵引在低速度区给正向（鼓励主动恢复速度）。
    v_kmh = vel * 3.6
    if v_kmh > 75.0 and throttle >= 0.0:
        reward -= 2.0    # 应制动未制动
    elif v_kmh < 55.0 and throttle <= 0.0:
        reward -= 2.0    # 应牵引未牵引
    elif v_kmh < 48.0 and throttle <= 0.0:
        reward -= 3.0    # E16.1 低于48仍不缓解+牵引 → 强惩罚（引导提前缓解，避免跌穿40）
    elif 48.0 <= v_kmh <= 52.0 and throttle <= 0.0:
        reward -= 1.0    # E16.1 接近下限应开始缓解但仍在制动 → 轻惩罚（引导缓解时机前移）
    elif v_kmh < 52.0 and throttle > 0.0:
        reward += 1.0    # E16.1 低速度区缓解+牵引 → 正向（鼓励主动恢复速度，对抗下坡惯性）

    # 空气制动距离惩罚（Zhang2024 La，本环境用制动档位持续时间近似）
    if brake_engaged:
        reward -= 0.5    # 空气制动中，维护成本惩罚（Zhang2024 制动距离=0奖励，这里是负）

    # 我们的创新点：车钩力约束
    if coupler_peak > env.coupler_force_limit_n:
        over_ratio = (coupler_peak - env.coupler_force_limit_n) / env.coupler_force_limit_n
        reward -= 5.0 * over_ratio
    reward -= 0.2 * (coupler_peak / env.coupler_force_limit_n)  # 车钩力峰值最小化

    return reward


def train(
    episodes: int = 300,
    consist_preset: str = '10kt_1plus0',
    grade_profile: str = 'shuozhou_23800',
    max_steps: int = 1500,     # Zhang2024 计划运行 1500s
    init_speed: float = 65.0 / 3.6,
    warm_start: bool = False,  # 用规则循环制动做行为克隆预训练（E15修复持续牵引问题）
    lr: float = 5e-5,
    entropy: float = 0.005,
    epochs: int = 4,
    batch_size: int = 64,
    device: str = None,
    seed: int = 0,
    release_sync: bool = True,
    checkpoint_dir: str = 'outputs/checkpoints',
    results_dir: str = 'outputs/results',
):
    device = device or ('cuda' if torch.cuda.is_available() else 'cpu')
    set_seed(seed)

    env_cfg = {
        'consist_preset': consist_preset,
        'grade_profile': grade_profile,
        'target_speed': 20.0,
        'max_steps': max_steps,
        'enable_safety': True,
        'dt': 0.1,
        # E7：第1层用同步缓解（简化物理），RL 能学会循环制动不掉速。
        # 第2层用缓解波（物理真实，保留"缓解后车钩力最大"机制）。
        'release_sync': release_sync,
    }
    env = TrainFormationEnv(env_cfg)
    num_vehicles = env.num_vehicles
    obs_dim = 4   # [速度, 速度误差, 位置, 车钩力峰值]（1 智能体）

    logger.info("=" * 70)
    logger.info("第1层：单列循环制动 MAPPO 训练（对齐 Zhang2024 DQN）")
    logger.info("=" * 70)
    logger.info(f"编组: {consist_preset} ({num_vehicles}节, {sum(v.mass_t for v in env.dynamics.consist.vehicles):.0f}t)")
    logger.info(f"线路剖面: {grade_profile} (朔黄线 23.8km)")
    logger.info(f"限速范围: {V_MIN_MPS*3.6:.0f}~{V_MAX_MPS*3.6:.0f} km/h")
    logger.info(f"智能体: 整列×1, obs={obs_dim}维, act=1维（列级throttle）")
    logger.info(f"设备: {device}")

    agent = MAPPOAgent(
        num_drones=1,               # 整列 1 个智能体
        obs_per_drone=obs_dim,
        act_per_drone=1,
        learning_rate=lr,
        gamma=0.99,
        gae_lambda=0.95,
        clip_epsilon=0.2,
        entropy_coef=entropy,
        value_coef=0.5,
        epochs=epochs,
        batch_size=batch_size,
        max_grad_norm=0.5,
        device=device,
        use_gae=True,
        use_clipped_value_loss=True,
    )

    Path(checkpoint_dir).mkdir(parents=True, exist_ok=True)
    Path(results_dir).mkdir(parents=True, exist_ok=True)

    episode_rewards = []
    episode_peak_coupler = []
    episode_violations = []
    episode_v_range = []
    best_reward = float('-inf')

    logger.info("=" * 70)
    logger.info("开始训练")
    logger.info("=" * 70)
    start_time = time.time()

    # E15：规则循环制动 warm start（修复 RL 学到"持续牵引"而非"循环制动"）
    if warm_start:
        warm_start_bc(agent, env, num_vehicles, cyclic_obs,
                      V_MAX_MPS, V_MIN_MPS, brake_notch=-0.8)

    for ep in range(episodes):
        env.reset(options={'speed': init_speed})  # 初始速度（默认 65 km/h Zhang2024；80=立即循环制动）
        obs = cyclic_obs(env)  # 用自定义单智能体观测 (1,4)，不用环境默认 (101,4)
        done = False
        ep_reward = 0.0
        ep_peak = 0.0
        ep_viol = 0
        v_min_ep = float('inf')
        v_max_ep = 0.0
        step = 0

        while not done and step < max_steps:
            flat_obs = obs.flatten()
            actions, log_prob = agent.select_actions(flat_obs)
            # E17 离散档位动作（对齐 Zhang2024/Tang2020/VCTS 重载列车领域标准）：
            # 连续策略输出 ∈[-1,1] 量化到最近离散档位（牵引3档+惰行+制动3档）。
            # 离散动作天然避免连续策略 mean 塌缩导致的 deterministic 掉速问题，
            # 且对齐领域"档位控制"惯例。
            throttle = quantize_to_notch(float(np.clip(actions[0], -1.0, 1.0)))
            # 实际执行离散档位 → 用档位值重算 log_prob（V5.1 教训：动作被量化后
            # 必须用实际执行动作重算 log_prob，保证重要性采样一致）
            if abs(throttle - float(actions[0])) > 1e-4:
                log_prob = agent.get_log_prob(flat_obs, np.array([throttle]))
            action_for_env = np.full(num_vehicles, throttle)

            value = agent.get_value(flat_obs)
            # 记录制动状态（throttle<0 = 制动）
            brake_engaged = throttle < -0.1
            prev_speed = float(env.dynamics.vel[0])

            next_obs, reward, terminated, truncated, info = env.step(action_for_env)

            # 安全层修正后重算 log_prob
            executed = info.get('executed_actions')
            if executed is not None and info.get('actions_modified', True):
                # executed 是 101 维，取第0节即可（整列统一）
                exec_throttle = np.array([executed[0]])
                actions = exec_throttle
                log_prob = agent.get_log_prob(flat_obs, actions)

            # 用自定义循环制动奖励（覆盖环境默认奖励，因 Zhang2024 奖励更贴合）
            reward = cyclic_reward(env, prev_speed, ep_peak, brake_engaged, throttle)

            done = terminated or truncated
            agent.store_transition(flat_obs, actions, reward, log_prob, done, value)

            ep_reward += reward
            ep_peak = max(ep_peak, info.get('coupler_force_peak', 0))
            ep_viol = info.get('coupler_limit_violations', 0)
            v = float(env.dynamics.vel[0])
            v_min_ep = min(v_min_ep, v)
            v_max_ep = max(v_max_ep, v)
            obs = cyclic_obs(env)  # 用自定义单智能体观测 (1,4)
            step += 1

        metrics = agent.update()

        episode_rewards.append(ep_reward)
        episode_peak_coupler.append(ep_peak / 1e3)
        episode_violations.append(ep_viol)
        episode_v_range.append((v_min_ep * 3.6, v_max_ep * 3.6))
        if ep_reward > best_reward:
            best_reward = ep_reward
            # checkpoint 命名含限速区间，避免不同限速训练互相覆盖（8/18 教训：
            # [45,65]重训覆盖了[40,80]成功模型导致后续评估出错）
            ckpt_name = (f"cyclic_mappo_best_seed{seed}_v{int(V_MIN_MPS*3.6)}-{int(V_MAX_MPS*3.6)}"
                         f"_init{int(init_speed*3.6)}.pt")
            agent.save(str(Path(checkpoint_dir) / ckpt_name))

        if (ep + 1) % 10 == 0 or ep == episodes - 1:
            recent = np.mean(episode_rewards[-10:])
            recent_peak = np.mean(episode_peak_coupler[-10:])
            recent_viol = np.mean(episode_violations[-10:])
            v_lo, v_hi = episode_v_range[-1]
            logger.info(
                f"Ep {ep+1}/{episodes} | Reward {ep_reward:+.1f} (avg {recent:+.1f}) | "
                f"best {best_reward:+.1f} | peakCoupler {recent_peak:.0f}kN | "
                f"viol {recent_viol:.1f} | v[{v_lo:.0f},{v_hi:.0f}]km/h | "
                f"loss {metrics.get('total_loss',0):.3f}"
            )
            sys.stdout.flush()

    total_time = time.time() - start_time
    logger.info("=" * 70)
    logger.info(f"训练完成！总耗时 {total_time:.1f}s ({total_time/60:.1f}min)")
    logger.info(f"最佳奖励: {best_reward:.2f}")
    logger.info(f"最终平均奖励: {np.mean(episode_rewards[-10:]):.2f}")
    logger.info(f"平均车钩力峰值: {np.mean(episode_peak_coupler[-10:]):.1f} kN")
    logger.info(f"平均超限: {np.mean(episode_violations[-10:]):.1f} 次")
    logger.info(f"末回合速度范围: {episode_v_range[-1][0]:.0f}~{episode_v_range[-1][1]:.0f} km/h")
    logger.info(f"模型已保存: {checkpoint_dir}")
    logger.info("=" * 70)

    return {
        'rewards': episode_rewards,
        'peak_coupler_kN': episode_peak_coupler,
        'violations': episode_violations,
        'v_range': episode_v_range,
        'best_reward': best_reward,
        'num_vehicles': num_vehicles,
        'grade_profile': grade_profile,
    }


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='单列循环制动 MAPPO 训练')
    parser.add_argument('--episodes', type=int, default=300)
    parser.add_argument('--preset', type=str, default='10kt_1plus0')
    parser.add_argument('--grade', type=str, default='shuozhou_23800')
    parser.add_argument('--max_steps', type=int, default=1500)
    parser.add_argument('--lr', type=float, default=5e-5)
    parser.add_argument('--entropy', type=float, default=0.005)
    parser.add_argument('--device', type=str, default=None)
    parser.add_argument('--seed', type=int, default=0)
    parser.add_argument('--v_max', type=float, default=80.0 / 3.6,
                        help='限速上限 m/s（默认 80 km/h，对齐 Zhang2024）')
    parser.add_argument('--v_min', type=float, default=40.0 / 3.6,
                        help='限速下限 m/s（默认 40 km/h，对齐 Zhang2024）')
    parser.add_argument('--no_release_sync', action='store_true',
                        help='使用缓解波传播（物理真实，默认关闭=同步缓解；第2层用缓解波）')
    parser.add_argument('--init_speed_kmh', type=float, default=65.0,
                        help='初始速度 km/h（默认 65，Zhang2024；80=立即触发循环制动）')
    parser.add_argument('--warm_start', action='store_true',
                        help='用规则循环制动做行为克隆预训练策略（E15修复持续牵引问题）')
    args = parser.parse_args()

    V_MAX_MPS = args.v_max
    V_MIN_MPS = args.v_min
    train(
        episodes=args.episodes,
        consist_preset=args.preset,
        grade_profile=args.grade,
        max_steps=args.max_steps,
        init_speed=args.init_speed_kmh / 3.6,
        warm_start=args.warm_start,
        lr=args.lr,
        entropy=args.entropy,
        device=args.device,
        seed=args.seed,
        release_sync=not args.no_release_sync,
    )
