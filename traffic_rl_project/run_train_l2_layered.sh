#!/bin/bash
# 第2层 M1 训练（最终分层架构：第1层规则循环制动 + 第2层 RL 阈值协同）
# RL 输出 coor_adj ∈ [-1,1]，映射为规则循环制动 v_max_adj/v_min_adj 阈值偏移
source /home/$(whoami)/miniconda3/etc/profile.d/conda.sh
conda activate traffic_rl
cd /mnt/d/Code/MultiAgent/traffic_rl_project
mkdir -p outputs/train_logs
python src/trainer/train_fleet.py \
    --episodes 200 \
    --num_trains 3 \
    --preset 10kt_1plus0 \
    --grade shuozhou_23800 \
    --max_steps 300 \
    --hierarchical \
    --adj_coef 0.3 \
    --entropy 0.001 \
    --seed 0 \
    > outputs/train_logs/l2_layered_200ep_seed0.log 2>&1
echo "L2 layered training done, exit=$?"
