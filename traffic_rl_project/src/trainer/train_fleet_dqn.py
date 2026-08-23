"""
公平 DQN baseline 训练：分层架构下第2层用 DQN 学协同阈值偏移。

【与 M1（MAPPO 协同）完全同架构，只换第2层 RL 算法】
- 环境/obs/reward：与 train_fleet.py 相同（train_fleet_env，分层模式）
- 第1层：规则循环制动 + 车钩力安全层（HierarchicalController，与 M1/M3/M4 相同）
- 第2层：每列独立 DQN 输出离散 coor_adj ∈ [-1,1] → 阈值偏移
  （CoorDQNAgent，obs_dim=11，与 M1 的每列 obs 相同）

这回答审稿人"DQN 输是因为没协同/没安全层，还是 DQN 本身不如 MAPPO"：
- M-DQN-fair（本脚本） = 有安全层 + 有 DQN 协同 → 若仍不如 M1，归因到 RL 算法本身
- M-DQN（朴素，Zhang2024 式）= 无安全层 + 无协同 → 归因到缺约束（论文已说明）

用法：
  python src/trainer/train_fleet_dqn.py --episodes 200 --seed 0
"""
import sys
import os
import time
import argparse
import logging
from pathlib import Path

sys.path.append(str(Path(__file__).parent.parent.parent))

import numpy as np
import torch

logging.basicConfig(level=logging.INFO, format='%(message)s')
logger = logging.getLogger('TrainFleetDQN')

from src.environments.train_fleet_env import TrainFleetEnv
from src.algorithms.coor_dqn_agent import CoorDQNAgent


def set_seed(seed: int):
    np.random.seed(seed)
    torch.manual_seed(seed)
    if torch.cuda.is_available():
        torch.cuda.manual_seed(seed)


