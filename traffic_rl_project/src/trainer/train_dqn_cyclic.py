"""
单列 DQN 训练：学循环制动（对齐 Zhang2024 DQN），用作论文 baseline（M-DQN）。

Zhang2024（Algorithms 2024,17,190）用 DQN 在朔黄线学单列循环制动（忽略车钩力）。
本脚本用 DQN 在同一场景学循环制动，obs 含车钩力（对齐我们项目），动作=离散制动设置。
多列场景中每列独立 DQN（无协同）→ 对比 M1（MAPPO 协同）。

用法（WSL）：
    python src/trainer/train_dqn_cyclic.py --episodes 300 --grade shuozhou_23800
"""
import sys
import os
from pathlib import Path
import argparse
import logging

sys.path.append(str(Path(__file__).parent.parent.parent))

import numpy as np
import torch

logging.basicConfig(level=logging.INFO, format='%(message)s')
logger = logging.getLogger('DQNCyclic')

from src.environments.train_env import TrainFormationEnv
from src.algorithms.dqn_agent import DQNAgent
from src.trainer.train_cyclic_braking import cyclic_obs, cyclic_reward, V_MAX_MPS, V_MIN_MPS


def set_seed(seed: int):
    np.random.seed(seed)
    torch.manual_seed(seed)
    if torch.cuda.is_available():
        torch.cuda.manual_seed_all(seed)


def train(
    episodes: int = 300,
    consist_preset: str = '10kt_1plus0',
    grade_profile: str = 'shuozhou_23800',
    max_steps: int = 3000,
    lr: float = 1e-4,
    seed: int = 0,
    init_speed_kmh: float = 65.0,
    checkpoint_dir: str = 'outputs/checkpoints',
    log_file: str = None,
):
    set_seed(seed)
    # 单列环境（10kt 1+0，朔黄线）
    env = TrainFormationEnv({
        'consist_preset': consist_preset,
        'grade_profile': grade_profile,
        'max_steps': max_steps,
        'dt': 0.1,
    })
    obs_dim = 4   # [速度, 速度误差, 位置, 车钩力峰值]（对齐 Zhang2024 + 车钩力）
    agent = DQNAgent(obs_dim=obs_dim, num_actions=4, lr=lr, device='cuda')
    num_vehicles = env.num_vehicles

    episode_rewards = []
    episode_peaks = []
    best_avg = -1e9
    best_ckpt = None

    for ep in range(episodes):
        env.reset(options={'speed': init_speed_kmh / 3.6})
        obs = cyclic_obs(env).flatten()
        done = False
        ep_reward = 0.0
        ep_peak = 0.0
        prev_speed = float(env.dynamics.vel[0])
        prev_coupler = 0.0
        brake_engaged = False
        step = 0
        while not done and step < max_steps:
            act_idx = agent.select_action(obs, eval_mode=False)
            throttle = agent.action_to_throttle(act_idx)
            reward = cyclic_reward(env, prev_speed, prev_coupler, brake_engaged, throttle)
            obs2, r, term, trunc, info = env.step(np.full(num_vehicles, throttle))
            # 用自定义奖励（cyclic_reward 更合适循环制动学习）
            next_obs = cyclic_obs(env).flatten()
            done = term or trunc
            agent.store_transition(obs, act_idx, reward, next_obs, done)
            loss = agent.update()
            obs = next_obs
            prev_speed = float(env.dynamics.vel[0])
            coupler = np.abs(env.dynamics._coupler_forces())
            prev_coupler = float(np.max(coupler)) if len(coupler) else 0.0
            ep_reward += reward
            ep_peak = max(ep_peak, info['coupler_force_peak'] / 1e3)
            if step == 0:
                brake_engaged = throttle < 0
            step += 1

        episode_rewards.append(ep_reward)
        episode_peaks.append(ep_peak)

        # 每 10 ep 评估（eval_mode，无探索）
        if (ep + 1) % 10 == 0 or ep == episodes - 1:
            eval_reward = 0.0
            eval_peak = 0.0
            eval_coll = 0
            env.reset(options={'speed': init_speed_kmh / 3.6})
            o = cyclic_obs(env).flatten()
            d = False
            es = 0
            pv = float(env.dynamics.vel[0])
            pc = 0.0
            be = False
            while not d and es < max_steps:
                ai = agent.select_action(o, eval_mode=True)
                th = agent.action_to_throttle(ai)
                rw = cyclic_reward(env, pv, pc, be, th)
                _, _, term, trunc, info = env.step(np.full(num_vehicles, th))
                o = cyclic_obs(env).flatten()
                pv = float(env.dynamics.vel[0])
                cou = np.abs(env.dynamics._coupler_forces())
                pc = float(np.max(cou)) if len(cou) else 0.0
                d = term or trunc
                eval_reward += rw
                eval_peak = max(eval_peak, info['coupler_force_peak'] / 1e3)
                es += 1
            avg_reward = np.mean(episode_rewards[-10:]) if episode_rewards else 0.0
            logger.info(
                f"Ep {ep+1}/{episodes} | Reward {ep_reward:+.0f} (avg {avg_reward:+.0f}) | "
                f"eval {eval_reward:+.0f} | peak {eval_peak:.0f}kN | eps {agent.eps:.2f} | loss {loss:.3f}"
            )
            if eval_reward > best_avg and eval_peak < 1000.0:
                best_avg = eval_reward
                best_ckpt = (ep + 1, eval_reward, eval_peak)
                ckpt_name = f"dqn_cyclic_best_seed{seed}.pt"
                agent.save(str(Path(checkpoint_dir) / ckpt_name))
                logger.info(f"  >> 保存 best DQN: {ckpt_name} (eval={eval_reward:+.0f}, peak={eval_peak:.0f}kN)")

    logger.info(f"训练完成。best eval={best_ckpt}")
    if best_ckpt:
        logger.info(f"best: Ep{best_ckpt[0]} eval={best_ckpt[1]:+.0f} peak={best_ckpt[2]:.0f}kN "
                    f"-> outputs/checkpoints/dqn_cyclic_best_seed{seed}.pt")


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--episodes', type=int, default=300)
    parser.add_argument('--preset', type=str, default='10kt_1plus0')
    parser.add_argument('--grade', type=str, default='shuozhou_23800')
    parser.add_argument('--max_steps', type=int, default=3000)
    parser.add_argument('--lr', type=float, default=1e-4)
    parser.add_argument('--seed', type=int, default=0)
    parser.add_argument('--init_speed_kmh', type=float, default=65.0)
    args = parser.parse_args()

    train(
        episodes=args.episodes,
        consist_preset=args.preset,
        grade_profile=args.grade,
        max_steps=args.max_steps,
        lr=args.lr,
        seed=args.seed,
        init_speed_kmh=args.init_speed_kmh,
    )
