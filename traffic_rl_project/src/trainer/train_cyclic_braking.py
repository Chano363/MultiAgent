"""
【legacy 2026-09-06】框架化后对应 configs/experiments/l1_cyclic_mappo.yaml；本脚本保留为 append-only
（其 cyclic_obs/cyclic_reward 等被评估脚本 import，勿删）。语义符号已镜像至 src/trainer/specs/cyclic_spec.py。
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
    python src/trainer/train_cyclic_braking.py --episodes 300 --grade shuozhou_ningwuxi_beidaniu_49km
    # 默认 max_steps=15000；49.6km 完整纵断面全程需按步长折算（见下）
"""

import sys
import os
from pathlib import Path
import time
import argparse
import logging
from typing import Dict


import numpy as np
import torch
from src.utils.seed import set_seed

logging.basicConfig(level=logging.INFO, format='%(message)s')
logger = logging.getLogger('CyclicBraking')

from src.environments.train_env import TrainFormationEnv
from src.algorithms.mappo_agent import MAPPOAgent
from src.physics_config import PhysicsConfig
from src.physics_governance import SimCase, official_world_config
from src.metadata import save_metadata, build_metadata


# Zhang2024 限速参数
V_MAX_MPS = 80.0 / 3.6      # 80 km/h 最高限速
V_MIN_MPS = 40.0 / 3.6      # 40 km/h 最低缓解速度




