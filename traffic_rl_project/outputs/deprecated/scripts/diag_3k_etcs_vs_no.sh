#!/bin/bash
# 快速验证：3000 步阶段 ETCS vs 无 ETCS 训练 reward 是否崩塌
# 20ep 直接 3000 步，不经过 curriculum 前阶段
set -u
source ~/miniconda3/etc/profile.d/conda.sh
conda activate traffic_rl
cd /mnt/d/Code/MultiAgent/traffic_rl_project

echo "############ A) 无 ETCS 3000步 20ep（对照前轮崩塌模式） ############"
timeout 900 python src/trainer/train_fleet.py \
    --episodes 20 --max_steps 3000 --seed 77 --hierarchical --adj_coef 0.1 \
    --checkpoint_dir /tmp/v3k_noetcs --results_dir /tmp/v3k_noetcs \
    > /tmp/v3k_noetcs.log 2>&1
echo "exit=$?"
grep -E 'Ep [0-9]+.*Reward' /tmp/v3k_noetcs.log | tail -6

echo ""
echo "############ B) ETCS 3000步 20ep ############"
timeout 900 python src/trainer/train_fleet.py \
    --episodes 20 --max_steps 3000 --seed 77 --hierarchical --adj_coef 0.1 --enable_etcs \
    --checkpoint_dir /tmp/v3k_etcs --results_dir /tmp/v3k_etcs \
    > /tmp/v3k_etcs.log 2>&1
echo "exit=$?"
grep -E 'Ep [0-9]+.*Reward' /tmp/v3k_etcs.log | tail -6
