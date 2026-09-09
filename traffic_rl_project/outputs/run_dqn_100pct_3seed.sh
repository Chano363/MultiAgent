#!/bin/bash
# 100% 动力学（Bug 3 修复后）DQN-fair baseline 重训 —— 论文主对比公平基线
#
# 历史 coor_dqn_best_seed*_train*.pt（8/23-24）在 75% 动力学下训练，需重训。
# 输出到 outputs/checkpoints_100pct/dqn/（不覆盖历史）。
# DQN 快（40ep 即收敛），与 M1 同架构同安全层，只换第2层算法。
set -u
cd "$(dirname "$0")/.."
source ~/miniconda3/etc/profile.d/conda.sh
conda activate traffic_rl

CKPT=outputs/checkpoints_100pct/dqn
mkdir -p "$CKPT"

for s in 0 1 2; do
    echo "[$(date +%H:%M:%S)] ===== DQN-fair 100pct seed$s 开始（40ep）====="
    python src/trainer/train_fleet_dqn.py \
        --episodes 40 --seed "$s" --num_trains 3 --adj_coef 0.3 \
        --checkpoint_dir "$CKPT" \
        > "outputs/train_100pct_dqn_seed${s}.log" 2>&1
    echo "[$(date +%H:%M:%S)] ===== DQN-fair 100pct seed$s 结束 ====="
done
echo "DQN-fair 100pct 3 seed 训练完成"