def cyclic_obs(env) -> np.ndarray:
    """整列观测（1 智能体）：[速度, 速度误差, 位置(缩放), 车钩力峰值归一化]。

    对齐 Zhang2024 s=[P,V,T]（位置/速度/时间），加我们的车钩力增量。
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
    # 【2026-09-30 口径统一】reward 塑形刻意保留**每车净力**口径（不改，避免作废既有 checkpoint）
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
    max_steps: int = 15000,   # 完整协议（对齐 MARL 评估 15000 步≈23.8km，控制变量；原 1500 步≈2.5km 太短）
    init_speed: float = 65.0 / 3.6,
    warm_start: bool = False,  # 用规则循环制动做行为克隆预训练（E15修复持续牵引问题）
    lr: float = 5e-5,
    entropy: float = 0.005,
    epochs: int = 4,
    batch_size: int = 64,
    device: str = None,
    seed: int = 0,
    curriculum: str = None,
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
    # 权威 metadata（git_commit / physics_version / simcase / 全物理配置）：
    # L1 原只在 save_training_artifacts 内嵌文本标签，缺权威 metadata.json →
    # 补上与 train_fleet 一致的落盘，保证"结果以 metadata 为准"可追溯。
    hp = {
        "algorithm": "mappo",
        "episodes": episodes, "consist_preset": consist_preset,
        "grade_profile": grade_profile, "max_steps": max_steps,
        "init_speed_kmh": init_speed * 3.6, "warm_start_bc": warm_start,
        "lr": lr, "entropy": entropy, "epochs": epochs,
        "batch_size": batch_size, "seed": seed, "curriculum": curriculum,
    }
    # 运行派生（2026-09-30）：metadata 的 physics 块随本次 run 的编组固化
    world_cfg = official_world_config(PhysicsConfig(), env_cfg={'consist_preset': consist_preset})
    save_metadata(results_dir, project_root=str(Path(__file__).parent.parent.parent),
                  case=SimCase('official').value, world_cfg=world_cfg,
                  seed=seed, entry=__file__, extra={"hyperparameters": hp})
    # 自包含 checkpoint：同一份权威 metadata 嵌入每个 .pt（对标 YOLO best.pt）
    ckpt_meta = build_metadata(project_root=str(Path(__file__).parent.parent.parent),
                               case=SimCase('official').value,
                               world_cfg=world_cfg,
                               seed=seed, entry=__file__, extra={"hyperparameters": hp})

    episode_rewards = []
    episode_peak_coupler = []
    episode_violations = []
    episode_v_range = []
    best_reward = float('-inf')

    # curriculum：按全局回合号递增 horizon（镜像 train_fleet，平衡训练成本）。
    #   相对格式 '300-1000-15000'：按 episodes 均分（如 300ep → 每段100：ep<100=300步，
    #   ep<200=1000步，之后=15000步）；绝对格式 '1000:66,3000:132'：ep66 起=1000步，
    #   ep132 起=3000步。均以【全局回合号】判定，末尾仍完整时域（不破坏协议）。
    cur_plan = []
    if curriculum:
        if ':' in curriculum:
            for part in curriculum.split(','):
                h_str, e_str = part.strip().split(':')
                cur_plan.append((int(e_str), int(h_str)))
            cur_plan.sort()
            logger.info(f"curriculum 绝对边界: {cur_plan}")
        else:
            stages = [int(x) for x in curriculum.split('-')]
            per_stage = max(1, episodes // len(stages))
            cur_plan = [(i * per_stage, h) for i, h in enumerate(stages)]
            logger.info(f"curriculum 分段: {stages}（每段约 {per_stage} ep）")

    def _resolve_horizon(gep: int) -> int:
        """按全局回合号返回该回合的 max_steps（curriculum 生效）。"""
        h = max_steps
        for e_bound, h_stage in cur_plan:
            if gep >= e_bound:
                h = h_stage
        return h

    logger.info("=" * 70)
    logger.info("开始训练")
    logger.info("=" * 70)
    start_time = time.time()

    # E15：规则循环制动 warm start（修复 RL 学到"持续牵引"而非"循环制动"）
    if warm_start:
        warm_start_bc(agent, env, num_vehicles, cyclic_obs,
                      V_MAX_MPS, V_MIN_MPS, brake_notch=-0.8)

    for ep in range(episodes):
        cur_horizon = _resolve_horizon(ep)
        if ep == 0 or cur_horizon != _resolve_horizon(ep - 1):
            logger.info(f"curriculum: ep{ep + 1} → horizon {cur_horizon} 步")
        env.reset(options={'speed': init_speed})  # 初始速度（默认 65 km/h Zhang2024；80=立即循环制动）
        obs = cyclic_obs(env)  # 用自定义单智能体观测 (1,4)，不用环境默认 (101,4)
        done = False
        ep_reward = 0.0
        ep_peak = 0.0
        ep_viol = 0
        v_min_ep = float('inf')
        v_max_ep = 0.0
        step = 0

        while not done and step < cur_horizon:
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
            agent.save(str(Path(checkpoint_dir) / ckpt_name), metadata=ckpt_meta)

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
            # 【2026-08-30】训练历史落盘 + 学习曲线图（论文/PPT 用，前台中断不丢数据）
            from src.trainer.train_fleet import save_training_artifacts
            save_training_artifacts(
                episode_rewards, episode_peak_coupler, episode_violations,
                meta={
                    'seed': seed, 'episodes': episodes, 'max_steps': max_steps,
                    'grade_profile': grade_profile, 'warm_start': warm_start,
                    'init_speed_kmh': init_speed * 3.6,
                    'v_range_kmh': [V_MIN_MPS * 3.6, V_MAX_MPS * 3.6],
                    'best_reward': float(best_reward),
                    'physics': 'R0(2026-09-06)+MT2统一(2026-09-07): 全列MT-2 Stribeck 750/500 + 卸载刚度 + 牵规β_c + 并行波速 + 段间衰减D + 两段式缓解τ=6s + Newmark-β',
                },
                results_dir=results_dir,
                figures_dir='outputs/figures',
                tag=f"l1_seed{seed}",
            )

    total_time = time.time() - start_time
    logger.info("=" * 70)
    logger.info(f"训练完成！总耗时 {total_time:.1f}s ({total_time/60:.1f}min)")
    logger.info(f"最佳奖励: {best_reward:.2f}")
    logger.info(f"最终平均奖励: {np.mean(episode_rewards[-10:]):.2f}")
    logger.info(f"平均车钩力峰值: {np.mean(episode_peak_coupler[-10:]):.1f} kN")
    logger.info(f"平均超限: {np.mean(episode_violations[-10:]):.1f} 次")
    logger.info(f"末回合速度范围: {episode_v_range[-1][0]:.0f}~{episode_v_range[-1][1]:.0f} km/h")
    logger.info(f"模型已保存: {checkpoint_dir}")
    # 【防漏】训练结束强制校验权威 metadata.json 已生成（入口已 save_metadata）
    from src.metadata import assert_training_metadata
    assert_training_metadata(results_dir)
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
    parser.add_argument('--max_steps', type=int, default=15000,
                        help='训练回合步数（15000≈23.8km完整协议，与 MARL 评估对齐控制变量）')
    parser.add_argument('--lr', type=float, default=5e-5)
    parser.add_argument('--entropy', type=float, default=0.005)
    parser.add_argument('--device', type=str, default=None)
    parser.add_argument('--seed', type=int, default=0)
    parser.add_argument('--v_max', type=float, default=80.0 / 3.6,
                        help='限速上限 m/s（默认 80 km/h，对齐 Zhang2024）')
    parser.add_argument('--v_min', type=float, default=40.0 / 3.6,
                        help='限速下限 m/s（默认 40 km/h，对齐 Zhang2024）')
    parser.add_argument('--init_speed_kmh', type=float, default=65.0,
                        help='初始速度 km/h（默认 65，Zhang2024；80=立即触发循环制动）')
    parser.add_argument('--warm_start', action='store_true',
                        help='用规则循环制动做行为克隆预训练策略（E15修复持续牵引问题）')
    parser.add_argument('--curriculum', type=str, default=None,
                        help='递增 horizon："300-1000-15000"（相对，按episodes均分）或 '
                             '"15000:200"（绝对，全局ep边界），平衡训练成本')
    parser.add_argument('--checkpoint_dir', type=str, default='outputs/checkpoints',
                        help='checkpoint 输出目录（重训时用新目录，避免覆盖旧模型）')
    parser.add_argument('--results_dir', type=str, default='outputs/results',
                        help='训练历史输出目录')
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
        curriculum=args.curriculum,
        checkpoint_dir=args.checkpoint_dir,
        results_dir=args.results_dir,
    )
