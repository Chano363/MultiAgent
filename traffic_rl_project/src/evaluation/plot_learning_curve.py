"""
论文可视化：训练收敛曲线（多种子对比）。

解析 train_fleet.py 的日志格式：
    Ep 10 | Reward -774.0 (avg -800.0) | best -784.0 | peakCoupler 500kN | viol 0.0 | loss 0.05

用法：
    python src/evaluation/plot_learning_curve.py \
        --logdir outputs/train_logs --pattern "fleet_60ep_seed*_v512.log" \
        --out outputs/figures/learning_curve.png
"""

import os
import sys
import re
import glob
import argparse
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt


def parse_log(filepath):
    """解析日志，返回 (episodes, rewards) 列表。"""
    eps = []
    rewards = []
    with open(filepath, 'r', encoding='utf-8', errors='ignore') as f:
        for line in f:
            m = re.search(r'Ep (\d+)/\d+ \| Reward ([-\d.]+) \(avg ([-\d.]+)\)', line)
            if m:
                eps.append(int(m.group(1)))
                rewards.append(float(m.group(2)))
    return eps, rewards


def plot(logdir, pattern, out):
    files = sorted(glob.glob(os.path.join(logdir, pattern)))
    if not files:
        print(f"未找到日志: {os.path.join(logdir, pattern)}")
        return

    print(f"找到 {len(files)} 个日志文件")
    plt.figure(figsize=(9, 6))
    all_curves = []
    for i, fpath in enumerate(files):
        eps, rewards = parse_log(fpath)
        if not rewards:
            print(f"  跳过空日志: {os.path.basename(fpath)}")
            continue
        name = os.path.basename(fpath).replace('.log', '')
        # 提取 seed 号
        sm = re.search(r'seed(\d+)', name)
        label = f"seed={sm.group(1)}" if sm else name
        plt.plot(eps, rewards, '-o', markersize=3, linewidth=1.5, alpha=0.8, label=label)
        all_curves.append((eps, rewards))

    # 平均曲线
    if all_curves:
        # 对齐到相同 episodes（取最短或插值）
        min_len = min(len(r) for _, r in all_curves)
        base_eps = [e for e, _ in all_curves][0][:min_len]
        reward_matrix = np.array([r[:min_len] for _, r in all_curves])
        mean_r = reward_matrix.mean(axis=0)
        std_r = reward_matrix.std(axis=0)
        plt.plot(base_eps, mean_r, 'k-', linewidth=2.5, label='mean')
        plt.fill_between(base_eps, mean_r - std_r, mean_r + std_r, color='k', alpha=0.15)

    plt.xlabel('Episode')
    plt.ylabel('Episode Reward')
    plt.title('MAPPO 列间协同制动训练收敛曲线')
    plt.legend()
    plt.grid(alpha=0.3)
    plt.tight_layout()
    os.makedirs(os.path.dirname(out), exist_ok=True)
    plt.savefig(out, dpi=150)
    print(f"收敛曲线已保存: {out}")
    plt.close()


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--logdir', type=str, default='outputs/train_logs')
    parser.add_argument('--pattern', type=str, default='fleet_60ep_seed*_v512.log')
    parser.add_argument('--out', type=str, default='outputs/figures/learning_curve.png')
    args = parser.parse_args()
    plot(args.logdir, args.pattern, args.out)