def main():
    parser = argparse.ArgumentParser(description='公平 DQN baseline 训练（分层阈值协同）')
    parser.add_argument('--episodes', type=int, default=200)
    parser.add_argument('--num_trains', type=int, default=3)
    parser.add_argument('--preset', type=str, default='10kt_1plus0')
    parser.add_argument('--grade', type=str, default='shuozhou_23800')
    parser.add_argument('--target_gap', type=float, default=100.0)
    parser.add_argument('--max_steps', type=int, default=300)
    parser.add_argument('--v_max', type=float, default=80.0 / 3.6)
    parser.add_argument('--v_min', type=float, default=40.0 / 3.6)
    parser.add_argument('--lr', type=float, default=1e-4)
    parser.add_argument('--batch_size', type=int, default=128)
    parser.add_argument('--device', type=str, default=None)
    parser.add_argument('--seed', type=int, default=0)
    parser.add_argument('--adj_coef', type=float, default=0.3,
                        help='协同阈值偏移缩放系数（与 M1 训练一致）')
    parser.add_argument('--eps_decay', type=float, default=0.995)
    parser.add_argument('--init_speed_kmh', type=float, default=65.0)
    parser.add_argument('--random_init_speed', action='store_true',
                        help='训练时随机化初始速度 [55,75]，增强泛化')
    parser.add_argument('--checkpoint_dir', type=str, default='outputs/checkpoints')
    parser.add_argument('--log_file', type=str, default=None)
    parser.add_argument('--resume', action='store_true',
                        help='从已有 checkpoint 续训（加载 Q 网络，eps 重置为 eps_start 以继续探索）')
    args = parser.parse_args()

    device = args.device or ('cuda' if torch.cuda.is_available() else 'cpu')
    set_seed(args.seed)

    env_cfg = {
        'num_trains': args.num_trains,
        'consist_preset': args.preset,
        'grade_profile': args.grade,
        'v_max': args.v_max,
        'v_min': args.v_min,
        'target_gap': args.target_gap,
        'max_steps': args.max_steps,
        'max_accel': 1.0,
        'use_coupler_constraint': True,
        'hierarchical': True,        # 分层模式（第1层规则循环制动 + 第2层协同）
        'adj_coef': args.adj_coef,
    }
    env = TrainFleetEnv(env_cfg)
    obs_dim = env.obs_dim  # 11 维（与 M1 每列 obs 相同）

    # 每列一个独立 DQN（多智能体 DQN 朴素公平形式）
    agents = [CoorDQNAgent(obs_dim=obs_dim, lr=args.lr, batch_size=args.batch_size,
                           eps_decay=args.eps_decay, device=device)
              for _ in range(args.num_trains)]
    # resume：加载已保存的 Q 网络继续训练（eps 重置以继续探索）
    if args.resume:
        for i, ag in enumerate(agents):
            cp = str(Path(args.checkpoint_dir) / f"coor_dqn_best_seed{args.seed}_train{i}.pt")
            if Path(cp).exists():
                ag.load(cp)
                ag.eps = ag.eps_start  # 重置探索
                logger.info(f"resume: 加载 {cp}")
            else:
                logger.warning(f"resume: 未找到 {cp}，从零开始")

    Path(args.checkpoint_dir).mkdir(parents=True, exist_ok=True)

    logger.info("=" * 70)
    logger.info("公平 DQN baseline 训练（分层阈值协同，与 M1 同架构）")
    logger.info(f"编队列数: {args.num_trains} | 限速[{args.v_min*3.6:.0f},{args.v_max*3.6:.0f}]km/h")
    logger.info(f"obs={obs_dim}维 | 离散协同动作={CoorDQNAgent.NUM_ACTIONS}档")
    logger.info(f"每列独立 DQN，seed={args.seed}，adj_coef={args.adj_coef}")
    logger.info("=" * 70)

    episode_rewards = []
    episode_peak = []
    episode_viol = []
    best_reward = float('-inf')
    start_time = time.time()

    for ep in range(args.episodes):
        if args.random_init_speed:
            init_speed = float(np.random.uniform(55.0, 75.0)) / 3.6
        else:
            init_speed = args.init_speed_kmh / 3.6
        obs, _ = env.reset(options={'speed': init_speed})
        done = False
        ep_reward = 0.0
        ep_peak = 0.0
        ep_viol = 0
        step = 0

        while not done and step < args.max_steps:
            # 每列独立 obs → 每列独立 DQN 输出 coor_adj
            coor = np.zeros((args.num_trains, 1), dtype=np.float32)
            for i in range(args.num_trains):
                oi = obs[i].flatten()  # 该列 11 维 obs
                ai = agents[i].select_action(oi)
                coor[i, 0] = agents[i].action_to_coor(ai)
            next_obs, reward, term, trunc, info = env.step(coor)
            done = term or trunc

            # 存储经验（每列独立 buffer）：存离散动作索引 ai
            for i in range(args.num_trains):
                oi = obs[i].flatten()
                ni = next_obs[i].flatten()
                # 探索时已 select_action 得到索引；此处重新取（一致性无碍，均 ε-greedy）
                ai = agents[i].select_action(oi)
                # 每列奖励 = 共享 reward（环境给的是列级总奖励；为简化，每列用同一 reward 学习）
                agents[i].store_transition(oi, ai, reward, ni, done)

            # 每列更新 DQN
            for i in range(args.num_trains):
                agents[i].update()

            ep_reward += reward
            ep_peak = max(ep_peak, info.get('coupler_force_peak', 0))
            ep_viol = info.get('coupler_limit_violations', 0)
            obs = next_obs
            step += 1

        episode_rewards.append(ep_reward)
        episode_peak.append(ep_peak / 1e3)
        episode_viol.append(ep_viol)
        if ep_reward > best_reward:
            best_reward = ep_reward
            for i, ag in enumerate(agents):
                ag.save(str(Path(args.checkpoint_dir) / f"coor_dqn_best_seed{args.seed}_train{i}.pt"))

        if (ep + 1) % 10 == 0 or ep == args.episodes - 1:
            recent = np.mean(episode_rewards[-10:])
            recent_peak = np.mean(episode_peak[-10:])
            recent_viol = np.mean(episode_viol[-10:])
            logger.info(
                f"Ep {ep+1}/{args.episodes} | Reward {ep_reward:+.1f} (avg {recent:+.1f}) | "
                f"best {best_reward:+.1f} | peakCoupler {recent_peak:.0f}kN | viol {recent_viol:.1f} | "
                f"eps {agents[0].eps:.3f}"
            )
            sys.stdout.flush()

    total_time = time.time() - start_time
    logger.info("=" * 70)
    logger.info(f"训练完成！耗时 {total_time:.1f}s ({total_time/60:.1f}min)")
    logger.info(f"最佳奖励: {best_reward:.2f} | 平均车钩力峰值: {np.mean(episode_peak[-10:]):.1f}kN")
    logger.info(f"模型已保存: {args.checkpoint_dir}/coor_dqn_best_seed{args.seed}_train*.pt")
    logger.info("=" * 70)

    if args.log_file:
        with open(args.log_file, 'a') as f:
            f.write(f"[seed{args.seed}] best={best_reward:.1f} peak_coupler={np.mean(episode_peak[-10:]):.0f}kN\n")


if __name__ == '__main__':
    main()
